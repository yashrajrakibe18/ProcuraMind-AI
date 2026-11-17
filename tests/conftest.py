from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from procureai.samples.generate import all_samples


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated settings, database, storage and vector store per test."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("VECTOR_STORE_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("DOCUMENT_STORAGE_PATH", str(tmp_path / "docs"))
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough-123456")
    monkeypatch.setenv("WORKFLOW_STEP_TIMEOUT_SECONDS", "60")
    from procureai.application.context import reset_context
    from procureai.config.settings import get_settings
    from procureai.infrastructure.database.session import reset_database_state

    get_settings.cache_clear()
    reset_database_state()
    reset_context()
    yield tmp_path
    reset_database_state()
    reset_context()
    get_settings.cache_clear()


@pytest.fixture()
def client(env):
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def auth(client):
    def make(email="officer@example.com", name="Test Officer"):
        client.post("/api/v1/auth/register", json={"email": email, "full_name": name, "password": "Passw0rd!x"})
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "Passw0rd!x"})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return make


@pytest.fixture()
def headers(auth):
    return auth()


@pytest.fixture(scope="session")
def samples() -> dict[str, bytes]:
    return all_samples()


@pytest.fixture()
def project_with_docs(client, headers, samples):
    """Project with tender, 4 quotations, policy and history all uploaded and processed."""
    pid = client.post(
        "/api/v1/projects", json={"title": "Laptop tender", "description": "synthetic"}, headers=headers
    ).json()["id"]
    for name, blob in samples.items():
        r = client.post(
            f"/api/v1/projects/{pid}/documents",
            headers=headers,
            files={"file": (name, blob)},
            data={"document_type": "auto"},
        )
        assert r.status_code == 201, r.text
    return pid
