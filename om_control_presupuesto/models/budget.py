from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


MONTH_SELECTION = [
    (str(number), name)
    for number, name in enumerate(
        [
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
        ],
        1,
    )
]


def _ensure_budgets_editable(budgets):
    if budgets.filtered(lambda budget: budget.state == "closed"):
        raise UserError(_("No se puede modificar la configuracion de un presupuesto cerrado."))


class ImagoBudget(models.Model):
    _name = "imago.budget"
    _description = "Presupuesto anual Imago"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "year desc, company_id"

    name = fields.Char(compute="_compute_name", store=True)
    year = fields.Integer(
        string="Ejercicio", required=True, default=lambda self: date.today().year, tracking=True
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="cascade",
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda de reporte",
        required=True,
        readonly=True,
        default=lambda self: self._default_currency_id(),
    )
    state = fields.Selection(
        [("draft", "Borrador"), ("active", "Vigente"), ("closed", "Cerrado")],
        required=True,
        default="draft",
        tracking=True,
        index=True,
    )
    responsible_id = fields.Many2one("res.users", string="Responsable", tracking=True)
    activation_date = fields.Datetime(readonly=True, tracking=True)
    closed_date = fields.Datetime(readonly=True, tracking=True)
    timezone = fields.Selection(
        selection=lambda self: self._tz_get(),
        required=True,
        default="America/Mexico_City",
        tracking=True,
    )
    amount_policy = fields.Selection(
        [("tax_included", "Total con impuestos")],
        required=True,
        default="tax_included",
        readonly=True,
    )
    date_policy = fields.Selection(
        [("confirmation", "Fecha de confirmacion")],
        required=True,
        default="confirmation",
        readonly=True,
    )
    line_ids = fields.One2many("imago.budget.line", "budget_id", string="Partidas")
    project_rule_ids = fields.One2many(
        "imago.budget.project.rule", "budget_id", string="Proyectos"
    )
    exchange_rate_ids = fields.One2many(
        "imago.budget.exchange.rate", "budget_id", string="Tipos de cambio"
    )
    snapshot_ids = fields.One2many(
        "imago.budget.snapshot", "budget_id", string="Historial", readonly=True
    )
    authorized_amount = fields.Monetary(
        compute="_compute_authorized_amount", store=True, currency_field="currency_id"
    )
    reopen_reason = fields.Char(string="Motivo de reapertura", copy=False)

    _sql_constraints = [
        (
            "company_year_unique",
            "unique(company_id, year)",
            "Solo puede existir un presupuesto por compania y ejercicio.",
        )
    ]

    @api.model
    def _tz_get(self):
        return [(tz, tz) for tz in __import__("pytz").all_timezones]

    @api.model
    def _default_currency_id(self):
        currency = self.env.ref("base.MXN", raise_if_not_found=False)
        return currency or self.env["res.currency"].search([("name", "=", "MXN")], limit=1)

    @api.depends("year", "company_id.name")
    def _compute_name(self):
        for budget in self:
            budget.name = "%s - %s" % (budget.year or "", budget.company_id.name or "")

    @api.depends("line_ids.amount", "line_ids.amount_status")
    def _compute_authorized_amount(self):
        for budget in self:
            budget.authorized_amount = sum(
                line.amount
                for line in budget.line_ids
                if line.amount_status == "authorized"
            )

    @api.constrains("year")
    def _check_year(self):
        for budget in self:
            if not 2000 <= budget.year <= 2200:
                raise ValidationError(_("El ejercicio debe estar entre 2000 y 2200."))

    @api.constrains("currency_id")
    def _check_reporting_currency(self):
        for budget in self:
            if budget.currency_id.name != "MXN":
                raise ValidationError(_("La moneda de reporte de esta version debe ser MXN."))

    def action_activate(self):
        for budget in self:
            if budget.state != "draft":
                continue
            if not budget.responsible_id:
                raise UserError(_("Defina un responsable antes de activar el presupuesto."))
            if budget.line_ids.filtered(lambda line: line.amount_status == "pending"):
                raise UserError(
                    _("Resuelva las partidas pendientes antes de activar el presupuesto.")
                )
            budget.write({"state": "active", "activation_date": fields.Datetime.now()})
        return True

    def action_close(self):
        self.ensure_one()
        if self.state != "active":
            raise UserError(_("Solamente un presupuesto vigente puede cerrarse."))
        report = self.env["imago.budget.report.service"].get_report(self, 12)
        if not report["complete"]:
            raise UserError(
                _("No se puede cerrar un reporte incompleto: %s")
                % "; ".join(report["issues"])
            )
        snapshot = self.env["imago.budget.snapshot"].create_from_report(self, report)
        self.write({"state": "closed", "closed_date": fields.Datetime.now()})
        self.message_post(body=_("Presupuesto cerrado. Fotografia %s creada.") % snapshot.name)
        return True

    def action_reopen(self):
        self.ensure_one()
        if self.state != "closed":
            raise UserError(_("Solamente un presupuesto cerrado puede reabrirse."))
        if not self.responsible_id or not self.reopen_reason:
            raise UserError(_("Indique responsable y motivo para reabrir."))
        reason = self.reopen_reason
        self.write({"state": "active", "closed_date": False, "reopen_reason": False})
        self.message_post(body=_("Presupuesto reabierto. Motivo: %s") % reason)
        return True

    def action_open_report(self):
        self.ensure_one()
        action = self.env.ref("om_control_presupuesto.action_imago_budget_report").read()[0]
        action["context"] = {
            "default_budget_id": self.id,
            "default_cutoff_month": "12",
        }
        return action

    def action_load_reference_structure(self):
        """Create the editable 2026 reference structure described in the specification."""
        self.ensure_one()
        if self.state != "draft" or self.line_ids:
            raise UserError(_("La carga inicial solo aplica a un borrador sin partidas."))

        category_model = self.env["imago.budget.category"].with_context(active_test=False)

        def get_category(name, sequence, parent=False):
            domain = [
                ("company_id", "=", self.company_id.id),
                ("parent_id", "=", parent.id if parent else False),
                ("name", "=ilike", name),
            ]
            record = category_model.search(domain, limit=1)
            if record:
                if not record.active:
                    record.active = True
                return record
            return category_model.create(
                {
                    "name": name,
                    "sequence": sequence,
                    "company_id": self.company_id.id,
                    "parent_id": parent.id if parent else False,
                }
            )

        structure = [
            ("Manufactura Turix / Holom I+D", 10, 750000.00, []),
            ("Pruebas de vuelo", 20, 150000.00, []),
            (
                "Nomina",
                30,
                None,
                [
                    ("Nomina actual", 4225092.75, "authorized"),
                    ("Personal ideal", 2738225.11, "authorized"),
                ],
            ),
            (
                "Servicios de terceros",
                40,
                None,
                [
                    ("Medios de comunicacion", 0.0, "pending"),
                    ("Social media manager", 0.0, "pending"),
                    ("Plan financiero", 0.0, "pending"),
                    ("Reclutamiento de gerente de ventas", 0.0, "pending"),
                    ("Servicios externos", 86700.00, "authorized"),
                ],
            ),
            ("Viajes", 50, 200000.00, []),
            ("Infraestructura / Software / Equipo", 60, 490000.00, []),
            ("Renta", 70, 0.0, []),
            (
                "Operacion",
                80,
                None,
                [
                    ("Suscripciones", 26760.00, "authorized"),
                    ("Servicios", 39468.00, "authorized"),
                    ("Gastos de oficina", 50000.00, "authorized"),
                ],
            ),
            ("Otros gastos", 90, 30000.00, []),
            ("Busqueda de clientes", 100, 200000.00, []),
        ]
        line_commands = []
        for parent_name, sequence, direct_amount, children in structure:
            parent = get_category(parent_name, sequence)
            if children:
                for child_sequence, (child_name, amount, amount_status) in enumerate(children, 1):
                    child = get_category(child_name, child_sequence * 10, parent=parent)
                    line_commands.append(
                        (
                            0,
                            0,
                            {
                                "category_id": child.id,
                                "amount": amount,
                                "amount_status": amount_status,
                            },
                        )
                    )
            else:
                line_commands.append(
                    (
                        0,
                        0,
                        {
                            "category_id": parent.id,
                            "amount": direct_amount,
                            "amount_status": "authorized",
                        },
                    )
                )
        self.write({"line_ids": line_commands})
        self.message_post(body=_("Se cargo la estructura inicial editable de la especificacion."))
        return True


class ImagoBudgetLine(models.Model):
    _name = "imago.budget.line"
    _description = "Partida de presupuesto Imago"
    _order = "category_id"

    budget_id = fields.Many2one(
        "imago.budget", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="budget_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="budget_id.currency_id", store=True)
    category_id = fields.Many2one(
        "imago.budget.category",
        required=True,
        ondelete="restrict",
        domain="[('company_id', '=', company_id)]",
    )
    amount_status = fields.Selection(
        [("pending", "Pendiente de definir"), ("authorized", "Autorizado")],
        required=True,
        default="authorized",
    )
    amount = fields.Monetary(currency_field="currency_id", default=0.0)
    note = fields.Char(string="Nota")

    _sql_constraints = [
        (
            "budget_category_unique",
            "unique(budget_id, category_id)",
            "La categoria solo puede tener una partida en el ejercicio.",
        ),
        ("amount_nonnegative", "check(amount >= 0)", "El importe no puede ser negativo."),
    ]

    @api.constrains("budget_id", "category_id")
    def _check_category(self):
        for line in self:
            if line.category_id.company_id != line.company_id:
                raise ValidationError(_("La partida y categoria deben pertenecer a la misma compania."))
            if line.category_id.with_context(active_test=False).child_ids:
                raise ValidationError(
                    _("Una categoria con subcategorias se presupuesta mediante sus subcategorias.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        budgets = self.env["imago.budget"].browse(
            [values.get("budget_id") for values in vals_list if values.get("budget_id")]
        )
        _ensure_budgets_editable(budgets)
        return super().create(vals_list)

    def write(self, values):
        budgets = self.mapped("budget_id")
        if values.get("budget_id"):
            budgets |= self.env["imago.budget"].browse(values["budget_id"])
        _ensure_budgets_editable(budgets)
        return super().write(values)

    def unlink(self):
        _ensure_budgets_editable(self.mapped("budget_id"))
        return super().unlink()


class ImagoBudgetProjectRule(models.Model):
    _name = "imago.budget.project.rule"
    _description = "Regla de proyecto para presupuesto Imago"
    _order = "project_id"

    budget_id = fields.Many2one(
        "imago.budget", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="budget_id.company_id", store=True, index=True)
    project_id = fields.Many2one(
        "project.project",
        required=True,
        ondelete="restrict",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
    category_id = fields.Many2one(
        "imago.budget.category",
        required=True,
        ondelete="restrict",
        domain="[('company_id', '=', company_id), ('parent_id', '=', False)]",
    )
    subcategory_id = fields.Many2one(
        "imago.budget.category",
        string="Subcategoria",
        ondelete="restrict",
        domain="[('parent_id', '=', category_id)]",
    )

    _sql_constraints = [
        (
            "budget_project_unique",
            "unique(budget_id, project_id)",
            "Un proyecto solo puede tener un destino en el mismo ejercicio.",
        )
    ]

    @api.constrains("budget_id", "project_id", "category_id", "subcategory_id")
    def _check_rule(self):
        for rule in self:
            if rule.category_id.company_id != rule.company_id:
                raise ValidationError(_("La categoria debe pertenecer a la compania del presupuesto."))
            if rule.subcategory_id and rule.subcategory_id.parent_id != rule.category_id:
                raise ValidationError(_("La subcategoria no pertenece a la categoria seleccionada."))
            if rule.project_id.company_id and rule.project_id.company_id != rule.company_id:
                raise ValidationError(_("El proyecto pertenece a otra compania."))

    @api.model_create_multi
    def create(self, vals_list):
        budgets = self.env["imago.budget"].browse(
            [values.get("budget_id") for values in vals_list if values.get("budget_id")]
        )
        _ensure_budgets_editable(budgets)
        return super().create(vals_list)

    def write(self, values):
        budgets = self.mapped("budget_id")
        if values.get("budget_id"):
            budgets |= self.env["imago.budget"].browse(values["budget_id"])
        _ensure_budgets_editable(budgets)
        return super().write(values)

    def unlink(self):
        _ensure_budgets_editable(self.mapped("budget_id"))
        return super().unlink()


class ImagoBudgetExchangeRate(models.Model):
    _name = "imago.budget.exchange.rate"
    _description = "Tipo de cambio mensual para presupuesto Imago"
    _order = "month, currency_id"

    budget_id = fields.Many2one(
        "imago.budget", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="budget_id.company_id", store=True, index=True)
    reporting_currency_id = fields.Many2one(related="budget_id.currency_id", store=True)
    currency_id = fields.Many2one("res.currency", required=True, ondelete="restrict")
    month = fields.Selection(MONTH_SELECTION, required=True)
    rate = fields.Float(
        string="MXN por unidad", required=True, digits=(16, 6), help="Moneda de reporte por unidad."
    )

    _sql_constraints = [
        (
            "budget_month_currency_unique",
            "unique(budget_id, month, currency_id)",
            "Solo puede existir un tipo por moneda y mes.",
        ),
        ("rate_positive", "check(rate > 0)", "El tipo de cambio debe ser mayor que cero."),
    ]

    @api.constrains("currency_id", "reporting_currency_id")
    def _check_foreign_currency(self):
        for rate in self:
            if rate.currency_id == rate.reporting_currency_id:
                raise ValidationError(
                    _("La moneda de la compania usa factor 1 y no requiere captura.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        budgets = self.env["imago.budget"].browse(
            [values.get("budget_id") for values in vals_list if values.get("budget_id")]
        )
        _ensure_budgets_editable(budgets)
        return super().create(vals_list)

    def write(self, values):
        budgets = self.mapped("budget_id")
        if values.get("budget_id"):
            budgets |= self.env["imago.budget"].browse(values["budget_id"])
        _ensure_budgets_editable(budgets)
        return super().write(values)

    def unlink(self):
        _ensure_budgets_editable(self.mapped("budget_id"))
        return super().unlink()
