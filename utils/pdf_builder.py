"""
Builds a structured, styled PDF of the Verified Decision-Support Report using
reportlab (pure Python - no system packages needed on Streamlit Cloud).

Agent output is free-form LLM text, so everything is sanitized first:
reportlab's built-in fonts only cover Windows-1252 characters, so anything
outside that (emoji, arrows, math symbols) is mapped to a plain equivalent or
dropped rather than rendering as black boxes.
"""

import io
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#111827")
INDIGO = colors.HexColor("#4f46e5")
INDIGO_SOFT = colors.HexColor("#eef2ff")
GREEN = colors.HexColor("#047857")
GREEN_SOFT = colors.HexColor("#ecfdf5")
AMBER = colors.HexColor("#b45309")
AMBER_SOFT = colors.HexColor("#fffbeb")
GREY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#e5e7eb")
TEXT = colors.HexColor("#1f2937")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

_REPLACEMENTS = {
    "\u2192": "->", "\u2190": "<-", "\u2265": ">=", "\u2264": "<=",
    "\u2248": "~", "\u2212": "-", "\u2260": "!=", "\u2011": "-",
    "\u2713": "", "\u2714": "", "\u00a0": " ", "\u202f": " ",
    "\u2009": " ", "\u200b": "",
}
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(value) -> str:
    text = "" if value is None else str(value)
    text = _CONTROL_CHARS.sub("", text)
    out = []
    for ch in text:
        if ch in _REPLACEMENTS:
            out.append(_REPLACEMENTS[ch])
        elif ord(ch) < 128:
            out.append(ch)
        else:
            try:
                ch.encode("cp1252")
                out.append(ch)
            except UnicodeEncodeError:
                pass  # drop emoji / unsupported symbols
    return "".join(out)


def _rich(value) -> str:
    text = escape(_clean(value)).strip()
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text.replace("\n", "<br/>")


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _styles() -> dict:
    return {
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=TEXT),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=GREY),
        "h1": ParagraphStyle(
            "h1", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INDIGO,
            spaceBefore=14, spaceAfter=3, keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "h2", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=NAVY,
            spaceBefore=6, spaceAfter=2, keepWithNext=1,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=9.5, leading=13, textColor=TEXT,
            leftIndent=12, bulletIndent=2, spaceAfter=1.5,
        ),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.8, leading=12, textColor=TEXT),
        "cellhead": ParagraphStyle("cellhead", fontName="Helvetica-Bold", fontSize=8.8, leading=12, textColor=colors.white),
        "card": ParagraphStyle("card", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INDIGO),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.white),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#c7d2fe")),
        "status": ParagraphStyle("status", fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=GREEN),
    }


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LIGHT)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(
        MARGIN, 10 * mm,
        "Industria-AI  |  Decision-support output - not a substitute for qualified professional judgment",
    )
    canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _bullets(items, st) -> list:
    flow = []
    for item in _as_list(items):
        if str(item).strip():
            flow.append(Paragraph(_rich(item), st["bullet"], bulletText="\u2022"))
    if not flow:
        flow.append(Paragraph("<i>None stated.</i>", st["small"]))
    return flow


def _box(flowables, bg, border, st_width=CONTENT_W) -> Table:
    t = Table([[flowables]], colWidths=[st_width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def build_pdf(report: dict) -> bytes:
    st = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=16 * mm, bottomMargin=20 * mm,
        title="Verified Decision-Support Report", author="Industria-AI",
    )
    story = []
    counter = {"n": 0}

    def section(title):
        counter["n"] += 1
        story.append(Paragraph(f"{counter['n']}. {_rich(title)}", st["h1"]))
        story.append(HRFlowable(width="100%", thickness=0.6, color=LIGHT, spaceAfter=5))

    # ---- Banner -------------------------------------------------------
    banner = Table(
        [[Paragraph("Verified Decision-Support Report", st["title"])],
         [Paragraph("Industria-AI  |  Human-in-the-loop multi-agent analysis", st["subtitle"])]],
        colWidths=[CONTENT_W],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (0, 0), 16),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 14),
        ("LINEBELOW", (0, -1), (-1, -1), 3, INDIGO),
    ]))
    story.append(banner)
    story.append(Spacer(1, 6))

    status = _clean(report.get("human_verification_status", "UNKNOWN"))
    accepted = status.upper() == "ACCEPTED"
    status_color = GREEN if accepted else AMBER
    status_style = ParagraphStyle("status2", parent=st["status"], textColor=status_color)
    story.append(_box(
        [Paragraph(f"HUMAN VERIFICATION STATUS: {escape(status)}", status_style),
         Paragraph(f"Generated {escape(_clean(report.get('generated_at_utc', '')))}", st["small"])],
        GREEN_SOFT if accepted else AMBER_SOFT, status_color,
    ))

    # ---- 1. Problem ---------------------------------------------------
    section("Problem Statement")
    story.append(Paragraph(_rich(report.get("problem_statement") or "(not provided)"), st["body"]))

    # ---- 2. Interpretation -------------------------------------------
    section("Human-Confirmed Interpretation")
    story.append(Paragraph(_rich(report.get("human_confirmed_interpretation") or "(not provided)"), st["body"]))

    # ---- 3. Domains & agents -----------------------------------------
    section("Relevant Domains & Agents Consulted")
    story.append(Paragraph("Domains", st["h2"]))
    story.extend(_bullets(report.get("relevant_domains"), st))
    story.append(Paragraph("Agents consulted", st["h2"]))
    story.extend(_bullets(report.get("agents_consulted"), st))

    # ---- 4. Evidence --------------------------------------------------
    section("Evidence Collected")
    evidence = _as_list(report.get("evidence_collected"))
    if report.get("evidence_available") and evidence:
        rows = [[Paragraph("Finding", st["cellhead"]), Paragraph("Type", st["cellhead"]), Paragraph("Source", st["cellhead"])]]
        for e in evidence:
            e = e if isinstance(e, dict) else {"finding": e}
            title = _rich(e.get("source_title") or "Source")
            url = _clean(e.get("source_url") or "").strip()
            if url.startswith(("http://", "https://")):
                href = escape(url, {'"': "&quot;"})
                source = f'<link href="{href}" color="#4f46e5"><u>{title}</u></link>'
            else:
                source = title
            cite = f" <b>[{e['citation']}]</b>" if e.get("citation") else ""
            kind = {"academic": "Academic", "web": "Web"}.get(e.get("source_type"), "Unverified")
            rows.append([Paragraph(_rich(e.get("finding", "")) + cite, st["cell"]), Paragraph(kind, st["cell"]),
                         Paragraph(source, st["cell"])])
        table = Table(rows, colWidths=[CONTENT_W * 0.52, CONTENT_W * 0.12, CONTENT_W * 0.36], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, INDIGO_SOFT]),
            ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
    else:
        story.append(_box(
            [Paragraph("<b>No external evidence was available.</b> All findings below are agent "
                       "inference or assumption, not independently verified fact.", st["body"])],
            AMBER_SOFT, AMBER,
        ))
    if report.get("evidence_notes"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"<i>Research notes: {_rich(report['evidence_notes'])}</i>", st["small"]))

    # ---- Tools used ---------------------------------------------------
    section("Tools Used by Agents")
    usage = _as_list(report.get("tool_usage"))
    if usage:
        rows = [[Paragraph(h, st["cellhead"]) for h in ("Time", "Agent", "Tool", "Input", "Result")]]
        for t in usage:
            t = t if isinstance(t, dict) else {}
            rows.append([Paragraph(_rich(t.get(k, "")), st["cell"]) for k in ("time", "agent", "tool", "input")]
                        + [Paragraph(_rich(f"{t.get('status', '')}: {t.get('detail', '')}"), st["cell"])])
        tt = Table(rows, colWidths=[CONTENT_W * w for w in (0.10, 0.22, 0.15, 0.31, 0.22)], repeatRows=1)
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, INDIGO_SOFT]),
            ("GRID", (0, 0), (-1, -1), 0.4, LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(tt)
    else:
        story.append(Paragraph("<i>No tools were called during this analysis.</i>", st["small"]))

    # ---- 5. Specialist analyses --------------------------------------
    section("Specialist Analyses")
    specialists = _as_list(report.get("specialist_findings"))
    for s in specialists:
        s = s if isinstance(s, dict) else {}
        name = s.get("specialist") or s.get("specialist_key") or "Specialist"
        head = Table([[Paragraph(_rich(name), st["card"])]], colWidths=[CONTENT_W])
        head.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), INDIGO_SOFT),
            ("LINEBEFORE", (0, 0), (0, 0), 3, INDIGO),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        if s.get("parse_error"):
            story.append(KeepTogether([
                head, Spacer(1, 3),
                Paragraph("This specialist's output could not be parsed into structured form. Raw text:", st["small"]),
                Paragraph(_rich(s.get("raw_text", "")), st["body"]),
            ]))
            story.append(Spacer(1, 8))
            continue
        block = [head, Spacer(1, 3),
                 Paragraph(f"<b>Confidence:</b> {_rich(s.get('confidence', 'not stated'))}", st["body"]),
                 Paragraph("Possible root causes", st["h2"])]
        block.extend(_bullets(s.get("possible_root_causes"), st))
        story.append(KeepTogether(block))
        if s.get("cause_basis"):
            story.append(Paragraph("Evidence vs. inference", st["h2"]))
            story.extend(_bullets(s.get("cause_basis"), st))
        story.append(Paragraph("Proposed solutions", st["h2"]))
        story.extend(_bullets(s.get("proposed_solutions"), st))
        story.append(Paragraph("Risks of proposed solutions", st["h2"]))
        story.extend(_bullets(s.get("risks_of_proposed_solutions"), st))
        story.append(Spacer(1, 8))
    if not specialists:
        story.append(Paragraph("<i>No specialist findings recorded.</i>", st["small"]))

    # ---- 6. Consolidated solutions -----------------------------------
    section("Consolidated Proposed Solutions")
    story.append(Paragraph(
        "<i>Compiled from the specialists' proposals above; not a new AI-generated recommendation.</i>", st["small"]))
    story.append(Spacer(1, 3))
    n = 0
    for s in specialists:
        if not isinstance(s, dict) or s.get("parse_error"):
            continue
        who = _rich(s.get("specialist") or s.get("specialist_key") or "Specialist")
        for sol in _as_list(s.get("proposed_solutions")):
            if str(sol).strip():
                n += 1
                story.append(Paragraph(f"{_rich(sol)} <font color='#6b7280'>({who})</font>", st["bullet"],
                                       bulletText=f"{n}."))
    if n == 0:
        story.append(Paragraph("<i>No solutions recorded.</i>", st["small"]))

    # ---- 7. Critical review ------------------------------------------
    section("Critical Review")
    cr = report.get("critical_review") or {}
    if cr.get("parse_error"):
        story.append(Paragraph(_rich(cr.get("raw_text", "")), st["body"]))
    else:
        story.append(Paragraph("Critical findings", st["h2"]))
        story.extend(_bullets(cr.get("critical_findings"), st))
        story.append(Paragraph("Alternative explanations considered", st["h2"]))
        story.extend(_bullets(cr.get("alternative_explanations"), st))
        story.append(Paragraph("Unresolved uncertainty", st["h2"]))
        story.extend(_bullets(cr.get("unresolved_uncertainty"), st))
        if cr.get("overall_confidence_assessment"):
            story.append(Paragraph("Overall confidence assessment", st["h2"]))
            story.append(Paragraph(_rich(cr["overall_confidence_assessment"]), st["body"]))

    # ---- References ---------------------------------------------------
    section("References")
    refs = _as_list(report.get("references"))
    if refs:
        for r in refs:
            url = _clean(r.get("url", ""))
            link = ""
            if url.startswith(("http://", "https://")):
                href = escape(url, {'"': "&quot;"})
                link = f' <link href="{href}" color="#4f46e5"><u>{escape(url)}</u></link>'
            story.append(Paragraph(_rich(r.get("text", "")) + link, st["bullet"], bulletText=f"[{r.get('number')}]"))
    else:
        story.append(Paragraph("<i>No academic papers were cited in this analysis.</i>", st["small"]))
    related = _as_list(report.get("related_literature"))
    if related:
        story.append(Paragraph("Related literature (retrieved, not cited)", st["h2"]))
        for r in related:
            url = _clean(r.get("url", ""))
            href = escape(url, {'"': "&quot;"})
            link = f' <link href="{href}" color="#4f46e5"><u>{escape(url)}</u></link>' if url.startswith("http") else ""
            story.append(Paragraph(_rich(r.get("text", "")) + link, st["bullet"], bulletText="\u2022"))

    # ---- Human verification -------------------------------------------
    section("Human Feedback & Verification")
    history = _as_list(report.get("human_feedback_history"))
    if history:
        for entry in history:
            entry = entry if isinstance(entry, dict) else {"detail": entry}
            story.append(Paragraph(
                f"<b>[{_rich(entry.get('timestamp', ''))}] {_rich(entry.get('decision', ''))}</b> - "
                f"{_rich(entry.get('detail', ''))}", st["bullet"], bulletText="\u2022"))
    else:
        story.append(Paragraph("<i>No revisions were requested.</i>", st["small"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Final human decision recorded: <b>{escape(status)}</b>", st["body"]))

    # ---- 9. Warnings --------------------------------------------------
    section("Important Warnings & Uncertainties")
    warn_flow = [Paragraph(_rich(w), st["bullet"], bulletText="!") for w in _as_list(report.get("warnings"))]
    story.append(_box(warn_flow or [Paragraph("None.", st["body"])], AMBER_SOFT, AMBER))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<i>Based on the available evidence and agent analysis above. Further verification by a "
        "qualified human expert is recommended before acting on any proposed solution.</i>", st["small"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
