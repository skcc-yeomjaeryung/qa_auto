from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DocumentKind = Literal["scenario_csv", "design_ppt", "unknown"]
DocumentStatus = Literal["queued", "extracting", "embedding", "ready", "partial", "error"]


class ProjectContextDocument(BaseModel):
    id: str
    projectId: str
    ownerUserId: str
    fileName: str
    contentType: str
    kind: DocumentKind
    status: DocumentStatus = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    sizeBytes: int = Field(ge=0)
    chunkCount: int = 0
    scenarioHintCount: int = 0
    summary: str | None = None
    processingMode: str | None = None
    indexBackend: str | None = None
    error: str | None = None
    missingData: list[str] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime


class ProjectContextSearchResult(BaseModel):
    status: Literal["found", "not_found"]
    projectId: str
    query: str
    documents: list[dict] = Field(default_factory=list)
    chunks: list[dict] = Field(default_factory=list)
    promptContext: str = ""
    guardrails: list[str] = Field(default_factory=list)

