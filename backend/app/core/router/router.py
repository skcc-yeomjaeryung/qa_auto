from __future__ import annotations

from dataclasses import dataclass

from app.core.workflow_registry import WorkflowRegistry


@dataclass
class RouteDecision:
    workflow_id: str
    modality: str = "execute"


class Router:
    """Minimal router: explicit workflowId only (no inventing Hub assets)."""

    def __init__(self, workflows: WorkflowRegistry) -> None:
        self.workflows = workflows

    def route(self, workflow_id: str) -> RouteDecision:
        self.workflows.require(workflow_id)
        return RouteDecision(workflow_id=workflow_id, modality="execute")
