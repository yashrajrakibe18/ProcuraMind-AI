from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from procureai.application.dto.schemas import (
    ExtractionReport,
    QuotationOut,
    QuotationUpdate,
    SpecOut,
    SpecUpdate,
    VendorOut,
    VendorUpdate,
)
from procureai.application.services import extraction_service
from procureai.application.services.access import get_project_for_user

router = APIRouter(tags=["vendors"])


@router.get(
    "/projects/{project_id}/vendors",
    response_model=list[VendorOut],
    summary="List vendors with quotations and extracted specifications",
)
def list_vendors(project_id: str, db: DB, user: CurrentUser):
    return extraction_service.list_vendors(db, user, project_id)


@router.post("/projects/{project_id}/vendors/extract", response_model=ExtractionReport)
def extract_vendors(project_id: str, db: DB, user: CurrentUser):
    get_project_for_user(db, user, project_id, write=True)
    return extraction_service.extract_project_vendors(db, project_id, user.id)


@router.patch("/vendors/{vendor_id}", response_model=VendorOut)
def rename_vendor(vendor_id: str, data: VendorUpdate, db: DB, user: CurrentUser):
    return extraction_service.update_vendor_name(db, user, vendor_id, data.vendor_name)


@router.patch("/quotations/{quotation_id}", response_model=QuotationOut)
def update_quotation(quotation_id: str, data: QuotationUpdate, db: DB, user: CurrentUser):
    return extraction_service.update_quotation(db, user, quotation_id, data)


@router.patch("/specifications/{spec_id}", response_model=SpecOut)
def update_spec(spec_id: str, data: SpecUpdate, db: DB, user: CurrentUser):
    return extraction_service.update_specification(db, user, spec_id, data.value_text)
