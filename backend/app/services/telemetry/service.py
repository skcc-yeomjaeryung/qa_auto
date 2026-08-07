from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any

from app.schemas.telemetry import (
    BackendTelemetryEvent,
    BackendTelemetryIngestRequest,
    BackendTelemetryIngestResponse,
    RunTimelineResponse,
    TimelineEntry,
)
from app.services.repository_store import InMemoryPlatformStore
from app.services.run_models import RunSummary
from app.services.telemetry.adapters import TelemetryAdapter, default_adapters
from app.services.telemetry.masking import prepare_body

logger = logging.getLogger(__name__)

class TelemetryService:
    def __init__(
        self,
        store: InMemoryPlatformStore,
        adapters: list[TelemetryAdapter] | None = None,
    ) -> None:
        self.store = store
        self.adapters = adapters if adapters is not None else default_adapters()

    def ingest(self, payload: BackendTelemetryIngestRequest) -> BackendTelemetryIngestResponse:
        accepted = 0
        run_ids: set[str] = set()
        sequences: dict[str, int] = {}
        for raw in payload.events:
            event = self._normalize(raw)
            seq = self.store.append_backend_event(event)
            event = event.model_copy(update={"requestSequence": seq})
            for adapter in self.adapters:
                try:
                    adapter.emit(event)
                except Exception:  # noqa: BLE001 — adapters must not break ingest
                    logger.exception("telemetry adapter failed name=%s", getattr(adapter, "name", "?"))
            accepted += 1
            run_ids.add(event.testRunId)
            sequences[event.testRunId] = max(sequences.get(event.testRunId, 0), seq)
            self._touch_run_trace(event.testRunId, linked=True)
        return BackendTelemetryIngestResponse(
            accepted=accepted,
            testRunIds=sorted(run_ids),
            sequences=sequences,
        )

    def list_backend_events(self, run_id: str) -> list[BackendTelemetryEvent]:
        return list(self.store.list_backend_events(run_id))

    def await_backend_logs(self, run_id: str, *, timeout_sec: float | None = None) -> str:
        """Poll for backend events; return linked | partial. Never blocks forever."""
        wait_sec = (
            float(timeout_sec)
            if timeout_sec is not None
            else float(os.getenv("QA_AUTO_BACKEND_LOG_WAIT_SEC", "2.0"))
        )
        poll_sec = float(os.getenv("QA_AUTO_BACKEND_LOG_POLL_SEC", "0.1"))
        if wait_sec <= 0:
            events = self.store.list_backend_events(run_id)
            if events:
                self._touch_run_trace(run_id, linked=True)
                return "linked"
            self._touch_run_trace(run_id, linked=False)
            return "partial"
        deadline = time.monotonic() + wait_sec
        while time.monotonic() < deadline:
            events = self.store.list_backend_events(run_id)
            if events:
                self._touch_run_trace(run_id, linked=True)
                return "linked"
            time.sleep(poll_sec)
        self._touch_run_trace(run_id, linked=False)
        return "partial"

    def build_timeline(self, run_id: str) -> RunTimelineResponse:
        run = self.store.get_run(run_id)
        if not run:
            raise LookupError(f"run not found: {run_id}")
        events = self.list_backend_events(run_id)
        entries: list[TimelineEntry] = []
        order = 1

        # Browser input / FE steps
        for step in run.steps or []:
            action = (step.action or "").lower()
            kind = "browser_step"
            title = f"Browser · {step.action or step.stepId}"
            if action in {"fill", "type"}:
                kind = "browser_input"
                title = "Browser input"
            elif action in {"click", "press"}:
                kind = "frontend_request"
                title = "Frontend Request (trigger)"
            elif action in {"verify_navigation", "snapshot"}:
                kind = "browser_response_received"
                title = "Browser response / binding observe"
            entries.append(
                TimelineEntry(
                    order=order,
                    kind=kind,
                    title=title,
                    timestamp=step.startedAt or step.endedAt,
                    status=step.status,
                    detail=step.observationSummary,
                    payload={
                        "stepId": step.stepId,
                        "refOrLocator": step.refOrLocator,
                        "networkRefs": step.networkRefs,
                        "missingData": step.missingData,
                    },
                )
            )
            order += 1

        # Backend structured events (grouped by requestSequence)
        by_seq: dict[int, list[BackendTelemetryEvent]] = defaultdict(list)
        for ev in events:
            by_seq[ev.requestSequence].append(ev)

        for seq in sorted(by_seq.keys()):
            for ev in by_seq[seq]:
                kind = f"backend_{ev.event}"
                title = ev.event
                if ev.event == "request_received":
                    title = "Backend request_received"
                elif ev.event in {"controller_entered", "service_called"}:
                    title = "Controller/Service"
                elif ev.event == "response_returned":
                    title = "Backend Response"
                entries.append(
                    TimelineEntry(
                        order=order,
                        kind=kind,
                        title=title,
                        timestamp=ev.timestamp,
                        status=str(ev.status) if ev.status is not None else None,
                        detail=self._event_detail(ev),
                        maskedFields=list(ev.maskedFields),
                        truncated=ev.truncated,
                        requestSequence=ev.requestSequence,
                        source=ev.source,
                        constraint=ev.constraint,
                        payload=ev.model_dump(),
                    )
                )
                order += 1

        # Phase 11: link persisted binding validation; remain observational when absent.
        if run.steps:
            binding = self.store.get_binding_result(run_id)
            if binding:
                result_counts: dict[str, int] = {}
                for assertion in binding.assertions:
                    result_counts[assertion.result] = (
                        result_counts.get(assertion.result, 0) + 1
                    )
                binding_status = binding.technicalStatus
                binding_detail = (
                    f"필드 {len(binding.assertions)}건 · "
                    + ", ".join(
                        f"{name} {count}"
                        for name, count in sorted(result_counts.items())
                    )
                    + " · 최종 품질 판단은 HITL"
                )
                binding_payload = {
                    "artifactPath": binding.artifactPath,
                    "businessReviewRequired": binding.businessReviewRequired,
                    "resultCounts": result_counts,
                    "missingData": binding.missingData,
                }
            else:
                binding_status = "not_validated"
                binding_detail = (
                    "바인딩 비교 결과 없음 · DOM/스크린샷 관측 재료만 존재"
                )
                binding_payload = {"missingData": ["binding_validation"]}
            entries.append(
                TimelineEntry(
                    order=order,
                    kind="binding",
                    title="B Binding",
                    timestamp=run.updatedAt,
                    status=binding_status,
                    detail=binding_detail,
                    payload=binding_payload,
                )
            )

        constraints: list[str] = []
        for ev in events:
            if ev.constraint and ev.constraint not in constraints:
                constraints.append(ev.constraint)
        if run.backendTraceConstraint:
            if run.backendTraceConstraint not in constraints:
                constraints.append(run.backendTraceConstraint)

        status = run.backendTraceStatus or ("linked" if events else "partial")
        partial = status == "partial" or bool(run.partialEvidence)
        if not events and status != "external_network_only":
            status = "partial"
            partial = True
            if "backend_telemetry" not in (run.missingData or []):
                # surface in timeline only; persist if run exists
                pass

        # Sort by timestamp when available, keep stable order fallback
        def sort_key(e: TimelineEntry) -> tuple[str, int]:
            return (e.timestamp or "", e.order)

        entries_sorted = sorted(entries, key=sort_key)
        for idx, e in enumerate(entries_sorted, start=1):
            e.order = idx

        return RunTimelineResponse(
            runId=run_id,
            backendTraceStatus=status,
            partialEvidence=partial,
            constraints=constraints,
            entries=entries_sorted,
            backendEventCount=len(events),
        )

    def mark_external_network_only(self, run_id: str) -> RunSummary | None:
        run = self.store.get_run(run_id)
        if not run:
            return None
        # 외부 테스트 대상은 내부 Controller 로그를 제공하지 않는 것이 정상이다.
        # 실제 브라우저 Network 요청·응답이 있으면 제약으로만 알리고 누락/partial로
        # 오인시키지 않는다.
        missing = [
            item
            for item in (run.missingData or [])
            if item not in {"backend_telemetry", "backend_instrumentation"}
        ]
        updated = run.model_copy(
            update={
                "backendTraceStatus": "external_network_only",
                "backendTraceConstraint": "external_target_network_only",
                "partialEvidence": False,
                "missingData": missing,
            }
        )
        return self.store.save_run(updated)

    def mark_backend_not_required(self, run_id: str) -> RunSummary | None:
        """Record that this browser case intentionally has no backend request.

        UI composition and client-side validation cases are complete without
        controller telemetry.  Labelling them partial made a deliberate absence
        look like lost evidence in Run History and HITL.
        """
        run = self.store.get_run(run_id)
        if not run:
            return None
        missing = [
            item
            for item in (run.missingData or [])
            if item not in {"backend_telemetry", "backend_instrumentation"}
        ]
        return self.store.save_run(
            run.model_copy(
                update={
                    "backendTraceStatus": "not_required",
                    "backendTraceConstraint": "client_side_case",
                    "partialEvidence": False,
                    "missingData": missing,
                }
            )
        )

    def _normalize(self, event: BackendTelemetryEvent) -> BackendTelemetryEvent:
        req, req_masked, req_trunc, req_meta = prepare_body(event.request)
        res, res_masked, res_trunc, res_meta = prepare_body(event.response)
        masked = list(dict.fromkeys([*(event.maskedFields or []), *req_masked, *res_masked]))
        truncated = bool(event.truncated or req_trunc or res_trunc)
        meta: dict[str, Any] | None = event.truncationMeta
        if req_meta or res_meta:
            meta = {"request": req_meta, "response": res_meta}
        return event.model_copy(
            update={
                "request": req,
                "response": res,
                "maskedFields": masked,
                "truncated": truncated,
                "truncationMeta": meta,
                "requestSequence": max(1, int(event.requestSequence or 1)),
            }
        )

    def _touch_run_trace(self, run_id: str, *, linked: bool) -> None:
        run = self.store.get_run(run_id)
        if not run:
            return
        if linked:
            updated = run.model_copy(
                update={
                    "backendTraceStatus": "linked",
                    "partialEvidence": False,
                }
            )
            # remove backend_telemetry missing if present
            missing = [m for m in (run.missingData or []) if m != "backend_telemetry"]
            updated = updated.model_copy(update={"missingData": missing})
            self.store.save_run(updated)
            return
        missing = list(run.missingData or [])
        if "backend_telemetry" not in missing:
            missing.append("backend_telemetry")
        self.store.save_run(
            run.model_copy(
                update={
                    "backendTraceStatus": "partial",
                    "partialEvidence": True,
                    "missingData": missing,
                }
            )
        )

    @staticmethod
    def _event_detail(ev: BackendTelemetryEvent) -> str:
        parts = []
        if ev.controller:
            parts.append(ev.controller)
        if ev.service:
            parts.append(ev.service)
        if ev.status is not None:
            parts.append(f"HTTP {ev.status}")
        if ev.durationMs is not None:
            parts.append(f"{ev.durationMs}ms")
        if ev.maskedFields:
            parts.append(f"masked={','.join(ev.maskedFields)}")
        if ev.truncated:
            parts.append("truncated")
        if ev.errorMessage:
            parts.append(ev.errorMessage)
        return " · ".join(parts) if parts else ev.event
