from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_ANALYSIS
from app.services.analysis_progress import count_analysis_files, execute_with_file_progress
from app.services.analysis_models import AnalysisSummary, BackendAnalysisRequest
from app.services.repository_models import RepoRole, utc_now
from app.services.repository_store import InMemoryPlatformStore

logger = logging.getLogger(__name__)


class BackendAnalysisService:
    """Resolve workspace metadata, then run Hub Workflow (no AST in services)."""

    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def run(self, payload: BackendAnalysisRequest) -> AnalysisSummary:
        project = self.store.get_project(payload.projectId)
        if not project:
            raise ValueError("project not found")

        set_id = payload.repositorySetId or project.repositorySetId
        repo_set = self.store.get_set(set_id) if set_id else None
        be = None
        if repo_set:
            be = next((r for r in repo_set.repositories if r.role == RepoRole.backend), None)
            if be is None:
                be = next((r for r in repo_set.repositories if r.role == RepoRole.workspace), None)

        workspace = (
            payload.workspacePath
            or (be.workspacePath if be else None)
            or (be.path if be else None)
        )
        commit = payload.commitSha or (be.commitSha if be else None)
        if not workspace:
            raise ValueError(
                "backend workspacePath missing — sync repository (Git URL or absolute path) first"
            )

        workspace_path = Path(workspace).expanduser().resolve()
        if not workspace_path.is_dir():
            raise ValueError(f"workspace not found: {workspace_path}")

        if not payload.force:
            reused = self.store.find_reusable_analysis(
                project_id=payload.projectId,
                role="backend",
                repository_set_id=set_id,
                commit_sha=commit,
                workspace_path=str(workspace_path),
            )
            if reused and reused.result:
                logger.info(
                    "backend analysis reused id=%s commit=%s",
                    reused.id,
                    (commit or "")[:12],
                )
                return reused

        analysis_id = f"AN-BE-{uuid4().hex[:12]}"
        out_file = ARTIFACTS_ANALYSIS / analysis_id / "backend.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        file_total = count_analysis_files(workspace_path, "backend")
        progress_file = out_file.parent / "progress.json"

        summary = AnalysisSummary(
            id=analysis_id,
            projectId=payload.projectId,
            repositorySetId=set_id,
            role="backend",
            commitSha=commit,
            workspacePath=str(workspace_path),
            status="progressing",
            fileTotal=file_total,
            fileCompleted=0,
            progressPercent=0,
            artifactPath=str(out_file),
            createdAt=utc_now().isoformat(),
        )
        self.store.save_analysis(summary)

        try:
            logger.info(
                "backend analysis start id=%s workspace=%s commit=%s via=wf_backend_spring_analyze",
                analysis_id,
                workspace_path,
                (commit or "")[:12],
            )
            def publish_file_progress(completed: int, failed: int) -> None:
                nonlocal summary
                processed = min(file_total, completed + failed)
                summary = summary.model_copy(
                    update={
                        "fileCompleted": completed,
                        "fileFailed": failed,
                        "progressPercent": round(processed / file_total * 100) if file_total else 0,
                    }
                )
                self.store.save_analysis(summary)

            response = execute_with_file_progress(
                progress_path=progress_file,
                file_total=file_total,
                on_progress=publish_file_progress,
                operation=lambda: PlatformRunnerAdapter().execute(
                    "wf_backend_spring_analyze",
                    {
                        "workspacePath": str(workspace_path),
                        "commitSha": commit,
                        "projectId": payload.projectId,
                        "analysisId": analysis_id,
                        "artifactPath": str(out_file.resolve()),
                        "progressPath": str(progress_file.resolve()),
                        "fileTotal": file_total,
                    },
                ),
            )
            if response.status != "complete" or not response.stepResults:
                err = response.summary or "workflow did not complete"
                summary = summary.model_copy(
                    update={"status": "error", "fileFailed": 1 if file_total else 0, "error": err[:2000]}
                )
                return self.store.save_analysis(summary)

            output = response.stepResults[0].get("output") or {}
            if not output.get("ok"):
                summary = summary.model_copy(
                    update={
                        "status": "error",
                        "fileFailed": 1 if file_total else 0,
                        "error": "skill output missing ok=true",
                    }
                )
                return self.store.save_analysis(summary)

            result = output.get("result") or {}
            counts = output.get("counts") or {}
            summary = summary.model_copy(
                update={
                    "status": "complete",
                    "result": result,
                    "endpointCount": int(
                        counts.get("endpoints") or len(result.get("endpoints", []))
                    ),
                    "componentCount": int(
                        counts.get("services") or len(result.get("services", []))
                    ),
                    "unresolvedCount": int(
                        counts.get("unresolved") or len(result.get("unresolved", []))
                    ),
                    "fileCompleted": file_total,
                    "fileFailed": 0,
                    "progressPercent": 100,
                    "commitSha": output.get("commitSha") or result.get("commitSha") or commit,
                    "artifactPath": output.get("artifactPath") or str(out_file),
                    "error": None,
                }
            )
            return self.store.save_analysis(summary)
        except Exception as exc:  # noqa: BLE001 — surface to API
            logger.exception("backend analysis failed id=%s", analysis_id)
            summary = summary.model_copy(
                update={
                    "status": "error",
                    "fileFailed": 1 if file_total else 0,
                    "progressPercent": round(summary.fileCompleted / file_total * 100) if file_total else 0,
                    "error": str(exc)[:2000],
                }
            )
            return self.store.save_analysis(summary)
