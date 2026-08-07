from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.deps import get_platform_store
from app.schemas.run_report import RunReport, RunReportGenerateRequest
from app.services.run_report_service import RunReportService


router = APIRouter(prefix="/api/runs", tags=["run-reports"])


def _service() -> RunReportService:
    return RunReportService(get_platform_store())


def _require_owner(run_id: str, user_id: str | None) -> None:
    store = get_platform_store()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    project = store.get_project(run.projectId) if run.projectId else None
    owner = project.ownerUserId if project else str((run.result or {}).get("ownerUserId") or "TEST")
    if not user_id or user_id.strip() != owner:
        raise HTTPException(status_code=403, detail="report access denied")


@router.post("/{run_id}/report", response_model=RunReport)
def generate_run_report(
    run_id: str,
    payload: RunReportGenerateRequest | None = None,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> RunReport:
    _require_owner(run_id, x_user_id)
    try:
        return _service().generate(run_id, force=bool(payload and payload.force))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{run_id}/report", response_model=RunReport)
def get_run_report(
    run_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> RunReport:
    _require_owner(run_id, x_user_id)
    try:
        report = _service().get(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(status_code=404, detail="report not generated")
    return report


@router.get("/{run_id}/report/download")
def download_run_report(
    run_id: str,
    format: Literal["html", "json"] = Query(default="html"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> FileResponse:
    _require_owner(run_id, x_user_id)
    try:
        target = _service().download_path(run_id, format)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    media_type = "text/html; charset=utf-8" if format == "html" else "application/json"
    return FileResponse(
        target,
        media_type=media_type,
        filename=f"{run_id}-review-report.{format}",
    )
