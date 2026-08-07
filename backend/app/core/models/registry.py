from __future__ import annotations

import time
from threading import RLock
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx

from app.core.models.contracts import ModelProfile, ModelProfileCreate, ModelProfileUpdate, utc_now
from app.core.models.secret_store import ModelSecretStore, build_model_secret_store
from app.services.sqlite_persist import kv_get, kv_set
from app.utils.config import get_settings

MODEL_PROFILES_KEY = "agent_model_profiles_v1"
MODEL_SECRETS_KEY = "agent_model_secrets_v1"  # legacy plaintext cleanup key


def _public_endpoint_and_paths(base_url: str) -> tuple[str, str, str]:
    raw = base_url.rstrip("/")
    if raw.endswith("/v1"):
        return raw[:-3], "/v1", "/v1/models"
    return raw, "/v1", "/v1/models"


class ModelRegistry:
    def __init__(self, secret_store: ModelSecretStore | None = None) -> None:
        self._lock = RLock()
        self._items: dict[str, ModelProfile] = {}
        self._secrets: dict[str, str] = {}
        self._secret_store = secret_store or build_model_secret_store()
        self.load()

    def load(self) -> None:
        with self._lock:
            self._items.clear()
            self._secrets.clear()
            for raw in kv_get(MODEL_PROFILES_KEY) or []:
                try:
                    item = ModelProfile.model_validate(raw)
                    self._items[item.id] = item
                except Exception:
                    continue
            # Remove the legacy SQLite secret blob. Credentials are hydrated from the
            # operating-system secret store and never serialized into platform data.
            kv_set(MODEL_SECRETS_KEY, {})
            hydrated: dict[str, ModelProfile] = {}
            for key, item in self._items.items():
                secret = self._secret_store.get(key)
                if secret:
                    self._secrets[key] = secret
                updates: dict[str, object] = {"hasApiKey": bool(secret)}
                if item.deploymentType == "external" and not secret:
                    updates.update(
                        {
                            "healthStatus": "unknown",
                            "lastHealthAt": None,
                            "healthLatencyMs": None,
                            "lastError": "API Key를 등록한 뒤 Health Check를 실행하세요.",
                        }
                    )
                hydrated[key] = item.model_copy(update=updates)
            self._items = hydrated
            if not self._items:
                self._seed_from_settings()

    def _seed_from_settings(self) -> None:
        settings = get_settings()
        endpoint, api_path, models_path = _public_endpoint_and_paths(settings.llm_base_url)
        created = self.create(
            ModelProfileCreate(
                displayName=f"기본 로컬 모델 · {settings.llm_model}",
                endpoint=endpoint,
                apiBasePath=api_path,
                modelsPath=models_path,
                modelId=settings.llm_model,
                deploymentType="internal",
                capabilities=["chat", "code"],
                contextWindow=32768,
                supportsStructuredOutput=True,
                qualityScore=75,
                costScore=95,
                speedScore=80,
                reliabilityScore=75,
                apiKey=settings.llm_api_key,
            )
        )
        if settings.embedding_model and settings.embedding_model != settings.llm_model:
            self.create(
                ModelProfileCreate(
                    displayName=f"기본 임베딩 · {settings.embedding_model}",
                    endpoint=endpoint,
                    apiBasePath=api_path,
                    modelsPath=models_path,
                    modelId=settings.embedding_model,
                    deploymentType="internal",
                    capabilities=["embedding"],
                    contextWindow=8192,
                    supportsStructuredOutput=False,
                    qualityScore=70,
                    costScore=95,
                    speedScore=85,
                    reliabilityScore=75,
                    apiKey=settings.llm_api_key,
                )
            )
        return created

    def _persist(self) -> None:
        kv_set(MODEL_PROFILES_KEY, [item.model_dump(mode="json") for item in self._items.values()])
        kv_set(MODEL_SECRETS_KEY, {})

    def list(self) -> list[ModelProfile]:
        with self._lock:
            return sorted(self._items.values(), key=lambda item: item.createdAt)

    def get(self, model_profile_id: str) -> ModelProfile | None:
        with self._lock:
            return self._items.get(model_profile_id)

    def require(self, model_profile_id: str) -> ModelProfile:
        item = self.get(model_profile_id)
        if item is None:
            raise KeyError(f"model profile not found: {model_profile_id}")
        return item

    def secret(self, model_profile_id: str) -> str | None:
        with self._lock:
            return self._secrets.get(model_profile_id)

    def create(self, payload: ModelProfileCreate) -> ModelProfile:
        now = utc_now()
        item_id = f"MODEL-{uuid4().hex[:12]}"
        data = payload.model_dump(exclude={"apiKey"})
        item = ModelProfile(
            id=item_id,
            **data,
            hasApiKey=bool(payload.apiKey),
            createdAt=now,
            updatedAt=now,
        )
        with self._lock:
            if payload.apiKey:
                self._secret_store.set(item_id, payload.apiKey)
            self._items[item_id] = item
            if payload.apiKey:
                self._secrets[item_id] = payload.apiKey
            self._persist()
        return item

    def update(self, model_profile_id: str, payload: ModelProfileUpdate) -> ModelProfile | None:
        with self._lock:
            item = self._items.get(model_profile_id)
            if item is None:
                return None
            updates = payload.model_dump(exclude_none=True, exclude={"apiKey"})
            if payload.apiKey is not None:
                if payload.apiKey:
                    self._secret_store.set(model_profile_id, payload.apiKey)
                    self._secrets[model_profile_id] = payload.apiKey
                    updates["hasApiKey"] = True
                else:
                    self._secret_store.delete(model_profile_id)
                    self._secrets.pop(model_profile_id, None)
                    updates["hasApiKey"] = False
            updates["updatedAt"] = utc_now()
            item = item.model_copy(update=updates)
            self._items[model_profile_id] = item
            self._persist()
            return item

    def delete(self, model_profile_id: str) -> bool:
        with self._lock:
            if model_profile_id not in self._items:
                return False
            self._secret_store.delete(model_profile_id)
            self._items.pop(model_profile_id, None)
            self._secrets.pop(model_profile_id, None)
            self._persist()
            return True

    @staticmethod
    def _models_url(item: ModelProfile) -> str:
        parts = urlsplit(str(item.endpoint))
        if parts.username or parts.password or parts.scheme not in {"http", "https"}:
            raise ValueError("only HTTP(S) endpoints without embedded credentials are supported")
        base = urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
        return f"{base}{item.modelsPath}"

    def health_check(self, model_profile_id: str, timeout: float = 5.0) -> ModelProfile:
        item = self.require(model_profile_id)
        started = time.monotonic()
        status = "down"
        error: str | None = None
        discovered: list[str] = []
        try:
            headers = {}
            secret = self.secret(model_profile_id)
            if secret:
                headers["Authorization"] = f"Bearer {secret}"
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.get(self._models_url(item), headers=headers)
                response.raise_for_status()
                body = response.json()
            rows = body.get("data") if isinstance(body, dict) else None
            if isinstance(rows, list):
                discovered = [str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")]
            status = "up" if item.modelId in discovered else "degraded"
            if status == "degraded":
                error = "endpoint reachable, configured model was not listed"
        except Exception as exc:
            error = str(exc)[:500]
        latency = int((time.monotonic() - started) * 1000)
        with self._lock:
            updated = item.model_copy(
                update={
                    "healthStatus": status,
                    "lastHealthAt": utc_now(),
                    "healthLatencyMs": latency,
                    "lastError": error,
                    "discoveredModels": discovered[:200],
                    "updatedAt": utc_now(),
                }
            )
            self._items[model_profile_id] = updated
            self._persist()
            return updated
