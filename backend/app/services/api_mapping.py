from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_ANALYSIS, REPO_ROOT
from app.services.api_mapping_models import (
    ApiMappingCreateRequest,
    ApiMappingPatchRequest,
    MappingSetSummary,
)
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore

logger = logging.getLogger(__name__)


class ApiMappingService:
    """Resolve FE/BE analysis artifacts, then run Hub Workflow (no join logic here)."""

    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def create_for_project(
        self, project_id: str, payload: ApiMappingCreateRequest
    ) -> MappingSetSummary:
        project = self.store.get_project(project_id)
        if not project:
            raise ValueError("project not found")

        fe_path, fe_id = self._resolve_analysis(
            project_id,
            role="frontend",
            analysis_id=payload.frontendAnalysisId,
            explicit_path=payload.frontendAnalysisPath,
        )
        be_path, be_id = self._resolve_analysis(
            project_id,
            role="backend",
            analysis_id=payload.backendAnalysisId,
            explicit_path=payload.backendAnalysisPath,
        )

        mapping_set_id = f"MAPSET-{uuid4().hex[:12]}"
        out_file = ARTIFACTS_ANALYSIS / mapping_set_id / "api-mapping.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)

        response = PlatformRunnerAdapter().execute(
            "wf_api_map",
            {
                "projectId": project_id,
                "frontendAnalysisId": fe_id,
                "backendAnalysisId": be_id,
                "frontendAnalysisPath": str(fe_path),
                "backendAnalysisPath": str(be_path),
                "mappingSetId": mapping_set_id,
                "artifactPath": str(out_file.resolve()),
            },
        )
        if response.status != "complete" or not response.stepResults:
            raise RuntimeError(response.summary or "api map workflow failed")

        output = response.stepResults[0].get("output") or {}
        if not output.get("ok"):
            raise RuntimeError("api_map skill output missing ok=true")

        result = output.get("result") or {}
        summary = MappingSetSummary(
            mappingSetId=result.get("mappingSetId") or mapping_set_id,
            projectId=project_id,
            frontendAnalysisId=fe_id,
            backendAnalysisId=be_id,
            status="complete",
            artifactPath=output.get("artifactPath") or str(out_file),
            summary=dict(result.get("summary") or output.get("summary") or {}),
            mappings=list(result.get("mappings") or []),
            unmappedFrontendCalls=list(result.get("unmappedFrontendCalls") or []),
            unmappedBackendEndpoints=list(result.get("unmappedBackendEndpoints") or []),
            createdAt=result.get("createdAt") or utc_now().isoformat(),
            result=result,
        )
        return self.store.save_mapping_set(summary)

    def list_for_project(self, project_id: str) -> list[MappingSetSummary]:
        if not self.store.get_project(project_id):
            raise ValueError("project not found")
        return list(self.store.list_mapping_sets(project_id))

    def get_set(self, mapping_set_id: str) -> MappingSetSummary | None:
        return self.store.get_mapping_set(mapping_set_id)

    def patch_mapping(
        self, mapping_id: str, payload: ApiMappingPatchRequest
    ) -> dict:
        found = self.store.patch_mapping(
            mapping_id,
            status=payload.status,
            note=payload.note,
            backend_endpoint_id=payload.backendEndpointId,
        )
        if not found:
            raise LookupError(f"mapping not found: {mapping_id}")
        return found

    def _resolve_analysis(
        self,
        project_id: str,
        *,
        role: str,
        analysis_id: str | None,
        explicit_path: str | None,
    ) -> tuple[Path, str | None]:
        if explicit_path:
            path = Path(explicit_path).expanduser().resolve()
            if not path.is_file():
                # allow repo-relative
                alt = (REPO_ROOT / explicit_path).resolve()
                path = alt if alt.is_file() else path
            if not path.is_file():
                raise ValueError(f"{role} analysis file not found: {explicit_path}")
            return path, analysis_id

        if analysis_id:
            item = self.store.get_analysis(analysis_id)
            if not item or item.role != role:
                raise ValueError(f"{role} analysis not found: {analysis_id}")
            if item.status != "complete" or not item.artifactPath:
                raise ValueError(f"{role} analysis not complete: {analysis_id}")
            path = Path(item.artifactPath).resolve()
            if not path.is_file():
                raise ValueError(f"{role} artifact missing: {path}")
            return path, analysis_id

        # latest complete analysis for project+role
        candidates = [
            a
            for a in self.store.list_analyses(project_id)
            if a.role == role and a.status == "complete" and a.artifactPath
        ]
        if not candidates:
            raise ValueError(
                f"no complete {role} analysis for project — run analysis first or pass ids/paths"
            )
        item = sorted(candidates, key=lambda a: a.createdAt, reverse=True)[0]
        path = Path(str(item.artifactPath)).resolve()
        if not path.is_file():
            raise ValueError(f"{role} artifact missing: {path}")
        return path, item.id
