from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import REPO_ROOT
from app.main import app
from app.services.run_models import RunSummary
from app.services.telemetry.masking import prepare_body, sanitize_headers
from app.services.telemetry.service import TelemetryService
from app.skills.browser_execute.script.execute_run import _sanitize_trace_headers

SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "backend_telemetry.schema.json"
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store():
    bootstrap_runtime()
    store = get_platform_store()
    for attr in (
        "_projects",
        "_sets",
        "_files",
        "_commit_cache",
        "_tokens",
        "_analyses",
        "_mapping_sets",
        "_graphs",
        "_scenarios",
        "_contracts",
        "_recommendations",
        "_profiles",
        "_runs",
        "_backend_events",
        "_backend_seq",
    ):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    yield


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_run(run_id: str = "RUN-p10-1") -> RunSummary:
    store = get_platform_store()
    item = RunSummary(
        runId=run_id,
        scenarioId="SCN-p10",
        status="WAITING_FOR_REVIEW",
        testCaseId="TC-p10",
        inputProfileId="IP-p10",
        steps=[],
        createdAt=_now(),
        updatedAt=_now(),
    )
    return store.save_run(item)


def _event(
    run_id: str,
    event: str,
    *,
    seq: int = 1,
    request: dict | None = None,
    response: dict | None = None,
    status: int | None = 200,
) -> dict:
    return {
        "timestamp": _now(),
        "event": event,
        "testRunId": run_id,
        "scenarioId": "SCN-p10",
        "testCaseId": "TC-p10",
        "inputProfileId": "IP-p10",
        "requestSequence": seq,
        "controller": "CustomerController.search",
        "request": request,
        "response": response,
        "status": status,
        "durationMs": 12,
        "maskedFields": [],
        "source": "spring",
    }


def test_schema_validates_sample_event():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(
        _event("RUN-x", "response_returned", request={"customerId": "C1"}, response={"riskLevel": "HIGH"})
    )


def test_header_sanitize_masks_secrets():
    cleaned = sanitize_headers(
        {
            "X-Test-Run-ID": "RUN-1",
            "Authorization": "Bearer secret",
            "Cookie": "a=1",
            "X-Api-Key": "k",
        }
    )
    assert cleaned["X-Test-Run-ID"] == "RUN-1"
    assert cleaned["Authorization"] == "***"
    assert cleaned["Cookie"] == "***"
    assert _sanitize_trace_headers({"password": "x"})["password"] == "***"


def test_request_response_masking_and_truncation():
    body, masked, truncated, meta = prepare_body(
        {"customerId": "C1", "password": "p@ss", "token": "t"},
        max_bytes=10_000,
    )
    assert body["password"] == "***"
    assert body["token"] == "***"
    assert "password" in masked
    assert truncated is False

    huge = {"blob": "x" * 20_000}
    body2, _, truncated2, meta2 = prepare_body(huge, max_bytes=100)
    assert truncated2 is True
    assert meta2 is not None
    assert body2["_truncated"] is True


def test_ingest_and_backend_events_api():
    _seed_run("RUN-p10-api")
    payload = {
        "events": [
            _event("RUN-p10-api", "request_received", seq=0, request={"customerId": "C1", "password": "secret"}),
            _event(
                "RUN-p10-api",
                "response_returned",
                seq=1,
                request={"customerId": "C1", "password": "secret"},
                response={"customerId": "C1", "riskLevel": "HIGH"},
            ),
        ]
    }
    res = client.post("/api/test-telemetry/backend", json=payload)
    assert res.status_code == 200
    assert res.json()["accepted"] == 2

    events = client.get("/api/runs/RUN-p10-api/backend-events")
    assert events.status_code == 200
    data = events.json()
    assert len(data) == 2
    assert data[0]["requestSequence"] == 1
    assert data[0]["request"]["password"] == "***"
    assert "password" in data[0]["maskedFields"]


def test_duplicate_request_sequence():
    _seed_run("RUN-p10-seq")
    client.post(
        "/api/test-telemetry/backend",
        json={
            "events": [
                _event("RUN-p10-seq", "request_received", seq=0),
                _event("RUN-p10-seq", "request_received", seq=0),
            ]
        },
    )
    events = client.get("/api/runs/RUN-p10-seq/backend-events").json()
    assert [e["requestSequence"] for e in events] == [1, 2]


def test_timeline_merge_and_masked_fields():
    store = get_platform_store()
    from app.services.run_models import RunStepSummary

    run = RunSummary(
        runId="RUN-p10-tl",
        scenarioId="SCN-p10",
        status="WAITING_FOR_REVIEW",
        steps=[
            RunStepSummary(stepId="S1", action="fill", status="ok", startedAt=_now(), observationSummary="filled"),
            RunStepSummary(stepId="S2", action="click", status="ok", startedAt=_now(), observationSummary="clicked"),
        ],
        createdAt=_now(),
        updatedAt=_now(),
    )
    store.save_run(run)
    client.post(
        "/api/test-telemetry/backend",
        json={
            "events": [
                _event("RUN-p10-tl", "request_received", request={"password": "x"}),
                _event("RUN-p10-tl", "controller_entered"),
                _event("RUN-p10-tl", "response_returned", response={"ok": True}, status=200),
            ]
        },
    )
    tl = client.get("/api/runs/RUN-p10-tl/timeline")
    assert tl.status_code == 200
    body = tl.json()
    assert body["backendTraceStatus"] == "linked"
    assert body["backendEventCount"] == 3
    kinds = [e["kind"] for e in body["entries"]]
    assert "browser_input" in kinds
    assert "frontend_request" in kinds
    assert any(k.startswith("backend_") for k in kinds)
    assert "binding" in kinds
    masked_entries = [e for e in body["entries"] if e.get("maskedFields")]
    assert masked_entries


def test_missing_backend_log_timeout_partial(monkeypatch):
    monkeypatch.setenv("QA_AUTO_BACKEND_LOG_WAIT_SEC", "0.05")
    monkeypatch.setenv("QA_AUTO_BACKEND_LOG_POLL_SEC", "0.01")
    _seed_run("RUN-p10-partial")
    status = TelemetryService(get_platform_store()).await_backend_logs("RUN-p10-partial")
    assert status == "partial"
    run = get_platform_store().get_run("RUN-p10-partial")
    assert run is not None
    assert run.backendTraceStatus == "partial"
    assert run.partialEvidence is True
    assert "backend_telemetry" in (run.missingData or [])


def test_external_target_constraint():
    _seed_run("RUN-p10-ext")
    res = client.post("/api/runs/RUN-p10-ext/backend-trace/external")
    assert res.status_code == 200
    assert res.json()["backendTraceStatus"] == "external_network_only"
    assert res.json()["partialEvidence"] is False
    run = get_platform_store().get_run("RUN-p10-ext")
    assert run is not None
    assert "backend_instrumentation" not in run.missingData
    tl = client.get("/api/runs/RUN-p10-ext/timeline").json()
    assert "external_target_network_only" in tl["constraints"]


def test_client_side_case_does_not_report_backend_as_missing():
    _seed_run("RUN-p10-ui")
    service = TelemetryService(get_platform_store())
    updated = service.mark_backend_not_required("RUN-p10-ui")
    assert updated is not None
    assert updated.backendTraceStatus == "not_required"
    assert updated.backendTraceConstraint == "client_side_case"
    assert updated.partialEvidence is False
    assert "backend_telemetry" not in (updated.missingData or [])


def test_concurrent_run_isolation():
    _seed_run("RUN-A")
    _seed_run("RUN-B")

    def ingest(run_id: str) -> None:
        client.post(
            "/api/test-telemetry/backend",
            json={"events": [_event(run_id, "request_received"), _event(run_id, "response_returned")]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(ingest, ["RUN-A", "RUN-B"]))

    a = client.get("/api/runs/RUN-A/backend-events").json()
    b = client.get("/api/runs/RUN-B/backend-events").json()
    assert all(e["testRunId"] == "RUN-A" for e in a)
    assert all(e["testRunId"] == "RUN-B" for e in b)
    assert len(a) == 2 and len(b) == 2


def test_validation_failed_and_exception_events_accepted():
    _seed_run("RUN-p10-err")
    res = client.post(
        "/api/test-telemetry/backend",
        json={
            "events": [
                _event("RUN-p10-err", "validation_failed", status=400),
                _event("RUN-p10-err", "exception_mapped", status=500),
            ]
        },
    )
    assert res.status_code == 200
    events = client.get("/api/runs/RUN-p10-err/backend-events").json()
    assert {e["event"] for e in events} == {"validation_failed", "exception_mapped"}
