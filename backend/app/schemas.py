from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    industry: str = Field(min_length=2, max_length=120)
    naics: str = Field(pattern=r"^\d{2,6}$")
    broker_contact: str = Field(min_length=3, max_length=160)


class UnderwritingCreate(BaseModel):
    company_id: int = Field(gt=0)
    property_id: int = Field(gt=0)


class FNOLCreate(BaseModel):
    company_id: int = Field(gt=0)
    property_id: int = Field(gt=0)
    policy_id: int = Field(gt=0)
    loss_at: datetime
    peril: Literal["water", "fire", "wind", "hail", "theft", "other"]
    narrative: str = Field(min_length=12, max_length=5000)
    reported_exposures: list[Literal["building", "equipment", "contents", "business_income", "extra_expense"]] = Field(min_length=1)
    incident_geometry: dict[str, Any] | None = None


class TaskDecisionCreate(BaseModel):
    actor: str = Field(min_length=2, max_length=100)
    actor_role: Literal["underwriter", "claims_reviewer", "supervisor", "engineer", "coverage_counsel"]
    action: Literal[
        "request_evidence",
        "approve_request",
        "assign_specialist",
        "approve_demo_terms",
        "approve_reserve_review",
        "authorize_settlement_simulation",
        "refer_formal_denial_review",
        "close_demo",
        "reopen_demo",
    ]
    rationale: str = Field(min_length=5, max_length=2000)


class FloorObjectCreate(BaseModel):
    asset_id: int | None = None
    object_type: str = Field(min_length=2, max_length=60)
    label: str = Field(min_length=1, max_length=120)
    geometry_type: Literal["point", "rect", "polygon"]
    geometry: dict[str, Any]
    layer: Literal[
        "machinery", "fire_safety", "utilities", "building_zones", "inspections",
        "evidence", "incidents", "financial_exposure", "ai_findings", "structural",
        "electrical", "claims",
    ] = "machinery"
    human_verified: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
    source_mode: Literal["human", "gemini_live", "prepared_fixture"] = "human"
    analysis_model: str | None = Field(default=None, max_length=100)
    confidence_label: Literal["low", "medium", "high"] | None = None

    @field_validator("geometry")
    @classmethod
    def normalized_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        numbers: list[float] = []
        for item in value.values():
            if isinstance(item, (int, float)):
                numbers.append(float(item))
            elif isinstance(item, list):
                for point in item:
                    if isinstance(point, list):
                        numbers.extend(float(v) for v in point)
        if not numbers or any(v < 0 or v > 1 for v in numbers):
            raise ValueError("geometry coordinates must be normalized between 0 and 1")
        return value


class IntersectionRequest(BaseModel):
    polygon: list[list[float]] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_polygon(self) -> "IntersectionRequest":
        if any(len(point) != 2 or any(v < 0 or v > 1 for v in point) for point in self.polygon):
            raise ValueError("polygon points must be normalized [x,y] pairs")
        return self


class DemoIssueRequest(BaseModel):
    submission_id: int = Field(gt=0)
    actor: str = Field(min_length=2)
    actor_role: Literal["underwriter", "supervisor"]
