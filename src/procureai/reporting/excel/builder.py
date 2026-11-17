"""Excel evidence workbook (openpyxl) with provenance and label columns."""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from procureai.reporting.data import DISCLAIMER, LEGEND, STATUS_ORDER, ReportData, req_text

HEAD_FILL = PatternFill("solid", fgColor="0F2A47")


def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list], widths: list[int] | None = None):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEAD_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(r)
    for i, h in enumerate(header, 1):
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1] if widths else max(12, min(48, len(h) + 6))
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    return ws


def build_excel(d: ReportData) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 26, 70, 22
    ws.append(["ProcureAI Evaluation Report"])
    ws["A1"].font = Font(bold=True, size=14)
    approved = d.run.summary.get("approved_by")
    for row in [
        ["Project", d.project.title, "Source fact"],
        ["Analysis run", f"{d.run.id} ({d.run.status})", "Calculated"],
        ["Generated (UTC)", d.generated_at.strftime("%Y-%m-%d %H:%M"), "Calculated"],
        [
            "Human approval",
            f"Approved by user {approved}" if approved else "Not yet approved",
            "Source fact" if approved else "Unresolved",
        ],
        [
            "Language model",
            f"{d.run.model_info.get('llm_provider')}: {d.run.model_info.get('llm_role')}",
            "Model interpretation",
        ],
        [],
        ["Label", "Meaning"],
    ]:
        ws.append(row)
    ws.append([])
    for k, v in LEGEND.items():
        ws.append([k, v])
    ws.append([])
    ws.append(["Disclaimer", DISCLAIMER])
    ws.append([])
    ws.append(["Vendor"] + STATUS_ORDER)
    for v, counts in d.counts_by_vendor.items():
        ws.append([v] + [counts[s] for s in STATUS_ORDER])

    _sheet(
        wb,
        "Requirements",
        ["Requirement", "Rule", "Criticality", "Source document", "Page", "Source text"],
        [
            [r.label, req_text(r), r.criticality, d.doc_name(r.source_document_id), r.source_page, r.source_text]
            for r in d.requirements
        ],
        [28, 18, 12, 30, 7, 50],
    )
    rows = []
    for r in d.compliance:
        off = (r.evidence or {}).get("offered") or {}
        rows.append(
            [
                r.requirement_label,
                r.requirement_text,
                r.criticality,
                r.category,
                r.vendor_name,
                r.effective_status,
                "manual" if r.effective_status != r.status else r.method,
                off.get("value"),
                d.doc_name(off.get("document_id")) if off else None,
                off.get("page"),
                r.explanation,
                r.reviewer_note,
                "yes" if r.used_unconfirmed_input else "no",
            ]
        )
    _sheet(
        wb,
        "Compliance",
        [
            "Requirement",
            "Rule",
            "Criticality",
            "Category",
            "Vendor",
            "Status",
            "Method",
            "Offered value (Source fact)",
            "Source document",
            "Page",
            "Explanation (Calculated)",
            "Reviewer note",
            "Unconfirmed input",
        ],
        rows,
        [26, 16, 11, 12, 22, 24, 22, 24, 28, 7, 60, 30, 12],
    )
    _sheet(
        wb,
        "Price analysis",
        [
            "Vendor",
            "Currency",
            "Subtotal",
            "Tax",
            "Delivery",
            "Total (base)",
            "Unit all-in (base)",
            "Base currency",
            "Baseline",
            "Deviation %",
            "Baseline source",
            "Method",
            "Flagged for review",
            "Explanation",
        ],
        [
            [
                p.vendor_name,
                p.currency,
                p.subtotal,
                p.tax_amount,
                p.delivery_cost,
                p.normalized_total,
                p.normalized_unit_price,
                p.base_currency,
                p.baseline,
                round(p.deviation_pct, 2) if p.deviation_pct is not None else None,
                p.baseline_source,
                p.method,
                "yes" if p.anomaly_flag else "no",
                p.explanation,
            ]
            for p in d.prices
        ],
        [22, 9, 12, 10, 10, 13, 15, 9, 12, 11, 12, 18, 10, 70],
    )
    _sheet(
        wb,
        "Policy evidence",
        ["Document", "Page", "Score", "Passage (Source fact)"],
        [[d.doc_name(p.document_id), p.page, round(p.score, 3), p.snippet] for p in d.policy],
        [30, 7, 8, 100],
    )
    _sheet(
        wb,
        "Review items",
        ["Status", "Kind", "Reason", "Resolution note"],
        [["Unresolved" if r.status == "open" else "Resolved", r.kind, r.reason, r.resolution_note] for r in d.reviews],
        [12, 14, 100, 50],
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
