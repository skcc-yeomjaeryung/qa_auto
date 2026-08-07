from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


AiPolicy = Literal[
    "auto",
    "cost_saver",
    "balanced",
    "highest_quality",
    "internal_only",
]
ModelCapability = Literal[
    "chat",
    "code",
    "vision",
    "embedding",
    "tools",
    "image_generation",
]
HealthStatus = Literal["unknown", "up", "degraded", "down"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelProfileBase(BaseModel):
    displayName: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="openai-compatible", min_length=1, max_length=80)
    endpoint: HttpUrl
    apiBasePath: str = "/v1"
    modelsPath: str = "/v1/models"
    modelId: str = Field(min_length=1, max_length=200)
    deploymentType: Literal["internal", "external"] = "internal"
    capabilities: list[ModelCapability] = Field(default_factory=lambda: ["chat", "code"])
    contextWindow: int = Field(default=8192, ge=256, le=10_000_000)
    supportsStructuredOutput: bool = True
    supportsTools: bool = False
    enabled: bool = True
    qualityScore: int = Field(default=70, ge=0, le=100)
    costScore: int = Field(default=70, ge=0, le=100)
    speedScore: int = Field(default=70, ge=0, le=100)
    reliabilityScore: int = Field(default=70, ge=0, le=100)

    @field_validator("apiBasePath", "modelsPath")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/") or ".." in value:
            raise ValueError("path must start with / and must not contain ..")
        return value.rstrip("/") or "/"

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[ModelCapability]) -> list[ModelCapability]:
        return list(dict.fromkeys(value))


class ModelProfileCreate(ModelProfileBase):
    apiKey: str | None = Field(default=None, max_length=4096, exclude=True)


class ModelProfileUpdate(BaseModel):
    displayName: str | None = Field(default=None, min_length=1, max_length=120)
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    endpoint: HttpUrl | None = None
    apiBasePath: str | None = None
    modelsPath: str | None = None
    modelId: str | None = Field(default=None, min_length=1, max_length=200)
    deploymentType: Literal["internal", "external"] | None = None
    capabilities: list[ModelCapability] | None = None
    contextWindow: int | None = Field(default=None, ge=256, le=10_000_000)
    supportsStructuredOutput: bool | None = None
    supportsTools: bool | None = None
    enabled: bool | None = None
    qualityScore: int | None = Field(default=None, ge=0, le=100)
    costScore: int | None = Field(default=None, ge=0, le=100)
    speedScore: int | None = Field(default=None, ge=0, le=100)
    reliabilityScore: int | None = Field(default=None, ge=0, le=100)
    apiKey: str | None = Field(default=None, max_length=4096, exclude=True)


class ModelProfile(ModelProfileBase):
    id: str
    healthStatus: HealthStatus = "unknown"
    lastHealthAt: datetime | None = None
    healthLatencyMs: int | None = None
    lastError: str | None = None
    discoveredModels: list[str] = Field(default_factory=list)
    hasApiKey: bool = False
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)


class ModelRequirement(BaseModel):
    capabilities: list[ModelCapability] = Field(default_factory=list)
    minimumContext: int = 0
    structuredOutput: bool = False
    tools: bool = False
    qualityProfile: str = "general"
    allowDeterministicFallback: bool = True


class CandidateEvaluation(BaseModel):
    modelProfileId: str
    displayName: str
    modelId: str
    eligible: bool
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)


class ModelDecision(BaseModel):
    route: Literal["model", "deterministic_fallback"]
    policy: AiPolicy
    selectedModelProfileId: str | None = None
    selectedDisplayName: str | None = None
    selectedModelId: str | None = None
    selectionMode: Literal["auto", "manual"] = "auto"
    selectionRole: Literal[
        "general",
        "vision",
        "embedding",
        "advanced",
        "image_generation",
    ] | None = None
    decisionSummary: str
    candidates: list[CandidateEvaluation] = Field(default_factory=list)
    promptName: str = "model_advisor"
    promptVersion: str = "deterministic-policy/v1"
