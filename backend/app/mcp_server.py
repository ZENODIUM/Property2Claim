"""Read-only MCP interface for the local Property2Claim workspace.

Run with: ``..\\.venv\\Scripts\\python -m app.mcp_server`` from ``backend/``.
The server intentionally exposes records and controlled document excerpts only;
it has no write, deletion, payment, or approval tools.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz
from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, func, select

from .database import SessionLocal, init_db
from .models import Building, Claim, Company, Document, EvidenceFact, Floor, FloorPlan, Property, WorkflowRun
from .seed.seed import ensure_portfolio_extension, seed_database
from .seed.supplied_floorplans import ensure_secondary_supplied_floorplans, ensure_supplied_floorplans
from .config import get_settings


settings = get_settings()
mcp = FastMCP(
    "Property2Claim Data",
    instructions=(
        "Read-only access to the local Property2Claim portfolio, workflow, floor-plan, "
        "claim, and evidence registry. Never treat model output as authorization for coverage, "
        "payment, or binding decisions."
    ),
)


def _json(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json(item) for item in value]
    return value


def _document_metadata(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "filename": document.filename,
        "media_type": document.media_type,
        "classification": document.classification,
        "company_id": document.company_id,
        "property_id": document.property_id,
        "claim_id": document.claim_id,
        "size_bytes": document.size_bytes,
        "analysis_status": document.analysis_status,
        "source_mode": document.source_mode,
        "created_at": _json(document.created_at),
        "content_route": f"/api/documents/{document.id}/content",
    }


def initialise_data() -> None:
    """Make standalone MCP startup match the local app's idempotent demo preparation."""
    init_db()
    if settings.demo_mode:
        with SessionLocal() as db:
            seed_database(db)
            ensure_portfolio_extension(db)
            ensure_supplied_floorplans(db, settings)
            ensure_secondary_supplied_floorplans(db, settings)


@mcp.tool(description="Return the portfolio summary and optionally the sites for one company.")
def get_portfolio(company_id: int | None = None) -> dict[str, Any]:
    with SessionLocal() as db:
        company_query = select(Company).order_by(Company.name)
        if company_id is not None:
            company_query = company_query.where(Company.id == company_id)
        companies = db.scalars(company_query).all()
        rows = []
        for company in companies:
            properties = db.scalars(select(Property).where(Property.company_id == company.id).order_by(Property.name)).all()
            rows.append({
                "id": company.id,
                "name": company.name,
                "industry": company.industry,
                "site_count": len(properties),
                "declared_tiv_cents": sum(property.tiv_cents for property in properties),
                "sites": [{"id": property.id, "site_code": property.site_code, "name": property.name, "city": property.city, "region": property.region, "occupancy": property.occupancy, "risk_score": property.risk_score, "declared_tiv_cents": property.tiv_cents} for property in properties],
            })
        return {"companies": rows, "company_count": len(rows), "read_only": True}


@mcp.tool(description="Return the persisted steps, provider metadata, and status for a workflow run.")
def get_workflow_run(run_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        run = db.get(WorkflowRun, run_id)
        if not run:
            return {"found": False, "run_id": run_id}
        return _json({"found": True, "id": run.id, "workflow_type": run.workflow_type, "subject_type": run.subject_type, "subject_id": run.subject_id, "trigger": run.trigger, "status": run.status, "steps": run.state.get("steps", []), "state": run.state, "provider_metadata": run.provider_metadata, "created_at": run.created_at, "updated_at": run.updated_at})


@mcp.tool(description="List workflow runs, optionally restricted to a workflow type such as underwriting_graph, claims_graph, hazard_graph, or floorplan_vision.")
def list_workflow_runs(workflow_type: str | None = None, limit: int = 20) -> dict[str, Any]:
    safe_limit = min(max(limit, 1), 100)
    with SessionLocal() as db:
        statement = select(WorkflowRun).order_by(desc(WorkflowRun.id)).limit(safe_limit)
        if workflow_type:
            statement = statement.where(WorkflowRun.workflow_type == workflow_type)
        runs = db.scalars(statement).all()
        return _json({"items": [{"id": run.id, "workflow_type": run.workflow_type, "subject_type": run.subject_type, "subject_id": run.subject_id, "status": run.status, "steps": run.state.get("steps", []), "route": run.state.get("route"), "created_at": run.created_at} for run in runs]})


@mcp.tool(description="Return a saved 2D floor-plan group's sheets and annotation summary for a property.")
def get_floorplan(property_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        prop = db.get(Property, property_id)
        if not prop:
            return {"found": False, "property_id": property_id}
        plans = db.scalars(select(FloorPlan).join(FloorPlan.floor).join(Floor.building).where(Building.property_id == property_id).order_by(FloorPlan.id)).all()
        return _json({"found": True, "property": {"id": prop.id, "name": prop.name}, "plans": [{"id": plan.id, "name": plan.name, "plan_type": plan.plan_type, "is_base": plan.is_base, "state": plan.state, "analysis_status": plan.analysis_status, "analysis_model": plan.analysis_model, "source_group": plan.source_group, "object_count": len(plan.objects), "human_verified_count": sum(1 for item in plan.objects if item.human_verified), "preview_route": f"/api/floorplans/{plan.id}/preview"} for plan in plans]})


@mcp.tool(description="List safely exposed evidence-file metadata from the document registry. This never returns filesystem paths.")
def list_evidence(property_id: int | None = None, claim_id: int | None = None, limit: int = 50) -> dict[str, Any]:
    safe_limit = min(max(limit, 1), 100)
    with SessionLocal() as db:
        statement = select(Document).order_by(desc(Document.id)).limit(safe_limit)
        if property_id is not None:
            statement = statement.where(Document.property_id == property_id)
        if claim_id is not None:
            statement = statement.where(Document.claim_id == claim_id)
        documents = db.scalars(statement).all()
        return {"items": [_document_metadata(document) for document in documents], "read_only": True}


@mcp.tool(description="Return extracted facts and a bounded text excerpt for a registered PDF or text document. Binary files return metadata only.")
def get_document_excerpt(document_id: int, max_characters: int = 6000) -> dict[str, Any]:
    safe_max = min(max(max_characters, 250), 12_000)
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            return {"found": False, "document_id": document_id}
        facts = db.scalars(select(EvidenceFact).where(EvidenceFact.document_id == document.id).order_by(EvidenceFact.id)).all()
        result: dict[str, Any] = {"found": True, "document": _document_metadata(document), "facts": _json([{"fact_type": fact.fact_type, "value": fact.value, "page_number": fact.page_number, "timestamp_seconds": fact.timestamp_seconds, "evidence_location": fact.evidence_location, "verified": fact.verified} for fact in facts]), "excerpt": None}
        path = Path(document.storage_path).resolve()
        allowed_roots: Iterable[Path] = (settings.upload_dir.resolve(), Path(__file__).resolve().parent / "seed" / "fixtures")
        if not any(path.is_relative_to(root) for root in allowed_roots) or not path.is_file():
            result["excerpt_status"] = "metadata_only_unavailable_or_outside_approved_storage"
            return result
        if document.media_type == "application/pdf":
            with fitz.open(path) as pdf:
                result["excerpt"] = "\n".join(page.get_text() for page in pdf)[:safe_max]
                result["page_count"] = len(pdf)
                result["excerpt_status"] = "pdf_text"
        elif document.media_type.startswith("text/") or path.suffix.lower() in {".txt", ".csv"}:
            result["excerpt"] = path.read_text(encoding="utf-8", errors="replace")[:safe_max]
            result["excerpt_status"] = "text"
        else:
            result["excerpt_status"] = "binary_metadata_only"
        return result


@mcp.tool(description="Return a claim's non-binding investigation state, linked evidence, and illustrative estimate summaries.")
def get_claim(claim_id: int) -> dict[str, Any]:
    with SessionLocal() as db:
        claim = db.get(Claim, claim_id)
        if not claim:
            return {"found": False, "claim_id": claim_id}
        documents = db.scalars(select(Document).where(Document.claim_id == claim.id).order_by(Document.id)).all()
        return _json({"found": True, "id": claim.id, "claim_number": claim.claim_number, "property_id": claim.property_id, "peril": claim.peril, "status": claim.status, "narrative": claim.narrative, "contradiction_summary": claim.contradiction_summary, "reported_at": claim.reported_at, "evidence": [_document_metadata(document) for document in documents], "notice": "Investigation data is advisory and does not determine coverage, reserve, payment, or legal outcome."})


@mcp.resource("property2claim://portfolio/summary", name="Portfolio summary", description="Read-only current portfolio counts and declared values.", mime_type="application/json")
def portfolio_summary_resource() -> dict[str, Any]:
    with SessionLocal() as db:
        properties = db.scalars(select(Property)).all()
        return {"company_count": db.scalar(select(func.count()).select_from(Company)) or 0, "property_count": len(properties), "declared_tiv_cents": sum(property.tiv_cents for property in properties), "workflow_run_count": db.scalar(select(func.count()).select_from(WorkflowRun)) or 0, "read_only": True}


def main() -> None:
    initialise_data()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
