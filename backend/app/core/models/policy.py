from __future__ import annotations

from typing import Any

from app.core.models.contracts import AiPolicy, ModelRequirement
from app.services.sqlite_persist import kv_get

_ALLOWED = {"auto", "cost_saver", "balanced", "highest_quality", "internal_only"}


def resolve_project_policy(project_id: str | None, explicit: Any = None) -> AiPolicy:
    if explicit in _ALLOWED:
        return explicit
    if project_id:
        catalog = kv_get("platform_catalog_v1") or {}
        for item in catalog.get("projects") or []:
            if isinstance(item, dict) and item.get("id") == project_id:
                value = item.get("aiPolicy")
                if value in _ALLOWED:
                    return value
    return "auto"


def model_role_for_requirement(requirement: ModelRequirement) -> str:
    """Map a Skill requirement to the operator-facing project model role."""
    capabilities = set(requirement.capabilities)
    if "image_generation" in capabilities:
        return "image_generation"
    if "embedding" in capabilities:
        return "embedding"
    if "vision" in capabilities:
        return "vision"
    if requirement.qualityProfile in {"scenario_generation", "evidence_review"}:
        return "advanced"
    return "general"


def resolve_project_model_binding(
    project_id: str | None,
    requirement: ModelRequirement,
) -> tuple[str, str | None]:
    """Return (role, fixed profile id). Unbound roles continue through auto policy."""
    role = model_role_for_requirement(requirement)
    if not project_id:
        return role, None
    catalog = kv_get("platform_catalog_v1") or {}
    for item in catalog.get("projects") or []:
        if not isinstance(item, dict) or item.get("id") != project_id:
            continue
        if item.get("modelSelectionMode") != "manual":
            return role, None
        bindings = item.get("modelBindings") or {}
        if not isinstance(bindings, dict):
            return role, None
        selected = str(bindings.get(role) or "").strip()
        return role, selected or None
    return role, None
