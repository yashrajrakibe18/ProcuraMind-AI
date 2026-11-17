"""SQLAlchemy ORM models (authoritative relational data). Never exposed directly by the API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from procureai.shared.types import new_id, utcnow


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[str]:
    return mapped_column(String(32), primary_key=True, default=new_id)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="procurement_officer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProcurementProject(Base):
    __tablename__ = "projects"
    id: Mapped[str] = _pk()
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    item_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tender_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(32), default="general")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(128))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    document_type: Mapped[str] = mapped_column(String(32), default="other")
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    auto_classify: Mapped[bool] = mapped_column(Boolean, default=False)
    checksum: Mapped[str] = mapped_column(String(64))
    processing_status: Mapped[str] = mapped_column(String(16), default="pending")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    pages: Mapped[list[DocumentPage]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    __table_args__ = (Index("ix_documents_project_checksum", "project_id", "checksum"),)


class DocumentPage(Base):
    __tablename__ = "document_pages"
    id: Mapped[str] = _pk()
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)


class TenderRequirement(Base):
    __tablename__ = "tender_requirements"
    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(128))
    label: Mapped[str] = mapped_column(String(255))
    operator: Mapped[str] = mapped_column(String(16))
    required_value: Mapped[str] = mapped_column(String(255))
    required_value_max: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    criticality: Mapped[str] = mapped_column(String(16), default="mandatory")
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, default="")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    vendor_name: Mapped[str] = mapped_column(String(255))
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    quotations: Mapped[list[VendorQuotation]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan", passive_deletes=True
    )


class VendorQuotation(Base):
    __tablename__ = "vendor_quotations"
    id: Mapped[str] = _pk()
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    tax_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    warranty_months: Mapped[float | None] = mapped_column(Float, nullable=True)
    item_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    vendor: Mapped[Vendor] = relationship(back_populates="quotations")
    specifications: Mapped[list[VendorSpecification]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class VendorSpecification(Base):
    __tablename__ = "vendor_specifications"
    id: Mapped[str] = _pk()
    quotation_id: Mapped[str] = mapped_column(ForeignKey("vendor_quotations.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(128))
    label: Mapped[str] = mapped_column(String(255))
    value_text: Mapped[str] = mapped_column(String(255))
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.9)


class HistoricalPurchase(Base):
    __tablename__ = "historical_purchases"
    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    item_category: Mapped[str] = mapped_column(String(128))
    unit_price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    purchased_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    supplier: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    workflow_version: Mapped[str] = mapped_column(String(16), default="1.0")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_info: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    steps: Mapped[list[AgentStep]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="AgentStep.sequence"
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"
    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceResult(Base):
    __tablename__ = "compliance_results"
    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("tender_requirements.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(32), default="deterministic")
    explanation: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_unconfirmed_input: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PriceAnalysis(Base):
    __tablename__ = "price_analyses"
    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    quotation_id: Mapped[str] = mapped_column(ForeignKey("vendor_quotations.id", ondelete="CASCADE"), index=True)
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    deviation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(String(48), default="")
    baseline_source: Mapped[str] = mapped_column(String(16), default="peer")
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text, default="")


class PolicyEvidence(Base):
    __tablename__ = "policy_evidence"
    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_id: Mapped[str] = mapped_column(String(64))
    document_id: Mapped[str] = mapped_column(String(32))
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float, default=0.0)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = _pk()
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    report_type: Mapped[str] = mapped_column(String(16))
    storage_key: Mapped[str] = mapped_column(String(128))
    filename: Mapped[str] = mapped_column(String(255))
    generated_by: Mapped[str] = mapped_column(String(32))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = _pk()
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(48))
    resource_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ReviewItem(Base):
    """A unit of human-review work raised by a run (compliance, price, extraction or verification)."""

    __tablename__ = "review_items"
    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    ref_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
