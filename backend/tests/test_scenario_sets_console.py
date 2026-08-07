"""테스트 시나리오 1단 목록(연결 저장소 기준) · 「테스트 종료」 회귀 테스트."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.main import app
from app.services.console_service import repository_display_name
from app.services.interaction_graph_models import InteractionGraphSummary
from app.services.repository_models import Project, Repository, RepositorySet
from app.services.run_models import RunSummary
from app.services.scenario_models import ScenarioSummary

GRAPH_ID = "IG-scenarioset-test"
PROJECT_ID = "PRJ-scenarioset-test"
SET_ID = "RS-scenarioset-test"

HEADERS = {"X-User-Id": "TEST"}

client = TestClient(app)


@pytest.fixture(autouse=True)
def seeded_store():
    bootstrap_runtime()
    store = get_platform_store()
    with store._lock:
        store._projects[PROJECT_ID] = Project(
            id=PROJECT_ID, name="관통 점검 프로젝트", ownerUserId="TEST"
        )
    store.save_set(
        RepositorySet(
            id=SET_ID,
            projectId=PROJECT_ID,
            name="기본 저장소",
            repositories=[
                Repository(
                    id="REPO-scenarioset-test",
                    role="frontend",
                    sourceType="github",
                    branch="main",
                    url="https://github.com/GoogleCloudPlatform/bank-of-anthos.git",
                )
            ],
        )
    )
    store.save_graph(
        InteractionGraphSummary(
            graphId=GRAPH_ID,
            projectId=PROJECT_ID,
            serviceId="bank-of-anthos",
            repositorySetId=SET_ID,
            nodeCount=0,
            edgeCount=0,
            result={"nodes": [], "edges": []},
        )
    )
    for index in (1, 2):
        store.save_scenario(
            ScenarioSummary(
                scenarioId=f"SCN-set-{index}",
                projectId=PROJECT_ID,
                graphId=GRAPH_ID,
                serviceId="login-ui",
                name=f"로그인 화면 점검 {index}",
            )
        )
    yield store


def _find_set(items: list[dict]) -> dict:
    return next(item for item in items if item["setId"] == GRAPH_ID)


def test_scenario_sets_group_by_repository_with_display_name() -> None:
    res = client.get("/api/console/scenario-sets", headers=HEADERS)
    assert res.status_code == 200, res.text
    row = _find_set(res.json())
    assert row["scenarioCount"] == 2
    # 「기본 저장소」 placeholder must fall back to the repository folder name.
    assert row["repositoryName"] == "bank-of-anthos"
    assert row["status"] == "ready"
    assert row["executedCount"] == 0


def test_repository_display_name_prefers_typed_name_then_slug() -> None:
    store = get_platform_store()
    repo_set = store.get_set(SET_ID)
    assert repository_display_name(repo_set) == "bank-of-anthos"
    named = repo_set.model_copy(update={"name": "코어뱅킹 FE"})
    assert repository_display_name(named) == "코어뱅킹 FE"
    assert repository_display_name(None, fallback="관통 점검 프로젝트") == "관통 점검 프로젝트"
    # 워크스페이스 폴더로 연결하면 set 이름에 내부 id가 박힐 수 있다 — 노출하지 않는다.
    internal = repo_set.model_copy(update={"name": "REPO-BA-0ad59489"})
    assert repository_display_name(internal) == "bank-of-anthos"
    opaque = internal.model_copy(
        update={
            "repositories": [
                Repository(
                    id="REPO-opaque",
                    role="frontend",
                    sourceType="local",
                    branch="main",
                    path="/tmp/.data/workspaces/REPO-BA-0ad59489",
                )
            ]
        }
    )
    assert repository_display_name(opaque, fallback="관통 점검 프로젝트") == "관통 점검 프로젝트"


def test_stop_scenario_set_cancels_only_unfinished_runs() -> None:
    store = get_platform_store()
    store.save_run(
        RunSummary(runId="RUN-set-running", scenarioId="SCN-set-1", status="RUNNING")
    )
    store.save_run(
        RunSummary(
            runId="RUN-set-done", scenarioId="SCN-set-2", status="WAITING_FOR_REVIEW"
        )
    )

    res = client.post(f"/api/console/scenario-sets/{GRAPH_ID}/stop", headers=HEADERS)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cancelledRunIds"] == ["RUN-set-running"]
    assert body["alreadyFinishedRunIds"] == ["RUN-set-done"]
    assert store.get_run("RUN-set-running").status == "CANCELLED"
    assert store.get_run("RUN-set-done").status == "WAITING_FOR_REVIEW"


def test_delete_project_removes_its_scenario_sets() -> None:
    """프로젝트를 지우면 그 프로젝트의 그래프·시나리오도 목록에서 사라진다.

    남겨두면 소속 없는 세트가 「연결 저장소」로 떠서 목록·지표가 실제와 어긋난다.
    """
    store = get_platform_store()
    assert store.delete_project(PROJECT_ID) is True
    res = client.get("/api/console/scenario-sets", headers=HEADERS)
    assert res.status_code == 200, res.text
    assert all(item["setId"] != GRAPH_ID for item in res.json())
    assert store.get_graph(GRAPH_ID) is None
    assert store.get_scenario("SCN-set-1") is None


def test_stop_unknown_scenario_set_returns_404() -> None:
    res = client.post("/api/console/scenario-sets/IG-nope/stop", headers=HEADERS)
    assert res.status_code == 404
