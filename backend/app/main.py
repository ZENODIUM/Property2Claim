from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import fitz
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from .ai.provider_adapters import GeminiVisionModel, MockVisionModel
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db, init_db
from .models import (
    Asset, AuditEvent, Building, Claim, ClaimExposure, Company, Coverage, Document,
    EstimateLineItem, EvidenceFact, Floor, FloorObject, FloorPlan, HazardEvent,
    HumanDecision, Inspection, LossEstimate, Policy, Property, PropertyHazardMatch,
    ReviewTask, RiskDataRecord, SafetyFinding, UnderwritingSubmission, WorkflowRun,
)
from .providers.hazards import fetch_live_hazards
from .schemas import CompanyCreate, DemoIssueRequest, FNOLCreate, FloorObjectCreate, IntersectionRequest, TaskDecisionCreate, UnderwritingCreate
from .seed.seed import ensure_portfolio_extension, seed_database
from .seed.supplied_floorplans import ensure_secondary_supplied_floorplans, ensure_supplied_floorplans
from .services.ingestion import extract_pdf_facts, import_sov, parse_sov
from .services.media import FloorPlanDetectionService, FrameSamplingConfig, MediaAnalysisService
from .services.spatial import normalized_object_shape
from .services.workflows import audit, create_estimate, decide_task, replay_hazard, run_claim, run_underwriting
from .storage.safe_upload import save_upload

settings = get_settings()


def backfill_demo_evidence_metadata(db: Session) -> None:
    """Add deterministic extraction metadata to legacy demo rows without provider calls."""
    for doc in db.scalars(select(Document).where(Document.media_type == "application/pdf")).all():
        if Path(doc.storage_path).is_file() and not db.scalar(select(EvidenceFact.id).where(EvidenceFact.document_id == doc.id).limit(1)):
            extract_pdf_facts(db, doc.id, Path(doc.storage_path), "property" if doc.property_id else "company", doc.property_id or doc.company_id)
            doc.analysis_status = "completed_text_extraction"
    for plan in db.scalars(select(FloorPlan).where(FloorPlan.analysis_status == "complete")).all():
        document = db.get(Document, plan.original_document_id)
        if document:
            document.analysis_status = "completed_floorplan_vision"
    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.demo_mode:
        with SessionLocal() as db:
            seed_database(db)
            ensure_portfolio_extension(db)
            ensure_supplied_floorplans(db, settings)
            ensure_secondary_supplied_floorplans(db, settings)
            backfill_demo_evidence_metadata(db)
    yield


app = FastAPI(title="Property2Claim API", version="0.1.0", description="Commercial property intelligence workspace with human authorization controls.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def money(cents: int | None) -> float | None:
    return round(cents / 100, 2) if cents is not None else None


def company_out(c: Company) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "industry": c.industry, "naics": c.naics, "broker_contact": c.broker_contact, "state": c.state, "synthetic": c.synthetic}


def property_out(p: Property) -> dict[str, Any]:
    return {"id": p.id, "company_id": p.company_id, "site_code": p.site_code, "name": p.name, "address": p.address, "city": p.city, "region": p.region, "latitude": p.latitude, "longitude": p.longitude, "occupancy": p.occupancy, "construction": p.construction, "year_built": p.year_built, "area_sqft": p.area_sqft, "roof": p.roof, "protection": p.protection, "operations": p.operations, "building_value_cents": p.building_value_cents, "equipment_value_cents": p.equipment_value_cents, "contents_value_cents": p.contents_value_cents, "business_income_cents": p.business_income_cents, "tiv_cents": p.tiv_cents, "risk_score": p.risk_score, "baseline_hazards": p.baseline_hazards, "synthetic": True}


def claim_out(c: Claim, db: Session, detail: bool = False) -> dict[str, Any]:
    company = db.get(Company, c.company_id)
    prop = db.get(Property, c.property_id)
    condition_classes = set(db.scalars(select(Document.classification).where(Document.claim_id == c.id, Document.classification.in_(["condition_before", "condition_after"]))).all())
    data = {"id": c.id, "company_id": c.company_id, "company_name": company.name if company else None, "property_id": c.property_id, "property_name": prop.name if prop else None, "policy_id": c.policy_id, "claim_number": c.claim_number, "loss_at": c.loss_at, "reported_at": c.reported_at, "peril": c.peril, "narrative": c.narrative, "status": c.status, "synthetic": c.synthetic, "incident_geometry": c.incident_geometry, "contradiction_summary": c.contradiction_summary, "has_condition_pair": condition_classes == {"condition_before", "condition_after"}}
    if detail:
        data["exposures"] = [{"id": x.id, "type": x.exposure_type, "state": x.state, "estimate_cents": x.estimate_cents} for x in db.scalars(select(ClaimExposure).where(ClaimExposure.claim_id == c.id)).all()]
        data["estimates"] = [estimate_out(e, db) for e in db.scalars(select(LossEstimate).where(LossEstimate.claim_id == c.id).order_by(LossEstimate.version)).all()]
        data["documents"] = [document_out(d) for d in db.scalars(select(Document).where((Document.claim_id == c.id) | (Document.property_id == c.property_id)).order_by(Document.created_at.desc())).all()]
        data["tasks"] = [task_out(t) for t in db.scalars(select(ReviewTask).where(ReviewTask.subject_type == "claim", ReviewTask.subject_id == c.id)).all()]
    return data


def estimate_out(e: LossEstimate, db: Session) -> dict[str, Any]:
    claim = db.get(Claim, e.claim_id)
    coverage = db.scalar(select(Coverage).where(Coverage.policy_id == claim.policy_id, Coverage.coverage_type == "commercial_property")) if claim else None
    return {"id": e.id, "claim_id": e.claim_id, "version": e.version, "method": e.method, "gross_cents": e.gross_cents, "deductible_cents": e.deductible_cents, "policy_limit_cents": coverage.limit_cents if coverage else None, "illustrative_eligible_cents": e.illustrative_eligible_cents, "low_cents": e.low_cents, "high_cents": e.high_cents, "reserve_suggestion_cents": e.reserve_suggestion_cents, "proposed_payment_cents": None, "authorized_payment_cents": None, "assumptions": e.assumptions, "limitations": e.limitations, "provenance": e.provenance, "status": e.status, "created_at": e.created_at, "line_items": [{"id": i.id, "category": i.category, "description": i.description, "amount_cents": i.amount_cents, "source_kind": i.source_kind, "supported": i.supported} for i in db.scalars(select(EstimateLineItem).where(EstimateLineItem.estimate_id == e.id)).all()]}


def document_out(d: Document) -> dict[str, Any]:
    return {"id": d.id, "company_id": d.company_id, "property_id": d.property_id, "claim_id": d.claim_id, "filename": d.filename, "media_type": d.media_type, "classification": d.classification, "size_bytes": d.size_bytes, "source_mode": d.source_mode, "analysis_status": d.analysis_status, "created_at": d.created_at, "detail_url": f"/api/documents/{d.id}", "content_url": f"/api/documents/{d.id}/content"}


def persist_media_observations(db: Session, doc: Document, analysis: dict[str, Any]) -> int:
    """Persist source-addressable observations while retaining superseded runs for audit."""
    existing = db.scalars(select(EvidenceFact).where(EvidenceFact.document_id == doc.id, EvidenceFact.fact_type == "vision_observation")).all()
    for fact in existing:
        fact.fact_type = "vision_observation_superseded"
    frames = analysis.get("analyses") or [analysis]
    created = 0
    for frame in frames:
        timestamp = frame.get("timestamp_seconds")
        for observation in frame.get("observations", []):
            description = observation.get("description", "") if isinstance(observation, dict) else str(observation)
            confidence = observation.get("confidence_label") if isinstance(observation, dict) else None
            fact = EvidenceFact(document_id=doc.id, subject_type="claim", subject_id=doc.claim_id or 0, fact_type="vision_observation", value={"description": description, "confidence_label": confidence, "model": frame.get("model"), "mode": frame.get("mode", "live" if settings.gemini_api_key else "mock"), "evidence_refs": frame.get("evidence_refs", []), "potential_asset_tags": frame.get("potential_asset_tags", []), "limitations": frame.get("limitations", [])}, timestamp_seconds=timestamp, evidence_location=f"video frame at {timestamp:.0f}s" if timestamp is not None else "original image", verified=False)
            db.add(fact)
            created += 1
    db.flush()
    return created


def task_out(t: ReviewTask) -> dict[str, Any]:
    return {"id": t.id, "company_id": t.company_id, "property_id": t.property_id, "subject_type": t.subject_type, "subject_id": t.subject_id, "kind": t.kind, "title": t.title, "priority": t.priority, "required_role": t.required_role, "status": t.status, "details": t.details, "created_at": t.created_at}


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"status": "ok", "database": "connected" if db.scalar(select(func.count()).select_from(Company)) is not None else "error", "demo_mode": settings.demo_mode, "synthetic_only": True, "timestamp": datetime.now(timezone.utc)}


@app.get("/api/config/capabilities")
def capabilities() -> dict[str, Any]:
    return {"groq": {"configured": bool(settings.groq_api_key), "model": settings.groq_model, "mode": "live_available" if settings.groq_api_key else "mock_fallback"}, "gemini": {**GeminiVisionModel(settings).status(), "floorplan_model": settings.gemini_floorplan_model, "mode": "adapter_configured" if settings.gemini_api_key else "mock_schema_only"}, "jev": {"configured": bool(settings.jev_api_key), "model": settings.jev_model, "base_url": settings.jev_api_base_url, "mode": "live_available" if settings.jev_api_key else "deterministic_rules"}, "nasa_eonet": {"configured": True, "key_required": False, "general_key_available": bool(settings.nasa_api_key), "live_enabled": settings.allow_live_hazards}, "noaa": {"configured": True, "live_enabled": settings.allow_live_hazards}, "nasa_firms": {"configured": bool(settings.nasa_firms_map_key), "note": "FIRMS requires its dedicated MAP credential; a general NASA developer credential is not substituted."}, "privacy_notice": "Use synthetic content only unless an approved provider privacy arrangement exists.", "secrets_exposed": False}


@app.get("/api/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    candidates = db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(40)).all()
    recent_events = []
    seen: set[tuple[str, str, int, str]] = set()
    for event in candidates:
        key = (event.event_type, event.subject_type, event.subject_id, event.source)
        if key in seen:
            continue
        seen.add(key)
        recent_events.append({"id": event.id, "event_type": event.event_type, "subject_type": event.subject_type, "subject_id": event.subject_id, "actor": event.actor, "source": event.source, "details": event.details, "created_at": event.created_at})
        if len(recent_events) == 8:
            break
    priority_claim = db.scalar(select(Claim).where(Claim.claim_number == "AR-CLM-1001")) or db.scalar(select(Claim).where(Claim.status != "closed_demo").order_by(Claim.id))
    priority_case = None
    if priority_claim:
        site = db.get(Property, priority_claim.property_id)
        queue = "Needs evidence" if priority_claim.status == "waiting_evidence" else "Completed" if priority_claim.status == "closed_demo" else "Human review"
        priority_case = {"property_name": site.name if site else "Insured site", "claim_id": priority_claim.id, "claim_number": priority_claim.claim_number, "summary": "Evidence review pending for machinery loss" if priority_claim.status == "waiting_evidence" else priority_claim.narrative, "queue": queue, "status": priority_claim.status, "href": f"/claims/{priority_claim.id}"}
    return {"portfolio_tiv_cents": sum(p.tiv_cents for p in db.scalars(select(Property)).all()), "companies": db.scalar(select(func.count()).select_from(Company)), "properties": db.scalar(select(func.count()).select_from(Property)), "open_underwriting": db.scalar(select(func.count()).select_from(UnderwritingSubmission).where(UnderwritingSubmission.status.not_in(["approved_demo", "declined_demo"]))), "pending_human_tasks": db.scalar(select(func.count()).select_from(ReviewTask).where(ReviewTask.status.in_(["queued", "waiting"]))), "active_hazard_reviews": db.scalar(select(func.count()).select_from(PropertyHazardMatch).where(PropertyHazardMatch.status == "potential_exposure_review")), "open_claims": db.scalar(select(func.count()).select_from(Claim).where(Claim.status != "closed_demo")), "recent_events": recent_events, "priority_case": priority_case, "labels": {"financials": "synthetic illustrative", "hazards": "potential exposure only", "dashboard": "illustrative dashboard data"}}


def demo_journey_out(db: Session) -> dict[str, Any]:
    company = db.scalar(select(Company).where(Company.name == "NorthStar Manufacturing")) or db.scalar(select(Company).order_by(Company.id))
    prop = db.scalar(select(Property).where(Property.company_id == company.id).order_by(Property.id)) if company else None
    submission = db.scalar(select(UnderwritingSubmission).where(UnderwritingSubmission.company_id == company.id).order_by(UnderwritingSubmission.id)) if company else None
    claim = db.scalar(select(Claim).where(Claim.company_id == company.id).order_by(Claim.id)) if company else None
    hazard = db.scalar(select(HazardEvent).where(HazardEvent.provider_event_id == "REPLAY-SEVERE-2026-01"))
    plan = db.scalar(select(FloorPlan).join(Floor).join(Building).where(Building.property_id == prop.id, FloorPlan.is_base.is_(True)).order_by(FloorPlan.id)) if prop else None
    category_count = db.scalar(select(func.count(func.distinct(RiskDataRecord.category))).where(RiskDataRecord.property_id == prop.id)) if prop else 0
    document_count = db.scalar(select(func.count()).select_from(Document).where(Document.property_id == prop.id)) if prop else 0
    match_count = db.scalar(select(func.count()).select_from(PropertyHazardMatch).where(PropertyHazardMatch.hazard_event_id == hazard.id)) if hazard else 0
    estimate_count = db.scalar(select(func.count()).select_from(LossEstimate).where(LossEstimate.claim_id == claim.id)) if claim else 0
    decision_count = 0
    if claim:
        claim_task_ids = select(ReviewTask.id).where(ReviewTask.subject_type.in_(["claim", "claims"]), ReviewTask.subject_id == claim.id)
        decision_count = db.scalar(select(func.count()).select_from(HumanDecision).where(HumanDecision.task_id.in_(claim_task_ids))) or 0
    phases = [
        {"phase": "A", "title": "Account intake", "description": "Synthetic company and insured site identity are established.", "status": "complete" if company and prop else "pending", "metric": f"{1 if company else 0} account · {1 if prop else 0} primary site", "href": f"/companies/{company.id}" if company else "/companies"},
        {"phase": "B", "title": "Risk data model", "description": "The canonical property record spans all required insurance categories.", "status": "complete" if category_count == 15 else "in_progress", "metric": f"{category_count}/15 categories", "href": f"/companies/{company.id}" if company else "/companies"},
        {"phase": "C", "title": "Evidence & spatial context", "description": "Documents, original 2D plans, annotations, and provenance stay linked to the site.", "status": "complete" if document_count and plan else "in_progress", "metric": f"{document_count} documents · {'plan ready' if plan else 'plan pending'}", "href": f"/properties/{prop.id}/floorplan" if prop else "/portfolio"},
        {"phase": "D", "title": "Underwriting orchestration", "description": "Rules and typed AI routing assemble missing items, exceptions, and an advisory scenario.", "status": "complete" if submission and submission.status != "draft" else "pending", "metric": submission.status.replace("_", " ") if submission else "not started", "href": "/underwriting"},
        {"phase": "E", "title": "Human terms checkpoint", "description": "A role-gated reviewer may approve demo terms; no model can bind coverage.", "status": "complete" if submission and submission.human_decision else "human_review", "metric": submission.human_decision.replace("_", " ") if submission and submission.human_decision else "review required", "href": "/tasks"},
        {"phase": "F", "title": "Hazard monitoring", "description": "Deterministic NASA/NOAA-style replay identifies potential exposure without asserting damage.", "status": "complete" if match_count else "ready", "metric": f"{match_count} potentially exposed sites", "href": "/hazards"},
        {"phase": "G", "title": "FNOL & triage", "description": "A synthetic notice of loss opens a claim and its reported exposure records.", "status": "complete" if claim else "pending", "metric": claim.claim_number if claim else "not reported", "href": f"/claims/{claim.id}" if claim else "/claims"},
        {"phase": "H", "title": "Evidence-led investigation", "description": "Claim evidence, contradictions, estimates, and human requests remain source-linked.", "status": "complete" if estimate_count else "needs_evidence", "metric": f"{estimate_count} estimate version(s)", "href": f"/claims/{claim.id}" if claim else "/claims"},
        {"phase": "I", "title": "Decision record & audit", "description": "Recommendations and authorized human outcomes are separated in a permanent timeline.", "status": "complete" if decision_count else "human_review", "metric": f"{decision_count} claim decision(s)", "href": "/audit"},
    ]
    return {"scenario": "NorthStar Manufacturing lifecycle", "synthetic": True, "prepared": bool(company and prop and submission and claim and hazard and plan), "phases": phases, "ids": {"company_id": company.id if company else None, "property_id": prop.id if prop else None, "submission_id": submission.id if submission else None, "claim_id": claim.id if claim else None, "hazard_id": hazard.id if hazard else None, "floorplan_id": plan.id if plan else None}, "guardrails": ["Potential exposure is not confirmed damage.", "Estimates are synthetic and not payable.", "Only recorded humans authorize demo outcomes."]}


@app.get("/api/demo/journey")
def demo_journey(db: Session = Depends(get_db)) -> dict[str, Any]:
    return demo_journey_out(db)


@app.post("/api/demo/prepare")
def prepare_demo(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Idempotently prepares the persisted demo trail without making human decisions."""
    submission = db.scalar(select(UnderwritingSubmission).order_by(UnderwritingSubmission.id))
    if submission and not db.scalar(select(WorkflowRun).where(WorkflowRun.subject_type == "underwriting", WorkflowRun.subject_id == submission.id)):
        run_underwriting(db, submission)
    hazard = db.scalar(select(HazardEvent).where(HazardEvent.provider_event_id == "REPLAY-SEVERE-2026-01"))
    if hazard:
        replay_hazard(db, hazard)
    claim = db.scalar(select(Claim).where(Claim.claim_number == "AR-CLM-1001"))
    if claim and not db.scalar(select(WorkflowRun).where(WorkflowRun.subject_type.in_(["claim", "claims"]), WorkflowRun.subject_id == claim.id)):
        run_claim(db, claim, "guided_demo")
    audit(db, None, "system", 0, "guided_demo_prepared", actor="demo_user", source="human", details={"idempotent": True, "human_decisions_created": 0})
    db.commit()
    return demo_journey_out(db)


@app.get("/api/companies")
def companies(limit: int = Query(50, le=100), offset: int = 0, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Company).order_by(Company.name).limit(limit).offset(offset)).all()
    return {"items": [company_out(c) | {"property_count": len(c.properties), "tiv_cents": sum(p.tiv_cents for p in c.properties)} for c in rows], "total": db.scalar(select(func.count()).select_from(Company))}


@app.post("/api/companies", status_code=201)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.scalar(select(Company).where(Company.name == payload.name)):
        raise HTTPException(409, "Company name already exists")
    row = Company(**payload.model_dump(), synthetic=True)
    db.add(row); db.flush(); audit(db, row.id, "company", row.id, "company_created", actor="demo_user", source="human", details={"synthetic": True}); db.commit()
    return company_out(row)


@app.get("/api/companies/{company_id}")
def company_detail(company_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(Company, company_id)
    if not row: raise HTTPException(404, "Company not found")
    return company_out(row) | {"properties": [property_out(p) for p in row.properties], "tiv_cents": sum(p.tiv_cents for p in row.properties)}


@app.get("/api/companies/{company_id}/properties")
def company_properties(company_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Company, company_id): raise HTTPException(404, "Company not found")
    return {"items": [property_out(p) for p in db.scalars(select(Property).where(Property.company_id == company_id)).all()]}


@app.get("/api/properties")
def properties(company_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Property).order_by(Property.name)
    if company_id: stmt = stmt.where(Property.company_id == company_id)
    return {"items": [property_out(p) for p in db.scalars(stmt).all()]}


@app.get("/api/properties/{property_id}")
def property_detail(property_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    prop = db.get(Property, property_id)
    if not prop: raise HTTPException(404, "Property not found")
    categories = db.scalars(select(RiskDataRecord).where(RiskDataRecord.property_id == prop.id).order_by(RiskDataRecord.category)).all()
    inspections = db.scalars(select(Inspection).where(Inspection.property_id == prop.id)).all()
    buildings = db.scalars(select(Building).where(Building.property_id == prop.id)).all()
    floorplans = db.scalars(select(FloorPlan).join(Floor).join(Building).where(Building.property_id == prop.id)).all()
    return property_out(prop) | {"company": company_out(db.get(Company, prop.company_id)), "risk_categories": [{"category": r.category, "name": r.category_name, "data": r.data, "source_type": r.source_type, "verification_status": r.verification_status, "observed_at": r.observed_at, "last_verified_at": r.last_verified_at, "revision": r.revision} for r in categories], "assets": [{"id": a.id, "asset_code": a.asset_code, "name": a.name, "asset_type": a.asset_type, "insured_value_cents": a.insured_value_cents, "status": a.status, "criticality": a.criticality} for a in prop.assets], "inspections": [{"id": i.id, "type": i.inspection_type, "status": i.status, "inspected_at": i.inspected_at, "expires_at": i.expires_at, "findings": [{"id": f.id, "finding": f.finding, "severity": f.severity, "status": f.status} for f in db.scalars(select(SafetyFinding).where(SafetyFinding.inspection_id == i.id)).all()]} for i in inspections], "floorplans": [{"id": f.id, "floor_id": f.floor_id, "name": f.name, "plan_type": f.plan_type, "is_base": f.is_base, "source_group": f.source_group, "state": f.state, "analysis_status": f.analysis_status, "analysis_model": f.analysis_model, "revision": f.revision, "media_type": f.media_type, "preview_url": f"/api/floorplans/{f.id}/preview"} for f in floorplans]}


@app.get("/api/properties/{property_id}/assets")
def property_assets(property_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Property, property_id): raise HTTPException(404, "Property not found")
    return {"items": [{"id": a.id, "asset_code": a.asset_code, "name": a.name, "asset_type": a.asset_type, "insured_value_cents": a.insured_value_cents, "criticality": a.criticality} for a in db.scalars(select(Asset).where(Asset.property_id == property_id)).all()]}


@app.get("/api/properties/{property_id}/evidence")
def property_evidence(property_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    prop = db.get(Property, property_id)
    if not prop: raise HTTPException(404, "Property not found")
    docs = db.scalars(select(Document).where(Document.property_id == property_id)).all()
    return {"documents": [document_out(d) for d in docs], "facts": [{"id": f.id, "document_id": f.document_id, "fact_type": f.fact_type, "value": f.value, "page_number": f.page_number, "evidence_location": f.evidence_location, "verified": f.verified} for f in db.scalars(select(EvidenceFact).where(EvidenceFact.subject_type == "property", EvidenceFact.subject_id == property_id)).all()]}


@app.post("/api/properties/{property_id}/inspection-request", status_code=201)
def request_property_inspection(property_id: int, object_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(404, "Property not found")
    if object_id:
        obj = db.get(FloorObject, object_id)
        if not obj or obj.floor_plan.floor.building.property_id != property_id:
            raise HTTPException(404, "Floor object not found for property")
    key = f"inspection-request:{property_id}:{object_id or 'site'}"
    task = db.scalar(select(ReviewTask).where(ReviewTask.idempotency_key == key))
    if not task:
        task = ReviewTask(company_id=prop.company_id, property_id=prop.id, subject_type="floor_object" if object_id else "property", subject_id=object_id or prop.id, kind="inspection_request", title=f"Review inspection request — {prop.name}", priority="medium", required_role="engineer", status="queued", details={"object_id": object_id, "source": "floor_plan_workspace", "human_authorization_required": True}, idempotency_key=key)
        db.add(task)
        db.flush()
        audit(db, prop.company_id, "task", task.id, "inspection_requested", actor="demo_user", source="human", details={"property_id": prop.id, "object_id": object_id})
        db.commit()
    return task_out(task)


@app.get("/api/policies/{policy_id}")
def policy_detail(policy_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    p = db.get(Policy, policy_id)
    if not p: raise HTTPException(404, "Policy not found")
    return {"id": p.id, "company_id": p.company_id, "property_id": p.property_id, "policy_number": p.policy_number, "status": p.status, "effective_at": p.effective_at, "expires_at": p.expires_at, "simulated": p.simulated, "coverages": [{"id": c.id, "coverage_type": c.coverage_type, "limit_cents": c.limit_cents, "deductible_cents": c.deductible_cents, "sublimit_cents": c.sublimit_cents, "excluded_perils": c.excluded_perils} for c in p.coverages], "disclaimer": "Simulated policy record; not bound coverage."}


@app.get("/api/policies")
def policies(property_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Policy).order_by(Policy.policy_number)
    if property_id is not None:
        stmt = stmt.where(Policy.property_id == property_id)
    return {"items": [{"id": p.id, "company_id": p.company_id, "property_id": p.property_id, "policy_number": p.policy_number, "status": p.status, "effective_at": p.effective_at, "expires_at": p.expires_at, "simulated": p.simulated} for p in db.scalars(stmt).all()]}


@app.post("/api/ingest/sov")
async def ingest_sov(company_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    company = db.get(Company, company_id)
    if not company: raise HTTPException(404, "Company not found")
    saved = await save_upload(file, settings.upload_dir / "sov", settings.max_upload_bytes)
    frame = parse_sov(saved.path, saved.media_type)
    result = import_sov(db, company, frame)
    doc = Document(company_id=company.id, filename=saved.original_name, media_type=saved.media_type, classification="sov", storage_path=str(saved.path), sha256=saved.sha256, size_bytes=saved.size, uploader="demo_user", source_mode="synthetic_or_user_supplied")
    db.add(doc); db.flush(); audit(db, company.id, "company", company.id, "sov_imported", actor="demo_user", source="upload", details=result | {"document_id": doc.id}); db.commit()
    return result | {"document": document_out(doc)}


@app.get("/api/demo/fixtures/sov")
def demo_sov_fixture():
    path = Path(__file__).parent / "seed" / "fixtures" / "synthetic_sov.csv"
    if not path.is_file():
        raise HTTPException(404, "Synthetic SOV fixture not found")
    return FileResponse(path, media_type="text/csv", filename="property2claim-sov.csv")


@app.post("/api/ingest/document")
async def ingest_document(company_id: int = Form(...), property_id: int | None = Form(None), classification: str = Form("evidence"), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    company = db.get(Company, company_id)
    prop = db.get(Property, property_id) if property_id else None
    if not company: raise HTTPException(404, "Company not found")
    if property_id and (not prop or prop.company_id != company_id): raise HTTPException(404, "Property not found for company")
    saved = await save_upload(file, settings.upload_dir / "documents", settings.max_upload_bytes)
    doc = Document(company_id=company_id, property_id=property_id, filename=saved.original_name, media_type=saved.media_type, classification=classification, storage_path=str(saved.path), sha256=saved.sha256, size_bytes=saved.size, uploader="demo_user", source_mode="synthetic_or_user_supplied")
    db.add(doc); db.flush()
    facts = extract_pdf_facts(db, doc.id, saved.path, "property" if property_id else "company", property_id or company_id) if saved.media_type == "application/pdf" else []
    doc.analysis_status = "completed_text_extraction" if saved.media_type == "application/pdf" else "not_applicable"
    audit(db, company_id, "document", doc.id, "document_ingested", actor="demo_user", source="upload", details={"fact_count": len(facts), "classification": classification}); db.commit()
    return {"document": document_out(doc), "facts": [{"id": f.id, "page_number": f.page_number, "evidence_location": f.evidence_location, "value": f.value} for f in facts]}


@app.get("/api/documents/{document_id}")
def document_detail(document_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(404, "Document not found")
    page_count = None
    if doc.media_type == "application/pdf" and Path(doc.storage_path).is_file():
        with fitz.open(doc.storage_path) as pdf:
            page_count = len(pdf)
    return document_out(doc) | {"page_count": page_count, "preview_url": f"/api/documents/{doc.id}/preview", "facts": [{"id": f.id, "fact_type": f.fact_type, "value": f.value, "page_number": f.page_number, "timestamp_seconds": f.timestamp_seconds, "evidence_location": f.evidence_location, "verified": f.verified} for f in db.scalars(select(EvidenceFact).where(EvidenceFact.document_id == doc.id).order_by(EvidenceFact.id)).all()]}


@app.get("/api/documents/{document_id}/content")
def document_content(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc or not Path(doc.storage_path).is_file(): raise HTTPException(404, "Document content not found")
    return FileResponse(doc.storage_path, media_type=doc.media_type, filename=doc.filename)


@app.get("/api/documents/{document_id}/preview")
def document_preview(document_id: int, page: int = Query(1, ge=1, le=500), db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc or not Path(doc.storage_path).is_file():
        raise HTTPException(404, "Document preview not found")
    if doc.media_type.startswith("image/"):
        return FileResponse(doc.storage_path, media_type=doc.media_type)
    if doc.media_type != "application/pdf":
        raise HTTPException(415, "Preview rendering is available for PDF and image evidence")
    with fitz.open(doc.storage_path) as pdf:
        if page > len(pdf):
            raise HTTPException(404, "PDF page not found")
        pixmap = pdf[page - 1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        return Response(content=pixmap.tobytes("png"), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/underwriting")
def underwriting_list(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": [underwriting_out(x) for x in db.scalars(select(UnderwritingSubmission).order_by(desc(UnderwritingSubmission.created_at))).all()]}


def underwriting_out(x: UnderwritingSubmission) -> dict[str, Any]:
    return {"id": x.id, "company_id": x.company_id, "property_id": x.property_id, "status": x.status, "completeness": x.completeness, "missing_items": x.missing_items, "exceptions": x.exceptions, "route": x.route, "decision_source": x.decision_source, "premium_scenario_cents": x.premium_scenario_cents, "human_decision": x.human_decision, "created_at": x.created_at, "disclaimer": "Synthetic illustrative premium; not a quote or binding decision."}


@app.post("/api/underwriting/submissions", status_code=201)
def create_underwriting(payload: UnderwritingCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    prop = db.get(Property, payload.property_id)
    if not prop or prop.company_id != payload.company_id: raise HTTPException(404, "Property not found for company")
    row = UnderwritingSubmission(**payload.model_dump(), status="draft")
    db.add(row); db.flush(); audit(db, row.company_id, "underwriting", row.id, "submission_created", actor="demo_user", source="human", details={}); db.commit()
    return underwriting_out(row)


@app.post("/api/underwriting/{submission_id}/run")
def run_underwriting_route(submission_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(UnderwritingSubmission, submission_id)
    if not row: raise HTTPException(404, "Submission not found")
    return underwriting_out(run_underwriting(db, row))


@app.get("/api/underwriting/{submission_id}")
def underwriting_detail(submission_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(UnderwritingSubmission, submission_id)
    if not row: raise HTTPException(404, "Submission not found")
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.workflow_type == "underwriting_graph", WorkflowRun.subject_id == row.id).order_by(desc(WorkflowRun.id)))
    workflow = None if not run else {"id": run.id, "status": run.status, "steps": run.state.get("steps", []), "route": run.state.get("route"), "missing_items": run.state.get("missing_items", []), "provider": run.provider_metadata.get("provider"), "decision_source": run.provider_metadata.get("decision_source"), "created_at": run.created_at}
    return underwriting_out(row) | {"tasks": [task_out(t) for t in db.scalars(select(ReviewTask).where(ReviewTask.subject_type == "underwriting", ReviewTask.subject_id == row.id)).all()], "workflow": workflow}


@app.post("/api/policies/demo-issue")
def issue_demo_policy(payload: DemoIssueRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    submission = db.get(UnderwritingSubmission, payload.submission_id)
    if not submission: raise HTTPException(404, "Submission not found")
    if submission.status not in {"ready_for_underwriter", "terms_approved_demo"} or payload.actor_role not in {"underwriter", "supervisor"}: raise HTTPException(409, "Authorized human-reviewed ready submission required")
    existing = db.scalar(select(Policy).where(Policy.policy_number.like(f"DEMO-ISSUED-{submission.id}-%")))
    if existing:
        return {"id": existing.id, "policy_number": existing.policy_number, "status": existing.status, "simulated": True, "idempotent": True, "disclaimer": "Demo record only; no policy was bound."}
    prop = db.get(Property, submission.property_id)
    policy = Policy(company_id=submission.company_id, property_id=prop.id, policy_number=f"DEMO-ISSUED-{submission.id}-{uuid4().hex[:6]}", status="demo_active", effective_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1), simulated=True)
    db.add(policy); db.flush(); db.add(Coverage(policy_id=policy.id, coverage_type="commercial_property", limit_cents=prop.building_value_cents + prop.equipment_value_cents + prop.contents_value_cents, deductible_cents=250_000_00, excluded_perils=[])); submission.status = "approved_demo"; submission.human_decision = "approve_demo_terms"
    audit(db, submission.company_id, "policy", policy.id, "simulated_policy_issued", actor=payload.actor, source="human", details={"submission_id": submission.id, "not_bound": True}); db.commit()
    return {"id": policy.id, "policy_number": policy.policy_number, "status": policy.status, "simulated": True, "disclaimer": "Demo record only; no policy was bound."}


@app.get("/api/hazards")
def hazards(db: Session = Depends(get_db)) -> dict[str, Any]:
    events = db.scalars(select(HazardEvent).order_by(desc(HazardEvent.valid_at))).all()
    return {"items": [{"id": e.id, "provider": e.provider, "provider_event_id": e.provider_event_id, "event_type": e.event_type, "title": e.title, "severity": e.severity, "geometry": e.geometry, "valid_at": e.valid_at, "fetched_at": e.fetched_at, "source_mode": e.source_mode, "matches": [{"property_id": m.property_id, "distance_km": float(m.distance_km), "exposed_value_cents": m.exposed_value_cents, "status": m.status} for m in db.scalars(select(PropertyHazardMatch).where(PropertyHazardMatch.hazard_event_id == e.id)).all()]} for e in events], "warning": "Hazard proximity indicates potential exposure only; it does not confirm damage or create a claim."}


@app.post("/api/hazards/replay/{scenario}")
def replay(scenario: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if scenario != "severe-weather-two-sites": raise HTTPException(404, "Unknown replay scenario")
    event = db.scalar(select(HazardEvent).where(HazardEvent.provider_event_id == "REPLAY-SEVERE-2026-01"))
    rows = replay_hazard(db, event)
    return {"event_id": event.id, "matched_property_ids": sorted(m.property_id for m in rows), "match_count": len(rows), "claims_created": 0, "source_mode": event.source_mode, "label": "potential exposure only"}


@app.post("/api/hazards/refresh")
def refresh_hazards(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not settings.allow_live_hazards: return {"status": "disabled", "mode": "replay_available", "errors": [], "imported": 0}
    events, errors = fetch_live_hazards(settings.noaa_user_agent, settings.nasa_firms_map_key)
    imported = 0
    created: list[HazardEvent] = []
    for item in events:
        if not item["provider_event_id"] or db.scalar(select(HazardEvent).where(HazardEvent.provider_event_id == item["provider_event_id"])): continue
        event = HazardEvent(**item)
        db.add(event); created.append(event); imported += 1
    db.flush()
    matched = 0
    for event in created:
        matched += len(replay_hazard(db, event))
    db.commit()
    return {"status": "completed_with_errors" if errors else "completed", "mode": "live", "errors": errors, "imported": imported, "property_matches": matched}


@app.get("/api/claims")
def claims(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": [claim_out(c, db) for c in db.scalars(select(Claim).order_by(desc(Claim.reported_at))).all()]}


@app.post("/api/claims/fnol", status_code=201)
def fnol(payload: FNOLCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    prop = db.get(Property, payload.property_id); policy = db.get(Policy, payload.policy_id)
    if not prop or prop.company_id != payload.company_id or not policy or policy.company_id != payload.company_id or policy.property_id != payload.property_id: raise HTTPException(404, "Property or policy not found for company")
    claim = Claim(company_id=payload.company_id, property_id=payload.property_id, policy_id=payload.policy_id, claim_number=f"AR-CLM-{datetime.now().strftime('%y%m%d')}-{uuid4().hex[:6].upper()}", loss_at=payload.loss_at, peril=payload.peril, narrative=payload.narrative, status="reported", incident_geometry=payload.incident_geometry, synthetic=True)
    db.add(claim); db.flush()
    for exposure in payload.reported_exposures: db.add(ClaimExposure(claim_id=claim.id, exposure_type=exposure, state="reported"))
    audit(db, claim.company_id, "claim", claim.id, "fnol_created", actor="demo_user", source="human", details={"hazard_generated": False, "synthetic": True}); db.commit()
    run_claim(db, claim, "fnol")
    return claim_out(claim, db, True)


@app.get("/api/claims/{claim_id}")
def claim_detail(claim_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    claim = db.get(Claim, claim_id)
    if not claim: raise HTTPException(404, "Claim not found")
    return claim_out(claim, db, True)


@app.post("/api/claims/{claim_id}/run-investigation")
def investigate(claim_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    claim = db.get(Claim, claim_id)
    if not claim: raise HTTPException(404, "Claim not found")
    return claim_out(run_claim(db, claim, "manual_rerun"), db, True)


@app.post("/api/claims/{claim_id}/evidence")
async def claim_evidence(claim_id: int, classification: str = Form("claim_evidence"), amount_cents: int | None = Form(None), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    claim = db.get(Claim, claim_id)
    if not claim: raise HTTPException(404, "Claim not found")
    saved = await save_upload(file, settings.upload_dir / "claims" / str(claim_id), settings.max_upload_bytes)
    doc = Document(company_id=claim.company_id, property_id=claim.property_id, claim_id=claim.id, filename=saved.original_name, media_type=saved.media_type, classification=classification, storage_path=str(saved.path), sha256=saved.sha256, size_bytes=saved.size, uploader="demo_user", source_mode="synthetic_or_user_supplied")
    db.add(doc); db.flush(); facts = []
    if saved.media_type == "application/pdf": facts.extend(extract_pdf_facts(db, doc.id, saved.path, "claim", claim.id))
    if amount_cents is not None:
        if amount_cents <= 0: raise HTTPException(422, "amount_cents must be positive")
        fact = EvidenceFact(document_id=doc.id, subject_type="claim", subject_id=claim.id, fact_type="repair_quote", value={"amount_cents": amount_cents, "currency": "USD"}, evidence_location="user supplied quote amount", verified=False)
        db.add(fact); facts.append(fact)
    doc.analysis_status = "completed_text_extraction" if saved.media_type == "application/pdf" else "completed_structured_input"
    audit(db, claim.company_id, "claim", claim.id, "evidence_uploaded", actor="demo_user", source="upload", details={"document_id": doc.id, "classification": classification, "fact_count": len(facts)}); db.commit()
    run_claim(db, claim, "evidence_uploaded")
    return {"document": document_out(doc), "claim": claim_out(claim, db, True)}


@app.post("/api/claims/{claim_id}/media")
async def claim_media(claim_id: int, authorize_external_analysis: bool = Form(False), frame_interval_seconds: int = Form(10), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    claim = db.get(Claim, claim_id)
    if not claim: raise HTTPException(404, "Claim not found")
    saved = await save_upload(file, settings.upload_dir / "media" / str(claim_id), min(settings.max_upload_bytes, 25 * 1024 * 1024))
    if not saved.media_type.startswith(("image/", "video/")): raise HTTPException(415, "Claim media endpoint accepts image or MP4 video")
    doc = Document(company_id=claim.company_id, property_id=claim.property_id, claim_id=claim.id, filename=saved.original_name, media_type=saved.media_type, classification="claim_media", storage_path=str(saved.path), sha256=saved.sha256, size_bytes=saved.size, uploader="demo_user", source_mode="synthetic_or_user_supplied", analysis_status="pending_user_authorization" if settings.gemini_api_key else "mock_schema_only")
    db.add(doc); db.flush(); audit(db, claim.company_id, "claim", claim.id, "media_uploaded_no_findings", actor="demo_user", source="upload", details={"document_id": doc.id, "external_analysis_authorized": authorize_external_analysis}); db.commit()
    service = MediaAnalysisService(settings)
    if authorize_external_analysis:
        try:
            analysis = service.analyze_video(doc.id, saved.path, FrameSamplingConfig(interval_seconds=frame_interval_seconds), explicitly_authorized=True) if saved.media_type == "video/mp4" else service.analyze_image(doc.id, saved.path, explicitly_authorized=True)
            observation_count = persist_media_observations(db, doc, analysis)
            doc.analysis_status = "completed_requires_human_verification" if observation_count else "completed_no_observations"
            audit(db, claim.company_id, "claim", claim.id, "media_analysis_completed", actor="media_analysis_service", source=analysis.get("mode", "mixed"), details={"document_id": doc.id, "observation_count": observation_count, "human_verification_required": True}); db.commit()
        except Exception as exc:
            doc.analysis_status = f"analysis_error_{type(exc).__name__}"[:40]
            audit(db, claim.company_id, "claim", claim.id, "media_analysis_failed", actor="media_analysis_service", source="provider_error", details={"document_id": doc.id, "error_type": type(exc).__name__, "retry_available": True}); db.commit()
            analysis = {"media_id": doc.id, "observations": [], "mode": "error", "limitations": ["Provider analysis failed; the original file was retained for review."], "error_type": type(exc).__name__}
    else:
        analysis = MockVisionModel().analyze(doc.id)
    return {"document": document_out(doc), "analysis_contract": analysis, "validation": "PENDING_USER_FIXTURES", "real_analysis_performed": analysis.get("mode") == "live" or any(item.get("mode") == "live" for item in analysis.get("analyses", []))}


@app.post("/api/documents/{document_id}/reprocess")
def reprocess_media(document_id: int, authorize_external_analysis: bool = Form(False), frame_interval_seconds: int = Form(10), db: Session = Depends(get_db)) -> dict[str, Any]:
    doc = db.get(Document, document_id)
    if not doc or not doc.claim_id:
        raise HTTPException(404, "Claim media not found")
    if not doc.media_type.startswith(("image/", "video/")):
        raise HTTPException(415, "Only image or video evidence can use vision reprocessing")
    if not authorize_external_analysis:
        raise HTTPException(409, "Explicit external-analysis authorization is required")
    path = Path(doc.storage_path)
    if not path.is_file():
        raise HTTPException(404, "Original media is unavailable")
    claim = db.get(Claim, doc.claim_id)
    service = MediaAnalysisService(settings)
    try:
        analysis = service.analyze_video(doc.id, path, FrameSamplingConfig(interval_seconds=frame_interval_seconds), explicitly_authorized=True) if doc.media_type == "video/mp4" else service.analyze_image(doc.id, path, explicitly_authorized=True)
        observation_count = persist_media_observations(db, doc, analysis)
        doc.analysis_status = "completed_requires_human_verification" if observation_count else "completed_no_observations"
        audit(db, doc.company_id, "claim", doc.claim_id, "media_selectively_reprocessed", actor="demo_user", source=analysis.get("mode", "mixed"), details={"document_id": doc.id, "observation_count": observation_count, "affected_steps": ["media_vision", "evidence_index"], "claim_graph_rerun": False})
        db.commit()
        return {"document": document_out(doc), "analysis_contract": analysis, "affected_steps": ["media_vision", "evidence_index"], "claim_graph_rerun": False}
    except HTTPException:
        raise
    except Exception as exc:
        doc.analysis_status = f"analysis_error_{type(exc).__name__}"[:40]
        audit(db, doc.company_id, "claim", doc.claim_id, "media_reprocessing_failed", actor="demo_user", source="provider_error", details={"document_id": doc.id, "error_type": type(exc).__name__})
        db.commit()
        raise HTTPException(502, f"Media provider failed safely: {type(exc).__name__}") from exc


@app.post("/api/claims/{claim_id}/estimate")
def estimate_claim(claim_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    claim = db.get(Claim, claim_id)
    if not claim: raise HTTPException(404, "Claim not found")
    estimate = create_estimate(db, claim); db.commit(); return estimate_out(estimate, db)


@app.get("/api/claims/{claim_id}/estimates")
def estimates(claim_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(Claim, claim_id): raise HTTPException(404, "Claim not found")
    return {"items": [estimate_out(e, db) for e in db.scalars(select(LossEstimate).where(LossEstimate.claim_id == claim_id).order_by(LossEstimate.version)).all()]}


@app.get("/api/tasks")
def tasks(status: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(ReviewTask).order_by(desc(ReviewTask.created_at))
    if status: stmt = stmt.where(ReviewTask.status == status)
    return {"items": [task_out(t) for t in db.scalars(stmt).all()]}


def workflow_result_out(run: WorkflowRun, db: Session) -> dict[str, Any]:
    subject_type = "claim" if run.subject_type in {"claim", "claims"} else run.subject_type
    company: Company | None = None
    prop: Property | None = None
    claim: Claim | None = None
    submission: UnderwritingSubmission | None = None
    subject_status = run.status
    outcome: str | None = None
    if subject_type == "claim":
        claim = db.get(Claim, run.subject_id)
        if claim:
            company = db.get(Company, claim.company_id)
            prop = db.get(Property, claim.property_id)
            subject_status = claim.status
            outcome = claim.status
    elif subject_type == "underwriting":
        submission = db.get(UnderwritingSubmission, run.subject_id)
        if submission:
            company = db.get(Company, submission.company_id)
            prop = db.get(Property, submission.property_id)
            subject_status = submission.status
            outcome = submission.human_decision or submission.status
    elif subject_type == "hazard":
        event = db.get(HazardEvent, run.subject_id)
        subject_status = "potential_exposure_review"
        outcome = "potential exposure only"
        matches = db.scalars(select(PropertyHazardMatch).where(PropertyHazardMatch.hazard_event_id == run.subject_id)).all()
        if len(matches) == 1:
            prop = db.get(Property, matches[0].property_id)
            company = db.get(Company, prop.company_id) if prop else None
        if event:
            outcome = f"{len(matches)} site(s) require exposure review"
    elif subject_type == "floorplan":
        plan = db.get(FloorPlan, run.subject_id)
        if plan:
            prop = db.get(Property, plan.floor.building.property_id)
            company = db.get(Company, prop.company_id) if prop else None
            subject_status = plan.state
            outcome = f"{len(plan.objects)} proposals require verification"

    task_subject_types = {subject_type}
    if subject_type == "claim":
        task_subject_types.add("claims")
    tasks_for_run = db.scalars(select(ReviewTask).where(ReviewTask.subject_type.in_(task_subject_types), ReviewTask.subject_id == run.subject_id).order_by(ReviewTask.created_at)).all()
    decisions = db.scalars(select(HumanDecision).where(HumanDecision.task_id.in_([task.id for task in tasks_for_run])).order_by(HumanDecision.created_at)).all() if tasks_for_run else []
    missing_items = list(run.state.get("missing_items", []))
    if subject_status in {"waiting_evidence", "needs_info"} and missing_items:
        queue = "needs_evidence"
    elif decisions and all(task.status not in {"queued", "waiting"} for task in tasks_for_run):
        queue = "completed"
    else:
        queue = "human_review"

    audit_subject = "claim" if subject_type == "claim" else subject_type
    events = db.scalars(select(AuditEvent).where(AuditEvent.subject_type == audit_subject, AuditEvent.subject_id == run.subject_id).order_by(AuditEvent.created_at)).all()
    step_summaries = {
        "collect": "Collected the linked account, property, and submission inputs.", "parse": "Normalized available structured and document-derived fields.", "validate": "Checked required fields and source consistency.", "cope": "Evaluated construction, occupancy, protection, and exposure context.", "jev_route": "Selected a bounded work queue; this is not an insurance verdict.", "draft_request": "Prepared a missing-evidence request for human authorization.", "pricing_scenario": "Calculated a synthetic, non-binding premium scenario.", "fnol": "Loaded the reported loss narrative and exposure types.", "check_policy": "Linked the synthetic policy and limits without resolving coverage.", "extract_evidence": "Loaded linked documents and extracted source facts.", "spatial_candidates": "Associated possible site and floor-plan context.", "reconcile": "Compared dates, facts, and outstanding contradictions.", "specialist_review": "Routed the case to the appropriate human specialist queue.", "estimate": "Calculated a versioned illustrative loss estimate from cited inputs.", "human_checkpoint": "Stopped for a role-gated human action.", "audit": "Persisted the run state and provenance trail.", "ingest_event": "Loaded the hazard event from its named source.", "normalize": "Converted provider data to the canonical hazard schema.", "match_locations": "Compared event geometry with insured-site coordinates.", "rank_attention": "Prioritized potentially exposed sites without asserting damage.", "draft_tasks": "Created review tasks; no claim was opened automatically.", "record": "Saved the replay result and source mode.",
    }
    route_provider = run.provider_metadata.get("decision_source", run.provider_metadata.get("provider", "deterministic rules"))
    workflow_steps = []
    for index, step in enumerate(run.state.get("steps", [])):
        source = route_provider if step == "jev_route" else "deterministic calculation" if step in {"pricing_scenario", "estimate", "match_locations"} else "LangGraph orchestration"
        workflow_steps.append({"kind": "workflow_step", "label": step, "timestamp": run.created_at, "actor": run.workflow_type, "source": source, "summary": step_summaries.get(step, "Persisted workflow stage completed."), "confidence": None, "details": {"sequence": index + 1, "timing_precision": "run-level", "route": run.state.get("route") if step == "jev_route" else None, "missing_items": run.state.get("missing_items", []) if step in {"validate", "draft_request", "reconcile"} else []}})
    audit_steps = [{"kind": "audit_event", "label": event.event_type, "timestamp": event.created_at, "actor": event.actor, "source": event.source, "details": event.details, "old_state": event.old_state, "new_state": event.new_state} for event in events]
    timeline = sorted(workflow_steps + audit_steps, key=lambda item: item["timestamp"])

    documents_stmt = select(Document)
    if claim:
        documents_stmt = documents_stmt.where((Document.claim_id == claim.id) | (Document.property_id == claim.property_id))
    elif prop:
        documents_stmt = documents_stmt.where(Document.property_id == prop.id)
    else:
        documents_stmt = documents_stmt.where(Document.id == -1)
    documents = db.scalars(documents_stmt.order_by(Document.created_at.desc())).all()
    evidence = []
    for document in documents:
        facts = db.scalars(select(EvidenceFact).where(EvidenceFact.document_id == document.id)).all()
        evidence.append(document_out(document) | {"content_url": f"/api/documents/{document.id}/content", "facts": [{"id": fact.id, "fact_type": fact.fact_type, "value": fact.value, "page_number": fact.page_number, "timestamp_seconds": fact.timestamp_seconds, "evidence_location": fact.evidence_location, "verified": fact.verified} for fact in facts]})

    estimates = []
    financials = None
    if claim:
        estimates = [estimate_out(estimate, db) for estimate in db.scalars(select(LossEstimate).where(LossEstimate.claim_id == claim.id).order_by(LossEstimate.version)).all()]
        policy = db.get(Policy, claim.policy_id)
        coverage = db.scalar(select(Coverage).where(Coverage.policy_id == policy.id, Coverage.coverage_type == "commercial_property")) if policy else None
        latest = estimates[-1] if estimates else None
        financials = {
            "gross_estimated_loss_cents": latest["gross_cents"] if latest else None,
            "calculation_method": latest["method"] if latest else None,
            "deductible_cents": latest["deductible_cents"] if latest else (coverage.deductible_cents if coverage else None),
            "policy_limit_cents": coverage.limit_cents if coverage else None,
            "illustrative_eligible_cents": latest["illustrative_eligible_cents"] if latest else None,
            "reserve_proposal_cents": latest["reserve_suggestion_cents"] if latest else None,
            "reviewed_reserve_cents": latest["reserve_suggestion_cents"] if latest and any(d.action == "approve_reserve_review" for d in decisions) else None,
            "proposed_payment_cents": None,
            "authorized_payment_cents": None,
            "payment_status": "not proposed or authorized",
        }
    return {
        "id": run.id,
        "workflow_type": run.workflow_type,
        "subject_type": subject_type,
        "subject_id": run.subject_id,
        "trigger": run.trigger,
        "queue": queue,
        "status": subject_status,
        "outcome": outcome,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "company": {"id": company.id, "name": company.name} if company else None,
        "property": {"id": prop.id, "name": prop.name, "site_code": prop.site_code} if prop else None,
        "claim": {"id": claim.id, "claim_number": claim.claim_number, "peril": claim.peril, "status": claim.status} if claim else None,
        "state": run.state,
        "provider_metadata": run.provider_metadata,
        "missing_items": missing_items,
        "tasks": [task_out(task) for task in tasks_for_run],
        "decisions": [{"id": decision.id, "task_id": decision.task_id, "actor": decision.actor, "actor_role": decision.actor_role, "action": decision.action, "rationale": decision.rationale, "state_before": decision.state_before, "state_after": decision.state_after, "created_at": decision.created_at} for decision in decisions],
        "timeline": timeline,
        "evidence": evidence,
        "estimates": estimates,
        "financials": financials,
        "contradictions": [claim.contradiction_summary] if claim and claim.contradiction_summary else list(run.state.get("conflicts", [])),
        "unresolved_coverage_questions": ["Coverage interpretation remains outside model authority and requires a qualified human review."] if claim else [],
        "recommendation_only": not bool(decisions),
        "authorized_outcome": decisions[-1].action if decisions else None,
    }


@app.get("/api/workflows/results")
def workflow_results(queue: str | None = None, workflow_type: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(WorkflowRun).order_by(desc(WorkflowRun.updated_at), desc(WorkflowRun.id))
    if workflow_type:
        stmt = stmt.where(WorkflowRun.workflow_type == workflow_type)
    items = [workflow_result_out(run, db) for run in db.scalars(stmt).all()]
    if queue:
        items = [item for item in items if item["queue"] == queue]
    counts = {name: sum(item["queue"] == name for item in items) for name in ["needs_evidence", "human_review", "completed"]}
    durations = [max(0.0, (run.updated_at - run.created_at).total_seconds()) for run in db.scalars(stmt).all()]
    claim_items = [item for item in items if item["subject_type"] == "claim" and item["financials"]]
    return {"items": items, "counts": counts, "summary": {"average_processing_seconds": round(sum(durations) / len(durations), 2) if durations else 0, "workflow_types": {name: sum(item["workflow_type"] == name for item in items) for name in sorted({item["workflow_type"] for item in items})}, "claim_gross_estimate_cents": sum(item["financials"]["gross_estimated_loss_cents"] or 0 for item in claim_items), "claim_reviewed_reserve_cents": sum(item["financials"]["reviewed_reserve_cents"] or 0 for item in claim_items)}, "labels": {"recommendations": "Model and rule output is advisory", "authorized": "Only recorded human decisions are authorized demo outcomes"}}


@app.get("/api/workflows/results/{run_id}")
def workflow_result_detail(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(404, "Workflow run not found")
    return workflow_result_out(run, db)


@app.post("/api/tasks/{task_id}/decision")
def task_decision(task_id: int, payload: TaskDecisionCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if not task: raise HTTPException(404, "Task not found")
    decision = decide_task(db, task, payload.actor, payload.actor_role, payload.action, payload.rationale)
    return {"id": decision.id, "task_id": decision.task_id, "actor": decision.actor, "actor_role": decision.actor_role, "action": decision.action, "rationale": decision.rationale, "state_before": decision.state_before, "state_after": decision.state_after, "created_at": decision.created_at, "simulation_only": payload.action == "authorize_settlement_simulation"}


@app.get("/api/audit")
def audit_events(subject_type: str | None = None, subject_id: int | None = None, limit: int = Query(100, le=250), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(limit)
    if subject_type: stmt = stmt.where(AuditEvent.subject_type == subject_type)
    if subject_id is not None: stmt = stmt.where(AuditEvent.subject_id == subject_id)
    return {"items": [{"id": e.id, "company_id": e.company_id, "subject_type": e.subject_type, "subject_id": e.subject_id, "event_type": e.event_type, "actor": e.actor, "source": e.source, "details": e.details, "old_state": e.old_state, "new_state": e.new_state, "created_at": e.created_at} for e in db.scalars(stmt).all()]}


async def _create_floorplan_record(
    prop: Property,
    floor_name: str,
    file: UploadFile,
    db: Session,
    *,
    plan_type: str = "base",
    name: str = "Original plan",
    source_group: str | None = None,
    is_base: bool = False,
) -> FloorPlan:
    saved = await save_upload(file, settings.upload_dir / "floorplans" / str(prop.id), settings.max_upload_bytes)
    if saved.media_type not in {"application/pdf", "image/png", "image/jpeg"}:
        raise HTTPException(415, "Floor plans must be PDF, PNG, or JPEG")
    doc = Document(company_id=prop.company_id, property_id=prop.id, filename=saved.original_name, media_type=saved.media_type, classification=f"floor_plan_{plan_type}", storage_path=str(saved.path), sha256=saved.sha256, size_bytes=saved.size, uploader="demo_user", source_mode="user_supplied", analysis_status="not_requested")
    db.add(doc)
    db.flush()
    building = db.scalar(select(Building).where(Building.property_id == prop.id))
    if not building:
        building = Building(property_id=prop.id, name="Main Building")
        db.add(building)
        db.flush()
    floor = db.scalar(select(Floor).where(Floor.building_id == building.id, Floor.name == floor_name))
    if not floor:
        floor = Floor(building_id=building.id, name=floor_name, level=1)
        db.add(floor)
        db.flush()
    preview_path = str(saved.path)
    width = height = None
    try:
        if saved.media_type == "application/pdf":
            pdf = fitz.open(saved.path)
            page = pdf[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            preview = saved.path.with_suffix(".preview.png")
            pix.save(preview)
            preview_path = str(preview)
            width, height = pix.width, pix.height
            pdf.close()
        else:
            pix = fitz.Pixmap(str(saved.path))
            width, height = pix.width, pix.height
    except Exception as exc:
        raise HTTPException(415, "Floor-plan image or PDF could not be decoded") from exc
    plan = FloorPlan(
        floor_id=floor.id,
        original_document_id=doc.id,
        preview_path=preview_path,
        media_type=saved.media_type,
        width=width,
        height=height,
        state="uploaded",
        name=name,
        plan_type=plan_type,
        is_base=is_base,
        source_group=source_group,
        analysis_status="not_requested",
        analysis_summary={},
    )
    db.add(plan)
    db.flush()
    audit(db, prop.company_id, "floorplan", plan.id, "floorplan_uploaded", actor="demo_user", source="upload", details={"property_id": prop.id, "plan_type": plan_type, "source_group": source_group, "vision_validation": "REQUIRES_HUMAN_REVIEW"})
    return plan


@app.post("/api/properties/{property_id}/floorplans", status_code=201)
async def upload_floorplan(property_id: int, floor_name: str = Form("Ground Floor"), plan_type: str = Form("base"), name: str = Form("Original plan"), file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(404, "Property not found")
    if plan_type not in {"base", "machinery", "emergency", "reference"}:
        raise HTTPException(422, "Unsupported plan type")
    group = f"upload-{uuid4()}"
    plan = await _create_floorplan_record(prop, floor_name, file, db, plan_type=plan_type, name=name, source_group=group, is_base=True)
    db.commit()
    return floorplan_out(plan, db)


@app.post("/api/properties/{property_id}/floorplans/batch", status_code=201)
async def upload_floorplan_batch(
    property_id: int,
    floor_name: str = Form("Ground Floor"),
    plan_types: str = Form(...),
    plan_names: str = Form("[]"),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(404, "Property not found")
    try:
        roles = json.loads(plan_types)
        names = json.loads(plan_names)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "plan_types and plan_names must be JSON arrays") from exc
    if not isinstance(roles, list) or len(roles) != len(files) or not 1 <= len(files) <= 8:
        raise HTTPException(422, "Provide one plan type for each file (maximum 8)")
    if any(role not in {"base", "machinery", "emergency", "reference"} for role in roles):
        raise HTTPException(422, "Unsupported plan type")
    if roles.count("base") != 1:
        raise HTTPException(422, "Exactly one uploaded drawing must be the base plan")
    group = f"upload-{uuid4()}"
    plans: list[FloorPlan] = []
    for index, (file, role) in enumerate(zip(files, roles, strict=True)):
        label = names[index] if isinstance(names, list) and index < len(names) and names[index] else f"{role.replace('_', ' ').title()} plan"
        plans.append(await _create_floorplan_record(prop, floor_name, file, db, plan_type=role, name=str(label)[:160], source_group=group, is_base=role == "base"))
    db.commit()
    base_plan = next(plan for plan in plans if plan.is_base)
    return {"source_group": group, "base_plan_id": base_plan.id, "plans": [floorplan_out(plan, db) for plan in plans]}


def floorplan_out(plan: FloorPlan, db: Session) -> dict[str, Any]:
    related = db.scalars(select(FloorPlan).where(FloorPlan.source_group == plan.source_group).order_by(FloorPlan.id)).all() if plan.source_group else [plan]
    property_id = plan.floor.building.property_id
    prop = db.get(Property, property_id)
    claims = db.scalars(select(Claim).where(Claim.property_id == property_id).order_by(desc(Claim.reported_at))).all()
    return {
        "id": plan.id,
        "floor_id": plan.floor_id,
        "property_id": property_id,
        "property_name": prop.name if prop else "Property",
        "original_document_id": plan.original_document_id,
        "name": plan.name,
        "plan_type": plan.plan_type,
        "is_base": plan.is_base,
        "source_group": plan.source_group,
        "preview_url": f"/api/floorplans/{plan.id}/preview",
        "media_type": plan.media_type,
        "width": plan.width,
        "height": plan.height,
        "revision": plan.revision,
        "coordinate_system": plan.coordinate_system,
        "state": plan.state,
        "analysis_status": plan.analysis_status,
        "analysis_model": plan.analysis_model,
        "analyzed_at": plan.analyzed_at,
        "analysis_summary": plan.analysis_summary or {},
        "objects": [floor_object_out(o, db) for o in plan.objects],
        "related_plans": [{"id": item.id, "name": item.name, "plan_type": item.plan_type, "is_base": item.is_base, "preview_url": f"/api/floorplans/{item.id}/preview", "analysis_status": item.analysis_status, "analysis_model": item.analysis_model} for item in related],
        "related_claims": [{"id": claim.id, "claim_number": claim.claim_number, "status": claim.status} for claim in claims],
        "validation": "AI_PROPOSALS_REQUIRE_HUMAN_VERIFICATION",
    }


def floor_object_out(o: FloorObject, db: Session | None = None) -> dict[str, Any]:
    asset = db.get(Asset, o.asset_id) if db and o.asset_id else None
    details = dict(o.details or {})
    if asset:
        details.setdefault("asset", {"name": asset.name, "id": asset.asset_code, "type": asset.asset_type, "condition": "Serviceable — synthetic record", "operational_status": asset.status, "declared_insured_value_cents": asset.insured_value_cents})
    return {"id": o.id, "floor_plan_id": o.floor_plan_id, "asset_id": o.asset_id, "object_type": o.object_type, "label": o.label, "geometry_type": o.geometry_type, "geometry": o.geometry, "layer": o.layer, "human_verified": o.human_verified, "details": details, "source_mode": o.source_mode, "analysis_model": o.analysis_model, "confidence_label": o.confidence_label, "created_at": o.created_at}


def _asset_for_annotation(plan: FloorPlan, label: str, db: Session) -> Asset | None:
    property_id = plan.floor.building.property_id
    assets = db.scalars(select(Asset).where(Asset.property_id == property_id)).all()
    normalized = label.lower()
    aliases = {
        "cnc": "cnc machining center",
        "electrical": "electrical switchgear",
        "compressor": "air compressor",
        "production": "production line",
        "finished goods": "finished goods rack",
        "fire pump": "fire pump",
    }
    wanted = next((asset_name for token, asset_name in aliases.items() if token in normalized), None)
    return next((asset for asset in assets if asset.name.lower() == wanted), None)


def _proposal_details(plan: FloorPlan, proposal: dict[str, Any], source_plan: FloorPlan, db: Session, index: int) -> tuple[int | None, dict[str, Any]]:
    property_id = plan.floor.building.property_id
    prop = db.get(Property, property_id)
    asset = _asset_for_annotation(plan, proposal["label"], db)
    label = proposal["label"]
    lower = label.lower()
    review_needed = proposal.get("confidence_label") != "high" or any(token in lower for token in ("electrical", "compressor", "exit", "alarm"))
    critical = any(token in lower for token in ("electrical", "fire", "exit", "cnc", "production"))
    indicator = "amber" if review_needed else "green"
    media = [
        {"type": "image", "title": "Illustrative machinery reference", "url": "/site-media/machinery-reference.jpg", "source": "Unsplash · Bergstrand Consultancy", "illustrative": True},
        {"type": "image", "title": "Illustrative factory reference", "url": "/site-media/factory-reference.jpg", "source": "Unsplash · Aditi Toys", "illustrative": True},
        {"type": "image", "title": "Illustrative inspection reference", "url": "/site-media/inspection-reference.jpg", "source": "Unsplash · TECNIC Bioprocess Solutions", "illustrative": True},
    ]
    selected_media = [media[index % len(media)], media[(index + 1) % len(media)]]
    declared_value = asset.insured_value_cents if asset else 0
    object_id = asset.asset_code if asset else f"ZONE-{source_plan.id}-{index + 1:02d}"
    incidents = []
    claims = db.scalars(select(Claim).where(Claim.property_id == property_id).order_by(desc(Claim.loss_at))).all()
    if claims and any(token in lower for token in ("production", "cnc", "electrical", "compressor")):
        claim = claims[0]
        incidents.append({"date": claim.loss_at.isoformat(), "status": claim.status, "summary": "Reported incident; spatial relationship requires review.", "claim_id": claim.id, "claim_number": claim.claim_number, "preliminary_repair_estimate_cents": None})
        indicator = "red" if "reported" in claim.status else indicator
    visible = proposal.get("details", {}).get("visible_evidence", "Visible label and symbol proposed from the uploaded drawing.")
    details = {
        "asset": {
            "name": asset.name if asset else label,
            "id": object_id,
            "type": asset.asset_type if asset else proposal["object_type"],
            "location": label,
            "condition": "Review due" if review_needed else "No open finding in synthetic record",
            "operational_status": asset.status if asset else "unverified",
            "declared_insured_value_cents": declared_value,
            "criticality": asset.criticality if asset else ("high" if critical else "medium"),
        },
        "inspection": {
            "last_inspection_date": "2026-04-18",
            "result": "Follow-up required" if review_needed else "No exception recorded",
            "next_due_date": "2026-11-15" if review_needed else "2027-04-18",
            "issues": ["Confirm location and current service certificate against source records."] if review_needed else [],
        },
        "media": selected_media,
        "documents": [
            {"title": "Synthetic inspection report", "type": "PDF", "source": "property evidence register"},
            {"title": "Maintenance certificate", "type": "Certificate", "source": "synthetic fixture", "status": "review needed" if review_needed else "current"},
        ],
        "evidence_summary": visible,
        "evidence_summary_source": proposal.get("analysis_model") or source_plan.analysis_model or "prepared fixture",
        "incidents": incidents,
        "ai_insights": {
            "concerns": ["Geometry and label require reviewer confirmation."] if review_needed else [],
            "missing_or_conflicting_evidence": ["No object-specific service document linked."] if review_needed else [],
            "recommended_next_action": "Request inspection" if review_needed else "Retain in routine review cycle",
            "decision_boundary": "Assistive observation only; no coverage, damage, or payment conclusion.",
        },
        "financial_exposure": {"declared_value_cents": declared_value, "potential_damage_cost_cents": None, "estimate_state": "not_estimated"},
        "timelines": {
            "inspection": [
                {"date": "2025-10-18", "label": "Routine check", "state": "complete"},
                {"date": "2026-04-18", "label": "Latest inspection", "state": "complete"},
                {"date": "2026-11-15" if review_needed else "2027-04-18", "label": "Next due", "state": "due" if review_needed else "scheduled"},
            ],
            "incidents": [{"date": item["date"], "label": item["claim_number"], "state": item["status"]} for item in incidents],
        },
        "status_indicator": indicator,
        "source_plan_id": source_plan.id,
        "source_plan_type": source_plan.plan_type,
        "property_name": prop.name if prop else "Property",
        "human_verification_required": True,
    }
    return asset.id if asset else None, details


@app.get("/api/floorplans/{floorplan_id}")
def floorplan_detail(floorplan_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(FloorPlan, floorplan_id)
    if not plan: raise HTTPException(404, "Floor plan not found")
    return floorplan_out(plan, db)


@app.get("/api/floorplans/{floorplan_id}/preview")
def floorplan_preview(floorplan_id: int, db: Session = Depends(get_db)):
    plan = db.get(FloorPlan, floorplan_id)
    if not plan or not plan.preview_path or not Path(plan.preview_path).is_file(): raise HTTPException(404, "Preview not found")
    media_type = "image/png" if plan.preview_path.endswith(".png") else plan.media_type
    return FileResponse(plan.preview_path, media_type=media_type)


@app.get("/api/floorplans/{floorplan_id}/objects")
def floor_objects(floorplan_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not db.get(FloorPlan, floorplan_id): raise HTTPException(404, "Floor plan not found")
    return {"items": [floor_object_out(o, db) for o in db.scalars(select(FloorObject).where(FloorObject.floor_plan_id == floorplan_id)).all()]}


@app.post("/api/floorplans/{floorplan_id}/objects", status_code=201)
def create_floor_object(floorplan_id: int, payload: FloorObjectCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(FloorPlan, floorplan_id)
    if not plan: raise HTTPException(404, "Floor plan not found")
    if payload.asset_id:
        asset = db.get(Asset, payload.asset_id)
        if not asset or asset.property_id != plan.floor.building.property_id: raise HTTPException(404, "Asset not found for floor plan property")
    obj = FloorObject(floor_plan_id=floorplan_id, **payload.model_dump()); db.add(obj); plan.state = "annotated" if not payload.human_verified else "verified"; db.flush(); audit(db, None, "floorplan", plan.id, "manual_annotation_created", actor="demo_user", source="human", details={"object_id": obj.id, "human_verified": obj.human_verified}); db.commit(); return floor_object_out(obj, db)


@app.patch("/api/floor-objects/{object_id}")
def update_floor_object(object_id: int, payload: FloorObjectCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    obj = db.get(FloorObject, object_id)
    if not obj: raise HTTPException(404, "Floor object not found")
    if payload.asset_id:
        asset = db.get(Asset, payload.asset_id)
        if not asset or asset.property_id != obj.floor_plan.floor.building.property_id: raise HTTPException(404, "Asset not found for floor plan property")
    for key, value in payload.model_dump().items(): setattr(obj, key, value)
    db.commit(); return floor_object_out(obj)


@app.delete("/api/floor-objects/{object_id}")
def delete_floor_object(object_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    obj = db.get(FloorObject, object_id)
    if not obj: raise HTTPException(404, "Floor object not found")
    db.delete(obj); db.commit(); return {"deleted": True}


@app.post("/api/floorplans/{floorplan_id}/verify-objects")
def verify_objects(floorplan_id: int, object_ids: list[int], db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(FloorPlan, floorplan_id)
    if not plan: raise HTTPException(404, "Floor plan not found")
    objects = db.scalars(select(FloorObject).where(FloorObject.floor_plan_id == floorplan_id, FloorObject.id.in_(object_ids))).all()
    for obj in objects: obj.human_verified = True
    plan.state = "verified" if objects else plan.state; db.commit(); return {"verified_ids": [o.id for o in objects], "verified_by": "human_demo_user"}


@app.post("/api/floorplans/{floorplan_id}/intersections")
def floorplan_intersections(floorplan_id: int, payload: IntersectionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    from shapely.geometry import Polygon
    plan = db.get(FloorPlan, floorplan_id)
    if not plan: raise HTTPException(404, "Floor plan not found")
    region = Polygon(payload.polygon)
    if not region.is_valid: raise HTTPException(422, "Invalid incident polygon")
    matches = [o for o in plan.objects if region.intersects(normalized_object_shape(o.geometry_type, o.geometry))]
    assets = [db.get(Asset, o.asset_id) for o in matches if o.asset_id]
    incidents = [incident for o in matches for incident in (o.details or {}).get("incidents", [])]
    evidence_count = sum(len((o.details or {}).get("media", [])) + len((o.details or {}).get("documents", [])) for o in matches)
    return {
        "possibly_affected_object_ids": [o.id for o in matches],
        "possibly_affected_asset_ids": [o.asset_id for o in matches if o.asset_id],
        "objects": [floor_object_out(o, db) for o in matches],
        "summary": {
            "asset_count": len(matches),
            "human_verified_count": sum(1 for o in matches if o.human_verified),
            "total_declared_asset_value_cents": sum(asset.insured_value_cents for asset in assets if asset),
            "reported_or_confirmed_damaged_assets": 0,
            "linked_incident_count": len(incidents),
            "linked_evidence_count": evidence_count,
            "preliminary_potential_loss_estimate_cents": None,
        },
        "disclaimer": "Spatial intersection is an investigation starting point and does not prove damage. Unverified AI proposals are identified separately.",
    }


@app.post("/api/floorplans/{floorplan_id}/propose-annotations")
def propose_annotations(floorplan_id: int, authorize_external_analysis: bool = False, force: bool = False, include_group: bool = True, db: Session = Depends(get_db)) -> dict[str, Any]:
    plan = db.get(FloorPlan, floorplan_id)
    if not plan: raise HTTPException(404, "Floor plan not found")
    if not authorize_external_analysis:
        return {"proposals": [], "mode": "disabled_pending_explicit_authorization", "human_verification_required": True, "validation": "PENDING_USER_FIXTURES", "message": "No findings generated. Configure an approved vision provider and explicitly request analysis."}
    source_plans = db.scalars(select(FloorPlan).where(FloorPlan.source_group == plan.source_group).order_by(FloorPlan.id)).all() if include_group and plan.source_group else [plan]
    target = next((item for item in source_plans if item.is_base), plan)
    pending = [item for item in source_plans if force or item.analysis_status != "complete"]
    if not pending:
        return {"floorplan": floorplan_out(target, db), "created": [], "cached": True, "mode": "cached", "model": target.analysis_model, "human_verification_required": True}
    service = FloorPlanDetectionService(settings)
    created: list[FloorObject] = []
    runs: list[dict[str, Any]] = []
    for source_plan in pending:
        if not source_plan.preview_path:
            continue
        previous = [obj for obj in target.objects if (obj.details or {}).get("source_plan_id") == source_plan.id and obj.source_mode == "gemini_live"]
        for obj in previous:
            db.delete(obj)
        source_plan.analysis_status = "running"
        db.flush()
        try:
            result = service.propose_annotations(source_plan.id, Path(source_plan.preview_path), source_plan.plan_type, explicitly_authorized=True)
        except Exception as exc:
            source_plan.analysis_status = "failed"
            source_plan.analysis_summary = {"error_type": type(exc).__name__, "message": "Provider analysis failed; no annotation geometry was saved."}
            db.commit()
            raise HTTPException(502, f"Gemini floor-plan analysis failed for {source_plan.name}") from exc
        for index, proposal in enumerate(result["proposals"]):
            asset_id, details = _proposal_details(target, proposal, source_plan, db, index)
            proposal["details"] = details
            proposal["asset_id"] = asset_id
            obj = FloorObject(floor_plan_id=target.id, **proposal)
            db.add(obj)
            created.append(obj)
        source_plan.analysis_status = "complete"
        source_plan.analysis_model = result.get("model")
        source_plan.analyzed_at = datetime.now(timezone.utc)
        source_plan.analysis_summary = {"drawing_summary": result.get("drawing_summary"), "limitations": result.get("limitations", []), "proposal_count": len(result["proposals"]), "cached": True}
        runs.append({"plan_id": source_plan.id, "plan_type": source_plan.plan_type, "proposal_count": len(result["proposals"]), "mode": result["mode"], "model": result.get("model")})
    target.state = "needs_review"
    target.analysis_status = "complete" if all(item.analysis_status == "complete" for item in source_plans) else "partial"
    target.analysis_model = ", ".join(sorted({item.analysis_model for item in source_plans if item.analysis_model}))
    target.analyzed_at = datetime.now(timezone.utc)
    db.flush()
    run_key = f"floorplan-vision:{target.source_group or target.id}"
    workflow_run = db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == run_key))
    if not workflow_run:
        workflow_run = WorkflowRun(workflow_type="floorplan_vision", subject_type="floorplan", subject_id=target.id, trigger="explicit_authorized_analysis", state={"subject_id": target.id, "missing_items": [], "steps": ["receive_plans", "align_sources", "gemini_vision", "validate_geometry", "persist_proposals", "human_checkpoint"], "proposal_count": len(target.objects)}, status="waiting_human", provider_metadata={"provider": "Google Gemini", "models": sorted({item.analysis_model for item in source_plans if item.analysis_model}), "source_mode": "live", "human_verification_required": True}, idempotency_key=run_key)
        db.add(workflow_run)
        db.flush()
    audit(db, None, "floorplan", target.id, "annotation_proposals_persisted", actor="floorplan_detection_service", source="gemini_live", details={"proposal_count": len(created), "runs": runs, "human_verification_required": True})
    db.commit()
    return {"floorplan": floorplan_out(target, db), "created": [floor_object_out(obj, db) for obj in created], "runs": runs, "cached": False, "mode": "live", "human_verification_required": True, "validation": "AI_PROPOSALS_REQUIRE_HUMAN_VERIFICATION"}


@app.post("/api/demo/seed")
def demo_seed(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not settings.demo_mode: raise HTTPException(403, "Demo controls disabled")
    return {"status": "ok", "counts": seed_database(db), "idempotent": True}


@app.post("/api/demo/reset")
def demo_reset(db: Session = Depends(get_db)) -> dict[str, Any]:
    if not settings.demo_mode: raise HTTPException(403, "Demo controls disabled")
    db.close(); Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    with SessionLocal() as reset_db: counts = seed_database(reset_db)
    return {"status": "reset", "counts": counts, "synthetic_only": True}
