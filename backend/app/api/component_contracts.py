from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_platform_store
from app.services.component_contract_models import (
    ComponentContractBuildRequest,
    ComponentContractSummary,
)
from app.services.component_contract_service import ComponentContractService

router = APIRouter(prefix="/api", tags=["component-contracts"])


def _service() -> ComponentContractService:
    return ComponentContractService(get_platform_store())


@router.post(
    "/scenarios/{scenario_id}/component-contract",
    response_model=ComponentContractSummary,
)
def build_component_contract(
    scenario_id: str, payload: ComponentContractBuildRequest | None = None
) -> ComponentContractSummary:
    try:
        return _service().build_for_scenario(scenario_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/scenarios/{scenario_id}/component-contract",
    response_model=ComponentContractSummary,
)
def get_component_contract(scenario_id: str) -> ComponentContractSummary:
    item = _service().get_for_scenario(scenario_id)
    if not item:
        raise HTTPException(status_code=404, detail="component contract not found")
    return item


@router.get("/component-contracts/{contract_id}", response_model=ComponentContractSummary)
def get_contract_by_id(contract_id: str) -> ComponentContractSummary:
    item = get_platform_store().get_contract(contract_id)
    if not item:
        raise HTTPException(status_code=404, detail="component contract not found")
    return item
