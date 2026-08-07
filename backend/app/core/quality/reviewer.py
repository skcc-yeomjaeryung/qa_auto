from __future__ import annotations

from typing import Any

from app.core.observability import AgentEventStore
from app.core.prompts import PromptCatalog


class Reviewer:
    """Contract and evidence review only. It never declares HITL Pass/Fail."""

    def __init__(self, events: AgentEventStore | None = None, prompts: PromptCatalog | None = None) -> None:
        self.events = events
        self.prompts = prompts or PromptCatalog()

    def review(
        self,
        step_results: list[dict[str, Any]],
        *,
        trace_id: str | None = None,
        workflow_id: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        _, metadata = self.prompts.render(
            "agent_roles/evidence_reviewer_system.md",
            "실행 단계 수: {step_count}. 구조 계약과 evidence 참조를 점검하십시오.",
            step_count=len(step_results),
        )
        notes: list[str] = []
        if not step_results:
            notes.append("missing_data: no step results")
        for item in step_results:
            output = item.get("output") or {}
            if not output.get("ok"):
                notes.append(f"step {item.get('stepId')} output.ok is not true")
            if output.get("artifactPath") is None and isinstance(output.get("result"), dict):
                notes.append(f"step {item.get('stepId')} has inline result without artifact reference")
        if not notes:
            notes.append("structural_ok: schemas and tool status are valid (not HITL Pass)")
        if trace_id and self.events:
            self.events.record(
                trace_id=trace_id,
                event_type="review_completed",
                workflow_id=workflow_id,
                project_id=project_id,
                status="complete",
                summary=f"구조·증적 계약 검토를 완료했습니다: {len(notes)}개 메모.",
                details={"notes": notes, "prompt": metadata.__dict__},
            )
        return notes
