from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from threading import Event, RLock, Thread
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.run_models import RunCreateRequest
from app.services.run_service import BrowserRunService
from app.services.schedule_models import (
    CronPreviewResponse,
    ScheduleCreateRequest,
    ScheduleDefinition,
    ScheduleExecution,
    ScheduleScenarioRef,
    ScheduleUpdateRequest,
)
from app.services.sqlite_persist import kv_get, kv_set


SCHEDULE_KV_KEY = "schedule_catalog_v1"
ACTIVE_RUN_STATUSES = {"QUEUED", "PREPARING", "RUNNING", "IN_PROGRESS", "ACTIVE", "STARTED"}
FAILED_RUN_STATUSES = {"AUTO_FAILED", "CANCELLED"}
_SCHEDULE_LOCK = RLock()
_COORDINATOR_STOP = Event()
_COORDINATOR_THREAD: Thread | None = None


def _now() -> str:
    return utc_now().isoformat()


class ScheduleRepository:
    """SQLite-backed repository boundary for future database replacement."""

    def list_all(self) -> list[ScheduleDefinition]:
        with _SCHEDULE_LOCK:
            raw = kv_get(SCHEDULE_KV_KEY)
            rows = raw if isinstance(raw, list) else []
            out: list[ScheduleDefinition] = []
            for row in rows:
                try:
                    out.append(ScheduleDefinition.model_validate(row))
                except Exception:
                    continue
            return out

    def get(self, schedule_id: str) -> ScheduleDefinition | None:
        return next((item for item in self.list_all() if item.scheduleId == schedule_id), None)

    def save(self, item: ScheduleDefinition) -> ScheduleDefinition:
        with _SCHEDULE_LOCK:
            rows = self.list_all()
            replaced = False
            next_rows: list[ScheduleDefinition] = []
            for row in rows:
                if row.scheduleId == item.scheduleId:
                    next_rows.append(item)
                    replaced = True
                else:
                    next_rows.append(row)
            if not replaced:
                next_rows.append(item)
            kv_set(SCHEDULE_KV_KEY, [row.model_dump(mode="json") for row in next_rows])
            return item

    def delete_many(self, schedule_ids: list[str], owner_user_id: str) -> int:
        targets = set(schedule_ids)
        with _SCHEDULE_LOCK:
            rows = self.list_all()
            kept = [row for row in rows if not (row.scheduleId in targets and row.ownerUserId == owner_user_id)]
            removed = len(rows) - len(kept)
            kv_set(SCHEDULE_KV_KEY, [row.model_dump(mode="json") for row in kept])
            return removed


class ScheduleService:
    def __init__(
        self,
        store: InMemoryPlatformStore,
        repository: ScheduleRepository | None = None,
        run_service: BrowserRunService | None = None,
    ) -> None:
        self.store = store
        self.repository = repository or ScheduleRepository()
        self.runs = run_service or BrowserRunService(store)

    def list(self, owner_user_id: str) -> list[ScheduleDefinition]:
        rows = [row for row in self.repository.list_all() if row.ownerUserId == owner_user_id]
        refreshed = [self._refresh_execution(row) for row in rows]
        return sorted(refreshed, key=lambda row: row.updatedAt, reverse=True)

    def get(self, schedule_id: str, owner_user_id: str) -> ScheduleDefinition:
        item = self.repository.get(schedule_id)
        if not item:
            raise LookupError(f"schedule not found: {schedule_id}")
        if item.ownerUserId != owner_user_id:
            raise PermissionError("다른 사용자의 스케줄은 조회할 수 없습니다")
        return self._refresh_execution(item)

    def create(self, payload: ScheduleCreateRequest, owner_user_id: str) -> ScheduleDefinition:
        if self.repository.get(payload.scheduleId):
            raise ValueError("이미 사용 중인 스케줄 ID입니다")
        project, scenarios, environment = self._validate_scope(
            payload.projectId, payload.scenarioIds, payload.environmentId, owner_user_id
        )
        validate_cron(payload.cronExpression)
        validate_timezone(payload.timezone)
        now = _now()
        definition = ScheduleDefinition(
            scheduleId=payload.scheduleId,
            ownerUserId=owner_user_id,
            projectId=project.id,
            projectName=project.name,
            name=payload.name,
            scenarios=self._scenario_refs(scenarios, project.name),
            environmentId=environment.id if environment else None,
            environmentName=environment.name if environment else None,
            cronExpression=payload.cronExpression,
            cronSummary=cron_summary(payload.cronExpression),
            timezone=payload.timezone,
            startDate=payload.startDate,
            endDate=payload.endDate,
            enabled=payload.enabled,
            overlapPolicy=payload.overlapPolicy,
            naturalLanguage=payload.naturalLanguage,
            note=payload.note,
            status="ACTIVE" if payload.enabled else "PAUSED",
            nextRunAt=next_run_at(
                payload.cronExpression,
                payload.timezone,
                start_date=payload.startDate,
                end_date=payload.endDate,
            ),
            createdAt=now,
            updatedAt=now,
        )
        if definition.enabled and not definition.nextRunAt:
            definition = definition.model_copy(update={"status": "COMPLETED"})
        return self.repository.save(definition)

    def update(
        self,
        schedule_id: str,
        payload: ScheduleUpdateRequest,
        owner_user_id: str,
    ) -> ScheduleDefinition:
        item = self.get(schedule_id, owner_user_id)
        data = payload.model_dump(exclude_unset=True)
        scenario_ids = data.pop("scenarioIds", None)
        environment_id = data.get("environmentId", item.environmentId)
        project, scenarios, environment = self._validate_scope(
            item.projectId,
            scenario_ids or [row.scenarioId for row in item.scenarios],
            environment_id,
            owner_user_id,
        )
        cron = str(data.get("cronExpression") or item.cronExpression)
        tz = str(data.get("timezone") or item.timezone)
        validate_cron(cron)
        validate_timezone(tz)
        start = data.get("startDate", item.startDate)
        end = data.get("endDate", item.endDate)
        if start and end and start > end:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다")
        enabled = bool(data.get("enabled", item.enabled))
        updates = {
            **data,
            "projectName": project.name,
            "scenarios": self._scenario_refs(scenarios, project.name),
            "environmentId": environment.id if environment else None,
            "environmentName": environment.name if environment else None,
            "cronExpression": cron,
            "cronSummary": cron_summary(cron),
            "timezone": tz,
            "enabled": enabled,
            "status": "ACTIVE" if enabled else "PAUSED",
            "nextRunAt": next_run_at(cron, tz, start_date=start, end_date=end),
            "updatedAt": _now(),
        }
        updated = item.model_copy(update=updates)
        if enabled and not updated.nextRunAt:
            updated = updated.model_copy(update={"status": "COMPLETED"})
        return self.repository.save(updated)

    def delete_many(self, schedule_ids: list[str], owner_user_id: str) -> int:
        if not schedule_ids:
            raise ValueError("scheduleIds required")
        return self.repository.delete_many(schedule_ids, owner_user_id)

    def execute(
        self,
        schedule_id: str,
        owner_user_id: str,
        *,
        trigger: str = "manual",
    ) -> ScheduleDefinition:
        item = self.get(schedule_id, owner_user_id)
        if item.lastExecution and item.lastExecution.status == "RUNNING":
            skipped = item.model_copy(
                update={
                    "lastMessage": "이전 실행이 진행 중이라 중복 실행을 건너뛰었습니다.",
                    "updatedAt": _now(),
                }
            )
            return self.repository.save(skipped)

        project, scenarios, environment = self._validate_scope(
            item.projectId,
            [row.scenarioId for row in item.scenarios],
            item.environmentId,
            owner_user_id,
        )
        if environment is None:
            environments = self.store.list_environments(project.id)
            environment = next(
                (
                    row
                    for row in environments
                    if str(getattr(row.status, "value", row.status)) == "active"
                ),
                environments[0] if environments else None,
            )
        if environment is None:
            raise ValueError("프로젝트 실행환경을 먼저 등록하세요")

        run_ids: list[str] = []
        errors: list[str] = []
        for scenario in scenarios:
            try:
                run = self.runs.start_run(
                    scenario.scenarioId,
                    RunCreateRequest(
                        consent=True,
                        environmentId=environment.id,
                        mode="interactive",
                        scenarioVersion=str(scenario.version or "1"),
                        allowDestructive=False,
                    ),
                )
                run_ids.append(run.runId)
            except Exception as exc:  # noqa: BLE001 — 스케줄 목록에 실행 실패 사유 보존
                errors.append(f"{scenario.scenarioId}: {exc}")

        started_at = _now()
        execution = ScheduleExecution(
            executionId=f"SE-{uuid4().hex[:12]}",
            trigger="scheduled" if trigger == "scheduled" else "manual",
            startedAt=started_at,
            runIds=run_ids,
            totalCount=len(scenarios),
            failedCount=len(errors),
            status="RUNNING" if run_ids else "ERROR",
            message=" · ".join(errors[:3]) if errors else None,
        )
        next_at = next_run_at(
            item.cronExpression,
            item.timezone,
            start_date=item.startDate,
            end_date=item.endDate,
            after=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        updated = item.model_copy(
            update={
                "environmentId": environment.id,
                "environmentName": environment.name,
                "status": "RUNNING" if run_ids else "ERROR",
                "lastRunAt": started_at,
                "lastExecution": execution,
                "runCount": item.runCount + len(run_ids),
                "progressCompleted": 0,
                "progressTotal": len(scenarios),
                "nextRunAt": next_at,
                "lastMessage": execution.message or f"{len(run_ids)}건 실행을 시작했습니다.",
                "updatedAt": started_at,
            }
        )
        return self.repository.save(updated)

    def tick(self) -> None:
        now = datetime.now(timezone.utc)
        for item in self.repository.list_all():
            current = self._refresh_execution(item)
            if not current.enabled or not current.nextRunAt or current.status == "RUNNING":
                continue
            try:
                due = datetime.fromisoformat(current.nextRunAt.replace("Z", "+00:00"))
            except ValueError:
                continue
            if due <= now:
                try:
                    self.execute(current.scheduleId, current.ownerUserId, trigger="scheduled")
                except Exception as exc:  # noqa: BLE001
                    self.repository.save(
                        current.model_copy(
                            update={
                                "status": "ERROR",
                                "lastMessage": str(exc),
                                "updatedAt": _now(),
                                "nextRunAt": next_run_at(
                                    current.cronExpression,
                                    current.timezone,
                                    start_date=current.startDate,
                                    end_date=current.endDate,
                                    after=now + timedelta(minutes=1),
                                ),
                            }
                        )
                    )

    def _refresh_execution(self, item: ScheduleDefinition) -> ScheduleDefinition:
        execution = item.lastExecution
        if not execution or execution.status != "RUNNING":
            return item
        runs = [self.runs.get_run(run_id) for run_id in execution.runIds]
        completed = sum(1 for run in runs if run and str(run.status).upper() not in ACTIVE_RUN_STATUSES)
        failed = execution.failedCount + sum(
            1 for run in runs if run and str(run.status).upper() in FAILED_RUN_STATUSES
        )
        if completed < len(execution.runIds):
            if completed == item.progressCompleted:
                return item
            updated = item.model_copy(
                update={"progressCompleted": completed, "updatedAt": _now()}
            )
            return self.repository.save(updated)
        final_status = "COMPLETED_WITH_FAILURES" if failed else "COMPLETED"
        finished = execution.model_copy(
            update={
                "completedAt": _now(),
                "completedCount": completed,
                "failedCount": failed,
                "status": final_status,
            }
        )
        schedule_status = "ACTIVE" if item.enabled and item.nextRunAt else "COMPLETED"
        updated = item.model_copy(
            update={
                "status": schedule_status,
                "lastExecution": finished,
                "progressCompleted": completed,
                "lastMessage": (
                    f"기술 실행 {completed}/{execution.totalCount}건 완료 · 예외 {failed}건"
                ),
                "updatedAt": _now(),
            }
        )
        return self.repository.save(updated)

    def _validate_scope(
        self,
        project_id: str,
        scenario_ids: list[str],
        environment_id: str | None,
        owner_user_id: str,
    ):
        project = self.store.get_project(project_id)
        if not project:
            raise LookupError(f"project not found: {project_id}")
        if project.ownerUserId != owner_user_id:
            raise PermissionError("다른 사용자의 프로젝트에는 스케줄을 만들 수 없습니다")
        scenarios = []
        for scenario_id in scenario_ids:
            scenario = self.store.get_scenario(scenario_id)
            if not scenario or scenario.projectId != project_id:
                raise ValueError(f"프로젝트에 속하지 않은 시나리오입니다: {scenario_id}")
            scenarios.append(scenario)
        environment = self.store.get_environment(environment_id) if environment_id else None
        if environment_id and (not environment or environment.projectId != project_id):
            raise ValueError("실행환경이 선택한 프로젝트에 속하지 않습니다")
        return project, scenarios, environment

    def _scenario_refs(self, scenarios, project_name: str) -> list[ScheduleScenarioRef]:
        refs: list[ScheduleScenarioRef] = []
        set_names = {
            str(row.get("setId")): str(row.get("repositoryName") or "테스트 시나리오")
            for row in _scenario_sets_for_store(self.store)
        }
        for scenario in scenarios:
            graph_id = str(
                scenario.graphId
                or ((scenario.result or {}).get("sourceRefs") or {}).get("graphId")
                or f"{scenario.projectId}:unlinked"
            )
            repository_name = set_names.get(graph_id) or "테스트 시나리오"
            refs.append(
                ScheduleScenarioRef(
                    scenarioId=scenario.scenarioId,
                    scenarioName=scenario.name or scenario.scenarioId,
                    scenarioGroupId=graph_id,
                    scenarioGroupName=f"{project_name} · {repository_name} 그룹",
                    businessPath=list(scenario.businessPath or []),
                )
            )
        return refs


def _scenario_sets_for_store(store: InMemoryPlatformStore) -> list[dict]:
    from app.services.console_service import ConsoleService

    return ConsoleService(store).list_scenario_sets()


def validate_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"지원하지 않는 시간대입니다: {value}") from exc


def validate_cron(expression: str) -> tuple[str, str, str, str, str]:
    fields = tuple(expression.strip().split())
    if len(fields) != 5:
        raise ValueError("크론은 분 시 일 월 요일의 5개 필드로 입력하세요. 예: 0 5 * * *")
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    for field, bounds in zip(fields, ranges, strict=True):
        _validate_cron_field(field, *bounds)
    return fields  # type: ignore[return-value]


def _validate_cron_field(field: str, minimum: int, maximum: int) -> None:
    for part in field.split(","):
        base, _, step = part.partition("/")
        if step and (not step.isdigit() or int(step) <= 0):
            raise ValueError(f"잘못된 크론 step입니다: {part}")
        if base == "*":
            continue
        if "-" in base:
            left, right = base.split("-", 1)
            if not left.isdigit() or not right.isdigit():
                raise ValueError(f"잘못된 크론 범위입니다: {part}")
            values = [int(left), int(right)]
        elif base.isdigit():
            values = [int(base)]
        else:
            raise ValueError(f"잘못된 크론 필드입니다: {part}")
        if any(value < minimum or value > maximum for value in values):
            raise ValueError(f"크론 값 범위를 벗어났습니다: {part}")


def cron_matches(expression: str, moment: datetime) -> bool:
    minute, hour, day, month, weekday = validate_cron(expression)
    cron_weekday = (moment.weekday() + 1) % 7
    return all(
        [
            _field_matches(minute, moment.minute, 0, 59),
            _field_matches(hour, moment.hour, 0, 23),
            _field_matches(day, moment.day, 1, 31),
            _field_matches(month, moment.month, 1, 12),
            _field_matches(weekday, cron_weekday, 0, 7, sunday_alias=True),
        ]
    )


def _field_matches(
    field: str,
    value: int,
    minimum: int,
    maximum: int,
    *,
    sunday_alias: bool = False,
) -> bool:
    for part in field.split(","):
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if base == "*":
            if (value - minimum) % step == 0:
                return True
            continue
        if "-" in base:
            left, right = [int(item) for item in base.split("-", 1)]
            candidate = 7 if sunday_alias and value == 0 and right == 7 else value
            if left <= candidate <= right and (candidate - left) % step == 0:
                return True
            continue
        candidate = int(base)
        if sunday_alias and candidate == 7:
            candidate = 0
        if candidate == value:
            return True
    return False


def next_run_at(
    expression: str,
    timezone_name: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    after: datetime | None = None,
) -> str | None:
    tz = validate_timezone(timezone_name)
    validate_cron(expression)
    cursor = (after or datetime.now(timezone.utc)).astimezone(tz)
    cursor = cursor.replace(second=0, microsecond=0) + timedelta(minutes=1)
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    for _ in range(60 * 24 * 366):
        current_date = cursor.date()
        if end and current_date > end:
            return None
        if (not start or current_date >= start) and cron_matches(expression, cursor):
            return cursor.astimezone(timezone.utc).isoformat()
        cursor += timedelta(minutes=1)
    return None


def cron_summary(expression: str) -> str:
    minute, hour, day, month, weekday = validate_cron(expression)
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday == "*":
        return f"매일 {int(hour):02d}:{int(minute):02d}"
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday == "1-5":
        return f"평일 {int(hour):02d}:{int(minute):02d}"
    if minute.isdigit() and hour.isdigit() and day == "*" and month == "*" and weekday.isdigit():
        labels = ["일", "월", "화", "수", "목", "금", "토", "일"]
        return f"매주 {labels[int(weekday)]}요일 {int(hour):02d}:{int(minute):02d}"
    if minute.isdigit() and hour.isdigit() and month == "*" and weekday == "*" and day.isdigit():
        return f"매월 {day}일 {int(hour):02d}:{int(minute):02d}"
    return f"크론 {expression}"


def natural_language_cron(text: str, timezone_name: str) -> CronPreviewResponse:
    phrase = re.sub(r"\s+", " ", text.strip())
    tz = validate_timezone(timezone_name)
    hour, minute = _extract_time(phrase)
    weekday_map = {"일": 0, "월": 1, "화": 2, "수": 3, "목": 4, "금": 5, "토": 6}
    start = datetime.now(tz).date()
    end: date | None = None

    monthly = re.search(r"매월\s*(\d{1,2})일", phrase)
    weekly = re.search(r"매주\s*([월화수목금토일])(?:요일)?", phrase)
    if monthly:
        day = int(monthly.group(1))
        if day < 1 or day > 31:
            raise ValueError("매월 실행일은 1~31일로 입력하세요")
        cron = f"{minute} {hour} {day} * *"
    elif "평일" in phrase:
        cron = f"{minute} {hour} * * 1-5"
    elif "주말" in phrase:
        cron = f"{minute} {hour} * * 0,6"
    elif weekly:
        cron = f"{minute} {hour} * * {weekday_map[weekly.group(1)]}"
    elif any(token in phrase for token in ["매일", "매일마다", "일주일 동안", "매일 실행"]):
        cron = f"{minute} {hour} * * *"
    else:
        raise ValueError("반복 주기를 인식하지 못했습니다. 예: 매일 새벽 5시, 매주 월요일 오전 9시")

    if "일주일 동안" in phrase:
        end = start + timedelta(days=6)
    return CronPreviewResponse(
        cronExpression=cron,
        summary=cron_summary(cron),
        timezone=timezone_name,
        suggestedStartDate=start.isoformat() if end else None,
        suggestedEndDate=end.isoformat() if end else None,
        nextRunAt=next_run_at(
            cron,
            timezone_name,
            start_date=start.isoformat() if end else None,
            end_date=end.isoformat() if end else None,
        ),
    )


def _extract_time(phrase: str) -> tuple[int, int]:
    if "자정" in phrase:
        return 0, 0
    if "정오" in phrase:
        return 12, 0
    match = re.search(r"(\d{1,2})시(?:\s*(\d{1,2})분)?", phrase)
    if not match:
        raise ValueError("실행 시간을 인식하지 못했습니다. 예: 새벽 5시, 오전 9시 30분")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if "오후" in phrase and hour < 12:
        hour += 12
    if "오전" in phrase and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError("시간은 00:00~23:59 범위로 입력하세요")
    return hour, minute


def start_schedule_coordinator(store_provider: Callable[[], InMemoryPlatformStore]) -> None:
    global _COORDINATOR_THREAD
    if _COORDINATOR_THREAD and _COORDINATOR_THREAD.is_alive():
        return
    _COORDINATOR_STOP.clear()

    def loop() -> None:
        while not _COORDINATOR_STOP.is_set():
            try:
                ScheduleService(store_provider()).tick()
            except Exception:
                pass
            _COORDINATOR_STOP.wait(15)

    _COORDINATOR_THREAD = Thread(target=loop, daemon=True, name="schedule-coordinator")
    _COORDINATOR_THREAD.start()


def stop_schedule_coordinator() -> None:
    _COORDINATOR_STOP.set()
    if _COORDINATOR_THREAD and _COORDINATOR_THREAD.is_alive():
        _COORDINATOR_THREAD.join(timeout=1)
