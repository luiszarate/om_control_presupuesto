from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ImagoBudgetCategory(models.Model):
    _name = "imago.budget.category"
    _description = "Categoria de presupuesto Imago"
    _order = "sequence, name, id"
    _parent_store = True

    name = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="cascade",
    )
    parent_id = fields.Many2one(
        "imago.budget.category",
        string="Categoria padre",
        index=True,
        ondelete="restrict",
        domain="[('parent_id', '=', False), ('company_id', '=', company_id)]",
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        "imago.budget.category", "parent_id", string="Subcategorias"
    )

    @api.constrains("name", "company_id", "parent_id")
    def _check_category_structure(self):
        for category in self:
            if category.parent_id:
                if category.parent_id.parent_id:
                    raise ValidationError(
                        _("El catalogo solamente admite categoria y subcategoria.")
                    )
                if category.parent_id.company_id != category.company_id:
                    raise ValidationError(
                        _("La categoria padre debe pertenecer a la misma compania.")
                    )
                if self.env["imago.budget.line"].search_count(
                    [
                        ("category_id", "=", category.parent_id.id),
                        ("budget_id.state", "!=", "closed"),
                    ]
                ):
                    raise ValidationError(
                        _(
                            "No se puede agregar una subcategoria mientras la categoria padre tenga partidas directas."
                        )
                    )
            duplicate = self.search_count(
                [
                    ("id", "!=", category.id),
                    ("company_id", "=", category.company_id.id),
                    ("parent_id", "=", category.parent_id.id or False),
                    ("name", "=ilike", category.name.strip()),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("Ya existe una categoria con ese nombre en el mismo nivel.")
                )

    def name_get(self):
        result = []
        for category in self:
            name = category.name
            if category.parent_id:
                name = "%s / %s" % (category.parent_id.name, name)
            result.append((category.id, name))
        return result
