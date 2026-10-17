from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import fitz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditEvent, Building, Document, Floor, FloorPlan, Property, WorkflowRun

if TYPE_CHECKING:
    from ..config import Settings


SUPPLIED_GROUP = "northstar-factory-a-user-plans-v1"
SUPPLIED_PLANS = (
    ("ChatGPT Image Oct 17, 2026, 02_46_52 AM-1.png", "base", "General arrangement", True),
    ("ChatGPT Image Oct 17, 2026, 02_46_53 AM-2.png", "machinery", "Machinery and equipment", False),
    ("ChatGPT Image Oct 17, 2026, 02_46_54 AM-3.png", "emergency", "Emergency and fire safety", False),
)

SECONDARY_GROUP = "meridian-chicago-user-plans-v1"
SECONDARY_PLAN_ROLES = (
    ("base", "General arrangement", True),
    ("machinery", "Machinery and equipment", False),
    ("emergency", "Emergency and fire safety", False),
)


def ensure_supplied_floorplans(db: Session, settings: "Settings") -> list[int]:
    """Attach the user-supplied plan set once without reprocessing it on startup."""
    existing = db.scalars(select(FloorPlan).where(FloorPlan.source_group == SUPPLIED_GROUP)).all()
    if existing:
        base = next((plan for plan in existing if plan.is_base), existing[0])
        if base.analysis_status == "complete" and not db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == f"floorplan-vision:{SUPPLIED_GROUP}")):
            models = sorted({plan.analysis_model for plan in existing if plan.analysis_model})
            db.add(WorkflowRun(
                workflow_type="floorplan_vision",
                subject_type="floorplan",
                subject_id=base.id,
                trigger="explicit_authorized_analysis",
                state={"subject_id": base.id, "missing_items": [], "steps": ["receive_plans", "align_sources", "gemini_vision", "validate_geometry", "persist_proposals", "human_checkpoint"], "proposal_count": len(base.objects)},
                status="waiting_human",
                provider_metadata={"provider": "Google Gemini", "models": models, "source_mode": "live", "human_verification_required": True},
                idempotency_key=f"floorplan-vision:{SUPPLIED_GROUP}",
            ))
            db.commit()
        return [plan.id for plan in existing]

    repository_root = Path(__file__).resolve().parents[3]
    source_dir = repository_root / "site 2d images"
    if not all((source_dir / filename).is_file() for filename, *_ in SUPPLIED_PLANS):
        return []

    prop = db.scalar(select(Property).where(Property.site_code == "NS-HOU-A"))
    if not prop:
        return []
    building = db.scalar(select(Building).where(Building.property_id == prop.id))
    if not building:
        building = Building(property_id=prop.id, name="Main Building")
        db.add(building)
        db.flush()
    floor = db.scalar(select(Floor).where(Floor.building_id == building.id, Floor.name == "Ground Floor"))
    if not floor:
        floor = Floor(building_id=building.id, name="Ground Floor", level=1)
        db.add(floor)
        db.flush()

    destination = Path(settings.upload_dir).resolve() / "floorplans" / str(prop.id) / SUPPLIED_GROUP
    destination.mkdir(parents=True, exist_ok=True)
    plan_ids: list[int] = []
    for filename, plan_type, label, is_base in SUPPLIED_PLANS:
        source = source_dir / filename
        target = destination / filename
        if not target.exists():
            shutil.copy2(source, target)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        document = db.scalar(select(Document).where(Document.sha256 == digest, Document.property_id == prop.id))
        if not document:
            document = Document(
                company_id=prop.company_id,
                property_id=prop.id,
                filename=filename,
                media_type="image/png",
                classification=f"floor_plan_{plan_type}",
                storage_path=str(target),
                sha256=digest,
                size_bytes=target.stat().st_size,
                uploader="workspace_user",
                source_mode="user_supplied",
                analysis_status="not_requested",
            )
            db.add(document)
            db.flush()
        pixmap = fitz.Pixmap(str(target))
        plan = FloorPlan(
            floor_id=floor.id,
            original_document_id=document.id,
            preview_path=str(target),
            media_type="image/png",
            width=pixmap.width,
            height=pixmap.height,
            revision=1,
            state="uploaded",
            name=label,
            plan_type=plan_type,
            is_base=is_base,
            source_group=SUPPLIED_GROUP,
            analysis_status="not_requested",
            analysis_summary={},
        )
        db.add(plan)
        db.flush()
        plan_ids.append(plan.id)

    db.add(AuditEvent(
        company_id=prop.company_id,
        subject_type="floorplan_group",
        subject_id=plan_ids[0],
        event_type="supplied_plan_set_attached",
        actor="workspace_user",
        source="user_supplied",
        details={"property_id": prop.id, "plan_count": len(plan_ids), "source_group": SUPPLIED_GROUP},
    ))
    db.commit()
    return plan_ids


def ensure_secondary_supplied_floorplans(db: Session, settings: "Settings") -> list[int]:
    """Attach the second user plan set exactly once when its three sheets are present.

    The folder is intentionally optional: no vision call or generated annotations occur
    until the user has actually supplied the base, machinery, and emergency sheets.
    """
    existing = db.scalars(select(FloorPlan).where(FloorPlan.source_group == SECONDARY_GROUP)).all()
    if existing:
        return [plan.id for plan in existing]
    repository_root = Path(__file__).resolve().parents[3]
    source_dir = repository_root / "site 2d images B"
    source_files = sorted(source_dir.glob("*.png"))
    if len(source_files) != 3:
        return []
    prop = db.scalar(select(Property).where(Property.site_code == "MF-CHI-1"))
    if not prop:
        return []
    building = db.scalar(select(Building).where(Building.property_id == prop.id))
    if not building:
        building = Building(property_id=prop.id, name="Primary facility")
        db.add(building); db.flush()
    floor = db.scalar(select(Floor).where(Floor.building_id == building.id, Floor.name == "Ground Floor"))
    if not floor:
        floor = Floor(building_id=building.id, name="Ground Floor", level=1)
        db.add(floor); db.flush()
    destination = Path(settings.upload_dir).resolve() / "floorplans" / str(prop.id) / SECONDARY_GROUP
    destination.mkdir(parents=True, exist_ok=True)
    plan_ids: list[int] = []
    for source, (plan_type, label, is_base) in zip(source_files, SECONDARY_PLAN_ROLES, strict=True):
        filename = source.name
        target = destination / filename
        if not target.exists():
            shutil.copy2(source, target)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        document = Document(company_id=prop.company_id, property_id=prop.id, filename=filename, media_type="image/png", classification=f"floor_plan_{plan_type}", storage_path=str(target), sha256=digest, size_bytes=target.stat().st_size, uploader="workspace_user", source_mode="user_supplied", analysis_status="queued")
        db.add(document); db.flush()
        pixmap = fitz.Pixmap(str(target))
        plan = FloorPlan(floor_id=floor.id, original_document_id=document.id, preview_path=str(target), media_type="image/png", width=pixmap.width, height=pixmap.height, revision=1, state="uploaded", name=label, plan_type=plan_type, is_base=is_base, source_group=SECONDARY_GROUP, analysis_status="queued", analysis_summary={"note": "Awaiting one explicit analysis request; results will be cached."})
        db.add(plan); db.flush(); plan_ids.append(plan.id)
    db.add(AuditEvent(company_id=prop.company_id, subject_type="floorplan_group", subject_id=plan_ids[0], event_type="secondary_plan_set_attached", actor="workspace_user", source="user_supplied", details={"property_id": prop.id, "plan_count": len(plan_ids), "source_group": SECONDARY_GROUP}))
    db.commit()
    return plan_ids
