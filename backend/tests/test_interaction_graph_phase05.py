from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import ARTIFACTS_ANALYSIS, BACKEND_ROOT, REPO_ROOT, SKILL_HUB
from app.main import app
from app.skills.api_map.script.map_apis import build_mappings
from app.skills.interaction_graph.script.compose_graph import compose_graph, find_paths

SAMPLE_FE = REPO_ROOT / "sample-targets" / "customer-portal-fe"
SAMPLE_BE = REPO_ROOT / "sample-targets" / "customer-service-be"
FIXTURE_FE = REPO_ROOT / "artifacts" / "analysis" / "AN-FE-5305d8bde832" / "frontend.json"
FIXTURE_BE = REPO_ROOT / "artifacts" / "analysis" / "AN-BE-5115c351b091" / "backend.json"
SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "interaction_graph.schema.json"


@pytest.fixture(autouse=True)
def fresh_store():
    bootstrap_runtime()
    store = get_platform_store()
    store._projects.clear()
    store._sets.clear()
    store._files.clear()
    store._commit_cache.clear()
    store._tokens.clear()
    store._analyses.clear()
    store._mapping_sets.clear()
    store._graphs.clear()
    if hasattr(store, "_scenarios"):
        store._scenarios.clear()
    yield


client = TestClient(app)


def test_interaction_graph_skill_textbook() -> None:
    skill_md = (SKILL_HUB / "interaction_graph" / "SKILL.md").read_text(encoding="utf-8")
    for header in (
        "## 1. Skill Purpose",
        "## 14. Changelog",
        "QA.CODE.INTERACTION_GRAPH",
        "script: script/compose_graph.py",
    ):
        assert header in skill_md


def test_interaction_graph_workflow_hub() -> None:
    import yaml

    data = yaml.safe_load(
        (BACKEND_ROOT / "app" / "workflow_definitions" / "wf_interaction_graph.yml").read_text(
            encoding="utf-8"
        )
    )
    assert data["workflow_id"] == "wf_interaction_graph"
    assert data["required_capabilities"][0]["capability_id"] == "QA.CODE.INTERACTION_GRAPH"


def test_compose_graph_from_fixtures_schema() -> None:
    assert FIXTURE_FE.is_file() and FIXTURE_BE.is_file() and SCHEMA.is_file()
    fe = json.loads(FIXTURE_FE.read_text(encoding="utf-8"))
    be = json.loads(FIXTURE_BE.read_text(encoding="utf-8"))
    mapping = build_mappings(fe, be, project_id="PRJ-ig")
    graph = compose_graph(
        fe,
        be,
        mapping,
        project_id="PRJ-ig",
        repository_set_id="RS-ig",
        graph_id="IG-fixture",
    )
    assert graph["schemaVersion"] == "interaction-graph/v1"
    types = {n["type"] for n in graph["nodes"]}
    for required in (
        "screen",
        "input",
        "event",
        "validation",
        "frontend_api_call",
        "backend_endpoint",
        "request_dto",
        "service",
        "response_dto",
        "route_transition",
        "binding",
    ):
        assert required in types, types

    # customerId lineage: input → … → request_dto (DOM 표기 customer-id는 계약 표기로 정규화)
    assert any(n["name"] == "customerId" and n["type"] == "input" for n in graph["nodes"])
    assert any(
        n["type"] == "input" and (n["attributes"].get("domName") or n["attributes"].get("testId"))
        for n in graph["nodes"]
    )
    assert any(e.get("dataMappings") for e in graph["edges"])

    # branches
    conditions = {e.get("condition") for e in graph["edges"]}
    assert "happy_path" in conditions
    assert "validation_failed" in conditions or "customer_not_found" in conditions

    # stable id merge
    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(set(ids))

    edge_ids = [e["id"] for e in graph["edges"]]
    assert len(edge_ids) == len(set(edge_ids)), "edge ids must stay unique for rewire/render"

    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(graph)

    # A→B 경로 — 노드 id는 라우트에서 파생되므로 그래프에서 찾아 쓴다 (하드코딩 금지)
    screens = {
        n["id"]: str(n["attributes"].get("route") or "")
        for n in graph["nodes"]
        if n["type"] == "screen"
    }
    a_id = next(nid for nid, route in screens.items() if route.endswith("/search"))
    b_id = next(nid for nid, route in screens.items() if ":" in route or "{" in route)
    paths = find_paths(graph, a_id, b_id)
    assert paths, "expected A→B path"
    assert all(p[0] == a_id and p[-1] == b_id for p in paths)


def test_find_paths_cycle_safe() -> None:
    graph = {
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
            {"from": "c", "to": "b"},
            {"from": "c", "to": "d"},
        ]
    }
    paths = find_paths(graph, "a", "d")
    assert paths == [["a", "b", "c", "d"]]


def test_commit_refs_separate_versions() -> None:
    fe = json.loads(FIXTURE_FE.read_text(encoding="utf-8"))
    be = json.loads(FIXTURE_BE.read_text(encoding="utf-8"))
    mapping = build_mappings(fe, be, project_id="PRJ-ig")
    fe_a = {**fe, "commitSha": "fe-aaa"}
    fe_b = {**fe, "commitSha": "fe-bbb"}
    g1 = compose_graph(fe_a, be, mapping, graph_id="IG-a")
    g2 = compose_graph(fe_b, be, mapping, graph_id="IG-b")
    assert g1["commitRefs"]["frontend"] != g2["commitRefs"]["frontend"]
    assert g1["graphId"] != g2["graphId"]


@pytest.mark.skipif(not (SAMPLE_FE.is_dir() and SAMPLE_BE.is_dir()), reason="samples missing")
def test_interaction_graph_api_on_live_chain() -> None:
    project = client.post("/api/projects", json={"name": "IG pilot"}).json()
    pid = project["id"]

    fe = client.post(
        "/api/analyses/frontend",
        json={"projectId": pid, "workspacePath": str(SAMPLE_FE), "commitSha": "fe-ig"},
    )
    assert fe.status_code == 200, fe.text
    assert fe.json()["status"] == "complete", fe.json().get("error")

    be = client.post(
        "/api/analyses/backend",
        json={"projectId": pid, "workspacePath": str(SAMPLE_BE), "commitSha": "be-ig"},
    )
    assert be.status_code == 200, be.text
    assert be.json()["status"] == "complete", be.json().get("error")

    mapped = client.post(
        f"/api/analyses/{pid}/api-mappings",
        json={
            "frontendAnalysisId": fe.json()["id"],
            "backendAnalysisId": be.json()["id"],
        },
    )
    assert mapped.status_code == 200, mapped.text

    graph_res = client.post(
        f"/api/analyses/{pid}/interaction-graphs",
        json={
            "frontendAnalysisId": fe.json()["id"],
            "backendAnalysisId": be.json()["id"],
            "mappingSetId": mapped.json()["mappingSetId"],
        },
    )
    assert graph_res.status_code == 200, graph_res.text
    body = graph_res.json()
    assert body["nodeCount"] >= 10
    assert body["edgeCount"] >= 8
    assert "node-screen-a-search" in body["primaryPath"]
    assert "node-screen-b-detail" in body["primaryPath"]

    listed = client.get("/api/interaction-graphs", params={"projectId": pid})
    assert listed.status_code == 200
    assert any(g["graphId"] == body["graphId"] for g in listed.json())

    got = client.get(f"/api/interaction-graphs/{body['graphId']}")
    assert got.status_code == 200
    assert got.json()["result"]["figmaRef"]["fileKey"] == "qpZeClozlSVQd6j8Od8P9x"

    paths = client.get(
        f"/api/interaction-graphs/{body['graphId']}/paths",
        params={"from": "node-screen-a-search", "to": "node-screen-b-detail"},
    )
    assert paths.status_code == 200
    assert paths.json()["count"] >= 1

    artifact = Path(body["artifactPath"])
    assert artifact.is_file()
    assert ARTIFACTS_ANALYSIS in artifact.parents or "interaction-graph.json" in artifact.name


def test_duplicate_endpoint_paths_get_unique_edge_ids() -> None:
    """Two controllers exposing the same endpoint must not share one edge id."""
    from app.skills.interaction_graph.script.compose_graph import _edge

    edges: list[dict] = []
    common = {"etype": "contains", "confidence": 0.75, "evidence": []}
    _edge(edges, eid="edge-be-req-post--transactions", frm="ep-writer", to="dto", **common)
    _edge(edges, eid="edge-be-req-post--transactions", frm="ep-monolith", to="dto", **common)
    # exact repeat is dropped rather than duplicated
    _edge(edges, eid="edge-be-req-post--transactions", frm="ep-writer", to="dto", **common)

    ids = [e["id"] for e in edges]
    assert len(edges) == 2
    assert len(ids) == len(set(ids)), ids
