from __future__ import annotations

from collections import Counter
from threading import Lock
from time import sleep

import pytest

from app.services.batch_models import BatchCreateRequest, BatchPolicy, ScenarioProfilePin
from app.services.batch_service import BatchService
from app.services.input_recommend_models import InputProfileSummary
from app.services.repository_models import ProjectCreate, utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.run_models import RunSummary
from app.services.scenario_models import ScenarioSummary


class FakeRuns:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store
        self.calls: Counter[str] = Counter()
        self.active = 0
        self.max_active = 0
        self.active_by_key: Counter[str] = Counter()
        self.max_active_by_key: Counter[str] = Counter()
        self.lock = Lock()

    def start_run(self, scenario_id, payload):
        key = str(payload.inputs.get("customerId") or "none")
        self.calls[key] += 1
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.active_by_key[key] += 1
            self.max_active_by_key[key] = max(self.max_active_by_key[key], self.active_by_key[key])
        sleep(0.01)
        first_infra = key == "FLAKY" and self.calls[key] == 1
        product = key == "PRODUCT"
        run = RunSummary(
            runId=f"RUN-{key}-{self.calls[key]}",
            scenarioId=scenario_id,
            projectId=self.store.get_scenario(scenario_id).projectId,
            status="AUTO_FAILED" if first_infra or product else "WAITING_FOR_REVIEW",
            outcomeKind="fe_error" if first_infra or product else "success",
            outcomeSummary="browser timeout" if first_infra else "assertion mismatch" if product else "observed",
            evidenceDir=f"/tmp/{key}",
            screenshotCount=1 if not first_infra and not product else 0,
            snapshotCount=1 if not first_infra and not product else 0,
            createdAt=utc_now().isoformat(),
        )
        self.store.save_run(run)
        with self.lock:
            self.active -= 1
            self.active_by_key[key] -= 1
        return run

    def cancel_run(self, run_id):
        run = self.store.get_run(run_id)
        if not run:
            raise LookupError(run_id)
        cancelled = run.model_copy(update={"status": "CANCELLED"})
        self.store.save_run(cancelled)
        return cancelled


@pytest.fixture
def seeded() -> tuple[InMemoryPlatformStore, str, list[ScenarioProfilePin]]:
    store = InMemoryPlatformStore()
    for attr in ("_projects", "_scenarios", "_profiles", "_runs", "_batches"):
        getattr(store, attr).clear()
    project = store.create_project(ProjectCreate(name="Phase 14", ownerUserId="TEST"))
    pins: list[ScenarioProfilePin] = []
    for index, customer in enumerate(["FLAKY", "PRODUCT", "LOCKED"]):
        scenario_id = f"SCN-{index}"
        profile_id = f"IP-{index}"
        store.save_scenario(
            ScenarioSummary(
                scenarioId=scenario_id,
                projectId=project.id,
                name=scenario_id,
                status="EXECUTABLE",
                version="3",
                result={"confidence": 0.9},
            )
        )
        store.save_profile(
            InputProfileSummary(
                profileId=profile_id,
                scenarioId=scenario_id,
                projectId=project.id,
                status="APPROVED",
                version="2",
                caseCount=1,
                categoryCounts={"happy_path": 1},
                result={
                    "cases": [
                        {
                            "caseId": f"CASE-{index}",
                            "category": "happy_path",
                            "inputs": {"customerId": customer},
                        }
                    ]
                },
            )
        )
        pins.append(ScenarioProfilePin(scenarioId=scenario_id, inputProfileId=profile_id))
    return store, project.id, pins


def test_success_summary_mentioning_agent_browser_network_is_not_infra() -> None:
    run = RunSummary(
        runId="RUN-network-success",
        scenarioId="SCN-login",
        status="WAITING_FOR_REVIEW",
        outcomeKind="success",
        outcomeSummary="agent-browser 네트워크에서 POST /login 응답을 관측했습니다",
        result={},
    )
    assert BatchService._failure_kind(run) == "none"


def test_batch_retries_only_infra_and_records_flaky(seeded) -> None:
    store, project_id, pins = seeded
    fake = FakeRuns(store)
    service = BatchService(store, fake)  # type: ignore[arg-type]
    batch = service.create(
        BatchCreateRequest(
            projectId=project_id,
            scenarioProfiles=pins,
            totalBudget=3,
            concurrency=3,
            policy=BatchPolicy(infraRetryCount=1, productRetryCount=0, projectRateLimit=2),
        ),
        "TEST",
    )
    store.save_batch(batch.model_copy(update={"status": "RUNNING", "startedAt": utc_now().isoformat()}))
    service._run_batch(batch.batchId)

    completed = store.get_batch(batch.batchId)
    assert completed is not None
    assert completed.status == "COMPLETED_WITH_FAILURES"
    by_customer = {case.inputs["customerId"]: case for case in completed.cases}
    assert len(by_customer["FLAKY"].attempts) == 2
    assert by_customer["FLAKY"].flaky is True
    assert by_customer["FLAKY"].status == "COMPLETED"
    assert len(by_customer["PRODUCT"].attempts) == 1
    assert by_customer["PRODUCT"].status == "FAILED"
    assert fake.max_active <= 2
    summary = service.summary(batch.batchId, "TEST")
    assert summary.flaky == 1
    assert summary.evidenceReady == 2
    assert summary.exceptions[0].kind in {"flaky", "product"}


def test_twenty_case_budget_versions_and_distribution_are_pinned(seeded) -> None:
    store, project_id, pins = seeded
    service = BatchService(store, FakeRuns(store))  # type: ignore[arg-type]
    payload = BatchCreateRequest(
        projectId=project_id,
        scenarioProfiles=pins,
        totalBudget=20,
        concurrency=4,
        policy=BatchPolicy(projectRateLimit=1),
    )
    batch = service.create(payload, "TEST")
    assert len(batch.cases) == 20
    assert all(case.scenarioVersion == "3" for case in batch.cases)
    assert all(case.inputProfileVersion == "2" for case in batch.cases)
    assert batch.categoryCounts == {"happy_path": 20}
    assert batch.concurrency == 4
    assert batch.policy.projectRateLimit == 1


def test_same_isolation_key_never_runs_concurrently(seeded) -> None:
    store, project_id, pins = seeded
    fake = FakeRuns(store)
    service = BatchService(store, fake)  # type: ignore[arg-type]
    batch = service.create(
        BatchCreateRequest(
            projectId=project_id,
            scenarioProfiles=[pins[2]],
            totalBudget=4,
            concurrency=4,
            policy=BatchPolicy(projectRateLimit=4, resourceLockFields=["customerId"]),
        ),
        "TEST",
    )
    store.save_batch(batch.model_copy(update={"status": "RUNNING", "startedAt": utc_now().isoformat()}))
    service._run_batch(batch.batchId)

    assert fake.calls["LOCKED"] == 4
    assert fake.max_active_by_key["LOCKED"] == 1


def test_unresolved_skip_and_pause_resume_cancel_state(seeded, monkeypatch) -> None:
    store, project_id, pins = seeded
    scenario = store.get_scenario(pins[0].scenarioId)
    store.save_scenario(scenario.model_copy(update={"unresolvedCount": 2}))
    service = BatchService(store, FakeRuns(store))  # type: ignore[arg-type]
    batch = service.create(
        BatchCreateRequest(projectId=project_id, scenarioProfiles=[pins[0]], totalBudget=1),
        "TEST",
    )
    assert batch.cases[0].status == "SKIPPED"
    running = store.save_batch(batch.model_copy(update={"status": "RUNNING"}))
    paused = service.pause(running.batchId, "TEST")
    assert paused.status == "PAUSED"
    monkeypatch.setattr(service, "_ensure_coordinator", lambda _batch_id: None)
    resumed = service.resume(paused.batchId, "TEST")
    assert resumed.status == "RUNNING"
    cancelled = service.cancel(resumed.batchId, "TEST")
    assert cancelled.status == "CANCELLED"
    assert cancelled.cases[0].status == "SKIPPED"


def test_policy_skips_complete_without_false_failure_status(seeded) -> None:
    store, project_id, pins = seeded
    scenario = store.get_scenario(pins[0].scenarioId)
    store.save_scenario(scenario.model_copy(update={"unresolvedCount": 1}))
    service = BatchService(store, FakeRuns(store))  # type: ignore[arg-type]
    batch = service.create(
        BatchCreateRequest(projectId=project_id, scenarioProfiles=[pins[0]], totalBudget=1),
        "TEST",
    )
    store.save_batch(batch.model_copy(update={"status": "RUNNING"}))

    service._run_batch(batch.batchId)

    completed = store.get_batch(batch.batchId)
    assert completed is not None
    assert completed.status == "COMPLETED"
    assert completed.cases[0].status == "SKIPPED"
    assert service.summary(batch.batchId, "TEST").skipped == 1
