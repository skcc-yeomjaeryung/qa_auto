from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.deps import get_platform_store
from app.services.dashboard_models import DashboardSummary
from app.services.dashboard_service import DashboardService
from app.services.repository_store import InMemoryPlatformStore


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    owner_user_id: str | None = Query(default=None, alias="ownerUserId"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> DashboardSummary:
    user_id = str(x_user_id or owner_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인 사용자 정보가 필요합니다")
    if owner_user_id and x_user_id and owner_user_id != x_user_id:
        raise HTTPException(status_code=403, detail="다른 사용자의 대시보드는 조회할 수 없습니다")
    return DashboardService(store).summary(user_id)

