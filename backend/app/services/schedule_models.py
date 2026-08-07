from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ScheduleStatus = Literal["ACTIVE", "PAUSED", "RUNNING", "COMPLETED", "ERROR"]
ScheduleTrigger = Literal["manual", "scheduled"]


class ScheduleScenarioRef(BaseModel):
    scenarioId: str
    scenarioName: str
    scenarioGroupId: str
    scenarioGroupName: str
    businessPath: list[str] = Field(default_factory=list)


class ScheduleExecution(BaseModel):
    executionId: str
    trigger: ScheduleTrigger
    startedAt: str
    completedAt: str | None = None
    runIds: list[str] = Field(default_factory=list)
    totalCount: int = 0
    completedCount: int = 0
    failedCount: int = 0
    status: Literal["RUNNING", "COMPLETED", "COMPLETED_WITH_FAILURES", "ERROR"] = "RUNNING"
    message: str | None = None


class ScheduleCreateRequest(BaseModel):
    scheduleId: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    projectId: str
    scenarioIds: list[str] = Field(min_length=1, max_length=200)
    environmentId: str | None = None
    cronExpression: str = Field(min_length=5, max_length=120)
    timezone: str = Field(default="Asia/Seoul", min_length=1, max_length=80)
    startDate: str | None = None
    endDate: str | None = None
    enabled: bool = True
    overlapPolicy: Literal["skip"] = "skip"
    naturalLanguage: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("scheduleId", "name", "projectId", "cronExpression", "timezone", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("scenarioIds")
    @classmethod
    def _unique_scenarios(cls, values: list[str]) -> list[str]:
        unique: list[str] = []
        for value in values:
            normalized = str(value).strip()
            if normalized and normalized not in unique:
                unique.append(normalized)
        if not unique:
            raise ValueError("scenarioIds required")
        return unique

    @model_validator(mode="after")
    def _date_order(self) -> "ScheduleCreateRequest":
        if self.startDate and self.endDate and self.startDate > self.endDate:
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다")
        return self


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    scenarioIds: list[str] | None = Field(default=None, min_length=1, max_length=200)
    environmentId: str | None = None
    cronExpression: str | None = Field(default=None, min_length=5, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    startDate: str | None = None
    endDate: str | None = None
    enabled: bool | None = None
    naturalLanguage: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2_000)


class ScheduleDefinition(BaseModel):
    scheduleId: str
    ownerUserId: str
    projectId: str
    projectName: str
    name: str
    scenarios: list[ScheduleScenarioRef]
    environmentId: str | None = None
    environmentName: str | None = None
    cronExpression: str
    cronSummary: str
    timezone: str
    startDate: str | None = None
    endDate: str | None = None
    enabled: bool = True
    overlapPolicy: Literal["skip"] = "skip"
    naturalLanguage: str | None = None
    note: str | None = None
    status: ScheduleStatus = "ACTIVE"
    nextRunAt: str | None = None
    lastRunAt: str | None = None
    runCount: int = 0
    progressCompleted: int = 0
    progressTotal: int = 0
    lastMessage: str | None = None
    lastExecution: ScheduleExecution | None = None
    createdAt: str
    updatedAt: str


class CronPreviewRequest(BaseModel):
    naturalLanguage: str = Field(min_length=2, max_length=500)
    timezone: str = Field(default="Asia/Seoul", min_length=1, max_length=80)


class CronPreviewResponse(BaseModel):
    cronExpression: str
    summary: str
    timezone: str
    suggestedStartDate: str | None = None
    suggestedEndDate: str | None = None
    nextRunAt: str | None = None
