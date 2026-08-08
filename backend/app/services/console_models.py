"""Console UX contracts — project connect, resource tree, bulk actions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.services.environment_models import PILOT_SANDBOX_BASE_URL
from app.services.repository_models import SourceType


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    aiPolicy: Literal["auto", "cost_saver", "balanced", "highest_quality", "internal_only"] | None = None
    modelSelectionMode: Literal["auto", "manual"] | None = None
    modelBindings: dict[
        Literal["general", "vision", "embedding", "advanced", "image_generation"],
        str,
    ] | None = None


class RepositoryUpdate(BaseModel):
    url: str | None = None
    path: str | None = None
    subdir: str | None = None
    branch: str | None = None
    token: str | None = Field(default=None, exclude=True)


class RepoSourceSpec(BaseModel):
    url: str | None = None
    path: str | None = None
    subdir: str | None = None
    branch: str = "main"
    token: str | None = Field(default=None, exclude=True)


class ConnectPairRequest(BaseModel):
    """Connect a git/local repository into a project, then auto-sync.

    Preferred: `repository` alone (whole tree, no FE/BE subdir).
    Legacy: optional `frontend` / `backend` pair with subdirs.
    """

    projectId: str | None = None
    # Edit wizard: update this stored connection in place instead of creating a second row.
    repositorySetId: str | None = None
    ownerUserId: str | None = None
    # When creating a new project together with first connection
    projectName: str | None = None
    description: str | None = None
    # User-facing repository connection name (목록 기준)
    repositoryName: str = Field(min_length=1, max_length=200)
    sourceType: SourceType = SourceType.local
    # Single repository root (GitHub URL or local path) — preferred
    repository: RepoSourceSpec | None = None
    frontend: RepoSourceSpec | None = None
    backend: RepoSourceSpec | None = None
    autoAnalyze: bool = True

    @model_validator(mode="after")
    def _require_source(self) -> "ConnectPairRequest":
        if self.repository is not None:
            return self
        if self.frontend is not None or self.backend is not None:
            return self
        raise ValueError("repository (or frontend/backend) source required")


class ConnectResult(BaseModel):
    projectId: str
    repositorySetId: str
    repositoryName: str
    status: str
    message: str
    syncStatus: str
    analysisStarted: bool = False
    frontendRepoId: str | None = None
    backendRepoId: str | None = None
    workspaceRepoId: str | None = None


class BulkAnalyzeRequest(BaseModel):
    # Prefer repository set ids (저장소 이름 단위)
    repositorySetIds: list[str] = Field(default_factory=list)
    repositoryIds: list[str] = Field(default_factory=list)
    projectId: str | None = None
    force: bool = False


class BulkAnalyzeResult(BaseModel):
    status: str
    message: str
    results: list[dict[str, Any]] = Field(default_factory=list)


class ResourceNode(BaseModel):
    id: str
    name: str
    path: str
    kind: Literal["dir", "file"] = "dir"
    role: str | None = None
    depth: int = 0
    excluded: bool = False
    selected: bool = True
    children: list[ResourceNode] = Field(default_factory=list)
    hasMore: bool = False


class ResourceTreeResponse(BaseModel):
    analysisId: str = ""
    repositorySetId: str | None = None
    repositoryId: str | None = None
    role: str
    rootPath: str
    label: str
    nodes: list[ResourceNode] = Field(default_factory=list)


class ResourceSelectionUpdate(BaseModel):
    analysisId: str
    excludedPaths: list[str] = Field(default_factory=list)
    selectedPaths: list[str] = Field(default_factory=list)


class ResourceSelectionState(BaseModel):
    analysisId: str
    excludedPaths: list[str] = Field(default_factory=list)
    selectedPaths: list[str] = Field(default_factory=list)


class ScenarioGenerateRequest(BaseModel):
    projectId: str
    analysisIds: list[str] = Field(default_factory=list)
    serviceId: str | None = None
    excludedPaths: list[str] = Field(default_factory=list)
    sourceMode: Literal["ai", "test_data_csv"] = "ai"
    testDataRows: list["TestDataScenarioRow"] = Field(default_factory=list, max_length=500)


class TestDataScenarioRow(BaseModel):
    scenarioId: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    description: str = Field(min_length=1, max_length=2_000)
    requestNaturalLanguage: str = Field(min_length=1, max_length=4_000)
    responseNaturalLanguage: str = Field(min_length=1, max_length=4_000)
    role: str | None = Field(default=None, max_length=80)
    businessPath: str | None = Field(default=None, max_length=300)


# 이 도메인 모델을 pytest 테스트 클래스로 오인하지 않게 한다.
TestDataScenarioRow.__test__ = False


class BulkRunRequest(BaseModel):
    scenarioIds: list[str] = Field(min_length=1)
    consent: bool = False
    baseUrl: str = PILOT_SANDBOX_BASE_URL
    environmentId: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    scenarioAccountIds: dict[str, str] = Field(default_factory=dict)


class BulkRunResult(BaseModel):
    status: str
    message: str
    runs: list[dict[str, Any]] = Field(default_factory=list)


class FlowNodePatch(BaseModel):
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None


class FlowNodeRetryRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class FlowNodeRuntime(BaseModel):
    nodeId: str
    graphId: str
    method: str | None = None
    operation: dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "failure", "warning", "pending", "unknown"] = "unknown"
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    errorMessage: str | None = None
    lastRetriedAt: str | None = None
