from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import jsonschema

from app.core.catalog import AgentRegistry
from app.core.context import ContextStore
from app.core.models import (
    ModelRequirement,
    ModelSelector,
    resolve_project_model_binding,
    resolve_project_policy,
)
from app.core.observability import AgentEventStore
from app.core.paths import PLAN_SCHEMA
from app.core.skill_registry import SkillRegistry
from app.core.workflow_registry import WorkflowRegistry
from app.schemas.plan import Plan, PlanStep

class Planner:
    """Capability-based planner with auditable Skill and model selection."""

    def __init__(
        self,
        workflows: WorkflowRegistry,
        skills: SkillRegistry,
        *,
        agents: AgentRegistry | None = None,
        model_selector: ModelSelector | None = None,
        context_store: ContextStore | None = None,
        events: AgentEventStore | None = None,
    ) -> None:
        self.workflows = workflows
        self.skills = skills
        self.agents = agents
        self.model_selector = model_selector
        self.context_store = context_store
        self.events = events
        self._schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))

    @staticmethod
    def _model_requirement(raw: dict[str, Any]) -> ModelRequirement | None:
        if not raw:
            return None
        return ModelRequirement(
            capabilities=list(raw.get("capabilities") or []),
            minimumContext=int(raw.get("minimum_context") or raw.get("minimumContext") or 0),
            structuredOutput=bool(raw.get("structured_output") or raw.get("structuredOutput")),
            tools=bool(raw.get("tools")),
            qualityProfile=str(raw.get("quality_profile") or raw.get("qualityProfile") or "general"),
            allowDeterministicFallback=bool(raw.get("allow_deterministic_fallback", True)),
        )

    def build(self, workflow_id: str, inputs: dict | None = None) -> Plan:
        provided = dict(inputs or {})
        wf = self.workflows.require(workflow_id)
        trace_id = f"PLAN-{uuid4().hex[:12]}"
        project_id = str(provided.get("projectId") or "") or None
        policy = resolve_project_policy(project_id, provided.get("aiPolicy"))
        if self.events:
            self.events.record(
                trace_id=trace_id,
                event_type="workflow_started",
                workflow_id=workflow_id,
                project_id=project_id,
                status="running",
                summary=f"{workflow_id} 실행 요청을 수신했습니다.",
                details={"inputKeys": sorted(provided), "aiPolicy": policy},
            )
        shared_inputs = provided
        context_meta = {"storage": "inline", "originalBytes": 0}
        if self.context_store:
            shared_inputs, context_meta = self.context_store.put(trace_id, provided)

        if wf.logical_steps:
            capability_seq = [step.required_capability for step in wf.logical_steps]
            step_meta = wf.logical_steps
        else:
            capability_seq = list(wf.required_capabilities)
            step_meta = None

        steps: list[PlanStep] = []
        for index, capability in enumerate(capability_seq):
            matches = self.skills.find_by_capability(capability)
            if not matches:
                raise KeyError(f"No Skill in Hub for capability {capability}")
            matches.sort(key=lambda item: (-int(item.raw.get("priority") or 0), item.name))
            skill = matches[0]
            agent_id = skill.agent or "platform_runner"
            if self.agents:
                self.agents.validate_skill(agent_id, skill.name)
            if not skill.tools:
                raise ValueError(f"Skill {skill.name} has no tools")
            tool = skill.tools[0]
            step_id = f"S{index + 1}"
            depends: list[str] = []
            if step_meta is not None:
                step_id = step_meta[index].step_id
                depends = list(step_meta[index].depends_on)
            elif index > 0:
                depends = [f"S{index}"]

            decision = None
            requirement = self._model_requirement(skill.model_requirements)
            if requirement is not None and self.model_selector is not None:
                selection_role, preferred_profile_id = resolve_project_model_binding(
                    project_id,
                    requirement,
                )
                decision = self.model_selector.select(
                    requirement,
                    policy,
                    preferred_model_profile_id=preferred_profile_id,
                    selection_role=selection_role,
                )
                if self.events:
                    self.events.record(
                        trace_id=trace_id,
                        event_type="model_candidates_evaluated",
                        workflow_id=workflow_id,
                        project_id=project_id,
                        step_id=step_id,
                        agent=agent_id,
                        skill=skill.name,
                        tool=tool.name,
                        summary=f"{len(decision.candidates)}개 모델 후보를 하드 필터와 가중 점수로 평가했습니다.",
                        details={
                            "policy": policy,
                            "requirement": requirement.model_dump(),
                            "candidates": [item.model_dump() for item in decision.candidates],
                        },
                    )
                    self.events.record(
                        trace_id=trace_id,
                        event_type="model_selected",
                        workflow_id=workflow_id,
                        project_id=project_id,
                        step_id=step_id,
                        agent=agent_id,
                        skill=skill.name,
                        tool=tool.name,
                        summary=decision.decisionSummary,
                        details=decision.model_dump(),
                    )

            reason = (
                f"Workflow capability {capability}을 제공하는 활성 Skill 중 priority가 가장 높은 "
                f"{skill.name}을 선택했습니다."
            )
            steps.append(
                PlanStep(
                    stepId=step_id,
                    agent=agent_id,
                    skill=skill.name,
                    tool=tool.name,
                    dependsOn=depends,
                    inputs=dict(shared_inputs),
                    requiredCapability=capability,
                    selectionReason=reason,
                    modelDecision=decision,
                )
            )

        plan = Plan(schemaVersion="plan/v2", planId=trace_id, workflowId=workflow_id, steps=steps)
        jsonschema.validate(plan.model_dump(mode="json"), self._schema)
        if self.events:
            self.events.record(
                trace_id=trace_id,
                event_type="plan_created",
                workflow_id=workflow_id,
                project_id=project_id,
                status="complete",
                summary=f"{len(steps)}단계 실행 Plan을 생성했습니다.",
                details={
                    "executionPattern": wf.execution_pattern,
                    "context": context_meta,
                    "steps": [
                        {
                            "stepId": item.stepId,
                            "capability": item.requiredCapability,
                            "agent": item.agent,
                            "skill": item.skill,
                            "tool": item.tool,
                            "dependsOn": item.dependsOn,
                            "selectionReason": item.selectionReason,
                        }
                        for item in steps
                    ],
                },
            )
        return plan
