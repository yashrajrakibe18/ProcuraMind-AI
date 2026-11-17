"""Price intelligence: deterministic cost normalization + transparent statistical baselines."""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from procureai.analytics.anomaly_detection.isolation import isolation_advisory
from procureai.analytics.pricing.baselines import evaluate_price
from procureai.config.settings import Settings
from procureai.domain.pricing.calc import MissingPricingData, calculate_quote_cost, convert_currency
from procureai.infrastructure.database.models import (
    HistoricalPurchase,
    PriceAnalysis,
    ProcurementProject,
    Vendor,
    VendorQuotation,
)
from procureai.rag.embeddings.hashing import analyze

logger = logging.getLogger(__name__)
ASSUMPTION = (
    "Assumes quoted unit prices exclude tax; tax and delivery are added; currencies converted with the "
    "configured static FX table."
)


def _similar(a: str, b: str) -> bool:
    ta, tb = set(analyze(a)), set(analyze(b))
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.34 or a.lower() in b.lower() or b.lower() in a.lower()


def run_price_analysis(session: Session, run_id: str, project_id: str, settings: Settings) -> dict:
    project = session.get(ProcurementProject, project_id)
    base, rates = settings.base_currency.upper(), settings.fx_rates
    quotes = list(
        session.scalars(
            select(VendorQuotation).join(Vendor).where(Vendor.project_id == project_id).order_by(Vendor.created_at)
        )
    )
    session.execute(delete(PriceAnalysis).where(PriceAnalysis.run_id == run_id))

    computed: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    for q in quotes:
        qty = q.quantity or (project.tender_quantity if project else None)
        try:
            cost = calculate_quote_cost(q.unit_price, qty, q.currency, q.tax_percent, q.delivery_cost)
            computed[q.id] = {
                "cost": cost,
                "total": convert_currency(cost.total, cost.currency, base, rates),
                "unit": convert_currency(cost.unit_price_all_in, cost.currency, base, rates),
            }
        except MissingPricingData as exc:
            skipped[q.id] = str(exc)

    history = list(session.scalars(select(HistoricalPurchase).where(HistoricalPurchase.project_id == project_id)))
    hist_prices: list[float] = []
    label = (project.item_description if project else "") or ""
    for h in history:
        if label and not _similar(label, h.item_category):
            continue
        try:
            hist_prices.append(convert_currency(h.unit_price, h.currency, base, rates))
        except MissingPricingData:
            continue

    flagged = 0
    for q in quotes:
        if q.id in skipped:
            session.add(
                PriceAnalysis(
                    run_id=run_id,
                    project_id=project_id,
                    quotation_id=q.id,
                    base_currency=base,
                    method="not_computed",
                    explanation=f"Cannot compute cost: {skipped[q.id]}.",
                )
            )
            continue
        info = computed[q.id]
        cost = info["cost"]
        peers = [v["unit"] for k, v in computed.items() if k != q.id]
        common = dict(
            run_id=run_id,
            project_id=project_id,
            quotation_id=q.id,
            subtotal=round(cost.subtotal, 2),
            tax_amount=round(cost.tax_amount, 2),
            delivery_cost=round(cost.delivery_cost, 2),
            normalized_total=round(info["total"], 2),
            normalized_unit_price=round(info["unit"], 2),
            base_currency=base,
        )
        peer = evaluate_price(info["unit"], peers, "peer quotations in this project", settings.price_threshold_pct)
        session.add(
            PriceAnalysis(
                **common,
                baseline=peer.baseline,
                deviation_pct=peer.deviation_pct,
                method=peer.method,
                baseline_source="peer",
                anomaly_flag=peer.anomaly_flag,
                explanation=f"{peer.explanation} {ASSUMPTION}",
            )
        )
        flagged += peer.anomaly_flag
        if hist_prices:
            hist = evaluate_price(info["unit"], hist_prices, "historical purchases", settings.price_threshold_pct)
            note = isolation_advisory(hist_prices, info["unit"], settings.min_history_for_ml)
            session.add(
                PriceAnalysis(
                    **common,
                    baseline=hist.baseline,
                    deviation_pct=hist.deviation_pct,
                    method=hist.method,
                    baseline_source="historical",
                    anomaly_flag=hist.anomaly_flag,
                    explanation=" ".join(x for x in (hist.explanation, note, ASSUMPTION) if x),
                )
            )
            flagged += hist.anomaly_flag
    session.flush()
    return {
        "quotations": len(quotes),
        "priced": len(computed),
        "not_priced": len(skipped),
        "historical_points": len(hist_prices),
        "flagged": flagged,
    }
