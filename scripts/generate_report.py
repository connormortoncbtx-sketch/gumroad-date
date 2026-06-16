"""
generate_report.py — Texas Construction Intelligence
Generates a polished weekly PDF digest from clean data + summary JSON.

Run: python scripts/generate_report.py
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CLEAN_DIR   = Path("data/clean")
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

TODAY      = datetime.utcnow().strftime("%Y%m%d")
TODAY_DISP = datetime.utcnow().strftime("%B %d, %Y")

NAVY  = colors.HexColor("#0D2137")
TEAL  = colors.HexColor("#1A7F6E")
AMBER = colors.HexColor("#D97706")
LIGHT = colors.HexColor("#F0F4F8")
MID   = colors.HexColor("#CBD5E1")
MUTED = colors.HexColor("#64748B")
WHITE = colors.white
BLACK = colors.HexColor("#1E293B")
GREEN = colors.HexColor("#15803D")
RED   = colors.HexColor("#DC2626")


def latest(prefix):
    files = sorted(CLEAN_DIR.glob(f"{prefix}_*.json"), reverse=True)
    return json.loads(files[0].read_text()) if files else {}


def fmt_usd(val, short=False):
    try:
        v = float(val)
        if short:
            if v >= 1_000_000_000: return f"${v/1_000_000_000:.1f}B"
            if v >= 1_000_000:     return f"${v/1_000_000:.1f}M"
            if v >= 1_000:         return f"${v/1_000:.0f}K"
        return f"${v:,.0f}"
    except Exception:
        return "—"


def fmt_num(val):
    try:    return f"{int(float(val)):,}"
    except: return "—"


def styles():
    s = {}
    def ps(name, **kw):
        s[name] = ParagraphStyle(name, **kw)
    ps("cover_title",   fontName="Helvetica-Bold", fontSize=32, leading=38, textColor=WHITE)
    ps("cover_sub",     fontName="Helvetica",      fontSize=13, leading=18, textColor=colors.HexColor("#B0C4D8"))
    ps("cover_date",    fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=TEAL)
    ps("h1",            fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=NAVY, spaceBefore=14, spaceAfter=4)
    ps("h2",            fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY, spaceBefore=8,  spaceAfter=3)
    ps("body",          fontName="Helvetica",      fontSize=9,  leading=13, textColor=BLACK)
    ps("muted",         fontName="Helvetica",      fontSize=8,  leading=11, textColor=MUTED)
    ps("kicker",        fontName="Helvetica-Bold", fontSize=8,  leading=11, textColor=TEAL, spaceBefore=10)
    ps("stat_num",      fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY, alignment=TA_CENTER)
    ps("stat_label",    fontName="Helvetica",      fontSize=7,  leading=10, textColor=MUTED, alignment=TA_CENTER)
    ps("table_header",  fontName="Helvetica-Bold", fontSize=8,  leading=10, textColor=WHITE)
    ps("table_cell",    fontName="Helvetica",      fontSize=8,  leading=10, textColor=BLACK)
    ps("insight",       fontName="Helvetica",      fontSize=9,  leading=13, textColor=BLACK,
       leftIndent=8, borderPadding=6)
    return s


def on_page(canvas, doc):
    w, h = letter
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, h - 0.4*inch, w, 0.4*inch, fill=1, stroke=0)
        return
    # Header
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 0.28*inch, w, 0.28*inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(0.5*inch, h - 0.17*inch, "TX CONSTRUCTION INTELLIGENCE  ·  CONFIDENTIAL")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(w - 0.5*inch, h - 0.17*inch, f"{TODAY_DISP}  ·  Page {doc.page}")
    # Footer
    canvas.setStrokeColor(MID)
    canvas.setLineWidth(0.5)
    canvas.line(0.5*inch, 0.45*inch, w - 0.5*inch, 0.45*inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawCentredString(w/2, 0.3*inch,
        "Data: USASpending.gov federal awards API  ·  TX Construction Intelligence Weekly Digest  ·  For subscriber use only")


def tbl_style(header_color=NAVY, stripe=LIGHT):
    return TableStyle([
        ("BACKGROUND",   (0,0), (-1,0),  header_color),
        ("TEXTCOLOR",    (0,0), (-1,0),  WHITE),
        ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, stripe]),
        ("GRID",         (0,0), (-1,-1), 0.4, MID),
        ("TOPPADDING",   (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
        ("LEFTPADDING",  (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ])


def build_cover(S):
    return [
        Spacer(1, 1.8*inch),
        Paragraph("TX Construction", S["cover_title"]),
        Paragraph("Intelligence", S["cover_title"]),
        Spacer(1, 0.12*inch),
        Paragraph(f"Weekly Market Digest", S["cover_sub"]),
        Spacer(1, 0.06*inch),
        Paragraph(f"Week of {TODAY_DISP}", S["cover_date"]),
        Spacer(1, 0.35*inch),
        Paragraph(
            "Federal contract awards  ·  Vendor intelligence  ·  Sector analysis  ·  Geographic breakdown",
            S["cover_sub"]
        ),
        Spacer(1, 2.8*inch),
        Paragraph("USASpending.gov  ·  Weekly automated pipeline", S["muted"]),
        PageBreak(),
    ]


def build_executive_summary(c, S):
    elems = []
    elems.append(Paragraph("Executive summary", S["h1"]))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=10))

    total    = c.get("total_count", 0)
    val      = c.get("total_value", 0)
    avg      = c.get("avg_value", 0)
    median   = c.get("median_value", 0)
    top_rec  = c.get("top_recipient", "—")
    top_val  = c.get("top_recipient_value", 0)
    by_county= c.get("by_county", {})
    top_county = list(by_county.keys())[0] if by_county else "—"
    top_county_val = list(by_county.values())[0] if by_county else 0

    # Stat cards
    stats = [
        [Paragraph(fmt_usd(total, True), S["stat_num"]),
         Paragraph(fmt_usd(val, True), S["stat_num"]),
         Paragraph(fmt_usd(avg, True), S["stat_num"]),
         Paragraph(fmt_usd(median, True), S["stat_num"])],
        [Paragraph("Total contracts", S["stat_label"]),
         Paragraph("Total obligation value", S["stat_label"]),
         Paragraph("Average contract size", S["stat_label"]),
         Paragraph("Median contract size", S["stat_label"])],
    ]
    t = Table(stats, colWidths=[1.55*inch]*4)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), LIGHT),
        ("LINEABOVE",    (0,0), (-1,0),  2.5, TEAL),
        ("GRID",         (0,0), (-1,-1), 0.4, MID),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 10),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 0.15*inch))

    # Key insights narrative
    elems.append(Paragraph("Key findings this week", S["h2"]))
    insights = [
        f"<b>{fmt_num(total)} federal construction and equipment contracts</b> were awarded in Texas over the past 52 weeks, representing <b>{fmt_usd(val, True)}</b> in total federal obligations.",
        f"The largest single recipient was <b>{top_rec}</b>, capturing <b>{fmt_usd(top_val, True)}</b> in contract value — representing {round(top_val/val*100, 1) if val else 0}% of all tracked awards.",
        f"<b>{top_county} County</b> leads all Texas counties by award volume at <b>{fmt_usd(top_county_val, True)}</b>, driven primarily by {list(c.get('by_agency', {}).keys())[0] if c.get('by_agency') else 'federal agencies'}.",
        f"The average contract size of <b>{fmt_usd(avg, True)}</b> versus a median of <b>{fmt_usd(median, True)}</b> indicates a skewed distribution — a small number of large awards dominate total spend.",
    ]
    for insight in insights:
        elems.append(Paragraph(f"• {insight}", S["body"]))
        elems.append(Spacer(1, 4))

    return elems


def build_county_breakdown(c, S):
    elems = []
    elems.append(Paragraph("Geographic breakdown — by county", S["h1"]))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=8))

    by_county = c.get("by_county", {})
    if not by_county:
        elems.append(Paragraph("No county data available this week.", S["muted"]))
        return elems

    total_val = c.get("total_value", 1)
    rows = [["County", "Total obligations", "% of TX total", "Est. contracts"]]
    county_items = list(by_county.items())[:20]
    county_total = sum(v for _, v in county_items)

    for county, val in county_items:
        pct   = round(val / total_val * 100, 1) if total_val else 0
        # Estimate contract count proportionally
        est_n = round(c.get("total_count", 0) * val / total_val) if total_val else "—"
        rows.append([
            county or "Unknown",
            fmt_usd(val),
            f"{pct}%",
            fmt_num(est_n),
        ])

    t = Table(rows, colWidths=[2.3*inch, 1.7*inch, 1.2*inch, 1.2*inch])
    ts = tbl_style()
    ts.add("ALIGN", (1, 0), (-1, -1), "RIGHT")
    t.setStyle(ts)
    elems.append(t)
    elems.append(Spacer(1, 0.1*inch))

    # City breakdown
    by_city = c.get("by_city", {})
    if by_city:
        elems.append(Paragraph("Top cities by obligation volume", S["kicker"]))
        city_rows = [["City", "Total obligations"]]
        for city, val in list(by_city.items())[:12]:
            if city.strip():
                city_rows.append([city, fmt_usd(val)])
        t2 = Table(city_rows, colWidths=[3.5*inch, 2.9*inch])
        ts2 = tbl_style(header_color=colors.HexColor("#1A4060"))
        ts2.add("ALIGN", (1, 0), (1, -1), "RIGHT")
        t2.setStyle(ts2)
        elems.append(t2)

    return elems


def build_sector_analysis(c, S):
    elems = []
    elems.append(Paragraph("Sector analysis — NAICS breakdown", S["h1"]))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=8))

    by_naics = c.get("by_naics", {})
    if not by_naics:
        elems.append(Paragraph("No sector data available.", S["muted"]))
        return elems

    total_val = c.get("total_value", 1)
    rows = [["NAICS sector", "Total obligations", "Share"]]
    for naics, val in list(by_naics.items())[:15]:
        if naics.strip():
            pct = round(val / total_val * 100, 1) if total_val else 0
            label = str(naics)[:58] + ("…" if len(str(naics)) > 58 else "")
            rows.append([label, fmt_usd(val), f"{pct}%"])

    t = Table(rows, colWidths=[3.8*inch, 1.7*inch, 0.9*inch])
    ts = tbl_style()
    ts.add("ALIGN", (1, 0), (-1, -1), "RIGHT")
    t.setStyle(ts)
    elems.append(t)
    elems.append(Spacer(1, 0.12*inch))

    # PSC breakdown
    by_psc = c.get("by_psc", {})
    if by_psc:
        elems.append(Paragraph("Product/Service code (PSC) breakdown", S["kicker"]))
        psc_rows = [["PSC description", "Obligations"]]
        for psc, val in list(by_psc.items())[:10]:
            if psc.strip():
                label = str(psc)[:58] + ("…" if len(str(psc)) > 58 else "")
                psc_rows.append([label, fmt_usd(val)])
        t2 = Table(psc_rows, colWidths=[4.5*inch, 1.9*inch])
        ts2 = tbl_style(header_color=colors.HexColor("#1A4060"))
        ts2.add("ALIGN", (1, 0), (1, -1), "RIGHT")
        t2.setStyle(ts2)
        elems.append(t2)

    return elems


def build_top_recipients(c, S):
    elems = []
    elems.append(Paragraph("Top vendors by obligation value", S["h1"]))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=8))

    by_rec = c.get("by_recipient", {})
    if not by_rec:
        elems.append(Paragraph("No recipient data available.", S["muted"]))
        return elems

    total_val = c.get("total_value", 1)
    rows = [["#", "Vendor name", "Total obligations", "% share"]]
    for i, (name, val) in enumerate(list(by_rec.items())[:15], 1):
        if name.strip():
            pct = round(val / total_val * 100, 1) if total_val else 0
            rows.append([str(i), name[:42], fmt_usd(val), f"{pct}%"])

    t = Table(rows, colWidths=[0.3*inch, 3.5*inch, 1.6*inch, 0.9*inch])
    ts = tbl_style()
    ts.add("ALIGN", (0, 0), (0, -1), "CENTER")
    ts.add("ALIGN", (2, 0), (-1, -1), "RIGHT")
    t.setStyle(ts)
    elems.append(t)
    return elems


def build_agency_breakdown(c, S):
    elems = []
    elems.append(Paragraph("Awarding agency breakdown", S["h1"]))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=8))

    by_agency = c.get("by_agency", {})
    if not by_agency:
        elems.append(Paragraph("No agency data available.", S["muted"]))
        return elems

    total_val = c.get("total_value", 1)
    rows = [["Agency", "Total obligations", "Share"]]
    for agency, val in list(by_agency.items())[:12]:
        if agency.strip():
            pct = round(val / total_val * 100, 1) if total_val else 0
            rows.append([agency[:50], fmt_usd(val), f"{pct}%"])

    t = Table(rows, colWidths=[3.8*inch, 1.7*inch, 0.9*inch])
    ts = tbl_style()
    ts.add("ALIGN", (1, 0), (-1, -1), "RIGHT")
    t.setStyle(ts)
    elems.append(t)
    return elems


def build_top_contracts(c, S):
    elems = []
    elems.append(Paragraph("Notable contracts this week", S["h1"]))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=8))
    elems.append(Paragraph(
        "The 25 highest-value contracts awarded in Texas during the reporting period.",
        S["body"]
    ))
    elems.append(Spacer(1, 6))

    top = c.get("top_contracts", [])
    if not top:
        elems.append(Paragraph("No contract detail available.", S["muted"]))
        return elems

    rows = [["Recipient", "Value", "City / County", "Agency", "Description", "Date"]]
    for contract in top:
        loc = ", ".join(filter(None, [
            str(contract.get("perf_city", "") or "").strip(),
            str(contract.get("perf_county", "") or "").strip(),
        ])) or "TX"
        desc = str(contract.get("description", "") or "")[:35]
        rows.append([
            str(contract.get("recipient", "") or "")[:22],
            fmt_usd(contract.get("obligation_usd"), short=True),
            loc[:20],
            str(contract.get("agency", "") or "")[:18],
            desc,
            str(contract.get("action_date", "") or "")[:10],
        ])

    t = Table(rows, colWidths=[1.5*inch, 0.7*inch, 1.3*inch, 1.2*inch, 1.5*inch, 0.65*inch])
    ts = tbl_style()
    ts.add("ALIGN", (1, 0), (1, -1), "RIGHT")
    ts.add("FONTSIZE", (0, 0), (-1, -1), 7)
    t.setStyle(ts)
    elems.append(t)
    return elems


def build_disclaimer(S):
    return [
        Spacer(1, 0.3*inch),
        HRFlowable(width="100%", thickness=0.5, color=MID, spaceAfter=6),
        Paragraph(
            "This report is generated automatically from publicly available data sourced from USASpending.gov, "
            "the official U.S. government portal for federal spending data maintained by the Department of the Treasury. "
            "All figures reflect obligations as reported by federal agencies and are subject to revision. "
            "For subscriber use only. Not for redistribution.",
            S["muted"]
        ),
    ]


def main():
    log.info("=== TX Construction Intel — generate_report.py ===")

    summary = latest("summary")
    c       = summary.get("contracts", {})
    S       = styles()

    out = REPORTS_DIR / f"TX_Construction_Intel_{TODAY}.pdf"
    doc = SimpleDocTemplate(
        str(out), pagesize=letter,
        leftMargin=0.55*inch, rightMargin=0.55*inch,
        topMargin=0.6*inch,   bottomMargin=0.6*inch,
    )

    elems = []
    elems += build_cover(S)
    elems += build_executive_summary(c, S)
    elems.append(PageBreak())
    elems += build_county_breakdown(c, S)
    elems.append(PageBreak())
    elems += build_sector_analysis(c, S)
    elems.append(PageBreak())
    elems += build_top_recipients(c, S)
    elems += [Spacer(1, 0.2*inch)]
    elems += build_agency_breakdown(c, S)
    elems.append(PageBreak())
    elems += build_top_contracts(c, S)
    elems += build_disclaimer(S)

    doc.build(elems, onFirstPage=on_page, onLaterPages=on_page)
    log.info(f"Report saved → {out}")
    return out


if __name__ == "__main__":
    main()
