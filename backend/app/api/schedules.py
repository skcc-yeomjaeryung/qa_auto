from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_platform_store
from app.services.repository_store import InMemoryPlatformStore
from app.services.schedule_models import (
    CronPreviewRequest,
    CronPreviewResponse,
    ScheduleCreateRequest,
    ScheduleDefinition,
    ScheduleUpdateRequest,
)
from app.services.schedule_service import ScheduleService, natural_language_cron


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _user(x_user_id: str | None) -> str:
    user = str(x_user_id or "").strip()
    if not user:
        raise HTTPException(status_code=401, detail="로그인 사용자 정보가 필요합니다")
    return user


def _service(store: InMemoryPlatformStore) -> ScheduleService:
    return ScheduleService(store)


def _translate(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[ScheduleDefinition])
def list_schedules(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[ScheduleDefinition]:
    return _service(store).list(_user(x_user_id))


@router.post("", response_model=ScheduleDefinition, status_code=201)
def create_schedule(
    payload: ScheduleCreateRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ScheduleDefinition:
    try:
        return _service(store).create(payload, _user(x_user_id))
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


@router.patch("/{schedule_id}", response_model=ScheduleDefinition)
def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdateRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ScheduleDefinition:
    try:
        return _service(store).update(schedule_id, payload, _user(x_user_id))
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


@router.post("/{schedule_id}/execute", response_model=ScheduleDefinition)
def execute_schedule(
    schedule_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ScheduleDefinition:
    try:
        return _service(store).execute(schedule_id, _user(x_user_id), trigger="manual")
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


@router.post("/bulk-delete")
def delete_schedules(
    payload: dict,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> dict:
    try:
        count = _service(store).delete_many(
            [str(value) for value in payload.get("scheduleIds") or []],
            _user(x_user_id),
        )
        return {"status": "deleted", "deletedCount": count, "message": f"스케줄 {count}건을 삭제했습니다."}
    except Exception as exc:  # noqa: BLE001
        _translate(exc)
        raise


@router.post("/cron-preview", response_model=CronPreviewResponse)
def preview_cron(payload: CronPreviewRequest) -> CronPreviewResponse:
    try:
        return natural_language_cron(payload.naturalLanguage, payload.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
