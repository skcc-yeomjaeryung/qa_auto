from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.core.skill_registry.registry import SkillRegistry
from app.core.tool_runtime.resolver import resolve_tool_script
from app.core.models.registry import ModelRegistry

logger = logging.getLogger(__name__)


class ToolRuntime:
    def __init__(self, skills: SkillRegistry, models: ModelRegistry | None = None) -> None:
        self.skills = skills
        self.models = models

    def run(self, skill_name: str, tool_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        skill = self.skills.require(skill_name)
        script = resolve_tool_script(skill, tool_name)
        with tempfile.TemporaryDirectory(prefix="qa-auto-tool-") as tmp:
            tmp_path = Path(tmp)
            in_file = tmp_path / "input.json"
            out_file = tmp_path / "output.json"
            usage_file = tmp_path / "model-usage.jsonl"
            in_file.write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
            env = os.environ.copy()
            runtime_meta = inputs.get("_runtime") if isinstance(inputs, dict) else None
            decision = runtime_meta.get("modelDecision") if isinstance(runtime_meta, dict) else None
            selected_id = decision.get("selectedModelProfileId") if isinstance(decision, dict) else None
            if selected_id and self.models:
                profile = self.models.require(str(selected_id))
                env.update(
                    {
                        "LLM_ENABLED": "1",
                        "LLM_BASE_URL": f"{str(profile.endpoint).rstrip('/')}{profile.apiBasePath}",
                        "LLM_MODEL": profile.modelId,
                        "LLM_API_KEY": self.models.secret(profile.id) or "local",
                        "LLM_USAGE_RECEIPT_PATH": str(usage_file),
                    }
                )
                # GPT-5 reasoning tokens share max_completion_tokens with the JSON answer.
                # Scenario narration is a bounded formatting pass, so minimal reasoning keeps
                # latency predictable while an 8K ceiling prevents otherwise valid JSON from
                # being truncated at the former 2K default.
                if skill_name == "scenario_narrate" and profile.modelId.lower().startswith("gpt-5"):
                    configured = int(env.get("LLM_MAX_TOKENS") or 0)
                    env["LLM_MAX_TOKENS"] = str(max(configured, 8192))
                    env["LLM_REASONING_EFFORT"] = "minimal"
            completed = subprocess.run(
                [sys.executable, str(script), "--input", str(in_file), "--output", str(out_file)],
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
                env=env,
            )
            if completed.returncode != 0:
                err = (completed.stderr or completed.stdout or "tool failed").strip()
                raise RuntimeError(f"tool {skill_name}/{tool_name} failed: {err[:1000]}")
            if not out_file.is_file():
                raise RuntimeError(f"tool {skill_name}/{tool_name} produced no output")
            output = json.loads(out_file.read_text(encoding="utf-8"))
            if selected_id and self.models and isinstance(output, dict):
                profile = self.models.require(str(selected_id))
                receipts: list[dict[str, Any]] = []
                if usage_file.is_file():
                    for line in usage_file.read_text(encoding="utf-8").splitlines():
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(item, dict):
                            receipts.append(item)
                if not receipts:
                    receipts.append(
                        {
                            "model": profile.modelId,
                            "modelProfileId": profile.id,
                            "displayName": profile.displayName,
                            "status": "not_invoked",
                            "reason": "도구가 완료됐지만 LLM 클라이언트 호출 경로는 실행되지 않았습니다.",
                        }
                    )
                else:
                    receipts = [
                        {
                            **item,
                            "modelProfileId": profile.id,
                            "displayName": profile.displayName,
                        }
                        for item in receipts
                    ]
                output["_modelInvocations"] = receipts
            return output
