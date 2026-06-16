"""
generate_report.py — Texas Construction Intelligence
Auto-generates a weekly PDF digest from clean data + summary JSON.
Outputs to reports/TX_Construction_Intel_YYYYMMDD.pdf

Run after clean.py:
  python scripts/generate_report.py
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CLEAN_DIR   = Path("data/clean")
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

TODAY      = datetime.utcnow().strftime("%Y%m%d")
TODAY_DISP = datetime.utcnow().strftime("%B %d, %Y")

# ── brand colors ──────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#0D2137")
TEAL   = colors.HexColor("#1A7F6E")
AMBER  = colors.HexColor("#D97706")
LIGHT  = colors.HexColor("#F0F4F8")
MID    = colors.HexColor("#CBD5E1")
WHITE  = colors.white
BLACK  = colors.HexColor("#1E293B")
MUTED  = colors.HexColor("#64748B")


# ── helpers ───────────────────────────────────────────────────────────────────

def latest_clean(prefix: str) -> Path | None:
    files = sorted(CLEAN_DIR.glob(f"{prefix}_*.json"), reverse=True)
    return files[0] if files else None


def load_summary() -> dict:
    path = latest_clean("summary")
    if not path:
        log.warning("No summary JSON found — using empty dict")
        return {}
    return json.loads(path.read_text())


def fmt_usd(val) -> str:
    if val is None:
        return "—"
    try:
        v = float(val)
        if v >= 1_000_000_000:
            return f"${v/1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v/1_000:.0f}K"
        return f"${v:,.0f}"
    except (TypeError, ValueError):
        return "—"


def fmt_num(val) -> str:
    if val is None:
        return "—"
    try:
        return f"{int(float(val)):,}"
    except (TypeError, ValueError):
        return "—"


# ── styles ────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["cover_title"] = ParagraphStyle(
        "cover_title", fontName="Helvetica-Bold",
        fontSize=28, leading=34, textColor=WHITE, alignment=TA_LEFT,
    )
    styles["cover_sub"] = ParagraphStyle(
        "cover_sub", fontName="Helvetica",
        fontSize=13, leading=18, textColor=colors.HexColor("#B0C4D8"),
        alignment=TA_LEFT,
    )
    styles["section_header"] = ParagraphStyle(
        "section_header", fontName="Helvetica-Bold",
        fontSize=14, leading=18, textColor=NAVY, spaceBefore=18, spaceAfter=6,
    )
    styles["body"] = ParagraphStyle(
        "body", fontName="Helvetica",
        fontSize=10, leading=15, textColor=BLACK,
    )
    styles["muted"] = ParagraphStyle(
        "muted", fontName="Helvetica",
        fontSize=9, leading=13, textColor=MUTED,
    )
    styles["kicker"] = ParagraphStyle(
        "kicker", fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=TEAL, spaceBefore=4,
    )
    styles["stat_num"] = ParagraphStyle(
        "stat_num", fontName="Helvetica-Bold",
        fontSize=22, leading=26, textColor=NAVY, alignment=TA_CENTER,
    )
    styles["stat_label"] = ParagraphStyle(
        "stat_label", fontName="Helvetica",
        fontSize=8, leading=11, textColor=MUTED, alignment=TA_CENTER,
    )
    styles["footer"] = ParagraphStyle(
        "footer", fontName="Helvetica",
        fontSize=8, leading=11, textColor=MUTED, alignment=TA_CENTER,
    )
    return styles


# ── page template ─────────────────────────────────────────────────────────────

def on_page(canvas, doc):
    """Draw header stripe and footer on every page after the cover."""
    if doc.page == 1:
        # Cover page — full navy background
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, letter[1] - 0.35 * inch, letter[0], 0.35 * inch, fill=1, stroke=0)
        return

    # Inner pages — thin top bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, letter[1] - 0.3 * inch, letter[0], 0.3 * inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.5 * inch, letter[1] - 0.19 * inch, "TX CONSTRUCTION INTELLIGENCE")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(letter[0] - 0.5 * inch, letter[1] - 0.19 * inch, TODAY_DISP)

    # Footer
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawCentredString(
        letter[0] / 2, 0.35 * inch,
        f"TX Construction Intelligence  ·  Week of {TODAY_DISP}  ·  Page {doc.page}  ·  Data: USASpending.gov, US Census BPS, City of Austin Open Data"
    )
    canvas.setStrokeColor(MID)
    canvas.setLineWidth(0.5)
    canvas.line(0.5 * inch, 0.5 * inch, letter[0] - 0.5 * inch, 0.5 * inch)


# ── content builders ──────────────────────────────────────────────────────────

def build_cover(styles) -> list:
    elems = []
    elems.append(Spacer(1, 2.2 * inch))
    elems.append(Paragraph("TX Construction", styles["cover_title"]))
    elems.append(Paragraph("Intelligence", styles["cover_title"]))
    elems.append(Spacer(1, 0.15 * inch))
    elems.append(Paragraph(f"Weekly Market Digest  ·  {TODAY_DISP}", styles["cover_sub"]))
    elems.append(Spacer(1, 0.1 * inch))
    elems.append(Paragraph(
        "Federal contracts · Construction permits · Vendor activity · Southeast Texas focus",
        styles["cover_sub"]
    ))
    elems.append(Spacer(1, 2.5 * inch))
    elems.append(Paragraph(
        "Data sources: USASpending.gov · US Census Bureau BPS · City of Austin Open Data",
        styles["muted"]
    ))
    elems.append(PageBreak())
    return elems


def build_stat_card(label: str, value: str, styles) -> list:
    return [
        Paragraph(value, styles["stat_num"]),
        Paragraph(label, styles["stat_label"]),
    ]


def build_summary_table(summary: dict, styles) -> list:
    elems = []
    c = summary.get("contracts", {})
    p = summary.get("permits", {})

    elems.append(Paragraph("Weekly at a glance", styles["section_header"]))
    elems.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=10))

    stat_data = [[
        Paragraph(fmt_num(c.get("total_count")), styles["stat_num"]),
        Paragraph(fmt_usd(c.get("total_value")), styles["stat_num"]),
        Paragraph(fmt_usd(c.get("avg_value")), styles["stat_num"]),
        Paragraph(fmt_num(p.get("total_count")), styles["stat_num"]),
    ], [
        Paragraph("Federal contracts", styles["stat_label"]),
        Paragraph("Total contract value", styles["stat_label"]),
        Paragraph("Avg contract size", styles["stat_label"]),
        Paragraph("Permits tracked", styles["stat_label"]),
    ]]

    t = Table(stat_data, colWidths=[1.6 * inch] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [LIGHT, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, MID),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, 0), 2, TEAL),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 0.2 * inch))
    return elems


def build_top_contracts(summary: dict, styles) -> list:
    elems = []
    elems.append(Paragraph("Top federal contracts — Texas", styles["section_header"]))
    elems.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8))

    by_county = summary.get("contracts", {}).get("by_county", {})
    by_naics  = summary.get("contracts", {}).get("by_naics", {})

    if by_county:
        elems.append(Paragraph("Contract value by county (top 10)", styles["kicker"]))
        rows = [["County", "Total value"]]
        for county, val in list(by_county.items())[:10]:
            rows.append([county or "Unknown", fmt_usd(val)])

        t = Table(rows, colWidths=[4.0 * inch, 2.5 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.5, MID),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        elems.append(t)
        elems.append(Spacer(1, 0.15 * inch))

    if by_naics:
        elems.append(Paragraph("Contract value by construction type (NAICS)", styles["kicker"]))
        rows = [["Sector", "Total value"]]
        for naics, val in list(by_naics.items())[:8]:
            label = str(naics)[:55] + ("…" if len(str(naics)) > 55 else "")
            rows.append([label, fmt_usd(val)])

        t = Table(rows, colWidths=[4.0 * inch, 2.5 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.5, MID),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        elems.append(t)

    elems.append(Spacer(1, 0.2 * inch))
    return elems


def build_top_permits(summary: dict, styles) -> list:
    elems = []
    p = summary.get("permits", {})
    top = p.get("top_projects", [])

    elems.append(Paragraph("Top construction permits", styles["section_header"]))
    elems.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8))

    if not top:
        elems.append(Paragraph("No permit data available this week.", styles["muted"]))
        return elems

    rows = [["Address", "City", "Type", "Valuation", "Sq Ft", "Date"]]
    for proj in top[:15]:
        addr = str(proj.get("address", "") or "")[:30]
        rows.append([
            addr,
            proj.get("city", ""),
            str(proj.get("permit_type", "") or "")[:22],
            fmt_usd(proj.get("valuation_usd")),
            fmt_num(proj.get("sq_ft")),
            str(proj.get("issued_date", "") or "")[:10],
        ])

    t = Table(rows, colWidths=[1.8*inch, 0.75*inch, 1.6*inch, 0.85*inch, 0.65*inch, 0.8*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, MID),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 0.2 * inch))
    return elems


def build_disclaimer(styles) -> list:
    return [
        HRFlowable(width="100%", thickness=0.5, color=MID, spaceBefore=20, spaceAfter=8),
        Paragraph(
            "Data sourced from USASpending.gov, US Census Bureau Building Permits Survey, and City of Austin Open Data. "
            "All figures reflect publicly available government data as of the report date. "
            "This report is provided for informational purposes only. Not investment or legal advice.",
            styles["muted"]
        ),
    ]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== TX Construction Intel — generate_report.py ===")
    summary = load_summary()
    styles  = build_styles()

    out_path = REPORTS_DIR / f"TX_Construction_Intel_{TODAY}.pdf"
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )

    elems = []
    elems += build_cover(styles)
    elems += build_summary_table(summary, styles)
    elems += build_top_contracts(summary, styles)
    elems += build_top_permits(summary, styles)
    elems += build_disclaimer(styles)

    doc.build(elems, onFirstPage=on_page, onLaterPages=on_page)
    log.info(f"Report saved → {out_path}")
    return out_path


if __name__ == "__main__":
    main()
