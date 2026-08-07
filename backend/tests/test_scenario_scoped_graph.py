"""시나리오 단위 의존관계 그래프(부분집합) 회귀 테스트.

근거(evidenceRefs · evidenceIndex)가 있는 노드와 1-hop 이웃만 남는지,
근거가 없으면 추정 없이 missing_data를 알리는지 확인한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.main import app
from app.services.interaction_graph_models import InteractionGraphSummary
from app.services.scenario_models import ScenarioSummary

GRAPH_ID = "IG-scoped-test"
PROJECT_ID = "PRJ-scoped-test"
SCOPED_SCENARIO = "SCN-scoped-login"
UNLINKED_SCENARIO = "SCN-scoped-norefs"
FLOW_SCENARIO = "SCN-scoped-step-flow"

client = TestClient(app)


@pytest.fixture(autouse=True)
def seeded_store():
    bootstrap_runtime()
    store = get_platform_store()
    store.save_graph(
        InteractionGraphSummary(
            graphId=GRAPH_ID,
            projectId=PROJECT_ID,
            serviceId="bank-of-anthos",
            nodeCount=4,
            edgeCount=3,
            primaryPath=["node-screen-login", "node-api-login"],
            branches=[{"id": "happy_path", "label": "정상 경로", "condition": "happy_path"}],
            result={
                "nodes": [
                    {"id": "node-screen-login", "type": "screen", "name": "login"},
                    {"id": "node-api-login", "type": "api", "name": "POST /login"},
                    {"id": "node-screen-home", "type": "screen", "name": "home"},
                    {"id": "node-screen-other", "type": "screen", "name": "unrelated"},
                ],
                "edges": [
                    {
                        "id": "E1",
                        "from": "node-screen-login",
                        "to": "node-api-login",
                        "type": "calls",
                        "condition": "happy_path",
                    },
                    {
                        "id": "E2",
                        "from": "node-api-login",
                        "to": "node-screen-home",
                        "type": "navigates_to",
                        "condition": "happy_path",
                    },
                    {
                        "id": "E3",
                        "from": "node-screen-other",
                        "to": "node-screen-other",
                        "type": "contains",
                        "condition": "error_path",
                    },
                ],
            },
        )
    )
    store.save_scenario(
        ScenarioSummary(
            scenarioId=SCOPED_SCENARIO,
            serviceId="bank-of-anthos",
            projectId=PROJECT_ID,
            graphId=GRAPH_ID,
            name="LOGIN-E2E-001 로그인 관통",
            result={
                "steps": [
                    {"stepId": "S1", "evidenceRefs": ["graph:node-screen-login"]},
                    {"stepId": "S2", "evidenceRefs": ["graph:node-api-login"]},
                ],
                "evidenceIndex": [{"nodeId": "node-api-login"}],
            },
        )
    )
    store.save_scenario(
        ScenarioSummary(
            scenarioId=UNLINKED_SCENARIO,
            serviceId="bank-of-anthos",
            projectId=PROJECT_ID,
            graphId=GRAPH_ID,
            name="NO-REFS-001 근거 없음",
            result={"steps": [{"stepId": "S1", "evidenceRefs": []}]},
        )
    )
    store.save_scenario(
        ScenarioSummary(
            scenarioId=FLOW_SCENARIO,
            serviceId="bank-of-anthos",
            projectId=PROJECT_ID,
            graphId=GRAPH_ID,
            name="SIGNUP-E2E-001 회원가입",
            result={
                "steps": [
                    {
                        "id": "S1",
                        "action": "navigate",
                        "title": "회원가입 화면 열기",
                        "target": {"route": "/signup"},
                        "evidenceRefs": ["graph:node-screen-login"],
                    },
                    {
                        "id": "S2",
                        "action": "fill",
                        "title": "회원가입 화면 값 입력",
                        "target": {"strategy": "css", "value": "#signup-username"},
                        "evidenceRefs": ["graph:node-screen-login"],
                    },
                    {
                        "id": "S3",
                        "action": "click",
                        "title": "회원가입 버튼 클릭",
                        "target": {"strategy": "css", "value": "button[type='submit']"},
                        "evidenceRefs": ["graph:node-screen-login"],
                    },
                    {
                        "id": "S4",
                        "action": "wait_for_response",
                        "title": "회원가입 서버 응답 확인",
                        "request": {"method": "POST", "path": "/signup"},
                        "evidenceRefs": ["graph:node-api-login"],
                    },
                ]
            },
        )
    )
    yield store
    store.delete_scenarios([SCOPED_SCENARIO, UNLINKED_SCENARIO, FLOW_SCENARIO])


def test_scoped_graph_keeps_only_evidenced_nodes_and_one_hop():
    res = client.get(f"/api/scenarios/{SCOPED_SCENARIO}/interaction-graph")
    assert res.status_code == 200
    body = res.json()

    node_ids = {n["id"] for n in body["result"]["nodes"]}
    # seed(login 화면 · POST /login) + 1-hop(home) 만 남고 무관 노드는 빠진다
    assert node_ids == {"node-screen-login", "node-api-login", "node-screen-home"}
    assert body["nodeCount"] == 3
    assert {e["id"] for e in body["result"]["edges"]} == {"E1", "E2"}
    assert body["missingData"] == []
    assert body["sourceGraphId"] == GRAPH_ID
    assert body["scopedScenarioId"] == SCOPED_SCENARIO
    assert body["primaryPath"] == ["node-screen-login", "node-api-login"]


def test_scoped_graph_reports_missing_data_without_refs():
    res = client.get(f"/api/scenarios/{UNLINKED_SCENARIO}/interaction-graph")
    assert res.status_code == 200
    body = res.json()

    assert body["result"]["nodes"] == []
    assert body["missingData"] == ["scenario_graph_refs"]


def test_executable_scenario_is_rendered_as_ordered_action_fragments():
    res = client.get(f"/api/scenarios/{FLOW_SCENARIO}/interaction-graph")
    assert res.status_code == 200
    body = res.json()
    nodes = body["result"]["nodes"]
    assert [node["type"] for node in nodes] == ["screen", "input", "event", "frontend_api_call"]
    assert [node["name"] for node in nodes] == [
        "회원가입 화면 열기",
        "회원가입 화면 값 입력",
        "회원가입 버튼 클릭",
        "회원가입 서버 응답 확인",
    ]
    assert body["primaryPath"] == [
        "scenario-step-s1",
        "scenario-step-s2",
        "scenario-step-s3",
        "scenario-step-s4",
    ]
    assert len(body["result"]["edges"]) == 3


def test_scoped_graph_404_for_unknown_scenario():
    res = client.get("/api/scenarios/SCN-does-not-exist/interaction-graph")
    assert res.status_code == 404
