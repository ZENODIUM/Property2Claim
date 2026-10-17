from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class WorkflowState(TypedDict, total=False):
    subject_id: int
    missing_items: list[str]
    conflicts: list[str]
    exposures: list[str]
    matched_property_ids: list[int]
    route: str
    steps: list[str]
    status: str


def _step(name: str):
    def node(state: WorkflowState) -> dict[str, Any]:
        return {"steps": [*(state.get("steps") or []), name]}
    return node


def _uw_route(state: WorkflowState) -> str:
    return "missing" if state.get("missing_items") else "ready"


uw = StateGraph(WorkflowState)
for node in ["collect", "parse", "validate", "cope", "jev_route", "draft_request", "pricing_scenario", "human_checkpoint"]:
    uw.add_node(node, _step(node))
uw.add_edge(START, "collect")
uw.add_edge("collect", "parse")
uw.add_edge("parse", "validate")
uw.add_edge("validate", "cope")
uw.add_edge("cope", "jev_route")
uw.add_conditional_edges("jev_route", _uw_route, {"missing": "draft_request", "ready": "pricing_scenario"})
uw.add_edge("draft_request", "human_checkpoint")
uw.add_edge("pricing_scenario", "human_checkpoint")
uw.add_edge("human_checkpoint", END)
underwriting_graph = uw.compile()


haz = StateGraph(WorkflowState)
for node in ["ingest_event", "normalize", "match_locations", "rank_attention", "draft_tasks", "human_checkpoint", "record"]:
    haz.add_node(node, _step(node))
haz.add_edge(START, "ingest_event")
haz.add_edge("ingest_event", "normalize")
haz.add_edge("normalize", "match_locations")
haz.add_edge("match_locations", "rank_attention")
haz.add_edge("rank_attention", "draft_tasks")
haz.add_edge("draft_tasks", "human_checkpoint")
haz.add_edge("human_checkpoint", "record")
haz.add_edge("record", END)
hazard_graph = haz.compile()


def _claim_route(state: WorkflowState) -> str:
    route = state.get("route", "needs_information")
    return "need_evidence" if route == "needs_information" else "specialist" if route in {"equipment_specialist", "business_income_specialist"} else "estimate"


clm = StateGraph(WorkflowState)
for node in ["fnol", "check_policy", "extract_evidence", "spatial_candidates", "reconcile", "jev_route", "draft_request", "specialist_review", "estimate", "human_checkpoint", "audit"]:
    clm.add_node(node, _step(node))
clm.add_edge(START, "fnol")
clm.add_edge("fnol", "check_policy")
clm.add_edge("check_policy", "extract_evidence")
clm.add_edge("extract_evidence", "spatial_candidates")
clm.add_edge("spatial_candidates", "reconcile")
clm.add_edge("reconcile", "jev_route")
clm.add_conditional_edges("jev_route", _claim_route, {"need_evidence": "draft_request", "specialist": "specialist_review", "estimate": "estimate"})
clm.add_edge("draft_request", "human_checkpoint")
clm.add_edge("specialist_review", "human_checkpoint")
clm.add_edge("estimate", "human_checkpoint")
clm.add_edge("human_checkpoint", "audit")
clm.add_edge("audit", END)
claims_graph = clm.compile()

