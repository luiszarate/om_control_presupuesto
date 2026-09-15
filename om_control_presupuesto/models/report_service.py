from collections import defaultdict
from datetime import datetime

import pytz

from odoo import _, fields, models


class ImagoBudgetReportService(models.AbstractModel):
    _name = "imago.budget.report.service"
    _description = "Motor de calculo de presupuesto Imago"

    def _integration_status(self):
        purchase_fields = self.env["purchase.order"]._fields
        project_field = purchase_fields.get("project_id")
        if not project_field or project_field.type != "many2one" or project_field.comodel_name != "project.project":
            return {
                "project": "error",
                "secihti": "unknown",
                "error": _("No se encontro purchase.order.project_id compatible."),
            }

        sec_field = purchase_fields.get("sec_project_id")
        if sec_field:
            if sec_field.type == "many2one" and sec_field.comodel_name == "sec.project":
                return {"project": "ready", "secihti": "ready", "error": False}
            return {
                "project": "ready",
                "secihti": "error",
                "error": _("purchase.order.sec_project_id no tiene la integracion esperada."),
            }

        module_installed = bool(
            self.env["ir.module.module"].sudo().search_count(
                [("name", "=", "secihti_budget"), ("state", "=", "installed")]
            )
        )
        if module_installed:
            return {
                "project": "ready",
                "secihti": "error",
                "error": _("secihti_budget esta instalado pero su campo de compra no fue reconocido."),
            }
        return {"project": "ready", "secihti": "not_installed", "error": False}

    @staticmethod
    def _period_utc(year, cutoff_month, timezone):
        zone = pytz.timezone(timezone)
        start_local = zone.localize(datetime(year, 1, 1))
        if cutoff_month == 12:
            end_local = zone.localize(datetime(year + 1, 1, 1))
        else:
            end_local = zone.localize(datetime(year, cutoff_month + 1, 1))
        return (
            start_local.astimezone(pytz.UTC).replace(tzinfo=None),
            end_local.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    @staticmethod
    def _month_in_timezone(value, timezone):
        value = fields.Datetime.to_datetime(value)
        return pytz.UTC.localize(value).astimezone(pytz.timezone(timezone)).month

    @staticmethod
    def _metrics(authorized, spent, cutoff_month, complete=True, future=False):
        available = authorized - spent if complete else None
        remaining_pct = None
        projection = None
        projection_pct = None
        deviation = None
        if complete and authorized:
            remaining_pct = available / authorized * 100.0
        if complete and cutoff_month and not future:
            projection = spent / cutoff_month * 12.0
            deviation = projection - authorized
            if authorized:
                projection_pct = projection / authorized * 100.0

        if not complete:
            status = "incomplete"
        elif not authorized and spent:
            status = "unbudgeted"
        elif spent > authorized:
            status = "over"
        elif projection is not None and projection > authorized:
            status = "risk"
        else:
            status = "within"
        return {
            "authorized": authorized,
            "spent": spent,
            "available": available,
            "remaining_pct": remaining_pct,
            "projection": projection,
            "projection_pct": projection_pct,
            "deviation": deviation,
            "status": status,
        }

    def get_report(self, budget, cutoff_month, category=None):
        budget.ensure_one()
        cutoff_month = int(cutoff_month)
        if cutoff_month < 1 or cutoff_month > 12:
            raise ValueError("cutoff_month must be between 1 and 12")

        integration = self._integration_status()
        issues = []
        if integration["error"]:
            issues.append(integration["error"])

        start_utc, end_utc = self._period_utc(budget.year, cutoff_month, budget.timezone)
        order_domain = [
            ("company_id", "=", budget.company_id.id),
            ("state", "in", ("purchase", "done")),
        ]
        missing_date_domain = order_domain + [("date_approve", "=", False)]
        if integration["secihti"] == "ready":
            missing_date_domain.append(("sec_project_id", "=", False))
        missing_date_orders = self.env["purchase.order"].search(missing_date_domain)
        if missing_date_orders:
            issues.append(
                _("%s ordenes confirmadas no tienen fecha de confirmacion.")
                % len(missing_date_orders)
            )

        line_domain = [
            ("order_id.company_id", "=", budget.company_id.id),
            ("order_id.state", "in", ("purchase", "done")),
            ("order_id.date_approve", ">=", fields.Datetime.to_string(start_utc)),
            ("order_id.date_approve", "<", fields.Datetime.to_string(end_utc)),
        ]
        if "display_type" in self.env["purchase.order.line"]._fields:
            line_domain.append(("display_type", "=", False))
        purchase_lines = self.env["purchase.order.line"].search(line_domain, order="order_id, id")
        rules = {rule.project_id.id: rule for rule in budget.project_rule_ids}
        rates = {
            (rate.currency_id.id, int(rate.month)): rate.rate
            for rate in budget.exchange_rate_ids
        }

        top_categories = self.env["imago.budget.category"].with_context(active_test=False).search(
            [
                ("company_id", "=", budget.company_id.id),
                ("parent_id", "=", False),
                ("id", "in", budget.line_ids.mapped("category_id.parent_id").ids
                 + budget.line_ids.filtered(lambda item: not item.category_id.parent_id).mapped("category_id").ids
                 + budget.project_rule_ids.mapped("category_id").ids),
            ],
            order="sequence, name, id",
        )
        if category:
            top_id = category.parent_id.id or category.id
            top_categories = top_categories.filtered(lambda item: item.id == top_id)

        authorized_by_top = defaultdict(float)
        for budget_line in budget.line_ids.filtered(lambda item: item.amount_status == "authorized"):
            top = budget_line.category_id.parent_id or budget_line.category_id
            selected = not category or (
                budget_line.category_id == category
                if category.parent_id
                else top == category
            )
            if selected:
                authorized_by_top[top.id] += budget_line.amount

        spent_by_top = defaultdict(float)
        spent_by_subcategory = defaultdict(float)
        monthly_by_top = defaultdict(lambda: [0.0] * 12)
        monthly_by_subcategory = defaultdict(lambda: [0.0] * 12)
        details = []
        pending = defaultdict(lambda: {"count": 0, "amount": 0.0})
        unclassified = 0.0
        unclassified_monthly = [0.0] * 12

        for line in purchase_lines:
            order = line.order_id
            month = self._month_in_timezone(order.date_approve, budget.timezone)
            currency = order.currency_id
            original_amount = line.price_total
            rate = 1.0 if currency == budget.currency_id else rates.get((currency.id, month))
            project = getattr(order, "project_id", False)
            rule = rules.get(project.id) if project else False
            top_category = rule.category_id if rule else False
            subcategory = rule.subcategory_id if rule else False
            excluded_secihti = (
                integration["secihti"] == "ready"
                and bool(getattr(order, "sec_project_id", False))
            )

            if category:
                selected_top = category.parent_id or category
                if not top_category or top_category != selected_top:
                    continue
                if category.parent_id and subcategory != category:
                    continue

            detail = {
                "purchase_line_id": line.id,
                "order_id": order.id,
                "order_name": order.name,
                "confirmation_date": fields.Datetime.to_string(order.date_approve),
                "month": month,
                "partner_id": order.partner_id.id,
                "partner_name": order.partner_id.display_name,
                "description": line.name,
                "project_id": project.id if project else False,
                "project_name": project.display_name if project else "",
                "category_id": top_category.id if top_category else False,
                "category_name": top_category.display_name if top_category else "",
                "subcategory_id": subcategory.id if subcategory else False,
                "subcategory_name": subcategory.display_name if subcategory else "",
                "currency_id": currency.id,
                "currency_name": currency.name,
                "subtotal_amount": line.price_subtotal,
                "tax_amount": line.price_total - line.price_subtotal,
                "original_amount": original_amount,
                "rate": rate,
                "converted_amount": None,
                "status": "included",
            }
            if excluded_secihti:
                detail["rate"] = None
                detail["status"] = "excluded_secihti"
                details.append(detail)
                continue
            if rate is None:
                key = (currency.name, month)
                pending[key]["count"] += 1
                pending[key]["amount"] += original_amount
                detail["status"] = "missing_rate"
                details.append(detail)
                continue

            converted = budget.currency_id.round(original_amount * rate)
            detail["converted_amount"] = converted
            if not top_category:
                detail["status"] = "unclassified"
            details.append(detail)
            if top_category:
                spent_by_top[top_category.id] += converted
                monthly_by_top[top_category.id][month - 1] += converted
                sub_key = (top_category.id, subcategory.id if subcategory else False)
                spent_by_subcategory[sub_key] += converted
                monthly_by_subcategory[sub_key][month - 1] += converted
            else:
                unclassified += converted
                unclassified_monthly[month - 1] += converted

        for (currency_name, month), values in sorted(pending.items()):
            issues.append(
                _("%s lineas %s del mes %s sin convertir (%s %s).")
                % (
                    values["count"],
                    currency_name,
                    month,
                    currency_name,
                    values["amount"],
                )
            )

        today = fields.Date.context_today(self)
        future = budget.year > today.year
        complete = not issues
        rows = []
        for top in top_categories:
            metrics = self._metrics(
                authorized_by_top[top.id],
                spent_by_top[top.id],
                cutoff_month,
                complete=complete,
                future=future,
            )
            selected_child = category if category and category.parent_id else False
            metrics.update(
                {
                    "category_id": selected_child.id if selected_child else top.id,
                    "category_name": selected_child.display_name if selected_child else top.name,
                    "monthly": monthly_by_top[top.id],
                    "children": [],
                }
            )
            child_categories = top.with_context(active_test=False).child_ids.sorted(
                key=lambda item: (item.sequence, item.name, item.id)
            )
            for child in child_categories:
                if selected_child:
                    continue
                authorized = sum(
                    budget.line_ids.filtered(
                        lambda item: item.category_id == child
                        and item.amount_status == "authorized"
                    ).mapped("amount")
                )
                child_key = (top.id, child.id)
                child_metrics = self._metrics(
                    authorized,
                    spent_by_subcategory[child_key],
                    cutoff_month,
                    complete=complete,
                    future=future,
                )
                child_metrics.update(
                    {
                        "category_id": child.id,
                        "category_name": child.name,
                        "monthly": monthly_by_subcategory[child_key],
                    }
                )
                metrics["children"].append(child_metrics)
            direct_key = (top.id, False)
            if not selected_child and child_categories and spent_by_subcategory[direct_key]:
                direct_metrics = self._metrics(
                    0.0,
                    spent_by_subcategory[direct_key],
                    cutoff_month,
                    complete=complete,
                    future=future,
                )
                direct_metrics.update(
                    {
                        "category_id": False,
                        "category_name": _("Sin subcategoria"),
                        "monthly": monthly_by_subcategory[direct_key],
                    }
                )
                metrics["children"].append(direct_metrics)
            rows.append(metrics)

        if not category:
            unclassified_metrics = self._metrics(
                0.0, unclassified, cutoff_month, complete=complete, future=future
            )
            unclassified_metrics.update(
                {
                    "category_id": False,
                    "category_name": _("Sin clasificar"),
                    "monthly": unclassified_monthly,
                }
            )
            rows.append(unclassified_metrics)

        total_authorized = sum(row["authorized"] for row in rows)
        total_spent = sum(row["spent"] for row in rows)
        totals = self._metrics(
            total_authorized,
            total_spent,
            cutoff_month,
            complete=complete,
            future=future,
        )
        totals["monthly"] = [sum(row["monthly"][month] for row in rows) for month in range(12)]

        warnings = [_("Resultado limitado a las ordenes de compra visibles para el usuario.")]
        if budget.year == today.year and cutoff_month == today.month:
            warnings.append(_("Mes en curso; proyeccion provisional."))
        if future:
            warnings.append(_("Ejercicio futuro; la proyeccion no aplica."))

        return {
            "budget_id": budget.id,
            "year": budget.year,
            "cutoff_month": cutoff_month,
            "currency_id": budget.currency_id.id,
            "currency_name": budget.currency_id.name,
            "complete": complete,
            "issues": issues,
            "warnings": warnings,
            "integration": integration,
            "rows": rows,
            "totals": totals,
            "details": details,
            "purchase_line_ids": [detail["purchase_line_id"] for detail in details],
            "missing_date_order_ids": missing_date_orders.ids,
        }

    def get_dashboard_data(self, budget_id=False, cutoff_month=False, category_id=False):
        """RPC entrypoint. It deliberately uses the caller's purchase access rules."""
        budgets = self.env["imago.budget"].search([], order="year desc, company_id, id desc")
        budget = self.env["imago.budget"]
        if budget_id:
            budget = budgets.filtered(lambda item: item.id == int(budget_id))[:1]
        if not budget:
            budget = budgets[:1]
        budget_options = [
            {
                "id": item.id,
                "name": item.display_name,
                "year": item.year,
                "company_id": item.company_id.id,
                "company_name": item.company_id.display_name,
                "state": item.state,
            }
            for item in budgets
        ]
        if not budget:
            return {
                "budget_options": budget_options,
                "category_options": [],
                "report": False,
                "message": _("No hay presupuestos accesibles."),
            }

        today = fields.Date.context_today(self)
        if cutoff_month:
            selected_month = int(cutoff_month)
        elif budget.year < today.year:
            selected_month = 12
        elif budget.year > today.year:
            selected_month = 12
        else:
            selected_month = max(today.month - 1, 1)

        categories = self.env["imago.budget.category"].with_context(active_test=False).search(
            [("company_id", "=", budget.company_id.id)], order="parent_path, sequence, name"
        )
        category = categories.filtered(lambda item: item.id == int(category_id or 0))[:1]
        report = self.get_report(budget, selected_month, category=category)
        if budget.year == today.year and today.month == 1 and not cutoff_month:
            report["warnings"].insert(
                0, _("Sin meses completos; enero se muestra como corte provisional.")
            )

        cumulative = []
        observed = 0.0
        authorized = report["totals"]["authorized"]
        projected_total = report["totals"]["projection"]
        for month in range(1, 13):
            if month <= selected_month:
                observed += report["totals"]["monthly"][month - 1]
                observed_value = observed
            else:
                observed_value = None
            projected_value = None
            if projected_total is not None and month >= selected_month:
                projected_value = projected_total / 12.0 * month
            cumulative.append(
                {
                    "month": month,
                    "observed": observed_value,
                    "reference": authorized / 12.0 * month,
                    "projected": projected_value,
                }
            )
        report["cumulative"] = cumulative
        return {
            "budget_options": budget_options,
            "category_options": [
                {"id": item.id, "name": item.display_name} for item in categories
            ],
            "selected_budget_id": budget.id,
            "selected_category_id": category.id if category else False,
            "selected_cutoff_month": selected_month,
            "report": report,
            "message": False,
        }
