from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.core.bootstrap import get_runtime
from app.core.models import ModelProfile, ModelProfileCreate, ModelProfileUpdate

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelProfile])
def list_models() -> list[ModelProfile]:
    return get_runtime().models.list()


@router.get("/policies")
def list_policies() -> list[dict[str, str]]:
    return [
        {"id": "auto", "name": "자동 추천", "description": "Core가 작업별 capability와 상태를 기준으로 모델을 선택합니다."},
        {"id": "cost_saver", "name": "비용 절약", "description": "비용 효율과 속도 점수가 높은 모델을 우선합니다."},
        {"id": "balanced", "name": "균형", "description": "품질·신뢰도·속도·비용을 균형 있게 평가합니다."},
        {"id": "highest_quality", "name": "최고 품질", "description": "복잡한 분석과 시나리오 생성에서 품질 점수를 최우선합니다."},
        {"id": "internal_only", "name": "내부망 전용", "description": "외부 배포 모델을 후보에서 강제로 제외합니다."},
    ]


@router.post("", response_model=ModelProfile, status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelProfileCreate) -> ModelProfile:
    try:
        return get_runtime().models.create(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/{model_profile_id}", response_model=ModelProfile)
def update_model(model_profile_id: str, payload: ModelProfileUpdate) -> ModelProfile:
    try:
        item = get_runtime().models.update(model_profile_id, payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="model profile not found")
    return item


@router.delete("/{model_profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_profile_id: str) -> Response:
    if not get_runtime().models.delete(model_profile_id):
        raise HTTPException(status_code=404, detail="model profile not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{model_profile_id}/health-check", response_model=ModelProfile)
def health_check_model(model_profile_id: str) -> ModelProfile:
    try:
        return get_runtime().models.health_check(model_profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="model profile not found") from exc
