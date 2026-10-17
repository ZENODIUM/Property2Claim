from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings


@dataclass
class DecisionResult:
    answer: str
    source: str
    provider: str
    trace: dict[str, Any]


class JevDecisionModel:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def request_payload(question: str, choices: list[str], context: dict[str, Any], model: str) -> dict[str, Any]:
        return {
            "model": model,
            "input": {"context": context},
            "questions": [{"id": "route", "type": "choice", "question": question, "choices": choices}],
        }

    @staticmethod
    def noul_payload(question: str, context: dict[str, Any], model: str) -> dict[str, Any]:
        """Build a bounded yes/no/uncertain/likely judgment using Jev's `noul` primitive."""
        return {
            "model": model,
            "input": {"context": context},
            "questions": [{"id": "evidence_support", "type": "noul", "question": question}],
        }

    def decide(self, question: str, choices: list[str], context: dict[str, Any], fallback: str) -> DecisionResult:
        if not self.settings.jev_api_key:
            return DecisionResult(fallback, "mock/rules", "deterministic", {"reason": "JEV_API_KEY absent"})
        payload = self.request_payload(question, choices, context, self.settings.jev_model)
        try:
            response = httpx.post(
                self.settings.jev_api_base_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.settings.jev_api_key}"},
                timeout=8,
            )
            response.raise_for_status()
            body = response.json()
            answer = body.get("answers", {}).get("route") or body.get("answer")
            if answer not in choices:
                raise ValueError("Jev returned an answer outside allowed labels")
            return DecisionResult(answer, "live", "jev", {"model": self.settings.jev_model})
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return DecisionResult(fallback, "mock/rules", "deterministic", {"reason": type(exc).__name__})


def route_submission(settings: Settings, missing: list[str], has_conflict: bool) -> DecisionResult:
    fallback = "incomplete" if missing else "engineering_specialist" if has_conflict else "standard"
    return JevDecisionModel(settings).decide(
        "Select the bounded underwriting review queue. This is not an approval decision.",
        ["standard", "engineering_specialist", "manual_review", "incomplete"],
        {"missing_items": missing, "protection_conflict": has_conflict, "synthetic": True},
        fallback,
    )


def route_claim(settings: Settings, missing_quote: bool, exposures: list[str]) -> DecisionResult:
    fallback = "needs_information" if missing_quote else "business_income_specialist" if "business_income" in exposures else "standard_adjuster"
    return JevDecisionModel(settings).decide(
        "Select the bounded claim handling queue. Do not decide coverage, payment, or denial.",
        ["standard_adjuster", "equipment_specialist", "business_income_specialist", "needs_information"],
        {"missing_repair_quote": missing_quote, "exposures": exposures, "synthetic": True},
        fallback,
    )
