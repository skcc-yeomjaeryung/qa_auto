from __future__ import annotations

from typing import Any

from app.core.runtime import AgentRuntime
from app.schemas.plan import RunExecuteResponse


class PlatformRunnerAdapter:
    """Thin adapter: invoke common plan_execution_graph only."""

    def execute(self, workflow_id: str, inputs: dict[str, Any] | None = None) -> RunExecuteResponse:
        return AgentRuntime().execute(workflow_id, inputs)
