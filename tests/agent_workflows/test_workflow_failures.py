import time

from procureai.agents.graphs.workflow import MAX_HOPS, supervisor_route
from procureai.shared.errors import ExternalServiceError


def _start(client, headers, pid):
    r = client.post(f"/api/v1/projects/{pid}/analysis-runs", headers=headers, json={"auto_confirm": True})
    return client.get(f"/api/v1/analysis-runs/{r.json()['id']}", headers=headers).json()


def test_supervisor_routing_is_pure_and_bounded():
    assert supervisor_route({}) == "validate_documents"
    s = {"documents_valid": True, "extraction_done": True, "vendors_done": True}
    assert supervisor_route(s) == ["technical_compliance", "price_intelligence"]  # parallel fan-out
    assert supervisor_route({**s, "compliance_done": True}) == ["price_intelligence"]
    assert supervisor_route({**s, "compliance_done": True, "price_done": True}) == "procurement_rag"
    done = {**s, "compliance_done": True, "price_done": True, "evidence_done": True}
    assert supervisor_route(done) == "verification"
    assert supervisor_route({**done, "verified": True}) == "finalize"
    assert supervisor_route({"errors": ["boom"]}) == "finalize"
    assert supervisor_route({"next_hops": MAX_HOPS + 1}) == "finalize"


def test_transient_failure_is_retried_then_succeeds(client, project_with_docs, headers, monkeypatch):
    from procureai.application.services import price_service

    real, calls = price_service.run_price_analysis, {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ExternalServiceError("fx service down")
        return real(*a, **k)

    monkeypatch.setattr(price_service, "run_price_analysis", flaky)
    run = _start(client, headers, project_with_docs)
    assert run["status"] in ("awaiting_human_review", "completed")
    steps = [s for s in run["steps"] if s["name"] == "price_intelligence"]
    assert [s["status"] for s in steps] == ["failed", "succeeded"] and [s["attempt"] for s in steps] == [1, 2]


def test_retry_exhaustion_fails_run_visibly(client, project_with_docs, headers, monkeypatch):
    from procureai.application.services import price_service

    def always(*a, **k):
        raise ExternalServiceError("down")

    monkeypatch.setattr(price_service, "run_price_analysis", always)
    run = _start(client, headers, project_with_docs)
    assert run["status"] == "failed" and "price_intelligence" in run["error"]
    steps = [s for s in run["steps"] if s["name"] == "price_intelligence"]
    assert len(steps) == 3 and all(s["status"] == "failed" for s in steps)  # 1 try + 2 retries, then stop
    assert "technical_compliance" in [s["name"] for s in run["steps"]]  # parallel branch still recorded


def test_deterministic_error_is_not_retried(client, project_with_docs, headers, monkeypatch):
    from procureai.application.services import compliance_service
    from procureai.shared.errors import ProcessingError

    def bad(*a, **k):
        raise ProcessingError("malformed extraction")

    monkeypatch.setattr(compliance_service, "run_compliance", bad)
    run = _start(client, headers, project_with_docs)
    steps = [s for s in run["steps"] if s["name"] == "technical_compliance"]
    assert run["status"] == "failed" and len(steps) == 1 and "malformed extraction" in run["error"]


def test_unexpected_exception_hides_internals(client, project_with_docs, headers, monkeypatch):
    from procureai.application.services import compliance_service

    def bad(*a, **k):
        raise RuntimeError("SECRET-INTERNAL-DETAIL /etc/passwd")

    monkeypatch.setattr(compliance_service, "run_compliance", bad)
    run = _start(client, headers, project_with_docs)
    assert run["status"] == "failed" and "SECRET-INTERNAL" not in str(run)


def test_step_timeout(client, project_with_docs, headers, monkeypatch):
    from procureai.application.services import price_service

    monkeypatch.setenv("WORKFLOW_STEP_TIMEOUT_SECONDS", "0.3")
    monkeypatch.setenv("WORKFLOW_STEP_MAX_RETRIES", "0")
    from procureai.application.context import reset_context
    from procureai.config.settings import get_settings

    get_settings.cache_clear()
    reset_context()

    def slow(*a, **k):
        time.sleep(1.5)

    monkeypatch.setattr(price_service, "run_price_analysis", slow)
    run = _start(client, headers, project_with_docs)
    assert run["status"] == "failed" and "timed out" in run["error"]
    time.sleep(1.6)  # let the abandoned worker thread finish before teardown


def test_retrieval_failure_is_non_fatal_but_visible(client, project_with_docs, headers, monkeypatch):
    from procureai.application.services import evidence_service

    def broken(*a, **k):
        raise ExternalServiceError("vector store down")

    monkeypatch.setattr(evidence_service, "collect_policy_evidence", broken)
    run = _start(client, headers, project_with_docs)
    assert run["status"] == "awaiting_human_review"
    assert any("Policy evidence unavailable" in n for n in run["summary"]["notes"])


def test_conflicting_vendor_values_raise_review_item(client, headers):
    pid = client.post("/api/v1/projects", json={"title": "Conflict"}, headers=headers).json()["id"]
    tender = (
        b"Tender notice for bidders\nItem: Widgets\nQuantity: 10 units\nTechnical Requirements\nMinimum RAM: 16 GB\n"
    )
    quote = b"Quotation from vendor\nVendor: Acme\nUnit price: USD 10\nQuantity: 10\nCurrency: USD\nOffered Specifications\nRAM: 8 GB\nRAM: 16 GB\n"
    for name, blob, t in (("t.txt", tender, "tender"), ("q.txt", quote, "quotation")):
        client.post(
            f"/api/v1/projects/{pid}/documents",
            headers=headers,
            files={"file": (name, blob)},
            data={"document_type": t},
        )
    run = _start(client, headers, pid)
    items = client.get(f"/api/v1/analysis-runs/{run['id']}/review-items", headers=headers).json()
    assert any("Conflicting values" in i["reason"] for i in items)


def test_no_unresolved_items_completes_directly(client, headers):
    pid = client.post("/api/v1/projects", json={"title": "Clean"}, headers=headers).json()["id"]
    tender = (
        b"Tender notice for bidders\nItem: Widgets\nQuantity: 10 units\nTechnical Requirements\nMinimum RAM: 16 GB\n"
    )
    quote = b"Quotation from vendor\nVendor: Acme\nUnit price: USD 10\nQuantity: 10\nCurrency: USD\nOffered Specifications\nRAM: 32 GB\n"
    for name, blob, t in (("t.txt", tender, "tender"), ("q.txt", quote, "quotation")):
        client.post(
            f"/api/v1/projects/{pid}/documents",
            headers=headers,
            files={"file": (name, blob)},
            data={"document_type": t},
        )
    run = _start(client, headers, pid)
    # one vendor only: single price point -> no baseline; auto-confirmed quotation -> nothing to review
    assert run["status"] == "completed", run
    assert run["summary"]["open_review_items"] == 0


def test_ambiguous_result_requires_review_without_llm(client, project_with_docs, headers):
    run = _start(client, headers, project_with_docs)
    comp = client.get(f"/api/v1/projects/{project_with_docs}/compliance?run_id={run['id']}", headers=headers).json()
    amb = [c for c in comp if c["status"] == "Requires Human Review"]
    assert amb and all(c["review_required"] and c["method"] == "deterministic" for c in amb)
