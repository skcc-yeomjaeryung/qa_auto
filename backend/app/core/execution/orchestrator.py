from __future__ import annotations

from typing import Any

from app.core.context import ContextStore
from app.core.observability import AgentEventStore
from app.core.tool_runtime import ToolRuntime
from app.schemas.plan import Plan, PlanStep


def _step_audit_details(output: Any) -> dict[str, Any]:
    """Return a compact, secret-free execution receipt for the Agent trace.

    The full browser payload belongs in the Evidence Package.  The Agent
    monitor only needs enough correlation and tool provenance to prove which
    run used which browser tools.
    """
    wrapper = output if isinstance(output, dict) else {}
    result = wrapper.get("result") if isinstance(wrapper.get("result"), dict) else {}
    steps = [item for item in (result.get("steps") or []) if isinstance(item, dict)]
    tools = list(
        dict.fromkeys(
            str(item.get("mcpTool"))
            for item in steps
            if item.get("mcpTool")
        )
    )
    details = {
        "ok": bool(wrapper.get("ok")),
        "artifactPath": wrapper.get("artifactPath") or result.get("artifactPath"),
        "runId": wrapper.get("runId") or result.get("runId"),
        "scenarioId": result.get("scenarioId"),
        "browserRunner": result.get("browserRunner"),
        "toolHistory": tools,
        "toolCallCount": sum(bool(item.get("mcpTool")) for item in steps),
        "networkRequestCount": len(result.get("networkRequests") or []),
        "matchedNetworkRequestCount": len(result.get("matchedNetworkRequests") or []),
    }
    narration_mode = result.get("narrationMode") or wrapper.get("mode")
    if narration_mode:
        details["narrationMode"] = narration_mode
    return details


def _merge_dependency_outputs(inputs: dict[str, Any], dependencies: list[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(inputs)
    for result in dependencies:
        output = result.get("output") or {}
        if output.get("artifactPath") and not merged.get("artifactPath"):
            merged["artifactPath"] = output["artifactPath"]
        previous = output.get("result")
        if isinstance(previous, dict):
            merged["result"] = previous
            for key in ("scenarios", "projectContext", "interactionGraph"):
                if key in previous:
                    merged[key] = previous[key]
        if output.get("serviceId") and not merged.get("serviceId"):
            merged["serviceId"] = output["serviceId"]
    return merged


class Orchestrator:
    """Dependency-aware Plan executor. Ready steps can be parallelized without changing the Plan contract."""

    def __init__(
        self,
        tools: ToolRuntime,
        *,
        context_store: ContextStore | None = None,
        events: AgentEventStore | None = None,
    ) -> None:
        self.tools = tools
        self.context_store = context_store
        self.events = events

    def _run_step(
        self,
        plan: Plan,
        step: PlanStep,
        project_id: str | None,
        dependencies: list[dict[str, Any]],
    ) -> dict[str, Any]:
        inputs = self.context_store.resolve(step.inputs) if self.context_store else dict(step.inputs or {})
        inputs = _merge_dependency_outputs(inputs, dependencies)
        if step.modelDecision is not None:
            inputs["_runtime"] = {
                "traceId": plan.planId,
                "stepId": step.stepId,
                "modelDecision": step.modelDecision.model_dump(),
            }
        if self.events:
            self.events.record(
                trace_id=plan.planId,
                event_type="step_started",
                workflow_id=plan.workflowId,
                project_id=project_id,
                step_id=step.stepId,
                agent=step.agent,
                skill=step.skill,
                tool=step.tool,
                status="running",
                summary=f"{step.skill}/{step.tool} 실행을 시작했습니다.",
                details={
                    "dependsOn": step.dependsOn,
                    "inputKeys": sorted(inputs),
                    "correlation": {
                        key: inputs.get(key)
                        for key in ("projectId", "runId", "scenarioId")
                        if inputs.get(key)
                    },
                },
            )
        try:
            output = self.tools.run(step.skill, step.tool, inputs)
        except Exception as exc:
            if self.events:
                self.events.record(
                    trace_id=plan.planId,
                    event_type="step_failed",
                    workflow_id=plan.workflowId,
                    project_id=project_id,
                    step_id=step.stepId,
                    agent=step.agent,
                    skill=step.skill,
                    tool=step.tool,
                    status="error",
                    summary=f"{step.skill}/{step.tool} 실행에 실패했습니다.",
                    details={"error": str(exc)},
                )
            raise
        result = {
            "stepId": step.stepId,
            "skill": step.skill,
            "tool": step.tool,
            "agent": step.agent,
            "output": output,
        }
        if self.events:
            invocation_receipts = (
                output.get("_modelInvocations")
                if isinstance(output, dict) and isinstance(output.get("_modelInvocations"), list)
                else []
            )
            for receipt in invocation_receipts:
                if not isinstance(receipt, dict):
                    continue
                receipt_status = str(receipt.get("status") or "failed")
                display_name = str(receipt.get("displayName") or receipt.get("model") or "선택 모델")
                if receipt_status == "completed":
                    event_type = "model_invocation_completed"
                    event_status = "complete"
                    summary = f"{display_name} 추론 호출을 완료했습니다."
                elif receipt_status == "not_invoked":
                    event_type = "model_not_invoked"
                    event_status = "info"
                    summary = "모델 후보는 선택했지만 이 단계에서는 추론 호출이 발생하지 않았습니다."
                else:
                    event_type = "model_invocation_failed"
                    event_status = "info"
                    summary = f"{display_name} 응답을 사용하지 못해 근거 기반 규칙으로 계속 진행했습니다."
                self.events.record(
                    trace_id=plan.planId,
                    event_type=event_type,
                    workflow_id=plan.workflowId,
                    project_id=project_id,
                    step_id=step.stepId,
                    agent=step.agent,
                    skill=step.skill,
                    tool=step.tool,
                    status=event_status,
                    summary=summary,
                    details=receipt,
                )
            self.events.record(
                trace_id=plan.planId,
                event_type="step_completed",
                workflow_id=plan.workflowId,
                project_id=project_id,
                step_id=step.stepId,
                agent=step.agent,
                skill=step.skill,
                tool=step.tool,
                status="complete",
                summary=f"{step.skill}/{step.tool} 실행이 완료되었습니다.",
                details=_step_audit_details(output),
            )
        return result

    def execute(self, plan: Plan) -> list[dict[str, Any]]:
        pending = {step.stepId: step for step in plan.steps}
        completed: dict[str, dict[str, Any]] = {}
        ordered: list[dict[str, Any]] = []
        project_id: str | None = None
        first_inputs = self.context_store.resolve(plan.steps[0].inputs) if plan.steps and self.context_store else (plan.steps[0].inputs if plan.steps else {})
        if isinstance(first_inputs, dict):
            project_id = str(first_inputs.get("projectId") or "") or None
        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dependency in completed for dependency in step.dependsOn)
            ]
            if not ready:
                unresolved = {key: value.dependsOn for key, value in pending.items()}
                raise ValueError(f"Plan contains a dependency cycle or missing step: {unresolved}")
            ready.sort(key=lambda item: next(i for i, row in enumerate(plan.steps) if row.stepId == item.stepId))
            for step in ready:
                dependencies = [completed[dep] for dep in step.dependsOn]
                try:
                    result = self._run_step(plan, step, project_id, dependencies)
                except Exception:
                    if self.events:
                        self.events.record(
                            trace_id=plan.planId,
                            event_type="workflow_failed",
                            workflow_id=plan.workflowId,
                            project_id=project_id,
                            status="error",
                            summary=f"{step.stepId} 실패로 Workflow가 중단되었습니다.",
                            details={"failedStepId": step.stepId},
                        )
                    raise
                completed[step.stepId] = result
                ordered.append(result)
                pending.pop(step.stepId)
        return ordered
