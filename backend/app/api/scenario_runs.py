from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import get_platform_store
from app.core.paths import ARTIFACTS_EVIDENCE, REPO_ROOT
from app.schemas.interactive_run import RunPreview, RunPreviewRequest
from app.services.run_models import RunCreateRequest, RunStepSummary, RunSummary
from app.services.run_preview_service import RunPreviewService
from app.services.run_service import BrowserRunService, StaleVersionError

router = APIRouter(prefix="/api", tags=["scenario-runs"])


def _service() -> BrowserRunService:
    return BrowserRunService(get_platform_store())


def _require_run_owner(run_id: str, user_id: str | None):
    store = get_platform_store()
    item = store.get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    project = store.get_project(item.projectId) if item.projectId else None
    owner = project.ownerUserId if project else str((item.result or {}).get("ownerUserId") or "TEST")
    if not user_id or user_id.strip() != owner:
        raise HTTPException(status_code=403, detail="evidence access denied")
    return item


def _evidence_preview(item, screenshots: list[dict], snapshots: list[dict], package) -> dict:
    store = get_platform_store()
    scenario = store.get_scenario(item.scenarioId)
    body = dict(scenario.result or {}) if scenario else {}
    source = body.get("source") if isinstance(body.get("source"), dict) else {}
    destination = body.get("destination") if isinstance(body.get("destination"), dict) else {}
    request = body.get("request") if isinstance(body.get("request"), dict) else {}
    steps = list(item.steps or [])
    source_steps = [step for step in steps if step.action in {"navigate", "fill", "select"}]
    expects_backend = any(
        str(step.get("action") or "") in {"wait_for_response", "verify_response"}
        for step in (body.get("steps") or [])
        if isinstance(step, dict)
    )
    network = [
        row
        for row in ((item.result or {}).get("matchedNetworkRequests") or [])
        if isinstance(row, dict) and row.get("expectedRequest")
    ]
    backend_events = list(store.list_backend_events(item.runId))
    result_steps = [
        step
        for step in steps
        if step.action.startswith("assert_") or step.action.startswith("verify_")
    ]

    def observed(rows) -> bool:
        return any(str(step.status).lower() in {"ok", "success", "complete", "completed"} for step in rows)

    backend_trace = str(item.backendTraceStatus or "pending")
    source_status = "observed" if observed(source_steps) else "missing"
    if not expects_backend:
        backend_status = "not_applicable"
    elif network or backend_events:
        backend_status = "observed"
    elif backend_trace not in {"", "pending", "missing_data"}:
        backend_status = "partial"
    else:
        backend_status = "missing"
    destination_status = "observed" if observed(result_steps) else "missing"
    missing: list[str] = []
    if source_status == "missing":
        missing.append("A 화면 입력·진입 관측")
    if backend_status in {"missing", "partial"}:
        missing.append("Backend 요청·응답 추적")
    if destination_status == "missing":
        missing.append("B 화면 결과·판정 기준 관측")
    if not screenshots:
        missing.append("화면 스크린샷")
    if package:
        missing.extend(str(value) for value in (package.missingData or []))
    complete_connection = (
        source_status == "observed"
        and destination_status == "observed"
        and backend_status in {"observed", "not_applicable"}
    )
    return {
        "connectionStatus": "complete" if complete_connection else "partial",
        "stages": [
            {
                "id": "source",
                "title": "A 화면 · 입력",
                "status": source_status,
                "summary": str(source.get("route") or source.get("screen") or "화면 경로 missing_data"),
                "evidenceCount": len(source_steps),
            },
            {
                "id": "backend",
                "title": "Backend 요청 · 응답",
                "status": backend_status,
                "summary": (
                    "요청 전 화면 입력 제약 검증 — Backend 호출 대상 아님"
                    if not expects_backend
                    else f"{request.get('method') or 'method missing_data'} {request.get('path') or 'path missing_data'} · trace {backend_trace}"
                ),
                "evidenceCount": len(network) + len(backend_events),
            },
            {
                "id": "destination",
                "title": "B 화면 · 결과",
                "status": destination_status,
                "summary": str(destination.get("routePattern") or destination.get("screen") or "결과 화면 missing_data"),
                "evidenceCount": len(result_steps),
            },
        ],
        "rawEvidence": {
            "files": len(screenshots) + len(snapshots),
            "screenshots": len(screenshots),
            "snapshots": len(snapshots),
        },
        "integrity": {
            "status": package.integrityStatus if package else "not_finalized",
            "message": (
                "해시 검증된 패키지"
                if package
                else "패키지 생성 시 파일별 SHA-256과 누락 상태를 확정합니다"
            ),
        },
        "masking": {
            "status": "applied" if package else "pending_package",
            "message": (
                "패키지 artifact 마스킹 적용"
                if package
                else "패키지 생성 시 계정·토큰·민감 입력을 마스킹합니다"
            ),
        },
        "missingData": list(dict.fromkeys(missing)),
    }


@router.post("/scenarios/{scenario_id}/run-preview", response_model=RunPreview)
def preview_scenario_run(
    scenario_id: str, payload: RunPreviewRequest | None = None
) -> RunPreview:
    """건별 실행 전 확인 요약 (A 화면 · 추천 입력 · 예상 API · B 화면 · destructive)."""
    try:
        return RunPreviewService(get_platform_store()).build(scenario_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scenarios/{scenario_id}/runs", response_model=RunSummary)
def start_scenario_run(
    scenario_id: str, payload: RunCreateRequest | None = None
) -> RunSummary:
    try:
        return _service().start_run(scenario_id, payload)
    except StaleVersionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "currentVersion": exc.expected,
                "requestedVersion": exc.actual,
            },
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/retest", response_model=RunSummary)
def retest_run(run_id: str, payload: RunCreateRequest | None = None) -> RunSummary:
    """이전 실행 입력을 선택적으로 재사용해 같은 시나리오를 다시 실행한다."""
    store = get_platform_store()
    previous = store.get_run(run_id)
    if not previous:
        raise HTTPException(status_code=404, detail="run not found")
    body = (payload or RunCreateRequest()).model_copy(
        update={
            "mode": (payload.mode if payload else None) or "interactive",
            "reuseFromRunId": run_id if (payload is None or payload.reuseFromRunId is None) else payload.reuseFromRunId,
            "environmentId": (payload.environmentId if payload else None) or previous.environmentId,
        }
    )
    try:
        return _service().start_run(previous.scenarioId, body)
    except StaleVersionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "currentVersion": exc.expected,
                "requestedVersion": exc.actual,
            },
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scenarios/{scenario_id}/runs", response_model=list[RunSummary])
def list_scenario_runs(scenario_id: str) -> list[RunSummary]:
    return _service().list_runs(scenario_id=scenario_id)


@router.get("/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: str) -> RunSummary:
    item = _service().get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    return item


@router.get("/runs/{run_id}/steps", response_model=list[RunStepSummary])
def get_run_steps(run_id: str) -> list[RunStepSummary]:
    try:
        return _service().list_steps(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel", response_model=RunSummary)
def cancel_run(run_id: str) -> RunSummary:
    try:
        return _service().cancel_run(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs", response_model=list[RunSummary])
def list_all_runs() -> list[RunSummary]:
    return _service().list_runs()


@router.post("/runs/bulk-delete")
def bulk_delete_runs(payload: dict) -> dict:
    """실행 이력 목록 일괄 삭제 (증적 파일은 보존)."""
    ids = [str(x) for x in (payload.get("runIds") or []) if x]
    try:
        return _service().delete_many(ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}/evidence")
def list_run_evidence(run_id: str) -> dict:
    """List screenshot/snapshot evidence paths for a run (trust materials; no Pass/Fail)."""
    item = _service().get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    evidence_dir = Path(item.evidenceDir) if item.evidenceDir else ARTIFACTS_EVIDENCE / "runs" / run_id
    screenshots: list[dict] = []
    snapshots: list[dict] = []
    if evidence_dir.is_dir():
        for path in sorted(evidence_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(evidence_dir))
            entry = {
                "name": path.name,
                "relativePath": rel,
                "url": f"/api/runs/{run_id}/evidence/file?path={rel}",
            }
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                screenshots.append(entry)
            elif path.suffix.lower() in {".txt", ".json", ".html"}:
                snapshots.append(entry)
    for step in item.steps or []:
        if step.screenshotPath:
            p = Path(step.screenshotPath)
            if p.is_file() and not any(s["name"] == p.name for s in screenshots):
                screenshots.append(
                    {
                        "name": p.name,
                        "relativePath": p.name,
                        "url": f"/api/runs/{run_id}/evidence/file?path={p.name}",
                        "stepId": step.stepId,
                    }
                )
    package = get_platform_store().get_evidence_manifest_by_run(run_id)
    return {
        "runId": run_id,
        "scenarioId": item.scenarioId,
        "evidenceDir": str(evidence_dir) if evidence_dir else None,
        "package": package.model_dump(mode="json") if package else None,
        "packagePreview": _evidence_preview(item, screenshots, snapshots, package),
        "screenshots": screenshots,
        "snapshots": snapshots,
        "missing_data": []
        if screenshots
        else ["screenshots — 실행 후 증적이 생성됩니다"],
    }


@router.get("/runs/{run_id}/evidence/download")
def download_run_evidence(
    run_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> StreamingResponse:
    """Download the currently collected raw run evidence before package finalization."""
    item = _require_run_owner(run_id, x_user_id)
    evidence_dir = Path(item.evidenceDir) if item.evidenceDir else ARTIFACTS_EVIDENCE / "runs" / run_id
    if not evidence_dir.is_dir():
        raise HTTPException(status_code=404, detail="evidence dir missing")
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(evidence_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=str(path.relative_to(evidence_dir)))
    payload = output.getvalue()
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{run_id}-evidence.zip"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get("/runs/{run_id}/evidence/file")
def get_run_evidence_file(run_id: str, path: str) -> FileResponse:
    """Serve a single evidence file under the run evidence directory (path jail)."""
    item = _service().get_run(run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    evidence_dir = Path(item.evidenceDir) if item.evidenceDir else ARTIFACTS_EVIDENCE / "runs" / run_id
    if not evidence_dir.is_dir():
        raise HTTPException(status_code=404, detail="evidence dir missing")
    # Prevent path traversal
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(status_code=400, detail="invalid path")
    target = (evidence_dir / rel).resolve()
    try:
        target.relative_to(evidence_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path outside evidence dir") from exc
    if not target.is_file():
        # Also allow absolute screenshotPath under repo artifacts
        alt = Path(path)
        if alt.is_file() and str(alt.resolve()).startswith(str(REPO_ROOT.resolve())):
            target = alt.resolve()
        else:
            raise HTTPException(status_code=404, detail="file not found")
    media = "image/png" if target.suffix.lower() == ".png" else "application/octet-stream"
    return FileResponse(target, media_type=media, filename=target.name)
