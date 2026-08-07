from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ApiMappingCreateRequest(BaseModel):
    frontendAnalysisId: str | None = None
    backendAnalysisId: str | None = None
    frontendAnalysisPath: str | None = None
    backendAnalysisPath: str | None = None


class ApiMappingPatchRequest(BaseModel):
    status: Literal["confirmed", "rejected", "candidate", "ambiguous", "unmapped"]
    note: str | None = None
    backendEndpointId: str | None = None


class MappingSetSummary(BaseModel):
    mappingSetId: str
    projectId: str | None = None
    frontendAnalysisId: str | None = None
    backendAnalysisId: str | None = None
    status: str = "complete"
    artifactPath: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    mappings: list[dict[str, Any]] = Field(default_factory=list)
    unmappedFrontendCalls: list[str] = Field(default_factory=list)
    unmappedBackendEndpoints: list[str] = Field(default_factory=list)
    createdAt: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
