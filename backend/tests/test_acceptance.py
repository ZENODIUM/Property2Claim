import base64
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.ai.jev_adapter import JevDecisionModel
from app.config import Settings
from app.models import AuditEvent, Claim, Company, Document, EvidenceFact, HistoricalClaim, LossEstimate, Property, ReviewTask, RiskDataRecord
from app.providers.hazards import parse_eonet_event, parse_noaa_feature
from app.seed.seed import seed_database


def test_seed_is_idempotent_and_persistent(test_context):
    _, Session, _ = test_context
    with Session() as db:
        first = seed_database(db)
        second = seed_database(db)
        assert first == second == {"companies": 8, "properties": 19, "historical_claims": 150, "claims": 7, "risk_records": 285}
    with Session() as restarted:
        assert restarted.scalar(select(func.count()).select_from(Company)) == 8
        assert restarted.scalar(select(func.count()).select_from(RiskDataRecord)) == 285
        assert set(restarted.scalars(select(RiskDataRecord.category).distinct()).all()) == set(range(1, 16))


def test_health_map_filter_and_drilldown(test_context):
    client, _, _ = test_context
    assert client.get("/api/health").json()["status"] == "ok"
    companies = client.get("/api/companies").json()["items"]
    assert len(companies) == 8 and all(c["synthetic"] for c in companies)
    northstar = next(c for c in companies if c["name"] == "NorthStar Manufacturing")
    props = client.get(f"/api/properties?company_id={northstar['id']}").json()["items"]
    assert len(props) == 3
    detail = client.get(f"/api/properties/{props[0]['id']}").json()
    assert len(detail["risk_categories"]) == 15
    assert detail["tiv_cents"] == sum(detail[f"{key}_value_cents"] for key in ["building", "equipment", "contents"]) + detail["business_income_cents"]


def test_machine_condition_pairs_are_consistently_linked(test_context):
    client, Session, _ = test_context
    claims = client.get("/api/claims").json()["items"]
    paired_numbers = {"AR-CLM-1001", "PC-CLM-2001", "PC-CLM-2002", "PC-CLM-2003", "PC-CLM-2004"}
    assert paired_numbers.issubset({claim["claim_number"] for claim in claims})
    for number in paired_numbers:
        claim = next(item for item in claims if item["claim_number"] == number)
        detail = client.get(f"/api/claims/{claim['id']}").json()
        pair = [doc for doc in detail["documents"] if doc["classification"] in {"condition_before", "condition_after"}]
        assert {doc["classification"] for doc in pair} == {"condition_before", "condition_after"}
        assert all(doc["source_mode"] == "user_supplied_scenario" for doc in pair)
        assert all(doc["analysis_status"] == "retained_requires_human_verification" for doc in pair)
        assert all(client.get(f"/api/documents/{doc['id']}/preview").status_code == 200 for doc in pair)
    with Session() as db:
        paired_docs = db.scalars(select(Document).where(Document.classification.in_(["condition_before", "condition_after"]))).all()
        assert len(paired_docs) == 10
        assert db.scalar(select(func.count()).select_from(EvidenceFact).where(EvidenceFact.document_id.in_([doc.id for doc in paired_docs]))) == 10


def test_sov_csv_and_pdf_ingestion(test_context):
    client, _, _ = test_context
    sov = Path(__file__).parents[1] / "app" / "seed" / "fixtures" / "synthetic_sov.csv"
    response = client.post("/api/ingest/sov", data={"company_id": 4}, files={"file": (sov.name, sov.read_bytes(), "text/csv")})
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    second = client.post("/api/ingest/sov", data={"company_id": 4}, files={"file": (sov.name, sov.read_bytes(), "text/csv")})
    assert second.json()["updated"] == 1
    pdf = Path(__file__).parents[1] / "app" / "seed" / "fixtures" / "synthetic_inspection.pdf"
    ingested = client.post("/api/ingest/document", data={"company_id": 1, "property_id": 1, "classification": "inspection_report"}, files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()["facts"][0]["page_number"] == 1
    assert "certificate" in ingested.json()["facts"][0]["value"]["text"]


def test_underwriting_graph_and_jev_contract(test_context):
    client, Session, _ = test_context
    result = client.post("/api/underwriting/1/run")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "needs_info"
    assert body["route"] in {"incomplete", "engineering_specialist"}
    assert body["decision_source"] == "mock/rules"
    with Session() as db:
        task = db.scalar(select(ReviewTask).where(ReviewTask.subject_type == "underwriting"))
        assert task and task.required_role == "underwriter"
    payload = JevDecisionModel.request_payload("route?", ["a", "b"], {"synthetic": True}, "jev-latest")
    assert payload["questions"][0]["type"] == "choice"
    assert "yesno" not in str(payload)
    assert JevDecisionModel.noul_payload("supported?", {"synthetic": True}, "jev-latest")["questions"][0]["type"] == "noul"


def test_provider_parsers_and_hazard_exact_match_no_claim(test_context):
    client, Session, _ = test_context
    noaa = parse_noaa_feature({"id": "n1", "geometry": {"type": "Point", "coordinates": [-95, 29]}, "properties": {"event": "Flood Warning", "headline": "Test", "severity": "Severe", "effective": "2026-01-01T00:00:00Z"}})
    eonet = parse_eonet_event({"id": "e1", "title": "Wildfire", "categories": [{"title": "Wildfires"}], "geometry": [{"date": "2026-01-01T00:00:00Z", "type": "Point", "coordinates": [-120, 38]}]})
    assert noaa["provider"] == "NOAA" and eonet["provider"] == "NASA_EONET"
    with Session() as db:
        claims_before = db.scalar(select(func.count()).select_from(Claim))
        expected = sorted(db.scalars(select(Property.id).where(Property.site_code.in_(["NS-HOU-A", "NS-TUL-B"]))).all())
    response = client.post("/api/hazards/replay/severe-weather-two-sites")
    assert response.status_code == 200
    assert response.json()["matched_property_ids"] == expected
    assert response.json()["claims_created"] == 0
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Claim)) == claims_before


def test_fnol_cross_company_guard_claim_resume_and_estimate_revision(test_context):
    client, Session, _ = test_context
    payload = {"company_id": 1, "property_id": 1, "policy_id": 1, "loss_at": datetime.now(timezone.utc).isoformat(), "peril": "water", "narrative": "Synthetic water leak reported at the production line.", "reported_exposures": ["building", "equipment"]}
    bad = payload | {"company_id": 2}
    assert client.post("/api/claims/fnol", json=bad).status_code == 404
    created = client.post("/api/claims/fnol", json=payload)
    assert created.status_code == 201, created.text
    claim = created.json()
    assert claim["status"] == "waiting_evidence"
    first = client.post(f"/api/claims/{claim['id']}/estimate").json()
    quote = client.post(f"/api/claims/{claim['id']}/evidence", data={"classification": "repair_quote", "amount_cents": 87500000}, files={"file": ("repair-quote.txt", b"Synthetic itemized repair quote: $875,000", "text/plain")})
    assert quote.status_code == 200, quote.text
    revised_claim = quote.json()["claim"]
    assert revised_claim["status"] == "estimate_review"
    estimates = client.get(f"/api/claims/{claim['id']}/estimates").json()["items"]
    assert len(estimates) >= 2
    assert estimates[-1]["gross_cents"] == 87500000
    assert estimates[-1]["gross_cents"] != first["gross_cents"]
    assert estimates[-1]["status"] == "synthetic_requires_human_review"
    assert any(p["kind"] == "repair_quote" for p in estimates[-1]["provenance"])


def test_role_gate_and_audit(test_context):
    client, Session, _ = test_context
    task = next(item for item in client.get("/api/tasks").json()["items"] if item["subject_type"] == "claim")
    denied = client.post(f"/api/tasks/{task['id']}/decision", json={"actor": "Demo Engineer", "actor_role": "engineer", "action": "authorize_settlement_simulation", "rationale": "Should be blocked by role permissions."})
    assert denied.status_code == 403
    approved = client.post(f"/api/tasks/{task['id']}/decision", json={"actor": "Demo Supervisor", "actor_role": "supervisor", "action": "authorize_settlement_simulation", "rationale": "Authorized synthetic settlement simulation review only."})
    assert approved.status_code == 200
    assert approved.json()["simulation_only"] is True
    with Session() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "human_decision").order_by(AuditEvent.id.desc()))
        assert event.details["action"] == "authorize_settlement_simulation"
        assert event.source == "human"


def test_workflow_results_missing_evidence_reanalysis_and_human_review(test_context):
    client, _, _ = test_context
    payload = {"company_id": 1, "property_id": 1, "policy_id": 1, "loss_at": datetime.now(timezone.utc).isoformat(), "peril": "water", "narrative": "Synthetic missing-evidence workflow result verification.", "reported_exposures": ["equipment"]}
    claim = client.post("/api/claims/fnol", json=payload).json()
    before = client.get("/api/workflows/results").json()
    original = next(item for item in before["items"] if (item.get("claim") or {}).get("id") == claim["id"])
    assert original["queue"] == "needs_evidence"
    assert original["missing_items"] == ["itemized machine repair quote"]
    upload = client.post(f"/api/claims/{claim['id']}/evidence", data={"classification": "repair_quote", "amount_cents": 42500000}, files={"file": ("quote.txt", b"Synthetic itemized repair quotation: $425,000", "text/plain")})
    assert upload.status_code == 200
    after = client.get("/api/workflows/results").json()
    revised = [item for item in after["items"] if (item.get("claim") or {}).get("id") == claim["id"] and item["trigger"] == "evidence_uploaded"][0]
    assert revised["queue"] == "human_review"
    assert revised["financials"]["gross_estimated_loss_cents"] == 42500000
    task = next(task for task in revised["tasks"] if task["kind"] == "estimate_review")
    decision = client.post(f"/api/tasks/{task['id']}/decision", json={"actor": "Demo Claims Reviewer", "actor_role": "claims_reviewer", "action": "approve_reserve_review", "rationale": "Reviewed the synthetic quote and calculation inputs."})
    assert decision.status_code == 200
    completed = client.get(f"/api/workflows/results/{revised['id']}").json()
    assert completed["queue"] == "completed"
    assert completed["financials"]["reviewed_reserve_cents"] is not None
    assert completed["financials"]["authorized_payment_cents"] is None
    assert any(step["label"] == "human_decision" for step in completed["timeline"])


def test_upload_security_validation_and_floorplan_manual_geometry(test_context):
    client, _, _ = test_context
    unsafe = client.post("/api/ingest/document", data={"company_id": 1}, files={"file": ("../escape.pdf", b"%PDF-invalid", "application/pdf")})
    assert unsafe.status_code == 400
    invalid = client.post("/api/claims/fnol", json={"company_id": 1, "property_id": 1, "policy_id": 1, "loss_at": datetime.now(timezone.utc).isoformat(), "peril": "invalid", "narrative": "too short", "reported_exposures": []})
    assert invalid.status_code == 422
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    uploaded = client.post("/api/properties/1/floorplans", data={"floor_name": "Ground Floor"}, files={"file": ("synthetic-plan.png", png, "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    plan_id = uploaded.json()["id"]
    obj = client.post(f"/api/floorplans/{plan_id}/objects", json={"object_type": "machine", "label": "Manually marked machine", "geometry_type": "rect", "geometry": {"x": .2, "y": .2, "w": .2, "h": .2}, "layer": "machinery", "human_verified": True})
    assert obj.status_code == 201
    intersect = client.post(f"/api/floorplans/{plan_id}/intersections", json={"polygon": [[.1, .1], [.5, .1], [.5, .5], [.1, .5]]})
    assert intersect.json()["possibly_affected_object_ids"] == [obj.json()["id"]]
    assert "does not prove damage" in intersect.json()["disclaimer"]


def test_capabilities_never_expose_secrets(test_context):
    client, _, _ = test_context
    body = client.get("/api/config/capabilities").json()
    assert body["secrets_exposed"] is False
    assert "api_key" not in str(body).lower()
    assert body["gemini"]["real_media_validation"] == "PENDING_USER_FIXTURES"


def test_evidence_preview_media_status_and_reprocess_gate(test_context):
    client, _, _ = test_context
    pdf = Path(__file__).parents[1] / "app" / "seed" / "fixtures" / "synthetic_inspection.pdf"
    uploaded = client.post("/api/claims/1/evidence", data={"classification": "inspection_report", "amount_cents": 1250000}, files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
    assert uploaded.status_code == 200
    document_id = uploaded.json()["document"]["id"]
    detail = client.get(f"/api/documents/{document_id}").json()
    assert detail["page_count"] == 1
    assert detail["analysis_status"] == "completed_text_extraction"
    assert any(fact["page_number"] == 1 for fact in detail["facts"])
    preview = client.get(f"/api/documents/{document_id}/preview?page=1")
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/png"

    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    media = client.post("/api/claims/1/media", data={"authorize_external_analysis": "false"}, files={"file": ("synthetic-evidence.png", png, "image/png")})
    assert media.status_code == 200
    media_id = media.json()["document"]["id"]
    assert media.json()["real_analysis_performed"] is False
    assert media.json()["document"]["analysis_status"] == "mock_schema_only"
    assert client.post(f"/api/documents/{media_id}/reprocess", data={"authorize_external_analysis": "false"}).status_code == 409


def test_overview_priority_and_estimate_calculation_fields(test_context):
    client, _, _ = test_context
    overview = client.get("/api/overview").json()
    assert overview["properties"] == 19
    assert overview["priority_case"]["claim_number"] == "AR-CLM-1001"
    assert overview["priority_case"]["queue"] == "Needs evidence"
    claim = client.get("/api/claims/1").json()
    estimate = claim["estimates"][-1]
    assert estimate["policy_limit_cents"] is not None
    assert estimate["proposed_payment_cents"] is None
    assert estimate["authorized_payment_cents"] is None
    assert estimate["line_items"]
    inspection = next(document for document in claim["documents"] if document["classification"] == "inspection_report")
    assert inspection["claim_id"] is None
