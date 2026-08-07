from __future__ import annotations

from typing import Any

from app.langgraph_runtime.graph import get_plan_execution_graph
from app.schemas.plan import Plan, RunExecuteResponse


class AgentRuntime:
    """Stable Core facade for every menu/service Workflow execution."""

    def execute(self, workflow_id: str, inputs: dict[str, Any] | None = None) -> RunExecuteResponse:
        final = get_plan_execution_graph().invoke(
            {"workflow_id": workflow_id, "inputs": inputs or {}}
        )
        plan = Plan.model_validate(final["plan"])
        return RunExecuteResponse(
            status=str(final.get("status") or "complete"),
            plan=plan,
            stepResults=list(final.get("step_results") or []),
            summary=str(final.get("summary") or ""),
            reviewNotes=list(final.get("review_notes") or []),
        )

