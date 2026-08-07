from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


BackendEventName = Literal[
    "request_received",
    "validation_passed",
    "validation_failed",
    "controller_entered",
    "service_called",
    "response_returned",
    "exception_mapped",
]

TelemetrySource = Literal["spring", "http_ingest", "file", "otel", "browser_network"]


class BackendTelemetryEvent(BaseModel):
    timestamp: str
    event: BackendEventName
    testRunId: str
    scenarioId: str | None = None
    scenarioVersion: str | None = None
    testCaseId: str | None = None
    inputProfileId: str | None = None
    requestSequence: int = 1
    controller: str | None = None
    service: str | None = None
    httpMethod: str | None = None
    path: str | None = None
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    status: int | None = None
    durationMs: int | None = None
    maskedFields: list[str] = Field(default_factory=list)
    truncated: bool = False
    truncationMeta: dict[str, Any] | None = None
    source: TelemetrySource = "http_ingest"
    constraint: str | None = None
    errorType: str | None = None
    errorMessage: str | None = None


class BackendTelemetryIngestRequest(BaseModel):
    events: list[BackendTelemetryEvent] = Field(default_factory=list)


class BackendTelemetryIngestResponse(BaseModel):
    accepted: int
    testRunIds: list[str] = Field(default_factory=list)
    sequences: dict[str, int] = Field(default_factory=dict)


class TimelineEntry(BaseModel):
    order: int
    kind: str
    title: str
    timestamp: str | None = None
    status: str | None = None
    detail: str | None = None
    maskedFields: list[str] = Field(default_factory=list)
    truncated: bool = False
    requestSequence: int | None = None
    source: str | None = None
    constraint: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunTimelineResponse(BaseModel):
    runId: str
    backendTraceStatus: str
    partialEvidence: bool = False
    constraints: list[str] = Field(default_factory=list)
    entries: list[TimelineEntry] = Field(default_factory=list)
    backendEventCount: int = 0
