from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.services.interaction_graph_models import InteractionGraphSummary


class ScenarioCreateRequest(BaseModel):
    serviceId: str = "multi"


class ScenarioSummary(BaseModel):
    scenarioId: str
    serviceId: str = "multi"
    projectId: str | None = None
    graphId: str | None = None
    name: str = ""
    version: str = "1"
    status: str = "DRAFT"
    artifactPath: str | None = None
    unresolvedCount: int = 0
    createdAt: str | None = None
    businessPath: list[str] = Field(default_factory=list)
    assignedRole: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


class ScenarioScopedGraph(InteractionGraphSummary):
    """시나리오 한 건에 근거가 있는 노드·엣지만 남긴 Interaction Graph.

    화면 렌더 계약은 `InteractionGraphSummary`와 같고, 어떤 시나리오 범위인지와
    근거 부족(`missingData`)만 추가로 알린다.
    """

    scopedScenarioId: str
    scopedScenarioName: str = ""
    sourceGraphId: str | None = None
    seedNodeIds: list[str] = Field(default_factory=list)
    missingData: list[str] = Field(default_factory=list)


class PipelineRequest(BaseModel):
    serviceId: str = "multi"
    frontendSubdir: str | None = None
    backendSubdir: str | None = None
    frontendAnalysisId: str | None = None
    backendAnalysisId: str | None = None


class PipelineResult(BaseModel):
    projectId: str
    serviceId: str
    status: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    frontendAnalysisId: str | None = None
    backendAnalysisId: str | None = None
    mappingSetId: str | None = None
    graphId: str | None = None
    scenarioIds: list[str] = Field(default_factory=list)
    contractIds: list[str] = Field(default_factory=list)
    recommendationIds: list[str] = Field(default_factory=list)
    message: str | None = None
