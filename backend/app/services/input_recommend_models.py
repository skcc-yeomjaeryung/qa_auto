from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RecommendInputsRequest(BaseModel):
    seed: int = 42
    contractId: str | None = None
    buildProfile: bool = False
    budget: int = 8
    unresolvedPolicy: str = "reviewRequired"
    profileName: str | None = None


class InputProfileCreateRequest(BaseModel):
    name: str = "batch profile"
    seed: int = 42
    budget: int = 8
    unresolvedPolicy: str = "reviewRequired"
    categories: list[str] | None = None
    recommendationId: str | None = None
    # Phase 13 — 건별 화면에서 사용자가 수정한 값을 첫 Case로 고정한다
    overrides: dict[str, Any] = Field(default_factory=dict)


class InputProfileApproveRequest(BaseModel):
    approvedBy: str = "qa-pilot"


class GenerateCasesRequest(BaseModel):
    budget: int | None = None
    unresolvedPolicy: str | None = None
    categories: list[str] | None = None
    seed: int | None = None


class RecommendationSummary(BaseModel):
    recommendationId: str
    scenarioId: str | None = None
    serviceId: str = "customer-search"
    projectId: str | None = None
    contractId: str | None = None
    artifactPath: str | None = None
    defaultCount: int = 0
    recommendationCount: int = 0
    createdAt: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class InputProfileSummary(BaseModel):
    profileId: str
    scenarioId: str
    serviceId: str = "customer-search"
    projectId: str | None = None
    name: str = ""
    version: str = "1"
    status: str = "DRAFT"
    caseCount: int = 0
    categoryCounts: dict[str, int] = Field(default_factory=dict)
    recommendationId: str | None = None
    approvedAt: str | None = None
    approvedBy: str | None = None
    createdAt: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
