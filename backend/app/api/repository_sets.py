from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_platform_store, get_sync_service
from app.services.console_models import ResourceTreeResponse
from app.services.console_service import ConsoleService
from app.services.repository_models import FileInventoryItem, RepositorySet, SyncRequest
from app.services.repository_store import InMemoryPlatformStore
from app.services.repository_sync import RepositorySyncBusyError, RepositorySyncService

router = APIRouter(prefix="/api/repository-sets", tags=["repository-sets"])


@router.post("/{set_id}/sync", response_model=RepositorySet)
def sync_repository_set(
    set_id: str,
    payload: SyncRequest | None = None,
    sync: RepositorySyncService = Depends(get_sync_service),
) -> RepositorySet:
    force = bool(payload.force) if payload else False
    try:
        return sync.sync(set_id, force=force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RepositorySyncBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{set_id}/status", response_model=RepositorySet)
def get_status(
    set_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> RepositorySet:
    repo_set = store.get_set(set_id)
    if not repo_set:
        raise HTTPException(status_code=404, detail="repository set not found")
    return repo_set


@router.get("/{set_id}/files", response_model=list[FileInventoryItem])
def list_files(
    set_id: str,
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[FileInventoryItem]:
    if not store.get_set(set_id):
        raise HTTPException(status_code=404, detail="repository set not found")
    return [FileInventoryItem(**item) for item in store.get_files(set_id)]


@router.get("/{set_id}/tree", response_model=ResourceTreeResponse)
def get_repository_tree(
    set_id: str,
    expandPath: str | None = Query(default=None),
    maxDepth: int = Query(default=3, ge=1, le=8),
    repositoryId: str | None = Query(default=None),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ResourceTreeResponse:
    """File tree from synced workspace — no FE/BE subdir required."""
    try:
        return ConsoleService(store).repository_set_tree(
            set_id,
            expand_path=expandPath,
            max_depth=maxDepth,
            repository_id=repositoryId,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
