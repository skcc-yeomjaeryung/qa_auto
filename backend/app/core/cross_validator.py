from __future__ import annotations

from app.core.capability_registry.registry import CapabilityRegistry
from app.core.skill_registry.registry import SkillRegistry
from app.core.workflow_registry.registry import WorkflowRegistry
from app.core.catalog.agents import AgentRegistry


class HubValidationError(RuntimeError):
    pass


def cross_validate(
    workflows: WorkflowRegistry,
    skills: SkillRegistry,
    capabilities: CapabilityRegistry,
    agents: AgentRegistry | None = None,
) -> None:
    if workflows.count() < 1:
        raise HubValidationError("Workflow Hub empty")
    if skills.count() < 1:
        raise HubValidationError("Skill Hub empty")
    if capabilities.count() < 1:
        raise HubValidationError("Capability Hub empty")

    for wid in workflows.ids():
        wf = workflows.require(wid)
        for cap in wf.required_capabilities:
            if not capabilities.has(cap):
                raise HubValidationError(f"Workflow {wid} requires unknown capability {cap}")
            matches = skills.find_by_capability(cap)
            if not matches:
                raise HubValidationError(f"No Skill provides capability {cap} for workflow {wid}")

    for name in skills.names():
        skill = skills.require(name)
        if not skill.tools:
            raise HubValidationError(f"Skill {name} has no tools")
        for cap in skill.provided_capabilities:
            if not capabilities.has(cap):
                raise HubValidationError(f"Skill {name} provides unknown capability {cap}")
        if agents is not None:
            if not skill.agent:
                raise HubValidationError(f"Skill {name} has no Agent")
            try:
                agents.validate_skill(skill.agent, name)
            except (KeyError, PermissionError) as exc:
                raise HubValidationError(str(exc)) from exc
