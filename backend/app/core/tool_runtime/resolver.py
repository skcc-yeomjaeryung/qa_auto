from __future__ import annotations

from pathlib import Path

from app.core.skill_registry.registry import SkillDefinition


class ToolResolutionError(RuntimeError):
    pass


def resolve_tool_script(skill: SkillDefinition, tool_name: str) -> Path:
    """skill + tool → SKILL.md tools[] → script path. Plan must not hardcode paths."""
    tool = next((t for t in skill.tools if t.name == tool_name), None)
    if tool is None:
        raise ToolResolutionError(f"Skill {skill.name} has no tool {tool_name}")
    if not skill.source_path:
        raise ToolResolutionError(f"Skill {skill.name} missing source_path")

    skill_dir = Path(skill.source_path).parent.resolve()
    raw = (tool.script or "").strip()
    if not raw:
        raise ToolResolutionError(f"Tool {tool_name} script empty")
    if Path(raw).is_absolute() or raw.startswith("~"):
        raise ToolResolutionError(f"absolute script path forbidden: {raw}")
    if ".." in Path(raw).parts:
        raise ToolResolutionError(f"'..' in script path forbidden: {raw}")

    candidate = (skill_dir / raw).resolve()
    try:
        candidate.relative_to(skill_dir)
    except ValueError as exc:
        raise ToolResolutionError(f"script outside skill root: {candidate}") from exc
    if not candidate.is_file():
        raise ToolResolutionError(f"script not found: {candidate}")
    return candidate
