from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from pydantic import BaseModel

from app.api.deps import get_platform_store
from app.services.interaction_graph import InteractionGraphService
from app.services.interaction_graph_models import (
    EDGE_CONDITION_PRESETS,
    EDGE_TYPES,
    EdgeCreateRequest,
    EdgePatchRequest,
    InteractionGraphCreateRequest,
    InteractionGraphSummary,
)


class EdgeOptions(BaseModel):
    """Allowed edge types and preset conditions the console offers."""

    types: list[str]
    conditionPresets: list[str]

router = APIRouter(prefix="/api", tags=["interaction-graphs"])


def _service() -> InteractionGraphService:
    return InteractionGraphService(get_platform_store())


@router.post(
    "/analyses/{project_id}/interaction-graphs",
    response_model=InteractionGraphSummary,
)
def create_interaction_graph(
    project_id: str, payload: InteractionGraphCreateRequest | None = None
) -> InteractionGraphSummary:
    try:
        return _service().create_for_project(
            project_id, payload or InteractionGraphCreateRequest()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/interaction-graphs", response_model=list[InteractionGraphSummary])
def list_interaction_graphs(
    projectId: str | None = Query(default=None),
) -> list[InteractionGraphSummary]:
    return _service().list_graphs(projectId)


# Declared before /{graph_id} so the literal path is not captured as an id.
@router.get("/interaction-graphs/edge-options", response_model=EdgeOptions)
def get_interaction_graph_edge_options() -> EdgeOptions:
    return EdgeOptions(
        types=list(EDGE_TYPES),
        conditionPresets=list(EDGE_CONDITION_PRESETS),
    )


@router.get("/interaction-graphs/{graph_id}", response_model=InteractionGraphSummary)
def get_interaction_graph(graph_id: str) -> InteractionGraphSummary:
    item = _service().get_graph(graph_id)
    if not item:
        raise HTTPException(status_code=404, detail="graph not found")
    return item


@router.get("/interaction-graphs/{graph_id}/paths")
def get_interaction_graph_paths(
    graph_id: str,
    from_: str = Query(alias="from"),
    to: str = Query(...),
) -> dict:
    try:
        return _service().find_paths(graph_id, from_, to)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/interaction-graphs/{graph_id}")
def delete_interaction_graph(graph_id: str) -> dict:
    if not _service().delete_graph(graph_id):
        raise HTTPException(status_code=404, detail="graph not found")
    return {"status": "deleted", "graphId": graph_id, "message": "플로우 그래프가 삭제되었습니다."}


@router.post("/interaction-graphs/bulk-delete")
def bulk_delete_interaction_graphs(payload: dict) -> dict:
    ids = list(payload.get("graphIds") or [])
    if not ids:
        raise HTTPException(status_code=400, detail="graphIds required")
    return _service().delete_graphs(ids)


@router.patch("/interaction-graphs/{graph_id}/edges/{edge_id}")
def patch_interaction_graph_edge(
    graph_id: str, edge_id: str, payload: EdgePatchRequest
) -> InteractionGraphSummary:
    try:
        return _service().patch_edge(graph_id, edge_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/interaction-graphs/{graph_id}/edges/{edge_id}")
def delete_interaction_graph_edge(graph_id: str, edge_id: str) -> InteractionGraphSummary:
    try:
        return _service().delete_edge(graph_id, edge_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/interaction-graphs/{graph_id}/edges")
def create_interaction_graph_edge(
    graph_id: str, payload: EdgeCreateRequest
) -> InteractionGraphSummary:
    try:
        return _service().create_edge(graph_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
