from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.main import app
from app.services.dashboard_service import DashboardService
from app.services.repository_models import ProjectCreate
from app.services.run_models import RunSummary
from app.services.scenario_models import ScenarioSummary


client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store():
    bootstrap_runtime()
    store = get_platform_store()
    for attr in (
        "_projects",
        "_sets",
        "_analyses",
        "_graphs",
        "_scenarios",
        "_runs",
        "_contracts",
        "_recommendations",
        "_profiles",
        "_evidence_manifests",
    ):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    yield


def _seed(now: datetime) -> tuple[str, str]:
    store = get_platform_store()
    mine = store.create_project(ProjectCreate(name="내 프로젝트", ownerUserId="TEST"))
    other = store.create_project(ProjectCreate(name="다른 사용자", ownerUserId="OTHER"))
    scenario = ScenarioSummary(
        scenarioId="SCN-dashboard",
        projectId=mine.id,
        serviceId="dashboard-service",
        name="대시보드 관통",
        status="EXECUTABLE",
        createdAt=(now - timedelta(days=2)).isoformat(),
    )
    store.save_scenario(scenario)
    store.save_scenario(
        ScenarioSummary(
            scenarioId="SCN-other",
            projectId=other.id,
            serviceId="other",
            name="다른 사용자 시나리오",
            status="EXECUTABLE",
            createdAt=now.isoformat(),
        )
    )
    store.save_run(
        RunSummary(
            runId="RUN-old",
            scenarioId=scenario.scenarioId,
            projectId=mine.id,
            status="AUTO_FAILED",
            outcomeKind="fe_error",
            createdAt=(now - timedelta(days=1, hours=2)).isoformat(),
        )
    )
    store.save_run(
        RunSummary(
            runId="RUN-new",
            scenarioId=scenario.scenarioId,
            projectId=mine.id,
            status="WAITING_FOR_REVIEW",
            outcomeKind="success",
            createdAt=(now - timedelta(hours=1)).isoformat(),
            screenshotCount=3,
            snapshotCount=2,
        )
    )
    store.save_run(
        RunSummary(
            runId="RUN-other",
            scenarioId="SCN-other",
            projectId=other.id,
            status="WAITING_FOR_REVIEW",
            outcomeKind="success",
            createdAt=now.isoformat(),
        )
    )
    return mine.id, other.id


def test_dashboard_summary_is_user_scoped_and_uses_observed_runs() -> None:
    now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    mine, _ = _seed(now)
    body = DashboardService(get_platform_store()).summary("TEST", now=now)
    assert body.projectCount == 1
    assert body.projects[0].projectId == mine
    assert body.scenarioCount == 1
    assert body.runCount == 2
    assert body.reviewCount == 2
    assert body.weeklyRate == 50.0
    assert body.recentRuns[0].runId == "RUN-new"
    assert body.recentRuns[0].changedFromPrevious is True
    assert body.recentRuns[0].screenshotCount == 3


def test_dashboard_api_rejects_cross_user_query() -> None:
    _seed(datetime.now(timezone.utc))
    denied = client.get(
        "/api/dashboard/summary?ownerUserId=OTHER",
        headers={"X-User-Id": "TEST"},
    )
    assert denied.status_code == 403

    allowed = client.get(
        "/api/dashboard/summary?ownerUserId=TEST",
        headers={"X-User-Id": "TEST"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["userId"] == "TEST"
    assert allowed.json()["projectCount"] == 1

