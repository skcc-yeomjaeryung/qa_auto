from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_platform_store
from app.schemas.binding_validation import (
    BindingAssertion,
    BindingValidateRequest,
    BindingValidationResult,
)
from app.services.binding_validation import BindingValidationService

router = APIRouter(prefix="/api", tags=["binding-validation"])


def _service() -> BindingValidationService:
    return BindingValidationService(get_platform_store())


@router.post(
    "/runs/{run_id}/validate-bindings",
    response_model=BindingValidationResult,
)
def validate_bindings(
    run_id: str,
    payload: BindingValidateRequest | None = None,
) -> BindingValidationResult:
    try:
        return _service().validate(run_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/runs/{run_id}/assertions",
    response_model=list[BindingAssertion],
)
def get_binding_assertions(run_id: str) -> list[BindingAssertion]:
    result = _service().get(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="binding validation not found")
    return result.assertions


@router.get(
    "/runs/{run_id}/binding-validation",
    response_model=BindingValidationResult,
)
def get_binding_validation(run_id: str) -> BindingValidationResult:
    result = _service().get(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="binding validation not found")
    return result
