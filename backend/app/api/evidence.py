from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import get_platform_store
from app.schemas.evidence import (
    EvidenceFinalizeRequest,
    EvidenceIntegrityReport,
    EvidenceManifest,
)
from app.services.evidence_package import EvidencePackageService

router = APIRouter(prefix="/api", tags=["evidence-package"])


def _service() -> EvidencePackageService:
    return EvidencePackageService(get_platform_store())


def _require_owner_for_run(run_id: str, user_id: str | None) -> str:
    store = get_platform_store()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    project = store.get_project(run.projectId) if run.projectId else None
    owner = project.ownerUserId if project else str((run.result or {}).get("ownerUserId") or "TEST")
    if not user_id or user_id.strip() != owner:
        raise HTTPException(status_code=403, detail="evidence access denied")
    return owner


def _require_owner_for_evidence(evidence_id: str, user_id: str | None) -> EvidenceManifest:
    manifest = _service().get_manifest(evidence_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="evidence not found")
    if not user_id or user_id.strip() != manifest.ownerUserId:
        raise HTTPException(status_code=403, detail="evidence access denied")
    return manifest


@router.post(
    "/runs/{run_id}/evidence/finalize",
    response_model=EvidenceManifest,
)
def finalize_evidence(
    run_id: str,
    payload: EvidenceFinalizeRequest | None = None,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> EvidenceManifest:
    _require_owner_for_run(run_id, x_user_id)
    return _service().finalize(
        run_id,
        retention_days=(payload.retentionDays if payload else None),
    )


@router.get(
    "/evidence/{evidence_id}/manifest",
    response_model=EvidenceManifest,
)
def get_evidence_manifest(
    evidence_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> EvidenceManifest:
    return _require_owner_for_evidence(evidence_id, x_user_id)


@router.get(
    "/evidence/{evidence_id}/integrity",
    response_model=EvidenceIntegrityReport,
)
def verify_evidence_integrity(
    evidence_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> EvidenceIntegrityReport:
    _require_owner_for_evidence(evidence_id, x_user_id)
    try:
        return _service().verify(evidence_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/evidence/{evidence_id}/download")
def download_evidence(
    evidence_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> StreamingResponse:
    _require_owner_for_evidence(evidence_id, x_user_id)
    try:
        payload = _service().zip_bytes(evidence_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{evidence_id}.zip"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get("/evidence/{evidence_id}/artifacts/{artifact_id}")
def get_evidence_artifact(
    evidence_id: str,
    artifact_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> FileResponse:
    manifest = _require_owner_for_evidence(evidence_id, x_user_id)
    artifact = next(
        (item for item in manifest.artifacts if item.artifactId == artifact_id),
        None,
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        path = _service().artifact_path(evidence_id, artifact_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type=artifact.mimeType, filename=path.name)
