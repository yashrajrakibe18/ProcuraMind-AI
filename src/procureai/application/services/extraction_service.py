"""Use cases for extracting, reviewing and confirming tender requirements and vendor quotations."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from procureai.application.dto.schemas import (
    ExtractionReport,
    QuotationUpdate,
    RequirementIn,
    RequirementUpdate,
)
from procureai.application.services.access import get_project_for_user
from procureai.application.services.audit import record_audit
from procureai.document_processing.extraction.quotation import extract_quotation
from procureai.document_processing.extraction.requirements import extract_requirements
from procureai.document_processing.extraction.tender_meta import extract_tender_metadata
from procureai.domain.requirements.fields import normalize_field
from procureai.domain.requirements.units import parse_quantity
from procureai.infrastructure.database.models import (
    Document,
    DocumentPage,
    TenderRequirement,
    User,
    Vendor,
    VendorQuotation,
    VendorSpecification,
)
from procureai.shared.enums import DocumentType, ProcessingStatus
from procureai.shared.errors import NotFoundError, ValidationAppError


def _pages(session: Session, document_id: str) -> list[tuple[int, str]]:
    rows = session.scalars(
        select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.page_number)
    )
    return [(r.page_number, r.text) for r in rows]


def _docs(session: Session, project_id: str, dtype: DocumentType) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .where(
                Document.project_id == project_id,
                Document.document_type == dtype.value,
                Document.processing_status == ProcessingStatus.PROCESSED.value,
            )
            .order_by(Document.created_at)
        )
    )


# ---- requirements -----------------------------------------------------------------------------------------
def extract_project_requirements(session: Session, project_id: str, actor_id: str | None) -> ExtractionReport:
    """Idempotent: re-extraction replaces unconfirmed rows from a document and keeps confirmed ones."""
    docs = _docs(session, project_id, DocumentType.TENDER)
    if not docs:
        raise ValidationAppError("Upload a tender document and wait for processing to finish before extracting.")
    from procureai.infrastructure.database.models import ProcurementProject

    project = session.get(ProcurementProject, project_id)
    report = ExtractionReport(created=0)
    for doc in docs:
        pages = _pages(session, doc.id)
        meta = extract_tender_metadata(pages)
        if project and project.tender_quantity is None and meta.quantity:
            project.tender_quantity = meta.quantity
        if project and not project.item_description and meta.item_description:
            project.item_description = meta.item_description
        confirmed = list(
            session.scalars(
                select(TenderRequirement).where(
                    TenderRequirement.source_document_id == doc.id, TenderRequirement.confirmed.is_(True)
                )
            )
        )
        report.kept_confirmed += len(confirmed)
        session.execute(
            delete(TenderRequirement).where(
                TenderRequirement.source_document_id == doc.id, TenderRequirement.confirmed.is_(False)
            )
        )
        existing = {(r.field, r.operator, r.required_value) for r in confirmed}
        found = extract_requirements(pages)
        if not found:
            report.warnings.append(
                f"No requirements were recognised in '{doc.original_filename}'. You can add them manually."
            )
        for r in found:
            if (r.field, r.operator.value, r.value) in existing:
                continue
            session.add(
                TenderRequirement(
                    project_id=project_id,
                    field=r.field,
                    label=r.label,
                    operator=r.operator.value,
                    required_value=r.value,
                    required_value_max=r.value_max,
                    unit=r.unit,
                    criticality=r.criticality.value,
                    source_document_id=doc.id,
                    source_page=r.page,
                    source_text=r.source_text,
                )
            )
            report.created += 1
    record_audit(
        session,
        actor_id=actor_id,
        action="requirements.extracted",
        resource_type="project",
        resource_id=project_id,
        project_id=project_id,
        metadata={"created": report.created},
    )
    session.commit()
    return report


def list_requirements(session: Session, user: User, project_id: str) -> list[TenderRequirement]:
    get_project_for_user(session, user, project_id)
    return list(
        session.scalars(
            select(TenderRequirement)
            .where(TenderRequirement.project_id == project_id)
            .order_by(TenderRequirement.created_at, TenderRequirement.id)
        )
    )


def add_requirement(session: Session, user: User, project_id: str, data: RequirementIn) -> TenderRequirement:
    get_project_for_user(session, user, project_id, write=True)
    _validate_requirement_values(data.operator, data.required_value, data.required_value_max)
    req = TenderRequirement(
        project_id=project_id,
        field=normalize_field(data.label),
        label=data.label.strip(),
        operator=data.operator,
        required_value=data.required_value.strip(),
        required_value_max=data.required_value_max,
        unit=data.unit,
        criticality=data.criticality,
        source_text="Added manually",
        confirmed=True,
    )
    session.add(req)
    session.flush()
    record_audit(
        session,
        actor_id=user.id,
        action="requirement.created",
        resource_type="requirement",
        resource_id=req.id,
        project_id=project_id,
    )
    session.commit()
    return req


def _validate_requirement_values(operator: str, value: str, value_max: str | None) -> None:
    if operator == "between" and not value_max:
        raise ValidationAppError("A 'between' requirement needs both required_value and required_value_max.")
    if operator in (">=", "<=", ">", "<", "between"):
        for v in (value, value_max):
            if v is not None and parse_quantity(v) is None:
                raise ValidationAppError(f"'{v}' is not a number; numeric operators need numeric values.")


def get_requirement(session: Session, user: User, requirement_id: str, write: bool = False) -> TenderRequirement:
    req = session.get(TenderRequirement, requirement_id)
    if req is None:
        raise NotFoundError("Requirement not found.")
    get_project_for_user(session, user, req.project_id, write=write)
    return req


def update_requirement(session: Session, user: User, requirement_id: str, data: RequirementUpdate) -> TenderRequirement:
    req = get_requirement(session, user, requirement_id, write=True)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(req, key, value)
    if "label" in changes:
        req.field = normalize_field(req.label)
    _validate_requirement_values(req.operator, req.required_value, req.required_value_max)
    record_audit(
        session,
        actor_id=user.id,
        action="requirement.updated",
        resource_type="requirement",
        resource_id=req.id,
        project_id=req.project_id,
        metadata={"fields": sorted(changes)},
    )
    session.commit()
    return req


def delete_requirement(session: Session, user: User, requirement_id: str) -> None:
    req = get_requirement(session, user, requirement_id, write=True)
    record_audit(
        session,
        actor_id=user.id,
        action="requirement.deleted",
        resource_type="requirement",
        resource_id=req.id,
        project_id=req.project_id,
    )
    session.delete(req)
    session.commit()


def confirm_all_requirements(session: Session, project_id: str, actor_id: str | None) -> int:
    rows = list(
        session.scalars(
            select(TenderRequirement).where(
                TenderRequirement.project_id == project_id, TenderRequirement.confirmed.is_(False)
            )
        )
    )
    for r in rows:
        r.confirmed = True
    if rows:
        record_audit(
            session,
            actor_id=actor_id,
            action="requirements.confirmed_bulk",
            resource_type="project",
            resource_id=project_id,
            project_id=project_id,
            metadata={"count": len(rows)},
        )
    session.commit()
    return len(rows)


# ---- vendors ----------------------------------------------------------------------------------------------
def extract_project_vendors(session: Session, project_id: str, actor_id: str | None) -> ExtractionReport:
    """Create vendor/quotation/spec records from processed quotation documents (idempotent per document)."""
    docs = _docs(session, project_id, DocumentType.QUOTATION)
    if not docs:
        raise ValidationAppError("Upload at least one quotation document and wait for processing to finish.")
    report = ExtractionReport(created=0)
    for doc in docs:
        if session.scalar(select(Vendor.id).where(Vendor.document_id == doc.id)):
            report.skipped.append(doc.original_filename)
            continue
        quote = extract_quotation(_pages(session, doc.id), doc.original_filename)
        if quote is None:
            report.warnings.append(f"No quotation data was recognised in '{doc.original_filename}'.")
            continue
        vendor = Vendor(
            project_id=project_id,
            vendor_name=quote.vendor_name[:255],
            contact=quote.contact,
            reference=quote.reference,
            document_id=doc.id,
        )
        session.add(vendor)
        session.flush()
        notes = list(quote.notes)
        q = VendorQuotation(
            vendor_id=vendor.id,
            document_id=doc.id,
            unit_price=quote.unit_price,
            quantity=quote.quantity,
            currency=quote.currency,
            tax_percent=quote.tax_percent,
            delivery_cost=quote.delivery_cost,
            delivery_days=quote.delivery_days,
            warranty_months=quote.warranty_months,
            item_category=quote.category,
            source_page=quote.source_page,
            extraction_notes=notes,
        )
        session.add(q)
        session.flush()
        session.add_all(
            VendorSpecification(
                quotation_id=q.id,
                field=s.field,
                label=s.label[:255],
                value_text=s.value_text[:255],
                value_numeric=s.value_numeric,
                unit=s.unit,
                source_page=s.page,
                source_text=s.source_text,
                confidence=s.confidence,
            )
            for s in quote.specs
        )
        report.created += 1
        report.warnings.extend(f"{vendor.vendor_name}: {n}" for n in notes)
    record_audit(
        session,
        actor_id=actor_id,
        action="vendors.extracted",
        resource_type="project",
        resource_id=project_id,
        project_id=project_id,
        metadata={"created": report.created},
    )
    session.commit()
    return report


def list_vendors(session: Session, user: User, project_id: str) -> list[Vendor]:
    get_project_for_user(session, user, project_id)
    return list(session.scalars(select(Vendor).where(Vendor.project_id == project_id).order_by(Vendor.created_at)))


def _quotation_for_user(session: Session, user: User, quotation_id: str, write: bool) -> VendorQuotation:
    q = session.get(VendorQuotation, quotation_id)
    if q is None:
        raise NotFoundError("Quotation not found.")
    get_project_for_user(session, user, q.vendor.project_id, write=write)
    return q


def update_quotation(session: Session, user: User, quotation_id: str, data: QuotationUpdate) -> VendorQuotation:
    q = _quotation_for_user(session, user, quotation_id, True)
    changes = data.model_dump(exclude_unset=True)
    if "currency" in changes and changes["currency"]:
        changes["currency"] = changes["currency"].upper()
    for k, v in changes.items():
        setattr(q, k, v)
    record_audit(
        session,
        actor_id=user.id,
        action="quotation.updated",
        resource_type="quotation",
        resource_id=q.id,
        project_id=q.vendor.project_id,
        metadata={"fields": sorted(changes)},
    )
    session.commit()
    return q


def update_vendor_name(session: Session, user: User, vendor_id: str, name: str) -> Vendor:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise NotFoundError("Vendor not found.")
    get_project_for_user(session, user, vendor.project_id, write=True)
    vendor.vendor_name = name.strip()
    record_audit(
        session,
        actor_id=user.id,
        action="vendor.renamed",
        resource_type="vendor",
        resource_id=vendor.id,
        project_id=vendor.project_id,
    )
    session.commit()
    return vendor


def update_specification(session: Session, user: User, spec_id: str, value_text: str) -> VendorSpecification:
    spec = session.get(VendorSpecification, spec_id)
    if spec is None:
        raise NotFoundError("Specification not found.")
    q = _quotation_for_user(session, user, spec.quotation_id, True)
    qty = parse_quantity(value_text)
    spec.value_text = value_text.strip()
    spec.value_numeric, spec.unit = (qty.value, qty.unit) if qty else (None, None)
    spec.confidence = 1.0  # a person has verified this value
    record_audit(
        session,
        actor_id=user.id,
        action="specification.corrected",
        resource_type="specification",
        resource_id=spec.id,
        project_id=q.vendor.project_id,
    )
    session.commit()
    return spec


def confirm_all_quotations(session: Session, project_id: str) -> int:
    rows = list(
        session.scalars(
            select(VendorQuotation)
            .join(Vendor)
            .where(Vendor.project_id == project_id, VendorQuotation.confirmed.is_(False))
        )
    )
    for q in rows:
        q.confirmed = True
    session.commit()
    return len(rows)
