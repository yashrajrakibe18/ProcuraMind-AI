"""HTTP client for the ProcureAI API. The UI talks to the backend ONLY through this module."""

from __future__ import annotations

import os
from typing import Any

import requests


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, message: str, request_id: str | None = None, details: Any = None
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.request_id, self.details = status, code, message, request_id, details

    def __str__(self) -> str:
        suffix = f" (ref {self.request_id})" if self.request_id else ""
        return f"{self.message}{suffix}"


class ApiClient:
    def __init__(
        self, base_url: str | None = None, token: str | None = None, session: Any = None, timeout: float = 60.0
    ) -> None:
        self.base_url = (base_url or os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")).rstrip("/")
        self.token, self.timeout = token, timeout
        self._http = session or requests.Session()

    # -- plumbing ------------------------------------------------------------------------------------------
    def _request(self, method: str, path: str, *, raw: bool = False, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        try:
            resp = (
                self._http.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
                if isinstance(self._http, requests.Session)
                else self._http.request(method, url, headers=headers, **kwargs)
            )
        except requests.RequestException as exc:
            raise ApiError(
                0, "unreachable", "The ProcureAI service is not reachable. Check that the API is running."
            ) from exc
        if resp.status_code >= 400:
            try:
                body = resp.json()
                raise ApiError(
                    resp.status_code,
                    body.get("code", "error"),
                    body.get("message", "Request failed."),
                    body.get("request_id"),
                    body.get("details"),
                )
            except ValueError:
                raise ApiError(resp.status_code, "error", "Request failed.") from None
        if raw:
            return resp.content
        return None if resp.status_code == 204 or not resp.content else resp.json()

    def get(self, path: str, **kw: Any) -> Any:
        return self._request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self._request("POST", path, **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self._request("PATCH", path, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self._request("DELETE", path, **kw)

    # -- auth ----------------------------------------------------------------------------------------------
    def login(self, email: str, password: str) -> dict:
        data = self.post("/auth/login", json={"email": email, "password": password})
        self.token = data["access_token"]
        return data["user"]

    def register(self, email: str, full_name: str, password: str) -> dict:
        return self.post("/auth/register", json={"email": email, "full_name": full_name, "password": password})

    # -- resources -----------------------------------------------------------------------------------------
    def overview(self) -> dict:
        return self.get("/dashboard/overview")

    def projects(self, include_archived: bool = False) -> list[dict]:
        return self.get("/projects", params={"include_archived": include_archived})

    def create_project(self, title: str, description: str) -> dict:
        return self.post("/projects", json={"title": title, "description": description})

    def archive_project(self, project_id: str) -> None:
        self.delete(f"/projects/{project_id}")

    def project(self, project_id: str) -> dict:
        return self.get(f"/projects/{project_id}")

    def documents(self, project_id: str) -> list[dict]:
        return self.get(f"/projects/{project_id}/documents")

    def upload(self, project_id: str, filename: str, data: bytes, document_type: str) -> dict:
        return self.post(
            f"/projects/{project_id}/documents", files={"file": (filename, data)}, data={"document_type": document_type}
        )

    def delete_document(self, document_id: str) -> None:
        self.delete(f"/documents/{document_id}")

    def pages(self, document_id: str) -> list[dict]:
        return self.get(f"/documents/{document_id}/pages")

    def extract_requirements(self, project_id: str) -> dict:
        return self.post(f"/projects/{project_id}/requirements/extract")

    def requirements(self, project_id: str) -> list[dict]:
        return self.get(f"/projects/{project_id}/requirements")

    def update_requirement(self, requirement_id: str, **fields: Any) -> dict:
        return self.patch(f"/requirements/{requirement_id}", json=fields)

    def add_requirement(self, project_id: str, **fields: Any) -> dict:
        return self.post(f"/projects/{project_id}/requirements", json=fields)

    def delete_requirement(self, requirement_id: str) -> None:
        self.delete(f"/requirements/{requirement_id}")

    def confirm_requirements(self, project_id: str) -> dict:
        return self.post(f"/projects/{project_id}/requirements/confirm-all")

    def vendors(self, project_id: str) -> list[dict]:
        return self.get(f"/projects/{project_id}/vendors")

    def extract_vendors(self, project_id: str) -> dict:
        return self.post(f"/projects/{project_id}/vendors/extract")

    def update_spec(self, spec_id: str, value_text: str) -> dict:
        return self.patch(f"/specifications/{spec_id}", json={"value_text": value_text})

    def update_quotation(self, quotation_id: str, **fields: Any) -> dict:
        return self.patch(f"/quotations/{quotation_id}", json=fields)

    def start_run(self, project_id: str, auto_confirm: bool) -> dict:
        return self.post(f"/projects/{project_id}/analysis-runs", json={"auto_confirm": auto_confirm})

    def runs(self, project_id: str) -> list[dict]:
        return self.get(f"/projects/{project_id}/analysis-runs")

    def run(self, run_id: str) -> dict:
        return self.get(f"/analysis-runs/{run_id}")

    def review_items(self, run_id: str) -> list[dict]:
        return self.get(f"/analysis-runs/{run_id}/review-items")

    def resolve_review(self, item_id: str, note: str, decision: str) -> dict:
        return self.post(f"/review-items/{item_id}/resolve", json={"note": note, "decision": decision})

    def approve_run(self, run_id: str) -> dict:
        return self.post(f"/analysis-runs/{run_id}/approve")

    def compliance(self, project_id: str, run_id: str | None = None) -> list[dict]:
        return self.get(f"/projects/{project_id}/compliance", params={"run_id": run_id} if run_id else None)

    def price_analysis(self, project_id: str, run_id: str | None = None) -> list[dict]:
        return self.get(f"/projects/{project_id}/price-analysis", params={"run_id": run_id} if run_id else None)

    def policy_evidence(self, project_id: str) -> list[dict]:
        return self.get(f"/projects/{project_id}/policy-evidence")

    def historical(self, project_id: str) -> list[dict]:
        return self.get(f"/projects/{project_id}/historical-purchases")

    def ask(self, project_id: str, question: str) -> dict:
        return self.post("/assistant/query", json={"project_id": project_id, "question": question})

    def create_report(self, project_id: str, report_type: str, run_id: str | None = None) -> dict:
        return self.post(f"/projects/{project_id}/reports", json={"report_type": report_type, "run_id": run_id})

    def reports(self, project_id: str) -> list[dict]:
        return self.get(f"/projects/{project_id}/reports")

    def download_report(self, report_id: str) -> bytes:
        return self.get(f"/reports/{report_id}/download", raw=True)

    def ready(self) -> dict:
        root = self.base_url.rsplit("/api/", 1)[0]
        return self._request("GET", f"{root}/ready")
