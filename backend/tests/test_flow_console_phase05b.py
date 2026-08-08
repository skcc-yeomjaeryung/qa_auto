from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.main import app
from app.services.console_service import normalize_io_payload
from app.services.interaction_graph_models import InteractionGraphSummary
from app.services.run_models import RunStepSummary, RunSummary
from app.services.scenario_models import ScenarioSummary

GRAPH_ID = "IG-flowruntime-test"


@pytest.fixture(autouse=True)
def fresh_store():
    bootstrap_runtime()
    store = get_platform_store()
    for attr in ("_graphs", "_scenarios", "_runs"):
        getattr(store, attr).clear()
    if hasattr(store, "_flow_node_runtime"):
        store._flow_node_runtime.clear()
    yield


client = TestClient(app)


def _seed_graph_with_list_inputs() -> None:
    store = get_platform_store()
    store.save_graph(
        InteractionGraphSummary(
            graphId=GRAPH_ID,
            projectId="PRJ-flowruntime",
            serviceId="bank-of-anthos",
            nodeCount=1,
            edgeCount=0,
            result={
                "nodes": [
                    {
                        "id": "node-screen-login",
                        "type": "screen",
                        "name": "login",
                        "confidence": 0.9,
                        "attributes": {
                            "route": "/login",
                            "inputs": [
                                {
                                    "name": "Username",
                                    "field": "username",
                                    "selector": "#login-username",
                                    "type": "text",
                                    "kind": "input",
                                },
                                {
                                    "name": "Password",
                                    "field": "password",
                                    "selector": "#login-password",
                                    "type": "password",
                                    "kind": "input",
                                },
                            ],
                        },
                    }
                ],
                "edges": [],
            },
        )
    )


def test_list_flow_nodes_accepts_list_shaped_inputs() -> None:
    """Frontend analysis emits attributes.inputs as a list — must not 500."""
    _seed_graph_with_list_inputs()
    res = client.get(f"/api/console/flows/{GRAPH_ID}/nodes")
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) == 1
    node = items[0]
    assert node["nodeId"] == "node-screen-login"
    assert node["input"] == {"username": None, "password": None}


def test_normalize_io_payload_keeps_field_keys_without_inventing_values() -> None:
    normalized = normalize_io_payload(
        [
            {"name": "Username", "field": "username", "type": "text"},
            {"name": "amount", "value": 100},
            {"name": "nameless_only"},
        ]
    )
    assert normalized == {"username": None, "amount": 100, "nameless_only": None}


def test_normalize_io_payload_passes_dict_and_ignores_scalars() -> None:
    assert normalize_io_payload({"a": 1}) == {"a": 1}
    assert normalize_io_payload(None) == {}
    assert normalize_io_payload("oops") == {}


def test_scoped_flow_runtime_uses_scenario_steps_and_latest_observation() -> None:
    store = get_platform_store()
    _seed_graph_with_list_inputs()
    scenario_id = "SCN-flow-runtime"
    store.save_scenario(
        ScenarioSummary(
            scenarioId=scenario_id,
            projectId="PRJ-flowruntime",
            graphId=GRAPH_ID,
            name="입금 실행",
            result={
                "scenarioId": scenario_id,
                "name": "입금 실행",
                "steps": [
                    {
                        "id": "S1",
                        "action": "fill",
                        "title": "입금액 입력",
                        "target": {"strategy": "css", "value": "#deposit-amount"},
                        "valueFrom": "inputs.amount",
                        "evidenceRefs": ["graph:node-screen-login"],
                    }
                ],
            },
        )
    )
    store.save_run(
        RunSummary(
            runId="RUN-flow-runtime",
            scenarioId=scenario_id,
            projectId="PRJ-flowruntime",
            status="WAITING_FOR_REVIEW",
            inputs={"amount": "30"},
            steps=[
                RunStepSummary(
                    stepId="S1",
                    action="fill",
                    status="ok",
                    refOrLocator="#deposit-amount",
                    observationSummary="입력 amount = 30",
                    screenshotPath="/tmp/S1.png",
                )
            ],
        )
    )

    scoped_id = f"{GRAPH_ID}::{scenario_id}"
    res = client.get(f"/api/console/flows/{scoped_id}/nodes")
    assert res.status_code == 200, res.text
    item = res.json()[0]
    assert item["nodeId"] == "scenario-step-s1"
    assert item["status"] == "success"
    assert item["operation"] == {
        "kind": "browser",
        "stepId": "S1",
        "action": "fill",
        "method": None,
        "path": "/login",
        "target": {"strategy": "css", "value": "#deposit-amount"},
    }
    assert item["input"]["value"] == "30"
    assert item["output"]["observed"] is True
    assert item["output"]["summary"] == "입력 amount = 30"

    patched = client.patch(
        f"/api/console/flows/{scoped_id}/nodes/scenario-step-s1",
        json={"input": {**item["input"], "value": "45"}, "output": item["output"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["input"]["value"] == "45"


def test_scoped_flow_runtime_propagates_failed_criterion_to_red_node() -> None:
    store = get_platform_store()
    _seed_graph_with_list_inputs()
    scenario_id = "SCN-flow-invalid-format"
    store.save_scenario(
        ScenarioSummary(
            scenarioId=scenario_id,
            projectId="PRJ-flowruntime",
            graphId=GRAPH_ID,
            name="입금 금액 문자 입력 거부",
            result={
                "steps": [
                    {"id": "S1", "action": "fill", "title": "문자 입력", "valueFrom": "inputs.amount"},
                    {
                        "id": "S2",
                        "action": "assert_invalid",
                        "title": "숫자 형식 검증",
                        "criterionId": "C-invalid-format",
                        "expect": {"valid": False},
                    },
                ]
            },
        )
    )
    store.save_run(
        RunSummary(
            runId="RUN-flow-invalid-format",
            scenarioId=scenario_id,
            projectId="PRJ-flowruntime",
            status="AUTO_FAILED",
            steps=[
                RunStepSummary(stepId="S1", action="fill", status="ok", observationSummary="한글입력 입력"),
                RunStepSummary(stepId="S2", action="assert_invalid", status="warning", observationSummary="거부 상태 미관측"),
            ],
            result={
                "verdict": {
                    "verdict": "expected_not_met",
                    "criteriaResults": [
                        {
                            "id": "C-invalid-format",
                            "check": "native_constraint_rejection",
                            "expected": "숫자 형식 외 문자 입력은 요청 전에 거부된다",
                            "result": "not_met",
                            "observed": "브라우저 입력 제약의 거부 상태를 확인하지 못했습니다",
                        }
                    ],
                }
            },
        )
    )

    scoped_id = f"{GRAPH_ID}::{scenario_id}"
    response = client.get(f"/api/console/flows/{scoped_id}/nodes")
    assert response.status_code == 200, response.text
    by_id = {item["nodeId"]: item for item in response.json()}
    assert by_id["scenario-step-s1"]["status"] == "success"
    assert by_id["scenario-step-s2"]["status"] == "failure"
    assert "숫자만 입력해야 하는 필드" in by_id["scenario-step-s2"]["errorMessage"]
