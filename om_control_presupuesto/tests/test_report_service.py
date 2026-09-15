import base64
import io
import zipfile

from odoo.tests.common import SavepointCase


class TestImagoBudgetReportService(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.reporting_currency = cls.env.ref("base.MXN")
        cls.reporting_currency.active = True
        cls.foreign_currency = cls.env["res.currency"].search(
            [("id", "!=", cls.reporting_currency.id)], limit=1
        )
        if not cls.foreign_currency:
            cls.foreign_currency = cls.env["res.currency"].create(
                {"name": "ZZZ", "symbol": "Z", "rounding": 0.01}
            )
        cls.foreign_currency.active = True
        cls.category = cls.env["imago.budget.category"].create(
            {"name": "Flight tests", "company_id": cls.company.id}
        )
        cls.project = cls.env["project.project"].create(
            {"name": "Test project", "company_id": cls.company.id}
        )
        cls.budget = cls.env["imago.budget"].create(
            {
                "year": 2026,
                "company_id": cls.company.id,
                "line_ids": [
                    (0, 0, {"category_id": cls.category.id, "amount": 100000.0})
                ],
                "project_rule_ids": [
                    (
                        0,
                        0,
                        {
                            "project_id": cls.project.id,
                            "category_id": cls.category.id,
                        },
                    )
                ],
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Vendor"})
        cls.product = cls.env["product.product"].create(
            {"name": "Service", "type": "service", "purchase_ok": True}
        )

    @classmethod
    def _create_order(cls, currency, amount, project=None, state="purchase"):
        values = {
            "partner_id": cls.partner.id,
            "company_id": cls.company.id,
            "currency_id": currency.id,
            "date_order": "2026-02-15 12:00:00",
            "date_approve": "2026-02-15 12:00:00",
            "state": state,
            "project_id": project.id if project else False,
            "order_line": [
                (
                    0,
                    0,
                    {
                        "name": "Test line",
                        "product_id": cls.product.id,
                        "product_qty": 1.0,
                        "product_uom": cls.product.uom_po_id.id,
                        "price_unit": amount,
                        "date_planned": "2026-02-20 12:00:00",
                        "taxes_id": [(6, 0, [])],
                    },
                )
            ],
        }
        return cls.env["purchase.order"].create(values)

    def test_monthly_rate_and_unclassified_are_reconciled(self):
        self.env["imago.budget.exchange.rate"].create(
            {
                "budget_id": self.budget.id,
                "currency_id": self.foreign_currency.id,
                "month": "2",
                "rate": 17.23,
            }
        )
        self._create_order(self.foreign_currency, 1000.0, self.project)
        self._create_order(self.reporting_currency, 50.0)

        report = self.env["imago.budget.report.service"].get_report(self.budget, 2)

        self.assertTrue(report["complete"])
        self.assertAlmostEqual(report["totals"]["spent"], 17280.0, places=2)
        self.assertAlmostEqual(report["totals"]["monthly"][1], 17280.0, places=2)
        self.assertAlmostEqual(report["totals"]["projection"], 103680.0, places=2)
        unclassified = next(row for row in report["rows"] if not row["category_id"])
        self.assertAlmostEqual(unclassified["spent"], 50.0, places=2)

    def test_missing_rate_marks_report_incomplete(self):
        self._create_order(self.foreign_currency, 1000.0, self.project)

        report = self.env["imago.budget.report.service"].get_report(self.budget, 2)

        self.assertFalse(report["complete"])
        self.assertIsNone(report["totals"]["available"])
        self.assertIsNone(report["totals"]["projection"])
        self.assertEqual(report["details"][0]["status"], "missing_rate")

    def test_draft_and_cancelled_orders_are_excluded(self):
        self._create_order(self.reporting_currency, 100.0, self.project, state="draft")
        self._create_order(self.reporting_currency, 200.0, self.project, state="cancel")

        report = self.env["imago.budget.report.service"].get_report(self.budget, 2)

        self.assertAlmostEqual(report["totals"]["spent"], 0.0, places=2)

    def test_zero_budget_metrics_do_not_divide_by_zero(self):
        metrics = self.env["imago.budget.report.service"]._metrics(0.0, 25.0, 2)
        self.assertIsNone(metrics["remaining_pct"])
        self.assertIsNone(metrics["projection_pct"])
        self.assertEqual(metrics["status"], "unbudgeted")

    def test_reference_projection_uses_common_february_cutoff(self):
        metrics = self.env["imago.budget.report.service"]._metrics(
            8986245.86, 1101691.52, 2
        )
        self.assertAlmostEqual(metrics["projection"], 6610149.12, places=2)
        self.assertAlmostEqual(metrics["projection_pct"], 73.56, places=2)

    def test_dashboard_uses_the_same_report_service(self):
        self._create_order(self.reporting_currency, 100.0, self.project)

        payload = self.env["imago.budget.report.wizard"].get_dashboard_data(
            self.budget.id, 2, False
        )

        self.assertEqual(payload["selected_budget_id"], self.budget.id)
        self.assertEqual(payload["selected_cutoff_month"], 2)
        self.assertAlmostEqual(payload["report"]["totals"]["spent"], 100.0, places=2)
        self.assertEqual(len(payload["report"]["cumulative"]), 12)

    def test_xlsx_export_contains_required_sheets(self):
        self._create_order(self.reporting_currency, 100.0, self.project)
        wizard = self.env["imago.budget.report.wizard"].create(
            {"budget_id": self.budget.id, "cutoff_month": "2"}
        )

        action = wizard.action_export_xlsx()

        self.assertEqual(action["type"], "ir.actions.act_url")
        content = base64.b64decode(wizard.export_file)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        for sheet_name in (
            "Resumen anual",
            "Detalle mensual",
            "Compras",
            "Tipos de cambio",
            "Parametros e incidencias",
        ):
            self.assertIn(sheet_name, workbook_xml)
