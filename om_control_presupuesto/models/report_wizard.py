import base64

from odoo import _, api, fields, models

from .budget import MONTH_SELECTION
from .xlsx_export import build_budget_xlsx


class ImagoBudgetReportWizard(models.TransientModel):
    _name = "imago.budget.report.wizard"
    _description = "Resumen de presupuesto Imago"

    budget_id = fields.Many2one("imago.budget", required=True)
    company_id = fields.Many2one(related="budget_id.company_id", readonly=True)
    currency_id = fields.Many2one(related="budget_id.currency_id", readonly=True)
    cutoff_month = fields.Selection(MONTH_SELECTION, required=True, default="12")
    category_id = fields.Many2one(
        "imago.budget.category",
        domain="[('company_id', '=', company_id)]",
    )
    include_subcategories = fields.Boolean(string="Incluir subcategorias", default=True)
    calculated_at = fields.Datetime(readonly=True)
    complete = fields.Boolean(readonly=True)
    issue_text = fields.Text(string="Incidencias", readonly=True)
    warning_text = fields.Text(string="Avisos", readonly=True)
    authorized_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    spent_amount = fields.Monetary(string="Gastado en OC", readonly=True, currency_field="currency_id")
    available_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    projection_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    remaining_pct = fields.Float(readonly=True, digits=(16, 2))
    projection_pct = fields.Float(readonly=True, digits=(16, 2))
    has_total_budget = fields.Boolean(readonly=True)
    has_total_projection = fields.Boolean(readonly=True)
    line_ids = fields.One2many("imago.budget.report.line", "wizard_id", readonly=True)
    detail_line_ids = fields.One2many(
        "imago.budget.report.purchase.line", "wizard_id", readonly=True
    )
    purchase_line_ids = fields.Many2many("purchase.order.line", readonly=True)
    export_file = fields.Binary(readonly=True, attachment=False)
    export_filename = fields.Char(readonly=True)

    @api.model
    def get_dashboard_data(self, budget_id=False, cutoff_month=False, category_id=False):
        return self.env["imago.budget.report.service"].get_dashboard_data(
            budget_id, cutoff_month, category_id
        )

    @api.onchange("budget_id")
    def _onchange_budget_id(self):
        self.category_id = False
        self._clear_calculation()

    @api.onchange("cutoff_month", "category_id")
    def _onchange_report_filters(self):
        self._clear_calculation()

    def _clear_calculation(self):
        self.calculated_at = False
        self.line_ids = [(5, 0, 0)]
        self.detail_line_ids = [(5, 0, 0)]
        self.purchase_line_ids = [(5, 0, 0)]

    def action_calculate(self):
        self.ensure_one()
        report = self.env["imago.budget.report.service"].get_report(
            self.budget_id, int(self.cutoff_month), self.category_id
        )
        totals = report["totals"]
        commands = [(5, 0, 0)]
        for row in report["rows"]:
            values = {
                "category_id": row["category_id"],
                "name": row["category_name"],
                "authorized_amount": row["authorized"],
                "spent_amount": row["spent"],
                "available_amount": row["available"] or 0.0,
                "remaining_pct": row["remaining_pct"] or 0.0,
                "projection_amount": row["projection"] or 0.0,
                "projection_pct": row["projection_pct"] or 0.0,
                "status": row["status"],
                "complete": report["complete"],
                "has_budget": bool(row["authorized"]),
                "has_projection": row["projection"] is not None,
            }
            for month, amount in enumerate(row["monthly"], 1):
                values["month_%02d" % month] = amount
            commands.append((0, 0, values))
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
        self.write(
            {
                "calculated_at": fields.Datetime.now(),
                "complete": report["complete"],
                "issue_text": "\n".join(report["issues"]),
                "warning_text": "\n".join(report["warnings"]),
                "authorized_amount": totals["authorized"],
                "spent_amount": totals["spent"],
                "available_amount": totals["available"] or 0.0,
                "projection_amount": totals["projection"] or 0.0,
                "remaining_pct": totals["remaining_pct"] or 0.0,
                "projection_pct": totals["projection_pct"] or 0.0,
                "has_total_budget": bool(totals["authorized"]),
                "has_total_projection": totals["projection"] is not None,
                "line_ids": commands,
                "detail_line_ids": detail_commands,
                "purchase_line_ids": [(6, 0, report["purchase_line_ids"])],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
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
        report = self.env["imago.budget.report.service"].get_report(
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
        self.write(
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


class ImagoBudgetReportLine(models.TransientModel):
    _name = "imago.budget.report.line"
    _description = "Renglon de resumen de presupuesto Imago"
    _order = "id"

    wizard_id = fields.Many2one("imago.budget.report.wizard", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    category_id = fields.Many2one("imago.budget.category", readonly=True)
    name = fields.Char(readonly=True)
    authorized_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    spent_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    available_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    remaining_pct = fields.Float(readonly=True, digits=(16, 2))
    projection_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    projection_pct = fields.Float(readonly=True, digits=(16, 2))
    status = fields.Selection(
        [
            ("incomplete", "Incompleto"),
            ("unbudgeted", "Sin presupuesto"),
            ("over", "Excedido"),
            ("risk", "Riesgo al cierre"),
            ("within", "Dentro del presupuesto"),
        ],
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


class ImagoBudgetReportPurchaseLine(models.TransientModel):
    _name = "imago.budget.report.purchase.line"
    _description = "Detalle de compra para presupuesto Imago"
    _order = "confirmation_date, order_id, purchase_line_id"

    wizard_id = fields.Many2one(
        "imago.budget.report.wizard", required=True, index=True, ondelete="cascade"
    )
    currency_id = fields.Many2one(related="wizard_id.currency_id", readonly=True)
    purchase_line_id = fields.Many2one("purchase.order.line", readonly=True)
    order_id = fields.Many2one("purchase.order", string="OC", readonly=True)
    confirmation_date = fields.Datetime(string="Fecha de creacion", readonly=True)
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
            "view_mode": "form",
            "target": "current",
        }
