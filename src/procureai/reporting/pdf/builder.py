"""PDF evidence report (ReportLab). Status is always printed as text, never colour alone."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from procureai.reporting.data import DISCLAIMER, LEGEND, STATUS_ORDER, ReportData, req_text

NAVY = colors.HexColor("#0F2A47")
LINE = colors.HexColor("#C9D3DF")
ZEBRA = colors.HexColor("#F4F7FA")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], textColor=NAVY, fontSize=20, alignment=0),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=NAVY, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontSize=9, leading=12),
        "cell": ParagraphStyle("c", parent=base["BodyText"], fontSize=7.5, leading=9.5),
        "head": ParagraphStyle(
            "hd", parent=base["BodyText"], fontSize=7.5, leading=9.5, textColor=colors.white, fontName="Helvetica-Bold"
        ),
        "small": ParagraphStyle("s", parent=base["BodyText"], fontSize=7.5, textColor=colors.HexColor("#4A5A6B")),
    }


def _table(rows: list[list], widths: list[float], st: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(escape(str(c)), st["head"]) for c in rows[0]]]
    data += [
        [
            c
            if not isinstance(c, str | int | float) and c is not None
            else Paragraph(escape(str(c if c is not None else "—")), st["cell"])
            for c in r
        ]
        for r in rows[1:]
    ]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#6B7A8A"))
    canvas.drawString(15 * mm, 8 * mm, "ProcureAI - decision support report. Human review and approval required.")
    canvas.drawRightString(landscape(A4)[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(d: ReportData) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"ProcureAI report - {d.project.title}",
    )
    width = landscape(A4)[0] - 30 * mm
    s: list = [Paragraph("ProcureAI Evaluation Report", st["title"]), Paragraph(escape(d.project.title), st["h2"])]
    approved = d.run.summary.get("approved_by")
    meta = [
        ["Field", "Value", "Type"],
        ["Project", d.project.title, "Source fact"],
        ["Item / quantity", f"{d.project.item_description or '—'} / {d.project.tender_quantity or '—'}", "Source fact"],
        ["Analysis run", f"{d.run.id} ({d.run.status})", "Calculated"],
        ["Generated (UTC)", d.generated_at.strftime("%Y-%m-%d %H:%M"), "Calculated"],
        [
            "Human approval",
            f"Approved by user {approved}" if approved else "Not yet approved",
            "Unresolved" if not approved else "Source fact",
        ],
        [
            "Language model",
            f"{d.run.model_info.get('llm_provider')} - {d.run.model_info.get('llm_role')}",
            "Model interpretation",
        ],
    ]
    s += [_table(meta, [45 * mm, width - 90 * mm, 45 * mm], st), Spacer(1, 6)]
    s.append(Paragraph("<b>How to read this report</b>", st["body"]))
    s += [Paragraph(f"<b>{k}</b>: {v}", st["small"]) for k, v in LEGEND.items()]
    s += [Spacer(1, 4), Paragraph(escape(DISCLAIMER), st["small"])]

    s.append(Paragraph("1. Compliance summary by vendor", st["h2"]))
    short = {
        "Meets Requirement": "Meets",
        "Does Not Meet Requirement": "Does not meet",
        "Missing Information": "Missing info",
        "Requires Human Review": "Needs review",
        "Not Applicable": "N/A",
    }
    rows = [["Vendor (Calculated)"] + [short[x] for x in STATUS_ORDER]]
    rows += [[v] + [c[x] for x in STATUS_ORDER] for v, c in d.counts_by_vendor.items()]
    s.append(
        _table(rows, [width * 0.3] + [width * 0.14] * 5, st) if len(rows) > 1 else Paragraph("No results.", st["body"])
    )

    s.append(Paragraph("2. Requirement-by-vendor matrix", st["h2"]))
    vendors = [v.vendor_name for v in d.vendors]
    by = {(r.requirement_id, r.vendor_name): r for r in d.compliance}
    rows = [["Requirement", "Criticality"] + vendors]
    for rq in d.requirements:
        rows.append(
            [f"{rq.label} {req_text(rq)}", rq.criticality]
            + [(by[(rq.id, v)].effective_status if (rq.id, v) in by else "—") for v in vendors]
        )
    s.append(_table(rows, [width * 0.28, width * 0.1] + [width * 0.62 / max(1, len(vendors))] * len(vendors), st))

    s += [PageBreak(), Paragraph("3. Detailed results with evidence", st["h2"])]
    rows = [
        [
            "Requirement",
            "Vendor",
            "Status",
            "Offered (Source fact)",
            "Page",
            "Explanation (Calculated)",
            "Reviewer note",
        ]
    ]
    for r in d.compliance:
        off = (r.evidence or {}).get("offered") or {}
        status = r.effective_status + (" (manually decided)" if r.effective_status != r.status else "")
        expl = r.explanation
        rows.append(
            [
                r.requirement_label + " " + r.requirement_text,
                r.vendor_name,
                status,
                f"{off.get('value', '—')} [{d.doc_name(off.get('document_id'))}]" if off else "not found",
                off.get("page", "—") if off else "—",
                expl,
                r.reviewer_note or "",
            ]
        )
    s.append(
        _table(
            rows, [width * 0.15, width * 0.1, width * 0.11, width * 0.2, width * 0.04, width * 0.28, width * 0.12], st
        )
    )

    s.append(Paragraph("4. Price analysis", st["h2"]))
    if d.prices:
        rows = [
            [
                "Vendor",
                "Cur.",
                "Subtotal",
                "Tax",
                "Delivery",
                "Total (base)",
                "Unit (base)",
                "Baseline",
                "Dev. %",
                "Source",
                "Flag",
                "Explanation",
            ]
        ]
        for p in d.prices:
            f = lambda v: f"{v:,.2f}" if v is not None else "—"  # noqa: E731
            rows.append(
                [
                    p.vendor_name,
                    p.currency or "—",
                    f(p.subtotal),
                    f(p.tax_amount),
                    f(p.delivery_cost),
                    f(p.normalized_total),
                    f(p.normalized_unit_price),
                    f(p.baseline),
                    f"{p.deviation_pct:+.1f}" if p.deviation_pct is not None else "—",
                    p.baseline_source,
                    "REVIEW" if p.anomaly_flag else "none",
                    p.explanation,
                ]
            )
        s.append(
            _table(
                rows, [width * w for w in (0.09, 0.04, 0.07, 0.06, 0.06, 0.08, 0.07, 0.07, 0.05, 0.07, 0.06, 0.28)], st
            )
        )
        s.append(
            Paragraph(
                f"All 'base' amounts are in {d.prices[0].base_currency} using the configured static FX table.",
                st["small"],
            )
        )
    else:
        s.append(Paragraph("No price analysis available.", st["body"]))

    s.append(Paragraph("5. Policy evidence (retrieved passages)", st["h2"]))
    if d.policy:
        rows = [["Document", "Page", "Score", "Passage (Source fact)"]]
        rows += [[d.doc_name(p.document_id), p.page or "—", f"{p.score:.2f}", p.snippet[:350]] for p in d.policy[:25]]
        s.append(_table(rows, [width * 0.2, width * 0.05, width * 0.06, width * 0.69], st))
    else:
        s.append(
            Paragraph("No policy passages were retrieved (no policy documents, or none were relevant).", st["body"])
        )

    s.append(Paragraph("6. Review items", st["h2"]))
    rows = [["Status", "Kind", "Reason", "Resolution"]]
    rows += [
        [("Unresolved" if r.status == "open" else "Resolved"), r.kind, r.reason, r.resolution_note or ""]
        for r in d.reviews
    ]
    s.append(
        _table(rows, [width * 0.09, width * 0.09, width * 0.57, width * 0.25], st)
        if len(rows) > 1
        else Paragraph("No review items were raised.", st["body"])
    )
    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
