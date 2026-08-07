from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_platform_store, get_sync_service
from app.services.console_models import ProjectUpdate, RepositoryUpdate
from app.services.repository_models import (
    Project,
    ProjectCreate,
    RepositoryRegister,
    RepositorySet,
)
from app.services.repository_store import InMemoryPlatformStore
from app.services.repository_sync import RepositorySyncService

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[Project])
def list_projects(
    ownerUserId: str | None = Query(default=None),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[Project]:
    return list(store.list_projects(owner_user_id=ownerUserId))


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> Project:
    return store.create_project(payload)


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> Project:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> Project:
    project = store.update_project(
        project_id,
        name=payload.name,
        description=payload.description,
        ai_policy=payload.aiPolicy,
        model_selection_mode=payload.modelSelectionMode,
        model_bindings=payload.modelBindings,
    )
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> None:
    if not store.delete_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")


@router.get("/{project_id}/repository-sets", response_model=list[RepositorySet])
def list_repository_sets(
    project_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[RepositorySet]:
    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    return store.list_sets_for_project(project_id)


@router.get("/{project_id}/repository-sets/{set_id}", response_model=RepositorySet)
def get_repository_set(
    project_id: str,
    set_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> RepositorySet:
    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    repo_set = store.get_set(set_id)
    if not repo_set or repo_set.projectId != project_id:
        raise HTTPException(status_code=404, detail="repository set not found")
    return repo_set


@router.delete("/{project_id}/repository-sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository_set(
    project_id: str,
    set_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> None:
    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail="project not found")
    repo_set = store.get_set(set_id)
    if not repo_set or repo_set.projectId != project_id:
        raise HTTPException(status_code=404, detail="repository set not found")
    store.delete_repository_set(set_id)


@router.post(
    "/{project_id}/repositories",
    response_model=RepositorySet,
    status_code=status.HTTP_201_CREATED,
)
def register_repository(
    project_id: str,
    payload: RepositoryRegister,
    sync: RepositorySyncService = Depends(get_sync_service),
) -> RepositorySet:
    try:
        return sync.register(project_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{project_id}/repositories/{repository_id}", response_model=RepositorySet)
def update_repository(
    project_id: str,
    repository_id: str,
    payload: RepositoryUpdate,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> RepositorySet:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    # find set containing repository
    for repo_set in store.list_sets_for_project(project_id):
        if any(r.id == repository_id for r in repo_set.repositories):
            updated = store.update_repository(
                repo_set.id,
                repository_id,
                url=payload.url,
                path=payload.path,
                subdir=payload.subdir,
                branch=payload.branch,
                token=payload.token,
            )
            if not updated:
                raise HTTPException(status_code=404, detail="repository not found")
            return updated
    raise HTTPException(status_code=404, detail="repository not found")


@router.delete("/{project_id}/repositories/{repository_id}", response_model=RepositorySet)
def delete_repository(
    project_id: str,
    repository_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> RepositorySet:
    for repo_set in store.list_sets_for_project(project_id):
        if any(r.id == repository_id for r in repo_set.repositories):
            updated = store.delete_repository(repo_set.id, repository_id)
            if not updated:
                raise HTTPException(status_code=404, detail="repository not found")
            return updated
    raise HTTPException(status_code=404, detail="repository not found")


@router.get("/{project_id}/repository-set", response_model=RepositorySet)
def get_project_repository_set(
    project_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> RepositorySet:
    repo_set = store.get_set_for_project(project_id)
    if not repo_set:
        raise HTTPException(status_code=404, detail="repository set not found")
    return repo_set
