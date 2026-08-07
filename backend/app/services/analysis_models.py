from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FrontendAnalysisRequest(BaseModel):
    projectId: str
    repositorySetId: str | None = None
    workspacePath: str | None = None
    commitSha: str | None = None
    force: bool = False


class BackendAnalysisRequest(FrontendAnalysisRequest):
    pass


class AnalysisSummary(BaseModel):
    id: str
    projectId: str
    repositorySetId: str | None = None
    role: str = "frontend"
    commitSha: str | None = None
    workspacePath: str | None = None
    status: str
    screenCount: int = 0
    componentCount: int = 0
    endpointCount: int = 0
    unresolvedCount: int = 0
    fileTotal: int = 0
    fileCompleted: int = 0
    fileFailed: int = 0
    progressPercent: int = Field(default=0, ge=0, le=100)
    artifactPath: str | None = None
    error: str | None = None
    createdAt: str
    result: dict[str, Any] = Field(default_factory=dict)
