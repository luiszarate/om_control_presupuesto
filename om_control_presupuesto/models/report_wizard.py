import base64
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .budget import MONTH_SELECTION
from .xlsx_export import build_budget_xlsx


REPORT_FILTER_FIELDS = ("budget_id", "cutoff_month", "category_id")
ISSUE_TYPE_SELECTION = [
    ("integration", "Integracion"),
    ("missing_date", "Sin fecha de recepcion"),
    ("missing_rate", "Sin tipo de cambio"),
]


def _ratio(percent):
    """The Odoo percentage widget multiplies by 100; the service returns 0-100 values."""
    return percent / 100.0 if percent is not None else 0.0


class ImagoBudgetReportWizard(models.Model):
    """Resumen mensual unico por usuario, recalculado al abrir o cambiar filtros."""

    _name = "imago.budget.report.wizard"
    _description = "Resumen de presupuesto Imago"
    _sql_constraints = [
        (
            "imago_budget_report_user_unique",
            "unique(user_id)",
            "Cada usuario tiene un solo resumen mensual.",
        ),
    ]

    user_id = fields.Many2one("res.users", index=True, readonly=True)
    budget_id = fields.Many2one("imago.budget", required=True)
    company_id = fields.Many2one(related="budget_id.company_id", readonly=True)
    currency_id = fields.Many2one(related="budget_id.currency_id", readonly=True)
    cutoff_month = fields.Selection(
        MONTH_SELECTION,
        string="Mes de corte",
        required=True,
        default="12",
        help="Ultimo mes considerado. La proyeccion extrapola linealmente el gasto de "
        "enero a este mes hasta diciembre: gasto / meses transcurridos x 12.",
    )
    category_id = fields.Many2one(
        "imago.budget.category",
        domain="[('company_id', '=', company_id)]",
    )
    include_subcategories = fields.Boolean(string="Incluir subcategorias", default=True)
    calculated_at = fields.Datetime(string="Actualizado", readonly=True)
    complete = fields.Boolean(string="Completo", readonly=True)
    issue_text = fields.Text(string="Incidencias", readonly=True)
    warning_text = fields.Text(string="Avisos", readonly=True)
    authorized_amount = fields.Monetary(string="Autorizado", readonly=True, currency_field="currency_id")
    spent_amount = fields.Monetary(string="Gastado en OC", readonly=True, currency_field="currency_id")
    available_amount = fields.Monetary(string="Restante", readonly=True, currency_field="currency_id")
    projection_amount = fields.Monetary(
        string="Proyeccion al cierre", readonly=True, currency_field="currency_id"
    )
    remaining_pct = fields.Float(string="Restante %", readonly=True, digits=(16, 4))
    projection_pct = fields.Float(string="Proyeccion %", readonly=True, digits=(16, 4))
    has_total_budget = fields.Boolean(readonly=True)
    has_total_projection = fields.Boolean(readonly=True)
    line_ids = fields.One2many("imago.budget.report.line", "wizard_id", readonly=True)
    issue_line_ids = fields.One2many(
        "imago.budget.report.issue", "wizard_id", string="Incidencias", readonly=True
    )
    active_issue_count = fields.Integer(readonly=True)
    dismissed_issue_count = fields.Integer(readonly=True)
    detail_line_ids = fields.One2many(
        "imago.budget.report.purchase.line", "wizard_id", readonly=True
    )
    purchase_line_ids = fields.Many2many("purchase.order.line", readonly=True)
    export_file = fields.Binary(readonly=True, attachment=False)
    export_filename = fields.Char(readonly=True)

    def init(self):
        """Adopt the latest legacy transient summary for each user on upgrade."""
        self.env.cr.execute("""
            WITH ranked AS (
                SELECT id, COALESCE(user_id, create_uid) AS owner_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY COALESCE(user_id, create_uid)
                           ORDER BY write_date DESC NULLS LAST, id DESC
                       ) AS position
                  FROM imago_budget_report_wizard
            )
            DELETE FROM imago_budget_report_wizard AS summary
                  USING ranked
             WHERE summary.id = ranked.id
               AND (ranked.position > 1 OR ranked.owner_id IS NULL)
        """)
        self.env.cr.execute("""
            UPDATE imago_budget_report_wizard
               SET user_id = create_uid
             WHERE user_id IS NULL
        """)

    # ------------------------------------------------------------------
    # Persistencia y recalculo
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(values, user_id=self.env.uid) for values in vals_list]
        wizards = super().create(vals_list)
        wizards._refresh()
        return wizards

    def write(self, values):
        if "user_id" in values:
            raise UserError(_("No se puede cambiar el usuario del resumen mensual."))
        result = super().write(values)
        if not self.env.context.get("imago_skip_refresh") and set(REPORT_FILTER_FIELDS) & set(values):
            self._refresh()
        return result

    @api.onchange(*REPORT_FILTER_FIELDS)
    def _onchange_report_filters(self):
        if self.category_id and self.category_id.company_id != self.budget_id.company_id:
            self.category_id = False
        if not self.budget_id or not self.cutoff_month:
            return
        report = self._get_service().get_report(
            self.budget_id, int(self.cutoff_month), self.category_id
        )
        # Vista previa inmediata; el detalle de compras se regenera al guardar.
        self.update(self._prepare_summary_values(report))

    def _get_service(self):
        return self.env["imago.budget.report.service"]

    def _refresh(self):
        for wizard in self:
            report = self._get_service().get_report(
                wizard.budget_id, int(wizard.cutoff_month), wizard.category_id
            )
            values = wizard._prepare_summary_values(report)
            values.update(wizard._prepare_detail_values(report))
            wizard.with_context(imago_skip_refresh=True).write(values)
        return True

    @api.model
    def _prepare_summary_values(self, report):
        totals = report["totals"]
        commands = [(5, 0, 0)]
        for row in report["rows"]:
            values = {
                "category_id": row["category_id"],
                "name": row["category_name"],
                "authorized_amount": row["authorized"],
                "spent_amount": row["spent"],
                "available_amount": row["available"] or 0.0,
                "remaining_pct": _ratio(row["remaining_pct"]),
                "projection_amount": row["projection"] or 0.0,
                "projection_pct": _ratio(row["projection_pct"]),
                "status": row["status"],
                "complete": report["complete"],
                "has_budget": row["remaining_pct"] is not None,
                "has_projection": row["projection"] is not None,
            }
            for month, amount in enumerate(row["monthly"], 1):
                values["month_%02d" % month] = amount
            commands.append((0, 0, values))
        issue_commands = [(5, 0, 0)]
        for issue in report["issue_items"] + report["dismissed_issue_items"]:
            issue_commands.append(
                (
                    0,
                    0,
                    {
                        "name": issue["title"],
                        "issue_type": issue["type"],
                        "hint": issue["hint"],
                        "details": "\n".join(issue["details"]),
                        "item_keys": json.dumps(issue["item_keys"]),
                        "dismissed": issue["dismissed"],
                    },
                )
            )
        return {
            "calculated_at": fields.Datetime.now(),
            "complete": report["complete"],
            "issue_text": "\n".join(report["issues"]) or False,
            "warning_text": "\n".join(report["warnings"]) or False,
            "authorized_amount": totals["authorized"],
            "spent_amount": totals["spent"],
            "available_amount": totals["available"] or 0.0,
            "projection_amount": totals["projection"] or 0.0,
            "remaining_pct": _ratio(totals["remaining_pct"]),
            "projection_pct": _ratio(totals["projection_pct"]),
            "has_total_budget": totals["remaining_pct"] is not None,
            "has_total_projection": totals["projection"] is not None,
            "line_ids": commands,
            "issue_line_ids": issue_commands,
            "active_issue_count": len(report["issue_items"]),
            "dismissed_issue_count": len(report["dismissed_issue_items"]),
        }

    @api.model
    def _prepare_detail_values(self, report):
        detail_commands = [(5, 0, 0)]
        for detail in report["details"]:
            detail_commands.append(
                (
                    0,
                    0,
                    {
                        "purchase_line_id": detail["purchase_line_id"],
                        "order_id": detail["order_id"],
                        "confirmation_date": detail["confirmation_date"],
                        "month": str(detail["month"]),
                        "partner_id": detail["partner_id"],
                        "description": detail["description"],
                        "project_id": detail["project_id"],
                        "category_id": detail["category_id"],
                        "subcategory_id": detail["subcategory_id"],
                        "original_currency_id": detail["currency_id"],
                        "subtotal_amount": detail["subtotal_amount"],
                        "tax_amount": detail["tax_amount"],
                        "original_amount": detail["original_amount"],
                        "rate": detail["rate"] or 0.0,
                        "converted_amount": detail["converted_amount"] or 0.0,
                        "has_conversion": detail["converted_amount"] is not None,
                        "inclusion_status": detail["status"],
                    },
                )
            )
        return {
            "detail_line_ids": detail_commands,
            "purchase_line_ids": [(6, 0, report["purchase_line_ids"])],
        }

    # ------------------------------------------------------------------
    # Resumen unico por usuario
    # ------------------------------------------------------------------
    @api.model
    def _get_user_summary(self, filters=None):
        """Return the caller's summary, applying ``filters`` when given.

        Without filters the last selection is kept, so the menu always opens the same
        refreshed summary instead of an empty form.
        """
        filters = dict(filters or {})
        service = self._get_service()
        # Serializa las primeras aperturas simultaneas del mismo usuario.
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s, %s)", (0x494D474F, self.env.uid))
        wizard = self.search([("user_id", "=", self.env.uid)], limit=1)
        budget_model = self.env["imago.budget"]

        budget = budget_model
        if filters.get("budget_id"):
            budget = budget_model.search([("id", "=", int(filters["budget_id"]))], limit=1)
        elif wizard:
            budget = budget_model.search([("id", "=", wizard.budget_id.id)], limit=1)
        budget = budget or service._default_budget()
        if not budget:
            raise UserError(_("No hay presupuestos accesibles."))

        same_budget = wizard and wizard.budget_id == budget
        if filters.get("cutoff_month"):
            cutoff_month = str(int(filters["cutoff_month"]))
        elif same_budget:
            cutoff_month = wizard.cutoff_month
        else:
            cutoff_month = str(service._default_cutoff_month(budget))

        if "category_id" in filters:
            category_id = int(filters["category_id"] or 0) or False
        else:
            category_id = wizard.category_id.id if same_budget else False

        values = {"budget_id": budget.id, "cutoff_month": cutoff_month, "category_id": category_id}
        if not wizard:
            return self.create(values)
        wizard.with_context(imago_skip_refresh=True).write(values)
        wizard._refresh()
        return wizard

    def _summary_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Resumen mensual"),
            "res_model": self._name,
            "res_id": self.id,
            "views": [(self.env.ref("om_control_presupuesto.view_imago_budget_report_form").id, "form")],
            "view_mode": "form",
            "target": "main",
            "context": {"form_view_initial_mode": "edit"},
        }

    @api.model
    def action_open_summary(self, filters=None):
        return self._get_user_summary(filters)._summary_action()

    @api.model
    def get_dashboard_data(self, budget_id=False, cutoff_month=False, category_id=False):
        return self._get_service().get_dashboard_data(budget_id, cutoff_month, category_id)

    @api.model
    def action_open_purchase_detail(self, filters=None):
        return self._get_user_summary(filters).action_view_purchase_lines()

    @api.model
    def action_export_summary(self, filters=None):
        return self._get_user_summary(filters).action_export_xlsx()

    @api.model
    def dismiss_report_issue(self, budget_id, item_keys, name=False):
        return self._get_service().dismiss_issue(budget_id, item_keys, name)

    @api.model
    def restore_report_issue(self, budget_id, item_keys):
        return self._get_service().restore_issue(budget_id, item_keys)

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------
    def action_calculate(self):
        self.ensure_one()
        self._refresh()
        return {"type": "ir.actions.act_window_close"}

    def action_view_issues(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Incidencias del reporte"),
            "res_model": "imago.budget.report.issue",
            "view_mode": "tree,form",
            "domain": [("wizard_id", "=", self.id)],
            "context": {
                "create": False,
                "search_default_active": 1 if self.active_issue_count else 0,
            },
        }

    def action_view_purchase_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Detalle de compras"),
            "res_model": "imago.budget.report.purchase.line",
            "view_mode": "tree,form",
            "domain": [("wizard_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_export_xlsx(self):
        self.ensure_one()
        report = self._get_service().get_report(
            self.budget_id, int(self.cutoff_month), self.category_id
        )
        content = build_budget_xlsx(
            self.env,
            self.budget_id,
            report,
            include_subcategories=self.include_subcategories,
        )
        filename = "presupuesto_%s_%02d.xlsx" % (
            self.budget_id.year,
            int(self.cutoff_month),
        )
        self.with_context(imago_skip_refresh=True).write(
            {
                "export_file": base64.b64encode(content),
                "export_filename": filename,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=%s&id=%s&field=export_file&filename_field=export_filename&download=true"
            % (self._name, self.id),
            "target": "self",
        }


class ImagoBudgetReportLine(models.Model):
    _name = "imago.budget.report.line"
    _description = "Renglon de resumen de presupuesto Imago"
    _order = "id"

    wizard_id = fields.Many2one("imago.budget.report.wizard", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    category_id = fields.Many2one("imago.budget.category", readonly=True)
    name = fields.Char(string="Categoria", readonly=True)
    authorized_amount = fields.Monetary(string="Autorizado", readonly=True, currency_field="currency_id")
    spent_amount = fields.Monetary(string="Gastado", readonly=True, currency_field="currency_id")
    available_amount = fields.Monetary(string="Restante", readonly=True, currency_field="currency_id")
    remaining_pct = fields.Float(string="Restante %", readonly=True, digits=(16, 4))
    projection_amount = fields.Monetary(string="Proyeccion", readonly=True, currency_field="currency_id")
    projection_pct = fields.Float(string="Proyeccion %", readonly=True, digits=(16, 4))
    status = fields.Selection(
        [
            ("incomplete", "Incompleto"),
            ("unbudgeted", "Sin presupuesto"),
            ("over", "Excedido"),
            ("risk", "Riesgo al cierre"),
            ("within", "Dentro del presupuesto"),
        ],
        string="Estado",
        readonly=True,
    )
    complete = fields.Boolean(readonly=True)
    has_budget = fields.Boolean(readonly=True)
    has_projection = fields.Boolean(readonly=True)
    month_01 = fields.Monetary(string="Ene", readonly=True, currency_field="currency_id")
    month_02 = fields.Monetary(string="Feb", readonly=True, currency_field="currency_id")
    month_03 = fields.Monetary(string="Mar", readonly=True, currency_field="currency_id")
    month_04 = fields.Monetary(string="Abr", readonly=True, currency_field="currency_id")
    month_05 = fields.Monetary(string="May", readonly=True, currency_field="currency_id")
    month_06 = fields.Monetary(string="Jun", readonly=True, currency_field="currency_id")
    month_07 = fields.Monetary(string="Jul", readonly=True, currency_field="currency_id")
    month_08 = fields.Monetary(string="Ago", readonly=True, currency_field="currency_id")
    month_09 = fields.Monetary(string="Sep", readonly=True, currency_field="currency_id")
    month_10 = fields.Monetary(string="Oct", readonly=True, currency_field="currency_id")
    month_11 = fields.Monetary(string="Nov", readonly=True, currency_field="currency_id")
    month_12 = fields.Monetary(string="Dic", readonly=True, currency_field="currency_id")


class ImagoBudgetReportIssue(models.Model):
    _name = "imago.budget.report.issue"
    _description = "Incidencia de resumen de presupuesto Imago"
    _order = "dismissed, id"

    wizard_id = fields.Many2one(
        "imago.budget.report.wizard", required=True, index=True, ondelete="cascade"
    )
    budget_id = fields.Many2one(related="wizard_id.budget_id", readonly=True)
    name = fields.Char(string="Incidencia", readonly=True)
    issue_type = fields.Selection(ISSUE_TYPE_SELECTION, string="Tipo", readonly=True)
    hint = fields.Char(string="Como resolver", readonly=True)
    details = fields.Text(string="Detalle", readonly=True)
    item_keys = fields.Text(readonly=True)
    dismissed = fields.Boolean(string="Descartada", readonly=True)

    def _item_keys(self):
        self.ensure_one()
        try:
            keys = json.loads(self.item_keys or "[]")
        except ValueError:
            keys = []
        if not isinstance(keys, list) or not keys:
            raise UserError(_("La incidencia ya no es valida; actualice el resumen."))
        return keys

    def _after_change(self):
        # Las lineas se regeneran; al no devolver una accion, la lista se recarga
        # sin apilar otra miga de pan.
        self.wizard_id._refresh()
        return True

    def action_dismiss(self):
        self.ensure_one()
        self.env["imago.budget.issue.dismissal"].dismiss_keys(
            self.budget_id, self._item_keys(), self.name
        )
        return self._after_change()

    def action_restore(self):
        self.ensure_one()
        self.env["imago.budget.issue.dismissal"].restore_keys(self.budget_id, self._item_keys())
        return self._after_change()


class ImagoBudgetReportPurchaseLine(models.Model):
    _name = "imago.budget.report.purchase.line"
    _description = "Detalle de compra para presupuesto Imago"
    _order = "confirmation_date, order_id, purchase_line_id"

    wizard_id = fields.Many2one(
        "imago.budget.report.wizard", required=True, index=True, ondelete="cascade"
    )
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    purchase_line_id = fields.Many2one("purchase.order.line", readonly=True)
    order_id = fields.Many2one("purchase.order", string="OC", readonly=True)
    confirmation_date = fields.Datetime(string="Fecha de recepcion", readonly=True)
    month = fields.Selection(MONTH_SELECTION, readonly=True)
    partner_id = fields.Many2one("res.partner", string="Proveedor", readonly=True)
    description = fields.Text(readonly=True)
    project_id = fields.Many2one("project.project", readonly=True)
    category_id = fields.Many2one("imago.budget.category", readonly=True)
    subcategory_id = fields.Many2one("imago.budget.category", readonly=True)
    original_currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)
    subtotal_amount = fields.Float(string="Subtotal original", readonly=True, digits=(16, 2))
    tax_amount = fields.Float(string="Impuestos", readonly=True, digits=(16, 2))
    original_amount = fields.Float(string="Total original", readonly=True, digits=(16, 2))
    rate = fields.Float(string="TC", readonly=True, digits=(16, 6))
    converted_amount = fields.Monetary(string="Importe MXN", readonly=True, currency_field="currency_id")
    has_conversion = fields.Boolean(readonly=True)
    inclusion_status = fields.Selection(
        [
            ("included", "Incluida"),
            ("unclassified", "Sin clasificar"),
            ("missing_rate", "Pendiente de conversion"),
            ("excluded_secihti", "Excluida por SECIHTI"),
        ],
        readonly=True,
    )

    def action_open_purchase_order(self):
        self.ensure_one()
        self.order_id.check_access_rights("read")
        self.order_id.check_access_rule("read")
        return {
            "type": "ir.actions.act_window",
            "name": self.order_id.display_name,
            "res_model": "purchase.order",
            "res_id": self.order_id.id,
            "views": [(False, "form")],
            "target": "current",
        }
