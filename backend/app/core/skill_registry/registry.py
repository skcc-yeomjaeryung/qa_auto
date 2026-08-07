from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core.paths import SKILL_HUB


@dataclass
class ToolSpec:
    name: str
    script: str
    order: int = 1
    description: str = ""
    input_path: str | None = None
    output_path: str | None = None


@dataclass
class SkillDefinition:
    name: str
    agent: str | None
    version: str = "1.0.0"
    provided_capabilities: list[str] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    source_path: Path | None = None
    raw: dict = field(default_factory=dict)

    @property
    def model_requirements(self) -> dict:
        value = self.raw.get("model_requirements") or {}
        return dict(value) if isinstance(value, dict) else {}


def _parse_skill_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # allow HTML comment preamble before frontmatter
    marker = text.find("---")
    if marker < 0:
        raise ValueError(f"SKILL.md frontmatter missing: {path}")
    rest = text[marker:]
    parts = rest.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"SKILL.md frontmatter malformed: {path}")
    data = yaml.safe_load(parts[1]) or {}
    if not isinstance(data, dict):
        raise ValueError(f"SKILL.md frontmatter must be mapping: {path}")
    body = parts[2]
    # 교보재: 본문 §1~§14 존재 검증 (최소 헤더)
    required_headers = [
        "## 1. Skill Purpose",
        "## 2. When to use",
        "## 3. Inputs",
        "## 4. Outputs",
        "## 5. Tools",
        "## 6. Process",
        "## 7. Guardrails",
        "## 8. Error Handling",
        "## 9. Examples",
        "## 10. Non-goals",
        "## 11. Observability",
        "## 12. Ownership",
        "## 13. Compatibility",
        "## 14. Changelog",
    ]
    missing = [h for h in required_headers if h not in body]
    if missing:
        raise ValueError(f"SKILL.md missing sections in {path}: {missing}")
    return data


class SkillRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SkillDefinition] = {}

    def load(self, hub: Path | None = None) -> None:
        root = hub or SKILL_HUB
        self._items.clear()
        for skill_md in sorted(root.glob("*/SKILL.md")):
            data = _parse_skill_md(skill_md)
            name = str(data.get("name") or skill_md.parent.name)
            if not data.get("agent"):
                raise ValueError(f"SKILL.md agent required: {skill_md}")
            caps = []
            for item in data.get("provided_capabilities", []) or []:
                if isinstance(item, dict) and item.get("capability_id"):
                    caps.append(str(item["capability_id"]))
                elif isinstance(item, str):
                    caps.append(item)
            if not caps:
                raise ValueError(f"SKILL.md provided_capabilities required: {skill_md}")
            tools: list[ToolSpec] = []
            for t in data.get("tools") or []:
                if not t.get("name") or not t.get("script"):
                    continue
                tools.append(
                    ToolSpec(
                        name=str(t["name"]),
                        script=str(t["script"]),
                        order=int(t.get("order") or 1),
                        description=str(t.get("description") or ""),
                        input_path=str(t["input"]) if t.get("input") else None,
                        output_path=str(t["output"]) if t.get("output") else None,
                    )
                )
            if not tools:
                raise ValueError(f"SKILL.md tools required: {skill_md}")
            tools.sort(key=lambda x: x.order)
            self._items[name] = SkillDefinition(
                name=name,
                agent=str(data["agent"]),
                version=str(data.get("version") or "1.0.0"),
                provided_capabilities=caps,
                tools=tools,
                source_path=skill_md,
                raw=data,
            )

    def get(self, name: str) -> SkillDefinition | None:
        return self._items.get(name)

    def require(self, name: str) -> SkillDefinition:
        item = self.get(name)
        if not item:
            raise KeyError(f"Skill not in Hub: {name}")
        return item

    def find_by_capability(self, capability_id: str) -> list[SkillDefinition]:
        return [s for s in self._items.values() if capability_id in s.provided_capabilities]

    def count(self) -> int:
        return len(self._items)

    def names(self) -> list[str]:
        return sorted(self._items)
