from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


BatchStatus = Literal[
    "DRAFT",
    "READY",
    "RUNNING",
    "PAUSED",
    "COMPLETED",
    "COMPLETED_WITH_FAILURES",
    "CANCELLED",
]
BatchCaseStatus = Literal[
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "REVIEW_REQUIRED",
    "SKIPPED",
    "CANCELLED",
]


class BatchPolicy(BaseModel):
    unresolvedAction: Literal["skip_notify", "review_required"] = "skip_notify"
    destructiveAction: Literal["exclude", "review_required"] = "exclude"
    lowConfidenceAction: Literal["review_required", "include"] = "review_required"
    infraRetryCount: int = Field(default=1, ge=0, le=3)
    productRetryCount: int = Field(default=0, ge=0, le=1)
    projectRateLimit: int = Field(default=2, ge=1, le=8)
    resourceLockFields: list[str] = Field(
        default_factory=lambda: ["customerId", "accountId", "resourceId"]
    )


class ScenarioProfilePin(BaseModel):
    scenarioId: str
    inputProfileId: str


class BatchCreateRequest(BaseModel):
    projectId: str
    name: str = Field(default="무인 반복 배치", min_length=1, max_length=160)
    scenarioProfiles: list[ScenarioProfilePin] = Field(min_length=1)
    environmentId: str | None = None
    totalBudget: int = Field(default=20, ge=1, le=200)
    categoryCounts: dict[str, int] = Field(default_factory=dict)
    concurrency: int = Field(default=2, ge=1, le=8)
    policy: BatchPolicy = Field(default_factory=BatchPolicy)
    ready: bool = True


class BatchAttempt(BaseModel):
    attempt: int
    runId: str | None = None
    status: str
    failureKind: Literal["none", "infra", "product", "cancelled"] = "none"
    outcomeKind: str | None = None
    outcomeSummary: str | None = None
    screenshotCount: int = 0
    snapshotCount: int = 0
    evidenceReady: bool = False
    startedAt: str
    endedAt: str | None = None


class BatchCase(BaseModel):
    caseId: str
    sourceCaseId: str | None = None
    scenarioId: str
    scenarioVersion: str
    inputProfileId: str
    inputProfileVersion: str
    category: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    isolationKey: str
    status: BatchCaseStatus = "PENDING"
    reviewRequired: bool = False
    skipReason: str | None = None
    currentRunId: str | None = None
    finalRunId: str | None = None
    flaky: bool = False
    attempts: list[BatchAttempt] = Field(default_factory=list)


class BatchDefinition(BaseModel):
    batchId: str
    ownerUserId: str
    projectId: str
    name: str
    status: BatchStatus
    scenarioProfiles: list[ScenarioProfilePin]
    environmentId: str | None = None
    totalBudget: int
    categoryCounts: dict[str, int] = Field(default_factory=dict)
    concurrency: int
    policy: BatchPolicy
    cases: list[BatchCase] = Field(default_factory=list)
    createdAt: str
    updatedAt: str
    startedAt: str | None = None
    endedAt: str | None = None


class BatchException(BaseModel):
    caseId: str
    scenarioId: str
    category: str
    status: str
    kind: str
    detail: str | None = None
    runId: str | None = None
    reviewRequired: bool = False
    flaky: bool = False


class BatchSummary(BaseModel):
    batchId: str
    status: BatchStatus
    total: int = 0
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: int = 0
    reviewRequired: int = 0
    flaky: int = 0
    evidenceReady: int = 0
    progressPercent: int = 0
    categoryCounts: dict[str, int] = Field(default_factory=dict)
    exceptions: list[BatchException] = Field(default_factory=list)
