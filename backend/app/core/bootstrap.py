from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.capability_registry import CapabilityRegistry
from app.core.catalog import AgentRegistry
from app.core.context import ContextStore
from app.core.cross_validator import cross_validate
from app.core.models import ModelRegistry, ModelSelector
from app.core.observability import AgentEventStore
from app.core.prompts import PromptCatalog
from app.core.skill_registry import SkillRegistry
from app.core.tool_runtime import ToolRuntime
from app.core.workflow_registry import WorkflowRegistry

logger = logging.getLogger(__name__)


@dataclass
class PlatformRuntime:
    workflows: WorkflowRegistry
    skills: SkillRegistry
    capabilities: CapabilityRegistry
    tools: ToolRuntime
    agents: AgentRegistry
    models: ModelRegistry
    model_selector: ModelSelector
    context: ContextStore
    events: AgentEventStore
    prompts: PromptCatalog


_RUNTIME: PlatformRuntime | None = None


def bootstrap_runtime() -> PlatformRuntime:
    global _RUNTIME
    workflows = WorkflowRegistry()
    skills = SkillRegistry()
    capabilities = CapabilityRegistry()
    agents = AgentRegistry()
    models = ModelRegistry()
    events = AgentEventStore()
    context = ContextStore()
    prompts = PromptCatalog()
    workflows.load()
    skills.load()
    capabilities.load()
    agents.load()
    cross_validate(workflows, skills, capabilities, agents)
    model_selector = ModelSelector(models, prompts)
    tools = ToolRuntime(skills, models)
    _RUNTIME = PlatformRuntime(
        workflows=workflows,
        skills=skills,
        capabilities=capabilities,
        tools=tools,
        agents=agents,
        models=models,
        model_selector=model_selector,
        context=context,
        events=events,
        prompts=prompts,
    )
    logger.info(
        "hub loaded workflows=%s skills=%s capabilities=%s agents=%s models=%s",
        workflows.count(),
        skills.count(),
        capabilities.count(),
        agents.count(),
        len(models.list()),
    )
    return _RUNTIME


def get_runtime() -> PlatformRuntime:
    if _RUNTIME is None:
        return bootstrap_runtime()
    return _RUNTIME
