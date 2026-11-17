"""Platform tests: organizations, plans, agents, orchestrator, workflows, approvals, webhooks, search."""

from __future__ import annotations

import io

import pytest

API = "/api/v1"
CONTRACT = """MASTER SERVICES AGREEMENT
This Agreement is made between Acme Corp and Globex Ltd (the parties). The Effective Date is 1 January 2026.
Term. This agreement expires on {expiry} and will automatically renew for successive one year terms unless terminated.
Payment. The client shall pay each invoice within 30 days of receipt. Late payment incurs a penalty of 2% per month.
Termination. Either party may terminate this agreement at any time at its sole discretion with 90 days notice.
Confidentiality. Each party shall keep all confidential information secret.
Governing law. This agreement is governed by the laws of England; courts of London have jurisdiction.
Liability. The supplier accepts unlimited liability for damages arising under this agreement.
""".strip()
DATASET = "date,category,amount,region\n" + "\n".join(f"2026-0{m}-15,{c},{a},{r}" for m, c, a, r in [(1, "Hardware", 1000, "N"), (2, "Hardware", 1100, "S"), (3, "Software", 900, "N"), (4, "Hardware", 1200, "S"), (5, "Software", 950, "N"), (6, "Hardware", 1300, "S"), (7, "Software", 990, "N"), (8, "Hardware", 1250, "S"), (9, "Software", 940, "N")]) + "\n2026-09-20,Hardware,25000,N\n"
BUDGET = "category,budget,actual\nHardware,10000,13000\nSoftware,5000,4800\nTraining,2000,2100\n"


def upload(client, headers, pid, name, content, dtype="auto"):
    data = content if isinstance(content, bytes) else content.encode()
    r = client.post(f"{API}/projects/{pid}/documents", headers=headers, files={"file": (name, io.BytesIO(data))}, data={"document_type": dtype})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def run(client, headers, agent, pid=None, **params):
    r = client.post(f"{API}/agents/{agent}/run", headers=headers, json={"project_id": pid, "params": params})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def pid(client, headers):
    return client.post(f"{API}/projects", json={"title": "Multi"}, headers=headers).json()["id"]


# ---------------------------------------------------------------- orgs, plans, isolation
def test_registration_creates_personal_org_and_project_gets_org(client, headers, pid):
    orgs = client.get(f"{API}/orgs", headers=headers).json()
    assert len(orgs) == 1 and orgs[0]["role"] == "owner" and orgs[0]["plan"] == "free"
    assert client.get(f"{API}/projects/{pid}", headers=headers).json()["org_id"] == orgs[0]["id"]


def test_free_plan_project_limit_and_upgrade(client, headers):
    for i in range(3):
        assert client.post(f"{API}/projects", json={"title": f"P{i}"}, headers=headers).status_code == 201
    r = client.post(f"{API}/projects", json={"title": "P4"}, headers=headers)
    assert r.status_code == 402 and r.json()["code"] == "plan_limit_reached"
    org = client.get(f"{API}/orgs", headers=headers).json()[0]["id"]
    assert client.put(f"{API}/orgs/{org}/plan", headers=headers, json={"plan": "professional"}).status_code == 200
    assert client.post(f"{API}/projects", json={"title": "P4"}, headers=headers).status_code == 201
    u = client.get(f"{API}/orgs/{org}/usage", headers=headers).json()
    assert u["projects"] == {"used": 4, "limit": 25}


def test_team_membership_roles_and_isolation(client, auth):
    owner, other, outsider = auth("o@x.io", "Olivia Owner"), auth("m@x.io", "Mia Member"), auth("z@x.io", "Zed Outsider")
    org = client.get(f"{API}/orgs", headers=owner).json()[0]["id"]
    pid = client.post(f"{API}/projects", json={"title": "Shared"}, headers=owner).json()["id"]
    assert client.get(f"{API}/projects/{pid}", headers=other).status_code == 404  # not yet a member
    client.put(f"{API}/orgs/{org}/plan", headers=owner, json={"plan": "team"})
    assert client.post(f"{API}/orgs/{org}/members", headers=owner, json={"email": "m@x.io", "role": "viewer"}).status_code == 201
    assert client.get(f"{API}/projects/{pid}", headers=other).status_code == 200
    # viewers are read-only
    r = client.post(f"{API}/projects/{pid}/documents", headers=other, files={"file": ("a.txt", io.BytesIO(b"hello policy text here"))})
    assert r.status_code == 403
    assert client.get(f"{API}/projects/{pid}", headers=outsider).status_code == 404
    assert client.post(f"{API}/orgs/{org}/members", headers=other, json={"email": "z@x.io"}).status_code == 403
    assert client.patch(f"{API}/orgs/{org}/members/{[m for m in client.get(f'{API}/orgs/{org}/members', headers=owner).json() if m['email'] == 'm@x.io'][0]['user_id']}", headers=owner, json={"role": "member"}).status_code == 200
    assert client.post(f"{API}/projects/{pid}/documents", headers=other, files={"file": ("a.txt", io.BytesIO(b"hello policy text here"))}).status_code == 201


def test_member_limit_enforced_on_free_plan(client, auth):
    o = auth("o2@x.io", "Olivia")
    auth("m2@x.io", "Mia")
    org = client.get(f"{API}/orgs", headers=o).json()[0]["id"]
    assert client.post(f"{API}/orgs/{org}/members", headers=o, json={"email": "m2@x.io"}).status_code == 402


# ---------------------------------------------------------------- hybrid retrieval and RAG agent
def test_rag_agent_cites_and_refuses_out_of_domain(client, headers, project_with_docs):
    r = run(client, headers, "rag", project_with_docs, question="What warranty is required for IT hardware?")
    assert r["status"] == "completed" and r["output"]["evidence"] and r["output"]["data"]["grounded"]
    off = run(client, headers, "rag", project_with_docs, question="What is the capital of France?")
    assert off["output"]["data"]["grounded"] is False and not off["output"]["evidence"]


def test_research_agent_reports_missing_evidence(client, headers, project_with_docs):
    r = run(client, headers, "research", project_with_docs, question="warranty requirement; approval authority; moon landing schedule")
    text = str(r["output"]["sections"])
    assert "NO EVIDENCE" in text and "Evidence found" in text


# ---------------------------------------------------------------- procurement chain with human checkpoint
def test_procurement_needs_confirmation_then_runs_and_vendor_agents(client, headers, project_with_docs):
    pid = project_with_docs
    first = run(client, headers, "procurement", pid)
    assert first["status"] == "needs_input" and "confirmation" in first["needs_input"]
    done = run(client, headers, "procurement", pid, auto_confirm=True)
    assert done["status"] == "completed" and done["output"]["data"]["run_status"] == "awaiting_human_review"
    comp = run(client, headers, "compliance", pid)
    assert "need attention" in comp["summary"] and comp["output"]["sections"][1]["rows"]
    vend = run(client, headers, "vendor_intelligence", pid)
    rows = vend["output"]["sections"][0]["rows"]
    assert len(rows) == 4 and rows[0][-2] == "LOW" and rows[-1][-2] in ("MEDIUM", "HIGH")  # sorted lowest risk first
    fin = run(client, headers, "financial", pid)
    assert "Quotation cost comparison" in str(fin["output"]["sections"])
    rep = run(client, headers, "report", pid, kind="pdf")
    assert rep["status"] == "completed" and client.get(f"{API}/projects/{pid}/reports", headers=headers).json()


def test_supervisor_plans_runs_children_and_stops_on_missing_input(client, headers, project_with_docs):
    t = run(client, headers, "supervisor", project_with_docs, request="Analyze these vendor quotations")
    assert t["status"] == "needs_input"  # procurement stops at the confirmation checkpoint, rest skipped
    rows = t["output"]["sections"][0]["rows"]
    assert [r[2] for r in rows] == ["needs_input", "skipped", "skipped"]
    detail = client.get(f"{API}/tasks/{t['id']}", headers=headers).json()
    assert len(detail["children"]) == 1 and detail["children"][0]["agent"] == "procurement"


def test_supervisor_routes_report_request_only_to_report_agent(client, headers, project_with_docs):
    run(client, headers, "procurement", project_with_docs, auto_confirm=True)
    t = run(client, headers, "supervisor", project_with_docs, request="Create a procurement report")
    assert [r[0] for r in t["output"]["sections"][0]["rows"]] == ["Report Generation Agent"]


# ---------------------------------------------------------------- document, contract, data, financial
def test_document_agent_summary_dates_and_missing_sections(client, headers, pid):
    d = upload(client, headers, pid, "msa.txt", CONTRACT.format(expiry="31 December 2030"), "contract")
    r = run(client, headers, "document_intelligence", pid, document_id=d)
    assert r["status"] == "completed" and "2030-12-31" in str(r["output"]["sections"][0]["rows"])


def test_contract_agent_finds_clauses_dates_risks_and_reminders(client, headers, pid):
    from datetime import date, timedelta

    soon = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    upload(client, headers, pid, "msa.txt", CONTRACT.format(expiry=soon), "contract")
    r = run(client, headers, "contract", pid, expiring_days=60)
    sections = r["output"]["sections"]
    assert sections[0]["title"].startswith("Expiring or renewing") and sections[0]["rows"][0][3] in (29, 30, 31)
    text = str(sections)
    for expected in ("Auto-renewal", "Unlimited liability", "Unilateral termination", "Penalties", "Governing law"):
        assert expected in text
    notes = client.get(f"{API}/notifications", headers=headers).json()
    assert any("expiring" in n["title"].lower() or "expir" in n["title"].lower() or "renew" in n["title"].lower() or "in " in n["title"] for n in notes["items"])


def test_contract_agent_needs_a_contract(client, headers, pid):
    assert run(client, headers, "contract", pid)["status"] == "needs_input"


def test_data_analyst_detects_trend_outlier_and_charts(client, headers, pid):
    upload(client, headers, pid, "sales.csv", DATASET, "dataset")
    r = run(client, headers, "data_analyst", pid)
    assert r["status"] == "completed"
    secs = r["output"]["sections"]
    kinds = {s["type"] for s in secs}
    assert {"kv", "table", "chart", "bullets"} <= kinds
    assert "25000" in str(secs)  # the injected outlier is reported as an anomaly


def test_financial_agent_budget_variance(client, headers, pid):
    upload(client, headers, pid, "budget.csv", BUDGET, "financial")
    r = run(client, headers, "financial", pid)
    rows = r["output"]["sections"][0]["rows"]
    hw = next(x for x in rows if x[0] == "Hardware")
    assert hw[3] == 3000 and hw[4] == 30.0 and hw[5] == "OVER budget"
    assert "Hardware: 30.0%" in str(r["output"]["sections"])


def test_docx_and_xlsx_are_ingested(client, headers, pid):
    import docx
    import openpyxl

    buf = io.BytesIO()
    d = docx.Document()
    d.add_paragraph("Company travel policy: employees shall obtain approval before booking international travel.")
    d.save(buf)
    upload(client, headers, pid, "travel.docx", buf.getvalue(), "policy")
    wb, b2 = openpyxl.Workbook(), io.BytesIO()
    wb.active.append(["category", "budget", "actual"])
    wb.active.append(["Ops", 100, 150])
    wb.save(b2)
    upload(client, headers, pid, "ops.xlsx", b2.getvalue(), "financial")
    r = run(client, headers, "rag", pid, question="international travel approval")
    assert r["output"]["evidence"] and r["output"]["evidence"][0]["document"] == "travel.docx"
    assert run(client, headers, "financial", pid)["output"]["sections"][0]["rows"][0][5] == "OVER budget"


# ---------------------------------------------------------------- approvals, cancel, retry
def test_communication_agent_requires_approval_and_never_sends(client, headers, project_with_docs):
    run(client, headers, "procurement", project_with_docs, auto_confirm=True)
    t = run(client, headers, "communication", project_with_docs, kind="vendor_followup")
    assert t["status"] == "awaiting_approval" and "Nothing is sent" in t["summary"]
    assert any(s["type"] == "draft" for s in t["output"]["sections"])
    d = client.post(f"{API}/tasks/{t['id']}/decision", headers=headers, json={"approve": True, "note": "ok"}).json()
    assert d["status"] == "completed"
    assert client.post(f"{API}/tasks/{t['id']}/decision", headers=headers, json={"approve": True}).status_code == 422


def test_cancel_and_retry(client, headers, pid):
    t = run(client, headers, "data_analyst", pid)  # no dataset -> needs_input
    assert t["status"] == "needs_input"
    assert client.post(f"{API}/tasks/{t['id']}/cancel", headers=headers).json()["status"] == "cancelled"
    upload(client, headers, pid, "sales.csv", DATASET, "dataset")
    again = client.post(f"{API}/tasks/{t['id']}/retry", headers=headers).json()
    assert again["status"] == "completed"


def test_agent_tool_permissions_are_enforced(env):
    from procureai.agents.suite.base import AgentContext
    from procureai.agents.suite.registry import AGENTS
    from procureai.shared.errors import PermissionDeniedError

    ctx = AgentContext(None, None, None, None, {}, AGENTS["rag"])
    with pytest.raises(PermissionDeniedError):
        ctx.tool("make_report")  # rag agent never declared this tool
    ctx2 = AgentContext(None, None, None, None, {}, AGENTS["vendor_intelligence"])
    with pytest.raises(PermissionDeniedError):
        ctx2.tool("notify")
    assert all("external_send" not in a.permissions for a in AGENTS.values())


def test_project_access_enforced_for_agents(client, auth, pid, headers):
    other = auth("other@x.io", "Other")
    r = client.post(f"{API}/agents/rag/run", headers=other, json={"project_id": pid, "params": {"question": "x"}})
    assert r.status_code == 404


# ---------------------------------------------------------------- workflows
def test_workflow_with_approval_checkpoint_pause_resume(client, headers, pid):
    upload(client, headers, pid, "sales.csv", DATASET, "dataset")
    steps = [{"agent": "data_analyst", "params": {}}, {"type": "approval", "title": "Manager sign-off"}, {"agent": "report", "params": {"kind": "summary"}}]
    wf = client.post(f"{API}/workflows", headers=headers, json={"name": "Data review", "steps": steps, "project_id": pid})
    assert wf.status_code == 201, wf.text
    r = client.post(f"{API}/workflows/{wf.json()['id']}/run", headers=headers, json={}).json()
    assert r["status"] == "awaiting_approval" and r["cursor"] == 2
    pending = [t for t in client.get(f"{API}/tasks?project_id={pid}&status=awaiting_approval", headers=headers).json() if t["agent"] == "approval"]
    assert len(pending) == 1
    client.post(f"{API}/tasks/{pending[0]['id']}/decision", headers=headers, json={"approve": True, "note": "go"})
    runs = client.get(f"{API}/workflows/{wf.json()['id']}/runs", headers=headers).json()
    assert runs[0]["status"] == "completed"


def test_workflow_reject_cancels_and_failure_is_recorded(client, headers, pid):
    wf = client.post(f"{API}/workflows", headers=headers, json={"name": "Needs data", "steps": [{"agent": "data_analyst"}], "project_id": pid}).json()
    r = client.post(f"{API}/workflows/{wf['id']}/run", headers=headers, json={}).json()
    assert r["status"] == "failed" and "needs input" in r["error"]  # failures are never silent
    wf2 = client.post(f"{API}/workflows", headers=headers, json={"name": "Gate", "steps": [{"type": "approval", "title": "ok?"}], "project_id": pid}).json()
    r2 = client.post(f"{API}/workflows/{wf2['id']}/run", headers=headers, json={}).json()
    task = [t for t in client.get(f"{API}/tasks?status=awaiting_approval", headers=headers).json()][0]
    client.post(f"{API}/tasks/{task['id']}/decision", headers=headers, json={"approve": False, "note": "no"})
    assert client.get(f"{API}/workflows/{wf2['id']}/runs", headers=headers).json()[0]["status"] == "cancelled"
    assert r2["status"] == "awaiting_approval"


def test_workflow_validation_and_schedule_gating(client, headers, pid):
    assert client.post(f"{API}/workflows", headers=headers, json={"name": "bad", "steps": [{"agent": "nope"}], "project_id": pid}).status_code == 422
    assert client.post(f"{API}/workflows", headers=headers, json={"name": "recursive", "steps": [{"agent": "supervisor"}], "project_id": pid}).status_code == 422
    r = client.post(f"{API}/workflows", headers=headers, json={"name": "sched", "steps": [{"agent": "rag", "params": {"question": "warranty"}}], "project_id": pid, "schedule_minutes": 60})
    assert r.status_code == 402  # schedules need a paid plan


def test_scheduler_runs_due_workflows(client, headers, pid, env):
    from datetime import timedelta

    from procureai.agents.suite.orchestrator import run_due_workflows
    from procureai.application.context import get_context
    from procureai.infrastructure.database.models import Workflow
    from procureai.infrastructure.database.session import get_session_factory
    from procureai.shared.types import utcnow

    org = client.get(f"{API}/orgs", headers=headers).json()[0]["id"]
    client.put(f"{API}/orgs/{org}/plan", headers=headers, json={"plan": "professional"})
    upload(client, headers, pid, "sales.csv", DATASET, "dataset")
    wf = client.post(f"{API}/workflows", headers=headers, json={"name": "Nightly", "steps": [{"agent": "data_analyst"}], "project_id": pid, "schedule_minutes": 60}).json()
    with get_session_factory()() as s:
        s.get(Workflow, wf["id"]).next_run_at = utcnow() - timedelta(minutes=1)
        s.commit()
    assert run_due_workflows(get_context()) == 1
    runs = client.get(f"{API}/workflows/{wf['id']}/runs", headers=headers).json()
    assert runs[0]["trigger"] == "schedule" and runs[0]["status"] == "completed"
    assert run_due_workflows(get_context()) == 0  # next run moved forward


# ---------------------------------------------------------------- webhooks
def test_webhook_signing_and_ssrf_guard(client, headers, env):
    import hashlib
    import hmac
    import json

    from procureai.infrastructure.database.session import get_session_factory
    from procureai.saas import webhooks

    org = client.get(f"{API}/orgs", headers=headers).json()[0]["id"]
    assert client.post(f"{API}/orgs/{org}/webhooks", headers=headers, json={"url": "https://example.com/h", "events": []}).status_code == 402  # free plan: 0 webhooks
    client.put(f"{API}/orgs/{org}/plan", headers=headers, json={"plan": "professional"})
    assert client.post(f"{API}/orgs/{org}/webhooks", headers=headers, json={"url": "http://localhost:9/h"}).status_code == 422
    assert client.post(f"{API}/orgs/{org}/webhooks", headers=headers, json={"url": "https://127.0.0.1/h"}).status_code == 422
    from procureai.config.settings import get_settings

    get_settings().allow_private_webhooks = True  # allow the fake sender target
    try:
        h = client.post(f"{API}/orgs/{org}/webhooks", headers=headers, json={"url": "https://hooks.test/x", "events": ["agent.task.completed"]}).json()
    finally:
        get_settings().allow_private_webhooks = False
    assert h["secret"] and "secret" not in client.get(f"{API}/orgs/{org}/webhooks", headers=headers).json()[0]
    sent = []
    with get_session_factory()() as s:
        n = webhooks.dispatch(s, org, "agent.task.completed", {"x": 1}, sender=lambda u, b, hd: (sent.append((u, b, hd)), 200)[1])
        assert webhooks.dispatch(s, org, "agent.task.failed", {}, sender=lambda *a: 200) == 0  # event filter
    url, body, headers_sent = sent[0]
    assert n == 1 and headers_sent["X-ProcuraMind-Signature"] == "sha256=" + hmac.new(h["secret"].encode(), body, hashlib.sha256).hexdigest()
    assert json.loads(body)["event"] == "agent.task.completed"


# ---------------------------------------------------------------- chat, search, dashboard, activity, notifications
def test_chat_routes_to_agents_and_keeps_history(client, headers, project_with_docs):
    pid = project_with_docs
    r = client.post(f"{API}/chat", headers=headers, json={"message": "What is the maximum delivery time allowed?", "project_id": pid}).json()
    assert r["task"]["status"] == "completed" and r["task"]["output"]["evidence"]
    cid = r["conversation_id"]
    r2 = client.post(f"{API}/chat", headers=headers, json={"message": "and warranty?", "conversation_id": cid}).json()
    assert r2["conversation_id"] == cid
    conv = client.get(f"{API}/conversations/{cid}", headers=headers).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]
    assert client.get(f"{API}/conversations", headers=headers).json()[0]["id"] == cid
    assert client.delete(f"{API}/conversations/{cid}", headers=headers).status_code == 204


def test_chat_without_project_searches_workspace(client, headers, project_with_docs):
    r = client.post(f"{API}/chat", headers=headers, json={"message": "tender"}).json()
    assert "Select a project" in r["reply"] and r["search"]["documents"]


def test_conversations_are_private(client, auth, project_with_docs, headers):
    cid = client.post(f"{API}/chat", headers=headers, json={"message": "warranty?", "project_id": project_with_docs}).json()["conversation_id"]
    other = auth("p@x.io", "P")
    assert client.get(f"{API}/conversations/{cid}", headers=other).status_code == 404


def test_search_dashboard_activity_and_global_lists(client, headers, project_with_docs):
    pid = project_with_docs
    run(client, headers, "rag", pid, question="warranty")
    s = client.get(f"{API}/search", params={"q": "quotation"}, headers=headers).json()
    assert s["documents"] and client.get(f"{API}/search", params={"q": "Laptop"}, headers=headers).json()["projects"]
    d = client.get(f"{API}/dashboard", headers=headers).json()
    assert d["kpis"]["projects"] == 1 and d["kpis"]["documents"] == 7 and d["tasks_by_agent"].get("rag") == 1
    assert d["usage"]["agent_tasks_month"]["used"] >= 1
    act = client.get(f"{API}/activity", headers=headers).json()
    assert any(a["action"].startswith("agent.task") for a in act)
    assert len(client.get(f"{API}/documents-all", headers=headers).json()) == 7
    assert client.get(f"{API}/agents", headers=headers).json()[0]["can_send_external"] is False


def test_notifications_read_flow(client, headers, pid):
    run(client, headers, "data_analyst", pid)  # needs_input -> notification
    n = client.get(f"{API}/notifications", headers=headers).json()
    assert n["unread"] >= 1
    client.post(f"{API}/notifications/read", headers=headers)
    assert client.get(f"{API}/notifications", headers=headers).json()["unread"] == 0


def test_agent_task_quota_on_free_plan(client, headers, pid, env):
    from procureai.infrastructure.database.models import UsageEvent
    from procureai.infrastructure.database.session import get_session_factory

    org = client.get(f"{API}/orgs", headers=headers).json()[0]["id"]
    from procureai.infrastructure.database.models import AgentTask

    with get_session_factory()() as s:
        for _ in range(100):
            s.add(AgentTask(org_id=org, user_id="u", agent="rag", status="completed"))
        s.commit()
    r = client.post(f"{API}/agents/rag/run", headers=headers, json={"project_id": pid, "params": {"question": "x"}})
    assert r.status_code == 402 and UsageEvent  # quota message, not a crash
