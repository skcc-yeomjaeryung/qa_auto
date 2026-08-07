from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.schemas.plan import RunExecuteRequest, RunExecuteResponse

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("/execute", response_model=RunExecuteResponse)
def execute_run(payload: RunExecuteRequest) -> RunExecuteResponse:
    try:
        return PlatformRunnerAdapter().execute(payload.workflowId, payload.inputs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
