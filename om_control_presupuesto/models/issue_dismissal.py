import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .budget import _ensure_budgets_editable


ISSUE_KEY_PATTERN = re.compile(r"^(integration|missing_date|missing_rate):[\w.:-]{1,120}$")
MANAGER_GROUP = "om_control_presupuesto.group_imago_budget_manager"


class ImagoBudgetIssueDismissal(models.Model):
    _name = "imago.budget.issue.dismissal"
    _description = "Incidencia descartada de presupuesto Imago"
    _order = "dismissed_at desc, id desc"

    budget_id = fields.Many2one(
        "imago.budget", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(related="budget_id.company_id", store=True, index=True)
    key = fields.Char(required=True, readonly=True)
    name = fields.Char(string="Incidencia", readonly=True)
    user_id = fields.Many2one(
        "res.users", string="Descartada por", required=True, readonly=True,
        default=lambda self: self.env.user,
    )
    dismissed_at = fields.Datetime(
        string="Fecha", required=True, readonly=True, default=fields.Datetime.now
    )

    _sql_constraints = [
        (
            "budget_key_unique",
            "unique(budget_id, key)",
            "La incidencia ya fue descartada en este presupuesto.",
        )
    ]

    @api.constrains("key")
    def _check_key(self):
        for dismissal in self:
            if not ISSUE_KEY_PATTERN.match(dismissal.key or ""):
                raise ValidationError(_("Identificador de incidencia no valido."))

    @api.model
    def _check_can_dismiss(self, budget):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(
                _("Solo el responsable de presupuesto puede descartar o restaurar incidencias.")
            )
        _ensure_budgets_editable(budget)

    @api.model
    def dismiss_keys(self, budget, item_keys, name=False):
        budget.ensure_one()
        self._check_can_dismiss(budget)
        existing = set(budget.issue_dismissal_ids.mapped("key"))
        values = [
            {"budget_id": budget.id, "key": key, "name": (name or "")[:250]}
            for key in dict.fromkeys(item_keys)
            if key not in existing
        ]
        if values:
            self.create(values)
            budget.message_post(body=_("Incidencia descartada: %s") % (name or ", ".join(item_keys)))
        return True

    @api.model
    def restore_keys(self, budget, item_keys):
        budget.ensure_one()
        self._check_can_dismiss(budget)
        dismissals = budget.issue_dismissal_ids.filtered(lambda item: item.key in set(item_keys))
        if dismissals:
            names = ", ".join(sorted(set(filter(None, dismissals.mapped("name")))))
            dismissals.unlink()
            budget.message_post(body=_("Incidencia restaurada: %s") % names)
        return True
