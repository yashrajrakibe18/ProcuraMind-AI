"""Full journey: create -> upload -> extract -> review -> analyse -> inspect evidence -> approve -> export."""

import io

from openpyxl import load_workbook


def _run(client, headers, pid, auto_confirm=False):
    r = client.post(f"/api/v1/projects/{pid}/analysis-runs", headers=headers, json={"auto_confirm": auto_confirm})
    assert r.status_code == 202, r.text
    return client.get(f"/api/v1/analysis-runs/{r.json()['id']}", headers=headers).json()


def test_blocked_until_requirements_confirmed(client, project_with_docs, headers):
    pid = project_with_docs
    client.post(f"/api/v1/projects/{pid}/requirements/extract", headers=headers)
    run = _run(client, headers, pid)
    assert run["status"] == "failed" and "not confirmed" in run["error"]
    assert [s["name"] for s in run["steps"]] == ["validate_documents"]
    assert run["steps"][0]["status"] == "failed"


def test_full_journey(client, project_with_docs, headers):
    pid = project_with_docs
    rep = client.post(f"/api/v1/projects/{pid}/requirements/extract", headers=headers).json()
    assert rep["created"] == 8
    assert client.post(f"/api/v1/projects/{pid}/requirements/confirm-all", headers=headers).json()["confirmed"] == 8
    again = client.post(f"/api/v1/projects/{pid}/requirements/extract", headers=headers).json()
    assert again["created"] == 0 and again["kept_confirmed"] == 8  # idempotent, keeps confirmed rows
    project = client.get(f"/api/v1/projects/{pid}", headers=headers).json()
    assert project["tender_quantity"] == 50 and project["item_description"] == "Business laptops"
    vend = client.post(f"/api/v1/projects/{pid}/vendors/extract", headers=headers).json()
    assert vend["created"] == 4

    run = _run(client, headers, pid)
    assert run["status"] == "awaiting_human_review", run
    names = [s["name"] for s in run["steps"]]
    for n in (
        "validate_documents",
        "document_intelligence",
        "vendor_analysis",
        "technical_compliance",
        "price_intelligence",
        "procurement_rag",
        "verification",
    ):
        assert n in names
    assert all(s["status"] == "succeeded" for s in run["steps"])
    assert run["model_info"]["llm_provider"] == "none"

    comp = client.get(f"/api/v1/projects/{pid}/compliance", headers=headers).json()
    assert len(comp) == 4 * 8
    cell = {(r["vendor_name"], r["requirement_label"]): r for r in comp}
    assert cell[("Northwind Computers", "RAM")]["status"] == "Meets Requirement"
    assert cell[("Northwind Computers", "Warranty")]["status"] == "Meets Requirement"
    assert cell[("Contoso Systems", "RAM")]["status"] == "Does Not Meet Requirement"
    assert cell[("Contoso Systems", "Warranty")]["status"] == "Does Not Meet Requirement"  # 24 months < 3 years
    assert cell[("Contoso Systems", "Delivery")]["status"] == "Does Not Meet Requirement"  # 6 weeks > 30 days
    assert cell[("Contoso Systems", "Operating system")]["status"] == "Requires Human Review"
    assert cell[("Fabrikam Tech", "Processor cores")]["status"] == "Missing Information"
    assert cell[("Fabrikam Tech", "Display size")]["status"] == "Does Not Meet Requirement"
    assert cell[("Globex Trading", "Storage capacity")]["status"] == "Meets Requirement"  # 1 TB >= 512 GB
    assert cell[("Globex Trading", "Delivery")]["status"] == "Meets Requirement"  # boundary: 30 <= 30
    ev = cell[("Northwind Computers", "RAM")]["evidence"]["offered"]
    assert ev["page"] == 2 and "16 GB" in ev["text"] and ev["document_id"]

    price = client.get(f"/api/v1/projects/{pid}/price-analysis", headers=headers).json()
    flagged = {(p["vendor_name"], p["baseline_source"]) for p in price if p["anomaly_flag"]}
    assert ("Fabrikam Tech", "peer") in flagged and ("Fabrikam Tech", "historical") in flagged
    assert not any(v == "Northwind Computers" for v, _ in flagged)
    nw = next(p for p in price if p["vendor_name"] == "Northwind Computers" and p["baseline_source"] == "peer")
    assert nw["subtotal"] == 57500 and nw["tax_amount"] == 5750 and nw["normalized_total"] == 63750  # 57500+5750+500
    assert "not a finding" in next(p for p in price if p["anomaly_flag"])["explanation"]

    policy = client.get(f"/api/v1/projects/{pid}/policy-evidence", headers=headers).json()
    assert policy and all(p["page"] for p in policy)

    # human review gates approval
    assert client.post(f"/api/v1/analysis-runs/{run['id']}/approve", headers=headers).status_code == 409
    items = client.get(f"/api/v1/analysis-runs/{run['id']}/review-items", headers=headers).json()
    assert {i["kind"] for i in items} >= {"compliance", "price", "extraction"}
    # extraction/verification items cannot take a compliance decision
    bad = next(i for i in items if i["kind"] == "extraction")
    assert (
        client.post(
            f"/api/v1/review-items/{bad['id']}/resolve", headers=headers, json={"note": "ok", "decision": "meets"}
        ).status_code
        == 422
    )
    for it in items:
        decision = "meets" if (it["kind"] == "compliance" and "Windows 11 Home" in it["reason"]) else "acknowledged"
        r = client.post(
            f"/api/v1/review-items/{it['id']}/resolve",
            headers=headers,
            json={"note": "Reviewed by officer", "decision": decision},
        )
        assert r.status_code == 200, r.text
    assert (
        client.post(
            f"/api/v1/review-items/{items[0]['id']}/resolve",
            headers=headers,
            json={"note": "again", "decision": "acknowledged"},
        ).status_code
        == 409
    )
    comp2 = {
        (r["vendor_name"], r["requirement_label"]): r
        for r in client.get(f"/api/v1/projects/{pid}/compliance", headers=headers).json()
    }
    osr = comp2[("Contoso Systems", "Operating system")]
    assert osr["status"] == "Requires Human Review" and osr["effective_status"] == "Meets Requirement"
    approved = client.post(f"/api/v1/analysis-runs/{run['id']}/approve", headers=headers)
    assert approved.status_code == 200 and approved.json()["status"] == "completed"
    assert approved.json()["summary"]["approved_by"]

    # exports
    pdf = client.post(f"/api/v1/projects/{pid}/reports", headers=headers, json={"report_type": "pdf"})
    xls = client.post(f"/api/v1/projects/{pid}/reports", headers=headers, json={"report_type": "excel"})
    assert pdf.status_code == 201 and xls.status_code == 201
    blob = client.get(f"/api/v1/reports/{pdf.json()['id']}/download", headers=headers)
    assert blob.content.startswith(b"%PDF") and blob.headers["content-type"] == "application/pdf"
    import pymupdf

    text = "\n".join(p.get_text() for p in pymupdf.open(stream=blob.content, filetype="pdf"))
    assert "Source fact" in text and "Calculated" in text and "Approved by user" in text
    assert "not findings of overpricing" in text.replace("\n", " ")
    wb = load_workbook(io.BytesIO(client.get(f"/api/v1/reports/{xls.json()['id']}/download", headers=headers).content))
    assert {"Summary", "Compliance", "Price analysis", "Policy evidence", "Review items"} <= set(wb.sheetnames)
    assert wb["Compliance"].max_row == 1 + 32
    assert len(client.get(f"/api/v1/projects/{pid}/reports", headers=headers).json()) == 2

    # dashboard shows real, non-zero figures
    kpis = client.get("/api/v1/dashboard/overview", headers=headers).json()["kpis"]
    assert kpis["projects"] == 1 and kpis["vendors"] == 4 and kpis["analysis_runs"] == 1
    assert kpis["pending_reviews"] == 0


def test_auto_confirm_run_and_idempotent_start(client, project_with_docs, headers):
    pid = project_with_docs
    run = _run(client, headers, pid, auto_confirm=True)
    assert run["status"] in ("awaiting_human_review", "completed")
    runs = client.get(f"/api/v1/projects/{pid}/analysis-runs", headers=headers).json()
    assert len(runs) == 1
    # a second run after the first finished is allowed (history preserved)
    run2 = _run(client, headers, pid, auto_confirm=True)
    assert run2["id"] != run["id"]
    assert len(client.get(f"/api/v1/projects/{pid}/analysis-runs", headers=headers).json()) == 2


def test_report_requires_finished_run(client, project_with_docs, headers):
    r = client.post(f"/api/v1/projects/{project_with_docs}/reports", headers=headers, json={"report_type": "pdf"})
    assert r.status_code == 422


def test_missing_tender_fails_with_reason(client, headers, samples):
    pid = client.post("/api/v1/projects", json={"title": "No tender"}, headers=headers).json()["id"]
    client.post(
        f"/api/v1/projects/{pid}/documents",
        headers=headers,
        files={"file": ("q.pdf", samples["quotation_northwind.pdf"])},
    )
    run = _run(client, headers, pid)
    assert run["status"] == "failed" and "tender" in run["error"]


def test_spec_correction_marks_verified(client, project_with_docs, headers):
    pid = project_with_docs
    client.post(f"/api/v1/projects/{pid}/vendors/extract", headers=headers)
    vendors = client.get(f"/api/v1/projects/{pid}/vendors", headers=headers).json()
    contoso = next(v for v in vendors if v["vendor_name"] == "Contoso Systems")
    spec = next(s for s in contoso["quotations"][0]["specifications"] if s["field"] == "ram")
    fixed = client.patch(f"/api/v1/specifications/{spec['id']}", json={"value_text": "16 GB"}, headers=headers).json()
    assert fixed["value_numeric"] == 16 and fixed["confidence"] == 1.0
    q = client.patch(
        f"/api/v1/quotations/{contoso['quotations'][0]['id']}",
        json={"currency": "usd", "confirmed": True},
        headers=headers,
    ).json()
    assert q["currency"] == "USD" and q["confirmed"]
