from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
import re
from typing import Any, Dict, List, Sequence
from zoneinfo import ZoneInfo

import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#07133f")
TEAL = colors.HexColor("#07859d")
TEAL_DARK = colors.HexColor("#0f766e")
ORANGE = colors.HexColor("#c2410c")
BLUE = colors.HexColor("#1d4ed8")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#d0d5dd")
PALE = colors.HexColor("#f4f7fa")
PALE_TEAL = colors.HexColor("#e8f5f7")
WHITE = colors.white


def as_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def money(value: Any) -> str:
    amount = as_number(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def percent(value: Any, digits: int = 2) -> str:
    return f"{as_number(value):.{digits}f}%"


def compact_money(value: float) -> str:
    amount = abs(value)
    sign = "-" if value < 0 else ""
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.1f}m"
    if amount >= 1_000:
        return f"{sign}${amount / 1_000:.0f}k"
    return f"{sign}${amount:.0f}"


def display_text(value: Any, fallback: str = "-") -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def display_money(value: Any, fallback: str = "-") -> str:
    if value in (None, ""):
        return fallback
    return money(value)


def display_percent(value: Any, digits: int = 2, fallback: str = "-") -> str:
    if value in (None, ""):
        return fallback
    return percent(value, digits)


def report_filename(address: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", address.strip()).strip("-").lower()
    return f"property-feasibility-{stem or 'report'}.pdf"


def make_styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=4 * mm,
        ),
        "address": ParagraphStyle(
            "Address",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=13,
            leading=17,
            textColor=TEAL_DARK,
            spaceAfter=2 * mm,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=NAVY,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
            keepWithNext=True,
        ),
        "subsection": ParagraphStyle(
            "Subsection",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=TEAL_DARK,
            spaceBefore=2 * mm,
            spaceAfter=1.5 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=8,
            leading=11,
            textColor=INK,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontSize=6.8,
            leading=8.5,
            textColor=INK,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.8,
            leading=8.5,
            textColor=WHITE,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=INK,
        ),
        "value": ParagraphStyle(
            "Value",
            parent=base["Normal"],
            fontSize=7.5,
            leading=9.5,
            textColor=INK,
        ),
        "card": ParagraphStyle(
            "Card",
            parent=base["Normal"],
            fontSize=7.2,
            leading=11.5,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "note": ParagraphStyle(
            "Note",
            parent=base["Normal"],
            fontSize=7,
            leading=9.5,
            textColor=MUTED,
        ),
    }


def safe_paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    text = "" if value in (None, "") else str(value)
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def link_paragraph(url: str, label: str, style: ParagraphStyle) -> Paragraph:
    if not url:
        return safe_paragraph("Not available", style)
    safe_url = escape(url, quote=True)
    return Paragraph(f'<link href="{safe_url}" color="#1d4ed8">{escape(label)}</link>', style)


def section_heading(title: str, styles: Dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(escape(title), styles["section"])


def styled_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    styles: Dict[str, ParagraphStyle],
    col_widths: Sequence[float] | None = None,
    font_size: float = 7.2,
) -> Table:
    body_style = styles["small"] if font_size < 7 else styles["value"]
    data: List[List[Any]] = [
        [Paragraph(escape(str(header)), styles["table_header"]) for header in headers]
    ]
    for row in rows:
        data.append([safe_paragraph(cell, body_style) for cell in row])

    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            table_style.append(("BACKGROUND", (0, row_index), (-1, row_index), PALE))
    table.setStyle(TableStyle(table_style))
    return table


def detail_table(
    items: Sequence[tuple[str, Any]],
    styles: Dict[str, ParagraphStyle],
    width: float,
) -> Table:
    rows: List[List[Any]] = []
    for index in range(0, len(items), 2):
        left = items[index]
        right = items[index + 1] if index + 1 < len(items) else ("", "")
        rows.append(
            [
                safe_paragraph(left[0], styles["label"]),
                safe_paragraph(left[1], styles["value"]),
                safe_paragraph(right[0], styles["label"]),
                safe_paragraph(right[1], styles["value"]),
            ]
        )
    table = Table(rows, colWidths=[width * 0.18, width * 0.32, width * 0.18, width * 0.32], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BACKGROUND", (0, 0), (0, -1), PALE_TEAL),
                ("BACKGROUND", (2, 0), (2, -1), PALE_TEAL),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def summary_cards(metrics: Dict[str, Any], styles: Dict[str, ParagraphStyle], width: float) -> Table:
    cards = [
        ("Pre-tax cash flow (yearly)", money(metrics.get("pre_tax_cashflow"))),
        ("Post-tax cash flow (yearly)", money(metrics.get("after_tax_cashflow"))),
        ("Gross yield", percent(metrics.get("gross_yield"))),
        ("Cash flow", metrics.get("cashflow_label", "")),
        ("Net yield before interest", percent(metrics.get("net_yield_before_interest"))),
        ("Net yield after interest", percent(metrics.get("net_yield_after_interest"))),
        ("Cash required upfront", money(metrics.get("cash_required_upfront"))),
        ("Total borrowings", money(metrics.get("total_borrowings"))),
        ("Recommendation", metrics.get("recommendation", "INCOMPLETE")),
        ("Overall score", f"{as_number(metrics.get('overall_score')):.1f}/10"),
        ("Risk score", f"{as_number(metrics.get('risk_score')):.1f}/10"),
        ("Growth score", f"{as_number(metrics.get('growth_score')):.1f}/10"),
    ]
    rows: List[List[Paragraph]] = []
    for start in range(0, len(cards), 4):
        row: List[Paragraph] = []
        for label, value in cards[start : start + 4]:
            cell = f"{escape(str(label))}<br/><font size=13 color='#07133f'><b>{escape(str(value))}</b></font>"
            row.append(Paragraph(cell, styles["card"]))
        rows.append(row)
    table = Table(rows, colWidths=[width / 4] * 4, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_TEAL),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, WHITE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def compact_summary_cards(
    payload: Dict[str, Any],
    metrics: Dict[str, Any],
    styles: Dict[str, ParagraphStyle],
    width: float,
) -> Table:
    cards = [
        ("Recommendation", display_text(metrics.get("recommendation"), "INCOMPLETE")),
        ("Purchase price", display_money(payload.get("price"))),
        ("Net yield after interest", display_percent(metrics.get("net_yield_after_interest"))),
        ("Cash required upfront", display_money(metrics.get("cash_required_upfront"))),
    ]
    rows: List[List[Paragraph]] = []
    for start in range(0, len(cards), 4):
        row: List[Paragraph] = []
        for label, value in cards[start : start + 4]:
            cell = (
                f"<font size=6.8 color='#667085'>{escape(str(label))}</font><br/>"
                f"<font size=12.5 color='#07133f'><b>{escape(str(value))}</b></font>"
            )
            row.append(Paragraph(cell, styles["card"]))
        rows.append(row)
    table = Table(rows, colWidths=[width / 4] * 4, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_TEAL),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, WHITE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def panel_table(
    title: str,
    body: Any,
    styles: Dict[str, ParagraphStyle],
    width: float,
    body_background: colors.Color = WHITE,
) -> Table:
    content = body if isinstance(body, list) else [body]
    table = Table(
        [
            [Paragraph(escape(title), styles["table_header"])],
            [content],
        ],
        colWidths=[width],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), NAVY),
                ("BACKGROUND", (0, 1), (0, 1), body_background),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, 0), 3),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 1), (-1, 1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 3),
            ]
        )
    )
    return table


def mortgage_chart(loan: Any, schedule: pd.DataFrame, width: float, height: float = 190) -> Drawing:
    drawing = Drawing(width, height)
    left = 65
    right = 68
    top = 30
    bottom = 34
    plot_width = width - left - right
    plot_height = height - top - bottom

    years = [as_number(value) for value in schedule.get("Year", [])]
    principals = [as_number(value) for value in schedule.get("Principal repaid", [])]
    interests = [as_number(value) for value in schedule.get("Interest paid", [])]
    cumulative_interest: List[float] = []
    running_interest = 0.0
    for value in interests:
        running_interest += value
        cumulative_interest.append(running_interest)

    if not years:
        return drawing

    min_year = min(years)
    max_year = max(years)
    left_max = max(principals + interests + [1.0])
    right_max = max(cumulative_interest + [1.0])

    def x_pos(year: float) -> float:
        if max_year == min_year:
            return left + plot_width / 2
        return left + (year - min_year) / (max_year - min_year) * plot_width

    def left_y(value: float) -> float:
        return bottom + value / left_max * plot_height

    def right_y(value: float) -> float:
        return bottom + value / right_max * plot_height

    drawing.add(Rect(left, bottom, plot_width, plot_height, fillColor=WHITE, strokeColor=LINE, strokeWidth=0.7))
    for tick in range(5):
        ratio = tick / 4
        y = bottom + ratio * plot_height
        drawing.add(Line(left, y, left + plot_width, y, strokeColor=colors.HexColor("#e8eaed"), strokeWidth=0.5))
        drawing.add(
            String(
                left - 5,
                y - 3,
                compact_money(left_max * ratio),
                fontName="Helvetica",
                fontSize=6.5,
                fillColor=MUTED,
                textAnchor="end",
            )
        )
        drawing.add(
            String(
                left + plot_width + 5,
                y - 3,
                compact_money(right_max * ratio),
                fontName="Helvetica",
                fontSize=6.5,
                fillColor=MUTED,
                textAnchor="start",
            )
        )

    tick_indexes = sorted(set([0, len(years) // 4, len(years) // 2, len(years) * 3 // 4, len(years) - 1]))
    for index in tick_indexes:
        x = x_pos(years[index])
        drawing.add(Line(x, bottom, x, bottom - 3, strokeColor=LINE, strokeWidth=0.5))
        drawing.add(
            String(
                x,
                bottom - 13,
                str(int(years[index])),
                fontName="Helvetica",
                fontSize=6.5,
                fillColor=MUTED,
                textAnchor="middle",
            )
        )

    principal_points = [(x_pos(year), left_y(value)) for year, value in zip(years, principals)]
    interest_points = [(x_pos(year), left_y(value)) for year, value in zip(years, interests)]
    tenure_points = [(x_pos(year), right_y(value)) for year, value in zip(years, cumulative_interest)]
    drawing.add(PolyLine(principal_points, strokeColor=TEAL_DARK, strokeWidth=2.2, fillColor=None))
    drawing.add(PolyLine(interest_points, strokeColor=ORANGE, strokeWidth=2.2, fillColor=None))
    drawing.add(PolyLine(tenure_points, strokeColor=BLUE, strokeWidth=2.2, fillColor=None, strokeDashArray=[5, 3]))

    legend_y = height - 12
    legend_items = [
        (left, TEAL_DARK, "Annual principal"),
        (left + 115, ORANGE, "Annual interest"),
        (left + 220, BLUE, "Interest over tenure"),
    ]
    for legend_x, colour, label in legend_items:
        drawing.add(Line(legend_x, legend_y, legend_x + 18, legend_y, strokeColor=colour, strokeWidth=2.2))
        drawing.add(String(legend_x + 23, legend_y - 3, label, fontSize=7, fillColor=INK))

    drawing.add(
        String(
            width - right,
            legend_y - 3,
            f"Total interest: {money(running_interest)}",
            fontName="Helvetica-Bold",
            fontSize=8,
            fillColor=NAVY,
            textAnchor="end",
        )
    )
    drawing.add(String(left + plot_width / 2, 5, "Mortgage year", fontSize=7, fillColor=MUTED, textAnchor="middle"))
    return drawing


def projection_chart(projection: pd.DataFrame, width: float, height: float = 190) -> Drawing:
    drawing = Drawing(width, height)
    left = 65
    right = 25
    top = 28
    bottom = 34
    plot_width = width - left - right
    plot_height = height - top - bottom
    years = [as_number(value) for value in projection.get("Year", [])]
    series = [
        ("Property value", TEAL, [as_number(value) for value in projection.get("Property value", [])]),
        ("Estimated equity", TEAL_DARK, [as_number(value) for value in projection.get("Estimated equity", [])]),
        ("Loan balance", ORANGE, [as_number(value) for value in projection.get("Loan balance", [])]),
    ]
    if not years:
        return drawing
    y_max = max([value for _, _, values in series for value in values] + [1.0])
    min_year, max_year = min(years), max(years)

    def x_pos(year: float) -> float:
        if max_year == min_year:
            return left + plot_width / 2
        return left + (year - min_year) / (max_year - min_year) * plot_width

    def y_pos(value: float) -> float:
        return bottom + value / y_max * plot_height

    drawing.add(Rect(left, bottom, plot_width, plot_height, fillColor=WHITE, strokeColor=LINE, strokeWidth=0.7))
    for tick in range(5):
        ratio = tick / 4
        y = bottom + ratio * plot_height
        drawing.add(Line(left, y, left + plot_width, y, strokeColor=colors.HexColor("#e8eaed"), strokeWidth=0.5))
        drawing.add(String(left - 5, y - 3, compact_money(y_max * ratio), fontSize=6.5, fillColor=MUTED, textAnchor="end"))
    for year in years:
        x = x_pos(year)
        drawing.add(String(x, bottom - 13, str(int(year)), fontSize=6.5, fillColor=MUTED, textAnchor="middle"))

    for label, colour, values in series:
        drawing.add(PolyLine([(x_pos(year), y_pos(value)) for year, value in zip(years, values)], strokeColor=colour, strokeWidth=2.2, fillColor=None))

    legend_y = height - 11
    for index, (label, colour, _) in enumerate(series):
        legend_x = left + index * 135
        drawing.add(Line(legend_x, legend_y, legend_x + 18, legend_y, strokeColor=colour, strokeWidth=2.2))
        drawing.add(String(legend_x + 23, legend_y - 3, label, fontSize=7, fillColor=INK))
    drawing.add(String(left + plot_width / 2, 5, "Projection year", fontSize=7, fillColor=MUTED, textAnchor="middle"))
    return drawing


def format_comparison_value(column: str, value: Any) -> str:
    if column in {"LVR", "Deposit %"}:
        return str(value)
    if column == "Actual LVR incl. LMI":
        return percent(value, 1)
    if "$" in column:
        return money(value)
    return str(value)


def build_property_report(
    payload: Dict[str, Any],
    metrics: Dict[str, Any],
    loan_schedules: Sequence[pd.DataFrame],
    deposit_comparison: pd.DataFrame,
    projection: pd.DataFrame | None = None,
) -> bytes:
    buffer = BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Property Feasibility Report",
        author="Property Scout",
        subject="Residential property investment feasibility analysis",
    )
    styles = make_styles()
    address = str(payload.get("property_address") or "Property address not entered")
    generated_at = datetime.now(ZoneInfo("Australia/Sydney")).strftime("%d %b %Y %I:%M %p")

    def page_frame(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setTitle(f"Property Feasibility Report - {address}")
        page_width, _ = page_size
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 8 * mm, page_width - doc.rightMargin, 8 * mm)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 4.5 * mm, "Decision-support summary only. Verify lending, tax, rent, and acquisition inputs independently.")
        canvas.drawRightString(page_width - doc.rightMargin, 4.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    deposit_mode = str(payload.get("deposit_input_mode") or "Percent")
    deposit_input = payload.get("deposit_input_value")
    deposit_display = (
        display_percent(deposit_input)
        if deposit_mode == "Percent"
        else display_money(deposit_input)
    )
    soi_low = as_number(payload.get("statement_price_low"))
    soi_high = as_number(payload.get("statement_price_high"))
    soi_range = f"{money(soi_low)} to {money(soi_high)}" if soi_low or soi_high else "Not available"
    listing_low = as_number(payload.get("listing_price_low"))
    listing_high = as_number(payload.get("listing_price_high"))
    listing_range = f"{money(listing_low)} to {money(listing_high)}" if listing_low or listing_high else "Not available"
    recommendation = display_text(metrics.get("recommendation"), "INCOMPLETE")
    recommendation_reasons = [str(reason) for reason in metrics.get("recommendation_reasons", []) if str(reason).strip()]
    reasons_text = (
        "<br/>".join(escape(reason) for reason in recommendation_reasons[:3])
        if recommendation_reasons
        else "Add price, rent, and finance inputs to generate the recommendation."
    )

    purchase_items = [
        ("Property address", address),
        ("Property type", display_text(payload.get("property_type"), "Not entered")),
        ("REA listed price", listing_range),
        ("Tenancy status", display_text(payload.get("tenancy_status"), "Unknown")),
        ("Suburb", display_text(payload.get("suburb"))),
        ("State / postcode", display_text(f"{payload.get('property_state') or ''} {payload.get('postcode') or ''}".strip())),
        ("Beds / baths", f"{display_text(payload.get('bedrooms'))} / {display_text(payload.get('bathrooms'))}"),
        ("Cars / land", f"{display_text(payload.get('car_spaces'))} / {display_text(payload.get('land_size_sqm'))} sqm"),
        ("SOI price range", soi_range),
        ("Purchase price", display_money(payload.get("price"))),
        ("Property value", display_money(payload.get("property_value"))),
        ("Weekly rent", display_money(payload.get("weekly_rent"))),
        ("Deposit input", f"{deposit_display} ({deposit_mode})"),
        ("Deposit source", display_text(payload.get("deposit_source"), "Cash")),
        ("Calculated deposit", display_money(metrics.get("deposit_amount"))),
        ("Stamp duty", display_money(payload.get("stamp_duty"))),
    ]

    acquisition_rows = [
        ["Purchase price", display_money(payload.get("price"))],
        ["Deposit amount", display_money(metrics.get("deposit_amount"))],
        ["Buying costs", display_money(metrics.get("buying_costs"))],
        ["Deposit plus buying costs", display_money(metrics.get("acquisition_cash_component"))],
        ["Cash required upfront", display_money(metrics.get("cash_required_upfront"))],
        ["Total borrowings", display_money(metrics.get("total_borrowings"))],
        ["Funding gap / surplus", display_money(metrics.get("funding_gap"))],
    ]

    cashflow_rows = [
        ["Pre-tax cash flow (yearly)", display_money(metrics.get("pre_tax_cashflow"))],
        ["Post-tax cash flow (yearly)", display_money(metrics.get("after_tax_cashflow"))],
        ["Pre-tax cash flow (monthly)", display_money(metrics.get("monthly_pre_tax_cashflow"))],
        ["Post-tax cash flow (monthly)", display_money(metrics.get("monthly_after_tax_cashflow"))],
        ["Pre-tax cash flow (weekly)", display_money(metrics.get("weekly_pre_tax_cashflow"))],
        ["Post-tax cash flow (weekly)", display_money(metrics.get("weekly_after_tax_cashflow"))],
        ["Gross yield", display_percent(metrics.get("gross_yield"))],
        ["Net yield before interest", display_percent(metrics.get("net_yield_before_interest"))],
        ["Net yield after interest", display_percent(metrics.get("net_yield_after_interest"))],
    ]

    profile_rows = [
        ["Recommendation", recommendation],
        ["Risk score", f"{as_number(metrics.get('risk_score')):.1f}/10"],
        ["Growth score", f"{as_number(metrics.get('growth_score')):.1f}/10"],
        ["Yield score", f"{as_number(metrics.get('yield_score')):.1f}/10"],
        ["Overall score", f"{as_number(metrics.get('overall_score')):.1f}/10"],
        ["Break-even rent", f"{display_money(metrics.get('break_even_rent_weekly'))}/wk"],
        ["Cash-on-cash", display_percent(metrics.get("cash_on_cash")) if as_number(metrics.get("cash_required_upfront")) else "n/a"],
        ["Funding gap / surplus", display_money(metrics.get("funding_gap"))],
    ]

    loan_rows: List[List[str]] = []
    loans = list(metrics.get("loans", []))
    for loan in loans:
        loan_rows.append(
            [
                loan.name,
                loan.repayment_type,
                f"{loan.effective_term_years:.0f}",
                percent(loan.rate_pct),
                money(loan.amount),
                money(loan.annual_repayment),
            ]
        )
    if not loan_rows:
        loan_rows = [["No active loan", "-", "-", "-", "-", "-"]]

    hero = Table(
        [
            [
                Paragraph(
                    f"<font size='20'><b>Property Feasibility Summary</b></font><br/><font size='11' color='#0f766e'>{escape(address)}</font>",
                    styles["body"],
                ),
                Paragraph(
                    f"<font size=13 color='white'><b>{escape(recommendation)}</b></font><br/><font size=8 color='white'>Generated {escape(generated_at)}</font>",
                    ParagraphStyle(
                        "HeroBadge",
                        parent=styles["body"],
                        alignment=TA_CENTER,
                        textColor=WHITE,
                        fontSize=10,
                        leading=12,
                    ),
                ),
            ],
        ],
        colWidths=[doc.width * 0.72, doc.width * 0.28],
        hAlign="LEFT",
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BACKGROUND", (1, 0), (1, 0), NAVY),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, -1), 8),
                ("RIGHTPADDING", (0, 0), (0, -1), 8),
                ("LEFTPADDING", (1, 0), (1, 0), 8),
                ("RIGHTPADDING", (1, 0), (1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    left_width = doc.width * 0.58
    right_width = doc.width * 0.42

    source_rows = [
        ["REA listing", link_paragraph(str(payload.get("listing_url") or ""), "Open listing", styles["value"])],
        ["Statement of Information", link_paragraph(str(payload.get("statement_source_url") or ""), "Open source", styles["value"])],
        ["Stamp duty", link_paragraph(str(payload.get("stamp_duty_source_url") or ""), "Open source", styles["value"])],
    ]
    source_table = Table(source_rows, colWidths=[right_width * 0.30, right_width * 0.70], hAlign="LEFT")
    source_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PALE_TEAL),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.0),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    left_column = [
        panel_table("Property overview", detail_table(purchase_items, styles, left_width - 10), styles, left_width),
        Spacer(1, 1.0 * mm),
        panel_table(
            "Acquisition snapshot",
            styled_table(["Item", "Value"], acquisition_rows, styles, [left_width * 0.62, left_width * 0.38], font_size=6.9),
            styles,
            left_width,
        ),
        Spacer(1, 1.0 * mm),
        panel_table(
            "Cashflow snapshot",
            styled_table(["Metric", "Value"], cashflow_rows, styles, [left_width * 0.68, left_width * 0.32], font_size=6.9),
            styles,
            left_width,
        ),
    ]

    right_column = [
        panel_table(
            "Recommendation and scores",
            [
                styled_table(["Metric", "Value"], profile_rows, styles, [right_width * 0.63, right_width * 0.37], font_size=6.8),
                Spacer(1, 1.0 * mm),
                Paragraph(f"<b>Decision notes:</b><br/>{reasons_text}", styles["note"]),
            ],
            styles,
            right_width,
        ),
        Spacer(1, 1.0 * mm),
        panel_table(
            "Loan structure",
            styled_table(
                ["Loan", "Type", "Term", "Rate", "Amount", "Annual repayment"],
                loan_rows,
                styles,
                [
                    right_width * 0.22,
                    right_width * 0.12,
                    right_width * 0.09,
                    right_width * 0.11,
                    right_width * 0.21,
                    right_width * 0.25,
                ],
                font_size=6.2,
            ),
            styles,
            right_width,
        ),
        Spacer(1, 1.0 * mm),
        panel_table("Sources", source_table, styles, right_width),
    ]

    main_grid = Table([[left_column, right_column]], colWidths=[left_width, right_width], hAlign="LEFT")
    main_grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story: List[Any] = [
        hero,
        Spacer(1, 1.2 * mm),
        main_grid,
    ]

    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return buffer.getvalue()
