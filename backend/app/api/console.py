"""Console UX API — connect, bulk analyze, resource tree, bulk run, flow I/O."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.deps import get_platform_store
from app.services.console_models import (
    BulkAnalyzeRequest,
    BulkAnalyzeResult,
    BulkRunRequest,
    BulkRunResult,
    ConnectPairRequest,
    ConnectResult,
    FlowNodePatch,
    FlowNodeRetryRequest,
    FlowNodeRuntime,
    ResourceSelectionState,
    ResourceSelectionUpdate,
    ResourceTreeResponse,
    ScenarioGenerateRequest,
)
from app.services.console_service import ConsoleService
from app.services.run_service import BrowserRunService
from app.services.scenario_models import PipelineResult

router = APIRouter(prefix="/api/console", tags=["console"])


def _svc() -> ConsoleService:
    return ConsoleService(get_platform_store())


@router.post("/connect", response_model=ConnectResult)
def connect_repositories(payload: ConnectPairRequest) -> ConnectResult:
    try:
        return _svc().connect_pair(payload)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bulk-analyze", response_model=BulkAnalyzeResult)
def bulk_analyze(payload: BulkAnalyzeRequest) -> BulkAnalyzeResult:
    try:
        return _svc().bulk_analyze(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analyses")
def list_analysis_catalog(projectId: str | None = None) -> list[dict]:
    return _svc().list_analysis_catalog(projectId)


@router.get("/scenario-sets")
def list_scenario_sets(projectId: str | None = None) -> list[dict]:
    """연결 저장소 기준 시나리오 생성 단위 목록 (테스트 시나리오 1단 화면)."""
    return _svc().list_scenario_sets(projectId)


@router.post("/scenario-sets/{set_id}/stop")
def stop_scenario_set(set_id: str) -> dict:
    """「테스트 종료」 — 해당 묶음에서 진행 중인 실행만 취소한다."""
    try:
        return _svc().stop_scenario_set(set_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: str) -> dict:
    store = get_platform_store()
    if not store.delete_analysis(analysis_id):
        raise HTTPException(status_code=404, detail="analysis not found")
    return {"status": "deleted", "analysisId": analysis_id, "message": "분석 결과가 삭제되었습니다."}


@router.post("/analyses/bulk-delete")
def bulk_delete_analyses(payload: dict) -> dict:
    ids = list(payload.get("analysisIds") or [])
    try:
        return _svc().delete_analyses(ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/tree", response_model=ResourceTreeResponse)
def get_resource_tree(
    analysis_id: str,
    expandPath: str | None = Query(default=None),
    maxDepth: int = Query(default=3, ge=1, le=8),
) -> ResourceTreeResponse:
    try:
        return _svc().resource_tree(analysis_id, expand_path=expandPath, max_depth=maxDepth)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/file")
def get_analysis_file(
    analysis_id: str,
    path: str = Query(..., min_length=1),
) -> dict:
    try:
        return _svc().read_workspace_file(analysis_id, path)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/resource-selection", response_model=ResourceSelectionState)
def put_resource_selection(payload: ResourceSelectionUpdate) -> ResourceSelectionState:
    try:
        return _svc().update_resource_selection(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/generate-scenarios", response_model=PipelineResult)
def generate_scenarios(payload: ScenarioGenerateRequest) -> PipelineResult:
    try:
        return _svc().generate_scenarios(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bulk-runs", response_model=BulkRunResult)
def bulk_runs(payload: BulkRunRequest) -> BulkRunResult:
    try:
        return _svc().bulk_run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bulk-runs/events")
async def bulk_run_events(runIds: str = Query(min_length=1)) -> StreamingResponse:
    run_ids = [value.strip() for value in runIds.split(",") if value.strip()]
    if not run_ids:
        raise HTTPException(status_code=400, detail="runIds required")

    async def stream():
        terminal = {"WAITING_FOR_REVIEW", "AUTO_FAILED", "CANCELLED"}
        while True:
            store = get_platform_store()
            run_service = BrowserRunService(store)
            rows = [run for run_id in run_ids if (run := run_service.get_run(run_id)) is not None]
            completed = sum(1 for run in rows if str(run.status).upper() in terminal)
            success = sum(
                1
                for run in rows
                if str(run.status).upper() in terminal
                and str(run.status).upper() == "WAITING_FOR_REVIEW"
                and str(run.outcomeKind or "").lower() == "success"
            )
            failed = sum(
                1
                for run in rows
                if str(run.status).upper() in terminal
                and (
                    str(run.status).upper() == "AUTO_FAILED"
                    or str(run.outcomeKind or "").lower()
                    in {"be_error", "business_error", "fe_error", "failure"}
                )
            )
            cancelled = sum(1 for run in rows if str(run.status).upper() == "CANCELLED")
            body = {
                "total": len(run_ids),
                "created": len(rows),
                "completed": completed,
                "running": sum(1 for run in rows if str(run.status).upper() not in terminal),
                "success": success,
                "failed": failed,
                "cancelled": cancelled,
                "percent": round(completed / len(run_ids) * 100),
                "runs": [
                    {
                        "runId": run.runId,
                        "scenarioId": run.scenarioId,
                        "status": run.status,
                        "outcomeKind": run.outcomeKind,
                        "progressPercent": run.progressPercent,
                        "currentStepId": run.currentStepId,
                    }
                    for run in rows
                ],
            }
            data = json.dumps(body, ensure_ascii=False)
            yield f"event: progress\ndata: {data}\n\n"
            if completed >= len(run_ids):
                yield f"event: complete\ndata: {data}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/flows/{graph_id}/nodes", response_model=list[FlowNodeRuntime])
def list_flow_nodes(graph_id: str) -> list[FlowNodeRuntime]:
    return _svc().list_flow_runtime(graph_id)


@router.patch("/flows/{graph_id}/nodes/{node_id}", response_model=FlowNodeRuntime)
def patch_flow_node(graph_id: str, node_id: str, payload: FlowNodePatch) -> FlowNodeRuntime:
    return _svc().patch_flow_node(graph_id, node_id, payload)


@router.post("/flows/{graph_id}/nodes/{node_id}/retry", response_model=FlowNodeRuntime)
def retry_flow_node(
    graph_id: str, node_id: str, payload: FlowNodeRetryRequest
) -> FlowNodeRuntime:
    return _svc().retry_flow_node(graph_id, node_id, payload)
