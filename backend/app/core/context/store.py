from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from threading import RLock
from typing import Any

from app.utils.config import get_settings

_SENSITIVE = re.compile(r"(secret|password|passwd|token|api[_-]?key|authorization|cookie)", re.I)


class ContextStore:
    """Stores large plan input once and passes an immutable reference to each step."""

    def __init__(self, threshold_bytes: int = 16_384) -> None:
        self.threshold_bytes = threshold_bytes
        self.root = Path(get_settings().data_dir) / "agent-context"
        self.root.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    @staticmethod
    def _has_secret(value: Any) -> bool:
        if isinstance(value, dict):
            return any(_SENSITIVE.search(str(key)) or ContextStore._has_secret(child) for key, child in value.items())
        if isinstance(value, list):
            return any(ContextStore._has_secret(child) for child in value)
        return False

    def put(self, trace_id: str, inputs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        raw = json.dumps(inputs, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        metadata = {"originalBytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if len(raw) < self.threshold_bytes:
            return dict(inputs), {**metadata, "storage": "inline"}
        if self._has_secret(inputs):
            with self._lock:
                self._memory[trace_id] = dict(inputs)
            return {"_contextRef": f"memory:{trace_id}"}, {**metadata, "storage": "memory"}
        path = self.root / f"{trace_id}.json"
        path.write_bytes(raw)
        return {"_contextRef": f"file:{path.name}"}, {**metadata, "storage": "file"}

    def resolve(self, payload: dict[str, Any]) -> dict[str, Any]:
        ref = payload.get("_contextRef")
        if not isinstance(ref, str):
            return dict(payload)
        if ref.startswith("memory:"):
            with self._lock:
                return dict(self._memory.get(ref.split(":", 1)[1]) or {})
        if ref.startswith("file:"):
            name = Path(ref.split(":", 1)[1]).name
            path = self.root / name
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        raise KeyError(f"context reference not found: {ref}")

