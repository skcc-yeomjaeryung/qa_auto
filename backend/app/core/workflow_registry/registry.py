from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.paths import WORKFLOW_HUB


def _capability_ids(raw: list | None) -> list[str]:
    """교보재: [{capability_id: X}] 또는 레거시 문자열 모두 수용."""
    ids: list[str] = []
    for item in raw or []:
        if isinstance(item, dict) and item.get("capability_id"):
            ids.append(str(item["capability_id"]))
        elif isinstance(item, str):
            ids.append(item)
    return ids


@dataclass
class LogicalStep:
    step_id: str
    name: str
    required_capability: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    workflow_id: str
    name: str
    required_capabilities: list[str] = field(default_factory=list)
    logical_steps: list[LogicalStep] = field(default_factory=list)
    execution_pattern: str = "plan_execute_review_reduce"
    source_path: Path | None = None
    raw: dict = field(default_factory=dict)


class WorkflowRegistry:
    def __init__(self) -> None:
        self._items: dict[str, WorkflowDefinition] = {}

    def load(self, hub: Path | None = None) -> None:
        root = hub or WORKFLOW_HUB
        self._items.clear()
        for path in sorted(root.glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            wid = data.get("workflow_id")
            if not wid:
                raise ValueError(f"workflow_id missing: {path}")
            if "graph" in data or "nodes" in data or "edges" in data:
                raise ValueError(f"Workflow must not contain Graph fields: {path}")

            caps = _capability_ids(data.get("required_capabilities"))
            steps: list[LogicalStep] = []
            for step in data.get("logical_steps") or []:
                req = step.get("required_capability")
                if not req and isinstance(step.get("required_capabilities"), list):
                    nested = _capability_ids(step.get("required_capabilities"))
                    req = nested[0] if nested else None
                if not req:
                    raise ValueError(f"logical_steps.required_capability missing in {path}")
                steps.append(
                    LogicalStep(
                        step_id=str(step.get("step_id")),
                        name=str(step.get("name") or step.get("step_id")),
                        required_capability=str(req),
                        depends_on=[str(d) for d in (step.get("depends_on") or [])],
                    )
                )
            if not caps and steps:
                caps = [s.required_capability for s in steps]

            policy = data.get("execution_policy") or {}
            self._items[str(wid)] = WorkflowDefinition(
                workflow_id=str(wid),
                name=str(data.get("name") or wid),
                required_capabilities=caps,
                logical_steps=steps,
                execution_pattern=str(
                    policy.get("execution_pattern") or "plan_execute_review_reduce"
                ),
                source_path=path,
                raw=data,
            )

    def get(self, workflow_id: str) -> WorkflowDefinition | None:
        return self._items.get(workflow_id)

    def require(self, workflow_id: str) -> WorkflowDefinition:
        item = self.get(workflow_id)
        if not item:
            raise KeyError(f"Workflow not in Hub: {workflow_id}")
        return item

    def count(self) -> int:
        return len(self._items)

    def ids(self) -> list[str]:
        return sorted(self._items)
