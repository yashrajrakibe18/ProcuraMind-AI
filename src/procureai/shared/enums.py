from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    OFFICER = "procurement_officer"
    REVIEWER = "reviewer"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    ANALYZED = "analyzed"
    ARCHIVED = "archived"


class DocumentType(StrEnum):
    TENDER = "tender"
    QUOTATION = "quotation"
    POLICY = "policy"
    HISTORICAL = "historical"
    CONTRACT = "contract"
    FINANCIAL = "financial"
    DATASET = "dataset"
    RESUME = "resume"
    JOB_DESCRIPTION = "job_description"
    TICKETS = "tickets"
    MEETING_NOTES = "meeting_notes"
    KNOWLEDGE_BASE = "knowledge_base"
    OTHER = "other"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class Operator(StrEnum):
    GTE = ">="
    LTE = "<="
    GT = ">"
    LT = "<"
    EQ = "=="
    BETWEEN = "between"
    CONTAINS = "contains"


class Criticality(StrEnum):
    MANDATORY = "mandatory"
    DESIRABLE = "desirable"


class ComplianceStatus(StrEnum):
    MEETS = "Meets Requirement"
    FAILS = "Does Not Meet Requirement"
    MISSING = "Missing Information"
    REVIEW = "Requires Human Review"
    NOT_APPLICABLE = "Not Applicable"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_human_review"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReportType(StrEnum):
    PDF = "pdf"
    EXCEL = "excel"
