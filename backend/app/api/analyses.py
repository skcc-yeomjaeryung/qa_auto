from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_platform_store
from app.services.analysis_models import (
    AnalysisSummary,
    BackendAnalysisRequest,
    FrontendAnalysisRequest,
)
from app.services.backend_analysis import BackendAnalysisService
from app.services.frontend_analysis import FrontendAnalysisService

router = APIRouter(prefix="/api", tags=["analyses"])


def _fe_service() -> FrontendAnalysisService:
    return FrontendAnalysisService(get_platform_store())


def _be_service() -> BackendAnalysisService:
    return BackendAnalysisService(get_platform_store())


@router.post("/analyses/frontend", response_model=AnalysisSummary)
def post_frontend_analysis(payload: FrontendAnalysisRequest) -> AnalysisSummary:
    try:
        return _fe_service().run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyses/backend", response_model=AnalysisSummary)
def post_backend_analysis(payload: BackendAnalysisRequest) -> AnalysisSummary:
    try:
        return _be_service().run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}", response_model=AnalysisSummary)
def get_analysis(analysis_id: str) -> AnalysisSummary:
    item = get_platform_store().get_analysis(analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="analysis not found")
    return item


@router.get("/analyses/{analysis_id}/frontend/screens")
def get_frontend_screens(analysis_id: str) -> list[dict]:
    item = _require_role(analysis_id, "frontend")
    return list(item.result.get("screens", []))


@router.get("/analyses/{analysis_id}/frontend/components/{component_id}")
def get_frontend_component(analysis_id: str, component_id: str) -> dict:
    item = _require_role(analysis_id, "frontend")
    for component in item.result.get("components", []):
        if component.get("id") == component_id:
            return {
                "component": component,
                "inputs": [
                    i
                    for i in item.result.get("inputs", [])
                    if i.get("componentId") == component_id
                    or component.get("name", "") in (i.get("name") or "")
                ],
                "events": [
                    e
                    for e in item.result.get("events", [])
                    if e.get("componentId") == component_id
                    or e.get("evidence", {}).get("file")
                    == component.get("evidence", {}).get("file")
                ],
            }
    raise HTTPException(status_code=404, detail="component not found")


@router.get("/analyses/{analysis_id}/frontend/unresolved")
def get_frontend_unresolved(analysis_id: str) -> list[dict]:
    item = _require_role(analysis_id, "frontend")
    return list(item.result.get("unresolved", []))


@router.get("/analyses/{analysis_id}/frontend")
def get_frontend_full(analysis_id: str) -> dict:
    item = _require_role(analysis_id, "frontend")
    return item.result


@router.get("/analyses/{analysis_id}/backend/endpoints")
def get_backend_endpoints(analysis_id: str) -> list[dict]:
    item = _require_role(analysis_id, "backend")
    return list(item.result.get("endpoints", []))


@router.get("/analyses/{analysis_id}/backend/endpoints/{endpoint_id}")
def get_backend_endpoint(analysis_id: str, endpoint_id: str) -> dict:
    item = _require_role(analysis_id, "backend")
    for endpoint in item.result.get("endpoints", []):
        if endpoint.get("id") == endpoint_id:
            return {
                "endpoint": endpoint,
                "requestDtos": [
                    d
                    for d in item.result.get("requestDtos", [])
                    if d.get("name") == endpoint.get("requestDto")
                ],
                "responseDtos": [
                    d
                    for d in item.result.get("responseDtos", [])
                    if d.get("name") == endpoint.get("responseDto")
                ],
                "validations": [
                    v
                    for v in item.result.get("validations", [])
                    if v.get("target") == endpoint.get("requestDto")
                ],
            }
    raise HTTPException(status_code=404, detail="endpoint not found")


@router.get("/analyses/{analysis_id}/backend/unresolved")
def get_backend_unresolved(analysis_id: str) -> list[dict]:
    item = _require_role(analysis_id, "backend")
    return list(item.result.get("unresolved", []))


@router.get("/analyses/{analysis_id}/backend")
def get_backend_full(analysis_id: str) -> dict:
    item = _require_role(analysis_id, "backend")
    return item.result


def _require_role(analysis_id: str, role: str) -> AnalysisSummary:
    item = get_platform_store().get_analysis(analysis_id)
    if not item:
        raise HTTPException(status_code=404, detail="analysis not found")
    if item.role != role:
        raise HTTPException(status_code=400, detail=f"not a {role} analysis")
    if item.status != "complete" or not item.result:
        raise HTTPException(status_code=409, detail=f"analysis not complete: {item.status}")
    return item
