from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.bootstrap import get_runtime
from app.core.observability import TraceSummary

router = APIRouter(prefix="/api/agent-monitor", tags=["agent-monitor"])


class SelectionPreviewRequest(BaseModel):
    workflowId: str = "wf_scenario_dsl"
    projectId: str | None = None
    aiPolicy: str | None = None


@router.get("/summary")
def monitor_summary() -> dict[str, int]:
    return get_runtime().events.summary()


@router.get("/traces", response_model=list[TraceSummary])
def list_traces(
    projectId: str | None = Query(default=None),
    workflowId: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TraceSummary]:
    return get_runtime().events.traces(
        project_id=projectId,
        workflow_id=workflowId,
        status=status,
        limit=limit,
    )


@router.get("/traces/{trace_id}")
def trace_detail(trace_id: str) -> dict:
    item = get_runtime().events.trace_detail(trace_id)
    if item is None:
        raise HTTPException(status_code=404, detail="agent trace not found")
    return item


@router.post("/selection-preview")
def selection_preview(payload: SelectionPreviewRequest) -> dict:
    """Builds an auditable Plan without executing tools or changing project data."""
    from app.core.planning import Planner

    runtime = get_runtime()
    inputs = {"selectionPreview": True}
    if payload.projectId:
        inputs["projectId"] = payload.projectId
    if payload.aiPolicy:
        inputs["aiPolicy"] = payload.aiPolicy
    try:
        plan = Planner(
            runtime.workflows,
            runtime.skills,
            agents=runtime.agents,
            model_selector=runtime.model_selector,
            context_store=runtime.context,
            events=runtime.events,
        ).build(payload.workflowId, inputs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    runtime.events.record(
        trace_id=plan.planId,
        event_type="workflow_completed",
        workflow_id=plan.workflowId,
        project_id=payload.projectId,
        status="complete",
        summary="도구 실행 없이 모델·Skill 선택 미리보기를 완료했습니다.",
        details={"selectionPreview": True},
    )
    return {
        "traceId": plan.planId,
        "workflowId": plan.workflowId,
        "steps": [
            {
                "stepId": step.stepId,
                "capability": step.requiredCapability,
                "skill": step.skill,
                "tool": step.tool,
                "modelDecision": step.modelDecision.model_dump() if step.modelDecision else None,
            }
            for step in plan.steps
        ],
    }
