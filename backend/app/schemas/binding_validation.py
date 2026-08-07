from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AssertionResult = Literal["MATCH", "MISMATCH", "MISSING_DATA", "REVIEW_REQUIRED"]
TechnicalStatus = Literal[
    "TECHNICALLY_MATCHED",
    "TECHNICAL_MISMATCH",
    "PARTIAL",
    "BLOCKED",
]


class BindingValidateRequest(BaseModel):
    """Runtime observations not already present in Run/Telemetry artifacts."""

    uiValues: dict[str, Any] = Field(default_factory=dict)
    frontendRequest: dict[str, Any] = Field(default_factory=dict)
    currentRoute: str | None = None
    visibleFields: list[str] = Field(default_factory=list)
    responseSchemaValid: bool | None = None
    enumLabels: dict[str, dict[str, str]] = Field(default_factory=dict)
    screenshotRegions: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BindingAssertion(BaseModel):
    assertionId: str
    field: str
    source: str
    target: str
    aInput: Any = None
    frontendRequest: Any = None
    backendRequest: Any = None
    backendResponse: Any = None
    uiValue: Any = None
    expected: Any = None
    actual: Any = None
    normalizedExpected: Any = None
    normalizedActual: Any = None
    normalizers: list[str] = Field(default_factory=list)
    result: AssertionResult
    businessReviewRequired: bool = False
    hard: bool = False
    masked: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)
    missingData: list[str] = Field(default_factory=list)


class BindingValidationResult(BaseModel):
    runId: str
    scenarioId: str
    contractId: str | None = None
    technicalStatus: TechnicalStatus
    businessReviewRequired: bool = False
    assertions: list[BindingAssertion] = Field(default_factory=list)
    missingData: list[str] = Field(default_factory=list)
    createdAt: str
    artifactPath: str | None = None
