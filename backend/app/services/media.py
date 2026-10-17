from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import HTTPException

from ..ai.provider_adapters import GeminiVisionModel
from ..config import Settings


@dataclass(frozen=True)
class FrameSamplingConfig:
    interval_seconds: int = 10
    max_frames: int = 12

    def __post_init__(self) -> None:
        if not 1 <= self.interval_seconds <= 300 or not 1 <= self.max_frames <= 30:
            raise ValueError("Frame sampling limits exceeded")


class MediaAnalysisService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.vision = GeminiVisionModel(settings)

    def analyze_image(self, media_id: int, path: Path, *, explicitly_authorized: bool = False) -> dict[str, Any]:
        if self.settings.gemini_api_key and not explicitly_authorized:
            raise HTTPException(409, "External vision analysis requires explicit authorization")
        return self.vision.analyze_image(path, media_id)

    def analyze_video(self, media_id: int, path: Path, config: FrameSamplingConfig, *, explicitly_authorized: bool = False) -> dict[str, Any]:
        if not explicitly_authorized:
            raise HTTPException(409, "Video frame analysis requires explicit authorization")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(503, "ffmpeg is not installed; video is safely retained without analysis")
        with TemporaryDirectory(prefix="property2claim-frames-") as temp:
            output = Path(temp) / "frame-%03d.jpg"
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-vf", f"fps=1/{config.interval_seconds}", "-frames:v", str(config.max_frames), str(output)],
                check=True, timeout=120, capture_output=True,
            )
            frames = sorted(Path(temp).glob("frame-*.jpg"))[: config.max_frames]
            analyses = [self.vision.analyze_image(frame, media_id) | {"timestamp_seconds": index * config.interval_seconds} for index, frame in enumerate(frames)]
        return {"media_id": media_id, "frames_sampled": len(analyses), "sampling": {"interval_seconds": config.interval_seconds, "max_frames": config.max_frames}, "analyses": analyses, "human_verification_required": True}


class FloorPlanDetectionService:
    def __init__(self, settings: Settings):
        self.media = MediaAnalysisService(settings)

    def propose_annotations(self, floorplan_id: int, preview_path: Path, plan_type: str = "base", *, explicitly_authorized: bool = False) -> dict[str, Any]:
        if self.media.settings.gemini_api_key and not explicitly_authorized:
            raise HTTPException(409, "External floor-plan analysis requires explicit authorization")
        analysis = self.media.vision.analyze_floorplan(preview_path, floorplan_id, plan_type)
        proposals = []
        for item in analysis.get("annotations", []):
            ymin, xmin, ymax, xmax = item["box_2d"]
            proposals.append({
                "object_type": item["object_type"],
                "label": item["label"],
                "geometry_type": "rect",
                "geometry": {
                    "x": round(xmin / 1000, 4),
                    "y": round(ymin / 1000, 4),
                    "w": round((xmax - xmin) / 1000, 4),
                    "h": round((ymax - ymin) / 1000, 4),
                },
                "layer": item["layer"],
                "human_verified": False,
                "source_mode": "gemini_live" if analysis["mode"] == "live" else "prepared_fixture",
                "analysis_model": analysis.get("model"),
                "confidence_label": item["confidence_label"],
                "details": {
                    "visible_evidence": item["visible_evidence"],
                    "source_plan_type": plan_type,
                    "human_verification_required": True,
                },
            })
        return {
            "floorplan_id": floorplan_id,
            "proposals": proposals,
            "drawing_summary": analysis.get("drawing_summary"),
            "limitations": analysis.get("limitations", []),
            "mode": analysis["mode"],
            "model": analysis.get("model"),
            "human_verification_required": True,
            "note": "Proposed boxes are cached after analysis and remain unverified until a reviewer confirms them.",
        }
