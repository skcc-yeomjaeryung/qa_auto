from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import get_platform_store
from app.services.interaction_graph_models import InteractionGraphSummary

router = APIRouter(prefix="/api/flows", tags=["flows"])


@router.get("/by-service/{service_id}")
def get_flow_by_service(
    service_id: str,
    projectId: str | None = Query(default=None),
) -> dict:
    store = get_platform_store()
    graph = store.find_graph_by_service(service_id, projectId)
    if not graph:
        raise HTTPException(status_code=404, detail="no graph for serviceId")
    scenarios = store.list_scenarios(project_id=projectId, service_id=service_id)
    return {
        "serviceId": service_id,
        "projectId": projectId or graph.projectId,
        "graphId": graph.graphId,
        "graph": graph,
        "scenarioIds": [s.scenarioId for s in scenarios],
    }
