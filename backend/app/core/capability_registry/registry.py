from __future__ import annotations

from pathlib import Path

import yaml

from app.core.paths import CAPABILITY_HUB


class CapabilityRegistry:
    def __init__(self) -> None:
        self._ids: set[str] = set()

    def load(self, hub: Path | None = None) -> None:
        root = hub or CAPABILITY_HUB
        self._ids.clear()
        for path in sorted(root.glob("*.yml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for item in data.get("capabilities", []):
                cid = item.get("capability_id")
                if cid:
                    self._ids.add(str(cid))

    def has(self, capability_id: str) -> bool:
        return capability_id in self._ids

    def ids(self) -> set[str]:
        return set(self._ids)

    def count(self) -> int:
        return len(self._ids)
