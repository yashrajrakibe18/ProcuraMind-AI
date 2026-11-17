from __future__ import annotations

from dataclasses import dataclass, field

from procureai.shared.enums import Criticality, Operator


@dataclass
class ExtractedRequirement:
    field: str
    label: str
    operator: Operator
    value: str
    unit: str | None
    criticality: Criticality
    page: int
    source_text: str
    value_max: str | None = None


@dataclass
class ExtractedSpec:
    field: str
    label: str
    value_text: str
    value_numeric: float | None
    unit: str | None
    page: int
    source_text: str
    confidence: float = 0.9


@dataclass
class ExtractedQuotation:
    vendor_name: str
    vendor_name_confident: bool = True
    reference: str | None = None
    contact: str | None = None
    currency: str | None = None
    unit_price: float | None = None
    quantity: float | None = None
    tax_percent: float | None = None
    delivery_cost: float | None = None
    delivery_days: float | None = None
    warranty_months: float | None = None
    category: str | None = None
    source_page: int | None = None
    specs: list[ExtractedSpec] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
