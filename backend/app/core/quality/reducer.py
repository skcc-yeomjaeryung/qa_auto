from __future__ import annotations

from typing import Any

from app.core.observability import AgentEventStore
from app.core.prompts import PromptCatalog
from app.schemas.plan import Plan


class Reducer:
    def __init__(self, events: AgentEventStore | None = None, prompts: PromptCatalog | None = None) -> None:
        self.events = events
        self.prompts = prompts or PromptCatalog()

    def reduce(
        self,
        plan: Plan,
        step_results: list[dict[str, Any]],
        notes: list[str],
        *,
        project_id: str | None = None,
    ) -> str:
        _, metadata = self.prompts.render(
            "agent_roles/context_reducer_system.md",
            "Workflow: {workflow_id}, 단계: {step_count}, 검토 메모: {note_count}",
            workflow_id=plan.workflowId,
            step_count=len(step_results),
            note_count=len(notes),
        )
        ok_count = sum(1 for result in step_results if (result.get("output") or {}).get("ok"))
        artifacts = [
            (result.get("output") or {}).get("artifactPath")
            for result in step_results
            if (result.get("output") or {}).get("artifactPath")
        ]
        summary = (
            f"workflow={plan.workflowId} plan={plan.planId} "
            f"steps={len(step_results)} ok={ok_count} "
            f"notes={len(notes)} artifacts={len(artifacts)} (HITL not decided)"
        )
        if self.events:
            self.events.record(
                trace_id=plan.planId,
                event_type="reduce_completed",
                workflow_id=plan.workflowId,
                project_id=project_id,
                status="complete",
                summary="다음 단계에 필요한 상태·artifact 참조만 남겼습니다.",
                details={
                    "stepCount": len(step_results),
                    "okCount": ok_count,
                    "artifactPaths": artifacts,
                    "reviewNoteCount": len(notes),
                    "prompt": metadata.__dict__,
                },
            )
        return summary
