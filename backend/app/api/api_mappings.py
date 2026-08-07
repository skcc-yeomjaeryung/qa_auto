from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_platform_store
from app.services.api_mapping import ApiMappingService
from app.services.api_mapping_models import (
    ApiMappingCreateRequest,
    ApiMappingPatchRequest,
    MappingSetSummary,
)

router = APIRouter(prefix="/api", tags=["api-mappings"])


def _service() -> ApiMappingService:
    return ApiMappingService(get_platform_store())


@router.post("/analyses/{project_id}/api-mappings", response_model=MappingSetSummary)
def create_api_mappings(
    project_id: str, payload: ApiMappingCreateRequest | None = None
) -> MappingSetSummary:
    try:
        return _service().create_for_project(project_id, payload or ApiMappingCreateRequest())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/analyses/{project_id}/api-mappings", response_model=list[MappingSetSummary])
def list_api_mappings(project_id: str) -> list[MappingSetSummary]:
    try:
        return _service().list_for_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api-mappings/sets/{mapping_set_id}", response_model=MappingSetSummary)
def get_mapping_set(mapping_set_id: str) -> MappingSetSummary:
    item = _service().get_set(mapping_set_id)
    if not item:
        raise HTTPException(status_code=404, detail="mapping set not found")
    return item


@router.patch("/api-mappings/{mapping_id}")
def patch_api_mapping(mapping_id: str, payload: ApiMappingPatchRequest) -> dict:
    try:
        return _service().patch_mapping(mapping_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
