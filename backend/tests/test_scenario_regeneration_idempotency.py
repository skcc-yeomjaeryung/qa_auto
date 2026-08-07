from __future__ import annotations

from app.services.repository_store import InMemoryPlatformStore
from app.services.scenario_models import ScenarioSummary
from app.services.scenario_service import ScenarioService


def test_scenario_list_keeps_latest_project_case_across_regenerated_graphs() -> None:
    store = InMemoryPlatformStore()
    store._scenarios.clear()
    older = ScenarioSummary(
        scenarioId="SCN-OLD",
        projectId="PRJ-1",
        graphId="IG-OLD",
        name="이전 초안",
        createdAt="2026-08-07T01:00:00+00:00",
        result={"caseId": "LOGIN-UI-001"},
    )
    latest = ScenarioSummary(
        scenarioId="SCN-LATEST",
        projectId="PRJ-1",
        graphId="IG-LATEST",
        name="최신 초안",
        createdAt="2026-08-07T02:00:00+00:00",
        result={"caseId": "LOGIN-UI-001"},
    )
    other_project = ScenarioSummary(
        scenarioId="SCN-OTHER",
        projectId="PRJ-2",
        graphId="IG-OTHER",
        name="다른 프로젝트",
        createdAt="2026-08-07T03:00:00+00:00",
        result={"caseId": "LOGIN-UI-001"},
    )
    for scenario in (older, latest, other_project):
        store.save_scenario(scenario)

    project_rows = ScenarioService(store).list_scenarios(project_id="PRJ-1")
    all_rows = ScenarioService(store).list_scenarios()

    assert [row.scenarioId for row in project_rows] == ["SCN-LATEST"]
    assert {row.scenarioId for row in all_rows} == {"SCN-LATEST", "SCN-OTHER"}
