import json

from odoo import _, api, fields, models


class ImagoBudgetSnapshot(models.Model):
    _name = "imago.budget.snapshot"
    _description = "Fotografia de cierre de presupuesto Imago"
    _order = "version desc"

    name = fields.Char(required=True, readonly=True)
    budget_id = fields.Many2one("imago.budget", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="budget_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="budget_id.currency_id", store=True)
    version = fields.Integer(required=True, readonly=True)
    snapshot_date = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", required=True, readonly=True, default=lambda self: self.env.user)
    cutoff_month = fields.Integer(required=True, readonly=True)
    authorized_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    spent_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    available_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    projection_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    payload = fields.Text(readonly=True)
    line_ids = fields.One2many("imago.budget.snapshot.line", "snapshot_id", readonly=True)
    purchase_line_ids = fields.One2many(
        "imago.budget.snapshot.purchase.line", "snapshot_id", readonly=True
    )

    _sql_constraints = [
        (
            "budget_version_unique",
            "unique(budget_id, version)",
            "La version de fotografia ya existe para este presupuesto.",
        )
    ]

    @api.model
    def create_from_report(self, budget, report):
        version = self.search_count([("budget_id", "=", budget.id)]) + 1
        totals = report["totals"]
        snapshot = self.create(
            {
                "name": _("Cierre %s v%s") % (budget.year, version),
                "budget_id": budget.id,
                "version": version,
                "cutoff_month": report["cutoff_month"],
                "authorized_amount": totals["authorized"],
                "spent_amount": totals["spent"],
                "available_amount": totals["available"],
                "projection_amount": totals["projection"],
                "payload": json.dumps(
                    {
                        "integration": report["integration"],
                        "warnings": report["warnings"],
                        "issues": report["issues"],
                        "dismissed_issues": [
                            issue["title"] for issue in report["dismissed_issue_items"]
                        ],
                        "policies": {
                            "timezone": budget.timezone,
                            "amount": budget.amount_policy,
                            "date": budget.date_policy,
                        },
                        "budget_lines": [
                            {
                                "category_id": line.category_id.id,
                                "category": line.category_id.display_name,
                                "amount_status": line.amount_status,
                                "amount": line.amount,
                                "note": line.note,
                            }
                            for line in budget.line_ids
                        ],
                        "project_rules": [
                            {
                                "project_id": rule.project_id.id,
                                "project": rule.project_id.display_name,
                                "category_id": rule.category_id.id,
                                "subcategory_id": rule.subcategory_id.id or False,
                            }
                            for rule in budget.project_rule_ids
                        ],
                        "exchange_rates": [
                            {
                                "currency": rate.currency_id.name,
                                "month": int(rate.month),
                                "rate": rate.rate,
                            }
                            for rate in budget.exchange_rate_ids
                        ],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        )
        summary_values = []
        for row in report["rows"]:
            summary_values.append(
                {
                    "snapshot_id": snapshot.id,
                    "category_id": row["category_id"],
                    "category_name": row["category_name"],
                    "authorized_amount": row["authorized"],
                    "spent_amount": row["spent"],
                    "available_amount": row["available"],
                    "projection_amount": row["projection"],
                    "status": row["status"],
                    "monthly_payload": json.dumps(row["monthly"]),
                }
            )
        self.env["imago.budget.snapshot.line"].create(summary_values)

        detail_values = []
        for detail in report["details"]:
            detail_values.append(
                {
                    "snapshot_id": snapshot.id,
                    "purchase_line_id": detail["purchase_line_id"],
                    "order_id": detail["order_id"],
                    "order_name": detail["order_name"],
                    "confirmation_date": detail["confirmation_date"],
                    "month": detail["month"],
                    "partner_name": detail["partner_name"],
                    "description": detail["description"],
                    "project_id": detail["project_id"],
                    "category_id": detail["category_id"],
                    "subcategory_id": detail["subcategory_id"],
                    "original_currency_name": detail["currency_name"],
                    "subtotal_amount": detail["subtotal_amount"],
                    "tax_amount": detail["tax_amount"],
                    "original_amount": detail["original_amount"],
                    "rate": detail["rate"] or 0.0,
                    "converted_amount": detail["converted_amount"] or 0.0,
                    "inclusion_status": detail["status"],
                }
            )
        self.env["imago.budget.snapshot.purchase.line"].create(detail_values)
        return snapshot


class ImagoBudgetSnapshotLine(models.Model):
    _name = "imago.budget.snapshot.line"
    _description = "Resumen congelado de presupuesto Imago"
    _order = "id"

    snapshot_id = fields.Many2one(
        "imago.budget.snapshot", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="snapshot_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="snapshot_id.currency_id", store=True)
    category_id = fields.Many2one("imago.budget.category", ondelete="set null", readonly=True)
    category_name = fields.Char(required=True, readonly=True)
    authorized_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    spent_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    available_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    projection_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    status = fields.Char(readonly=True)
    monthly_payload = fields.Text(readonly=True)


class ImagoBudgetSnapshotPurchaseLine(models.Model):
    _name = "imago.budget.snapshot.purchase.line"
    _description = "Compra congelada de presupuesto Imago"
    _order = "confirmation_date, order_name, id"

    snapshot_id = fields.Many2one(
        "imago.budget.snapshot", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="snapshot_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="snapshot_id.currency_id", store=True)
    purchase_line_id = fields.Many2one("purchase.order.line", ondelete="set null", readonly=True)
    order_id = fields.Many2one("purchase.order", ondelete="set null", readonly=True)
    order_name = fields.Char(readonly=True)
    confirmation_date = fields.Datetime(string="Fecha de recepcion", readonly=True)
    month = fields.Integer(readonly=True)
    partner_name = fields.Char(readonly=True)
    description = fields.Text(readonly=True)
    project_id = fields.Many2one("project.project", ondelete="set null", readonly=True)
    category_id = fields.Many2one("imago.budget.category", ondelete="set null", readonly=True)
    subcategory_id = fields.Many2one("imago.budget.category", ondelete="set null", readonly=True)
    original_currency_name = fields.Char(string="Moneda original", readonly=True)
    subtotal_amount = fields.Float(string="Subtotal original", readonly=True, digits=(16, 2))
    tax_amount = fields.Float(string="Impuestos", readonly=True, digits=(16, 2))
    original_amount = fields.Float(readonly=True, digits=(16, 2))
    rate = fields.Float(readonly=True, digits=(16, 6))
    converted_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    inclusion_status = fields.Selection(
        [
            ("included", "Incluida"),
            ("unclassified", "Sin clasificar"),
            ("missing_rate", "Sin tipo de cambio"),
            ("excluded_secihti", "Excluida por SECIHTI"),
        ],
        readonly=True,
    )
