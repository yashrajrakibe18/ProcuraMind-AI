"""Typed application error hierarchy. Messages must be safe to show to clients."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"


class ProcessingError(AppError):
    status_code = 422
    code = "processing_error"


class WorkflowError(AppError):
    status_code = 500
    code = "workflow_error"
