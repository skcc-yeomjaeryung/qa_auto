"""Flow edge editing — connect, disconnect, condition edit.

Observational contract tests. No Pass/Fail declaration for scenarios.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.main import app
from app.services.interaction_graph_models import InteractionGraphSummary

GRAPH_ID = "IG-edge-edit-test"
HEADERS = {"X-User-Id": "TEST"}

client = TestClient(app)


@pytest.fixture(autouse=True)
def seeded_graph():
    bootstrap_runtime()
    store = get_platform_store()
    store._graphs.clear()
    store.save_graph(
        InteractionGraphSummary(
            graphId=GRAPH_ID,
            projectId="PRJ-edge-edit",
            serviceId="bank-of-anthos",
            nodeCount=3,
            edgeCount=1,
            result={
                "nodes": [
                    {"id": "node-a", "type": "screen", "name": "a", "confidence": 0.9,
                     "attributes": {}, "evidence": []},
                    {"id": "node-b", "type": "screen", "name": "b", "confidence": 0.9,
                     "attributes": {}, "evidence": []},
                    {"id": "node-c", "type": "screen", "name": "c", "confidence": 0.9,
                     "attributes": {}, "evidence": []},
                ],
                "edges": [
                    {
                        "id": "edge-a-b",
                        "from": "node-a",
                        "to": "node-b",
                        "type": "navigates_to",
                        "condition": "happy_path",
                        "dataMappings": [],
                        "confidence": 0.9,
                        "evidence": [],
                    }
                ],
                "unresolved": [],
            },
        )
    )
    yield


def _edges() -> list[dict]:
    res = client.get(f"/api/interaction-graphs/{GRAPH_ID}")
    assert res.status_code == 200
    return res.json()["result"]["edges"]


def test_edge_options_lists_types_and_condition_presets():
    res = client.get("/api/interaction-graphs/edge-options")
    assert res.status_code == 200
    body = res.json()
    assert "navigates_to" in body["types"]
    assert "happy_path" in body["conditionPresets"]
    assert "validation_error" in body["conditionPresets"]


def test_patch_edge_changes_condition_without_retargeting():
    res = client.patch(
        f"/api/interaction-graphs/{GRAPH_ID}/edges/edge-a-b",
        json={"condition": "validation_error"},
        headers=HEADERS,
    )
    assert res.status_code == 200, res.text
    edge = _edges()[0]
    assert edge["to"] == "node-b", "condition-only edit must not move the target"
    assert edge["condition"] == "validation_error"
    assert edge["editedBy"] == "human"


def test_patch_edge_can_clear_condition():
    res = client.patch(
        f"/api/interaction-graphs/{GRAPH_ID}/edges/edge-a-b",
        json={"clearCondition": True},
        headers=HEADERS,
    )
    assert res.status_code == 200, res.text
    assert _edges()[0]["condition"] is None


def test_patch_edge_retargets_to_existing_node_only():
    ok = client.patch(
        f"/api/interaction-graphs/{GRAPH_ID}/edges/edge-a-b",
        json={"to": "node-c"},
        headers=HEADERS,
    )
    assert ok.status_code == 200, ok.text
    assert _edges()[0]["to"] == "node-c"

    bad = client.patch(
        f"/api/interaction-graphs/{GRAPH_ID}/edges/edge-a-b",
        json={"to": "node-does-not-exist"},
        headers=HEADERS,
    )
    assert bad.status_code == 400
    assert "missing_data" in bad.json()["detail"]


def test_delete_edge_disconnects_but_keeps_nodes():
    res = client.delete(
        f"/api/interaction-graphs/{GRAPH_ID}/edges/edge-a-b", headers=HEADERS
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["edgeCount"] == 0
    assert len(body["result"]["nodes"]) == 3
    assert _edges() == []

    missing = client.delete(
        f"/api/interaction-graphs/{GRAPH_ID}/edges/edge-a-b", headers=HEADERS
    )
    assert missing.status_code == 400


def test_create_edge_marks_human_edit_with_low_confidence():
    res = client.post(
        f"/api/interaction-graphs/{GRAPH_ID}/edges",
        json={"from": "node-b", "to": "node-c", "type": "navigates_to",
              "condition": "auth_required"},
        headers=HEADERS,
    )
    assert res.status_code == 200, res.text
    created = [e for e in res.json()["result"]["edges"] if e["from"] == "node-b"][0]
    assert created["editedBy"] == "human"
    assert created["condition"] == "auth_required"
    # A person asserting an edge is not code evidence — must stay unresolved-grade.
    assert created["confidence"] < 0.70
    assert created["evidence"] == []


def test_create_edge_rejects_unknown_node_self_loop_and_duplicate():
    unknown = client.post(
        f"/api/interaction-graphs/{GRAPH_ID}/edges",
        json={"from": "node-a", "to": "nope"},
        headers=HEADERS,
    )
    assert unknown.status_code == 400
    assert "missing_data" in unknown.json()["detail"]

    self_loop = client.post(
        f"/api/interaction-graphs/{GRAPH_ID}/edges",
        json={"from": "node-a", "to": "node-a"},
        headers=HEADERS,
    )
    assert self_loop.status_code == 400

    dup = client.post(
        f"/api/interaction-graphs/{GRAPH_ID}/edges",
        json={"from": "node-a", "to": "node-b", "type": "navigates_to"},
        headers=HEADERS,
    )
    assert dup.status_code == 400
    assert "exists" in dup.json()["detail"]


def test_create_edge_rejects_type_outside_contract_enum():
    res = client.post(
        f"/api/interaction-graphs/{GRAPH_ID}/edges",
        json={"from": "node-a", "to": "node-c", "type": "teleports_to"},
        headers=HEADERS,
    )
    assert res.status_code == 400
    assert "unsupported edge type" in res.json()["detail"]
