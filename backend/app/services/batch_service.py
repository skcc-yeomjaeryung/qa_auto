from __future__ import annotations

import hashlib
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4

from app.services.batch_models import (
    BatchAttempt,
    BatchCase,
    BatchCreateRequest,
    BatchDefinition,
    BatchException,
    BatchSummary,
)
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.run_models import RunCreateRequest, RunSummary
from app.services.run_service import BrowserRunService, TERMINAL_STATUSES


_BATCH_MUTATION_LOCK = Lock()
_RESOURCE_LOCKS_GUARD = Lock()
_RESOURCE_LOCKS: dict[str, Lock] = {}
_COORDINATORS_GUARD = Lock()
_COORDINATORS: dict[str, Thread] = {}
_IDLE_WAIT = Event()


def _resource_lock(key: str) -> Lock:
    with _RESOURCE_LOCKS_GUARD:
        return _RESOURCE_LOCKS.setdefault(key, Lock())


def _now() -> str:
    return utc_now().isoformat()


def _is_destructive(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in {"destructive", "isdestructive"} and item is True:
                return True
            if normalized in {"risk", "safetyclass"} and str(item).lower() == "destructive":
                return True
            if _is_destructive(item):
                return True
    if isinstance(value, list):
        return any(_is_destructive(item) for item in value)
    return False


def _confidence(value: Any) -> float | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() == "confidence":
                try:
                    return float(item)
                except (TypeError, ValueError):
                    pass
        for item in value.values():
            found = _confidence(item)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _confidence(item)
            if found is not None:
                return found
    return None


class BatchService:
    """승인 Profile을 고정해 무인 실행하는 재현 가능한 Phase 14 배치 오케스트레이터."""

    def __init__(
        self,
        store: InMemoryPlatformStore,
        run_service: BrowserRunService | None = None,
    ) -> None:
        self.store = store
        self.runs = run_service or BrowserRunService(store)

    def create(self, payload: BatchCreateRequest, owner_user_id: str) -> BatchDefinition:
        project = self.store.get_project(payload.projectId)
        if not project:
            raise LookupError(f"project not found: {payload.projectId}")
        if project.ownerUserId != owner_user_id:
            raise PermissionError("다른 사용자의 프로젝트에는 배치를 만들 수 없습니다")

        sources: list[tuple[Any, Any, dict[str, Any]]] = []
        for pin in payload.scenarioProfiles:
            scenario = self.store.get_scenario(pin.scenarioId)
            profile = self.store.get_profile(pin.inputProfileId)
            if not scenario or scenario.projectId != payload.projectId:
                raise ValueError(f"scenario is not assigned to project: {pin.scenarioId}")
            if not profile or profile.scenarioId != scenario.scenarioId:
                raise ValueError(f"input profile does not match scenario: {pin.inputProfileId}")
            if profile.status != "APPROVED":
                raise ValueError(f"approved input profile required: {pin.inputProfileId}")
            for case in list((profile.result or {}).get("cases") or []):
                sources.append((scenario, profile, dict(case)))

        if not sources:
            raise ValueError("approved input profiles contain no cases")

        selected = self._select_sources(sources, payload.totalBudget, payload.categoryCounts)
        batch_id = f"BAT-{uuid4().hex[:12]}"
        cases = [self._make_case(batch_id, index, source, payload) for index, source in enumerate(selected, 1)]
        now = _now()
        definition = BatchDefinition(
            batchId=batch_id,
            ownerUserId=owner_user_id,
            projectId=payload.projectId,
            name=payload.name,
            status="READY" if payload.ready else "DRAFT",
            scenarioProfiles=payload.scenarioProfiles,
            environmentId=payload.environmentId,
            totalBudget=len(cases),
            categoryCounts=dict(Counter(case.category for case in cases)),
            concurrency=payload.concurrency,
            policy=payload.policy,
            cases=cases,
            createdAt=now,
            updatedAt=now,
        )
        return self.store.save_batch(definition)

    @staticmethod
    def _select_sources(
        sources: list[tuple[Any, Any, dict[str, Any]]],
        budget: int,
        category_counts: dict[str, int],
    ) -> list[tuple[Any, Any, dict[str, Any]]]:
        ordered = sorted(
            sources,
            key=lambda row: (
                row[0].scenarioId,
                row[1].profileId,
                str(row[2].get("category") or "uncategorized"),
                str(row[2].get("caseId") or ""),
            ),
        )
        selected: list[tuple[Any, Any, dict[str, Any]]] = []
        if category_counts:
            for category in sorted(category_counts):
                candidates = [row for row in ordered if str(row[2].get("category") or "uncategorized") == category]
                for index in range(max(0, int(category_counts[category]))):
                    if candidates and len(selected) < budget:
                        selected.append(candidates[index % len(candidates)])
        else:
            for index in range(budget):
                selected.append(ordered[index % len(ordered)])
        return selected[:budget]

    @staticmethod
    def _make_case(
        batch_id: str,
        index: int,
        source: tuple[Any, Any, dict[str, Any]],
        payload: BatchCreateRequest,
    ) -> BatchCase:
        scenario, profile, source_case = source
        inputs = dict(source_case.get("inputs") or {})
        lock_values = [str(inputs[field]) for field in payload.policy.resourceLockFields if inputs.get(field) is not None]
        isolation = ":".join([payload.environmentId or payload.projectId, *(lock_values or [scenario.scenarioId])])
        digest = hashlib.sha256(
            f"{batch_id}:{index}:{scenario.scenarioId}:{profile.profileId}:{source_case.get('caseId')}".encode()
        ).hexdigest()[:12]
        skip_reason = None
        if scenario.unresolvedCount and payload.policy.unresolvedAction == "skip_notify":
            skip_reason = f"unresolved input/evidence {scenario.unresolvedCount}건"
        elif _is_destructive(scenario.result) and payload.policy.destructiveAction == "exclude":
            skip_reason = "destructive scenario excluded by policy"
        confidence = _confidence(scenario.result)
        low_confidence = confidence is not None and confidence < 0.7
        review = bool(source_case.get("reviewRequired")) or (
            low_confidence and payload.policy.lowConfidenceAction == "review_required"
        )
        return BatchCase(
            caseId=f"BCASE-{digest}",
            sourceCaseId=source_case.get("caseId"),
            scenarioId=scenario.scenarioId,
            scenarioVersion=str(scenario.version or "1"),
            inputProfileId=profile.profileId,
            inputProfileVersion=str(profile.version or "1"),
            category=str(source_case.get("category") or "uncategorized"),
            inputs=inputs,
            isolationKey=isolation,
            status="SKIPPED" if skip_reason else "PENDING",
            reviewRequired=review,
            skipReason=skip_reason,
        )

    def list(self, owner_user_id: str) -> list[BatchDefinition]:
        return [item for item in self.store.list_batches() if item.ownerUserId == owner_user_id]

    def get(self, batch_id: str, owner_user_id: str) -> BatchDefinition:
        item = self.store.get_batch(batch_id)
        if not item:
            raise LookupError(f"batch not found: {batch_id}")
        if item.ownerUserId != owner_user_id:
            raise PermissionError("다른 사용자의 배치는 조회할 수 없습니다")
        return item

    def start(self, batch_id: str, owner_user_id: str) -> BatchDefinition:
        item = self.get(batch_id, owner_user_id)
        if item.status not in {"READY", "PAUSED"}:
            raise ValueError(f"batch cannot start from {item.status}")
        now = _now()
        updated = item.model_copy(
            update={"status": "RUNNING", "startedAt": item.startedAt or now, "updatedAt": now}
        )
        self.store.save_batch(updated)
        self._ensure_coordinator(batch_id)
        return updated

    def pause(self, batch_id: str, owner_user_id: str) -> BatchDefinition:
        item = self.get(batch_id, owner_user_id)
        if item.status != "RUNNING":
            raise ValueError(f"batch cannot pause from {item.status}")
        return self.store.save_batch(item.model_copy(update={"status": "PAUSED", "updatedAt": _now()}))

    def resume(self, batch_id: str, owner_user_id: str) -> BatchDefinition:
        return self.start(batch_id, owner_user_id)

    def cancel(self, batch_id: str, owner_user_id: str) -> BatchDefinition:
        item = self.get(batch_id, owner_user_id)
        if item.status in {"COMPLETED", "COMPLETED_WITH_FAILURES", "CANCELLED"}:
            return item
        active = [case.currentRunId for case in item.cases if case.currentRunId]
        for run_id in active:
            try:
                self.runs.cancel_run(str(run_id))
            except (LookupError, RuntimeError):
                pass
        cases = [
            case.model_copy(update={"status": "CANCELLED", "currentRunId": None})
            if case.status in {"PENDING", "RUNNING"}
            else case
            for case in item.cases
        ]
        return self.store.save_batch(
            item.model_copy(
                update={"status": "CANCELLED", "cases": cases, "updatedAt": _now(), "endedAt": _now()}
            )
        )

    def _ensure_coordinator(self, batch_id: str) -> None:
        with _COORDINATORS_GUARD:
            existing = _COORDINATORS.get(batch_id)
            if existing and existing.is_alive():
                return
            thread = Thread(target=self._run_batch, args=(batch_id,), daemon=True, name=f"batch-{batch_id}")
            _COORDINATORS[batch_id] = thread
            thread.start()

    def _run_batch(self, batch_id: str) -> None:
        item = self.store.get_batch(batch_id)
        if not item:
            return
        worker_count = min(item.concurrency, item.policy.projectRateLimit)
        futures: dict[Future[BatchCase], str] = {}
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix=f"{batch_id}-case") as pool:
            while True:
                current = self.store.get_batch(batch_id)
                if not current or current.status == "CANCELLED":
                    break
                if current.status == "PAUSED":
                    if futures:
                        done, _ = wait(list(futures), timeout=0.2, return_when=FIRST_COMPLETED)
                        self._collect(batch_id, futures, done)
                    else:
                        _IDLE_WAIT.wait(0.2)
                    continue
                pending = [case for case in current.cases if case.status == "PENDING"]
                while pending and len(futures) < worker_count:
                    case = pending.pop(0)
                    claimed = self._claim_case(batch_id, case.caseId)
                    if claimed is None:
                        continue
                    future = pool.submit(self._execute_case, batch_id, claimed)
                    futures[future] = case.caseId
                if not futures:
                    break
                done, _ = wait(list(futures), timeout=0.2, return_when=FIRST_COMPLETED)
                self._collect(batch_id, futures, done)

        current = self.store.get_batch(batch_id)
        if not current or current.status == "CANCELLED":
            return
        # Policy exclusions are an intentional safety outcome, not a product or
        # infrastructure failure. Keep them visible in summary.skipped/exceptions
        # without turning an otherwise successful batch red.
        has_failures = any(case.status in {"FAILED", "REVIEW_REQUIRED"} for case in current.cases)
        final = "COMPLETED_WITH_FAILURES" if has_failures else "COMPLETED"
        self.store.save_batch(
            current.model_copy(update={"status": final, "updatedAt": _now(), "endedAt": _now()})
        )

    def _collect(
        self,
        batch_id: str,
        futures: dict[Future[BatchCase], str],
        done: set[Future[BatchCase]],
    ) -> None:
        for future in done:
            case_id = futures.pop(future)
            try:
                case = future.result()
            except Exception as exc:  # noqa: BLE001
                current = self.store.get_batch(batch_id)
                original = next((row for row in (current.cases if current else []) if row.caseId == case_id), None)
                if not original:
                    continue
                attempt = BatchAttempt(
                    attempt=len(original.attempts) + 1,
                    status="error",
                    failureKind="infra",
                    outcomeSummary=str(exc),
                    startedAt=_now(),
                    endedAt=_now(),
                )
                case = original.model_copy(
                    update={"status": "FAILED", "currentRunId": None, "attempts": [*original.attempts, attempt]}
                )
            self._replace_case(batch_id, case)

    def _execute_case(self, batch_id: str, case: BatchCase) -> BatchCase:
        lock = _resource_lock(case.isolationKey)
        with lock:
            case = case.model_copy(update={"status": "RUNNING"})
            self._replace_case(batch_id, case)
            attempts = list(case.attempts)
            max_attempts = 1
            policy = self.store.get_batch(batch_id).policy  # type: ignore[union-attr]
            while len(attempts) < max_attempts:
                if (current := self.store.get_batch(batch_id)) is None or current.status == "CANCELLED":
                    return case.model_copy(update={"status": "CANCELLED", "currentRunId": None})
                started = _now()
                try:
                    run = self.runs.start_run(
                        case.scenarioId,
                        RunCreateRequest(
                            consent=True,
                            environmentId=current.environmentId,
                            inputs=case.inputs,
                            inputProfileId=case.inputProfileId,
                            mode="interactive",
                            scenarioVersion=case.scenarioVersion,
                            inputProfileVersion=case.inputProfileVersion,
                        ),
                    )
                    case = case.model_copy(update={"currentRunId": run.runId})
                    self._replace_case(batch_id, case)
                    run = self._await_terminal(batch_id, run)
                    failure_kind = self._failure_kind(run)
                    attempt = BatchAttempt(
                        attempt=len(attempts) + 1,
                        runId=run.runId,
                        status=run.status,
                        failureKind=failure_kind,
                        outcomeKind=run.outcomeKind,
                        outcomeSummary=run.outcomeSummary or run.observationSummary,
                        screenshotCount=run.screenshotCount,
                        snapshotCount=run.snapshotCount,
                        evidenceReady=bool(run.evidenceDir and (run.screenshotCount + run.snapshotCount > 0)),
                        startedAt=started,
                        endedAt=_now(),
                    )
                except Exception as exc:  # noqa: BLE001
                    failure_kind = "infra"
                    attempt = BatchAttempt(
                        attempt=len(attempts) + 1,
                        status="error",
                        failureKind="infra",
                        outcomeSummary=str(exc),
                        startedAt=started,
                        endedAt=_now(),
                    )
                attempts.append(attempt)
                allowed_retries = (
                    policy.infraRetryCount if failure_kind == "infra" else policy.productRetryCount
                )
                max_attempts = 1 + allowed_retries
                if failure_kind == "none" or len(attempts) >= max_attempts:
                    break

            latest = attempts[-1]
            flaky = latest.failureKind == "none" and any(item.failureKind != "none" for item in attempts[:-1])
            if latest.failureKind == "cancelled":
                status = "CANCELLED"
            elif latest.failureKind != "none":
                status = "FAILED"
            elif case.reviewRequired or not latest.evidenceReady:
                status = "REVIEW_REQUIRED"
            else:
                status = "COMPLETED"
            return case.model_copy(
                update={
                    "status": status,
                    "currentRunId": None,
                    "finalRunId": latest.runId,
                    "attempts": attempts,
                    "flaky": flaky,
                }
            )

    def _await_terminal(self, batch_id: str, run: RunSummary) -> RunSummary:
        current = run
        while str(current.status).upper() not in TERMINAL_STATUSES:
            batch = self.store.get_batch(batch_id)
            if not batch or batch.status == "CANCELLED":
                try:
                    return self.runs.cancel_run(current.runId)
                except RuntimeError:
                    return self.store.get_run(current.runId) or current
            _IDLE_WAIT.wait(0.2)
            current = self.store.get_run(current.runId) or current
        return current

    @staticmethod
    def _failure_kind(run: RunSummary) -> str:
        if str(run.status).upper() == "CANCELLED":
            return "cancelled"
        result = run.result or {}
        # A successful observational run can legitimately mention "agent-browser
        # network" in its evidence summary.  Keyword classification is only a fallback
        # once the run itself reports failure or an explicit execution error.
        if (
            str(run.status).upper() == "WAITING_FOR_REVIEW"
            and str(run.outcomeKind or "").lower() not in {
                "be_error",
                "business_error",
                "fe_error",
                "failure",
                "fail",
                "error",
            }
            and not result.get("error")
        ):
            return "none"
        error_text = " ".join(
            str(value or "")
            for value in [run.outcomeKind, run.outcomeSummary, run.observationSummary, result.get("error")]
        ).lower()
        infra_tokens = ("timeout", "connection", "browser", "network", "dns", "unavailable", "infra")
        if any(token in error_text for token in infra_tokens):
            return "infra"
        if str(run.status).upper() == "AUTO_FAILED" or str(run.outcomeKind or "").lower() in {
            "be_error",
            "business_error",
            "fe_error",
            "failure",
            "fail",
            "error",
        }:
            return "product"
        return "none"

    def _replace_case(self, batch_id: str, replacement: BatchCase) -> None:
        with _BATCH_MUTATION_LOCK:
            current = self.store.get_batch(batch_id)
            if not current or current.status == "CANCELLED":
                return
            cases = [replacement if case.caseId == replacement.caseId else case for case in current.cases]
            self.store.save_batch(current.model_copy(update={"cases": cases, "updatedAt": _now()}))

    def _claim_case(self, batch_id: str, case_id: str) -> BatchCase | None:
        """PENDING 케이스를 실행 큐에 한 번만 올리도록 원자적으로 선점한다."""
        with _BATCH_MUTATION_LOCK:
            current = self.store.get_batch(batch_id)
            if not current or current.status != "RUNNING":
                return None
            target = next((case for case in current.cases if case.caseId == case_id), None)
            if target is None or target.status != "PENDING":
                return None
            claimed = target.model_copy(update={"status": "RUNNING"})
            cases = [claimed if case.caseId == case_id else case for case in current.cases]
            self.store.save_batch(current.model_copy(update={"cases": cases, "updatedAt": _now()}))
            return claimed

    def summary(self, batch_id: str, owner_user_id: str) -> BatchSummary:
        item = self.get(batch_id, owner_user_id)
        counts = Counter(case.status for case in item.cases)
        done = sum(counts[key] for key in ["COMPLETED", "FAILED", "REVIEW_REQUIRED", "SKIPPED", "CANCELLED"])
        exceptions: list[BatchException] = []
        for case in item.cases:
            if case.status in {"COMPLETED", "PENDING", "RUNNING"} and not case.flaky:
                continue
            latest = case.attempts[-1] if case.attempts else None
            exceptions.append(
                BatchException(
                    caseId=case.caseId,
                    scenarioId=case.scenarioId,
                    category=case.category,
                    status=case.status,
                    kind=("flaky" if case.flaky else latest.failureKind if latest else "policy"),
                    detail=case.skipReason or (latest.outcomeSummary if latest else None),
                    runId=case.finalRunId,
                    reviewRequired=case.reviewRequired,
                    flaky=case.flaky,
                )
            )
        return BatchSummary(
            batchId=item.batchId,
            status=item.status,
            total=len(item.cases),
            pending=counts["PENDING"],
            running=counts["RUNNING"],
            completed=counts["COMPLETED"],
            failed=counts["FAILED"],
            skipped=counts["SKIPPED"],
            cancelled=counts["CANCELLED"],
            reviewRequired=counts["REVIEW_REQUIRED"],
            flaky=sum(1 for case in item.cases if case.flaky),
            evidenceReady=sum(
                1 for case in item.cases if case.attempts and case.attempts[-1].evidenceReady
            ),
            progressPercent=round(done / len(item.cases) * 100) if item.cases else 0,
            categoryCounts=dict(Counter(case.category for case in item.cases)),
            exceptions=exceptions,
        )
