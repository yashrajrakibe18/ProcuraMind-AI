"""Request/response schemas. Distinct from ORM models; ORM objects are never returned directly."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth -------------------------------------------------------------------------------------------------
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str


class UserOut(_Out):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---- projects ---------------------------------------------------------------------------------------------
class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    org_id: str | None = None
    domain: Literal["general", "procurement", "hr", "support", "legal", "finance", "operations", "knowledge", "contracts", "data"] = "general"


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    status: Literal["draft", "in_review", "analyzed", "archived"] | None = None
    tender_quantity: float | None = Field(default=None, gt=0)
    item_description: str | None = Field(default=None, max_length=255)


class ProjectOut(_Out):
    id: str
    title: str
    description: str
    owner_id: str
    status: str
    item_description: str | None
    tender_quantity: float | None
    org_id: str | None = None
    domain: str = "general"
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectOut):
    document_count: int = 0
    vendor_count: int = 0
    requirement_count: int = 0
    latest_run_status: str | None = None


# ---- documents --------------------------------------------------------------------------------------------
class DocumentOut(_Out):
    id: str
    project_id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    document_type: str
    classification_confidence: float
    checksum: str
    processing_status: str
    processing_error: str | None
    page_count: int
    created_at: datetime


class DocumentPageOut(_Out):
    page_number: int
    text: str
    ocr_used: bool


# ---- requirements -----------------------------------------------------------------------------------------
class RequirementIn(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    operator: Literal[">=", "<=", ">", "<", "==", "between", "contains"]
    required_value: str = Field(min_length=1, max_length=255)
    required_value_max: str | None = None
    unit: str | None = Field(default=None, max_length=32)
    criticality: Literal["mandatory", "desirable"] = "mandatory"


class RequirementUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    operator: Literal[">=", "<=", ">", "<", "==", "between", "contains"] | None = None
    required_value: str | None = Field(default=None, min_length=1, max_length=255)
    required_value_max: str | None = None
    unit: str | None = None
    criticality: Literal["mandatory", "desirable"] | None = None
    confirmed: bool | None = None


class RequirementOut(_Out):
    id: str
    project_id: str
    field: str
    label: str
    operator: str
    required_value: str
    required_value_max: str | None
    unit: str | None
    criticality: str
    source_document_id: str | None
    source_page: int | None
    source_text: str
    confirmed: bool


class ExtractionReport(BaseModel):
    created: int
    kept_confirmed: int = 0
    skipped: list[str] = []
    warnings: list[str] = []


# ---- vendors ----------------------------------------------------------------------------------------------
class SpecOut(_Out):
    id: str
    field: str
    label: str
    value_text: str
    value_numeric: float | None
    unit: str | None
    source_page: int | None
    source_text: str
    confidence: float


class SpecUpdate(BaseModel):
    value_text: str = Field(min_length=1, max_length=255)


class QuotationOut(_Out):
    id: str
    vendor_id: str
    document_id: str | None
    unit_price: float | None
    quantity: float | None
    currency: str | None
    tax_percent: float | None
    delivery_cost: float | None
    delivery_days: float | None
    warranty_months: float | None
    item_category: str | None
    source_page: int | None
    confirmed: bool
    extraction_notes: list[str]
    specifications: list[SpecOut]


class QuotationUpdate(BaseModel):
    unit_price: float | None = Field(default=None, gt=0)
    quantity: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    tax_percent: float | None = Field(default=None, ge=0, le=100)
    delivery_cost: float | None = Field(default=None, ge=0)
    confirmed: bool | None = None


class VendorOut(_Out):
    id: str
    project_id: str
    vendor_name: str
    contact: str | None
    reference: str | None
    document_id: str | None
    quotations: list[QuotationOut]


class VendorUpdate(BaseModel):
    vendor_name: str = Field(min_length=1, max_length=255)


# ---- analysis ---------------------------------------------------------------------------------------------
class RunCreate(BaseModel):
    auto_confirm: bool = False


class StepOut(_Out):
    id: str
    sequence: int
    name: str
    status: str
    attempt: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None
    step_metadata: dict[str, Any]


class RunOut(_Out):
    id: str
    project_id: str
    workflow_version: str
    status: str
    created_by: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    error: str | None
    summary: dict[str, Any]
    model_info: dict[str, Any]
    steps: list[StepOut] = []


class ReviewItemOut(_Out):
    id: str
    run_id: str
    project_id: str
    kind: str
    ref_id: str | None
    reason: str
    status: str
    resolution_note: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    created_at: datetime


class ReviewResolve(BaseModel):
    note: str = Field(min_length=3, max_length=2000)
    decision: Literal["meets", "fails", "not_applicable", "acknowledged"] = "acknowledged"


class ComplianceResultOut(BaseModel):
    id: str
    run_id: str
    vendor_id: str
    vendor_name: str
    requirement_id: str
    requirement_label: str
    requirement_text: str
    criticality: str
    category: str
    status: str
    effective_status: str
    method: str
    explanation: str
    evidence: dict[str, Any]
    review_required: bool
    used_unconfirmed_input: bool
    reviewer_note: str | None


class PriceAnalysisOut(BaseModel):
    id: str
    run_id: str
    quotation_id: str
    vendor_name: str
    currency: str | None
    subtotal: float | None
    tax_amount: float | None
    delivery_cost: float | None
    normalized_total: float | None
    normalized_unit_price: float | None
    base_currency: str
    baseline: float | None
    deviation_pct: float | None
    method: str
    baseline_source: str
    anomaly_flag: bool
    explanation: str


class PolicyEvidenceOut(_Out):
    id: str
    requirement_id: str | None
    chunk_id: str
    document_id: str
    page: int | None
    snippet: str
    score: float


# ---- assistant / reports / dashboard ---------------------------------------------------------------------
class AssistantQuery(BaseModel):
    project_id: str
    question: str = Field(min_length=3, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10)


class CitationOut(BaseModel):
    marker: int
    document_id: str
    filename: str
    page: int | None
    chunk_id: str
    snippet: str
    score: float


class AssistantAnswer(BaseModel):
    answer: str
    grounded: bool
    mode: str
    citations: list[CitationOut]


class ReportCreate(BaseModel):
    report_type: Literal["pdf", "excel"]
    run_id: str | None = None


class ReportOut(_Out):
    id: str
    project_id: str
    run_id: str | None
    report_type: str
    filename: str
    generated_by: str
    generated_at: datetime


class AuditEventOut(_Out):
    id: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    project_id: str | None
    timestamp: datetime
    event_metadata: dict[str, Any]


class HistoricalPurchaseOut(_Out):
    id: str
    item_category: str
    unit_price: float
    currency: str
    purchased_on: date | None
    supplier: str | None
