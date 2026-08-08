"""Console orchestration: connect → sync → analyze, resource trees, bulk actions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.analysis_models import BackendAnalysisRequest, FrontendAnalysisRequest
from app.services.analysis_progress import count_analysis_files
from app.services.backend_analysis import BackendAnalysisService
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
from app.services.frontend_analysis import FrontendAnalysisService
from app.services.input_recommend_service import InputRecommendService
from app.services.pipeline import AnalyzeToScenariosPipeline
from app.services.repository_models import RepoRole, RepositoryRegister, utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.repository_sync import RepositorySyncService
from app.services.resource_tree import build_resource_tree, expand_resource_node
from app.services.repository_models import ProjectCreate
from app.services.run_models import RunCreateRequest
from app.services.run_service import BrowserRunService, _normalize_derived_outcome
from app.services.scenario_models import PipelineRequest

logger = logging.getLogger(__name__)


def normalize_io_payload(raw: object) -> dict[str, object]:
    """Coerce graph node input/output attributes into the FlowNodeRuntime dict shape.

    Frontend analysis emits `attributes.inputs` as a list of field descriptors
    (name/field/selector/type). Keys are kept, values stay None so an unobserved
    field reads as missing_data instead of a fabricated value.
    """
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, list):
        return {}
    normalized: dict[str, object] = {}
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            normalized[f"field_{index}"] = entry
            continue
        key = str(entry.get("field") or entry.get("name") or f"field_{index}")
        normalized[key] = entry.get("value") if "value" in entry else None
    return normalized


def normalize_flow_runtime(raw: dict[str, object]) -> dict[str, object]:
    """Apply IO normalization to a stored flow node runtime record."""
    item = dict(raw)
    item["input"] = normalize_io_payload(item.get("input"))
    item["output"] = normalize_io_payload(item.get("output"))
    operation = item.get("operation")
    item["operation"] = dict(operation) if isinstance(operation, dict) else {}
    return item


def _scoped_flow_parts(graph_id: str) -> tuple[str, str | None]:
    """Return source graph id and optional scenario id for a flow runtime key."""
    if "::" not in graph_id:
        return graph_id, None
    source_id, scenario_id = graph_id.split("::", 1)
    return source_id, scenario_id or None


def _safe_step_value(reference: object, run_inputs: dict[str, Any]) -> object:
    """Resolve non-secret ``inputs.foo`` references for the step inspector."""
    ref = str(reference or "")
    if not ref.startswith("inputs."):
        return None
    key = ref.split(".", 1)[1]
    lowered = key.lower()
    if any(token in lowered for token in ("password", "secret", "token", "credential")):
        return "***" if key in run_inputs else None
    return run_inputs.get(key)


def _flow_operation(node: dict[str, Any]) -> dict[str, Any]:
    attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    request = attrs.get("request") if isinstance(attrs.get("request"), dict) else {}
    target = attrs.get("target") if isinstance(attrs.get("target"), dict) else {}
    action = str(attrs.get("action") or "")
    method = str(request.get("method") or attrs.get("method") or "").upper()
    path = str(request.get("path") or attrs.get("path") or attrs.get("route") or "")
    return {
        "kind": "http" if method and request.get("path") else "browser",
        "stepId": attrs.get("scenarioStepId"),
        "action": action or node.get("type"),
        "method": method or None,
        "path": path or None,
        "target": target or None,
    }


def _planned_step_input(node: dict[str, Any], latest_run: object | None = None) -> dict[str, Any]:
    attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    target = attrs.get("target") if isinstance(attrs.get("target"), dict) else {}
    request = attrs.get("request") if isinstance(attrs.get("request"), dict) else {}
    value_ref = attrs.get("valueFrom") or attrs.get("valueRef")
    run_inputs = dict(getattr(latest_run, "inputs", {}) or {}) if latest_run else {}
    payload: dict[str, Any] = {
        "stepId": attrs.get("scenarioStepId"),
        "action": attrs.get("action") or node.get("type"),
    }
    if target:
        payload["target"] = target
    if request:
        payload["request"] = request
    if value_ref:
        payload["valueSource"] = value_ref
        payload["value"] = _safe_step_value(value_ref, run_inputs)
    expect = attrs.get("expect")
    if isinstance(expect, dict) and expect:
        payload["expect"] = expect
    return {key: value for key, value in payload.items() if value not in (None, "", {})}


def _observed_step_output(step: object | None, run_id: str | None = None) -> dict[str, Any]:
    if step is None:
        return {"observed": False, "note": "아직 이 단계의 실행 관측이 없습니다."}
    return {
        "observed": True,
        "runId": run_id,
        "status": getattr(step, "status", None),
        "summary": getattr(step, "observationSummary", None),
        "networkRefs": list(getattr(step, "networkRefs", []) or []),
        "snapshotPath": getattr(step, "snapshotPath", None),
        "screenshotPath": getattr(step, "screenshotPath", None),
        "missingData": list(getattr(step, "missingData", []) or []),
    }


PLACEHOLDER_SET_NAMES = {"기본 저장소", "저장소", ""}
# Internal workspace/cache ids are never a user-facing repository name.
INTERNAL_ID_PREFIXES = ("REPO-", "RS-", "IG-", "AN-", "PRJ-", "SCN-", "RUN-")


def _repo_slug(repo: object) -> str | None:
    """Repository folder name from its url or local path — deterministic parse only."""
    raw = getattr(repo, "url", None) or getattr(repo, "path", None)
    if not raw:
        return None
    text = str(raw).rstrip("/")
    if text.endswith(".git"):
        text = text[: -len(".git")]
    tail = text.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not tail or tail.upper().startswith(INTERNAL_ID_PREFIXES):
        return None
    return tail


def _is_internal_id(text: str) -> bool:
    return text.upper().startswith(INTERNAL_ID_PREFIXES)


def repository_display_name(repo_set: object | None, fallback: str | None = None) -> str:
    """User-facing 연결 저장소 명칭.

    A repository set keeps a placeholder name ("기본 저장소") when the user did not type
    one on connect, and a wizard connect from a workspace folder can even store an
    internal id ("REPO-BA-…"). Neither tells the tester anything. Prefer, in order:
    the typed name, the repository folder name parsed from url/path, then the caller's
    fallback (project name).
    """
    if repo_set is None:
        return (fallback or "").strip() or "연결 저장소"
    name = (getattr(repo_set, "name", "") or "").strip()
    if name and name not in PLACEHOLDER_SET_NAMES and not _is_internal_id(name):
        return name
    slugs: list[str] = []
    for repo in getattr(repo_set, "repositories", []) or []:
        slug = _repo_slug(repo)
        if slug and slug not in slugs:
            slugs.append(slug)
    if slugs:
        return " · ".join(slugs[:2])
    return (fallback or "").strip() or "연결 저장소"


def _source_identity(source_type: object, source: object, role: RepoRole) -> tuple[str, str, str, str]:
    """Stable identity for an already-connected repository source.

    Display names are deliberately excluded: the same Git/local root renamed in the
    wizard is still one connection, not another repository row.
    """
    source_value = str(getattr(source_type, "value", source_type) or "")
    raw = str(getattr(source, "url", None) or getattr(source, "path", None) or "").strip()
    if source_value == "github":
        location = raw.rstrip("/")
        if location.lower().endswith(".git"):
            location = location[:-4]
        location = location.lower()
    else:
        location = str(Path(raw).expanduser()).rstrip("/\\")
    branch = str(getattr(source, "branch", None) or "main").strip()
    subdir = str(getattr(source, "subdir", None) or "").strip("/\\")
    return (role.value, source_value, location, f"{branch}:{subdir}")


class ConsoleService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store
        self.sync = RepositorySyncService(store)
        self.fe = FrontendAnalysisService(store)
        self.be = BackendAnalysisService(store)
        self.pipeline = AnalyzeToScenariosPipeline(store)
        self.input_recommend = InputRecommendService(store)
        self.runs = BrowserRunService(store)

    def connect_pair(self, payload: ConnectPairRequest) -> ConnectResult:
        if payload.projectId:
            project = self.store.get_project(payload.projectId)
            if not project:
                raise LookupError(f"project not found: {payload.projectId}")
        else:
            project = self.store.create_project(
                ProjectCreate(
                    name=payload.projectName or payload.repositoryName,
                    description=payload.description,
                    ownerUserId=payload.ownerUserId or "QA-DEFAULT",
                )
            )

        requested_sources: list[tuple[RepoRole, object]] = []
        if payload.repository is not None:
            requested_sources.append((RepoRole.workspace, payload.repository))
        else:
            if payload.frontend is not None:
                requested_sources.append((RepoRole.frontend, payload.frontend))
            if payload.backend is not None:
                requested_sources.append((RepoRole.backend, payload.backend))

        requested_identities = {
            _source_identity(payload.sourceType, source, role)
            for role, source in requested_sources
        }
        repo_set = None
        updated_connection = False
        if payload.repositorySetId:
            repo_set = self.store.get_set(payload.repositorySetId)
            if not repo_set or repo_set.projectId != project.id:
                raise LookupError(f"repository set not found: {payload.repositorySetId}")
            if payload.repository is None:
                raise ValueError("repositorySetId edit supports one repository root")
            current = next(
                (repo for repo in repo_set.repositories if repo.role == RepoRole.workspace),
                repo_set.repositories[0] if repo_set.repositories else None,
            )
            if current is None:
                self.sync.register(
                    project.id,
                    RepositoryRegister(
                        role=RepoRole.workspace,
                        sourceType=payload.sourceType,
                        url=payload.repository.url,
                        path=payload.repository.path,
                        subdir=payload.repository.subdir,
                        branch=payload.repository.branch,
                        token=payload.repository.token,
                    ),
                    repository_set_id=repo_set.id,
                    repository_set_name=payload.repositoryName,
                )
            elif current.sourceType == payload.sourceType:
                updated = self.store.update_repository(
                    repo_set.id,
                    current.id,
                    url=payload.repository.url,
                    path=payload.repository.path,
                    subdir=payload.repository.subdir,
                    branch=payload.repository.branch,
                    token=payload.repository.token,
                )
                if updated is None:
                    raise LookupError(f"repository not found: {current.id}")
                repo_set = updated
            else:
                self.store.delete_repository(repo_set.id, current.id)
                self.sync.register(
                    project.id,
                    RepositoryRegister(
                        role=RepoRole.workspace,
                        sourceType=payload.sourceType,
                        url=payload.repository.url,
                        path=payload.repository.path,
                        subdir=payload.repository.subdir,
                        branch=payload.repository.branch,
                        token=payload.repository.token,
                    ),
                    repository_set_id=repo_set.id,
                    repository_set_name=payload.repositoryName,
                )
            repo_set = self.store.rename_repository_set(repo_set.id, payload.repositoryName) or repo_set
            updated_connection = True
        else:
            for candidate in reversed(self.store.list_sets_for_project(project.id)):
                existing_identities = {
                    _source_identity(repo.sourceType, repo, repo.role)
                    for repo in candidate.repositories
                }
                if requested_identities and requested_identities.issubset(existing_identities):
                    repo_set = candidate
                    break
        already_connected = repo_set is not None
        if repo_set is None:
            repo_set = self.store.create_repository_set(project.id, payload.repositoryName)
        elif not updated_connection and repo_set.name != payload.repositoryName:
            repo_set = self.store.rename_repository_set(repo_set.id, payload.repositoryName) or repo_set

        # Preferred path: one git/local root → full tree (no FE/BE subdir)
        if payload.repository is not None and not already_connected:
            self.sync.register(
                project.id,
                RepositoryRegister(
                    role=RepoRole.workspace,
                    sourceType=payload.sourceType,
                    url=payload.repository.url,
                    path=payload.repository.path,
                    subdir=payload.repository.subdir,
                    branch=payload.repository.branch,
                    token=payload.repository.token,
                ),
                repository_set_id=repo_set.id,
                repository_set_name=payload.repositoryName,
            )
        elif not already_connected:
            if payload.frontend is not None:
                self.sync.register(
                    project.id,
                    RepositoryRegister(
                        role=RepoRole.frontend,
                        sourceType=payload.sourceType,
                        url=payload.frontend.url,
                        path=payload.frontend.path,
                        subdir=payload.frontend.subdir,
                        branch=payload.frontend.branch,
                        token=payload.frontend.token,
                    ),
                    repository_set_id=repo_set.id,
                    repository_set_name=payload.repositoryName,
                )
            if payload.backend is not None:
                self.sync.register(
                    project.id,
                    RepositoryRegister(
                        role=RepoRole.backend,
                        sourceType=payload.sourceType,
                        url=payload.backend.url,
                        path=payload.backend.path,
                        subdir=payload.backend.subdir,
                        branch=payload.backend.branch,
                        token=payload.backend.token,
                    ),
                    repository_set_id=repo_set.id,
                    repository_set_name=payload.repositoryName,
                )

        repo_set = self.store.get_set(repo_set.id) or repo_set
        if not repo_set.repositories:
            raise ValueError("no repository source registered")

        fe_id = next((r.id for r in repo_set.repositories if r.role == RepoRole.frontend), None)
        be_id = next((r.id for r in repo_set.repositories if r.role == RepoRole.backend), None)
        ws_id = next((r.id for r in repo_set.repositories if r.role == RepoRole.workspace), None)

        synced = self.sync.sync(repo_set.id, force=False)
        analysis_started = False
        if payload.autoAnalyze and synced.status.value in {"complete", "cached"}:
            try:
                analysis_started = self._analyze_synced_repos(project.id, synced)
            except Exception as exc:  # noqa: BLE001
                logger.warning("auto analyze after connect failed: %s", exc)
                self.store.append_log(synced.id, f"auto analyze deferred: {exc}")

        display_name = repository_display_name(repo_set, payload.repositoryName)
        message = (
            f"「{display_name}」 연결 정보를 수정하고 다시 동기화했습니다."
            if updated_connection
            else f"「{display_name}」은 이미 연결되어 있어 기존 연결을 갱신했습니다."
            if already_connected
            else f"「{display_name}」 연결이 완료되었습니다. 동기화 및 분석을 진행했습니다."
            if analysis_started
            else f"「{display_name}」 연결이 완료되었습니다. 저장소 트리를 확인하세요."
        )
        if synced.status.value == "error":
            message = f"「{display_name}」 연결은 등록되었으나 동기화 중 오류가 발생했습니다."

        return ConnectResult(
            projectId=project.id,
            repositorySetId=synced.id,
            repositoryName=display_name,
            status="connected" if synced.status.value != "error" else "error",
            message=message,
            syncStatus=synced.status.value,
            analysisStarted=analysis_started,
            frontendRepoId=fe_id,
            backendRepoId=be_id,
            workspaceRepoId=ws_id,
        )

    def bulk_analyze(self, payload: BulkAnalyzeRequest) -> BulkAnalyzeResult:
        set_ids = list(payload.repositorySetIds or [])
        if not set_ids and payload.projectId:
            set_ids = [s.id for s in self.store.list_sets_for_project(payload.projectId)]
        if not set_ids and payload.repositoryIds:
            for proj in self.store.list_projects():
                for rs in self.store.list_sets_for_project(proj.id):
                    if any(r.id in payload.repositoryIds for r in rs.repositories):
                        set_ids.append(rs.id)
        if not set_ids:
            raise ValueError("저장소(이름)를 선택하세요")

        results: list[dict] = []
        for set_id in set_ids:
            repo_set = self.store.get_set(set_id)
            if not repo_set:
                results.append({"repositorySetId": set_id, "status": "error", "error": "not found"})
                continue
            if repo_set.status.value not in {"complete", "cached"}:
                repo_set = self.sync.sync(repo_set.id, force=False)
            for repo in repo_set.repositories:
                if not repo.workspacePath:
                    results.append(
                        {
                            "repositorySetId": set_id,
                            "repositoryName": repository_display_name(repo_set),
                            "repositoryId": repo.id,
                            "role": repo.role.value,
                            "status": "error",
                            "error": "workspacePath missing",
                        }
                    )
                    continue
                try:
                    if repo.role == RepoRole.workspace:
                        started, analysis_ids = self._analyze_workspace_repo(
                            repo_set.projectId, repo_set, repo, force=bool(payload.force)
                        )
                        results.append(
                            {
                                "repositorySetId": set_id,
                                "repositoryName": repository_display_name(repo_set),
                                "repositoryId": repo.id,
                                "role": repo.role.value,
                                "status": "complete" if started else "skipped",
                                "analysisIds": analysis_ids,
                                "analysisId": analysis_ids[0] if analysis_ids else None,
                                "message": "workspace tree synced; role-specific analyze optional",
                            }
                        )
                        # Also emit one row per analysis for FE chaining
                        for aid in analysis_ids:
                            analysis = self.store.get_analysis(aid)
                            results.append(
                                {
                                    "repositorySetId": set_id,
                                    "repositoryName": repository_display_name(repo_set),
                                    "repositoryId": repo.id,
                                    "role": analysis.role if analysis else "workspace",
                                    "status": analysis.status if analysis else "complete",
                                    "analysisId": aid,
                                }
                            )
                        continue
                    if repo.role == RepoRole.frontend:
                        summary = self.fe.run(
                            FrontendAnalysisRequest(
                                projectId=repo_set.projectId,
                                repositorySetId=repo_set.id,
                                workspacePath=repo.workspacePath,
                                commitSha=repo.commitSha,
                                force=bool(payload.force),
                            )
                        )
                    else:
                        summary = self.be.run(
                            BackendAnalysisRequest(
                                projectId=repo_set.projectId,
                                repositorySetId=repo_set.id,
                                workspacePath=repo.workspacePath,
                                commitSha=repo.commitSha,
                                force=bool(payload.force),
                            )
                        )
                    results.append(
                        {
                            "repositorySetId": set_id,
                            "repositoryName": repository_display_name(repo_set),
                            "repositoryId": repo.id,
                            "role": repo.role.value,
                            "status": summary.status,
                            "analysisId": summary.id,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    results.append(
                        {
                            "repositorySetId": set_id,
                            "repositoryName": repository_display_name(repo_set),
                            "repositoryId": repo.id,
                            "role": repo.role.value,
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        ok = sum(1 for r in results if r.get("status") not in {"error", "failed"})
        return BulkAnalyzeResult(
            status="complete" if ok == len(results) else "partial",
            message=f"저장소 단위 분석 완료: 성공 {ok}/{len(results)}. 분석 메뉴에서 확인하세요.",
            results=results,
        )

    def list_scenario_sets(self, project_id: str | None = None) -> list[dict]:
        """시나리오 생성 단위 목록 — 연결 저장소 기준으로 묶는다.

        A generation run produces one interaction graph plus its scenarios, so the
        graph id is the 생성 ID the tester sees. Repository name comes from the graph's
        repository set; counts and last outcome are aggregated from stored runs only.
        """
        from app.services.scenario_service import ScenarioService

        scenarios = ScenarioService(self.store).list_scenarios(project_id=project_id)
        runs_by_scenario: dict[str, object] = {}
        for run in self.store.list_runs():
            existing = runs_by_scenario.get(run.scenarioId)
            if existing is None or (run.createdAt or "") > (getattr(existing, "createdAt", "") or ""):
                runs_by_scenario[run.scenarioId] = run

        groups: dict[str, dict] = {}
        for scenario in scenarios:
            graph_id = scenario.graphId or (
                (scenario.result or {}).get("sourceRefs", {}).get("graphId")
                if isinstance(scenario.result, dict)
                else None
            )
            key = str(graph_id or f"{scenario.projectId}:unlinked")
            group = groups.get(key)
            if group is None:
                graph = self.store.get_graph(graph_id) if graph_id else None
                repo_set = (
                    self.store.get_set(graph.repositorySetId)
                    if graph and graph.repositorySetId
                    else self.store.get_set_for_project(scenario.projectId)
                    if scenario.projectId
                    else None
                )
                project = self.store.get_project(scenario.projectId) if scenario.projectId else None
                group = {
                    "setId": key,
                    "graphId": graph_id,
                    "projectId": scenario.projectId,
                    "projectName": project.name if project else scenario.projectId,
                    "repositoryName": repository_display_name(
                        repo_set, fallback=project.name if project else None
                    ),
                    "scenarioCount": 0,
                    "unresolvedCount": 0,
                    "executedCount": 0,
                    "runningCount": 0,
                    "failureCount": 0,
                    "createdAt": scenario.createdAt,
                    "lastRunAt": None,
                    "lastOutcomeKind": None,
                    "serviceIds": [],
                }
                groups[key] = group

            group["scenarioCount"] += 1
            group["unresolvedCount"] += scenario.unresolvedCount or 0
            if scenario.serviceId and scenario.serviceId not in group["serviceIds"]:
                group["serviceIds"].append(scenario.serviceId)
            if scenario.createdAt and (
                not group["createdAt"] or scenario.createdAt < group["createdAt"]
            ):
                group["createdAt"] = scenario.createdAt

            run = runs_by_scenario.get(scenario.scenarioId)
            if run is None:
                continue
            group["executedCount"] += 1
            status = str(getattr(run, "status", "") or "").upper()
            if status in {"RUNNING", "IN_PROGRESS", "ACTIVE", "QUEUED"}:
                group["runningCount"] += 1
            kind = str(getattr(run, "outcomeKind", "") or "")
            if kind in {"fail", "failure", "error"}:
                group["failureCount"] += 1
            created = getattr(run, "createdAt", None)
            if created and (not group["lastRunAt"] or created > group["lastRunAt"]):
                group["lastRunAt"] = created
                group["lastOutcomeKind"] = kind or None

        result = list(groups.values())
        for group in result:
            total = group["scenarioCount"]
            done = group["executedCount"]
            if group["runningCount"] > 0:
                group["status"] = "running"
            elif done == 0:
                group["status"] = "ready"
            elif done < total:
                group["status"] = "partial"
            else:
                group["status"] = "executed"
        return sorted(result, key=lambda g: (g.get("repositoryName") or "", g.get("createdAt") or ""))

    def stop_scenario_set(self, set_id: str) -> dict:
        """저장소 시나리오 묶음에서 아직 끝나지 않은 실행만 취소한다.

        The tester needs a 「테스트 종료」 next to 「테스트 수행」, and a set is only a
        grouping, so this cancels the runs that belong to it. Already-finished runs are
        left untouched and reported, never rewritten.
        """
        target = next(
            (item for item in self.list_scenario_sets() if item.get("setId") == set_id),
            None,
        )
        if target is None:
            raise LookupError(f"scenario set not found: {set_id}")
        scenario_ids = {
            scenario.scenarioId
            for scenario in self.store.list_scenarios(target.get("projectId"))
            if (
                scenario.graphId == target.get("graphId")
                or (target.get("graphId") is None and scenario.graphId is None)
            )
        }
        cancelled: list[str] = []
        skipped: list[str] = []
        for run in self.store.list_runs():
            if run.scenarioId not in scenario_ids:
                continue
            try:
                self.runs.cancel_run(run.runId)
                cancelled.append(run.runId)
            except (RuntimeError, LookupError):
                skipped.append(run.runId)
        message = (
            f"진행 중인 실행 {len(cancelled)}건을 종료했습니다."
            if cancelled
            else "종료할 진행 중 실행이 없습니다."
        )
        return {
            "setId": set_id,
            "cancelledRunIds": cancelled,
            "alreadyFinishedRunIds": skipped,
            "message": message,
        }

    def list_analysis_catalog(self, project_id: str | None = None) -> list[dict]:
        """List analyses; mark latest complete row per (repositorySetId, role). FE+BE pair is intentional."""
        items = []
        latest_keys: set[tuple[str, str]] = set()
        analyses = sorted(
            self.store.list_analyses(project_id),
            key=lambda a: a.createdAt or "",
            reverse=True,
        )
        for analysis in analyses:
            project = self.store.get_project(analysis.projectId)
            repo_set = (
                self.store.get_set(analysis.repositorySetId)
                if analysis.repositorySetId
                else self.store.get_set_for_project(analysis.projectId)
            )
            role = analysis.role
            role_label = {
                "frontend": "FRONTEND",
                "backend": "BACKEND",
                "workspace": "WORKSPACE",
            }.get(role, role.upper())
            repo_name = repository_display_name(
                repo_set, fallback=project.name if project else None
            )
            set_key = analysis.repositorySetId or (repo_set.id if repo_set else analysis.projectId)
            pair_key = (str(set_key), role)
            is_latest = pair_key not in latest_keys and analysis.status == "complete"
            if is_latest:
                latest_keys.add(pair_key)
            previous = next(
                (
                    candidate
                    for candidate in analyses
                    if candidate.id != analysis.id
                    and candidate.status == "complete"
                    and candidate.role == analysis.role
                    and str(candidate.repositorySetId or candidate.projectId) == str(set_key)
                    and (candidate.createdAt or "") < (analysis.createdAt or "")
                ),
                None,
            )
            deltas = (
                {
                    "screenCount": analysis.screenCount - previous.screenCount,
                    "componentCount": analysis.componentCount - previous.componentCount,
                    "endpointCount": analysis.endpointCount - previous.endpointCount,
                    "unresolvedCount": analysis.unresolvedCount - previous.unresolvedCount,
                }
                if previous
                else None
            )
            changed_from_previous = bool(
                previous
                and (
                    analysis.commitSha != previous.commitSha
                    or any(value != 0 for value in (deltas or {}).values())
                )
            )
            matching_repo = next(
                (
                    repo
                    for repo in (repo_set.repositories if repo_set else [])
                    if repo.role.value == analysis.role
                    or (repo.role.value == "workspace" and repo.workspacePath == analysis.workspacePath)
                ),
                None,
            )
            legacy_file_total = 0
            if not analysis.fileTotal and analysis.workspacePath:
                workspace = Path(analysis.workspacePath).expanduser().resolve()
                if workspace.is_dir():
                    legacy_file_total = count_analysis_files(workspace, analysis.role)
            file_total = int(
                analysis.fileTotal
                or legacy_file_total
                or (matching_repo.fileCount if matching_repo else 0)
                or 0
            )
            file_completed = int(
                analysis.fileCompleted
                or (file_total if analysis.status in {"complete", "cached"} else 0)
            )
            file_failed = int(analysis.fileFailed or (1 if analysis.status == "error" else 0))
            progress_percent = int(
                analysis.progressPercent
                or (round(file_completed / file_total * 100) if file_total else 0)
            )
            items.append(
                {
                    "analysisId": analysis.id,
                    "projectId": analysis.projectId,
                    "projectName": project.name if project else analysis.projectId,
                    "repositorySetId": analysis.repositorySetId or (repo_set.id if repo_set else None),
                    "repositoryName": repo_name,
                    "role": role,
                    "label": f"{repo_name} · {role_label}",
                    "pairNote": "저장소 1건의 FE/BE 페어" if role in {"frontend", "backend"} else None,
                    "isLatestForRole": is_latest,
                    "status": analysis.status,
                    "workspacePath": analysis.workspacePath,
                    "commitSha": analysis.commitSha,
                    "previousAnalysisId": previous.id if previous else None,
                    "previousCommitSha": previous.commitSha if previous else None,
                    "changedFromPrevious": changed_from_previous,
                    "delta": deltas,
                    "screenCount": analysis.screenCount,
                    "endpointCount": analysis.endpointCount,
                    "componentCount": analysis.componentCount,
                    "unresolvedCount": analysis.unresolvedCount,
                    "fileTotal": file_total,
                    "fileCompleted": file_completed,
                    "fileFailed": file_failed,
                    "progressPercent": progress_percent,
                    "createdAt": analysis.createdAt,
                }
            )
        # Prefer latest complete FE/BE rows first; hide superseded duplicates from default list
        # by sorting latest first, then keep only isLatestForRole + in-progress/error.
        visible = [
            i
            for i in items
            if i.get("isLatestForRole")
            or i.get("status") in {"progressing", "error", "queued"}
        ]
        return sorted(
            visible,
            key=lambda x: (x.get("repositoryName") or "", x.get("role") or "", x.get("createdAt") or ""),
            reverse=True,
        )

    def delete_analyses(self, analysis_ids: list[str]) -> dict:
        if not analysis_ids:
            raise ValueError("analysisIds required")
        removed = self.store.delete_analyses(analysis_ids)
        return {
            "status": "complete" if removed == len(analysis_ids) else "partial",
            "removed": removed,
            "requested": len(analysis_ids),
            "message": f"분석 결과 {removed}건을 삭제했습니다.",
        }

    def resource_tree(
        self,
        analysis_id: str,
        *,
        expand_path: str | None = None,
        max_depth: int = 3,
    ) -> ResourceTreeResponse:
        analysis = self.store.get_analysis(analysis_id)
        if not analysis:
            raise LookupError("analysis not found")
        root = Path(analysis.workspacePath or "")
        if not root.exists():
            raise ValueError("analysis workspacePath missing or not found")
        selection = self.store.get_resource_selection(analysis_id)
        excluded = set(selection.get("excludedPaths") or [])
        role = analysis.role
        role_tag = {"frontend": "FRONTEND", "backend": "BACKEND", "workspace": "WORKSPACE"}.get(
            role, role.upper()
        )
        label = f"레파지토리_{role_tag}_분석"
        if expand_path:
            nodes = expand_resource_node(
                root,
                expand_path,
                role=role,
                analysis_id=analysis_id,
                excluded=excluded,
            )
        else:
            nodes = build_resource_tree(
                root,
                role=role,
                analysis_id=analysis_id,
                max_depth=max_depth,
                excluded=excluded,
            )
        return ResourceTreeResponse(
            analysisId=analysis_id,
            role=role,
            rootPath=str(root),
            label=label,
            nodes=nodes,
        )

    def read_workspace_file(self, analysis_id: str, relative_path: str) -> dict:
        """Read a text file under analysis workspace (path-jail)."""
        analysis = self.store.get_analysis(analysis_id)
        if not analysis:
            raise LookupError("analysis not found")
        root = Path(analysis.workspacePath or "").resolve()
        if not root.exists():
            raise ValueError("analysis workspacePath missing or not found")
        rel = relative_path.strip().lstrip("/")
        if not rel or ".." in Path(rel).parts:
            raise ValueError("invalid path")
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("path escapes workspace") from exc
        if not target.is_file():
            raise LookupError("file not found")
        # Skip binary-ish files
        suffix = target.suffix.lower()
        binary = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".jar", ".class", ".woff", ".woff2"}
        if suffix in binary:
            return {
                "analysisId": analysis_id,
                "path": rel,
                "name": target.name,
                "truncated": True,
                "content": f"// binary file ({suffix or 'unknown'}) — 미리보기 생략",
            }
        raw = target.read_bytes()
        if b"\x00" in raw[:2048]:
            return {
                "analysisId": analysis_id,
                "path": rel,
                "name": target.name,
                "truncated": True,
                "content": "// binary content — 미리보기 생략",
            }
        text = raw.decode("utf-8", errors="replace")
        max_chars = 40_000
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n\n// … truncated …"
        return {
            "analysisId": analysis_id,
            "path": rel,
            "name": target.name,
            "truncated": truncated,
            "content": text,
        }

    def update_resource_selection(self, payload: ResourceSelectionUpdate) -> ResourceSelectionState:
        if not self.store.get_analysis(payload.analysisId):
            raise LookupError("analysis not found")
        state = self.store.set_resource_selection(
            payload.analysisId,
            excluded_paths=payload.excludedPaths,
            selected_paths=payload.selectedPaths,
        )
        return ResourceSelectionState(
            analysisId=payload.analysisId,
            excludedPaths=list(state.get("excludedPaths") or []),
            selectedPaths=list(state.get("selectedPaths") or []),
        )

    def generate_scenarios(self, payload: ScenarioGenerateRequest):
        if payload.excludedPaths and payload.analysisIds:
            for aid in payload.analysisIds:
                self.store.set_resource_selection(aid, excluded_paths=payload.excludedPaths)
        fe_id: str | None = None
        be_id: str | None = None
        for aid in payload.analysisIds:
            analysis = self.store.get_analysis(aid)
            if not analysis:
                continue
            if analysis.role == "frontend" and not fe_id:
                fe_id = analysis.id
            elif analysis.role == "backend" and not be_id:
                be_id = analysis.id
        if not fe_id or not be_id:
            for analysis in self.store.list_analyses(payload.projectId):
                if analysis.role == "frontend" and not fe_id:
                    fe_id = analysis.id
                elif analysis.role == "backend" and not be_id:
                    be_id = analysis.id
        result = self.pipeline.run(
            payload.projectId,
            PipelineRequest(
                # Do not stamp customer-search — let graph/DSL derive per-endpoint serviceIds
                serviceId=payload.serviceId or "multi",
                frontendAnalysisId=fe_id,
                backendAnalysisId=be_id,
            ),
        )
        if payload.sourceMode == "test_data_csv":
            if not payload.testDataRows:
                raise ValueError("testDataRows required for test_data_csv")
            generated = [
                scenario
                for scenario_id in result.scenarioIds
                if (scenario := self.store.get_scenario(scenario_id)) is not None
            ]
            if not generated:
                raise RuntimeError("AI code analysis produced no base scenario to augment")
            adapted_ids: list[str] = []
            for index, row in enumerate(payload.testDataRows):
                base = generated[index % len(generated)]
                scenario_id = row.scenarioId
                existing = self.store.get_scenario(scenario_id)
                if existing and existing.scenarioId != base.scenarioId:
                    scenario_id = f"{row.scenarioId}-{uuid4().hex[:6]}"
                body = dict(base.result or {})
                path = [part.strip() for part in (row.businessPath or "").replace(">", "/").split("/") if part.strip()]
                if len(path) < 3:
                    path = [path[0] if path else "사용자 제공 업무", row.role or "업무 담당", row.description]
                path = path[:2] + [row.description]
                body.update(
                    {
                        "scenarioId": scenario_id,
                        "name": row.description,
                        "description": row.description,
                        "businessHierarchy": {
                            "path": path,
                            "assignedRole": row.role or path[1],
                            "source": "user_csv+ai_code_evidence",
                        },
                        "testDataSource": {
                            "mode": "test_data_csv",
                            "requestNaturalLanguage": row.requestNaturalLanguage,
                            "responseNaturalLanguage": row.responseNaturalLanguage,
                            "reviewRequired": True,
                            "aiAugmentedFromScenarioId": base.scenarioId,
                        },
                    }
                )
                updated = base.model_copy(
                    update={
                        "scenarioId": scenario_id,
                        "name": row.description,
                        "status": "REVIEW_REQUIRED",
                        "businessPath": path,
                        "assignedRole": row.role or path[1],
                        "result": body,
                        "createdAt": utc_now().isoformat(),
                    }
                )
                self.store.save_scenario(updated)
                adapted_ids.append(scenario_id)
                if base.scenarioId != scenario_id and index < len(generated):
                    self.store.delete_scenario(base.scenarioId)
            result = result.model_copy(
                update={
                    "scenarioIds": adapted_ids,
                    "message": f"사용자 CSV {len(adapted_ids)}건을 코드 분석 근거로 AI 보강했습니다. 자연어 기대값은 HITL 검토가 필요합니다.",
                }
            )
        self.store.update_project_journey(
            payload.projectId,
            scenario_create=result.status if result.status != "error" else "error",
            scenario_list="complete" if result.scenarioIds else "pending",
        )
        return result

    def bulk_run(self, payload: BulkRunRequest) -> BulkRunResult:
        runs: list[dict] = []
        for scenario_id in payload.scenarioIds:
            try:
                # A bulk request can contain scenarios with different fields and
                # boundaries.  When an operator did not provide an explicit shared
                # override, prepare each scenario's own evidence-based defaults
                # instead of leaking a sample value from another domain into every
                # form (for example, customerId into a deposit amount field).
                if not payload.inputs and not self.store.get_recommendation_by_scenario(
                    scenario_id
                ):
                    self.input_recommend.recommend(scenario_id)
                summary = self.runs.start_run(
                    scenario_id,
                    RunCreateRequest(
                        consent=True,
                        baseUrl=payload.baseUrl,
                        environmentId=payload.environmentId,
                        executionAccountId=payload.scenarioAccountIds.get(scenario_id),
                        inputs=payload.inputs,
                        mode="interactive",
                    ),
                )
                runs.append(
                    {
                        "scenarioId": scenario_id,
                        "runId": summary.runId,
                        "status": summary.status,
                        "outcomeKind": getattr(summary, "outcomeKind", None)
                        or _classify_outcome(summary),
                        "outcomeSummary": getattr(summary, "outcomeSummary", None)
                        or summary.observationSummary,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                runs.append(
                    {
                        "scenarioId": scenario_id,
                        "status": "error",
                        "outcomeKind": "fe_error",
                        "outcomeSummary": str(exc),
                        "error": str(exc),
                    }
                )
        ok = sum(1 for r in runs if r.get("status") not in {"error", "AUTO_FAILED"})
        return BulkRunResult(
            status="complete" if ok == len(runs) else "partial",
            message=f"일괄 실행 요청 완료: {ok}/{len(runs)}",
            runs=runs,
        )

    def patch_flow_node(self, graph_id: str, node_id: str, payload: FlowNodePatch) -> FlowNodeRuntime:
        key = f"{graph_id}:{node_id}"
        current = self.store.get_flow_node_runtime(key) or {
            "nodeId": node_id,
            "graphId": graph_id,
            "status": "pending",
            "input": {},
            "output": {},
        }
        if payload.input is not None:
            current["input"] = payload.input
        if payload.output is not None:
            current["output"] = payload.output
        nodes, _scenario_id = self._flow_nodes(graph_id)
        node = next((item for item in nodes if item.get("id") == node_id), None)
        method = None
        if node:
            attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
            method = attrs.get("method") or attrs.get("handlerMethod") or attrs.get("action") or node.get("type")
            current["operation"] = _flow_operation(node)
        current["method"] = method
        saved = self.store.save_flow_node_runtime(key, normalize_flow_runtime(current))
        return FlowNodeRuntime(**normalize_flow_runtime(saved))

    def retry_flow_node(
        self, graph_id: str, node_id: str, payload: FlowNodeRetryRequest
    ) -> FlowNodeRuntime:
        key = f"{graph_id}:{node_id}"
        # Prefer starting a linked scenario run (env+agent-browser). Never auto Pass/Fail.
        runtime: dict = {
            "nodeId": node_id,
            "graphId": graph_id,
            "status": "pending",
            "input": payload.input,
            "output": {"retryQueued": True, "note": payload.note},
            "errorMessage": None,
            "lastRetriedAt": utc_now().isoformat(),
            "method": None,
        }
        source_graph_id, scenario_id = _scoped_flow_parts(graph_id)
        graph = self.store.get_graph(source_graph_id)
        run_id: str | None = None
        if graph and graph.projectId:
            scenarios = (
                [self.store.get_scenario(scenario_id)]
                if scenario_id
                else [
                    s
                    for s in self.store.list_scenarios(graph.projectId)
                    if (s.graphId == source_graph_id)
                    or (
                        isinstance(s.result, dict)
                        and (s.result.get("sourceRefs") or {}).get("graphId") == source_graph_id
                    )
                ]
            )
            scenarios = [scenario for scenario in scenarios if scenario is not None]
            if scenarios:
                try:
                    from app.services.run_models import RunCreateRequest

                    node = next(
                        (item for item in self._flow_nodes(graph_id)[0] if item.get("id") == node_id),
                        None,
                    )
                    attrs = node.get("attributes") if node and isinstance(node.get("attributes"), dict) else {}
                    value_ref = str(attrs.get("valueFrom") or attrs.get("valueRef") or "")
                    retry_inputs: dict[str, Any] = {}
                    if isinstance(payload.input.get("runInputs"), dict):
                        retry_inputs.update(payload.input["runInputs"])
                    if value_ref.startswith("inputs.") and "value" in payload.input:
                        retry_inputs[value_ref.split(".", 1)[1]] = payload.input["value"]
                    summary = BrowserRunService(self.store).start_run(
                        scenarios[0].scenarioId,
                        RunCreateRequest(
                            consent=True,
                            inputs=retry_inputs,
                            mode="interactive",
                        ),
                    )
                    run_id = summary.runId
                    runtime["status"] = "pending"
                    runtime["output"] = {
                        "retryQueued": True,
                        "runId": run_id,
                        "note": payload.note or "flow node reprocess → browser run",
                        "observationOnly": True,
                    }
                except Exception as exc:  # noqa: BLE001
                    runtime["status"] = "failure"
                    runtime["errorMessage"] = f"재처리 실행 실패: {exc}"
                    runtime["output"] = {"retryQueued": False, "error": str(exc)}
        nodes, _ = self._flow_nodes(graph_id)
        if nodes:
            for node in nodes:
                if node.get("id") == node_id:
                    runtime["operation"] = _flow_operation(node)
                    runtime["method"] = (
                        node.get("attributes", {}).get("method")
                        or node.get("attributes", {}).get("action")
                        or node.get("name")
                    )
                    if runtime.get("errorMessage"):
                        break
                    vs = str(node.get("verificationStatus") or "").lower()
                    if "fail" in vs or "error" in vs:
                        runtime["status"] = "failure"
                        runtime["errorMessage"] = (
                            node.get("attributes", {}).get("error")
                            or "재시도 대기 · 이전 실패 관측"
                        )
                    break
        saved = self.store.save_flow_node_runtime(key, normalize_flow_runtime(runtime))
        return FlowNodeRuntime(**normalize_flow_runtime(saved))

    def list_flow_runtime(self, graph_id: str) -> list[FlowNodeRuntime]:
        stored = {
            str(item.get("nodeId")): self._drop_internal_error(graph_id, item)
            for item in self.store.list_flow_node_runtime(graph_id)
        }
        nodes, scenario_id = self._flow_nodes(graph_id)
        raw_latest_run = next(iter(self.store.list_runs(scenario_id)), None) if scenario_id else None
        latest_run = _normalize_derived_outcome(raw_latest_run) if raw_latest_run else None
        observed_by_step = {
            str(step.stepId): step for step in (getattr(latest_run, "steps", []) or [])
        }
        run_result = dict(getattr(latest_run, "result", {}) or {}) if latest_run else {}
        verdict = run_result.get("verdict") if isinstance(run_result.get("verdict"), dict) else {}
        diagnosis = run_result.get("runDiagnosis") if isinstance(run_result.get("runDiagnosis"), dict) else {}
        verdict_kind = str(verdict.get("verdict") or "")
        cause_category = str(diagnosis.get("causeCategory") or verdict.get("blockedCause") or "")
        policy_warning = cause_category in {"destructive_policy_blocked", "input_precondition_invalid"}
        attention_status = (
            "warning"
            if verdict_kind == "undetermined" or policy_warning
            else "failure"
            if verdict_kind == "expected_not_met"
            else None
        )
        attention_message = str(
            diagnosis.get("problemSummary")
            or diagnosis.get("causeSummary")
            or verdict.get("reason")
            or ""
        )
        first_action = next(
            (
                str(item.get("action") or "")
                for item in (diagnosis.get("actions") or [])
                if isinstance(item, dict) and item.get("action")
            ),
            "",
        )
        if first_action:
            attention_message = f"{attention_message} · 조치: {first_action}".strip(" ·")
        criterion_status: dict[str, str] = {}
        for item in (verdict.get("criteriaResults") or verdict.get("criteria") or []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            result = str(item.get("result") or "")
            if result == "not_met":
                criterion_status[str(item["id"])] = "failure"
            elif result == "undetermined":
                criterion_status[str(item["id"])] = "warning"
        attention_step_ids = {
            str(step.stepId)
            for step in (getattr(latest_run, "steps", []) or [])
            if set(step.missingData or [])
            & {"submit_blocked_destructive", "input_precondition_invalid"}
        }
        criterion_node_ids = {
            str(node.get("id") or "")
            for node in nodes
            if str((node.get("attributes") or {}).get("criterionId") or "") in criterion_status
        }
        attention_node_ids = {
            str(node.get("id") or "")
            for node in nodes
            if str((node.get("attributes") or {}).get("scenarioStepId") or "") in attention_step_ids
        } | criterion_node_ids
        if attention_status and not attention_node_ids and nodes:
            attention_node_ids.add(str(nodes[-1].get("id") or ""))
        items: list[dict[str, Any]] = []
        for node in nodes:
            node_id = str(node.get("id") or "")
            if not node_id:
                continue
            attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
            step_id = str(attrs.get("scenarioStepId") or "")
            observed = observed_by_step.get(step_id)
            vs = str(node.get("verificationStatus") or "").lower()
            status = "unknown"
            err = None
            if observed:
                observed_status = str(getattr(observed, "status", "") or "").lower()
                status = "failure" if observed_status in {"error", "failed", "failure"} else "success" if observed_status in {"ok", "complete", "completed", "success"} else "pending"
                if status == "failure":
                    err = getattr(observed, "observationSummary", None)
            elif "fail" in vs or "error" in vs:
                status = "failure"
                err = attrs.get("error")
            elif scenario_id:
                # A scenario definition is not a successful observation.
                status = "unknown"
            elif float(node.get("confidence") or 0) >= 0.85:
                status = "success"
            elif "pending" in vs:
                status = "pending"

            criterion_id = str(attrs.get("criterionId") or "")
            if node_id in attention_node_ids:
                status = criterion_status.get(criterion_id) or attention_status or status
                if policy_warning:
                    status = "warning"
                err = attention_message or err

            seeded_input = (
                _planned_step_input(node, latest_run)
                if scenario_id
                else normalize_io_payload(attrs.get("sampleInput") or attrs.get("inputs"))
            )
            seeded_output = (
                _observed_step_output(observed, getattr(latest_run, "runId", None))
                if scenario_id
                else normalize_io_payload(attrs.get("sampleOutput") or attrs.get("outputs"))
            )
            current = {
                "nodeId": node_id,
                "graphId": graph_id,
                "method": attrs.get("method") or attrs.get("handlerMethod") or attrs.get("action") or node.get("type"),
                "operation": _flow_operation(node),
                "status": status,
                "input": seeded_input,
                "output": seeded_output,
                "errorMessage": err,
            }
            saved = stored.get(node_id)
            if saved:
                # User-saved I/O wins; latest run observation refreshes output unless the
                # saved record was explicitly edited after the run.
                current.update(saved)
                current["operation"] = _flow_operation(node)
                if (observed or node_id in attention_node_ids) and not saved.get("lastRetriedAt"):
                    current["status"] = status
                    current["output"] = seeded_output
                    current["errorMessage"] = err
            normalized = normalize_flow_runtime(current)
            self.store.save_flow_node_runtime(f"{graph_id}:{node_id}", normalized)
            items.append(normalized)
        return [FlowNodeRuntime(**normalize_flow_runtime(i)) for i in items]

    def _flow_nodes(self, graph_id: str) -> tuple[list[dict[str, Any]], str | None]:
        """Resolve original or scenario-scoped graph nodes for runtime I/O."""
        source_graph_id, scenario_id = _scoped_flow_parts(graph_id)
        if scenario_id:
            from app.services.scenario_service import ScenarioService

            scoped = ScenarioService(self.store).scoped_graph(scenario_id)
            if scoped.sourceGraphId != source_graph_id:
                raise LookupError("scoped flow source graph mismatch")
            result = scoped.result or {}
            return [item for item in (result.get("nodes") or []) if isinstance(item, dict)], scenario_id
        graph = self.store.get_graph(source_graph_id)
        result = graph.result if graph and graph.result else {}
        return [item for item in (result.get("nodes") or []) if isinstance(item, dict)], None

    def _drop_internal_error(self, graph_id: str, runtime: dict) -> dict:
        """지난 내부 오류 문구(모듈 import 실패 등)를 노드에 남겨두지 않는다.

        고쳐진 결함의 스택 문구가 카드에 계속 붙어 있으면 관측 결과로 오독된다.
        사용자에게 의미 있는 관측(실패 사유)만 남기고 내부 예외 흔적은 지운다.
        """
        message = str(runtime.get("errorMessage") or "")
        if not message:
            return runtime
        internal = ("cannot import name", "Traceback", "ModuleNotFoundError", "/backend/app/")
        if not any(token in message for token in internal):
            return runtime
        cleaned = {**runtime, "errorMessage": None, "status": "unknown"}
        self.store.save_flow_node_runtime(
            f"{graph_id}:{runtime.get('nodeId')}", normalize_flow_runtime(cleaned)
        )
        return cleaned

    def repository_set_tree(
        self,
        set_id: str,
        *,
        expand_path: str | None = None,
        max_depth: int = 3,
        repository_id: str | None = None,
    ) -> ResourceTreeResponse:
        """Build file tree from synced repository workspace (no analysis required)."""
        repo_set = self.store.get_set(set_id)
        if not repo_set:
            raise LookupError("repository set not found")
        repos = list(repo_set.repositories)
        if repository_id:
            repos = [r for r in repos if r.id == repository_id]
        # Prefer workspace → frontend → backend
        order = {RepoRole.workspace: 0, RepoRole.frontend: 1, RepoRole.backend: 2}
        repos = sorted(repos, key=lambda r: order.get(r.role, 9))
        repo = next((r for r in repos if r.workspacePath), None)
        if not repo or not repo.workspacePath:
            raise ValueError("synced workspacePath missing — sync repository first")
        root = Path(repo.workspacePath)
        if not root.exists():
            raise ValueError("workspace path not found on disk")
        tree_id = f"set:{set_id}:{repo.id}"
        if expand_path:
            nodes = expand_resource_node(
                root,
                expand_path,
                role=repo.role.value,
                analysis_id=tree_id,
            )
        else:
            nodes = build_resource_tree(
                root,
                role=repo.role.value,
                analysis_id=tree_id,
                max_depth=max_depth,
            )
        return ResourceTreeResponse(
            analysisId=tree_id,
            repositorySetId=set_id,
            repositoryId=repo.id,
            role=repo.role.value,
            rootPath=str(root),
            label=f"{repository_display_name(repo_set)} · 저장소 트리",
            nodes=nodes,
        )

    def _analyze_synced_repos(self, project_id: str, repo_set) -> bool:
        started = False
        for repo in repo_set.repositories:
            if not repo.workspacePath:
                continue
            if repo.role == RepoRole.workspace:
                ok, _ids = self._analyze_workspace_repo(project_id, repo_set, repo)
                if ok:
                    started = True
                continue
            if repo.role == RepoRole.frontend:
                self.fe.run(
                    FrontendAnalysisRequest(
                        projectId=project_id,
                        repositorySetId=repo_set.id,
                        workspacePath=repo.workspacePath,
                        commitSha=repo.commitSha,
                    )
                )
                started = True
            elif repo.role == RepoRole.backend:
                self.be.run(
                    BackendAnalysisRequest(
                        projectId=project_id,
                        repositorySetId=repo_set.id,
                        workspacePath=repo.workspacePath,
                        commitSha=repo.commitSha,
                    )
                )
                started = True
        return started

    def _analyze_workspace_repo(
        self, project_id: str, repo_set, repo, *, force: bool = False
    ) -> tuple[bool, list[str]]:
        """Analyze the whole connected workspace without losing Flask/Jinja UI.

        A workspace repository can contain templates, static assets and server code
        under one root.  Stack metadata is only a hint and is often incomplete at
        connect time, so the FE analyzer must always inspect the root.  It already
        combines TS/JS analysis with Flask/Jinja extraction and safely returns an
        empty evidenced result when no UI exists.  The server analyzer remains
        guarded by server-language signals.
        """
        stack = repo.stack or {}
        frameworks = " ".join(str(x).lower() for x in (stack.get("frameworks") or []))
        languages = " ".join(str(x).lower() for x in (stack.get("languages") or []))
        blob = f"{frameworks} {languages}"
        started = False
        analysis_ids: list[str] = []
        # Never hide the UI half of a mixed repository because stack detection only
        # happened to report Python/Flask or Java.  Users choose the evidenced files
        # later in the source explorer before scenario generation.
        want_fe = True
        want_be = any(k in blob for k in ("spring", "java", "kotlin", "fastapi", "django", "flask"))
        # Bank-of-Anthos style: Python web + Java services under src/
        if not want_fe and not want_be:
            # Still try soft probes — analyzers may no-op / fail without inventing layout
            want_fe = "python" in blob or "html" in blob
            want_be = "java" in blob or "python" in blob
        # Even when Java BE is detected, still run FE if Jinja/HTML templates exist
        try:
            from pathlib import Path as _Path

            wp = _Path(str(repo.workspacePath or ""))
            if (wp / "src" / "frontend" / "templates").is_dir() or (wp / "templates").is_dir():
                want_fe = True
        except Exception:  # noqa: BLE001
            pass
        if want_fe:
            try:
                summary = self.fe.run(
                    FrontendAnalysisRequest(
                        projectId=project_id,
                        repositorySetId=repo_set.id,
                        workspacePath=repo.workspacePath,
                        commitSha=repo.commitSha,
                        force=force,
                    )
                )
                started = True
                if summary and summary.id:
                    analysis_ids.append(summary.id)
            except Exception as exc:  # noqa: BLE001
                logger.info("workspace FE analyze skipped: %s", exc)
                self.store.append_log(repo_set.id, f"workspace FE analyze skipped: {exc}")
        if want_be:
            try:
                summary = self.be.run(
                    BackendAnalysisRequest(
                        projectId=project_id,
                        repositorySetId=repo_set.id,
                        workspacePath=repo.workspacePath,
                        commitSha=repo.commitSha,
                    )
                )
                started = True
                if summary and summary.id:
                    analysis_ids.append(summary.id)
            except Exception as exc:  # noqa: BLE001
                logger.info("workspace BE analyze skipped: %s", exc)
                self.store.append_log(repo_set.id, f"workspace BE analyze skipped: {exc}")
        return started, analysis_ids


def _classify_outcome(summary) -> str:
    status = str(getattr(summary, "status", "") or "")
    obs = str(getattr(summary, "observationSummary", "") or "").lower()
    result = getattr(summary, "result", {}) or {}
    be_status = result.get("backendHttpStatus") or result.get("httpStatus")
    business = result.get("businessError") or result.get("businessMessage")
    if status in {"WAITING_FOR_REVIEW", "SUCCEEDED", "SUCCESS"} and not business:
        return "success"
    if business or "원장이 존재" in obs or "업무" in obs:
        return "business_error"
    if be_status and int(be_status) >= 400:
        return "be_error"
    if status in {"AUTO_FAILED", "FAILED", "error"}:
        if "backend" in obs or "api" in obs or "http" in obs:
            return "be_error"
        return "fe_error"
    return "unknown"
