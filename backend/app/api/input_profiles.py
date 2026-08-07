from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_platform_store
from app.services.input_recommend_models import (
    GenerateCasesRequest,
    InputProfileApproveRequest,
    InputProfileCreateRequest,
    InputProfileSummary,
    RecommendInputsRequest,
    RecommendationSummary,
)
from app.services.input_recommend_service import InputRecommendService

router = APIRouter(prefix="/api", tags=["input-profiles"])


def _service() -> InputRecommendService:
    return InputRecommendService(get_platform_store())


@router.post(
    "/scenarios/{scenario_id}/recommend-inputs",
    response_model=RecommendationSummary,
)
def recommend_inputs(
    scenario_id: str, payload: RecommendInputsRequest | None = None
) -> RecommendationSummary:
    try:
        return _service().recommend(scenario_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/scenarios/{scenario_id}/recommend-inputs",
    response_model=RecommendationSummary,
)
def get_recommend_inputs(scenario_id: str) -> RecommendationSummary:
    item = _service().get_recommendation(scenario_id)
    if not item:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return item


@router.get(
    "/scenarios/{scenario_id}/input-profiles",
    response_model=list[InputProfileSummary],
)
def list_input_profiles(scenario_id: str) -> list[InputProfileSummary]:
    return _service().list_profiles(scenario_id)


@router.post(
    "/scenarios/{scenario_id}/input-profiles",
    response_model=InputProfileSummary,
)
def create_input_profile(
    scenario_id: str, payload: InputProfileCreateRequest | None = None
) -> InputProfileSummary:
    try:
        return _service().create_profile(scenario_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/input-profiles/{profile_id}/approve",
    response_model=InputProfileSummary,
)
def approve_input_profile(
    profile_id: str, payload: InputProfileApproveRequest | None = None
) -> InputProfileSummary:
    try:
        return _service().approve_profile(profile_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/input-profiles/{profile_id}/generate-cases",
    response_model=InputProfileSummary,
)
def generate_profile_cases(
    profile_id: str, payload: GenerateCasesRequest | None = None
) -> InputProfileSummary:
    try:
        return _service().generate_cases(profile_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
