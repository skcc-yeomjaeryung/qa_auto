from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    workflow_id: str
    inputs: dict[str, Any]
    route: dict[str, Any]
    plan: dict[str, Any]
    step_results: list[dict[str, Any]]
    review_notes: list[str]
    summary: str
    status: str
    error: str
