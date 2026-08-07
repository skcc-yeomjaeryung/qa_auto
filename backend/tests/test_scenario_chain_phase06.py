from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import BACKEND_ROOT, REPO_ROOT, SKILL_HUB
from app.main import app
from app.skills.api_map.script.map_apis import build_mappings
from app.skills.interaction_graph.script.compose_graph import compose_graph
from app.skills.scenario_dsl.script.generate_dsl import generate_scenarios

SAMPLE_JAVA = Path("/Users/a11123/Desktop/sample_java")
FIXTURE_FE = REPO_ROOT / "artifacts" / "analysis" / "AN-FE-5305d8bde832" / "frontend.json"
FIXTURE_BE = REPO_ROOT / "artifacts" / "analysis" / "AN-BE-5115c351b091" / "backend.json"
SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "scenario_dsl.schema.json"
BANK_URL = "https://github.com/GoogleCloudPlatform/bank-of-anthos.git"


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
    store._scenarios.clear()
    yield


client = TestClient(app)


def test_scenario_skill_textbook() -> None:
    skill_md = (SKILL_HUB / "scenario_dsl" / "SKILL.md").read_text(encoding="utf-8")
    assert "QA.CODE.SCENARIO_DSL" in skill_md
    assert "## 14. Changelog" in skill_md


def test_generate_dsl_schema() -> None:
    fe = json.loads(FIXTURE_FE.read_text(encoding="utf-8"))
    be = json.loads(FIXTURE_BE.read_text(encoding="utf-8"))
    mapping = build_mappings(fe, be, project_id="PRJ-dsl")
    graph = compose_graph(fe, be, mapping, project_id="PRJ-dsl", graph_id="IG-dsl")
    scenarios = generate_scenarios(graph, service_id="customer-search", project_id="PRJ-dsl")
    assert scenarios
    # serviceId는 그래프에서 관측한 화면·엔드포인트에서 파생된다 (요청 인자를 그대로 쓰지 않는다).
    assert all(scn["serviceId"] for scn in scenarios)
    assert any("customer" in scn["serviceId"] for scn in scenarios), [
        scn["serviceId"] for scn in scenarios
    ]
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    for scn in scenarios:
        body = dict(scn)
        for key in ("serviceId", "projectId", "unresolved", "evidenceIndex", "generatedAt"):
            body.pop(key, None)
        validator.validate(body)


@pytest.mark.skipif(not (SAMPLE_JAVA / "frontend").is_dir(), reason="sample_java monorepo missing")
def test_local_monorepo_pipeline_and_flow_lookup() -> None:
    project = client.post("/api/projects", json={"name": "sample_java chain"}).json()
    pid = project["id"]

    fe = client.post(
        f"/api/projects/{pid}/repositories",
        json={
            "role": "frontend",
            "sourceType": "local",
            "path": str(SAMPLE_JAVA / "frontend"),
        },
    )
    assert fe.status_code == 201, fe.text
    be = client.post(
        f"/api/projects/{pid}/repositories",
        json={
            "role": "backend",
            "sourceType": "local",
            "path": str(SAMPLE_JAVA / "backend"),
        },
    )
    assert be.status_code == 201, be.text

    sync = client.post(
        f"/api/repository-sets/{be.json()['id']}/sync",
        json={"force": False},
    )
    assert sync.status_code == 200, sync.text
    assert sync.json()["status"] in ("complete", "cached")

    pipe = client.post(
        f"/api/projects/{pid}/pipeline/analyze-to-scenarios",
        json={"serviceId": "customer-search"},
    )
    assert pipe.status_code == 200, pipe.text
    body = pipe.json()
    assert body["status"] == "complete", body
    assert body["graphId"]
    assert body["scenarioIds"]

    listed = client.get("/api/scenarios", params={"projectId": pid})
    assert listed.status_code == 200
    assert len(listed.json()) >= 1

    flow = client.get(
        "/api/flows/by-service/customer-search",
        params={"projectId": pid},
    )
    assert flow.status_code == 200
    assert flow.json()["graphId"] == body["graphId"]


@pytest.mark.skipif(True, reason="live bank-of-anthos clone is slow; run manually in chain-verify")
def test_bank_of_anthos_github_sync() -> None:
    project = client.post("/api/projects", json={"name": "boa"}).json()
    pid = project["id"]
    for role, subdir in (("frontend", "src/frontend"), ("backend", "src/ledger/ledgerwriter")):
        reg = client.post(
            f"/api/projects/{pid}/repositories",
            json={
                "role": role,
                "sourceType": "github",
                "url": BANK_URL,
                "subdir": subdir,
                "branch": "main",
            },
        )
        assert reg.status_code == 201, reg.text
        set_id = reg.json()["id"]
    sync = client.post(
        f"/api/repository-sets/{set_id}/sync",
        json={"force": False},
    )
    assert sync.status_code == 200
    repos = sync.json()["repositories"]
    assert all(r["syncStatus"] in ("complete", "cached") for r in repos)
    assert all(r.get("subdir") for r in repos)
