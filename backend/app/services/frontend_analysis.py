from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_ANALYSIS
from app.services.analysis_progress import count_analysis_files, execute_with_file_progress
from app.services.analysis_models import AnalysisSummary, FrontendAnalysisRequest
from app.services.repository_models import RepoRole, utc_now
from app.services.repository_store import InMemoryPlatformStore

logger = logging.getLogger(__name__)


class FrontendAnalysisService:
    """Resolve workspace metadata, then run Hub Workflow (no AST in services)."""

    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def run(self, payload: FrontendAnalysisRequest) -> AnalysisSummary:
        project = self.store.get_project(payload.projectId)
        if not project:
            raise ValueError("project not found")

        set_id = payload.repositorySetId or project.repositorySetId
        repo_set = self.store.get_set(set_id) if set_id else None
        fe = None
        if repo_set:
            fe = next((r for r in repo_set.repositories if r.role == RepoRole.frontend), None)
            if fe is None:
                fe = next((r for r in repo_set.repositories if r.role == RepoRole.workspace), None)

        workspace = (
            payload.workspacePath
            or (fe.workspacePath if fe else None)
            or (fe.path if fe else None)
        )
        commit = payload.commitSha or (fe.commitSha if fe else None)
        if not workspace:
            raise ValueError(
                "frontend workspacePath missing — sync repository first or pass workspacePath"
            )

        workspace_path = Path(workspace).expanduser().resolve()
        if not workspace_path.is_dir():
            raise ValueError(f"workspace not found: {workspace_path}")

        if not payload.force:
            reused = self.store.find_reusable_analysis(
                project_id=payload.projectId,
                role="frontend",
                repository_set_id=set_id,
                commit_sha=commit,
                workspace_path=str(workspace_path),
            )
            if reused and reused.result:
                logger.info(
                    "frontend analysis reused id=%s commit=%s",
                    reused.id,
                    (commit or "")[:12],
                )
                return reused

        analysis_id = f"AN-FE-{uuid4().hex[:12]}"
        out_file = ARTIFACTS_ANALYSIS / analysis_id / "frontend.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        file_total = count_analysis_files(workspace_path, "frontend")
        progress_file = out_file.parent / "progress.json"

        summary = AnalysisSummary(
            id=analysis_id,
            projectId=payload.projectId,
            repositorySetId=set_id,
            role="frontend",
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
                "frontend analysis start id=%s workspace=%s commit=%s via=wf_frontend_analyze",
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
                    "wf_frontend_analyze",
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

            result = dict(output.get("result") or {})
            counts = dict(output.get("counts") or {})
            # TS/JSX-only analyzer misses Flask/Jinja (bank-of-anthos). Fill screens when empty.
            if not result.get("screens"):
                try:
                    from app.skills.frontend_analyze.script.extract_flask_screens import (
                        extract_flask_screens,
                    )

                    flask_hit = extract_flask_screens(workspace_path)
                    if flask_hit.get("screens"):
                        result["screens"] = list(flask_hit["screens"])
                        result["apiCalls"] = list(result.get("apiCalls") or []) + list(
                            flask_hit.get("apiCalls") or []
                        )
                        # 세션 선행조건 재료 (D-015) — 로그인 뒤 동작 트리거·인증 전용 요소
                        result["actionForms"] = list(flask_hit.get("actionForms") or [])
                        result["sessionMarkers"] = list(flask_hit.get("sessionMarkers") or [])
                        result["extractors"] = list(result.get("extractors") or []) + [
                            "flask-jinja"
                        ]
                        counts["screens"] = len(result["screens"])
                        counts["apiCalls"] = len(result.get("apiCalls") or [])
                        out_file.write_text(
                            __import__("json").dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        logger.info(
                            "frontend flask fallback screens=%s apiCalls=%s id=%s",
                            counts["screens"],
                            counts.get("apiCalls"),
                            analysis_id,
                        )
                except Exception as flask_exc:  # noqa: BLE001
                    logger.info("frontend flask fallback skipped: %s", flask_exc)
            summary = summary.model_copy(
                update={
                    "status": "complete",
                    "result": result,
                    "screenCount": int(counts.get("screens") or len(result.get("screens", []))),
                    "componentCount": int(
                        counts.get("components") or len(result.get("components", []))
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
            logger.exception("frontend analysis failed id=%s", analysis_id)
            summary = summary.model_copy(
                update={
                    "status": "error",
                    "fileFailed": 1 if file_total else 0,
                    "progressPercent": round(summary.fileCompleted / file_total * 100) if file_total else 0,
                    "error": str(exc)[:2000],
                }
            )
            return self.store.save_analysis(summary)
