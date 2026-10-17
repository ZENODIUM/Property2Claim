from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Asset, AuditEvent, Building, Claim, ClaimExposure, Company, Coverage, Document,
    EvidenceFact, HazardEvent, HistoricalClaim, Inspection, Policy, Property, RiskDataRecord,
    SafetyFinding, UnderwritingSubmission,
)
from ..services.workflows import create_estimate, run_claim, run_underwriting

NOW = datetime(2026, 10, 17, 14, 0, tzinfo=timezone.utc)

CATEGORY_NAMES = [
    "Company identity", "Insured locations", "Building characteristics", "Roof and structure condition",
    "Operations and occupancy", "Fire/life safety protection", "Building insured value", "Machinery/equipment",
    "Inventory/contents", "Business income and extra expense exposure", "Policies and coverages",
    "Claims/loss history", "Inspections and documents", "Baseline geographic hazards", "Active threats",
]

COMPANIES = [
    ("NorthStar Manufacturing", "Industrial machinery", "333249", "Avery Morgan — synthetic broker"),
    ("Harborline Logistics", "Warehousing and logistics", "493110", "Jordan Lee — synthetic broker"),
    ("Redwood Components", "Electronic components", "334419", "Morgan Chen — synthetic broker"),
    ("Beacon Retail Group", "Specialty retail", "459999", "Riley Patel — synthetic broker"),
]

PROPERTIES = [
    ("NS-HOU-A", "NorthStar Factory A", "1000 Fictional Foundry Way", "Houston", "TX", 29.7604, -95.3698, "heavy manufacturing", "steel frame non-combustible", 1998, 240000, "single-ply membrane; inspection due", "outdated certificate conflict; sprinklers installed", 52_000_000, 38_000_000, 8_000_000, 12_000_000, 78),
    ("NS-TUL-B", "NorthStar Factory B", "200 Imaginary Industrial Drive", "Tulsa", "OK", 36.1540, -95.9928, "machining", "masonry non-combustible", 2005, 175000, "metal standing seam", "current sprinkler certificate", 31_000_000, 24_000_000, 6_000_000, 9_000_000, 48),
    ("NS-DAL-W", "NorthStar Dallas Warehouse", "300 Prototype Parkway", "Dallas", "TX", 32.7767, -96.7970, "warehouse", "tilt-up concrete", 2012, 210000, "TPO membrane", "current sprinkler certificate", 24_000_000, 8_000_000, 15_000_000, 6_000_000, 41),
    ("HL-NWK-1", "Harborline Newark Hub", "40 Fictional Port Road", "Newark", "NJ", 40.7357, -74.1724, "warehouse", "protected steel", 2009, 320000, "TPO membrane", "current sprinkler certificate", 39_000_000, 11_000_000, 30_000_000, 14_000_000, 58),
    ("HL-SAV-2", "Harborline Savannah Hub", "55 Demo Terminal Avenue", "Savannah", "GA", 32.0809, -81.0912, "warehouse", "tilt-up concrete", 2016, 280000, "metal standing seam", "current sprinkler certificate", 35_000_000, 9_000_000, 26_000_000, 11_000_000, 46),
    ("HL-MEM-3", "Harborline Memphis Crossdock", "60 Sample Cargo Lane", "Memphis", "TN", 35.1495, -90.0490, "cross-dock warehouse", "masonry non-combustible", 2011, 190000, "TPO membrane", "certificate renewal pending", 22_000_000, 7_000_000, 18_000_000, 8_000_000, 55),
    ("RC-SAC-1", "Redwood Sacramento Plant", "700 Synthetic Circuit Court", "Sacramento", "CA", 38.5816, -121.4944, "electronics manufacturing", "reinforced concrete", 2003, 145000, "built-up roof", "current sprinkler certificate", 28_000_000, 42_000_000, 12_000_000, 18_000_000, 63),
    ("RC-PHX-2", "Redwood Phoenix Plant", "800 Fictional Wafer Way", "Phoenix", "AZ", 33.4484, -112.0740, "electronics manufacturing", "reinforced concrete", 2018, 155000, "reflective membrane", "current sprinkler certificate", 30_000_000, 48_000_000, 14_000_000, 20_000_000, 44),
    ("BR-CHI-1", "Beacon Chicago Flagship", "900 Example Market Street", "Chicago", "IL", 41.8781, -87.6298, "retail", "masonry", 1987, 48000, "modified bitumen", "partial sprinkler; review open", 14_000_000, 2_000_000, 9_000_000, 4_000_000, 61),
    ("BR-BOS-2", "Beacon Boston Distribution", "950 Placeholder Commerce Road", "Boston", "MA", 42.3601, -71.0589, "warehouse", "protected steel", 2014, 92000, "TPO membrane", "current sprinkler certificate", 18_000_000, 5_000_000, 13_000_000, 5_000_000, 39),
]

# Portfolio expansion is intentionally idempotent so a running demo database can
# gain breadth without being reset or losing uploaded evidence.
PORTFOLIO_EXTENSION = [
    ("Meridian Food Systems", "Food processing", "311999", "Casey Rivera — account lead", "MF-CHI-1", "Meridian Chicago Processing", "1250 Lakeview Industrial Way", "Chicago", "IL", 41.7619, -87.6056, "food processing", "precast concrete", 2015, 186000, "TPO membrane", "current sprinkler certificate; sanitation systems", 34_000_000, 22_000_000, 10_000_000, 13_000_000, 52),
    ("Meridian Food Systems", "Food processing", "311999", "Casey Rivera — account lead", "MF-FRE-2", "Meridian Fresno Cold Chain", "4600 Valley Logistics Drive", "Fresno", "CA", 36.7378, -119.7871, "cold storage food distribution", "insulated concrete panel", 2019, 132000, "standing seam metal", "sprinklers current; refrigeration maintenance review", 27_000_000, 18_000_000, 16_000_000, 9_000_000, 66),
    ("Meridian Food Systems", "Food processing", "311999", "Casey Rivera — account lead", "MF-ATL-3", "Meridian Atlanta Packaging", "8100 Peachtree Commerce Park", "Atlanta", "GA", 33.7490, -84.3880, "food packaging", "masonry non-combustible", 2007, 118000, "single-ply membrane", "current sprinkler certificate", 21_000_000, 14_000_000, 8_000_000, 7_000_000, 47),
    ("LoomWorks Textiles", "Technical textiles", "313210", "Taylor Brooks — account lead", "LW-CLT-1", "LoomWorks Charlotte Mill", "2200 Innovation Textile Road", "Charlotte", "NC", 35.2271, -80.8431, "technical textile manufacturing", "heavy timber with upgrades", 1994, 214000, "metal panel roof", "fire pump tested; lint control review open", 25_000_000, 31_000_000, 12_000_000, 11_000_000, 72),
    ("LoomWorks Textiles", "Technical textiles", "313210", "Taylor Brooks — account lead", "LW-GRE-2", "LoomWorks Greenville Finishing", "90 Textile Exchange Boulevard", "Greenville", "SC", 34.8526, -82.3940, "textile finishing", "masonry non-combustible", 2010, 164000, "TPO membrane", "current sprinkler certificate", 22_000_000, 25_000_000, 9_000_000, 10_000_000, 57),
    ("Apex Precision Systems", "Precision machining", "332710", "Jamie Foster — account lead", "AP-DET-1", "Apex Detroit Machining", "4100 Motor Works Avenue", "Detroit", "MI", 42.3314, -83.0458, "precision machining", "protected steel", 2017, 172000, "standing seam metal", "current sprinkler certificate; coolant containment inspected", 29_000_000, 46_000_000, 9_000_000, 14_000_000, 54),
    ("Apex Precision Systems", "Precision machining", "332710", "Jamie Foster — account lead", "AP-CLE-2", "Apex Cleveland Components", "880 Foundry Technology Drive", "Cleveland", "OH", 41.4993, -81.6944, "precision component manufacturing", "reinforced concrete", 2008, 148000, "TPO membrane", "sprinklers current; compressor maintenance due", 24_000_000, 39_000_000, 8_000_000, 11_000_000, 62),
    ("Cobalt Distribution", "Industrial distribution", "493110", "Drew Coleman — account lead", "CB-CIN-1", "Cobalt Cincinnati Distribution", "2700 River Commerce Parkway", "Cincinnati", "OH", 39.1031, -84.5120, "industrial distribution warehouse", "tilt-up concrete", 2013, 246000, "TPO membrane", "current sprinkler certificate; dock protection review", 32_000_000, 12_000_000, 28_000_000, 10_000_000, 59),
    ("Cobalt Distribution", "Industrial distribution", "493110", "Drew Coleman — account lead", "CB-STL-2", "Cobalt St. Louis Fulfillment", "620 Gateway Logistics Court", "St. Louis", "MO", 38.6270, -90.1994, "industrial fulfillment warehouse", "protected steel", 2020, 218000, "standing seam metal", "current sprinkler and dock-door inspection", 30_000_000, 10_000_000, 25_000_000, 9_000_000, 43),
]

MACHINE_CLAIM_SCENARIOS = [
    ("AR-CLM-1001", "NS-HOU-A", "water", "CNC machining center water exposure reported after a localized production-zone leak; condition images require human verification.", ["equipment", "business_income"], "cnc-machining-center", 1, 2),
    ("PC-CLM-2001", "RC-SAC-1", "fire", "Electrical distribution panel fire reported in the production utility area; adjacent equipment condition remains under specialist review.", ["building", "equipment"], "electrical-distribution-panel", 3, 4),
    ("PC-CLM-2002", "MF-FRE-2", "water", "Sprinkler valve assembly leakage and corrosion reported during protection-system inspection; impairment scope requires confirmation.", ["building", "equipment"], "sprinkler-valve-assembly", 5, 6),
    ("PC-CLM-2003", "CB-CIN-1", "impact", "Loading-bay roll-up door impact reported after dock operations; access and repair scope remain under review.", ["building", "business_income"], "loading-bay-door", 7, 8),
    ("PC-CLM-2004", "AP-CLE-2", "water", "Compressed-air system water exposure and corrosion reported after a utility-room leak; operational effect requires engineering review.", ["equipment", "business_income"], "air-compressor-system", 9, 10),
]


def _fixture_pdf() -> Path:
    path = Path(__file__).parent / "fixtures" / "synthetic_inspection.pdf"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "SYNTHETIC INSPECTION REPORT — NorthStar Factory A", fontsize=14)
        page.insert_text((72, 110), "Inspection date: 2024-04-18\nFire protection certificate reviewed: expired 2024-06-30.\nSite record states renewal current, creating a chronology conflict.\nRecommendation: obtain current certificate and qualified specialist review.\nThis fixture contains synthetic demo data only.", fontsize=10)
        pdf.save(path)
        pdf.close()
    return path


def _category_payload(prop: Property, number: int) -> dict:
    payloads = {
        1: {"company_id": prop.company_id, "synthetic": True},
        2: {"site_code": prop.site_code, "coordinates": [prop.longitude, prop.latitude]},
        3: {"construction": prop.construction, "year_built": prop.year_built, "area_sqft": prop.area_sqft},
        4: {"roof": prop.roof, "condition": "reviewed in synthetic seed"},
        5: {"occupancy": prop.occupancy, "operations": prop.operations},
        6: {"protection": prop.protection},
        7: {"building_value_cents": prop.building_value_cents, "currency": "USD"},
        8: {"equipment_value_cents": prop.equipment_value_cents, "currency": "USD"},
        9: {"contents_value_cents": prop.contents_value_cents, "currency": "USD"},
        10: {"business_income_cents": prop.business_income_cents, "currency": "USD"},
        11: {"policy_status": "demo_active", "simulated": True},
        12: {"loss_history_source": "synthetic generated history"},
        13: {"inspection_status": "seeded"},
        14: prop.baseline_hazards,
        15: {"active_threat_state": "monitored", "events_do_not_confirm_damage": True},
    }
    return payloads[number]


def seed_database(db: Session) -> dict[str, int]:
    if db.scalar(select(func.count()).select_from(Company)):
        return summary(db)
    rng = random.Random(20261017)
    company_rows: list[Company] = []
    for name, industry, naics, broker in COMPANIES:
        company = Company(name=name, industry=industry, naics=naics, broker_contact=broker)
        db.add(company)
        company_rows.append(company)
    db.flush()
    properties: list[Property] = []
    company_indexes = [0, 0, 0, 1, 1, 1, 2, 2, 3, 3]
    for company_index, row in zip(company_indexes, PROPERTIES, strict=True):
        code, name, address, city, region, lat, lon, occupancy, construction, built, area, roof, protection, building, equipment, contents, bi, score = row
        prop = Property(company_id=company_rows[company_index].id, site_code=code, name=name, address=address, city=city, region=region, latitude=lat, longitude=lon, occupancy=occupancy, construction=construction, year_built=built, area_sqft=area, floors_count=1, roof=roof, protection=protection, operations=f"Synthetic {occupancy} operations", building_value_cents=building * 100, equipment_value_cents=equipment * 100, contents_value_cents=contents * 100, business_income_cents=bi * 100, baseline_hazards={"flood": "moderate" if region in {"TX", "GA", "NJ"} else "low", "wildfire": "moderate" if region in {"CA", "AZ"} else "low", "source": "synthetic baseline"}, risk_score=score)
        db.add(prop)
        properties.append(prop)
    db.flush()
    inspection_pdf = _fixture_pdf()
    inspection_doc = Document(company_id=company_rows[0].id, property_id=properties[0].id, filename=inspection_pdf.name, media_type="application/pdf", classification="inspection_report", storage_path=str(inspection_pdf.resolve()), sha256=hashlib.sha256(inspection_pdf.read_bytes()).hexdigest(), size_bytes=inspection_pdf.stat().st_size, uploader="seed", source_mode="synthetic")
    db.add(inspection_doc)
    db.flush()
    for prop in properties:
        for category, name in enumerate(CATEGORY_NAMES, 1):
            db.add(RiskDataRecord(company_id=prop.company_id, property_id=prop.id, category=category, category_name=name, data=_category_payload(prop, category), source_type="synthetic_seed", source_document_id=inspection_doc.id if prop.id == properties[0].id and category in {6, 13} else None, observed_at=NOW - timedelta(days=30), received_at=NOW - timedelta(days=29), effective_at=NOW - timedelta(days=30), last_verified_at=NOW - timedelta(days=10), verification_status="needs_review" if prop.id == properties[0].id and category == 6 else "verified", revision=1, created_by="deterministic_seed", updated_by="deterministic_seed"))
        building = Building(property_id=prop.id, name="Main Building")
        db.add(building)
        for asset_number in range(1, 7):
            db.add(Asset(property_id=prop.id, asset_code=f"{prop.site_code}-A{asset_number:02}", name=["CNC machining center", "Electrical switchgear", "Air compressor", "Production line", "Finished goods rack", "Fire pump"][asset_number - 1], asset_type=["machine", "electrical", "utility", "production", "inventory", "fire_safety"][asset_number - 1], insured_value_cents=(250_000 + asset_number * 175_000) * 100, owner="Named insured — synthetic", criticality="high" if asset_number in {1, 2, 4} else "medium"))
        policy = Policy(company_id=prop.company_id, property_id=prop.id, policy_number=f"DEMO-{prop.site_code}-2026", status="demo_active", effective_at=NOW - timedelta(days=180), expires_at=NOW + timedelta(days=185), simulated=True)
        db.add(policy)
        db.flush()
        db.add_all([
            Coverage(policy_id=policy.id, coverage_type="commercial_property", limit_cents=(prop.building_value_cents + prop.equipment_value_cents + prop.contents_value_cents), deductible_cents=250_000_00, excluded_perils=["synthetic exclusions require human coverage review"]),
            Coverage(policy_id=policy.id, coverage_type="business_income", limit_cents=prop.business_income_cents, deductible_cents=0, excluded_perils=[]),
        ])
    inspection = Inspection(property_id=properties[0].id, inspection_type="fire_protection", inspected_at=NOW - timedelta(days=913), expires_at=NOW - timedelta(days=474), status="expired_conflict", source_document_id=inspection_doc.id)
    db.add(inspection)
    db.flush()
    db.add(SafetyFinding(inspection_id=inspection.id, property_id=properties[0].id, finding="Fire protection certificate dates conflict with site record; obtain current evidence.", severity="high", due_at=NOW - timedelta(days=430), status="open"))
    perils = ["water", "fire", "wind", "hail", "theft"]
    occupancies = ["heavy manufacturing", "warehouse", "electronics manufacturing", "retail"]
    for index in range(150):
        peril = rng.choice(perils)
        occupancy = rng.choice(occupancies)
        value = rng.randint(3_000_000, 100_000_000) * 100
        equipment = rng.randint(500_000, 45_000_000) * 100
        damaged = rng.randint(0, 9)
        repair = rng.randint(0 if damaged == 0 else 20_000, max(25_000, damaged * 500_000)) * 100
        gross = repair + rng.randint(5_000, 800_000) * 100
        db.add(HistoricalClaim(synthetic_key=f"HIST-{index:04}", peril=peril, occupancy=occupancy, property_value_cents=value, equipment_value_cents=equipment, damaged_asset_count=damaged, documented_repair_cents=repair, gross_loss_cents=gross, reserve_cents=int(gross * rng.uniform(.9, 1.4)), final_paid_cents=int(gross * rng.uniform(.55, 1.0))))
    hazard = HazardEvent(provider="Property2Claim replay fixture", provider_event_id="REPLAY-SEVERE-2026-01", event_type="severe_weather", title="Severe weather corridor replay", severity="severe", geometry={"type": "MultiPolygon", "coordinates": [[[[-95.55, 29.60], [-95.15, 29.60], [-95.15, 29.90], [-95.55, 29.90], [-95.55, 29.60]]], [[[-96.15, 36.00], [-95.80, 36.00], [-95.80, 36.30], [-96.15, 36.30], [-96.15, 36.00]]]]}, valid_at=NOW - timedelta(days=14), source_mode="replay")
    db.add(hazard)
    db.flush()
    policies = db.scalars(select(Policy).order_by(Policy.id)).all()
    claim_specs = [
        (properties[0], policies[0], "AR-CLM-1001", "water", "Water leak reported in production zone. Maintenance entry dates conflict; machine repair quotation is missing.", ["building", "equipment", "business_income"], "Maintenance chronology contains an earlier leak reference that conflicts with the reported onset."),
        (properties[3], policies[3], "AR-CLM-1002", "wind", "Synthetic storm roof damage report with conflicting inspection dates.", ["building", "contents"], "Roof inspection dates require reconciliation."),
        (properties[5], policies[5], "AR-CLM-1003", "fire", "Small contained warehouse fire reported; specialist review is required.", ["building", "contents", "business_income"], None),
    ]
    claims: list[Claim] = []
    for index, (prop, policy, number, peril, narrative, exposures, contradiction) in enumerate(claim_specs):
        claim = Claim(company_id=prop.company_id, property_id=prop.id, policy_id=policy.id, claim_number=number, loss_at=NOW - timedelta(days=7 + index), peril=peril, narrative=narrative, status="reported", contradiction_summary=contradiction)
        db.add(claim)
        db.flush()
        for exposure in exposures:
            db.add(ClaimExposure(claim_id=claim.id, exposure_type=exposure, state="reported"))
        claims.append(claim)
    submission = UnderwritingSubmission(company_id=properties[0].company_id, property_id=properties[0].id, status="draft")
    db.add(submission)
    db.flush()
    db.commit()
    run_underwriting(db, submission)
    run_claim(db, claims[0], "seed_scenario")
    create_estimate(db, claims[0])
    db.add(AuditEvent(company_id=None, subject_type="system", subject_id=0, event_type="deterministic_seed_completed", actor="seed", source="synthetic", details={"seed": 20261017, "synthetic_only": True}))
    db.commit()
    return summary(db)


def ensure_portfolio_extension(db: Session) -> dict[str, int]:
    """Add the additional polished-demo accounts without touching existing records."""
    replay = db.scalar(select(HazardEvent).where(HazardEvent.provider_event_id == "REPLAY-SEVERE-2026-01"))
    if replay and replay.provider.endswith("replay fixture") and replay.provider != "Property2Claim replay fixture":
        replay.provider = "Property2Claim replay fixture"
        replay.title = "Severe weather corridor replay"
        replay.source_mode = "replay"
    for row in PORTFOLIO_EXTENSION:
        company_name, industry, naics, contact, code, name, address, city, region, lat, lon, occupancy, construction, built, area, roof, protection, building_value, equipment_value, contents_value, bi_value, risk_score = row
        company = db.scalar(select(Company).where(Company.name == company_name))
        if not company:
            company = Company(name=company_name, industry=industry, naics=naics, broker_contact=contact)
            db.add(company)
            db.flush()
        prop = db.scalar(select(Property).where(Property.site_code == code))
        if prop:
            continue
        prop = Property(company_id=company.id, site_code=code, name=name, address=address, city=city, region=region, latitude=lat, longitude=lon, occupancy=occupancy, construction=construction, year_built=built, area_sqft=area, floors_count=1, roof=roof, protection=protection, operations=f"{occupancy.title()} operations", building_value_cents=building_value * 100, equipment_value_cents=equipment_value * 100, contents_value_cents=contents_value * 100, business_income_cents=bi_value * 100, baseline_hazards={"flood": "moderate" if region in {"GA", "SC", "NC"} else "low", "wildfire": "moderate" if region == "CA" else "low", "source": "portfolio baseline"}, risk_score=risk_score)
        db.add(prop)
        db.flush()
        for category, category_name in enumerate(CATEGORY_NAMES, 1):
            db.add(RiskDataRecord(company_id=company.id, property_id=prop.id, category=category, category_name=category_name, data=_category_payload(prop, category), source_type="seeded_portfolio", observed_at=NOW - timedelta(days=30), received_at=NOW - timedelta(days=29), effective_at=NOW - timedelta(days=30), last_verified_at=NOW - timedelta(days=10), verification_status="needs_review" if category in {4, 6} and risk_score >= 65 else "verified", revision=1, created_by="portfolio_extension", updated_by="portfolio_extension"))
        building = Building(property_id=prop.id, name="Primary facility")
        db.add(building)
        asset_names = ["Production line", "Electrical switchgear", "Air compressor", "Critical process equipment", "Finished goods rack", "Fire pump"]
        for asset_number, asset_name in enumerate(asset_names, 1):
            db.add(Asset(property_id=prop.id, asset_code=f"{prop.site_code}-A{asset_number:02}", name=asset_name, asset_type=["machine", "electrical", "utility", "production", "inventory", "fire_safety"][asset_number - 1], insured_value_cents=(250_000 + asset_number * 175_000) * 100, owner="Named insured", criticality="high" if asset_number in {1, 2, 4} else "medium"))
        policy = Policy(company_id=company.id, property_id=prop.id, policy_number=f"PC-{prop.site_code}-2026", status="active", effective_at=NOW - timedelta(days=180), expires_at=NOW + timedelta(days=185), simulated=True)
        db.add(policy)
        db.flush()
        db.add_all([
            Coverage(policy_id=policy.id, coverage_type="commercial_property", limit_cents=prop.building_value_cents + prop.equipment_value_cents + prop.contents_value_cents, deductible_cents=250_000_00, excluded_perils=["Terms require authorized coverage review"]),
            Coverage(policy_id=policy.id, coverage_type="business_income", limit_cents=prop.business_income_cents, deductible_cents=0, excluded_perils=[]),
        ])
        db.add(AuditEvent(company_id=company.id, subject_type="property", subject_id=prop.id, event_type="portfolio_site_added", actor="seed", source="seeded_portfolio", details={"site_code": code, "profile_image_category": occupancy}))
    db.commit()
    ensure_machine_claims(db)
    return summary(db)


def ensure_machine_claims(db: Session) -> None:
    """Attach the user-supplied paired machine scenarios without claiming vision verification."""
    media_dir = Path(__file__).parent / "fixtures" / "machine_claims"
    for index, (claim_number, site_code, peril, narrative, exposures, asset_slug, before_number, after_number) in enumerate(MACHINE_CLAIM_SCENARIOS):
        prop = db.scalar(select(Property).where(Property.site_code == site_code))
        if not prop:
            continue
        policy = db.scalar(select(Policy).where(Policy.property_id == prop.id).order_by(Policy.id.desc()))
        if not policy:
            continue
        claim = db.scalar(select(Claim).where(Claim.claim_number == claim_number))
        created_claim = claim is None
        if not claim:
            claim = Claim(
                company_id=prop.company_id,
                property_id=prop.id,
                policy_id=policy.id,
                claim_number=claim_number,
                loss_at=NOW - timedelta(days=3 + index),
                peril=peril,
                narrative=narrative,
                status="reported",
                contradiction_summary=None,
            )
            db.add(claim)
            db.flush()
            for exposure in exposures:
                db.add(ClaimExposure(claim_id=claim.id, exposure_type=exposure, state="reported"))
        else:
            claim.narrative = narrative

        for role, sequence in (("condition_before", before_number), ("condition_after", after_number)):
            path = media_dir / f"{asset_slug}-{role}.png"
            if not path.is_file():
                continue
            existing = db.scalar(select(Document).where(Document.claim_id == claim.id, Document.classification == role))
            if existing:
                continue
            content = path.read_bytes()
            document = Document(
                company_id=prop.company_id,
                property_id=prop.id,
                claim_id=claim.id,
                filename=path.name,
                media_type="image/png",
                classification=role,
                storage_path=str(path.resolve()),
                sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                uploader="user supplied scenario set",
                source_mode="user_supplied_scenario",
                analysis_status="retained_requires_human_verification",
            )
            db.add(document)
            db.flush()
            db.add(EvidenceFact(
                document_id=document.id,
                subject_type="claim",
                subject_id=claim.id,
                fact_type="media_context",
                value={"asset": asset_slug.replace("-", " "), "sequence": role, "source": "user supplied scenario image", "vision_analysis_performed": False},
                evidence_location=f"original image {sequence} of 10",
                verified=False,
            ))
            db.add(AuditEvent(
                company_id=prop.company_id,
                subject_type="claim",
                subject_id=claim.id,
                event_type="scenario_media_linked",
                actor="seed",
                source="user_supplied_scenario",
                details={"document_id": document.id, "classification": role, "asset": asset_slug, "human_verification_required": True},
            ))
        db.commit()
        if created_claim:
            run_claim(db, claim, "machine_scenario_intake")


def summary(db: Session) -> dict[str, int]:
    return {
        "companies": db.scalar(select(func.count()).select_from(Company)) or 0,
        "properties": db.scalar(select(func.count()).select_from(Property)) or 0,
        "historical_claims": db.scalar(select(func.count()).select_from(HistoricalClaim)) or 0,
        "claims": db.scalar(select(func.count()).select_from(Claim)) or 0,
        "risk_records": db.scalar(select(func.count()).select_from(RiskDataRecord)) or 0,
    }
