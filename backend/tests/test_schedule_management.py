from __future__ import annotations

from app.services.environment_models import ExecutionEnvironmentCreate
from app.services.repository_models import ProjectCreate, utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.run_models import RunSummary
from app.services.schedule_models import ScheduleCreateRequest
from app.services.schedule_service import (
    ScheduleRepository,
    ScheduleService,
    natural_language_cron,
    next_run_at,
)
from app.services.scenario_models import ScenarioSummary


class MemoryScheduleRepository:
    def __init__(self) -> None:
        self.rows = {}

    def list_all(self):
        return list(self.rows.values())

    def get(self, schedule_id):
        return self.rows.get(schedule_id)

    def save(self, item):
        self.rows[item.scheduleId] = item
        return item

    def delete_many(self, schedule_ids, owner_user_id):
        removed = 0
        for schedule_id in schedule_ids:
            row = self.rows.get(schedule_id)
            if row and row.ownerUserId == owner_user_id:
                del self.rows[schedule_id]
                removed += 1
        return removed


class FakeRuns:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def start_run(self, scenario_id, payload):
        run = RunSummary(
            runId=f"RUN-{scenario_id}",
            scenarioId=scenario_id,
            projectId=self.store.get_scenario(scenario_id).projectId,
            status="WAITING_FOR_REVIEW",
            screenshotCount=1,
            snapshotCount=1,
            createdAt=utc_now().isoformat(),
        )
        self.store.save_run(run)
        return run

    def get_run(self, run_id):
        return self.store.get_run(run_id)


def seeded_store() -> tuple[InMemoryPlatformStore, str, str, str]:
    store = InMemoryPlatformStore()
    for attr in ("_projects", "_scenarios", "_runs", "_environments"):
        getattr(store, attr).clear()
    project = store.create_project(ProjectCreate(name="스케줄 프로젝트", ownerUserId="TEST"))
    scenario = store.save_scenario(
        ScenarioSummary(
            scenarioId="SCN-SCHEDULE-001",
            projectId=project.id,
            graphId="IG-SCHEDULE",
            name="로그인 후 잔액 확인",
            businessPath=["금융 거래", "잔액 담당", "로그인 후 잔액 확인"],
        )
    )
    environment = store.create_environment(
        project.id,
        ExecutionEnvironmentCreate(
            name="테스트 환경",
            frontendBaseUrl="https://example.test",
            loginId="tester",
            loginPassword="secret",
        ),
    )
    return store, project.id, scenario.scenarioId, environment.id


def test_natural_language_cron_and_date_window() -> None:
    preview = natural_language_cron("일주일 동안 매일 새벽 5시에 돌려줘", "Asia/Seoul")
    assert preview.cronExpression == "0 5 * * *"
    assert preview.summary == "매일 05:00"
    assert preview.suggestedStartDate is not None
    assert preview.suggestedEndDate is not None
    assert preview.nextRunAt is not None
    assert next_run_at("0 9 * * 1-5", "Asia/Seoul") is not None


def test_schedule_crud_scope_execute_and_overlap_guard() -> None:
    store, project_id, scenario_id, environment_id = seeded_store()
    repository = MemoryScheduleRepository()
    service = ScheduleService(store, repository, FakeRuns(store))  # type: ignore[arg-type]
    schedule = service.create(
        ScheduleCreateRequest(
            scheduleId="SCH-DAILY-0500",
            name="매일 새벽 잔액 확인",
            projectId=project_id,
            scenarioIds=[scenario_id],
            environmentId=environment_id,
            cronExpression="0 5 * * *",
            timezone="Asia/Seoul",
        ),
        "TEST",
    )
    assert schedule.status == "ACTIVE"
    assert schedule.scenarios[0].scenarioId == scenario_id
    assert schedule.nextRunAt is not None

    running = service.execute(schedule.scheduleId, "TEST")
    assert running.lastExecution is not None
    assert running.lastExecution.totalCount == 1
    assert running.runCount == 1
    completed = service.get(schedule.scheduleId, "TEST")
    assert completed.progressCompleted == 1
    assert completed.lastExecution.status == "COMPLETED"

    store.save_run(
        RunSummary(
            runId="RUN-ACTIVE",
            scenarioId=scenario_id,
            projectId=project_id,
            status="RUNNING",
            createdAt=utc_now().isoformat(),
        )
    )
    repository.save(
        completed.model_copy(
            update={
                "status": "RUNNING",
                "lastExecution": completed.lastExecution.model_copy(
                    update={"status": "RUNNING", "runIds": ["RUN-ACTIVE"], "completedAt": None}
                ),
            }
        )
    )
    skipped = service.execute(schedule.scheduleId, "TEST")
    assert "중복 실행" in (skipped.lastMessage or "")
    assert skipped.runCount == 1

    assert service.delete_many([schedule.scheduleId], "TEST") == 1
    assert service.list("TEST") == []


def test_schedule_repository_uses_sqlite_catalog(monkeypatch) -> None:
    state = {}
    monkeypatch.setattr("app.services.schedule_service.kv_get", lambda key: state.get(key))
    monkeypatch.setattr("app.services.schedule_service.kv_set", lambda key, value: state.__setitem__(key, value))
    store, project_id, scenario_id, _ = seeded_store()
    repository = ScheduleRepository()
    service = ScheduleService(store, repository, FakeRuns(store))  # type: ignore[arg-type]
    saved = service.create(
        ScheduleCreateRequest(
            scheduleId="SCH-SQLITE-001",
            name="SQLite 저장 검증",
            projectId=project_id,
            scenarioIds=[scenario_id],
            cronExpression="0 6 * * *",
        ),
        "TEST",
    )
    assert state["schedule_catalog_v1"][0]["scheduleId"] == saved.scheduleId
    assert ScheduleRepository().get(saved.scheduleId) is not None
