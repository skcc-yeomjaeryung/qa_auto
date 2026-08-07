from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "qa-auto-backend"
    version: str = "0.1.0"
    workspace_root: str = Field(
        default=str(REPO_ROOT / ".data" / "workspaces"),
        validation_alias="WORKSPACE_ROOT",
    )
    data_dir: str = Field(
        default=str(REPO_ROOT / ".data"),
        validation_alias="DATA_DIR",
    )
    evidence_retention_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        validation_alias="QA_AUTO_EVIDENCE_RETENTION_DAYS",
    )
    # Local OpenAI-compatible endpoint only (D-014). Disabled → deterministic fallback.
    llm_enabled: bool = Field(default=True, validation_alias="LLM_ENABLED")
    llm_base_url: str = Field(
        default="http://127.0.0.1:11434/v1",
        validation_alias="LLM_BASE_URL",
    )
    llm_model: str = Field(default="llama3.2", validation_alias="LLM_MODEL")
    embedding_model: str = Field(
        default="nomic-embed-text",
        validation_alias="EMBEDDING_MODEL",
    )
    llm_api_key: str = Field(default="local", validation_alias="LLM_API_KEY")
    llm_temperature: float = Field(default=0.2, validation_alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, validation_alias="LLM_MAX_TOKENS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
