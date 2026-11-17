"""Independent verification of a run's outputs; raises review items for anything a person must look at."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from procureai.infrastructure.database.models import (
    ComplianceResult,
    PriceAnalysis,
    ReviewItem,
    TenderRequirement,
    Vendor,
    VendorQuotation,
)
from procureai.shared.enums import ComplianceStatus

VALID_STATUSES = {s.value for s in ComplianceStatus}


def verify_run(session: Session, run_id: str, project_id: str) -> dict:
    session.execute(delete(ReviewItem).where(ReviewItem.run_id == run_id))
    items: list[ReviewItem] = []

    def add(kind: str, ref: str | None, reason: str) -> None:
        items.append(ReviewItem(run_id=run_id, project_id=project_id, kind=kind, ref_id=ref, reason=reason))

    vendors = {v.id: v for v in session.scalars(select(Vendor).where(Vendor.project_id == project_id))}
    reqs = {
        r.id: r
        for r in session.scalars(
            select(TenderRequirement).where(
                TenderRequirement.project_id == project_id, TenderRequirement.confirmed.is_(True)
            )
        )
    }
    results = list(session.scalars(select(ComplianceResult).where(ComplianceResult.run_id == run_id)))
    seen = {(r.vendor_id, r.requirement_id) for r in results}

    for vid in vendors:
        for rid in reqs:
            if (vid, rid) not in seen:
                add("verification", None, f"No compliance result for {vendors[vid].vendor_name} / {reqs[rid].label}.")
    for r in results:
        who, what = vendors[r.vendor_id].vendor_name, reqs[r.requirement_id].label
        if r.status not in VALID_STATUSES:
            add("verification", r.id, f"Invalid compliance status '{r.status}' for {who} / {what}.")
        elif r.review_required:
            add("compliance", r.id, f"{who} / {what}: {r.status}. {r.explanation}")
        elif r.status in (ComplianceStatus.MEETS.value, ComplianceStatus.FAILS.value):
            if not (r.evidence or {}).get("offered") or (r.evidence["offered"].get("page") is None):
                add("verification", r.id, f"{who} / {what}: decided without a source page; value is unverified.")

    quotes = list(session.scalars(select(VendorQuotation).join(Vendor).where(Vendor.project_id == project_id)))
    for q in quotes:
        name = vendors[q.vendor_id].vendor_name
        if not q.confirmed:
            add("extraction", q.id, f"{name}: quotation data was extracted automatically and has not been confirmed.")
        for note in q.extraction_notes or []:
            add("extraction", q.id, f"{name}: {note}")

    for pa in session.scalars(select(PriceAnalysis).where(PriceAnalysis.run_id == run_id)):
        name = vendors[session.get(VendorQuotation, pa.quotation_id).vendor_id].vendor_name
        if pa.method == "not_computed":
            add("price", pa.id, f"{name}: price could not be normalised. {pa.explanation}")
        elif pa.anomaly_flag:
            add(
                "price",
                pa.id,
                f"{name}: price deviates from the {pa.baseline_source} baseline "
                f"({pa.deviation_pct:+.1f}%). Review; this is not a finding of misconduct.",
            )
    session.add_all(items)
    session.flush()
    by_kind: dict[str, int] = {}
    for it in items:
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
    return {"open_review_items": len(items), "by_kind": by_kind, "compliance_results_checked": len(results)}
