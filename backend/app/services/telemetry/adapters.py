from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from app.core.paths import ARTIFACTS_EVIDENCE
from app.schemas.telemetry import BackendTelemetryEvent

logger = logging.getLogger(__name__)


class TelemetryAdapter(Protocol):
    name: str

    def emit(self, event: BackendTelemetryEvent) -> None: ...


class MemoryAdapter:
    """In-process sink used by Control Plane store (primary Pilot path)."""

    name = "memory"

    def __init__(self) -> None:
        self.events: list[BackendTelemetryEvent] = []

    def emit(self, event: BackendTelemetryEvent) -> None:
        self.events.append(event)


class FileAdapter:
    """Append JSONL under artifacts/evidence/runs/{runId}/backend-telemetry.jsonl."""

    name = "file"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (ARTIFACTS_EVIDENCE / "runs")

    def emit(self, event: BackendTelemetryEvent) -> None:
        run_dir = self.root / event.testRunId
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "backend-telemetry.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")


class HttpIngestAdapter:
    """No-op marker: HTTP ingest is the Control Plane API itself."""

    name = "http_ingest"

    def emit(self, event: BackendTelemetryEvent) -> None:
        logger.debug("http_ingest adapter passthrough run=%s event=%s", event.testRunId, event.event)


class OtelStubAdapter:
    """Extension point — Pilot does not export OTLP; records intent only."""

    name = "otel"

    def emit(self, event: BackendTelemetryEvent) -> None:
        logger.debug(
            "otel stub (not exported) run=%s event=%s payload_keys=%s",
            event.testRunId,
            event.event,
            list((event.request or {}).keys())[:8],
        )


def default_adapters() -> list[TelemetryAdapter]:
    return [FileAdapter(), HttpIngestAdapter(), OtelStubAdapter()]
