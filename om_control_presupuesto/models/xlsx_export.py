import io
from datetime import datetime

from odoo import _, fields
from odoo.exceptions import UserError


MONTH_NAMES = [
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
]


def _safe_text(value):
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text[:32767]


def build_budget_xlsx(env, budget, report, include_subcategories=True):
    try:
        import xlsxwriter
    except ImportError as error:
        raise UserError(_("Instale la biblioteca Python xlsxwriter para exportar Excel.")) from error

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title = workbook.add_format(
        {"bold": True, "font_size": 15, "font_color": "#17365D"}
    )
    header = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E78",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )
    body_edge = {"bottom": 1, "bottom_color": "#D9E1F2", "valign": "vcenter"}
    money = workbook.add_format(
        dict(body_edge, num_format='$#,##0.00;[Red]($#,##0.00);-')
    )
    number = workbook.add_format(
        dict(body_edge, num_format='#,##0.00;[Red](#,##0.00);-')
    )
    percent = workbook.add_format(
        dict(body_edge, num_format='0.00%;[Red](0.00%);-')
    )
    text_format = workbook.add_format(body_edge)
    child_text = workbook.add_format(dict(body_edge, indent=1))
    date_format = workbook.add_format(dict(body_edge, num_format="yyyy-mm-dd hh:mm"))
    warning = workbook.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})
    error_format = workbook.add_format({"bg_color": "#F4CCCC", "font_color": "#990000"})
    status_error = workbook.add_format({"bg_color": "#F4CCCC", "font_color": "#990000"})
    status_warning = workbook.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})

    def write_text(sheet, row, column, value, cell_format=text_format):
        sheet.write_string(row, column, _safe_text(value), cell_format)

    def write_number_or_blank(sheet, row, column, value, cell_format=number):
        if value is None:
            sheet.write_blank(row, column, None, cell_format)
        else:
            sheet.write_number(row, column, value, cell_format)

    summary = workbook.add_worksheet("Resumen anual")
    summary.hide_gridlines(2)
    summary.set_tab_color("#1F4E78")
    summary.write_string(1, 0, _safe_text("Presupuesto Imago %s" % budget.year), title)
    summary_headers = [
        "Categoria",
        "Autorizado",
        "Gastado en OC",
        "Restante",
        "Restante %",
        "Proyeccion MXN",
        "Proyeccion %",
        "Estado",
    ]
    for column, value in enumerate(summary_headers):
        summary.write_string(3, column, value, header)
    status_labels = {
        "incomplete": "Incompleto",
        "unbudgeted": "Sin presupuesto",
        "over": "Excedido",
        "risk": "Riesgo al cierre",
        "within": "Dentro del presupuesto",
    }
    row_number = 4
    for row in report["rows"]:
        write_text(summary, row_number, 0, row["category_name"])
        write_number_or_blank(summary, row_number, 1, row["authorized"], money)
        write_number_or_blank(summary, row_number, 2, row["spent"], money)
        write_number_or_blank(summary, row_number, 3, row["available"], money)
        write_number_or_blank(
            summary,
            row_number,
            4,
            row["remaining_pct"] / 100.0 if row["remaining_pct"] is not None else None,
            percent,
        )
        write_number_or_blank(summary, row_number, 5, row["projection"], money)
        write_number_or_blank(
            summary,
            row_number,
            6,
            row["projection_pct"] / 100.0 if row["projection_pct"] is not None else None,
            percent,
        )
        write_text(summary, row_number, 7, status_labels.get(row["status"], row["status"]))
        row_number += 1
    totals = report["totals"]
    write_text(summary, row_number, 0, "TOTAL", header)
    for column, key in ((1, "authorized"), (2, "spent"), (3, "available"), (5, "projection")):
        write_number_or_blank(summary, row_number, column, totals[key], money)
    write_number_or_blank(
        summary,
        row_number,
        4,
        totals["remaining_pct"] / 100.0 if totals["remaining_pct"] is not None else None,
        percent,
    )
    write_number_or_blank(
        summary,
        row_number,
        6,
        totals["projection_pct"] / 100.0 if totals["projection_pct"] is not None else None,
        percent,
    )
    write_text(summary, row_number, 7, status_labels.get(totals["status"], totals["status"]))
    summary.conditional_format(4, 7, max(4, row_number - 1), 7, {
        "type": "text", "criteria": "containing", "value": "Excedido", "format": status_error,
    })
    summary.conditional_format(4, 7, max(4, row_number - 1), 7, {
        "type": "text", "criteria": "containing", "value": "Riesgo", "format": status_warning,
    })
    summary.conditional_format(4, 7, max(4, row_number - 1), 7, {
        "type": "text", "criteria": "containing", "value": "Incompleto", "format": status_error,
    })
    summary.freeze_panes(4, 1)
    summary.autofilter(3, 0, max(4, row_number - 1), len(summary_headers) - 1)
    summary.set_column(0, 0, 36)
    summary.set_column(1, 6, 17)
    summary.set_column(7, 7, 24)

    monthly = workbook.add_worksheet("Detalle mensual")
    monthly.hide_gridlines(2)
    monthly.set_tab_color("#5B9BD5")
    monthly_headers = ["Categoria", "Nivel", "Autorizado", "Gastado"] + MONTH_NAMES
    for column, value in enumerate(monthly_headers):
        monthly.write_string(0, column, value, header)
    monthly_row = 1
    for row in report["rows"]:
        records = [(row, "Categoria", text_format)]
        if include_subcategories:
            records.extend((child, "Subcategoria", child_text) for child in row.get("children", []))
        for item, level, name_format in records:
            write_text(monthly, monthly_row, 0, item["category_name"], name_format)
            write_text(monthly, monthly_row, 1, level)
            write_number_or_blank(monthly, monthly_row, 2, item["authorized"], money)
            write_number_or_blank(monthly, monthly_row, 3, item["spent"], money)
            for month_index, amount in enumerate(item["monthly"], 1):
                if month_index <= report["cutoff_month"]:
                    write_number_or_blank(monthly, monthly_row, month_index + 3, amount, money)
                else:
                    monthly.write_blank(monthly_row, month_index + 3, None, money)
            monthly_row += 1
    monthly.freeze_panes(1, 2)
    monthly.autofilter(0, 0, max(1, monthly_row - 1), len(monthly_headers) - 1)
    monthly.set_column(0, 0, 38)
    monthly.set_column(1, 1, 15)
    monthly.set_column(2, len(monthly_headers) - 1, 15)

    purchases = workbook.add_worksheet("Compras")
    purchases.hide_gridlines(2)
    purchase_headers = [
        "OC",
        "Fecha recepcion UTC",
        "Mes",
        "Proveedor",
        "Descripcion",
        "Proyecto",
        "Categoria",
        "Subcategoria",
        "Moneda",
        "Subtotal original",
        "Impuestos",
        "Total original",
        "TC aplicado",
        "Importe MXN",
        "Estado de inclusion",
    ]
    for column, value in enumerate(purchase_headers):
        purchases.write_string(0, column, value, header)
    detail_row = 1
    detail_status = {
        "included": "Incluida",
        "unclassified": "Sin clasificar",
        "missing_rate": "Pendiente de conversion",
        "excluded_secihti": "Excluida por SECIHTI",
    }
    for detail in report["details"]:
        text_values = {
            0: detail["order_name"],
            3: detail["partner_name"],
            4: detail["description"],
            5: detail["project_name"],
            6: detail["category_name"],
            7: detail["subcategory_name"],
            8: detail["currency_name"],
            14: detail_status.get(detail["status"], detail["status"]),
        }
        for column, value in text_values.items():
            write_text(purchases, detail_row, column, value)
        confirmation_date = datetime.strptime(
            detail["confirmation_date"], "%Y-%m-%d %H:%M:%S"
        )
        purchases.write_datetime(detail_row, 1, confirmation_date, date_format)
        purchases.write_number(detail_row, 2, detail["month"], text_format)
        for column, key in (
            (9, "subtotal_amount"),
            (10, "tax_amount"),
            (11, "original_amount"),
        ):
            write_number_or_blank(purchases, detail_row, column, detail[key], number)
        write_number_or_blank(purchases, detail_row, 12, detail["rate"], number)
        write_number_or_blank(purchases, detail_row, 13, detail["converted_amount"], money)
        detail_row += 1
    purchases.freeze_panes(1, 5)
    purchases.autofilter(0, 0, max(1, detail_row - 1), len(purchase_headers) - 1)
    purchases.set_column(0, 3, 22)
    purchases.set_column(4, 4, 50)
    purchases.set_column(5, 8, 28)
    purchases.set_column(9, 14, 19)

    rates = workbook.add_worksheet("Tipos de cambio")
    rates.hide_gridlines(2)
    rate_headers = ["Moneda", "Mes", "MXN por unidad", "Lineas que lo usan"]
    for column, value in enumerate(rate_headers):
        rates.write_string(0, column, value, header)
    used_rates = {}
    for detail in report["details"]:
        if detail["rate"] is None or detail["status"] == "excluded_secihti":
            continue
        key = (detail["currency_name"], detail["month"], detail["rate"])
        used_rates[key] = used_rates.get(key, 0) + 1
    rate_row = 1
    for (currency_name, month, rate), count in sorted(used_rates.items()):
        write_text(rates, rate_row, 0, currency_name)
        write_text(rates, rate_row, 1, MONTH_NAMES[month - 1])
        rates.write_number(rate_row, 2, rate, number)
        rates.write_number(rate_row, 3, count, text_format)
        rate_row += 1
    rates.freeze_panes(1, 0)
    rates.autofilter(0, 0, max(1, rate_row - 1), len(rate_headers) - 1)
    rates.set_column(0, 3, 22)

    parameters = workbook.add_worksheet("Parametros e incidencias")
    parameters.hide_gridlines(2)
    parameters.write_string(0, 0, "Parametro", header)
    parameters.write_string(0, 1, "Valor", header)
    parameter_values = [
        ("Compania", budget.company_id.display_name),
        ("Ejercicio", budget.year),
        ("Mes de corte", MONTH_NAMES[report["cutoff_month"] - 1]),
        ("Moneda", budget.currency_id.name),
        ("Politica de importe", "Total con impuestos"),
        ("Politica de fecha", "Fecha de recepcion"),
        ("Zona horaria", budget.timezone),
        ("Fecha de generacion UTC", fields.Datetime.to_string(fields.Datetime.now())),
        ("Reporte completo", "Si" if report["complete"] else "No"),
        ("Integracion SECIHTI", report["integration"]["secihti"]),
    ]
    parameter_row = 1
    for key, value in parameter_values:
        write_text(parameters, parameter_row, 0, key)
        if isinstance(value, (int, float)):
            parameters.write_number(parameter_row, 1, value, text_format)
        else:
            write_text(parameters, parameter_row, 1, value)
        parameter_row += 1
    parameter_row += 1
    parameters.write_string(parameter_row, 0, "Incidencias", header)
    parameter_row += 1
    for issue in report["issue_items"]:
        parameters.merge_range(parameter_row, 0, parameter_row, 1, _safe_text(issue["title"]), error_format)
        parameter_row += 1
        for detail in [issue["hint"]] + issue["details"]:
            write_text(parameters, parameter_row, 1, detail)
            parameter_row += 1
    if not report["issue_items"]:
        parameters.merge_range(parameter_row, 0, parameter_row, 1, "Sin incidencias", text_format)
        parameter_row += 1
    if report["dismissed_issue_items"]:
        parameter_row += 1
        parameters.write_string(parameter_row, 0, "Incidencias descartadas", header)
        parameter_row += 1
        for issue in report["dismissed_issue_items"]:
            parameters.merge_range(parameter_row, 0, parameter_row, 1, _safe_text(issue["title"]), warning)
            parameter_row += 1
            for detail in issue["details"]:
                write_text(parameters, parameter_row, 1, detail)
                parameter_row += 1
    parameter_row += 1
    parameters.write_string(parameter_row, 0, "Avisos", header)
    parameter_row += 1
    for notice in report["warnings"]:
        parameters.merge_range(parameter_row, 0, parameter_row, 1, _safe_text(notice), warning)
        parameter_row += 1
    parameters.set_column(0, 0, 30)
    parameters.set_column(1, 1, 90)
    parameters.freeze_panes(1, 0)

    workbook.close()
    return output.getvalue()
