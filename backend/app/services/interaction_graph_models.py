from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InteractionGraphCreateRequest(BaseModel):
    frontendAnalysisId: str | None = None
    backendAnalysisId: str | None = None
    mappingSetId: str | None = None
    frontendAnalysisPath: str | None = None
    backendAnalysisPath: str | None = None
    apiMappingPath: str | None = None


EDGE_TYPES: tuple[str, ...] = (
    "contains",
    "triggers",
    "validates",
    "calls",
    "receives",
    "returns",
    "navigates_to",
    "binds_to",
    "asserts",
    "branches_to",
)

# Preset conditions the console offers. Free text stays allowed — analysis may
# surface a condition these presets do not cover.
EDGE_CONDITION_PRESETS: tuple[str, ...] = (
    "happy_path",
    "validation_error",
    "auth_required",
    "not_found",
    "server_error",
    "empty_result",
)


class EdgePatchRequest(BaseModel):
    """Edit an existing edge. Omitted fields keep their current value."""

    to: str | None = None
    newTo: str | None = None
    condition: str | None = None
    clearCondition: bool = False
    type: str | None = None

    def resolved_to(self) -> str | None:
        return self.to or self.newTo


class EdgeCreateRequest(BaseModel):
    """Connect two existing nodes. Nodes are never invented."""

    from_: str = Field(alias="from")
    to: str
    type: str = "navigates_to"
    condition: str | None = None

    model_config = {"populate_by_name": True}


class InteractionGraphSummary(BaseModel):
    graphId: str
    projectId: str | None = None
    repositorySetId: str | None = None
    frontendAnalysisId: str | None = None
    backendAnalysisId: str | None = None
    mappingSetId: str | None = None
    serviceId: str = "multi"
    status: str = "complete"
    artifactPath: str | None = None
    version: str = "1"
    commitRefs: dict[str, str] = Field(default_factory=dict)
    nodeCount: int = 0
    edgeCount: int = 0
    primaryPath: list[str] = Field(default_factory=list)
    branches: list[dict[str, Any]] = Field(default_factory=list)
    unresolvedCount: int = 0
    createdAt: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
