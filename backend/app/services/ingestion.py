from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import fitz
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, EvidenceFact, Property


REQUIRED_SOV_COLUMNS = {"site_code", "name", "address", "city", "region", "latitude", "longitude", "occupancy", "building_value", "equipment_value", "contents_value", "business_income"}


def parse_sov(path: Path, media_type: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path) if media_type == "text/csv" else pd.read_excel(path)
    except Exception as exc:
        raise HTTPException(422, f"Could not parse SOV: {type(exc).__name__}") from exc
    missing = REQUIRED_SOV_COLUMNS - set(frame.columns)
    if missing:
        raise HTTPException(422, {"message": "Missing SOV columns", "columns": sorted(missing)})
    if frame["site_code"].duplicated().any():
        raise HTTPException(422, "Duplicate site_code in SOV")
    return frame


def import_sov(db: Session, company: Company, frame: pd.DataFrame) -> dict[str, Any]:
    created = 0
    updated = 0
    for row in frame.to_dict(orient="records"):
        prop = db.scalar(select(Property).where(Property.site_code == str(row["site_code"])))
        values = {
            "company_id": company.id,
            "name": str(row["name"]), "address": str(row["address"]), "city": str(row["city"]), "region": str(row["region"]),
            "latitude": float(row["latitude"]), "longitude": float(row["longitude"]), "occupancy": str(row["occupancy"]),
            "construction": str(row.get("construction", "masonry non-combustible")), "year_built": int(row.get("year_built", 2000)),
            "area_sqft": int(row.get("area_sqft", 50000)), "floors_count": int(row.get("floors", 1)), "roof": str(row.get("roof", "membrane")),
            "protection": str(row.get("protection", "documentation pending")), "operations": str(row.get("operations", row["occupancy"])),
            "building_value_cents": int(float(row["building_value"]) * 100), "equipment_value_cents": int(float(row["equipment_value"]) * 100),
            "contents_value_cents": int(float(row["contents_value"]) * 100), "business_income_cents": int(float(row["business_income"]) * 100),
            "baseline_hazards": {"source": "SOV import", "status": "pending validation"},
        }
        if prop:
            if prop.company_id != company.id:
                raise HTTPException(409, "site_code belongs to another company")
            for key, value in values.items():
                setattr(prop, key, value)
            updated += 1
        else:
            db.add(Property(site_code=str(row["site_code"]), **values))
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "rows": len(frame)}


def extract_pdf_facts(db: Session, document_id: int, path: Path, subject_type: str, subject_id: int) -> list[EvidenceFact]:
    try:
        pdf = fitz.open(path)
    except Exception as exc:
        raise HTTPException(422, "Invalid PDF") from exc
    facts: list[EvidenceFact] = []
    for index, page in enumerate(pdf):
        text = page.get_text("text").strip()
        if text:
            fact = EvidenceFact(
                document_id=document_id, subject_type=subject_type, subject_id=subject_id,
                fact_type="document_text", value={"text": text[:8000]}, page_number=index + 1,
                evidence_location=f"page {index + 1}", verified=False,
            )
            db.add(fact)
            facts.append(fact)
    db.flush()
    return facts
