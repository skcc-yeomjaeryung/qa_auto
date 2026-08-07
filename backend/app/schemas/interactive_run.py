"""Phase 13 — 건별(interactive) 시나리오 실행 Structured Output 계약.

사용자가 시나리오 1건을 최소 피로로 확인·수정·실행하기 위한 사전 요약(Run Preview)과
실행 진행(Live Progress) 계약을 정의한다. Pass/Fail 확정은 포함하지 않는다 (HITL).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RunMode = Literal["interactive", "batch"]
# inferred = 분석된 필드명·타입에서 rule로 만든 합성 테스트값 (실행 가능 · 사람 확인 권장)
InputConfidence = Literal["confirmed", "inferred", "review_required", "unresolved"]
PlanStage = Literal["a_input", "request", "b_ui"]


class RunPreviewScreen(BaseModel):
    """A 화면 / B 화면 요약."""

    screen: str = "missing_data"
    route: str | None = None
    routePattern: str | None = None


class RunPreviewApi(BaseModel):
    """실행 시 예상되는 Backend 호출 (Graph·Contract 근거)."""

    stepId: str | None = None
    method: str = "missing_data"
    path: str = "missing_data"


class RunPreviewField(BaseModel):
    """자동 인식된 입력 1건. `confidence`가 confirmed면 기본 접힘 대상."""

    field: str
    value: Any = None
    displayValue: str | None = None
    required: bool = False
    category: str | None = None
    expectedPath: str | None = None
    locator: str | None = None
    source: str | None = None
    rationale: str | None = None
    confidence: InputConfidence = "confirmed"
    synthesized: bool = False
    masked: bool = False
    editable: bool = True
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class RunPreviewStep(BaseModel):
    """실행 예정 step (Progress Type 4 스텝 라벨 재료)."""

    stepId: str
    action: str = ""
    stage: PlanStage = "a_input"
    target: str | None = None
    description: str = ""


class RunPreviewPreviousRun(BaseModel):
    """직전 실행 — 입력 재사용 후보."""

    runId: str
    status: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    outcomeKind: str | None = None
    createdAt: str | None = None


class RunPreview(BaseModel):
    """건별 실행 전 확인 요약 (A 화면 · 입력 · 예상 API · B 화면 · destructive)."""

    scenarioId: str
    scenarioName: str = ""
    scenarioVersion: str = "1"
    scenarioStatus: str = "DRAFT"
    projectId: str | None = None
    serviceId: str | None = None
    aScreen: RunPreviewScreen = Field(default_factory=RunPreviewScreen)
    bScreen: RunPreviewScreen = Field(default_factory=RunPreviewScreen)
    expectedApis: list[RunPreviewApi] = Field(default_factory=list)
    fields: list[RunPreviewField] = Field(default_factory=list)
    reviewFieldCount: int = 0
    inferredFieldCount: int = 0
    destructive: bool = False
    destructiveReasons: list[str] = Field(default_factory=list)
    plannedSteps: list[RunPreviewStep] = Field(default_factory=list)
    recommendationId: str | None = None
    inputProfileId: str | None = None
    inputProfileVersion: str | None = None
    inputProfileStatus: str | None = None
    commitRefs: dict[str, str] = Field(default_factory=dict)
    environmentId: str | None = None
    environmentName: str | None = None
    baseUrl: str | None = None
    previousRun: RunPreviewPreviousRun | None = None
    unresolved: list[dict[str, Any]] = Field(default_factory=list)
    missingData: list[str] = Field(default_factory=list)
    generatedAt: str | None = None


class RunPreviewRequest(BaseModel):
    environmentId: str | None = None
    inputProfileId: str | None = None
    reuseFromRunId: str | None = None
    refreshRecommendation: bool = False
