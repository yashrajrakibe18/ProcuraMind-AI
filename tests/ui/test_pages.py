"""Smoke-run every Streamlit page against the real API (in-process). Verifies no exceptions in empty and populated states."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

WEB = Path(__file__).resolve().parents[2] / "apps" / "web"
PAGES = sorted(p.name for p in (WEB / "pages").glob("*.py"))


@pytest.fixture()
def web(client, monkeypatch):
    monkeypatch.syspath_prepend(str(WEB))
    for mod in [m for m in sys.modules if m.split(".")[0] in ("services", "state", "components")]:
        del sys.modules[mod]
    from services.api_client import ApiClient

    def make(email="ui@example.com"):
        api = ApiClient(base_url="/api/v1", session=client)
        client.post("/api/v1/auth/register", json={"email": email, "full_name": "UI Tester", "password": "Passw0rd!x"})
        user = api.login(email, "Passw0rd!x")
        return api, user

    return make


def _run(page: str, api, user, project_id=None) -> AppTest:
    at = AppTest.from_file(str(WEB / "pages" / page), default_timeout=60)
    at.session_state["api"], at.session_state["user"] = api, user
    if project_id:
        at.session_state["project_id"] = project_id
    return at.run()


def test_login_page_renders(web):
    at = AppTest.from_file(str(WEB / "app.py"), default_timeout=30).run()
    assert not at.exception and "ProcureAI" in at.title[0].value


@pytest.mark.parametrize("page", PAGES)
def test_pages_require_login(web, page):
    at = AppTest.from_file(str(WEB / "pages" / page), default_timeout=30).run()
    assert not at.exception
    assert any("sign in" in i.value.lower() for i in at.info)


@pytest.mark.parametrize("page", PAGES)
def test_pages_empty_state(web, page):
    api, user = web()
    at = _run(page, api, user)
    assert not at.exception, [e.value for e in at.exception]


def test_pages_populated(web, client, project_with_docs, headers):
    # project_with_docs belongs to officer@example.com (the fixture's user); log in as the same user
    from services.api_client import ApiClient

    api = ApiClient(base_url="/api/v1", session=client)
    user = api.login("officer@example.com", "Passw0rd!x")
    pid = project_with_docs
    client.post(f"/api/v1/projects/{pid}/requirements/extract", headers=headers)
    client.post(f"/api/v1/projects/{pid}/analysis-runs", headers=headers, json={"auto_confirm": True})
    run = client.get(f"/api/v1/projects/{pid}/analysis-runs", headers=headers).json()[0]
    assert run["status"] == "awaiting_human_review"
    client.post(f"/api/v1/projects/{pid}/reports", headers=headers, json={"report_type": "pdf"})
    for page in PAGES:
        at = _run(page, api, user, pid)
        assert not at.exception, (page, [e.value for e in at.exception])
    # the compliance page shows real statuses as text
    at = _run("05_compliance.py", api, user, pid)
    body = " ".join(m.value for m in at.markdown)
    assert "Awaiting human review" in body
    assert any("Meets Requirement" in str(df.value) for df in at.dataframe)
    # assistant page: ask a question through the UI
    at = _run("07_ai_assistant.py", api, user, pid)
    at.chat_input[0].set_value("What warranty is required for IT hardware?").run()
    assert not at.exception and any("page" in e.label for e in at.expander)


def test_navigation_has_no_self_reference():
    """app.py must never register itself as a page (caused recursive rendering)."""
    sys.path.insert(0, str(WEB))
    from components.ui import NAV

    assert all(path.startswith("pages/") for path, _ in NAV)
    assert all((WEB / path).exists() for path, _ in NAV)
    assert [t for _, t in NAV][0] == "Overview" and len(NAV) == 9
