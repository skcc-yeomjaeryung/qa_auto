from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.main import app
from app.services.run_models import RunSummary


def test_bulk_run_sse_emits_progress_and_complete_for_terminal_runs() -> None:
    store = get_platform_store()
    store._runs.clear()
    store.save_run(
        RunSummary(
            runId="RUN-SSE-1",
            scenarioId="SCN-SSE-1",
            status="WAITING_FOR_REVIEW",
            progressPercent=100,
            outcomeKind="success",
            result={"verdict": {"verdict": "expected_met", "reason": "기대 기준 관측"}},
        )
    )

    response = TestClient(app).get("/api/console/bulk-runs/events?runIds=RUN-SSE-1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert "event: complete" in response.text
    assert '"completed": 1' in response.text
    assert '"success": 1' in response.text
    assert '"failed": 0' in response.text
    assert '"percent": 100' in response.text
