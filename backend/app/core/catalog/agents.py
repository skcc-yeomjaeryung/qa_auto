from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.paths import AGENT_SPECS


@dataclass
class AgentDefinition:
    agent_id: str
    name: str
    version: str
    description: str = ""
    allowed_skills: list[str] = field(default_factory=list)
    prohibited_actions: list[str] = field(default_factory=list)
    source_path: Path | None = None


class AgentRegistry:
    def __init__(self) -> None:
        self._items: dict[str, AgentDefinition] = {}

    def load(self, root: Path | None = None) -> None:
        self._items.clear()
        for path in sorted((root or AGENT_SPECS).glob("*.yml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            agent_id = str(raw.get("agent_id") or "").strip()
            if not agent_id:
                raise ValueError(f"agent_id missing: {path}")
            self._items[agent_id] = AgentDefinition(
                agent_id=agent_id,
                name=str(raw.get("name") or agent_id),
                version=str(raw.get("version") or "1.0.0"),
                description=str(raw.get("description") or ""),
                allowed_skills=[str(item) for item in raw.get("allowed_skills") or []],
                prohibited_actions=[str(item) for item in raw.get("prohibited_actions") or []],
                source_path=path,
            )

    def require(self, agent_id: str) -> AgentDefinition:
        item = self._items.get(agent_id)
        if item is None:
            raise KeyError(f"Agent not in Hub: {agent_id}")
        return item

    def validate_skill(self, agent_id: str, skill_name: str) -> None:
        agent = self.require(agent_id)
        if skill_name not in agent.allowed_skills:
            raise PermissionError(f"Agent {agent_id} is not allowed to execute Skill {skill_name}")

    def count(self) -> int:
        return len(self._items)


