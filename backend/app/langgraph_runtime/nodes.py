from __future__ import annotations

from app.core.bootstrap import get_runtime
from app.core.execution import Orchestrator
from app.core.planning import Planner
from app.core.quality import Reducer, Reviewer
from app.core.router import Router
from app.langgraph_runtime.state import GraphState
from app.schemas.plan import Plan


def route_node(state: GraphState) -> GraphState:
    runtime = get_runtime()
    decision = Router(runtime.workflows).route(state["workflow_id"])
    return {**state, "route": {"workflow_id": decision.workflow_id, "modality": decision.modality}}


def plan_node(state: GraphState) -> GraphState:
    runtime = get_runtime()
    plan = Planner(
        runtime.workflows,
        runtime.skills,
        agents=runtime.agents,
        model_selector=runtime.model_selector,
        context_store=runtime.context,
        events=runtime.events,
    ).build(
        state["workflow_id"],
        state.get("inputs") or {},
    )
    return {**state, "plan": plan.model_dump()}


def execute_plan_node(state: GraphState) -> GraphState:
    runtime = get_runtime()
    plan = Plan.model_validate(state["plan"])
    results = Orchestrator(
        runtime.tools,
        context_store=runtime.context,
        events=runtime.events,
    ).execute(plan)
    return {**state, "step_results": results}


def review_node(state: GraphState) -> GraphState:
    runtime = get_runtime()
    plan = Plan.model_validate(state["plan"])
    project_id = str((state.get("inputs") or {}).get("projectId") or "") or None
    notes = Reviewer(runtime.events, runtime.prompts).review(
        state.get("step_results") or [],
        trace_id=plan.planId,
        workflow_id=plan.workflowId,
        project_id=project_id,
    )
    return {**state, "review_notes": notes}


def reduce_node(state: GraphState) -> GraphState:
    runtime = get_runtime()
    plan = Plan.model_validate(state["plan"])
    project_id = str((state.get("inputs") or {}).get("projectId") or "") or None
    summary = Reducer(runtime.events, runtime.prompts).reduce(
        plan,
        state.get("step_results") or [],
        state.get("review_notes") or [],
        project_id=project_id,
    )
    return {**state, "summary": summary}


def response_node(state: GraphState) -> GraphState:
    runtime = get_runtime()
    has_error_notes = any(
        n.startswith("missing_data") or "not true" in n for n in (state.get("review_notes") or [])
    )
    status = "error" if has_error_notes or state.get("error") else "complete"
    plan = Plan.model_validate(state["plan"])
    project_id = str((state.get("inputs") or {}).get("projectId") or "") or None
    runtime.events.record(
        trace_id=plan.planId,
        event_type="workflow_failed" if status == "error" else "workflow_completed",
        workflow_id=plan.workflowId,
        project_id=project_id,
        status="error" if status == "error" else "complete",
        summary="Workflow가 오류 상태로 종료되었습니다." if status == "error" else "Workflow가 정상 완료되었습니다.",
        details={"reviewNotes": state.get("review_notes") or [], "summary": state.get("summary")},
    )
    return {**state, "status": status}
