from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import get_platform_store
from app.services.scenario_models import (
    ScenarioCreateRequest,
    ScenarioScopedGraph,
    ScenarioSummary,
)
from app.services.scenario_service import ScenarioService

router = APIRouter(prefix="/api", tags=["scenarios"])


def _service() -> ScenarioService:
    return ScenarioService(get_platform_store())


@router.post(
    "/interaction-graphs/{graph_id}/scenarios",
    response_model=list[ScenarioSummary],
)
def create_scenarios(
    graph_id: str, payload: ScenarioCreateRequest | None = None
) -> list[ScenarioSummary]:
    try:
        return _service().create_from_graph(graph_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/scenarios", response_model=list[ScenarioSummary])
def list_scenarios(
    projectId: str | None = Query(default=None),
    serviceId: str | None = Query(default=None),
) -> list[ScenarioSummary]:
    return _service().list_scenarios(project_id=projectId, service_id=serviceId)


@router.post("/scenarios/bulk-delete")
def bulk_delete_scenarios(payload: dict) -> dict:
    ids = list(payload.get("scenarioIds") or [])
    try:
        return _service().delete_many(ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scenarios/{scenario_id}", response_model=ScenarioSummary)
def get_scenario(scenario_id: str) -> ScenarioSummary:
    item = _service().get(scenario_id)
    if not item:
        raise HTTPException(status_code=404, detail="scenario not found")
    return item


@router.get("/scenarios/{scenario_id}/interaction-graph", response_model=ScenarioScopedGraph)
def get_scenario_interaction_graph(scenario_id: str) -> ScenarioScopedGraph:
    """이 시나리오와 근거가 연결된 컴포넌트만 남긴 의존관계 그래프."""
    try:
        return _service().scoped_graph(scenario_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str) -> dict:
    if not _service().delete(scenario_id):
        raise HTTPException(status_code=404, detail="scenario not found")
    return {"status": "deleted", "scenarioId": scenario_id, "message": "시나리오가 삭제되었습니다."}


@router.post("/scenarios/{scenario_id}/validate")
def validate_scenario(scenario_id: str) -> dict:
    try:
        return _service().validate(scenario_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid: {exc}") from exc


@router.post("/scenarios/{scenario_id}/versions", response_model=ScenarioSummary)
def bump_scenario_version(scenario_id: str) -> ScenarioSummary:
    try:
        return _service().add_version(scenario_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/scenarios/{scenario_id}/diff")
def scenario_diff(
    scenario_id: str,
    from_: str = Query(alias="from"),
    to: str = Query(...),
) -> dict:
    try:
        return _service().diff(scenario_id, from_, to)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
