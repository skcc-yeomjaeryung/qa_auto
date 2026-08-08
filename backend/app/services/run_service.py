from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_EVIDENCE, REPO_ROOT
from app.services.environment_service import EnvironmentService
from app.services.binding_validation import BindingValidationService
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.run_models import RunCreateRequest, RunStepSummary, RunSummary
from app.services.telemetry.masking import sanitize_headers
from app.services.telemetry.service import TelemetryService
from app.schemas.binding_validation import BindingValidateRequest
from app.schemas.telemetry import BackendTelemetryEvent, BackendTelemetryIngestRequest
from app.skills.browser_execute.script.execute_run import execute_scenario, resolve_dsl_steps

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"WAITING_FOR_REVIEW", "AUTO_FAILED", "CANCELLED"}
ACTIVE_STATUSES = {"QUEUED", "PREPARING", "RUNNING"}


class StaleVersionError(RuntimeError):
    """화면이 본 시나리오·Input Profile 버전이 현재 저장 버전과 다를 때."""

    def __init__(self, message: str, *, expected: str, actual: str) -> None:
        super().__init__(message)
        self.expected = expected
        self.actual = actual


class BrowserRunService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store
        self.env_service = EnvironmentService(store)

    def _repo_meta(self, project_id: str | None) -> dict[str, str | None]:
        if not project_id:
            return {"repositoryUrl": None, "branch": None, "commitSha": None}
        repo_set = self.store.get_set_for_project(project_id)
        if not repo_set or not repo_set.repositories:
            return {"repositoryUrl": None, "branch": None, "commitSha": None}
        repo = next(
            (r for r in repo_set.repositories if r.role.value == "workspace"),
            repo_set.repositories[0],
        )
        return {
            "repositoryUrl": repo.url or repo.path,
            "branch": repo.branch,
            "commitSha": repo.commitSha,
        }

    def _resolve_inputs(
        self, scenario_id: str, payload: RunCreateRequest
    ) -> tuple[dict, str | None, str | None]:
        """추천 → 프로필 → 이전 실행 → override 순으로 입력을 확정한다."""
        inputs: dict = {}
        profile_id = payload.inputProfileId
        profile_version: str | None = None

        if payload.reuseFromRunId:
            previous = self.store.get_run(payload.reuseFromRunId)
            if not previous:
                raise LookupError(f"run not found: {payload.reuseFromRunId}")
            if previous.scenarioId != scenario_id:
                raise RuntimeError("재사용 대상 실행이 다른 시나리오입니다")
            inputs = dict(previous.inputs or {})
            profile_id = profile_id or previous.inputProfileId

        if not inputs:
            inputs = dict(payload.inputs or {})

        if profile_id:
            profile = self.store.get_profile(profile_id)
            if profile:
                profile_version = profile.version
                if not inputs and profile.result:
                    cases = profile.result.get("cases") or []
                    if cases:
                        inputs = dict(cases[0].get("inputs") or {})
        if not inputs:
            rec = self.store.get_recommendation_by_scenario(scenario_id)
            if rec and rec.result:
                inputs = dict(rec.result.get("defaults") or {})
        if not inputs:
            scenario = self.store.get_scenario(scenario_id)
            if scenario and isinstance(scenario.result, dict):
                inputs = dict(scenario.result.get("inputDefaults") or {})
        # 사용자 수정값은 항상 마지막에 덮어쓴다
        inputs.update(dict(payload.overrides or {}))
        scenario = self.store.get_scenario(scenario_id)
        if scenario and scenario.serviceId == "customer-search" and "customerId" not in inputs:
            inputs["customerId"] = "CUS-1001"
        return inputs, profile_id, profile_version

    def _assert_fresh_versions(
        self, scenario, payload: RunCreateRequest, profile_id: str | None
    ) -> None:
        current = str(scenario.version or "1")
        if payload.scenarioVersion and str(payload.scenarioVersion) != current:
            raise StaleVersionError(
                f"시나리오 버전이 변경되었습니다 (화면 {payload.scenarioVersion} · 현재 {current}). 새로고침 후 다시 실행하세요.",
                expected=current,
                actual=str(payload.scenarioVersion),
            )
        if payload.inputProfileVersion and profile_id:
            profile = self.store.get_profile(profile_id)
            actual = str(profile.version) if profile else "missing_data"
            if str(payload.inputProfileVersion) != actual:
                raise StaleVersionError(
                    f"Input Profile 버전이 변경되었습니다 (화면 {payload.inputProfileVersion} · 현재 {actual}). 새로고침 후 다시 실행하세요.",
                    expected=actual,
                    actual=str(payload.inputProfileVersion),
                )

    def start_run(self, scenario_id: str, payload: RunCreateRequest | None = None) -> RunSummary:
        payload = payload or RunCreateRequest()
        # Console policy: agent-browser consent is always granted by platform (no user toggle).
        payload = payload.model_copy(update={"consent": True})
        scenario = self.store.get_scenario(scenario_id)
        if not scenario:
            raise LookupError(f"scenario not found: {scenario_id}")

        base_url, env = self.env_service.resolve_base_url(
            environment_id=payload.environmentId,
            project_id=scenario.projectId,
            explicit_base_url=payload.baseUrl,
        )
        repo_meta = self._repo_meta(scenario.projectId)
        # 연결 계정·브라우저 — 프로젝트 환경에 등록된 값만 사용한다 (없으면 missing_data)
        connection = self._connection(env, payload.executionAccountId)
        environment_allows_mutation = bool(
            getattr(env, "dataMutationAllowed", False)
        )
        allow_destructive = bool(payload.allowDestructive) or environment_allows_mutation
        mutation_policy_source = (
            "environment"
            if environment_allows_mutation
            else "one_time_confirmation"
            if payload.allowDestructive
            else "default_block"
        )

        inputs, input_profile_id, input_profile_version = self._resolve_inputs(
            scenario_id, payload
        )
        self._assert_fresh_versions(scenario, payload, input_profile_id)

        run_id = f"RUN-{uuid4().hex[:12]}"
        evidence_dir = ARTIFACTS_EVIDENCE / "runs" / run_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        test_case_id = f"TC-{run_id[-8:]}"
        planned = self._planned_steps(scenario.result or {})
        queued = RunSummary(
            runId=run_id,
            scenarioId=scenario_id,
            projectId=scenario.projectId,
            serviceId=scenario.serviceId,
            status="PREPARING",
            consent=True,
            baseUrl=base_url,
            environmentId=env.id if env else payload.environmentId,
            executionAccountId=payload.executionAccountId,
            executionAccountRole=connection.get("role"),
            testCaseId=test_case_id,
            inputProfileId=input_profile_id,
            backendTraceStatus="pending",
            partialEvidence=False,
            environmentName=env.name if env else None,
            repositoryUrl=repo_meta["repositoryUrl"],
            branch=repo_meta["branch"],
            commitSha=repo_meta["commitSha"],
            inputs=inputs,
            evidenceDir=str(evidence_dir),
            mode="interactive" if payload.mode == "interactive" else "batch",
            scenarioVersion=str(scenario.version or "1"),
            inputProfileVersion=input_profile_version,
            overrides=dict(payload.overrides or {}),
            reusedFromRunId=payload.reuseFromRunId,
            plannedStepCount=len(planned),
            steps=planned,
            createdAt=utc_now().isoformat(),
            updatedAt=utc_now().isoformat(),
        )
        self.store.save_run(queued)

        headers = sanitize_headers(
            {
                "X-Test-Run-ID": run_id,
                "X-Scenario-ID": scenario_id,
                "X-Scenario-Version": str(scenario.version or "1"),
                "X-Test-Case-ID": test_case_id,
                **(
                    {"X-Input-Profile-ID": input_profile_id}
                    if input_profile_id
                    else {}
                ),
                **dict(payload.headers or {}),
            }
        )

        running = queued.model_copy(update={"status": "RUNNING", "updatedAt": utc_now().isoformat()})
        self.store.save_run(running)

        if payload.mode == "interactive":
            # Console이 즉시 Step Timeline을 그릴 수 있도록 실행은 백그라운드로 넘긴다.
            thread = threading.Thread(
                target=self._execute_and_persist,
                args=(
                    running,
                    scenario,
                    inputs,
                    base_url,
                    headers,
                    payload.headed,
                    connection,
                    allow_destructive,
                    mutation_policy_source,
                ),
                name=f"run-{run_id}",
                daemon=True,
            )
            thread.start()
            return self.store.get_run(run_id) or running

        return self._execute_and_persist(
            running,
            scenario,
            inputs,
            base_url,
            headers,
            payload.headed,
            connection,
            allow_destructive,
            mutation_policy_source,
        )

    def _connection(self, env, execution_account_id: str | None = None) -> dict[str, Any]:
        """환경에 등록된 연결 브라우저·계정. 비밀번호는 실행기 전달용으로만 읽는다."""
        if not env:
            return {"browser": "chrome", "loginId": None, "loginPassword": None, "role": None}
        if execution_account_id:
            account = self.store.get_execution_account(execution_account_id)
            if not account or account.environmentId != env.id:
                raise ValueError("선택한 실행 계정이 실행환경에 속하지 않습니다")
            return {
                "browser": str(getattr(getattr(env, "browser", None), "value", env.browser) or "chrome"),
                "loginId": account.loginId,
                "loginPassword": self.store.get_execution_account_secret(account.id),
                "role": account.role,
            }
        secret = None
        getter = getattr(self.store, "get_environment_secret", None)
        if callable(getter):
            secret = getter(env.id)
        browser = getattr(env, "browser", None)
        return {
            "browser": str(getattr(browser, "value", browser) or "chrome"),
            "loginId": getattr(env, "loginId", None),
            "loginPassword": secret,
            "role": getattr(env, "loginRole", None),
        }

    def _execute_and_persist(
        self,
        running: RunSummary,
        scenario,
        inputs: dict,
        base_url: str,
        headers: dict[str, str],
        headed: bool,
        connection: dict[str, Any] | None = None,
        allow_destructive: bool = False,
        mutation_policy_source: str = "default_block",
    ) -> RunSummary:
        run_id = running.runId
        evidence_dir = Path(running.evidenceDir or (ARTIFACTS_EVIDENCE / "runs" / run_id))
        progress_path = self._progress_path(running)
        scenario_body = {
            **dict(scenario.result or {}),
            "runPolicy": {
                "allowDestructive": bool(allow_destructive),
                "source": mutation_policy_source,
                "environmentId": running.environmentId,
            },
        }
        try:
            response = PlatformRunnerAdapter().execute(
                "wf_browser_execute",
                {
                    "projectId": running.projectId,
                    "runId": run_id,
                    "scenarioId": running.scenarioId,
                    "scenario": scenario_body,
                    "inputs": inputs,
                    "consent": True,
                    "baseUrl": base_url,
                    "headed": headed,
                    "headers": headers,
                    "connection": connection or {},
                    "evidenceDir": str(evidence_dir.resolve()),
                    "progressPath": str(progress_path.resolve()) if progress_path else None,
                    "artifactPath": str((evidence_dir / "skill-output.json").resolve()),
                },
            )

            result: dict = {}
            if response.status == "complete" and response.stepResults:
                output = response.stepResults[0].get("output") or {}
                if output.get("result"):
                    result = output["result"]
                    result["agentTraceId"] = response.plan.planId

            if not result:
                result = execute_scenario(
                    scenario=scenario_body,
                    inputs=inputs,
                    base_url=base_url,
                    run_id=run_id,
                    consent=True,
                    evidence_dir=evidence_dir,
                    headers=headers,
                    headed=headed,
                    progress_path=progress_path,
                    connection=connection or {},
                )
        except Exception as exc:  # noqa: BLE001 — 실행 실패도 관측 재료로 남긴다
            logger.exception("browser run failed run=%s", run_id)
            result = {
                "status": "AUTO_FAILED",
                "runId": run_id,
                "steps": [],
                "missing_data": ["execution_error"],
                "observationSummary": f"실행 중 오류 관측: {exc}",
                "evidenceDir": str(evidence_dir),
            }

        persisted = self._persist_result(running, result)
        # External targets cannot expose internal controller logs.  The actual
        # agent-browser request/status is still structured evidence, but is labelled
        # external_network_only so it is never confused with internal instrumentation.
        try:
            telemetry = TelemetryService(self.store)
            observed = self._ingest_browser_network(persisted)
            expects_backend = any(
                str(step.get("action") or "") in {"wait_for_response", "verify_response"}
                for step in (scenario_body.get("steps") or [])
                if isinstance(step, dict)
            )
            if observed:
                telemetry.ingest(BackendTelemetryIngestRequest(events=observed))
                telemetry.mark_external_network_only(persisted.runId)
            elif expects_backend:
                telemetry.await_backend_logs(persisted.runId)
            else:
                telemetry.mark_backend_not_required(persisted.runId)
        except Exception:  # noqa: BLE001
            logger.exception("backend log await failed run=%s", persisted.runId)
        try:
            latest = self.store.get_run(persisted.runId) or persisted
            BindingValidationService(self.store).validate(
                persisted.runId,
                BindingValidateRequest(
                    currentRoute=str((latest.result or {}).get("currentUrl") or "") or None,
                ),
            )
        except Exception:  # noqa: BLE001 — 검증 부재는 Evidence missing_data로 남긴다
            logger.exception("binding auto validation failed run=%s", persisted.runId)
        return self.store.get_run(persisted.runId) or persisted

    @staticmethod
    def _ingest_browser_network(run: RunSummary) -> list[BackendTelemetryEvent]:
        events: list[BackendTelemetryEvent] = []
        rows = [
            row
            for row in ((run.result or {}).get("matchedNetworkRequests") or [])
            if isinstance(row, dict) and row.get("expectedRequest")
        ]
        for sequence, row in enumerate(rows, start=1):
            timestamp = str(row.get("timestamp") or run.updatedAt or utc_now().isoformat())
            common = {
                "timestamp": timestamp,
                "testRunId": run.runId,
                "scenarioId": run.scenarioId,
                "scenarioVersion": run.scenarioVersion,
                "testCaseId": run.testCaseId,
                "inputProfileId": run.inputProfileId,
                "requestSequence": sequence,
                "httpMethod": str(row.get("method") or "") or None,
                "path": str(row.get("path") or "") or None,
                "source": "browser_network",
                "constraint": "external_target_network_only",
            }
            events.append(
                BackendTelemetryEvent(
                    **common,
                    event="request_received",
                    request={
                        "method": row.get("method"),
                        "path": row.get("path"),
                        "headers": dict(row.get("requestHeaders") or {}),
                        "networkId": row.get("networkId"),
                    },
                )
            )
            events.append(
                BackendTelemetryEvent(
                    **common,
                    event="response_returned",
                    response={
                        "status": row.get("status")
                        if isinstance(row.get("status"), int)
                        else row.get("effectiveStatus"),
                        "mimeType": row.get("mimeType"),
                        "headers": dict(row.get("responseHeaders") or {}),
                        "networkId": row.get("networkId"),
                        "statusBasis": row.get("statusBasis"),
                        "redirectUrl": row.get("redirectUrl"),
                    },
                    status=(
                        row.get("status")
                        if isinstance(row.get("status"), int)
                        else row.get("effectiveStatus")
                        if isinstance(row.get("effectiveStatus"), int)
                        else None
                    ),
                )
            )
        return events

    def _progress_path(self, run: RunSummary) -> Path | None:
        if not run.evidenceDir:
            return None
        return Path(run.evidenceDir) / "progress.json"

    def _planned_steps(self, scenario_body: dict) -> list[RunStepSummary]:
        """실행 전에도 스텝 목록을 보여주기 위한 queued step seed."""
        planned = [
            RunStepSummary(
                stepId="H0", action="set_headers", status="queued", observationSummary="추적 헤더 준비"
            )
        ]
        for idx, step in enumerate(resolve_dsl_steps(scenario_body)):
            planned.append(
                RunStepSummary(
                    stepId=str(step.get("id") or f"S{idx + 1}"),
                    action=str(step.get("action") or ""),
                    status="queued",
                )
            )
        return planned

    def get_run(self, run_id: str) -> RunSummary | None:
        item = self.store.get_run(run_id)
        if not item:
            return None
        if item.status not in ACTIVE_STATUSES:
            return _normalize_derived_outcome(item)
        return self._merge_live_progress(item)

    def _merge_live_progress(self, run: RunSummary) -> RunSummary:
        """실행 중에는 progress.json의 관측 step을 queued seed 위에 덮어 보여준다."""
        progress_path = self._progress_path(run)
        if not progress_path or not progress_path.is_file():
            return run
        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return run
        observed = [
            RunStepSummary.model_validate(
                {
                    "stepId": str(s.get("stepId") or ""),
                    "action": str(s.get("action") or ""),
                    "mcpTool": s.get("mcpTool"),
                    "refOrLocator": s.get("refOrLocator"),
                    "status": str(s.get("status") or "queued"),
                    "startedAt": s.get("startedAt"),
                    "endedAt": s.get("endedAt"),
                    "snapshotPath": s.get("snapshotPath"),
                    "screenshotPath": s.get("screenshotPath"),
                    "networkRefs": list(s.get("networkRefs") or []),
                    "observationSummary": s.get("observationSummary"),
                    "missingData": list(s.get("missingData") or []),
                }
            )
            for s in (payload.get("steps") or [])
        ]
        if not observed:
            return run
        merged: list[RunStepSummary] = []
        seen = {step.stepId for step in observed}
        merged.extend(observed)
        for step in run.steps:
            if step.stepId not in seen:
                merged.append(step)
        total = max(int(payload.get("plannedTotal") or 0), run.plannedStepCount, len(merged))
        percent = int(round(len(observed) / total * 100)) if total else 0
        return run.model_copy(
            update={
                "steps": merged,
                "plannedStepCount": total,
                "progressPercent": min(percent, 99),
                "currentStepId": next(
                    (s.stepId for s in merged if s.status == "queued"), None
                ),
                "failedStepId": next(
                    (s.stepId for s in observed if s.status == "error"), None
                ),
            }
        )

    def list_steps(self, run_id: str) -> list[RunStepSummary]:
        item = self.get_run(run_id)
        if not item:
            raise LookupError(f"run not found: {run_id}")
        return list(item.steps)

    def cancel_run(self, run_id: str) -> RunSummary:
        item = self.store.get_run(run_id)
        if not item:
            raise LookupError(f"run not found: {run_id}")
        if item.status in TERMINAL_STATUSES:
            raise RuntimeError(f"이미 종료된 실행입니다 (상태 {item.status})")
        if item.evidenceDir:
            flag = Path(item.evidenceDir) / "CANCEL"
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("1", encoding="utf-8")
        updated = item.model_copy(
            update={
                "status": "CANCELLED",
                "updatedAt": utc_now().isoformat(),
                "observationSummary": "취소 요청됨 (관측만 · Pass/Fail 단정 없음)",
            }
        )
        return self.store.save_run(updated)

    def list_runs(self, scenario_id: str | None = None) -> list[RunSummary]:
        # 과거 실행도 현재의 보수적 판정 규칙으로 표시한다. 원본 증적은 바꾸지
        # 않고, verdict에서 파생되는 기술 상태·관측 분류만 응답 시 재계산한다.
        return [
            _normalize_derived_outcome(item)
            for item in self.store.list_runs(scenario_id=scenario_id)
        ]

    def delete_many(self, run_ids: list[str]) -> dict:
        """실행 이력 일괄 삭제 — 목록 정리용. 증적 파일은 지우지 않는다."""
        if not run_ids:
            raise ValueError("runIds required")
        removed = self.store.delete_runs(run_ids)
        return {
            "status": "complete" if removed == len(run_ids) else "partial",
            "removed": removed,
            "requested": len(run_ids),
            "message": f"실행 이력 {removed}건을 목록에서 삭제했습니다.",
        }

    def _persist_result(self, base: RunSummary, result: dict) -> RunSummary:
        steps = [
            RunStepSummary(
                stepId=str(s.get("stepId") or s.get("step_id") or ""),
                action=str(s.get("action") or ""),
                mcpTool=s.get("mcpTool") or s.get("mcp_tool"),
                refOrLocator=s.get("refOrLocator") or s.get("ref_or_locator"),
                status=str(s.get("status") or ""),
                startedAt=s.get("startedAt") or s.get("started_at"),
                endedAt=s.get("endedAt") or s.get("ended_at"),
                snapshotPath=s.get("snapshotPath") or s.get("snapshot_path"),
                screenshotPath=s.get("screenshotPath") or s.get("screenshot_path"),
                networkRefs=list(s.get("networkRefs") or s.get("network_refs") or []),
                observationSummary=s.get("observationSummary") or s.get("observation_summary"),
                missingData=list(s.get("missingData") or s.get("missing_data") or []),
            )
            for s in (result.get("steps") or [])
        ]
        status = str(result.get("status") or "AUTO_FAILED")
        # technical complete never equals HITL pass — force review wait on soft success
        if status == "AUTO_PASSED":
            status = "WAITING_FOR_REVIEW"
        # 취소 요청이 실행 도중 들어왔다면 취소 상태를 유지한다
        current = self.store.get_run(base.runId)
        if current and current.status == "CANCELLED":
            status = "CANCELLED"
        outcome_kind, outcome_summary = _classify_run_outcome(status, result)
        failed_step = next((s.stepId for s in steps if s.status == "error"), None)
        # 실행 데이터 요약 — LLM이 관측만 설명한다 (미가동이면 결정론 문장)
        narrative, narrative_mode, diagnosis = summarize_run_observation(
            scenario_name=base.scenarioId,
            status=status,
            steps=[s.model_dump() for s in steps],
            bindings=list(result.get("inputBindings") or []),
            missing=list(result.get("missing_data") or []),
            verdict=result.get("verdict") if isinstance(result.get("verdict"), dict) else None,
            session_policy=str(result.get("sessionPolicy") or ""),
        )
        result = {
            **result,
            "runNarrative": narrative,
            "runNarrativeMode": narrative_mode,
            "runDiagnosis": diagnosis,
        }
        updated = base.model_copy(
            update={
                "status": status,
                "plannedStepCount": max(base.plannedStepCount, len(steps)),
                "progressPercent": 100 if status != "CANCELLED" else base.progressPercent,
                "currentStepId": None,
                "failedStepId": failed_step,
                "screenshotCount": len(result.get("screenshots") or []),
                "snapshotCount": len(result.get("snapshots") or []),
                "missingData": list(result.get("missing_data") or []),
                "observationSummary": result.get("observationSummary"),
                "outcomeKind": outcome_kind,
                "outcomeSummary": outcome_summary,
                "evidenceDir": result.get("evidenceDir") or base.evidenceDir,
                "updatedAt": utc_now().isoformat(),
                "steps": steps,
                "result": result,
                "browserRunner": str(result.get("browserRunner") or "agent-browser-cli"),
            }
        )
        return self.store.save_run(updated)


STATUS_KO = {
    "WAITING_FOR_REVIEW": "기술 실행 완료 · 검토 대기",
    "AUTO_FAILED": "자동 실행 실패",
    "CANCELLED": "실행 취소",
}

# 기대 결과 대조 판정 표기 (D-015) — 합격 확정 표현은 쓰지 않는다
VERDICT_KO = {
    "expected_met": "기대한 결과를 관측",
    "expected_not_met": "기대와 다르게 관측",
    "undetermined": "판정 불가",
}


def summarize_run_observation(
    *,
    scenario_name: str,
    status: str,
    steps: list[dict],
    bindings: list[dict],
    missing: list[str],
    verdict: dict | None = None,
    session_policy: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """실행 결과를 사람이 읽는 한국어 관측 요약으로 만든다. (llm | deterministic)"""
    facts = {
        "scenario": scenario_name,
        "status": status,
        # 기대 결과 대조 판정이 요약의 1순위 재료다 (D-015)
        "verdict": verdict or {},
        "sessionPolicy": session_policy or "",
        "steps": [
            {
                "stepId": s.get("stepId"),
                "action": s.get("action"),
                "status": s.get("status"),
                "observation": s.get("observationSummary"),
            }
            for s in steps
        ],
        "inputBindings": [
            {"field": b.get("field"), "value": b.get("value"), "source": b.get("source")}
            for b in bindings
        ],
        "missingData": missing,
    }
    diagnosis = _build_run_diagnosis(
        status,
        {
            "verdict": verdict or {},
            "steps": steps,
            "missing_data": missing,
            "observationSummary": str((verdict or {}).get("reason") or ""),
        },
    )
    try:
        from app.core.llm.llm_client import get_llm_client
        from app.core.prompts import PromptCatalog

        system, _ = PromptCatalog().render_system("run/summarize_run_system.md")
        if system:
            parsed = get_llm_client().chat_json(
                system=system, user=json.dumps(facts, ensure_ascii=False), timeout_s=25.0
            )
            text = str((parsed or {}).get("summary") or "").strip()
            if text:
                diagnosis = _merge_llm_diagnosis(diagnosis, (parsed or {}).get("diagnosis"))
                return text[:600], "llm", diagnosis
    except Exception:  # noqa: BLE001 — LLM 미가동 시 결정론 문장으로 대체
        logger.info("run narrative llm unavailable")
    ok_steps = sum(1 for s in steps if s.get("status") == "ok")
    warn_steps = sum(1 for s in steps if s.get("status") == "warning")
    err_steps = sum(1 for s in steps if s.get("status") == "error")
    filled = [b for b in bindings if b.get("filled")]
    parts: list[str] = []
    if verdict and verdict.get("reason"):
        parts.append(f"{VERDICT_KO.get(str(verdict.get('verdict')), '관측')} — {verdict['reason']}.")
    else:
        parts.append(f"{STATUS_KO.get(status, status)}.")
    parts.append(f"단계 {len(steps)}건 중 정상 {ok_steps}건 · 경고 {warn_steps}건 · 오류 {err_steps}건 관측.")
    if filled:
        sample = ", ".join(f"{b.get('field')}={b.get('value')}" for b in filled[:3])
        parts.append(f"화면에 넣은 값 {len(filled)}건 ({sample}).")
    if missing:
        parts.append(f"근거 없음 항목 {len(missing)}건: {', '.join(missing[:3])}.")
    parts.append("Pass/Fail·배포는 담당자가 확정합니다.")
    return " ".join(parts), "deterministic", diagnosis


def _blocking_observation_outcome(result: dict) -> tuple[str, str] | None:
    """Find explicit blocking signals in immutable step observations.

    Legacy runs may contain an incorrectly optimistic structured verdict while
    their captured URL/snapshot says `None#error=server_error` or Flask Not Found.
    Direct execution evidence must win over that derived verdict.
    """
    texts = [str(result.get("observationSummary") or "")]
    for step in result.get("steps") or []:
        if not isinstance(step, dict):
            continue
        texts.extend(
            str(step.get(key) or "")
            for key in ("observationSummary", "currentUrl", "url", "errorMessage")
        )
    observed = "\n".join(texts)
    lower = observed.lower()
    server_signals = (
        "error=server_error",
        "/none#error=",
        "the requested url was not found on the server",
        'heading "not found"',
        "http 404",
        "method not allowed",
    )
    if any(signal in lower for signal in server_signals):
        return "be_error", "서버 오류/Not Found가 실행 단계에서 관측됐습니다"
    return None


_VISIBLE_ASSERTION_RE = re.compile(r"표시\s*확인\s*(\d+)\s*/\s*(\d+)\s*건")


def _reconcile_direct_visibility_evidence(result: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Repair a legacy derived verdict when its own direct assertion contradicts it.

    The evidence files stay immutable.  Only the API projection is corrected, and only
    when every failed criterion is a visibility criterion, no server denial exists, and
    an `assert_visible` step explicitly recorded a complete N/N observation.
    """
    verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
    if verdict.get("verdict") != "expected_not_met" or _blocking_observation_outcome(result):
        return result, False
    blockers = list(verdict.get("blockingIssues") or [])
    if any(
        str(item.get("kind") or "") not in {"", "element_missing", "controls_visible"}
        for item in blockers
        if isinstance(item, dict)
    ):
        return result, False
    criteria = list(verdict.get("criteriaResults") or verdict.get("criteria") or [])
    failed = [item for item in criteria if isinstance(item, dict) and item.get("result") == "not_met"]
    if not failed or any(str(item.get("check") or "") != "controls_visible" for item in failed):
        return result, False
    direct_observation = next(
        (
            str(step.get("observationSummary") or "")
            for step in (result.get("steps") or [])
            if isinstance(step, dict)
            and str(step.get("action") or "") == "assert_visible"
            and str(step.get("status") or "") == "ok"
            and (match := _VISIBLE_ASSERTION_RE.search(str(step.get("observationSummary") or "")))
            and int(match.group(1)) == int(match.group(2))
            and int(match.group(2)) > 0
        ),
        None,
    )
    if not direct_observation:
        return result, False
    corrected_criteria: list[dict[str, Any]] = []
    for item in criteria:
        candidate = dict(item) if isinstance(item, dict) else {"observed": str(item)}
        if candidate.get("result") == "not_met" and candidate.get("check") == "controls_visible":
            candidate["result"] = "met"
            candidate["observed"] = f"직접 표시 단계에서 대상 컨트롤을 관측했습니다 ({direct_observation})"
            candidate["evidenceReconciled"] = True
        corrected_criteria.append(candidate)
    corrected_verdict = {
        **verdict,
        "verdict": "expected_met",
        "reason": "표시 확인 단계에서 대상 화면 컨트롤을 직접 관측했습니다",
        "verdictReason": "표시 확인 단계에서 대상 화면 컨트롤을 직접 관측했습니다",
        "criteria": corrected_criteria,
        "criteriaResults": corrected_criteria,
        "blockingIssues": [],
        "blockedCause": None,
        "remediation": [],
        "coverageNote": "기준 항목 전부 관측",
        "evidenceReconciled": True,
    }
    return {
        **result,
        "verdict": corrected_verdict,
        "observationSummary": corrected_verdict["reason"],
    }, True


def _classify_run_outcome(status: str, result: dict) -> tuple[str, str]:
    """Classify FE/BE/business outcomes for Console list — observation only."""
    obs = str(result.get("observationSummary") or "")
    business = result.get("businessError") or result.get("businessMessage")
    http_status = result.get("backendHttpStatus") or result.get("httpStatus")
    # 기대 결과 대조 판정이 우선한다 — 「도달했다」만으로 정상 관측 플래그를 주지 않는다 (D-015)
    verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
    kind = str(verdict.get("verdict") or "")
    reason = str(verdict.get("reason") or "")
    blocking = _blocking_observation_outcome(result)
    if blocking:
        return blocking
    if kind == "expected_not_met":
        cause = str(verdict.get("blockedCause") or "")
        if cause in {"server_error", "method_not_allowed", "not_found"}:
            return "be_error", reason or "요청이 거부됐습니다"
        if cause == "session_missing":
            return "fe_error", reason or "선행 로그인 세션이 성립하지 않았습니다"
        return "business_error", reason or "기대 결과와 다르게 관측됐습니다"
    if kind == "undetermined":
        return "unknown", reason or "기대 결과를 확인할 관측 자료가 부족합니다"
    if business:
        return "business_error", str(business)
    if http_status is not None:
        try:
            code = int(http_status)
            if code >= 400:
                return "be_error", f"백엔드 HTTP {code}"
        except (TypeError, ValueError):
            pass
    lower = obs.lower()
    if any(token in obs for token in ("원장이 존재", "업무", "business")):
        return "business_error", obs or "업무 오류 관측"
    if status in {"WAITING_FOR_REVIEW", "SUCCEEDED", "SUCCESS"}:
        if kind == "expected_met":
            return "success", reason or obs or "기대한 화면·응답을 관측했습니다 (HITL 대기)"
        # 판정 기준이 아예 없는 실행은 정상 관측으로 단정하지 않는다
        if not kind:
            return "unknown", obs or "기대 결과 기준이 없어 판정하지 않았습니다 (HITL 대기)"
        return "success", reason or obs or "화면·요청 관측 완료 (HITL 대기)"
    if status in {"AUTO_FAILED", "FAILED"}:
        if any(token in lower for token in ("backend", "api", "http", "5xx", "4xx")):
            return "be_error", obs or "백엔드 오류 관측"
        return "fe_error", obs or "화면 실행 오류 관측"
    return "unknown", obs or status


def _diagnosis_owner(kind: str) -> str:
    if kind in {"server_error", "method_not_allowed", "not_found"}:
        return "Backend 개발 담당"
    if kind in {
        "element_missing",
        "no_state_change",
        "client_validation_missing",
        "required_validation_missing",
        "boundary_validation_missing",
    }:
        return "Frontend 개발·QA 자동화 담당"
    if kind == "session_missing":
        return "실행환경·QA 담당"
    if kind == "destructive_policy_blocked":
        return "QA 실행 담당"
    if kind == "input_precondition_invalid":
        return "QA 테스트 데이터·실행환경 담당"
    return "개발·QA 담당"


def _grounded_failure_guidance(
    criteria: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Explain common product failures from the recorded criterion itself.

    This deliberately avoids guessing an implementation defect.  It turns the
    expected/observed pair into an actionable review target and keeps the
    proposed fix phrased as a validation point to inspect.
    """
    failed = next(
        (
            item
            for item in criteria
            if str(item.get("result") or "") in {"not_met", "undetermined"}
        ),
        None,
    )
    blocker = blockers[0] if blockers else {}
    check = str((failed or {}).get("check") or blocker.get("kind") or "").strip()
    expected = str((failed or {}).get("expected") or "").strip()
    observed = str((failed or {}).get("observed") or blocker.get("detail") or "").strip()
    combined = f"{check} {expected} {observed}".lower()
    evidence_pair = " · ".join(
        part for part in (f"기대: {expected}" if expected else "", f"관측: {observed}" if observed else "") if part
    )

    if check == "native_constraint_rejection" or any(
        token in combined for token in ("입력 제약", "checkvalidity", "validity")
    ):
        required = any(token in combined for token in ("필수", "required", "누락", "비어"))
        boundary = any(token in combined for token in ("최소", "최대", "min", "max", "경계", "초과", "미만"))
        numeric = any(token in combined for token in ("숫자", "number", "numeric", "금액"))
        cause_kind = (
            "required_validation_missing"
            if required
            else "boundary_validation_missing"
            if boundary
            else "client_validation_missing"
        )
        if numeric:
            problem = (
                "숫자만 입력해야 하는 필드가 숫자가 아닌 입력을 거부하지 못했습니다. "
                f"{evidence_pair or '브라우저 유효성 관측에서 거부 상태를 확인하지 못했습니다.'}"
            )
            cause = (
                "숫자 필드의 DOM type·pattern·inputMode 또는 제출 전 validation이 분석된 입력 제약과 "
                "같이 적용되는지 확인해야 합니다. 현재 증적에서는 잘못된 값의 거부 상태가 관측되지 않았습니다."
            )
            action = (
                "해당 필드의 type=number·pattern과 제출 핸들러 validation을 확인하고, 숫자가 아닌 값은 "
                "업무 요청 전에 오류 안내와 함께 차단되도록 보완하세요."
            )
            retest = "같은 숫자 외 입력으로 재실행해 필드 오류 표시와 Network 요청 미전송을 함께 확인하세요."
        elif required:
            problem = f"필수 입력이 비어 있는데도 화면 제약이 제출을 막지 못했습니다. {evidence_pair}".strip()
            cause = "required 속성과 제출 전 필수값 validation이 실제 입력 컨트롤과 같은 필드에 연결됐는지 확인해야 합니다."
            action = "필수 필드의 required·스키마 규칙·제출 핸들러 검증을 일치시키고, 빈 값이면 요청 전에 오류를 표시하도록 보완하세요."
            retest = "동일 필드를 비운 채 재실행해 오류 표시와 Network 요청 미전송을 함께 확인하세요."
        elif boundary:
            problem = f"분석된 최소·최대 경계 밖의 값을 화면이 거부하지 못했습니다. {evidence_pair}".strip()
            cause = "DOM min/max/step과 제출 전 경계값 validation이 분석된 제약과 같이 적용되는지 확인해야 합니다."
            action = "해당 필드의 min/max/step과 서버 DTO 경계 규칙을 대조하고, 범위 밖 값은 요청 전에 차단하도록 보완하세요."
            retest = "같은 경계 밖 입력으로 재실행해 오류 표시·요청 미전송·경계값 정상 허용을 함께 확인하세요."
        else:
            problem = f"분석된 형식 제약과 달리 유효하지 않은 입력이 화면에서 허용됐습니다. {evidence_pair}".strip()
            cause = "DOM pattern/type과 제출 전 validation이 분석된 입력 제약에 맞게 적용되는지 확인해야 합니다."
            action = "필드 형식 제약과 제출 전 validation을 대조하고, 잘못된 값은 오류 안내와 함께 요청 전에 차단하도록 보완하세요."
            retest = "동일한 유효하지 않은 값으로 재실행해 오류 표시와 Network 요청 미전송을 함께 확인하세요."
        return {
            "causeCategory": cause_kind,
            "problemSummary": problem,
            "causeSummary": cause,
            "action": action,
            "retestCondition": retest,
        }

    known = {
        "element_missing": (
            "화면에서 기대한 컨트롤 또는 결과 요소를 찾지 못했습니다.",
            "분석된 selector·접근성 이름과 현재 DOM 구조가 달라졌거나 조건부 렌더링이 적용됐는지 확인해야 합니다.",
            "해당 화면의 DOM·접근성 이름·조건부 렌더링을 확인하고 분석 selector를 최신 코드 근거로 갱신하세요.",
            "같은 화면 상태에서 재실행해 대상 요소와 캡처 증적이 함께 관측되는지 확인하세요.",
        ),
        "no_state_change": (
            "업무 요청 뒤 기대한 화면 값 또는 목록 변화가 관측되지 않았습니다.",
            "응답 데이터가 화면 상태에 바인딩되는 경로, 캐시 갱신, 후속 조회가 실행됐는지 확인해야 합니다.",
            "API 응답과 화면 상태 갱신 코드를 대조하고 잔액·목록·완료 안내가 같은 요청 결과로 갱신되도록 보완하세요.",
            "동일 입력으로 재실행해 요청 응답과 전후 화면 값 변화가 같은 실행 ID로 연결되는지 확인하세요.",
        ),
        "not_found": (
            "분석된 화면 또는 API 경로가 실행 서버에서 Not Found로 관측됐습니다.",
            "분석 시점의 route·endpoint와 배포된 실행환경의 라우팅 버전이 같은지 확인해야 합니다.",
            "Frontend route와 Backend endpoint 배포 상태·base URL·버전을 대조한 뒤 실제 화면 트리거 경로를 갱신하세요.",
            "같은 실행환경에서 화면 트리거를 통해 재실행하고 404가 사라졌는지 확인하세요.",
        ),
    }
    if check in known:
        problem, cause, action, retest = known[check]
        return {
            "causeCategory": check,
            "problemSummary": f"{problem} {evidence_pair}".strip(),
            "causeSummary": cause,
            "action": action,
            "retestCondition": retest,
        }
    return None


def _build_run_diagnosis(status: str, result: dict[str, Any]) -> dict[str, Any]:
    """Build a review-ready cause/action handoff from captured facts only."""
    verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
    verdict_kind = str(verdict.get("verdict") or "undetermined")
    if verdict_kind == "expected_met":
        outcome, headline = "success", "성공 기준 충족"
    elif verdict_kind == "expected_not_met":
        outcome, headline = "failure", "실패 기준 관측"
    else:
        outcome, headline = "undetermined", "판정 근거 부족"
    blockers = [item for item in (verdict.get("blockingIssues") or []) if isinstance(item, dict)]
    steps = [item for item in (result.get("steps") or []) if isinstance(item, dict)]
    policy_blocked_step = next(
        (
            item
            for item in steps
            if "submit_blocked_destructive" in {
                str(value) for value in (item.get("missingData") or item.get("missing_data") or [])
            }
            or "자동 클릭을 차단" in str(item.get("observationSummary") or "")
        ),
        None,
    )
    missing_data = {str(item) for item in (result.get("missing_data") or result.get("missingData") or [])}
    policy_blocked = policy_blocked_step is not None or "submit_blocked_destructive" in missing_data
    input_precondition_step = next(
        (
            item
            for item in steps
            if "input_precondition_invalid" in {
                str(value) for value in (item.get("missingData") or item.get("missing_data") or [])
            }
        ),
        None,
    )
    input_precondition_invalid = (
        input_precondition_step is not None or "input_precondition_invalid" in missing_data
    )
    if input_precondition_invalid:
        outcome, headline = "undetermined", "실행환경 확인 필요"
    elif policy_blocked:
        outcome, headline = "undetermined", "실행 승인 필요"
    cause_kind = (
        "input_precondition_invalid"
        if input_precondition_invalid
        else "destructive_policy_blocked"
        if policy_blocked
        else str((blockers[0].get("kind") if blockers else verdict.get("blockedCause")) or "unknown")
    )
    cause_summary = (
        str(
            (input_precondition_step or {}).get("observationSummary")
            or "현재 테스트 계정의 잔액·허용 범위가 실행 입력을 수용하지 않아 브라우저가 제출 요청을 보내지 않았습니다. 대상 서비스 장애가 아니라 테스트 데이터 선행조건 부족입니다."
        )
        if input_precondition_invalid
        else "데이터를 변경하는 제출 단계가 명시적 1회 허용 없이 실행되어 안전 정책이 클릭을 차단했습니다. 대상 서비스 오류가 아니라 실행 정책에 의해 제출이 수행되지 않은 상태입니다."
        if policy_blocked
        else str(
            (blockers[0].get("detail") if blockers else None)
            or verdict.get("reason")
            or result.get("observationSummary")
            or "관측 요약이 없습니다"
        )
    )
    criteria = [
        item
        for item in (verdict.get("criteriaResults") or verdict.get("criteria") or [])
        if isinstance(item, dict)
    ]
    failed_criteria = [
        str(item.get("observed") or item.get("expected") or item.get("check") or "")
        for item in criteria
        if item.get("result") in {"not_met", "undetermined"}
    ]
    problem_summary = (
        "현재 테스트 계정 상태가 입력 제약을 충족하지 않아 제출 요청이 전송되지 않았습니다. 후속 성공 안내·잔액·거래내역 미관측은 하나의 선행조건 문제에서 파생된 결과입니다."
        if input_precondition_invalid
        else "업무 제출이 실행되지 않아 완료 안내, 화면 값 변화, 결과 목록 추가를 확인하지 못했습니다."
        if policy_blocked
        else " · ".join(item for item in failed_criteria[:3] if item)
        or cause_summary
    )
    specific_guidance = (
        _grounded_failure_guidance(criteria, blockers)
        if outcome == "failure" and not input_precondition_invalid and not policy_blocked
        else None
    )
    if specific_guidance:
        cause_kind = str(specific_guidance["causeCategory"])
        problem_summary = str(specific_guidance["problemSummary"])
        cause_summary = str(specific_guidance["causeSummary"])
    evidence = [
        str(item.get("observed"))
        for item in criteria
        if item.get("observed") and (item.get("result") != "met" or outcome == "success")
    ][:3]
    if not evidence:
        evidence = [
            f"{step.get('stepId')}: {step.get('observationSummary')}"
            for step in (result.get("steps") or [])
            if isinstance(step, dict) and step.get("observationSummary")
        ][:3]
    actions: list[dict[str, str]] = []
    if input_precondition_invalid:
        actions.append(
            {
                "owner": _diagnosis_owner(cause_kind),
                "action": "테스트 계정의 선행 데이터를 초기화·충전하거나 현재 잔액 범위 안의 값을 선택한 뒤 같은 시나리오를 다시 실행하세요.",
                "reason": cause_summary,
            }
        )
    elif policy_blocked:
        actions.append(
            {
                "owner": _diagnosis_owner(cause_kind),
                "action": "시나리오 상세에서 현재 입력값으로 실행하는 1회 테스트를 명시적으로 승인한 뒤 재실행하세요. 배치 실행은 데이터 변경 시나리오를 기본 제외하므로 별도 승인 실행으로 검증하세요.",
                "reason": str(
                    (policy_blocked_step or {}).get("observationSummary")
                    or "데이터 변경 가능 제출 단계가 안전 정책으로 차단됨"
                ),
            }
        )
    elif specific_guidance:
        actions.append(
            {
                "owner": _diagnosis_owner(cause_kind),
                "action": str(specific_guidance["action"]),
                "reason": cause_summary,
            }
        )
    for blocker in blockers:
        action = str(blocker.get("suggestedFix") or "").strip()
        if action:
            actions.append(
                {
                    "owner": _diagnosis_owner(str(blocker.get("kind") or cause_kind)),
                    "action": action,
                    "reason": str(blocker.get("detail") or cause_summary),
                }
            )
    if outcome == "failure" and not actions:
        actions.append(
            {
                "owner": _diagnosis_owner(cause_kind),
                "action": "실패 단계의 화면 DOM·요청 응답·서버 로그를 함께 대조하고 원인을 조치하세요",
                "reason": cause_summary,
            }
        )
    retest = (
        "잔액이 있는 테스트 계정을 준비한 뒤 입력값이 화면의 최소·최대 허용 범위 안인지 확인하고, 성공 안내·잔액 감소·신규 거래 행을 함께 재관측하세요"
        if input_precondition_invalid
        else "현재 화면의 허용 입력 범위를 확인하고 데이터 변경 1회 실행을 명시 승인한 뒤 완료 안내·화면 값 변화·신규 결과 행을 함께 확인하세요"
        if policy_blocked
        else str(specific_guidance["retestCondition"])
        if specific_guidance
        else
        "조치 후 같은 입력과 실행환경으로 재실행해 기대 기준과 실제 관측이 모두 일치하는지 확인하세요"
        if outcome == "failure"
        else "담당자가 증적을 확인해 최종 판정을 확정하세요"
        if outcome == "success"
        else "누락된 화면·요청·로그 근거를 보강한 뒤 다시 실행하세요"
    )
    handoff = (
        "QA 테스트 데이터 담당자님, 현재 계정의 잔액·허용 범위가 입력값을 수용하지 않아 요청이 전송되지 않았습니다. 계정 상태를 초기화·충전한 뒤 동일 조건으로 재검증해 주세요."
        if input_precondition_invalid
        else "QA 실행 담당자님, 이번 결과는 서비스 오류가 아니라 제출 단계의 안전 정책 차단입니다. 데이터 변경 1회 실행을 승인하고 잔액이 있는 계정으로 재검증해 주세요."
        if policy_blocked
        else
        f"{_diagnosis_owner(cause_kind)}님, {cause_summary} 조치 후 동일 조건으로 재검증해 주세요."
        if outcome == "failure"
        else "QA 담당자님, 자동 관측 근거를 확인한 뒤 최종 결과를 판정해 주세요."
        if outcome == "success"
        else "개발·QA 담당자님, 누락된 관측 근거를 보강한 뒤 다시 확인해 주세요."
    )
    return {
        "outcome": outcome,
        "headline": headline,
        "problemSummary": problem_summary,
        "causeCategory": cause_kind,
        "causeSummary": cause_summary,
        "evidence": evidence,
        "actions": actions[:3],
        "retestCondition": retest,
        "handoffMessage": handoff,
        "mode": "deterministic",
        "humanDecisionRequired": True,
        "statusAtDiagnosis": status,
    }


def _merge_llm_diagnosis(base: dict[str, Any], candidate: Any) -> dict[str, Any]:
    """Accept grounded explanatory fields while preserving deterministic verdict facts."""
    if not isinstance(candidate, dict):
        return base
    merged = dict(base)
    for key in ("causeSummary", "retestCondition", "handoffMessage"):
        value = str(candidate.get(key) or "").strip()
        if value:
            merged[key] = value[:600]
    raw_actions = candidate.get("actions") if isinstance(candidate.get("actions"), list) else []
    actions: list[dict[str, str]] = []
    for item in raw_actions[:3]:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip()
        if not action:
            continue
        actions.append(
            {
                "owner": str(item.get("owner") or _diagnosis_owner(str(base.get("causeCategory") or "unknown")))[:80],
                "action": action[:400],
                "reason": str(item.get("reason") or base.get("causeSummary") or "")[:400],
            }
        )
    if base.get("outcome") == "failure" and actions:
        merged["actions"] = actions
    merged["mode"] = "llm"
    return merged


def _normalize_derived_outcome(run: RunSummary) -> RunSummary:
    """Recompute fields derived from immutable execution evidence.

    Earlier Phase-14 builds compared the structured verdict with the wrong enum
    literal and could persist a Flask 404 as WAITING_FOR_REVIEW/success.  The raw
    result already contains the conservative verdict, so old and new runs can be
    presented consistently without rewriting evidence files.
    """
    result, reconciled = _reconcile_direct_visibility_evidence(dict(run.result or {}))
    verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
    status = run.status
    if (
        verdict.get("verdict") == "expected_not_met"
        or _blocking_observation_outcome(result) is not None
    ) and status == "WAITING_FOR_REVIEW":
        status = "AUTO_FAILED"
    elif reconciled and status == "AUTO_FAILED":
        status = "WAITING_FOR_REVIEW"
    outcome_kind, outcome_summary = _classify_run_outcome(status, result)
    if reconciled:
        met_count = sum(
            1
            for item in (verdict.get("criteriaResults") or verdict.get("criteria") or [])
            if isinstance(item, dict) and item.get("result") == "met"
        )
        result = {
            **result,
            "runNarrative": (
                f"직접 화면 관측과 구조화 기준을 다시 대조해 기대 기준 {met_count}건을 모두 관측했습니다. "
                "과거 selector 문자열 비교에서 생긴 오판정은 응답 화면에서 보정했으며, "
                "최종 Pass/Fail은 담당자가 증적을 확인해 확정합니다."
            ),
            "runNarrativeMode": "evidence-reconciled",
        }
    diagnosis = _build_run_diagnosis(status, result)
    stored_diagnosis = result.get("runDiagnosis")
    if isinstance(stored_diagnosis, dict) and stored_diagnosis.get("mode") == "llm" and not reconciled:
        diagnosis = _merge_llm_diagnosis(diagnosis, stored_diagnosis)
    result = {**result, "runDiagnosis": diagnosis}
    if (
        status == run.status
        and outcome_kind == run.outcomeKind
        and outcome_summary == run.outcomeSummary
        and result == run.result
    ):
        return run
    return run.model_copy(
        update={
            "status": status,
            "outcomeKind": outcome_kind,
            "outcomeSummary": outcome_summary,
            "result": result,
        }
    )
