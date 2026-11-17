"""Deterministic cost normalization. Totals and deviations are calculated, never inferred by an LLM."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuoteCost:
    subtotal: float
    tax_amount: float
    delivery_cost: float
    total: float
    unit_price_all_in: float
    currency: str


class MissingPricingData(ValueError):
    pass


def calculate_quote_cost(
    unit_price: float | None,
    quantity: float | None,
    currency: str | None,
    tax_percent: float | None,
    delivery_cost: float | None,
) -> QuoteCost:
    if unit_price is None or quantity is None or quantity <= 0:
        raise MissingPricingData("unit price and a positive quantity are required")
    if not currency:
        raise MissingPricingData("currency is required")
    subtotal = unit_price * quantity
    tax_amount = subtotal * (tax_percent or 0.0) / 100.0
    delivery = delivery_cost or 0.0
    total = subtotal + tax_amount + delivery
    return QuoteCost(subtotal, tax_amount, delivery, total, total / quantity, currency.upper())


def convert_currency(amount: float, currency: str, base: str, rates: dict[str, float]) -> float:
    """rates map currency -> value of 1 unit in the base currency."""
    cur, base = currency.upper(), base.upper()
    if cur == base:
        return amount
    if cur not in rates:
        raise MissingPricingData(f"no FX rate for {cur}")
    return amount * rates[cur] / rates.get(base, 1.0)


def deviation_pct(value: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return (value - baseline) / baseline * 100.0
