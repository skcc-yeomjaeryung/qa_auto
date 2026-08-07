from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_platform_store
from app.services.batch_models import BatchCreateRequest, BatchDefinition, BatchSummary
from app.services.batch_service import BatchService
from app.services.repository_store import InMemoryPlatformStore


router = APIRouter(prefix="/api/batches", tags=["batches"])


def _user(x_user_id: str | None) -> str:
    user = str(x_user_id or "").strip()
    if not user:
        raise HTTPException(status_code=401, detail="로그인 사용자 정보가 필요합니다")
    return user


def _service(store: InMemoryPlatformStore) -> BatchService:
    return BatchService(store)


def _translate(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[BatchDefinition])
def list_batches(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[BatchDefinition]:
    return _service(store).list(_user(x_user_id))


@router.post("", response_model=BatchDefinition, status_code=201)
def create_batch(
    payload: BatchCreateRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> BatchDefinition:
    try:
        return _service(store).create(payload, _user(x_user_id))
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


@router.get("/{batch_id}", response_model=BatchDefinition)
def get_batch(
    batch_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> BatchDefinition:
    try:
        return _service(store).get(batch_id, _user(x_user_id))
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


@router.get("/{batch_id}/summary", response_model=BatchSummary)
def get_batch_summary(
    batch_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> BatchSummary:
    try:
        return _service(store).summary(batch_id, _user(x_user_id))
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


def _transition(
    action: str,
    batch_id: str,
    user: str,
    store: InMemoryPlatformStore,
) -> BatchDefinition:
    service = _service(store)
    try:
        return getattr(service, action)(batch_id, user)
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


@router.post("/{batch_id}/start", response_model=BatchDefinition)
def start_batch(
    batch_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> BatchDefinition:
    return _transition("start", batch_id, _user(x_user_id), store)


@router.post("/{batch_id}/pause", response_model=BatchDefinition)
def pause_batch(
    batch_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> BatchDefinition:
    return _transition("pause", batch_id, _user(x_user_id), store)


@router.post("/{batch_id}/resume", response_model=BatchDefinition)
def resume_batch(
    batch_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> BatchDefinition:
    return _transition("resume", batch_id, _user(x_user_id), store)


@router.post("/{batch_id}/cancel", response_model=BatchDefinition)
def cancel_batch(
    batch_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> BatchDefinition:
    return _transition("cancel", batch_id, _user(x_user_id), store)
