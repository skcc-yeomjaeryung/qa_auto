from __future__ import annotations

import re
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.services.sqlite_persist import kv_get, kv_set

AGENT_EVENTS_KEY = "agent_events_v1"
_SENSITIVE = re.compile(r"(secret|password|passwd|token|api[_-]?key|authorization|cookie)", re.I)
_SAFE_USAGE_KEYS = {"promptTokens", "completionTokens", "totalTokens"}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in list(value.items())[:100]:
            key_text = str(key)
            result[key_text] = (
                sanitize(child, depth + 1)
                if key_text in _SAFE_USAGE_KEYS or not _SENSITIVE.search(key_text)
                else "[redacted]"
            )
        return result
    if isinstance(value, list):
        return [sanitize(child, depth + 1) for child in value[:100]]
    if isinstance(value, str):
        return value[:2000] + ("…" if len(value) > 2000 else "")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


class AgentEvent(BaseModel):
    eventId: str = Field(default_factory=lambda: f"EVT-{uuid4().hex[:14]}")
    traceId: str
    occurredAt: str = Field(default_factory=utc_iso)
    eventType: str
    workflowId: str | None = None
    projectId: str | None = None
    stepId: str | None = None
    agent: str | None = None
    skill: str | None = None
    tool: str | None = None
    status: Literal["running", "complete", "error", "info"] = "info"
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class TraceSummary(BaseModel):
    traceId: str
    workflowId: str | None = None
    projectId: str | None = None
    startedAt: str
    finishedAt: str | None = None
    status: str
    durationMs: int | None = None
    stepCount: int = 0
    selectedModel: str | None = None
    selectedRoute: str | None = None
    decisionSummary: str | None = None
    modelExecutionStatus: str | None = None
    modelCallCount: int = 0
    modelTotalTokens: int = 0
    eventCount: int = 0


class AgentEventStore:
    def __init__(self, max_events: int = 2000) -> None:
        self.max_events = max_events
        self._lock = RLock()
        self._events: list[AgentEvent] = []
        self.load()

    def load(self) -> None:
        with self._lock:
            self._events = []
            for raw in kv_get(AGENT_EVENTS_KEY) or []:
                try:
                    self._events.append(AgentEvent.model_validate(raw))
                except Exception:
                    continue

    def append(self, event: AgentEvent) -> AgentEvent:
        event = event.model_copy(update={"details": sanitize(event.details)})
        with self._lock:
            self._events.append(event)
            self._events = self._events[-self.max_events :]
            kv_set(AGENT_EVENTS_KEY, [item.model_dump(mode="json") for item in self._events])
        return event

    def record(self, *, trace_id: str, event_type: str, summary: str, **kwargs: Any) -> AgentEvent:
        return self.append(
            AgentEvent(
                traceId=trace_id,
                eventType=event_type,
                summary=summary,
                workflowId=kwargs.get("workflow_id"),
                projectId=kwargs.get("project_id"),
                stepId=kwargs.get("step_id"),
                agent=kwargs.get("agent"),
                skill=kwargs.get("skill"),
                tool=kwargs.get("tool"),
                status=kwargs.get("status", "info"),
                details=kwargs.get("details") or {},
            )
        )

    def list_events(self, trace_id: str | None = None) -> list[AgentEvent]:
        with self._lock:
            values = list(self._events)
        if trace_id:
            values = [event for event in values if event.traceId == trace_id]
        return values

    @staticmethod
    def _duration_ms(first: AgentEvent, last: AgentEvent) -> int | None:
        try:
            start = datetime.fromisoformat(first.occurredAt)
            end = datetime.fromisoformat(last.occurredAt)
            return max(0, int((end - start).total_seconds() * 1000))
        except Exception:
            return None

    def traces(
        self,
        *,
        project_id: str | None = None,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[TraceSummary]:
        grouped: dict[str, list[AgentEvent]] = {}
        for event in self.list_events():
            grouped.setdefault(event.traceId, []).append(event)
        output: list[TraceSummary] = []
        for trace_id, events in grouped.items():
            events.sort(key=lambda row: row.occurredAt)
            first, last = events[0], events[-1]
            trace_status = "running"
            if any(row.eventType == "workflow_failed" for row in events):
                trace_status = "error"
            elif any(row.eventType == "workflow_completed" for row in events):
                trace_status = "complete"
            elif any(row.status == "error" for row in events):
                trace_status = "error"
            selected = next((row for row in reversed(events) if row.eventType == "model_selected"), None)
            invocation_events = [
                row
                for row in events
                if row.eventType in {"model_invocation_completed", "model_invocation_failed", "model_not_invoked"}
            ]
            if any(row.eventType == "model_invocation_completed" for row in invocation_events):
                model_execution_status = "used"
            elif any(row.eventType == "model_invocation_failed" for row in invocation_events):
                model_execution_status = "failed"
            elif any(row.eventType == "model_not_invoked" for row in invocation_events):
                model_execution_status = "not_invoked"
            elif selected:
                model_execution_status = "unverified"
            else:
                model_execution_status = "not_required"
            steps = {row.stepId for row in events if row.eventType == "step_started" and row.stepId}
            item = TraceSummary(
                traceId=trace_id,
                workflowId=first.workflowId,
                projectId=first.projectId,
                startedAt=first.occurredAt,
                finishedAt=last.occurredAt if trace_status != "running" else None,
                status=trace_status,
                durationMs=self._duration_ms(first, last) if trace_status != "running" else None,
                stepCount=len(steps),
                selectedModel=(selected.details.get("selectedDisplayName") if selected else None),
                selectedRoute=(selected.details.get("route") if selected else None),
                decisionSummary=(selected.summary if selected else None),
                modelExecutionStatus=model_execution_status,
                modelCallCount=sum(
                    row.eventType in {"model_invocation_completed", "model_invocation_failed"}
                    for row in invocation_events
                ),
                modelTotalTokens=sum(
                    int(row.details.get("totalTokens") or 0)
                    for row in invocation_events
                    if isinstance(row.details.get("totalTokens"), (int, float))
                ),
                eventCount=len(events),
            )
            if project_id and item.projectId != project_id:
                continue
            if workflow_id and item.workflowId != workflow_id:
                continue
            if status and item.status != status:
                continue
            output.append(item)
        output.sort(key=lambda row: row.startedAt, reverse=True)
        return output[: max(1, min(limit, 500))]

    def trace_detail(self, trace_id: str) -> dict[str, Any] | None:
        events = self.list_events(trace_id)
        if not events:
            return None
        summary = next((row for row in self.traces(limit=500) if row.traceId == trace_id), None)
        return {
            "trace": summary.model_dump(mode="json") if summary else None,
            "events": [event.model_dump(mode="json") for event in events],
            "privacyNotice": (
                "이 화면은 후보 점수·제외 사유·선택 결과·도구 실행 상태를 보여주는 구조화 감사 로그입니다. "
                "모델의 비공개 사고과정(chain-of-thought)은 저장하거나 노출하지 않습니다."
            ),
        }

    def summary(self) -> dict[str, int]:
        traces = self.traces(limit=500)
        events = self.list_events()
        return {
            "traces": len(traces),
            "running": sum(row.status == "running" for row in traces),
            "complete": sum(row.status == "complete" for row in traces),
            "errors": sum(row.status == "error" for row in traces),
            "modelDecisions": sum(row.eventType == "model_selected" for row in events),
            "modelInvocations": sum(row.eventType == "model_invocation_completed" for row in events),
            "modelFailures": sum(row.eventType == "model_invocation_failed" for row in events),
            "selectedWithoutInvocation": sum(
                row.modelExecutionStatus in {"not_invoked", "unverified"} for row in traces
            ),
        }

    def prometheus_metrics(self) -> str:
        """Expose low-cardinality model usage counters for Prometheus/Grafana."""
        events = self.list_events()
        grouped: dict[tuple[str, str], dict[str, int]] = {}
        for event in events:
            if event.eventType not in {"model_invocation_completed", "model_invocation_failed"}:
                continue
            model = str(event.details.get("displayName") or event.details.get("model") or "unknown")
            outcome = "completed" if event.eventType == "model_invocation_completed" else str(event.details.get("status") or "failed")
            row = grouped.setdefault((model, outcome), {"calls": 0, "prompt": 0, "completion": 0, "total": 0, "duration": 0})
            row["calls"] += 1
            for source, target in (
                ("promptTokens", "prompt"),
                ("completionTokens", "completion"),
                ("totalTokens", "total"),
                ("durationMs", "duration"),
            ):
                value = event.details.get(source)
                if isinstance(value, (int, float)):
                    row[target] += int(value)

        def escape_label(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        summary = self.summary()
        lines = [
            "# HELP qa_auto_model_invocations_total Completed or failed model provider calls.",
            "# TYPE qa_auto_model_invocations_total counter",
        ]
        for (model, outcome), row in sorted(grouped.items()):
            labels = f'model="{escape_label(model)}",outcome="{escape_label(outcome)}"'
            lines.append(f"qa_auto_model_invocations_total{{{labels}}} {row['calls']}")
            for token_type in ("prompt", "completion", "total"):
                lines.append(
                    f'qa_auto_model_tokens_total{{model="{escape_label(model)}",type="{token_type}"}} {row[token_type]}'
                )
            lines.append(
                f'qa_auto_model_invocation_duration_milliseconds_sum{{model="{escape_label(model)}"}} {row["duration"]}'
            )
        lines.extend(
            [
                "# HELP qa_auto_model_selected_without_invocation Selected model traces without a confirmed provider call.",
                "# TYPE qa_auto_model_selected_without_invocation gauge",
                f"qa_auto_model_selected_without_invocation {summary['selectedWithoutInvocation']}",
            ]
        )
        return "\n".join(lines) + "\n"
