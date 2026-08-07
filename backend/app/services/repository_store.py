from __future__ import annotations

from collections.abc import Sequence
from threading import Lock
from uuid import uuid4

from app.services.analysis_models import AnalysisSummary
from app.services.batch_models import BatchDefinition
from app.services.api_mapping_models import MappingSetSummary
from app.services.environment_models import (
    BrowserEngine,
    ExecutionAccount,
    ExecutionAccountCreate,
    ExecutionEnvironment,
    ExecutionEnvironmentCreate,
    ExecutionEnvironmentUpdate,
    HealthStatus,
    is_host_allowlisted,
)
from app.services.interaction_graph_models import InteractionGraphSummary
from app.services.component_contract_models import ComponentContractSummary
from app.services.input_recommend_models import InputProfileSummary, RecommendationSummary
from app.schemas.binding_validation import BindingValidationResult
from app.schemas.evidence import EvidenceManifest
from app.schemas.telemetry import BackendTelemetryEvent
from app.services.run_models import RunSummary
from app.services.scenario_models import ScenarioSummary
from app.services.repository_models import (
    JourneyStatus,
    Project,
    ProjectCreate,
    Repository,
    RepositorySet,
    SyncStatus,
    utc_now,
)
from app.services.sqlite_persist import kv_get, kv_set

# 기존 실행환경 비밀번호 저장 키. 추가 다중 계정은 메모리에서만 유지한다.
ENV_SECRET_KV_KEY = "platform_env_secrets_v1"
LEGACY_ENV_ACCOUNT_SECRET_KV_KEY = "platform_env_account_secrets_v1"


class InMemoryPlatformStore:
    """In-memory project + repository-set store with SQLite catalog persistence."""

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}
        self._sets: dict[str, RepositorySet] = {}
        self._files: dict[str, list[dict]] = {}  # repositorySetId -> inventory
        # commitSha -> workspace absolute path (cache)
        self._commit_cache: dict[str, str] = {}
        # repoId -> token (memory only, never serialized to API)
        self._tokens: dict[str, str] = {}
        self._analyses: dict[str, AnalysisSummary] = {}
        self._mapping_sets: dict[str, MappingSetSummary] = {}
        self._graphs: dict[str, InteractionGraphSummary] = {}
        self._scenarios: dict[str, ScenarioSummary] = {}
        self._contracts: dict[str, ComponentContractSummary] = {}
        self._recommendations: dict[str, RecommendationSummary] = {}
        self._profiles: dict[str, InputProfileSummary] = {}
        self._runs: dict[str, RunSummary] = {}
        self._batches: dict[str, BatchDefinition] = {}
        self._environments: dict[str, ExecutionEnvironment] = {}
        # environmentId -> 연결 비밀번호. API 응답·증적·로그에 절대 실리지 않는다.
        self._env_secrets: dict[str, str] = {}
        self._environment_accounts: dict[str, ExecutionAccount] = {}
        self._env_account_secrets: dict[str, str] = {}
        # analysisId -> {excludedPaths, selectedPaths}
        self._resource_selections: dict[str, dict] = {}
        # graphId:nodeId -> FlowNodeRuntime dict
        self._flow_node_runtime: dict[str, dict] = {}
        # Phase 10 — backend telemetry (memory; JSONL also via FileAdapter)
        self._backend_events: dict[str, list[BackendTelemetryEvent]] = {}
        self._backend_seq: dict[str, int] = {}
        self._binding_results: dict[str, BindingValidationResult] = {}
        self._evidence_manifests: dict[str, EvidenceManifest] = {}
        self._lock = Lock()
        self._hydrate_from_sqlite()

    def _hydrate_from_sqlite(self) -> None:
        blob = kv_get("platform_catalog_v1")
        if not isinstance(blob, dict):
            return
        try:
            for item in blob.get("projects") or []:
                p = Project.model_validate(item)
                self._projects[p.id] = p
            for item in blob.get("sets") or []:
                s = RepositorySet.model_validate(item)
                self._sets[s.id] = s
            for item in blob.get("analyses") or []:
                a = AnalysisSummary.model_validate(item)
                self._analyses[a.id] = a
            for item in blob.get("graphs") or []:
                g = InteractionGraphSummary.model_validate(item)
                self._graphs[g.graphId] = g
            for item in blob.get("scenarios") or []:
                sc = ScenarioSummary.model_validate(item)
                self._scenarios[sc.scenarioId] = sc
            sels = blob.get("resource_selections") or {}
            if isinstance(sels, dict):
                self._resource_selections = {str(k): dict(v) for k, v in sels.items()}
            files = blob.get("files") or {}
            if isinstance(files, dict):
                self._files = {str(k): list(v) for k, v in files.items()}
            flow_rt = blob.get("flow_node_runtime") or {}
            if isinstance(flow_rt, dict):
                self._flow_node_runtime = {str(k): dict(v) for k, v in flow_rt.items()}
            runs = blob.get("runs") or []
            for item in runs:
                try:
                    r = RunSummary.model_validate(item)
                    self._runs[r.runId] = r
                except Exception:
                    continue
            for item in blob.get("batches") or []:
                try:
                    batch = BatchDefinition.model_validate(item)
                    self._batches[batch.batchId] = batch
                except Exception:
                    continue
            for item in blob.get("binding_results") or []:
                try:
                    result = BindingValidationResult.model_validate(item)
                    self._binding_results[result.runId] = result
                except Exception:
                    continue
            backend_events = blob.get("backend_events") or {}
            if isinstance(backend_events, dict):
                for run_id, items in backend_events.items():
                    parsed: list[BackendTelemetryEvent] = []
                    for item in items or []:
                        try:
                            parsed.append(BackendTelemetryEvent.model_validate(item))
                        except Exception:
                            continue
                    if parsed:
                        self._backend_events[str(run_id)] = parsed
                        self._backend_seq[str(run_id)] = max(
                            event.requestSequence for event in parsed
                        )
            for item in blob.get("contracts") or []:
                try:
                    contract = ComponentContractSummary.model_validate(item)
                    self._contracts[contract.contractId] = contract
                except Exception:
                    continue
            for item in blob.get("recommendations") or []:
                try:
                    rec = RecommendationSummary.model_validate(item)
                    self._recommendations[rec.recommendationId] = rec
                except Exception:
                    continue
            for item in blob.get("profiles") or []:
                try:
                    profile = InputProfileSummary.model_validate(item)
                    self._profiles[profile.profileId] = profile
                except Exception:
                    continue
            for item in blob.get("evidence_manifests") or []:
                try:
                    manifest = EvidenceManifest.model_validate(item)
                    self._evidence_manifests[manifest.evidenceId] = manifest
                except Exception:
                    continue
            for item in blob.get("environments") or []:
                try:
                    env = ExecutionEnvironment.model_validate(item)
                    self._environments[env.id] = env
                except Exception:
                    continue
            self._hydrate_env_secrets()
            # 다중 계정 메타데이터/비밀번호를 저장했던 초기 구현의 흔적을 즉시 제거한다.
            if "environment_accounts" in blob:
                cleaned = dict(blob)
                cleaned.pop("environment_accounts", None)
                kv_set("platform_catalog_v1", cleaned)
        except Exception:
            # Corrupt blob must not block boot — keep empty memory store
            self._projects.clear()
            self._sets.clear()
            self._analyses.clear()

    def _hydrate_env_secrets(self) -> None:
        """연결 비밀번호는 카탈로그와 분리된 키에 둔다 (응답 직렬화 경로에 섞이지 않게)."""
        blob = kv_get(ENV_SECRET_KV_KEY)
        if isinstance(blob, dict):
            self._env_secrets = {str(k): str(v) for k, v in blob.items() if v}
        kv_set(LEGACY_ENV_ACCOUNT_SECRET_KV_KEY, {})

    def _persist_env_secrets(self) -> None:
        kv_set(ENV_SECRET_KV_KEY, dict(self._env_secrets))

    def _persist_catalog(self) -> None:
        with self._lock:
            blob = {
                "projects": [p.model_dump(mode="json") for p in self._projects.values()],
                "sets": [s.model_dump(mode="json") for s in self._sets.values()],
                "analyses": [a.model_dump(mode="json") for a in self._analyses.values()],
                "graphs": [g.model_dump(mode="json") for g in self._graphs.values()],
                "scenarios": [s.model_dump(mode="json") for s in self._scenarios.values()],
                "runs": [r.model_dump(mode="json") for r in self._runs.values()],
                "batches": [b.model_dump(mode="json") for b in self._batches.values()],
                "binding_results": [
                    r.model_dump(mode="json") for r in self._binding_results.values()
                ],
                "backend_events": {
                    run_id: [event.model_dump(mode="json") for event in events]
                    for run_id, events in self._backend_events.items()
                },
                "contracts": [c.model_dump(mode="json") for c in self._contracts.values()],
                "recommendations": [
                    r.model_dump(mode="json") for r in self._recommendations.values()
                ],
                "profiles": [p.model_dump(mode="json") for p in self._profiles.values()],
                "evidence_manifests": [
                    manifest.model_dump(mode="json")
                    for manifest in self._evidence_manifests.values()
                ],
                "environments": [e.model_dump(mode="json") for e in self._environments.values()],
                "resource_selections": self._resource_selections,
                "files": self._files,
                # step I/O · assertion hints · binding snapshots (paths only for large artifacts)
                "flow_node_runtime": self._flow_node_runtime,
            }
        kv_set("platform_catalog_v1", blob)

    def list_projects(self, owner_user_id: str | None = None) -> Sequence[Project]:
        with self._lock:
            values = list(self._projects.values())
        if owner_user_id:
            values = [p for p in values if p.ownerUserId == owner_user_id]
        return sorted(values, key=lambda p: p.updatedAt or p.createdAt, reverse=True)

    def get_project(self, project_id: str) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)

    def create_project(self, payload: ProjectCreate) -> Project:
        project_id = f"PRJ-{uuid4().hex[:12]}"
        now = utc_now()
        project = Project(
            id=project_id,
            name=payload.name,
            description=payload.description,
            ownerUserId=payload.ownerUserId or "QA-DEFAULT",
            aiPolicy=payload.aiPolicy,
            modelSelectionMode=payload.modelSelectionMode,
            modelBindings=payload.modelBindings,
            repositorySetId=None,
            repositorySetIds=[],
            journey={
                "project": JourneyStatus.complete.value,
                "repository": JourneyStatus.pending.value,
                "scenarioCreate": JourneyStatus.pending.value,
                "scenarioList": JourneyStatus.pending.value,
                "testRun": JourneyStatus.pending.value,
            },
            createdAt=now,
            updatedAt=now,
        )
        with self._lock:
            self._projects[project_id] = project
        self._persist_catalog()
        return project

    def create_repository_set(self, project_id: str, name: str) -> RepositorySet:
        project = self.get_project(project_id)
        if not project:
            raise LookupError(f"project not found: {project_id}")
        set_id = f"RS-{uuid4().hex[:12]}"
        repo_set = RepositorySet(id=set_id, projectId=project_id, name=name)
        with self._lock:
            ids = list(project.repositorySetIds or [])
            if set_id not in ids:
                ids.append(set_id)
            self._projects[project_id] = project.model_copy(
                update={"repositorySetId": set_id, "repositorySetIds": ids, "updatedAt": utc_now()}
            )
            self._sets[set_id] = repo_set
        self._persist_catalog()
        return repo_set

    def list_sets_for_project(self, project_id: str) -> list[RepositorySet]:
        project = self.get_project(project_id)
        if not project:
            return []
        ids = list(project.repositorySetIds or [])
        if project.repositorySetId and project.repositorySetId not in ids:
            ids.append(project.repositorySetId)
        out: list[RepositorySet] = []
        with self._lock:
            for sid in ids:
                item = self._sets.get(sid)
                if item:
                    out.append(item)
        return out

    def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        ai_policy: str | None = None,
        model_selection_mode: str | None = None,
        model_bindings: dict[str, str] | None = None,
    ) -> Project | None:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return None
            updates: dict = {}
            if name is not None:
                updates["name"] = name
            if description is not None:
                updates["description"] = description
            if ai_policy is not None:
                updates["aiPolicy"] = ai_policy
            if model_selection_mode is not None:
                updates["modelSelectionMode"] = model_selection_mode
            if model_bindings is not None:
                updates["modelBindings"] = dict(model_bindings)
            if not updates:
                return project
            updates["updatedAt"] = utc_now()
            updated = project.model_copy(update=updates)
            self._projects[project_id] = updated
        self._persist_catalog()
        return updated

    def list_environments(self, project_id: str) -> list[ExecutionEnvironment]:
        with self._lock:
            values = [e for e in self._environments.values() if e.projectId == project_id]
        return sorted(values, key=lambda e: e.updatedAt or e.createdAt, reverse=True)

    def get_environment(self, environment_id: str) -> ExecutionEnvironment | None:
        with self._lock:
            return self._environments.get(environment_id)

    def create_environment(
        self, project_id: str, payload: ExecutionEnvironmentCreate
    ) -> ExecutionEnvironment:
        if not self.get_project(project_id):
            raise LookupError(f"project not found: {project_id}")
        env_id = f"ENV-{uuid4().hex[:12]}"
        now = utc_now()
        env = ExecutionEnvironment(
            id=env_id,
            projectId=project_id,
            name=payload.name,
            frontendBaseUrl=payload.frontendBaseUrl,
            backendBaseUrl=payload.backendBaseUrl,
            healthCheckPath=payload.healthCheckPath or "/",
            apiBasePath=payload.apiBasePath,
            https=bool(payload.https),
            verifyTls=payload.verifyTls,
            proxy=payload.proxy,
            accessNotes=payload.accessNotes,
            testAccountRefKey=payload.testAccountRefKey,
            browser=payload.browser or BrowserEngine.chrome,
            loginId=(payload.loginId or None),
            loginRole=payload.loginRole,
            hasLoginSecret=bool(payload.loginPassword),
            hostAllowlisted=is_host_allowlisted(payload.frontendBaseUrl),
            lastHealthStatus=HealthStatus.unknown,
            createdAt=now,
            updatedAt=now,
        )
        with self._lock:
            self._environments[env_id] = env
            if payload.loginPassword:
                self._env_secrets[env_id] = payload.loginPassword
        self._persist_catalog()
        if payload.loginPassword:
            self._persist_env_secrets()
        return env

    def update_environment(
        self, environment_id: str, payload: ExecutionEnvironmentUpdate
    ) -> ExecutionEnvironment | None:
        env = self.get_environment(environment_id)
        if not env:
            return None
        data = payload.model_dump(exclude_unset=True)
        if "frontendBaseUrl" in data and data["frontendBaseUrl"]:
            data["hostAllowlisted"] = is_host_allowlisted(data["frontendBaseUrl"])
            if data.get("https") is None:
                data["https"] = data["frontendBaseUrl"].startswith("https://")
        secret = payload.loginPassword
        data.pop("loginPassword", None)
        if secret:
            data["hasLoginSecret"] = True
        data["updatedAt"] = utc_now()
        data["version"] = env.version + 1
        updated = env.model_copy(update=data)
        with self._lock:
            self._environments[environment_id] = updated
            if secret:
                self._env_secrets[environment_id] = secret
        self._persist_catalog()
        if secret:
            self._persist_env_secrets()
        return updated

    def get_environment_secret(self, environment_id: str) -> str | None:
        """실행기에만 전달할 연결 비밀번호. 응답·로그에 노출 금지."""
        with self._lock:
            return self._env_secrets.get(environment_id)

    def list_execution_accounts(self, environment_id: str) -> list[ExecutionAccount]:
        with self._lock:
            accounts = [
                account
                for account in self._environment_accounts.values()
                if account.environmentId == environment_id
            ]
            env = self._environments.get(environment_id)
        if env and env.loginId and not any(account.isDefault for account in accounts):
            accounts.append(
                ExecutionAccount(
                    id=f"ACCOUNT-DEFAULT-{environment_id}",
                    environmentId=environment_id,
                    label="실행환경 기본 계정",
                    loginId=env.loginId,
                    role=env.loginRole,
                    hasSecret=env.hasLoginSecret,
                    isDefault=True,
                    createdAt=env.createdAt,
                )
            )
        return sorted(accounts, key=lambda item: (not item.isDefault, item.createdAt))

    def create_execution_account(
        self, environment_id: str, payload: ExecutionAccountCreate
    ) -> ExecutionAccount:
        env = self.get_environment(environment_id)
        if not env:
            raise LookupError(f"environment not found: {environment_id}")
        account_id = f"ACCOUNT-{uuid4().hex[:12]}"
        account = ExecutionAccount(
            id=account_id,
            environmentId=environment_id,
            label=payload.label,
            loginId=payload.loginId,
            role=payload.role,
            hasSecret=True,
            isDefault=payload.isDefault,
        )
        with self._lock:
            if payload.isDefault:
                for key, existing in list(self._environment_accounts.items()):
                    if existing.environmentId == environment_id and existing.isDefault:
                        self._environment_accounts[key] = existing.model_copy(
                            update={"isDefault": False}
                        )
            self._environment_accounts[account_id] = account
            self._env_account_secrets[account_id] = payload.loginPassword
        return account

    def get_execution_account(self, account_id: str) -> ExecutionAccount | None:
        if account_id.startswith("ACCOUNT-DEFAULT-"):
            environment_id = account_id.removeprefix("ACCOUNT-DEFAULT-")
            return next(iter(self.list_execution_accounts(environment_id)), None)
        with self._lock:
            return self._environment_accounts.get(account_id)

    def get_execution_account_secret(self, account_id: str) -> str | None:
        if account_id.startswith("ACCOUNT-DEFAULT-"):
            return self.get_environment_secret(
                account_id.removeprefix("ACCOUNT-DEFAULT-")
            )
        with self._lock:
            return self._env_account_secrets.get(account_id)

    def save_environment(self, env: ExecutionEnvironment) -> ExecutionEnvironment:
        with self._lock:
            self._environments[env.id] = env
        self._persist_catalog()
        return env

    def delete_environment(self, environment_id: str) -> bool:
        with self._lock:
            if environment_id not in self._environments:
                return False
            del self._environments[environment_id]
            had_secret = self._env_secrets.pop(environment_id, None) is not None
            account_ids = [
                aid
                for aid, account in self._environment_accounts.items()
                if account.environmentId == environment_id
            ]
            for account_id in account_ids:
                self._environment_accounts.pop(account_id, None)
                self._env_account_secrets.pop(account_id, None)
        self._persist_catalog()
        if had_secret:
            self._persist_env_secrets()
        return True

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            project = self._projects.pop(project_id, None)
            if not project:
                return False
            ids = list(project.repositorySetIds or [])
            if project.repositorySetId and project.repositorySetId not in ids:
                ids.append(project.repositorySetId)
            for sid in ids:
                self._sets.pop(sid, None)
                self._files.pop(sid, None)
            stale_envs = [eid for eid, e in self._environments.items() if e.projectId == project_id]
            for eid in stale_envs:
                self._environments.pop(eid, None)
                self._env_secrets.pop(eid, None)
                for account_id in [
                    aid
                    for aid, account in self._environment_accounts.items()
                    if account.environmentId == eid
                ]:
                    self._environment_accounts.pop(account_id, None)
                    self._env_account_secrets.pop(account_id, None)
            self._purge_project_artifacts(project_id)
        self._persist_catalog()
        self._persist_env_secrets()
        return True

    def _purge_project_artifacts(self, project_id: str) -> None:
        """프로젝트를 지우면 그 프로젝트의 분석·그래프·시나리오도 함께 내린다.

        남겨두면 분석·테스트 시나리오 목록에 소속 없는 항목이 「연결 저장소」로 떠서
        지표와 목록이 실제와 어긋난다. 호출자는 self._lock을 이미 잡고 있어야 한다.
        """
        for analysis_id in [
            aid for aid, item in self._analyses.items() if item.projectId == project_id
        ]:
            self._analyses.pop(analysis_id, None)
        for graph_id in [
            gid for gid, item in self._graphs.items() if item.projectId == project_id
        ]:
            self._graphs.pop(graph_id, None)
        scenario_ids = {
            sid for sid, item in self._scenarios.items() if item.projectId == project_id
        }
        for scenario_id in scenario_ids:
            self._scenarios.pop(scenario_id, None)
        for contract_id in [
            cid
            for cid, item in self._contracts.items()
            if item.projectId == project_id or item.scenarioId in scenario_ids
        ]:
            self._contracts.pop(contract_id, None)
        for rec_id in [
            rid
            for rid, item in self._recommendations.items()
            if item.projectId == project_id or item.scenarioId in scenario_ids
        ]:
            self._recommendations.pop(rec_id, None)
        for profile_id in [
            pid for pid, item in self._profiles.items() if item.scenarioId in scenario_ids
        ]:
            self._profiles.pop(profile_id, None)
        for run_id in [
            rid for rid, item in self._runs.items() if item.scenarioId in scenario_ids
        ]:
            self._runs.pop(run_id, None)
        for batch_id in [
            bid for bid, item in self._batches.items() if item.projectId == project_id
        ]:
            self._batches.pop(batch_id, None)

    def rename_repository_set(self, set_id: str, name: str) -> RepositorySet | None:
        with self._lock:
            repo_set = self._sets.get(set_id)
            if not repo_set:
                return None
            updated = repo_set.model_copy(update={"name": name})
            self._sets[set_id] = updated
            return updated

    def delete_repository_set(self, set_id: str) -> bool:
        with self._lock:
            repo_set = self._sets.pop(set_id, None)
            if not repo_set:
                return False
            self._files.pop(set_id, None)
            project = self._projects.get(repo_set.projectId)
            if project:
                ids = [i for i in (project.repositorySetIds or []) if i != set_id]
                primary = project.repositorySetId if project.repositorySetId != set_id else (ids[-1] if ids else None)
                self._projects[repo_set.projectId] = project.model_copy(
                    update={"repositorySetIds": ids, "repositorySetId": primary, "updatedAt": utc_now()}
                )
            return True

    def update_repository(
        self,
        set_id: str,
        repository_id: str,
        *,
        url: str | None = None,
        path: str | None = None,
        subdir: str | None = None,
        branch: str | None = None,
        token: str | None = None,
    ) -> RepositorySet | None:
        with self._lock:
            repo_set = self._sets.get(set_id)
            if not repo_set:
                return None
            repos: list[Repository] = []
            found = False
            for repo in repo_set.repositories:
                if repo.id != repository_id:
                    repos.append(repo)
                    continue
                found = True
                updates: dict = {"syncStatus": SyncStatus.pending, "lastError": None}
                if url is not None:
                    updates["url"] = url
                if path is not None:
                    updates["path"] = path
                if subdir is not None:
                    updates["subdir"] = (subdir or "").strip().strip("/") or None
                if branch is not None:
                    updates["branch"] = branch
                if token is not None:
                    if token:
                        self._tokens[repository_id] = token
                        updates["hasCredential"] = True
                    else:
                        self._tokens.pop(repository_id, None)
                        updates["hasCredential"] = False
                repos.append(repo.model_copy(update=updates))
            if not found:
                return None
            updated = repo_set.model_copy(
                update={
                    "repositories": repos,
                    "status": SyncStatus.pending,
                    "journeyStatus": JourneyStatus.pending,
                }
            )
            self._sets[set_id] = updated
            return updated

    def delete_repository(self, set_id: str, repository_id: str) -> RepositorySet | None:
        with self._lock:
            repo_set = self._sets.get(set_id)
            if not repo_set:
                return None
            repos = [r for r in repo_set.repositories if r.id != repository_id]
            if len(repos) == len(repo_set.repositories):
                return None
            self._tokens.pop(repository_id, None)
            updated = repo_set.model_copy(
                update={
                    "repositories": repos,
                    "status": SyncStatus.pending if repos else SyncStatus.pending,
                    "journeyStatus": JourneyStatus.pending,
                }
            )
            self._sets[set_id] = updated
            return updated

    def set_resource_selection(
        self,
        analysis_id: str,
        *,
        excluded_paths: list[str] | None = None,
        selected_paths: list[str] | None = None,
    ) -> dict:
        with self._lock:
            current = dict(self._resource_selections.get(analysis_id) or {})
            if excluded_paths is not None:
                current["excludedPaths"] = list(excluded_paths)
            if selected_paths is not None:
                current["selectedPaths"] = list(selected_paths)
            self._resource_selections[analysis_id] = current
            return current

    def get_resource_selection(self, analysis_id: str) -> dict:
        with self._lock:
            return dict(self._resource_selections.get(analysis_id) or {})

    def save_flow_node_runtime(self, key: str, payload: dict) -> dict:
        with self._lock:
            self._flow_node_runtime[key] = payload
        self._persist_catalog()
        return payload

    def get_flow_node_runtime(self, key: str) -> dict | None:
        with self._lock:
            return self._flow_node_runtime.get(key)

    def list_flow_node_runtime(self, graph_id: str) -> list[dict]:
        with self._lock:
            # Scoped flow ids contain ``::``. Prefix matching made an original graph
            # (IG-x) accidentally absorb records belonging to IG-x::SCN-y.
            return [
                v
                for v in self._flow_node_runtime.values()
                if str(v.get("graphId") or "") == graph_id
            ]

    def update_project_journey(
        self,
        project_id: str,
        repository_status: str | None = None,
        *,
        repository: str | None = None,
        scenario_create: str | None = None,
        scenario_list: str | None = None,
        test_run: str | None = None,
    ) -> None:
        with self._lock:
            project = self._projects.get(project_id)
            if not project:
                return
            journey = dict(project.journey)
            repo_status = repository if repository is not None else repository_status
            if repo_status is not None:
                journey["repository"] = repo_status
            if scenario_create is not None:
                journey["scenarioCreate"] = scenario_create
            if scenario_list is not None:
                journey["scenarioList"] = scenario_list
            if test_run is not None:
                journey["testRun"] = test_run
            self._projects[project_id] = project.model_copy(update={"journey": journey, "updatedAt": utc_now()})

    def get_set(self, set_id: str) -> RepositorySet | None:
        with self._lock:
            return self._sets.get(set_id)

    def get_set_for_project(self, project_id: str) -> RepositorySet | None:
        with self._lock:
            for item in self._sets.values():
                if item.projectId == project_id:
                    return item
        return None

    def save_set(self, repo_set: RepositorySet) -> RepositorySet:
        with self._lock:
            self._sets[repo_set.id] = repo_set
        self._persist_catalog()
        return repo_set

    def add_repository(
        self, set_id: str, repository: Repository, token: str | None = None
    ) -> RepositorySet:
        with self._lock:
            repo_set = self._sets[set_id]
            repos = [r for r in repo_set.repositories if r.role != repository.role]
            repos.append(repository)
            if token:
                self._tokens[repository.id] = token
            elif repository.id in self._tokens:
                del self._tokens[repository.id]
            updated = repo_set.model_copy(
                update={
                    "repositories": repos,
                    "status": SyncStatus.pending,
                    "journeyStatus": JourneyStatus.pending,
                }
            )
            self._sets[set_id] = updated
            return updated

    def get_token(self, repository_id: str) -> str | None:
        with self._lock:
            return self._tokens.get(repository_id)

    def set_files(self, set_id: str, files: list[dict]) -> None:
        with self._lock:
            self._files[set_id] = files

    def get_files(self, set_id: str) -> list[dict]:
        with self._lock:
            return list(self._files.get(set_id, []))

    def get_cached_workspace(self, commit_sha: str) -> str | None:
        with self._lock:
            return self._commit_cache.get(commit_sha)

    def put_cached_workspace(self, commit_sha: str, path: str) -> None:
        with self._lock:
            self._commit_cache[commit_sha] = path

    def append_log(self, set_id: str, message: str) -> None:
        with self._lock:
            repo_set = self._sets[set_id]
            logs = list(repo_set.logs[-99:]) + [f"{utc_now().isoformat()} {message}"]
            self._sets[set_id] = repo_set.model_copy(update={"logs": logs})

    def save_analysis(self, analysis: AnalysisSummary) -> AnalysisSummary:
        with self._lock:
            self._analyses[analysis.id] = analysis
        self._persist_catalog()
        return analysis

    def get_analysis(self, analysis_id: str) -> AnalysisSummary | None:
        with self._lock:
            return self._analyses.get(analysis_id)

    def find_reusable_analysis(
        self,
        *,
        project_id: str,
        role: str,
        repository_set_id: str | None = None,
        commit_sha: str | None = None,
        workspace_path: str | None = None,
    ) -> AnalysisSummary | None:
        """Return latest complete analysis matching project/role/set/commit/workspace."""
        candidates = [
            a
            for a in self.list_analyses(project_id)
            if a.role == role and a.status == "complete"
        ]
        if repository_set_id:
            candidates = [a for a in candidates if a.repositorySetId == repository_set_id]
        if commit_sha:
            matched = [a for a in candidates if (a.commitSha or "") == commit_sha]
            if matched:
                candidates = matched
        if workspace_path:
            wp = str(workspace_path).rstrip("/")
            matched = [
                a
                for a in candidates
                if (a.workspacePath or "").rstrip("/") == wp
            ]
            if matched:
                candidates = matched
        candidates = sorted(candidates, key=lambda a: a.createdAt or "", reverse=True)
        return candidates[0] if candidates else None

    def list_analyses(self, project_id: str | None = None) -> Sequence[AnalysisSummary]:
        with self._lock:
            values = list(self._analyses.values())
        if project_id:
            values = [a for a in values if a.projectId == project_id]
        return sorted(values, key=lambda analysis: analysis.createdAt or "", reverse=True)

    def delete_analysis(self, analysis_id: str) -> bool:
        with self._lock:
            if analysis_id not in self._analyses:
                return False
            del self._analyses[analysis_id]
            self._resource_selections.pop(analysis_id, None)
        self._persist_catalog()
        return True

    def delete_analyses(self, analysis_ids: list[str]) -> int:
        removed = 0
        for analysis_id in analysis_ids:
            with self._lock:
                if analysis_id not in self._analyses:
                    continue
                del self._analyses[analysis_id]
                self._resource_selections.pop(analysis_id, None)
                removed += 1
        if removed:
            self._persist_catalog()
        return removed

    def save_mapping_set(self, item: MappingSetSummary) -> MappingSetSummary:
        with self._lock:
            self._mapping_sets[item.mappingSetId] = item
        return item

    def get_mapping_set(self, mapping_set_id: str) -> MappingSetSummary | None:
        with self._lock:
            return self._mapping_sets.get(mapping_set_id)

    def list_mapping_sets(self, project_id: str | None = None) -> Sequence[MappingSetSummary]:
        with self._lock:
            values = list(self._mapping_sets.values())
        if project_id:
            values = [m for m in values if m.projectId == project_id]
        return sorted(values, key=lambda mapping: mapping.createdAt or "", reverse=True)

    def patch_mapping(
        self,
        mapping_id: str,
        *,
        status: str,
        note: str | None = None,
        backend_endpoint_id: str | None = None,
    ) -> dict | None:
        with self._lock:
            for set_id, mapping_set in self._mapping_sets.items():
                mappings = list(mapping_set.mappings)
                for index, mapping in enumerate(mappings):
                    if mapping.get("mappingId") != mapping_id:
                        continue
                    updated = dict(mapping)
                    updated["status"] = status
                    if backend_endpoint_id is not None:
                        updated["backendEndpointId"] = backend_endpoint_id
                    trail = list(updated.get("auditTrail") or [])
                    trail.append(
                        {
                            "at": utc_now().isoformat(),
                            "action": "manual_patch",
                            "status": status,
                            "note": note,
                            "backendEndpointId": backend_endpoint_id,
                        }
                    )
                    updated["auditTrail"] = trail
                    mappings[index] = updated
                    result = dict(mapping_set.result or {})
                    result["mappings"] = mappings
                    self._mapping_sets[set_id] = mapping_set.model_copy(
                        update={"mappings": mappings, "result": result}
                    )
                    return updated
        return None

    def save_graph(self, item: InteractionGraphSummary) -> InteractionGraphSummary:
        with self._lock:
            self._graphs[item.graphId] = item
        self._persist_catalog()
        return item

    def get_graph(self, graph_id: str) -> InteractionGraphSummary | None:
        with self._lock:
            return self._graphs.get(graph_id)

    def list_graphs(self, project_id: str | None = None) -> Sequence[InteractionGraphSummary]:
        with self._lock:
            values = list(self._graphs.values())
        if project_id:
            values = [g for g in values if g.projectId == project_id]
        return sorted(values, key=lambda graph: graph.createdAt or "", reverse=True)

    def delete_graph(self, graph_id: str) -> bool:
        with self._lock:
            if graph_id not in self._graphs:
                return False
            del self._graphs[graph_id]
            # Drop node runtime keys for this graph
            drop = [k for k in self._flow_node_runtime if k.startswith(f"{graph_id}:")]
            for k in drop:
                del self._flow_node_runtime[k]
        self._persist_catalog()
        return True

    def delete_graphs(self, graph_ids: list[str]) -> int:
        removed = 0
        for gid in graph_ids:
            if self.delete_graph(gid):
                removed += 1
        return removed

    def save_scenario(self, item: ScenarioSummary) -> ScenarioSummary:
        with self._lock:
            self._scenarios[item.scenarioId] = item
        self._persist_catalog()
        return item

    def delete_scenario(self, scenario_id: str) -> bool:
        with self._lock:
            if scenario_id not in self._scenarios:
                return False
            del self._scenarios[scenario_id]
        self._persist_catalog()
        return True

    def delete_scenarios(self, scenario_ids: list[str]) -> int:
        removed = 0
        for scenario_id in scenario_ids:
            if self.delete_scenario(scenario_id):
                removed += 1
        return removed

    def get_scenario(self, scenario_id: str) -> ScenarioSummary | None:
        with self._lock:
            return self._scenarios.get(scenario_id)

    def list_scenarios(
        self,
        project_id: str | None = None,
        service_id: str | None = None,
    ) -> Sequence[ScenarioSummary]:
        with self._lock:
            values = list(self._scenarios.values())
        if project_id:
            values = [s for s in values if s.projectId == project_id]
        if service_id:
            values = [s for s in values if s.serviceId == service_id]
        return sorted(values, key=lambda scenario: scenario.createdAt or "", reverse=True)

    def save_contract(self, item: ComponentContractSummary) -> ComponentContractSummary:
        with self._lock:
            self._contracts[item.contractId] = item
        self._persist_catalog()
        return item

    def get_contract(self, contract_id: str) -> ComponentContractSummary | None:
        with self._lock:
            return self._contracts.get(contract_id)

    def get_contract_by_scenario(self, scenario_id: str) -> ComponentContractSummary | None:
        with self._lock:
            matches = [c for c in self._contracts.values() if c.scenarioId == scenario_id]
        matches = sorted(matches, key=lambda c: c.createdAt or "", reverse=True)
        return matches[0] if matches else None

    def save_recommendation(self, item: RecommendationSummary) -> RecommendationSummary:
        with self._lock:
            self._recommendations[item.recommendationId] = item
        self._persist_catalog()
        return item

    def get_recommendation(self, recommendation_id: str) -> RecommendationSummary | None:
        with self._lock:
            return self._recommendations.get(recommendation_id)

    def get_recommendation_by_scenario(self, scenario_id: str) -> RecommendationSummary | None:
        with self._lock:
            matches = [r for r in self._recommendations.values() if r.scenarioId == scenario_id]
        matches = sorted(matches, key=lambda r: r.createdAt or "", reverse=True)
        return matches[0] if matches else None

    def save_profile(self, item: InputProfileSummary) -> InputProfileSummary:
        with self._lock:
            self._profiles[item.profileId] = item
        self._persist_catalog()
        return item

    def get_profile(self, profile_id: str) -> InputProfileSummary | None:
        with self._lock:
            return self._profiles.get(profile_id)

    def list_profiles(self, scenario_id: str | None = None) -> Sequence[InputProfileSummary]:
        with self._lock:
            values = list(self._profiles.values())
        if scenario_id:
            values = [p for p in values if p.scenarioId == scenario_id]
        return sorted(values, key=lambda p: p.createdAt or "", reverse=True)

    def save_run(self, item: RunSummary) -> RunSummary:
        with self._lock:
            self._runs[item.runId] = item
        self._persist_catalog()
        return item

    def get_run(self, run_id: str) -> RunSummary | None:
        with self._lock:
            return self._runs.get(run_id)

    def delete_run(self, run_id: str) -> bool:
        """실행 이력 1건 삭제 — 텔레메트리 이벤트도 같이 지운다 (증적 파일은 보존)."""
        with self._lock:
            if run_id not in self._runs:
                return False
            del self._runs[run_id]
            self._backend_events.pop(run_id, None)
            self._backend_seq.pop(run_id, None)
        self._persist_catalog()
        return True

    def delete_runs(self, run_ids: list[str]) -> int:
        removed = 0
        for run_id in run_ids:
            if self.delete_run(run_id):
                removed += 1
        return removed

    def list_runs(self, scenario_id: str | None = None) -> Sequence[RunSummary]:
        with self._lock:
            values = list(self._runs.values())
        if scenario_id:
            values = [r for r in values if r.scenarioId == scenario_id]
        return sorted(values, key=lambda r: r.createdAt or "", reverse=True)

    def save_batch(self, item: BatchDefinition) -> BatchDefinition:
        with self._lock:
            self._batches[item.batchId] = item
        self._persist_catalog()
        return item

    def get_batch(self, batch_id: str) -> BatchDefinition | None:
        with self._lock:
            return self._batches.get(batch_id)

    def list_batches(self, project_id: str | None = None) -> Sequence[BatchDefinition]:
        with self._lock:
            values = list(self._batches.values())
        if project_id:
            values = [batch for batch in values if batch.projectId == project_id]
        return sorted(values, key=lambda batch: batch.createdAt, reverse=True)

    def append_backend_event(self, event: BackendTelemetryEvent) -> int:
        """Append event; assign requestSequence for duplicates/retries. Returns sequence."""
        with self._lock:
            run_id = event.testRunId
            bucket = self._backend_events.setdefault(run_id, [])
            if event.event == "request_received" or int(event.requestSequence or 0) <= 0:
                if event.event == "request_received":
                    seq = self._backend_seq.get(run_id, 0) + 1
                    self._backend_seq[run_id] = seq
                else:
                    seq = self._backend_seq.get(run_id, 1) or 1
            else:
                seq = int(event.requestSequence)
                self._backend_seq[run_id] = max(self._backend_seq.get(run_id, 0), seq)
            stored = event.model_copy(update={"requestSequence": seq})
            bucket.append(stored)
        self._persist_catalog()
        return seq

    def replace_last_backend_event(self, run_id: str, event: BackendTelemetryEvent) -> None:
        with self._lock:
            bucket = self._backend_events.get(run_id) or []
            if not bucket:
                self._backend_events.setdefault(run_id, []).append(event)
            else:
                bucket[-1] = event
        self._persist_catalog()

    def list_backend_events(self, run_id: str) -> Sequence[BackendTelemetryEvent]:
        with self._lock:
            return list(self._backend_events.get(run_id) or [])

    def save_binding_result(
        self, result: BindingValidationResult
    ) -> BindingValidationResult:
        with self._lock:
            self._binding_results[result.runId] = result
        self._persist_catalog()
        return result

    def get_binding_result(self, run_id: str) -> BindingValidationResult | None:
        with self._lock:
            return self._binding_results.get(run_id)

    def save_evidence_manifest(self, manifest: EvidenceManifest) -> EvidenceManifest:
        with self._lock:
            self._evidence_manifests[manifest.evidenceId] = manifest
        self._persist_catalog()
        return manifest

    def get_evidence_manifest(self, evidence_id: str) -> EvidenceManifest | None:
        with self._lock:
            return self._evidence_manifests.get(evidence_id)

    def get_evidence_manifest_by_run(self, run_id: str) -> EvidenceManifest | None:
        with self._lock:
            return next(
                (
                    manifest
                    for manifest in self._evidence_manifests.values()
                    if manifest.runId == run_id
                ),
                None,
            )

    def list_evidence_manifests(self) -> Sequence[EvidenceManifest]:
        with self._lock:
            return list(self._evidence_manifests.values())

    def delete_evidence_manifest(self, evidence_id: str) -> None:
        with self._lock:
            self._evidence_manifests.pop(evidence_id, None)
        self._persist_catalog()

    def find_graph_by_service(
        self, service_id: str, project_id: str | None = None
    ) -> InteractionGraphSummary | None:
        scenarios = list(self.list_scenarios(project_id=project_id, service_id=service_id))
        scenarios = sorted(scenarios, key=lambda s: s.createdAt or "", reverse=True)
        for scn in scenarios:
            if scn.graphId:
                graph = self.get_graph(scn.graphId)
                if graph:
                    return graph
        # fallback: latest graph for project
        graphs = list(self.list_graphs(project_id))
        graphs = sorted(graphs, key=lambda g: g.createdAt or "", reverse=True)
        return graphs[0] if graphs else None
