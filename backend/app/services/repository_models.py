from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceType(str, Enum):
    github = "github"
    local = "local"


class RepoRole(str, Enum):
    frontend = "frontend"
    backend = "backend"
    # Whole git/local workspace (no FE/BE subdir required)
    workspace = "workspace"


class SyncStatus(str, Enum):
    pending = "pending"
    progressing = "progressing"
    complete = "complete"
    error = "error"
    cached = "cached"


class JourneyStatus(str, Enum):
    pending = "pending"
    progressing = "progressing"
    complete = "complete"
    error = "error"


class RepositoryRegister(BaseModel):
    role: RepoRole
    sourceType: SourceType
    url: str | None = None
    path: str | None = None
    # Monorepo relative root inside clone/local path (e.g. frontend, src/frontend).
    subdir: str | None = None
    branch: str = "main"
    commitSha: str | None = None
    # Accepted once; never returned in API responses.
    token: str | None = Field(default=None, exclude=True)


class FileInventoryItem(BaseModel):
    path: str
    language: str | None = None
    sizeBytes: int
    sha256: str
    roleHint: str | None = None


class Repository(BaseModel):
    id: str
    role: RepoRole
    sourceType: SourceType
    url: str | None = None
    path: str | None = None
    subdir: str | None = None
    branch: str
    commitSha: str | None = None
    # 명시 커밋이 없으면 branch HEAD를 추적한다. 이전 저장 데이터는 branch 추적으로 본다.
    trackBranch: bool = True
    workspacePath: str | None = None
    stack: dict[str, Any] = Field(default_factory=dict)
    fileCount: int = 0
    syncStatus: SyncStatus = SyncStatus.pending
    lastError: str | None = None
    # Never expose credentials
    hasCredential: bool = False

    @field_serializer("url")
    def mask_url(self, value: str | None) -> str | None:
        if not value:
            return value
        # strip embedded userinfo if any
        if "@" in value and "://" in value:
            scheme, rest = value.split("://", 1)
            if "@" in rest:
                rest = rest.split("@", 1)[1]
                return f"{scheme}://***@{rest}" if False else f"{scheme}://{rest}"
        return value


class RepositorySet(BaseModel):
    id: str
    projectId: str
    # User-facing connection name (목록·분석·일괄처리 기준 키)
    name: str = "기본 저장소"
    repositories: list[Repository] = Field(default_factory=list)
    status: SyncStatus = SyncStatus.pending
    journeyStep: Literal["project", "repository"] = "repository"
    journeyStatus: JourneyStatus = JourneyStatus.pending
    lastSyncedAt: datetime | None = None
    retryCount: int = 0
    logs: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    ownerUserId: str | None = Field(default=None, max_length=120)
    aiPolicy: Literal["auto", "cost_saver", "balanced", "highest_quality", "internal_only"] = "auto"
    modelSelectionMode: Literal["auto", "manual"] = "auto"
    modelBindings: dict[
        Literal["general", "vision", "embedding", "advanced", "image_generation"],
        str,
    ] = Field(default_factory=dict)


class Project(BaseModel):
    id: str
    name: str
    description: str | None = None
    ownerUserId: str = "QA-DEFAULT"
    aiPolicy: Literal["auto", "cost_saver", "balanced", "highest_quality", "internal_only"] = "auto"
    modelSelectionMode: Literal["auto", "manual"] = "auto"
    modelBindings: dict[
        Literal["general", "vision", "embedding", "advanced", "image_generation"],
        str,
    ] = Field(default_factory=dict)
    # Primary / latest repository connection for this project
    repositorySetId: str | None = None
    repositorySetIds: list[str] = Field(default_factory=list)
    journey: dict[str, str] = Field(
        default_factory=lambda: {
            "project": JourneyStatus.complete.value,
            "repository": JourneyStatus.pending.value,
            "scenarioCreate": JourneyStatus.pending.value,
            "scenarioList": JourneyStatus.pending.value,
            "testRun": JourneyStatus.pending.value,
        }
    )
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime | None = None


class SyncRequest(BaseModel):
    force: bool = False
