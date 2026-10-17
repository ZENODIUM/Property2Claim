from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(120))
    naics: Mapped[str] = mapped_column(String(12))
    broker_contact: Mapped[str] = mapped_column(String(160))
    state: Mapped[str] = mapped_column(String(32), default="active")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    properties: Mapped[list[Property]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    site_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(220))
    city: Mapped[str] = mapped_column(String(80))
    region: Mapped[str] = mapped_column(String(40))
    latitude: Mapped[float]
    longitude: Mapped[float]
    occupancy: Mapped[str] = mapped_column(String(100))
    construction: Mapped[str] = mapped_column(String(100))
    year_built: Mapped[int]
    area_sqft: Mapped[int]
    floors_count: Mapped[int] = mapped_column(default=1)
    roof: Mapped[str] = mapped_column(String(100))
    protection: Mapped[str] = mapped_column(String(200))
    operations: Mapped[str] = mapped_column(Text)
    building_value_cents: Mapped[int]
    equipment_value_cents: Mapped[int]
    contents_value_cents: Mapped[int]
    business_income_cents: Mapped[int]
    baseline_hazards: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_score: Mapped[int] = mapped_column(default=50)
    company: Mapped[Company] = relationship(back_populates="properties")
    assets: Mapped[list[Asset]] = relationship(back_populates="property", cascade="all, delete-orphan")

    @property
    def tiv_cents(self) -> int:
        return self.building_value_cents + self.equipment_value_cents + self.contents_value_cents + self.business_income_cents


class RiskDataRecord(Base):
    """Versioned rows for all 15 locked insurance data categories."""
    __tablename__ = "risk_data_records"
    __table_args__ = (UniqueConstraint("property_id", "category", "revision", name="uq_risk_category_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True, index=True)
    category: Mapped[int] = mapped_column(index=True)
    category_name: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String(50))
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified")
    revision: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str] = mapped_column(String(80), default="seed")
    updated_by: Mapped[str] = mapped_column(String(80), default="seed")


class Building(Base):
    __tablename__ = "buildings"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    floors: Mapped[list[Floor]] = relationship(back_populates="building", cascade="all, delete-orphan")


class Floor(Base):
    __tablename__ = "floors"
    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    level: Mapped[int] = mapped_column(default=1)
    building: Mapped[Building] = relationship(back_populates="floors")
    plans: Mapped[list[FloorPlan]] = relationship(back_populates="floor", cascade="all, delete-orphan")


class FloorPlan(Base):
    __tablename__ = "floor_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id"), index=True)
    original_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    revision: Mapped[int] = mapped_column(default=1)
    coordinate_system: Mapped[str] = mapped_column(String(40), default="normalized_0_1")
    state: Mapped[str] = mapped_column(String(30), default="uploaded")
    name: Mapped[str] = mapped_column(String(160), default="Original plan")
    plan_type: Mapped[str] = mapped_column(String(40), default="base")
    is_base: Mapped[bool] = mapped_column(Boolean, default=False)
    source_group: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    analysis_status: Mapped[str] = mapped_column(String(40), default="not_requested")
    analysis_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    floor: Mapped[Floor] = relationship(back_populates="plans")
    objects: Mapped[list[FloorObject]] = relationship(back_populates="floor_plan", cascade="all, delete-orphan")


class FloorObject(Base):
    __tablename__ = "floor_objects"
    id: Mapped[int] = mapped_column(primary_key=True)
    floor_plan_id: Mapped[int] = mapped_column(ForeignKey("floor_plans.id"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    object_type: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120))
    geometry_type: Mapped[str] = mapped_column(String(20))
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON)
    layer: Mapped[str] = mapped_column(String(40), default="machinery")
    human_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_mode: Mapped[str] = mapped_column(String(40), default="human")
    analysis_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    floor_plan: Mapped[FloorPlan] = relationship(back_populates="objects")


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    asset_code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(140))
    asset_type: Mapped[str] = mapped_column(String(60))
    insured_value_cents: Mapped[int]
    value_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    owner: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="active")
    criticality: Mapped[str] = mapped_column(String(30), default="medium")
    property: Mapped[Property] = relationship(back_populates="assets")


class AssetDependency(Base):
    __tablename__ = "asset_dependencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    upstream_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    downstream_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    relationship: Mapped[str] = mapped_column(String(40))


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True, index=True)
    policy_number: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="demo_active")
    effective_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    coverages: Mapped[list[Coverage]] = relationship(back_populates="policy", cascade="all, delete-orphan")


class Coverage(Base):
    __tablename__ = "coverages"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    coverage_type: Mapped[str] = mapped_column(String(80))
    limit_cents: Mapped[int]
    deductible_cents: Mapped[int]
    sublimit_cents: Mapped[int | None] = mapped_column(nullable=True)
    excluded_perils: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy: Mapped[Policy] = relationship(back_populates="coverages")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True, index=True)
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    classification: Mapped[str] = mapped_column(String(80))
    storage_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int]
    uploader: Mapped[str] = mapped_column(String(80))
    source_mode: Mapped[str] = mapped_column(String(30), default="synthetic")
    analysis_status: Mapped[str] = mapped_column(String(40), default="not_requested")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceFact(Base):
    __tablename__ = "evidence_facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[int] = mapped_column(index=True)
    fact_type: Mapped[str] = mapped_column(String(80))
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    timestamp_seconds: Mapped[float | None] = mapped_column(nullable=True)
    evidence_location: Mapped[str] = mapped_column(String(200))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    contradiction_group: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Inspection(Base):
    __tablename__ = "inspections"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    inspection_type: Mapped[str] = mapped_column(String(80))
    inspected_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(40))
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)


class SafetyFinding(Base):
    __tablename__ = "safety_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    finding: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(30))
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")


class HazardEvent(Base):
    __tablename__ = "hazard_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_event_id: Mapped[str] = mapped_column(String(100), unique=True)
    event_type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(30))
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON)
    valid_at: Mapped[datetime]
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_mode: Mapped[str] = mapped_column(String(30))


class PropertyHazardMatch(Base):
    __tablename__ = "property_hazard_matches"
    __table_args__ = (UniqueConstraint("property_id", "hazard_event_id", name="uq_property_hazard"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    hazard_event_id: Mapped[int] = mapped_column(ForeignKey("hazard_events.id"), index=True)
    match_method: Mapped[str] = mapped_column(String(50))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    exposed_value_cents: Mapped[int]
    status: Mapped[str] = mapped_column(String(50), default="potential_exposure_review")


class UnderwritingSubmission(Base):
    __tablename__ = "underwriting_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    completeness: Mapped[int] = mapped_column(default=0)
    missing_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    exceptions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    route: Mapped[str | None] = mapped_column(String(50), nullable=True)
    decision_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    premium_scenario_cents: Mapped[int | None] = mapped_column(nullable=True)
    human_decision: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    claim_number: Mapped[str] = mapped_column(String(80), unique=True)
    loss_at: Mapped[datetime]
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    peril: Mapped[str] = mapped_column(String(50))
    narrative: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="reported")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    incident_geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    contradiction_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClaimExposure(Base):
    __tablename__ = "claim_exposures"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    exposure_type: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(40), default="reported")
    estimate_cents: Mapped[int | None] = mapped_column(nullable=True)
    evidence_ids: Mapped[list[int]] = mapped_column(JSON, default=list)


class LossEstimate(Base):
    __tablename__ = "loss_estimates"
    __table_args__ = (UniqueConstraint("claim_id", "version", name="uq_claim_estimate_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    version: Mapped[int]
    method: Mapped[str] = mapped_column(String(80))
    gross_cents: Mapped[int]
    deductible_cents: Mapped[int]
    illustrative_eligible_cents: Mapped[int]
    low_cents: Mapped[int]
    high_cents: Mapped[int]
    reserve_suggestion_cents: Mapped[int]
    assumptions: Mapped[list[str]] = mapped_column(JSON)
    limitations: Mapped[list[str]] = mapped_column(JSON)
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default="synthetic_requires_human_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EstimateLineItem(Base):
    __tablename__ = "estimate_line_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    estimate_id: Mapped[int] = mapped_column(ForeignKey("loss_estimates.id"), index=True)
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(240))
    amount_cents: Mapped[int]
    source_kind: Mapped[str] = mapped_column(String(60))
    source_id: Mapped[int | None] = mapped_column(nullable=True)
    supported: Mapped[bool] = mapped_column(Boolean, default=False)


class HistoricalClaim(Base):
    __tablename__ = "historical_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    synthetic_key: Mapped[str] = mapped_column(String(80), unique=True)
    peril: Mapped[str] = mapped_column(String(50), index=True)
    occupancy: Mapped[str] = mapped_column(String(80), index=True)
    property_value_cents: Mapped[int]
    equipment_value_cents: Mapped[int]
    damaged_asset_count: Mapped[int]
    documented_repair_cents: Mapped[int]
    gross_loss_cents: Mapped[int]
    reserve_cents: Mapped[int]
    final_paid_cents: Mapped[int]


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_task_idempotency"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[int] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    priority: Mapped[str] = mapped_column(String(30))
    required_role: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(40), default="queued")
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HumanDecision(Base):
    __tablename__ = "human_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("review_tasks.id"), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    actor_role: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(80))
    rationale: Mapped[str] = mapped_column(Text)
    state_before: Mapped[str] = mapped_column(String(60))
    state_after: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String(50), index=True)
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[int] = mapped_column(index=True)
    trigger: Mapped[str] = mapped_column(String(60))
    state: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40))
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    subject_type: Mapped[str] = mapped_column(String(40), index=True)
    subject_id: Mapped[int] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    old_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
