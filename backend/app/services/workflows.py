from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.jev_adapter import route_claim, route_submission
from ..config import get_settings
from ..graphs import claims_graph, hazard_graph, underwriting_graph
from ..models import (
    AuditEvent, Claim, ClaimExposure, Coverage, Document, EstimateLineItem, EvidenceFact,
    HazardEvent, HistoricalClaim, HumanDecision, LossEstimate, Policy, Property,
    PropertyHazardMatch, ReviewTask, UnderwritingSubmission, WorkflowRun,
)
from .spatial import property_matches_geometry


def audit(db: Session, company_id: int | None, subject_type: str, subject_id: int, event_type: str, *, actor: str, source: str, details: dict, old_state: dict | None = None, new_state: dict | None = None) -> AuditEvent:
    event = AuditEvent(company_id=company_id, subject_type=subject_type, subject_id=subject_id, event_type=event_type, actor=actor, source=source, details=details, old_state=old_state, new_state=new_state)
    db.add(event)
    return event


def task_once(db: Session, *, company_id: int, property_id: int | None, subject_type: str, subject_id: int, kind: str, title: str, priority: str, required_role: str, details: dict, key: str) -> ReviewTask:
    existing = db.scalar(select(ReviewTask).where(ReviewTask.idempotency_key == key))
    if existing:
        return existing
    task = ReviewTask(company_id=company_id, property_id=property_id, subject_type=subject_type, subject_id=subject_id, kind=kind, title=title, priority=priority, required_role=required_role, details=details, idempotency_key=key)
    db.add(task)
    db.flush()
    return task


def persist_run(db: Session, workflow_type: str, subject_id: int, trigger: str, state: dict, provider: dict, key: str) -> WorkflowRun:
    existing = db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == key))
    if existing:
        return existing
    run = WorkflowRun(workflow_type=workflow_type, subject_type=workflow_type.replace("_graph", ""), subject_id=subject_id, trigger=trigger, state=state, status="waiting_human", provider_metadata=provider, idempotency_key=key)
    db.add(run)
    db.flush()
    return run


def run_underwriting(db: Session, submission: UnderwritingSubmission) -> UnderwritingSubmission:
    prop = db.get(Property, submission.property_id)
    if not prop or prop.company_id != submission.company_id:
        raise HTTPException(404, "Property not found for company")
    missing: list[str] = []
    if "current" not in prop.protection.lower():
        missing.append("current fire protection certificate")
    if not db.scalar(select(Document).where(Document.property_id == prop.id, Document.classification == "inspection_report")):
        missing.append("current inspection report")
    has_conflict = "conflict" in prop.protection.lower() or "outdated" in prop.protection.lower()
    decision = route_submission(get_settings(), missing, has_conflict)
    graph_state = underwriting_graph.invoke({"subject_id": submission.id, "missing_items": missing, "conflicts": ["protection certificate dates conflict"] if has_conflict else [], "route": decision.answer, "steps": []})
    old = {"status": submission.status}
    submission.missing_items = missing
    submission.exceptions = ([{"type": "protection_conflict", "source": "synthetic inspection report", "requires_human_review": True}] if has_conflict else [])
    submission.completeness = max(0, 100 - len(missing) * 20 - (15 if has_conflict else 0))
    submission.route = decision.answer
    submission.decision_source = decision.source
    submission.premium_scenario_cents = int(prop.tiv_cents * (0.004 + prop.risk_score / 100000))
    submission.status = "needs_info" if missing else "ready_for_underwriter"
    task = task_once(db, company_id=prop.company_id, property_id=prop.id, subject_type="underwriting", subject_id=submission.id, kind="request_info" if missing else "underwriter_review", title="Resolve underwriting evidence exceptions" if missing else "Review synthetic underwriting terms", priority="high" if has_conflict else "normal", required_role="underwriter", details={"missing_items": missing, "decision_source": decision.source, "not_an_approval": True}, key=f"uw:{submission.id}:{submission.status}")
    run = persist_run(db, "underwriting_graph", submission.id, "manual_run", graph_state, {"decision_source": decision.source, "provider": decision.provider, **decision.trace}, f"uw-run:{submission.id}:{submission.status}")
    audit(db, prop.company_id, "underwriting", submission.id, "workflow_waiting_human", actor="underwriting_graph", source=decision.source, details={"task_id": task.id, "run_id": run.id, "steps": graph_state["steps"]}, old_state=old, new_state={"status": submission.status})
    db.commit()
    return submission


def replay_hazard(db: Session, event: HazardEvent) -> list[PropertyHazardMatch]:
    matches: list[PropertyHazardMatch] = []
    matched_ids: list[int] = []
    for prop in db.scalars(select(Property)).all():
        matched, distance = property_matches_geometry(prop.latitude, prop.longitude, event.geometry)
        if not matched:
            continue
        row = db.scalar(select(PropertyHazardMatch).where(PropertyHazardMatch.property_id == prop.id, PropertyHazardMatch.hazard_event_id == event.id))
        if not row:
            row = PropertyHazardMatch(property_id=prop.id, hazard_event_id=event.id, match_method="geometry_intersection" if distance == 0 else "geodesic_radius", distance_km=distance, exposed_value_cents=prop.tiv_cents)
            db.add(row)
            db.flush()
        matches.append(row)
        matched_ids.append(prop.id)
        task_once(db, company_id=prop.company_id, property_id=prop.id, subject_type="hazard", subject_id=event.id, kind="exposure_review", title=f"Potential exposure review: {event.title}", priority="high", required_role="underwriter", details={"property_id": prop.id, "exposed_value_cents": prop.tiv_cents, "does_not_confirm_damage": True}, key=f"hazard:{event.id}:property:{prop.id}")
        audit(db, prop.company_id, "hazard", event.id, "potential_exposure_matched", actor="hazard_graph", source=event.source_mode, details={"property_id": prop.id, "exposed_value_cents": prop.tiv_cents, "claim_created": False})
    state = hazard_graph.invoke({"subject_id": event.id, "matched_property_ids": matched_ids, "steps": []})
    persist_run(db, "hazard_graph", event.id, "replay", state, {"provider": event.provider, "source_mode": event.source_mode}, f"hazard-run:{event.id}")
    db.commit()
    return matches


def run_claim(db: Session, claim: Claim, trigger: str = "manual_run") -> Claim:
    exposures = [x.exposure_type for x in db.scalars(select(ClaimExposure).where(ClaimExposure.claim_id == claim.id)).all()]
    quote = db.scalar(select(EvidenceFact).where(EvidenceFact.subject_type == "claim", EvidenceFact.subject_id == claim.id, EvidenceFact.fact_type == "repair_quote").order_by(EvidenceFact.id.desc()))
    decision = route_claim(get_settings(), quote is None, exposures)
    state = claims_graph.invoke({"subject_id": claim.id, "missing_items": [] if quote else ["itemized machine repair quote"], "exposures": exposures, "route": decision.answer, "steps": []})
    old = {"status": claim.status}
    if quote is None:
        claim.status = "waiting_evidence"
        task = task_once(db, company_id=claim.company_id, property_id=claim.property_id, subject_type="claim", subject_id=claim.id, kind="request_evidence", title="Obtain itemized machine repair quote", priority="high", required_role="claims_reviewer", details={"missing": "machine repair quote", "requires_human_approval_before_outreach": True}, key=f"claim:{claim.id}:repair-quote")
    else:
        claim.status = "estimate_review"
        for evidence_task in db.scalars(select(ReviewTask).where(ReviewTask.subject_type == "claim", ReviewTask.subject_id == claim.id, ReviewTask.kind == "request_evidence", ReviewTask.status.in_(["queued", "waiting"]))).all():
            evidence_task.status = "completed_evidence_received"
        task = task_once(db, company_id=claim.company_id, property_id=claim.property_id, subject_type="claim", subject_id=claim.id, kind="estimate_review", title="Review revised synthetic loss estimate", priority="normal", required_role="claims_reviewer", details={"quote_fact_id": quote.id, "not_payable": True}, key=f"claim:{claim.id}:estimate:{quote.id}")
        create_estimate(db, claim)
    run_key = f"claim-run:{claim.id}:{trigger}:{quote.id if quote else 'missing'}"
    run = persist_run(db, "claims_graph", claim.id, trigger, state, {"decision_source": decision.source, "provider": decision.provider, **decision.trace}, run_key)
    audit(db, claim.company_id, "claim", claim.id, "investigation_waiting_human", actor="claims_graph", source=decision.source, details={"task_id": task.id, "run_id": run.id, "route": decision.answer, "steps": state["steps"]}, old_state=old, new_state={"status": claim.status})
    db.commit()
    return claim


def create_estimate(db: Session, claim: Claim) -> LossEstimate:
    quotes = db.scalars(select(EvidenceFact).where(EvidenceFact.subject_type == "claim", EvidenceFact.subject_id == claim.id, EvidenceFact.fact_type == "repair_quote")).all()
    historical = db.scalars(select(HistoricalClaim).where(HistoricalClaim.peril == claim.peril)).all()
    analogs = [h.gross_loss_cents for h in historical]
    baseline = int(median(analogs)) if analogs else 100_000_00
    documented = sum(int(q.value.get("amount_cents", 0)) for q in quotes)
    gross = documented if documented else baseline
    policy = db.get(Policy, claim.policy_id)
    coverage = db.scalar(select(Coverage).where(Coverage.policy_id == policy.id, Coverage.coverage_type == "commercial_property")) if policy else None
    deductible = coverage.deductible_cents if coverage else 0
    limit = coverage.limit_cents if coverage else gross
    eligible = min(max(gross - deductible, 0), limit)
    version = (db.scalar(select(func.max(LossEstimate.version)).where(LossEstimate.claim_id == claim.id)) or 0) + 1
    estimate = LossEstimate(claim_id=claim.id, version=version, method="documented_quote_sum" if documented else "synthetic_historical_median", gross_cents=gross, deductible_cents=deductible, illustrative_eligible_cents=eligible, low_cents=int(gross * .75), high_cents=int(gross * 1.35), reserve_suggestion_cents=int(gross * 1.15), assumptions=["Synthetic demo policy terms applied", f"{len(analogs)} synthetic peril analogs available"], limitations=["Illustrative estimate only", "Not an actuarially validated prediction", "Not payable and requires authorized human review", "Coverage interpretation is not resolved by this calculation"], provenance=[{"kind": "repair_quote", "fact_id": q.id, "document_id": q.document_id} for q in quotes] or [{"kind": "synthetic_history", "sample_count": len(analogs)}])
    db.add(estimate)
    db.flush()
    db.add(EstimateLineItem(estimate_id=estimate.id, category="equipment" if claim.peril == "water" else "building", description="Supported repair quote" if documented else "Synthetic comparable baseline", amount_cents=gross, source_kind="documented_quote" if documented else "synthetic_history", source_id=quotes[-1].id if quotes else None, supported=bool(documented)))
    audit(db, claim.company_id, "claim", claim.id, "estimate_version_created", actor="estimate_service", source="deterministic", details={"estimate_id": estimate.id, "version": version, "not_payable": True}, old_state={"prior_version": version - 1}, new_state={"gross_cents": gross, "illustrative_eligible_cents": eligible})
    db.flush()
    return estimate


ROLE_ACTIONS = {
    "underwriter": {"request_evidence", "approve_request", "assign_specialist", "approve_demo_terms"},
    "claims_reviewer": {"request_evidence", "approve_request", "assign_specialist", "approve_reserve_review", "authorize_settlement_simulation", "close_demo", "reopen_demo"},
    "supervisor": {"approve_demo_terms", "approve_reserve_review", "authorize_settlement_simulation", "refer_formal_denial_review", "close_demo", "reopen_demo"},
    "engineer": {"assign_specialist", "approve_request"},
    "coverage_counsel": {"refer_formal_denial_review"},
}


def decide_task(db: Session, task: ReviewTask, actor: str, role: str, action: str, rationale: str) -> HumanDecision:
    if action not in ROLE_ACTIONS.get(role, set()):
        raise HTTPException(403, f"Role {role} cannot perform {action}")
    if action in {"authorize_settlement_simulation", "refer_formal_denial_review"} and role not in {"claims_reviewer", "supervisor", "coverage_counsel"}:
        raise HTTPException(403, "Authorized human review role required")
    underwriting_only = {"approve_demo_terms"}
    claim_only = {"approve_reserve_review", "authorize_settlement_simulation", "refer_formal_denial_review", "close_demo", "reopen_demo"}
    if action in underwriting_only and task.subject_type != "underwriting":
        raise HTTPException(409, "This action applies only to an underwriting task")
    if action in claim_only and task.subject_type not in {"claim", "claims"}:
        raise HTTPException(409, "This action applies only to a claim task")
    before = task.status
    subject_before: str | None = None
    subject_after: str | None = None
    if task.subject_type == "underwriting":
        submission = db.get(UnderwritingSubmission, task.subject_id)
        if submission:
            subject_before = submission.status
            if action == "approve_demo_terms":
                submission.status = "terms_approved_demo"
                submission.human_decision = action
            elif action == "request_evidence":
                submission.status = "needs_info"
            subject_after = submission.status
    elif task.subject_type in {"claim", "claims"}:
        claim = db.get(Claim, task.subject_id)
        if claim:
            subject_before = claim.status
            if action == "approve_reserve_review":
                claim.status = "reserve_reviewed_demo"
            elif action == "authorize_settlement_simulation":
                claim.status = "settlement_simulation_authorized"
            elif action == "close_demo":
                claim.status = "closed_demo"
            elif action == "reopen_demo":
                claim.status = "estimate_review"
            elif action == "request_evidence":
                claim.status = "waiting_evidence"
            subject_after = claim.status
    task.status = "approved" if action.startswith("approve") or action == "authorize_settlement_simulation" else "completed"
    decision = HumanDecision(task_id=task.id, actor=actor, actor_role=role, action=action, rationale=rationale, state_before=before, state_after=task.status)
    db.add(decision)
    terminal_actions = {"approve_demo_terms", "approve_reserve_review", "authorize_settlement_simulation", "close_demo"}
    for run in db.scalars(select(WorkflowRun).where(WorkflowRun.subject_id == task.subject_id, WorkflowRun.subject_type.in_({task.subject_type, task.subject_type.rstrip("s")}))).all():
        if action in terminal_actions:
            run.status = "completed_human_review"
        elif action == "reopen_demo":
            run.status = "waiting_human"
    audit(db, task.company_id, task.subject_type.rstrip("s"), task.subject_id, "human_decision", actor=actor, source="human", details={"task_id": task.id, "role": role, "action": action, "simulation_only": action == "authorize_settlement_simulation"}, old_state={"task_status": before, "subject_status": subject_before}, new_state={"task_status": task.status, "subject_status": subject_after})
    db.commit()
    return decision
