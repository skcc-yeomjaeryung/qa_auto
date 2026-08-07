from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_platform_store
from app.schemas.telemetry import (
    BackendTelemetryEvent,
    BackendTelemetryIngestRequest,
    BackendTelemetryIngestResponse,
    RunTimelineResponse,
)
from app.services.telemetry.service import TelemetryService

router = APIRouter(prefix="/api", tags=["telemetry"])


def _service() -> TelemetryService:
    return TelemetryService(get_platform_store())


@router.post("/test-telemetry/backend", response_model=BackendTelemetryIngestResponse)
def ingest_backend_telemetry(payload: BackendTelemetryIngestRequest) -> BackendTelemetryIngestResponse:
    if not payload.events:
        raise HTTPException(status_code=400, detail="events required")
    return _service().ingest(payload)


@router.get("/runs/{run_id}/backend-events", response_model=list[BackendTelemetryEvent])
def get_backend_events(run_id: str) -> list[BackendTelemetryEvent]:
    store = get_platform_store()
    if not store.get_run(run_id) and not store.list_backend_events(run_id):
        # allow orphan ingest for late-arriving logs if events exist; else 404 when neither
        raise HTTPException(status_code=404, detail="run not found")
    return _service().list_backend_events(run_id)


@router.get("/runs/{run_id}/timeline", response_model=RunTimelineResponse)
def get_run_timeline(run_id: str) -> RunTimelineResponse:
    try:
        return _service().build_timeline(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/backend-trace/external", response_model=dict)
def mark_external_network_only(run_id: str) -> dict:
    """Mark run as external BE (no instrumentation) — browser network evidence only."""
    updated = _service().mark_external_network_only(run_id)
    if not updated:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "runId": updated.runId,
        "backendTraceStatus": updated.backendTraceStatus,
        "constraint": updated.backendTraceConstraint,
        "partialEvidence": updated.partialEvidence,
    }
