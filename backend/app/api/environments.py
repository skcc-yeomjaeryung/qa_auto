"""Execution environment CRUD + health-check APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.api.deps import get_platform_store
from app.services.environment_models import (
    EnvironmentPreset,
    ExecutionAccount,
    ExecutionAccountCreate,
    ExecutionEnvironment,
    ExecutionEnvironmentCreate,
    ExecutionEnvironmentUpdate,
    HealthCheckResult,
)
from app.services.environment_service import EnvironmentService, list_presets
from app.services.repository_store import InMemoryPlatformStore

router = APIRouter(tags=["environments"])


def _env_service(store: InMemoryPlatformStore = Depends(get_platform_store)) -> EnvironmentService:
    return EnvironmentService(store)


@router.get("/api/environment-presets", response_model=list[EnvironmentPreset])
def get_environment_presets() -> list[EnvironmentPreset]:
    return list_presets()


@router.get(
    "/api/projects/{project_id}/environments",
    response_model=list[ExecutionEnvironment],
)
def list_project_environments(
    project_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[ExecutionEnvironment]:
    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    return store.list_environments(project_id)


@router.post(
    "/api/projects/{project_id}/environments",
    response_model=ExecutionEnvironment,
    status_code=status.HTTP_201_CREATED,
)
def create_project_environment(
    project_id: str,
    payload: ExecutionEnvironmentCreate,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ExecutionEnvironment:
    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    try:
        return store.create_environment(project_id, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/environments/{environment_id}", response_model=ExecutionEnvironment)
def get_environment(
    environment_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ExecutionEnvironment:
    env = store.get_environment(environment_id)
    if not env:
        raise HTTPException(status_code=404, detail="environment not found")
    return env


@router.patch("/api/environments/{environment_id}", response_model=ExecutionEnvironment)
def update_environment(
    environment_id: str,
    payload: ExecutionEnvironmentUpdate,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ExecutionEnvironment:
    try:
        env = store.update_environment(environment_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not env:
        raise HTTPException(status_code=404, detail="environment not found")
    return env


@router.delete(
    "/api/environments/{environment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_environment(
    environment_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> None:
    if not store.delete_environment(environment_id):
        raise HTTPException(status_code=404, detail="environment not found")


@router.post(
    "/api/environments/{environment_id}/health-check",
    response_model=HealthCheckResult,
)
def health_check_environment(
    environment_id: str,
    service: EnvironmentService = Depends(_env_service),
) -> HealthCheckResult:
    try:
        return service.health_check(environment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/environments/{environment_id}/accounts", response_model=list[ExecutionAccount])
def list_environment_accounts(
    environment_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[ExecutionAccount]:
    if not store.get_environment(environment_id):
        raise HTTPException(status_code=404, detail="environment not found")
    return store.list_execution_accounts(environment_id)


@router.post(
    "/api/environments/{environment_id}/accounts",
    response_model=ExecutionAccount,
    status_code=status.HTTP_201_CREATED,
)
def create_environment_account(
    environment_id: str,
    payload: ExecutionAccountCreate,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ExecutionAccount:
    try:
        return store.create_execution_account(environment_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
