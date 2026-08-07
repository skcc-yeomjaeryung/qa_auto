from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComponentContractBuildRequest(BaseModel):
    frontendAnalysisId: str | None = None
    backendAnalysisId: str | None = None
    adapterPath: str | None = None
    serviceId: str | None = None


class ComponentContractSummary(BaseModel):
    contractId: str
    scenarioId: str | None = None
    serviceId: str = "customer-search"
    projectId: str | None = None
    graphId: str | None = None
    artifactPath: str | None = None
    inputCount: int = 0
    outputCount: int = 0
    warningCount: int = 0
    mismatchCount: int = 0
    createdAt: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
