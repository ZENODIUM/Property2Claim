from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..config import Settings


@dataclass
class TextResult:
    text: str
    mode: str
    model: str


class MockTextModel:
    def summarize(self, facts: list[str]) -> TextResult:
        return TextResult("Synthetic evidence summary: " + "; ".join(facts[:4]), "mock", "deterministic-template")


class GroqTextModel:
    """Optional focused text adapter. Import and network use occur only with a configured key."""
    def __init__(self, settings: Settings):
        self.settings = settings

    def summarize(self, facts: list[str]) -> TextResult:
        if not self.settings.groq_api_key:
            return MockTextModel().summarize(facts)
        try:
            from groq import Groq  # optional dependency

            client = Groq(api_key=self.settings.groq_api_key)
            result = client.chat.completions.create(
                model=self.settings.groq_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": "Summarize only supplied synthetic insurance facts. Never decide coverage, approval, denial, or payment."},
                    {"role": "user", "content": "\n".join(facts)},
                ],
            )
            return TextResult(result.choices[0].message.content or "", "live", self.settings.groq_model)
        except Exception:
            return MockTextModel().summarize(facts)


class MockVisionModel:
    def analyze(self, media_id: int) -> dict[str, Any]:
        return {
            "media_id": media_id,
            "observations": [],
            "potential_asset_tags": [],
            "limitations": ["Mock schema result only; no visual interpretation was performed."],
            "evidence_refs": [],
            "mode": "mock",
        }


class VisionObservation(BaseModel):
    description: str = Field(max_length=500)
    confidence_label: str = Field(description="One of low, medium, or high")


class VisionAnalysis(BaseModel):
    observations: list[VisionObservation]
    potential_asset_tags: list[str]
    limitations: list[str]
    evidence_refs: list[str]


class FloorPlanAnnotation(BaseModel):
    # Keep the provider schema intentionally simple; Gemini supports only a
    # subset of JSON Schema. Values are constrained again after parsing.
    label: str
    object_type: str
    layer: str
    box_2d: list[int]
    confidence_label: str
    visible_evidence: str


class FloorPlanVisionAnalysis(BaseModel):
    drawing_summary: str
    annotations: list[FloorPlanAnnotation]
    limitations: list[str]


class GeminiVisionModel:
    def __init__(self, settings: Settings):
        self.settings = settings

    def status(self) -> dict[str, Any]:
        return {"configured": bool(self.settings.gemini_api_key), "model": self.settings.gemini_model, "real_media_validation": "PENDING_USER_FIXTURES"}

    def analyze_image(self, path: Path, media_id: int) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            return MockVisionModel().analyze(media_id)
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.settings.gemini_api_key)
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=path.read_bytes(), mime_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg"),
                "Analyze this authorized synthetic insurance image conservatively. Report visible observations only; do not decide cause, coverage, damage amount, payment, or denial. Include limitations and evidence references.",
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=VisionAnalysis),
        )
        parsed = VisionAnalysis.model_validate_json(response.text or "{}")
        return {"media_id": media_id, **parsed.model_dump(), "mode": "live", "model": self.settings.gemini_model, "human_verification_required": True}

    def analyze_floorplan(self, path: Path, floorplan_id: int, plan_type: str) -> dict[str, Any]:
        """Extract conservative, normalized boxes from an explicitly authorized drawing.

        This is deliberately a proposal generator. The geometry is persisted for
        review and never represents certified measurements or confirmed damage.
        """
        if not self.settings.gemini_api_key:
            return {
                "floorplan_id": floorplan_id,
                "drawing_summary": "No visual interpretation was performed.",
                "annotations": [],
                "limitations": ["Gemini is not configured."],
                "mode": "mock",
                "model": "mock-schema",
                "human_verification_required": True,
            }
        from google import genai
        from google.genai import types

        role_instructions = {
            "base": "Detect the major labelled building rooms and operating zones. Use one tight box per named room or zone; do not mark furniture or drawing legends.",
            "machinery": "Detect named machines, equipment, production lines, material racks, electrical panels, compressors, pumps, and utility equipment. Prefer the printed equipment label and a tight box around the corresponding symbol.",
            "emergency": "Detect emergency exits, fire extinguishers, fire alarm panels, fire hose cabinets, fire department connections, exterior hydrants, and major labelled fire-protection zones. Do not return every sprinkler head; return representative safety equipment and zone boundaries.",
            "reference": "Detect only clearly labelled operational or safety objects relevant to commercial property insurance.",
        }
        prompt = f"""
You are extracting clickable map proposals from an authorized synthetic factory floor-plan drawing.
{role_instructions.get(plan_type, role_instructions['reference'])}
Return each location as box_2d=[ymin,xmin,ymax,xmax] normalized to 0..1000 against the full image.
Allowed layers are machinery, fire_safety, utilities, and building_zones.
Be conservative: omit ambiguous marks, never infer damage or code compliance, and do not treat the legend as an installed object.
This is an assistive draft that a reviewer must verify, not a certified engineering interpretation.
""".strip()
        mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        candidates = []
        for model in [self.settings.gemini_floorplan_model, "gemini-3.8-flash", self.settings.gemini_model, "gemini-2.5-pro"]:
            if model and model not in candidates:
                candidates.append(model)
        client = genai.Client(api_key=self.settings.gemini_api_key)
        last_error: Exception | None = None
        for model in candidates:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type),
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=12_000,
                        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
                        response_mime_type="application/json",
                        response_schema=FloorPlanVisionAnalysis,
                    ),
                )
                parsed = FloorPlanVisionAnalysis.model_validate_json(response.text or "{}")
                clean = []
                allowed_layers = {"machinery", "fire_safety", "utilities", "building_zones"}
                for item in parsed.annotations[:40]:
                    if len(item.box_2d) != 4 or item.layer not in allowed_layers:
                        continue
                    ymin, xmin, ymax, xmax = item.box_2d
                    if not all(0 <= value <= 1000 for value in item.box_2d):
                        continue
                    if ymax <= ymin or xmax <= xmin:
                        continue
                    clean.append({
                        "label": item.label[:120],
                        "object_type": item.object_type[:60],
                        "layer": item.layer,
                        "box_2d": item.box_2d,
                        "confidence_label": item.confidence_label if item.confidence_label in {"low", "medium", "high"} else "low",
                        "visible_evidence": item.visible_evidence[:300],
                    })
                return {
                    "floorplan_id": floorplan_id,
                    "drawing_summary": parsed.drawing_summary,
                    "annotations": clean,
                    "limitations": parsed.limitations,
                    "mode": "live",
                    "model": model,
                    "human_verification_required": True,
                }
            except Exception as exc:  # provider/model access varies by account
                last_error = exc
        raise RuntimeError(f"Gemini floor-plan analysis failed for all configured models: {type(last_error).__name__}")
