"""HR, Customer Support and Operations platforms (synthetic samples)."""

from __future__ import annotations

import io

import pytest

from procureai.samples import packs

API = "/api/v1"


def up(client, headers, pid, name, content, dtype):
    r = client.post(f"{API}/projects/{pid}/documents", headers=headers, files={"file": (name, io.BytesIO(content.encode()))}, data={"document_type": dtype})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def run(client, headers, agent, pid, **params):
    r = client.post(f"{API}/agents/{agent}/run", headers=headers, json={"project_id": pid, "params": params})
    assert r.status_code == 200, r.text
    return r.json()


def mk(client, headers, domain):
    return client.post(f"{API}/projects", json={"title": f"{domain} project", "domain": domain}, headers=headers).json()["id"]


def test_platform_catalogue(client, headers):
    cat = client.get(f"{API}/platforms", headers=headers).json()
    ids = {p["id"] for p in cat}
    assert ids == {"procurement", "hr", "support", "legal", "finance", "operations", "knowledge"}
    hr = next(p for p in cat if p["id"] == "hr")
    assert "resume_screener" in hr["agents"] and "rag" in hr["agents"]
    assert all(p["agents"] for p in cat)


def test_new_document_types_accepted_and_autoclassified(client, headers):
    pid = mk(client, headers, "hr")
    jd = up(client, headers, pid, "any.txt", packs.JOB_DESCRIPTION, "auto")
    docs = {d["id"]: d for d in client.get(f"{API}/projects/{pid}/documents", headers=headers).json()}
    assert docs[jd]["document_type"] == "job_description"
    up(client, headers, pid, "r.txt", packs.RESUMES["resume_arjun.txt"], "auto")
    assert any(d["document_type"] == "resume" for d in client.get(f"{API}/projects/{pid}/documents", headers=headers).json())


def test_resume_screener_ranks_and_explains(client, headers):
    pid = mk(client, headers, "hr")
    up(client, headers, pid, "jd.txt", packs.JOB_DESCRIPTION, "job_description")
    for n, t in packs.RESUMES.items():
        up(client, headers, pid, n, t, "resume")
    t = run(client, headers, "resume_screener", pid)
    assert t["status"] == "completed"
    table = next(s for s in t["output"]["sections"] if s["type"] == "table")
    assert [r[1] for r in table["rows"]] == ["resume_arjun.txt", "resume_neha.txt", "resume_kabir.txt"]
    top, mid = table["rows"][0], table["rows"][1]
    assert top[3] > mid[3] > table["rows"][2][3] and top[5] == "-" and "kubernetes" in mid[5] or "docker" in mid[5]
    assert "protected attributes" in str(t["output"]["sections"]) and t["output"]["evidence"]
    basis = next(s for s in t["output"]["sections"] if s["type"] == "kv")
    assert "python" in str(basis["items"]) and "3" in str(basis["items"])


def test_resume_screener_needs_inputs(client, headers):
    pid = mk(client, headers, "hr")
    assert run(client, headers, "resume_screener", pid)["status"] == "needs_input"
    up(client, headers, pid, "jd.txt", packs.JOB_DESCRIPTION, "job_description")
    assert run(client, headers, "resume_screener", pid)["status"] == "needs_input"  # no resumes yet
    up(client, headers, pid, "r.txt", packs.RESUMES["resume_neha.txt"], "resume")
    assert run(client, headers, "resume_screener", pid, must_have="python, sql")["status"] == "completed"


def test_ticket_triage_categories_priority_duplicates(client, headers):
    pid = mk(client, headers, "support")
    up(client, headers, pid, "tickets.csv", packs.tickets_csv(), "tickets")
    t = run(client, headers, "ticket_triage", pid)
    assert t["status"] == "completed"
    d = t["output"]["data"]
    assert d["priorities"]["High"] >= 3 and d["categories"]["Billing"] >= 2
    secs = t["output"]["sections"]
    top = next(s for s in secs if s["title"].startswith("Highest"))
    assert top["rows"][0][1] == "High"
    dup = next(s for s in secs if "duplicate" in s["title"].lower())
    assert {dup["rows"][0][0], dup["rows"][0][1]} == {"1", "6"}


def test_ticket_triage_validates_columns(client, headers):
    pid = mk(client, headers, "support")
    up(client, headers, pid, "x.csv", "a,b\n1,2\n", "tickets")
    assert run(client, headers, "ticket_triage", pid)["status"] == "needs_input"


def test_support_reply_is_grounded_cited_and_needs_approval(client, headers):
    pid = mk(client, headers, "support")
    up(client, headers, pid, "kb.txt", packs.KNOWLEDGE_BASE, "knowledge_base")
    t = run(client, headers, "support_reply", pid, ticket="I was charged twice for my order, how do I get refunded?")
    assert t["status"] == "awaiting_approval" and t["output"]["data"]["grounded"] is True and t["output"]["evidence"]
    draft = next(s for s in t["output"]["sections"] if s["type"] == "draft")
    assert "5 to 7 business days" in draft["body"] and "not sent" in draft["title"]
    off = run(client, headers, "support_reply", pid, ticket="What is the airspeed velocity of an unladen swallow?")
    assert off["output"]["data"]["grounded"] is False and "Escalate" in off["summary"]
    ok = client.post(f"{API}/tasks/{t['id']}/decision", headers=headers, json={"approve": True}).json()
    assert ok["status"] == "completed"


def test_meeting_actions_owners_dates_decisions(client, headers):
    pid = mk(client, headers, "operations")
    up(client, headers, pid, "m.txt", packs.MEETING_NOTES, "meeting_notes")
    t = run(client, headers, "meeting_actions", pid)
    secs = {s["title"]: s for s in t["output"]["sections"]}
    acts = secs["Action items"]["rows"]
    assert any(a[0] == "Ravi" and a[2].startswith("2026-12-01") for a in acts)
    assert any(a[0] == "Meera" and "2026-11-20" in a[2] for a in acts)
    assert any(a[0] == "Unassigned" for a in acts)
    assert secs["Decisions recorded"]["rows"] and any("security review" in r[0] for r in secs["Open questions / TBD"]["rows"])


def test_risk_register_flags_and_ranks(client, headers):
    pid = mk(client, headers, "operations")
    up(client, headers, pid, "m.txt", packs.MEETING_NOTES, "meeting_notes")
    t = run(client, headers, "risk_register", pid)
    reg = t["output"]["sections"][0]["rows"]
    assert reg[0][2] == "High" and reg[0][0] == "R-001" and any(r[1] == "Budget" for r in reg)
    assert "humans" in str(t["output"]["sections"][-1]) or "people" in str(t["output"]["sections"][-1])


def test_supervisor_routes_to_platform_agents(client, headers):
    pid = mk(client, headers, "hr")
    up(client, headers, pid, "jd.txt", packs.JOB_DESCRIPTION, "job_description")
    up(client, headers, pid, "r.txt", packs.RESUMES["resume_arjun.txt"], "resume")
    t = run(client, headers, "supervisor", pid, request="Shortlist the candidates for the job description")
    assert t["output"]["data"]["plan"]["agents"] == ["resume_screener"] and t["status"] == "completed"
    pid2 = mk(client, headers, "support")
    up(client, headers, pid2, "t.csv", packs.tickets_csv(), "tickets")
    assert run(client, headers, "supervisor", pid2, request="triage our support tickets")["output"]["data"]["plan"]["agents"] == ["ticket_triage"]


@pytest.mark.parametrize("req,agent", [("reply to the customer about the refund", "support_reply"), ("what action items came from the meeting", "meeting_actions"), ("identify project risks", "risk_register")])
def test_router_pack_intents(req, agent):
    from procureai.agents.suite.router import plan

    assert plan(req)["agents"] == [agent]
