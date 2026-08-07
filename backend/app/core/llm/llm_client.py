"""OpenAI-compatible local LLM client — singleton, never invent Hub assets."""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.utils.config import get_settings

logger = logging.getLogger("qa_auto.llm")


class LlmClient:
    """Thin Chat Completions client. Falls back to None when endpoint unavailable."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        embedding_model: str,
        api_key: str,
        temperature: float,
        max_tokens: int,
        enabled: bool,
        receipt_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enabled = enabled
        self.receipt_callback = receipt_callback
        self._pending_receipt: dict[str, Any] | None = None

    def _write_receipt(self, receipt: dict[str, Any]) -> None:
        """Append a secret-free provider receipt for the parent ToolRuntime.

        Prompts and model responses are deliberately excluded. The receipt only
        proves whether an OpenAI-compatible request happened and what usage the
        provider reported.
        """
        if self.receipt_callback:
            try:
                self.receipt_callback(dict(receipt))
            except Exception as exc:  # noqa: BLE001 - observability must not break inference
                logger.info("model usage callback failed: %s", exc)
        receipt_path = os.getenv("LLM_USAGE_RECEIPT_PATH", "").strip()
        if not receipt_path:
            return
        try:
            path = Path(receipt_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.info("model usage receipt write failed: %s", exc)

    def _finish_receipt(self, status: str, **details: Any) -> None:
        if self._pending_receipt is None:
            return
        receipt = {**self._pending_receipt, "status": status, **details}
        self._pending_receipt = None
        self._write_receipt(receipt)

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        timeout_s: float = 45.0,
    ) -> dict[str, Any] | None:
        """Return parsed JSON object or None on disable/error (caller uses deterministic fallback)."""
        if not self.enabled:
            return None
        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        self._apply_generation_options(body)
        payload = self._post_json("chat/completions", body, timeout_s)
        if not payload:
            return None
        try:
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                self._finish_receipt("invalid_response", errorType="json_object_required")
                return None
            self._finish_receipt("completed")
            return parsed
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            logger.info("llm json parse failed: %s", exc)
            self._finish_receipt("invalid_response", errorType=type(exc).__name__)
            return None

    def vision_json(
        self,
        *,
        system: str,
        prompt: str,
        image_data_url: str,
        timeout_s: float = 60.0,
    ) -> dict[str, Any] | None:
        """Use an OpenAI-compatible VLM for slide/screen OCR and return structured JSON."""
        if not self.enabled:
            return None
        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
        }
        self._apply_generation_options(body, vision=True)
        payload = self._post_json("chat/completions", body, timeout_s)
        if not payload:
            return None
        try:
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                self._finish_receipt("invalid_response", errorType="json_object_required")
                return None
            self._finish_receipt("completed")
            return parsed
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            logger.info("vlm json parse failed: %s", exc)
            self._finish_receipt("invalid_response", errorType=type(exc).__name__)
            return None

    def embed_texts(self, texts: list[str], *, timeout_s: float = 45.0) -> list[list[float]] | None:
        """Create embeddings through the configured local OpenAI-compatible endpoint."""
        if not self.enabled or not texts:
            return None
        payload = self._post_json(
            "embeddings",
            {"model": self.embedding_model, "input": texts},
            timeout_s,
        )
        if not payload:
            return None
        try:
            rows = sorted(payload["data"], key=lambda item: int(item.get("index", 0)))
            vectors = [list(map(float, item["embedding"])) for item in rows]
            if len(vectors) != len(texts):
                self._finish_receipt("invalid_response", errorType="embedding_count_mismatch")
                return None
            self._finish_receipt("completed")
            return vectors
        except (KeyError, TypeError, ValueError) as exc:
            self._finish_receipt("invalid_response", errorType=type(exc).__name__)
            return None

    def _apply_generation_options(self, body: dict[str, Any], *, vision: bool = False) -> None:
        """GPT-5 Chat Completions uses the reasoning-family token field.

        Local OpenAI-compatible servers keep the legacy max_tokens/temperature pair.
        """
        normalized = self.model.lower().strip()
        if normalized.startswith(("gpt-5", "o1", "o3", "o4")):
            body["max_completion_tokens"] = self.max_tokens
            reasoning_effort = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()
            if reasoning_effort in {"minimal", "low", "medium", "high"}:
                body["reasoning_effort"] = reasoning_effort
            return
        body["temperature"] = 0.0 if vision else self.temperature
        body["max_tokens"] = self.max_tokens

    def _post_json(self, path: str, body: dict[str, Any], timeout_s: float) -> dict[str, Any] | None:
        url = f"{self.base_url}/{path.lstrip('/')}"
        raw = json.dumps(body).encode("utf-8")
        request_id = f"LLMREQ-{uuid4().hex[:14]}"
        started = time.monotonic()
        req = urllib.request.Request(
            url,
            data=raw,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if not isinstance(result, dict):
                    self._write_receipt(
                        {
                            "requestId": request_id,
                            "model": str(body.get("model") or self.model),
                            "operation": path,
                            "status": "invalid_response",
                            "durationMs": int((time.monotonic() - started) * 1000),
                            "occurredAt": datetime.now(timezone.utc).isoformat(),
                            "errorType": "response_object_required",
                        }
                    )
                    return None
                usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
                self._pending_receipt = {
                    "requestId": request_id,
                    "providerRequestId": result.get("id"),
                    "model": str(result.get("model") or body.get("model") or self.model),
                    "operation": path,
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "occurredAt": datetime.now(timezone.utc).isoformat(),
                    "promptTokens": usage.get("prompt_tokens"),
                    "completionTokens": usage.get("completion_tokens"),
                    "totalTokens": usage.get("total_tokens"),
                }
                return result
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            logger.info("local model endpoint unavailable: %s", exc)
            self._pending_receipt = None
            self._write_receipt(
                {
                    "requestId": request_id,
                    "model": str(body.get("model") or self.model),
                    "operation": path,
                    "status": "failed",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "occurredAt": datetime.now(timezone.utc).isoformat(),
                    "errorType": type(exc).__name__,
                    "httpStatus": getattr(exc, "code", None),
                }
            )
            return None


@lru_cache
def get_llm_client() -> LlmClient:
    settings = get_settings()
    return LlmClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        embedding_model=settings.embedding_model,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        enabled=settings.llm_enabled,
    )
