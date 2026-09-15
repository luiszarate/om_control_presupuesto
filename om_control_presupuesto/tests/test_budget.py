from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import SavepointCase


class TestImagoBudget(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.budget = cls.env["imago.budget"].create(
            {"year": 2026, "company_id": cls.company.id}
        )

    def test_reference_structure_total_and_pending_items(self):
        self.budget.action_load_reference_structure()
        self.assertAlmostEqual(self.budget.authorized_amount, 8986245.86, places=2)
        pending = self.budget.line_ids.filtered(lambda line: line.amount_status == "pending")
        self.assertEqual(len(pending), 4)
        self.assertEqual(set(pending.mapped("amount")), {0.0})
        self.budget.responsible_id = self.env.user
        with self.assertRaises(UserError):
            self.budget.with_user(self.env.user).action_activate()

    def test_project_may_have_only_one_destination(self):
        category_a = self.env["imago.budget.category"].create(
            {"name": "A", "company_id": self.company.id}
        )
        category_b = self.env["imago.budget.category"].create(
            {"name": "B", "company_id": self.company.id}
        )
        project = self.env["project.project"].create(
            {"name": "Project", "company_id": self.company.id}
        )
        self.env["imago.budget.project.rule"].create(
            {
                "budget_id": self.budget.id,
                "project_id": project.id,
                "category_id": category_a.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["imago.budget.project.rule"].create(
                {
                    "budget_id": self.budget.id,
                    "project_id": project.id,
                    "category_id": category_b.id,
                }
            )

    def test_parent_with_children_cannot_have_direct_budget_line(self):
        parent = self.env["imago.budget.category"].create(
            {"name": "Parent", "company_id": self.company.id}
        )
        self.env["imago.budget.category"].create(
            {"name": "Child", "company_id": self.company.id, "parent_id": parent.id}
        )
        with self.assertRaises(ValidationError):
            self.env["imago.budget.line"].create(
                {
                    "budget_id": self.budget.id,
                    "category_id": parent.id,
                    "amount": 100.0,
                }
            )
