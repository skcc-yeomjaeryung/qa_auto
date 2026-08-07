from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.services.environment_models import PILOT_SANDBOX_BASE_URL


class RunCreateRequest(BaseModel):
    consent: bool = False
    baseUrl: str = PILOT_SANDBOX_BASE_URL
    environmentId: str | None = None
    executionAccountId: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    inputProfileId: str | None = None
    headed: bool = False
    headers: dict[str, str] = Field(default_factory=dict)
    # Phase 13 — 건별 실행
    # interactive: 즉시 응답 후 백그라운드 실행 (Console이 step 진행을 폴링)
    # batch: 기존 동기 실행 (일괄·API 호출자 호환)
    mode: str = "batch"
    # 사용자가 추천값에서 바꾼 값만 명시 (감사·증적 구분용)
    overrides: dict[str, Any] = Field(default_factory=dict)
    # 화면이 본 버전을 그대로 되돌려 보내 stale 실행을 차단한다
    scenarioVersion: str | None = None
    inputProfileVersion: str | None = None
    # 이전 실행 입력 재사용 (재실행)
    reuseFromRunId: str | None = None
    # 데이터 변경 가능 단계는 실행 직전 Console의 명시 확인을 받은 건에만 허용한다.
    # 일반 API·배치 호출은 기본 False라 기존 destructive 차단 정책을 유지한다.
    allowDestructive: bool = False


class RunStepSummary(BaseModel):
    stepId: str
    action: str = ""
    mcpTool: str | None = None
    refOrLocator: str | None = None
    status: str = "queued"
    startedAt: str | None = None
    endedAt: str | None = None
    snapshotPath: str | None = None
    screenshotPath: str | None = None
    networkRefs: list[str] = Field(default_factory=list)
    observationSummary: str | None = None
    missingData: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    runId: str
    scenarioId: str
    projectId: str | None = None
    serviceId: str | None = None
    status: str = "QUEUED"
    browserRunner: str = "agent-browser-cli"
    consent: bool = False
    baseUrl: str | None = None
    environmentId: str | None = None
    environmentName: str | None = None
    executionAccountId: str | None = None
    executionAccountRole: str | None = None
    repositoryUrl: str | None = None
    branch: str | None = None
    commitSha: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    evidenceDir: str | None = None
    screenshotCount: int = 0
    snapshotCount: int = 0
    missingData: list[str] = Field(default_factory=list)
    observationSummary: str | None = None
    # success | be_error | business_error | fe_error | unknown
    outcomeKind: str | None = None
    outcomeSummary: str | None = None
    hitlRequired: bool = True
    createdAt: str | None = None
    updatedAt: str | None = None
    steps: list[RunStepSummary] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    # Phase 10 — Backend trace correlation
    testCaseId: str | None = None
    inputProfileId: str | None = None
    backendTraceStatus: str | None = None  # linked | partial | external_network_only
    backendTraceConstraint: str | None = None
    partialEvidence: bool = False
    # Phase 13 — 건별 실행 추적
    mode: str = "batch"
    scenarioVersion: str | None = None
    inputProfileVersion: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)
    reusedFromRunId: str | None = None
    plannedStepCount: int = 0
    progressPercent: int = 0
    currentStepId: str | None = None
    failedStepId: str | None = None
