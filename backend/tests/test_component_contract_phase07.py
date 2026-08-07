from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import REPO_ROOT, SKILL_HUB
from app.main import app
from app.skills.api_map.script.map_apis import build_mappings
from app.skills.component_contract.script.build_contract import (
    _choose_locator,
    build_contract,
)
from app.skills.interaction_graph.script.compose_graph import compose_graph
from app.skills.scenario_dsl.script.generate_dsl import generate_scenarios

FIXTURE_FE = REPO_ROOT / "artifacts" / "analysis" / "AN-FE-5305d8bde832" / "frontend.json"
FIXTURE_BE = REPO_ROOT / "artifacts" / "analysis" / "AN-BE-5115c351b091" / "backend.json"
SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "component_contract.schema.json"
ADAPTER = (
    REPO_ROOT / "packages" / "adapter-sdk" / "examples" / "ui-adapter.customer-search.json"
)
SAMPLE_JAVA = Path("/Users/a11123/Desktop/sample_java")


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
    store._contracts.clear()
    if hasattr(store, "_recommendations"):
        store._recommendations.clear()
    if hasattr(store, "_profiles"):
        store._profiles.clear()
    yield


client = TestClient(app)


def _adapter() -> dict:
    return json.loads(ADAPTER.read_text(encoding="utf-8"))


def _fe_be_graph():
    fe = json.loads(FIXTURE_FE.read_text(encoding="utf-8"))
    be = json.loads(FIXTURE_BE.read_text(encoding="utf-8"))
    mapping = build_mappings(fe, be, project_id="PRJ-cc")
    graph = compose_graph(fe, be, mapping, project_id="PRJ-cc", graph_id="IG-cc")
    return fe, be, graph


def test_component_contract_skill_textbook() -> None:
    skill_md = (SKILL_HUB / "component_contract" / "SKILL.md").read_text(encoding="utf-8")
    assert "QA.CODE.COMPONENT_CONTRACT" in skill_md
    assert "## 14. Changelog" in skill_md
    wf = (
        REPO_ROOT
        / "backend"
        / "app"
        / "workflow_definitions"
        / "wf_component_contract.yml"
    ).read_text(encoding="utf-8")
    assert "QA.CODE.COMPONENT_CONTRACT" in wf


def test_locator_priority_testid_over_css() -> None:
    loc = _choose_locator(
        {"testId": "customer-id-input", "label": "Customer", "name": "customer-id"}
    )
    assert loc["strategy"] == "testId"
    assert loc["stable"] is True


def test_unstable_css_locator_warning() -> None:
    fe, be, graph = _fe_be_graph()
    contract = build_contract(
        fe,
        be,
        graph=graph,
        adapter=_adapter(),
        force_unstable_css_for="customerId",
    )
    assert any(w["kind"] == "unstable_locator" for w in contract["warnings"])
    customer = next(i for i in contract["inputs"] if i["field"] == "customerId")
    assert customer["locator"]["strategy"] == "css"
    assert customer["reviewRequired"] is True


def test_native_input_and_button_events() -> None:
    fe, be, graph = _fe_be_graph()
    contract = build_contract(fe, be, graph=graph, adapter=_adapter())
    customer = next(i for i in contract["inputs"] if i["field"] == "customerId")
    assert "fill" in customer["events"]
    assert customer["required"] is True
    assert customer["pattern"]
    assert any(a["kind"] == "button" for a in contract["actions"])
    submit = next(a for a in contract["actions"] if "submit" in (a.get("logicalName") or "").lower() or a["locator"].get("value") == "customer-search-submit")
    assert "click" in submit["events"]


def test_bizinput_adapter_mapping() -> None:
    adapter = _adapter()
    assert any(c["name"] == "BizInput" for c in adapter["components"])
    fe = {
        "screens": [{"name": "SearchPage", "route": "/customers/search"}],
        "inputs": [
            {
                "id": "biz-1",
                "name": "customerId",
                "kind": "BizInput",
                "testId": "biz-customer-id",
                "required": True,
                "constraints": {},
                "evidence": {"file": "BizForm.tsx", "line": 10},
            }
        ],
        "events": [],
        "validations": [],
    }
    contract = build_contract(fe, {}, adapter=adapter)
    item = contract["inputs"][0]
    assert item["componentType"] == "BizInput"
    assert "fill" in item["events"]


def test_b_four_bindings_and_mask() -> None:
    fe, be, graph = _fe_be_graph()
    contract = build_contract(fe, be, graph=graph, adapter=_adapter())
    fields = {o["field"] for o in contract["outputs"]}
    assert fields == {"customerId", "customerName", "riskLevel", "status"}
    risk = next(o for o in contract["outputs"] if o["field"] == "riskLevel")
    assert risk["responsePath"] == "$.riskLevel"
    assert risk["uiLocator"]["value"] == "customer-detail-risk"
    assert "uppercase" in risk["normalize"]
    masks = contract["screenshotHooks"]["maskRegions"]
    assert any(m["locator"]["value"] == "customer-id-input" for m in masks)


def test_schema_validation() -> None:
    fe, be, graph = _fe_be_graph()
    contract = build_contract(fe, be, graph=graph, adapter=_adapter(), service_id="customer-search")
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(contract)


def test_multi_service_contract_is_scoped_to_scenario_inputs() -> None:
    frontend = {
        "commitSha": "fe-scope",
        "screens": [
            {"name": "Login", "route": "/login"},
            {"name": "Home", "route": "/home"},
        ],
        "inputs": [
            {"name": "username", "kind": "input", "constraints": {"id": "login-username"}},
            {"name": "password", "kind": "input", "constraints": {"id": "login-password"}},
            {"name": "amount", "kind": "input", "constraints": {"id": "deposit-amount"}},
        ],
        "events": [],
        "validations": [],
    }
    scenario = {
        "source": {"screen": "Login", "route": "/login"},
        "destination": {"screen": "Home", "routePattern": "/home"},
        "inputs": [
            {
                "name": "username",
                "required": True,
                "locator": {"strategy": "css", "value": "#login-username"},
            }
        ],
        "bindings": {"beforeAfter": ["#account-user-name"]},
    }
    contract = build_contract(
        frontend,
        {},
        service_id="multi",
        scenario_id="SCN-login",
        scenario=scenario,
    )
    assert [item["field"] for item in contract["inputs"]] == ["username"]
    assert "amount" not in {item["field"] for item in contract["inputs"]}
    assert contract["outputs"] == []
    assert contract["screenA"]["route"] == "/login"


def test_scenario_contract_does_not_invent_outputs_for_ui_hints_or_na_route() -> None:
    contract = build_contract(
        {"commitSha": "fe-ui", "screens": [{"name": "Index", "route": "/"}]},
        {},
        service_id="multi",
        scenario_id="SCN-index",
        scenario={
            "source": {"screen": "Index", "route": "/"},
            "destination": {"screen": "n/a", "routePattern": "n/a"},
            "bindings": {"beforeAfter": ["#account-user-name"]},
            "inputs": [],
        },
    )
    assert contract["outputs"] == []


def test_hub_loaded() -> None:
    health = client.get("/health").json()
    assert health["hubCounts"]["skills"] >= 7
    assert health["hubCounts"]["workflows"] >= 7


@pytest.mark.skipif(not (SAMPLE_JAVA / "frontend").is_dir(), reason="sample_java missing")
def test_api_build_contract_after_pipeline() -> None:
    project = client.post("/api/projects", json={"name": "cc-chain"}).json()
    pid = project["id"]
    assert (
        client.post(
            f"/api/projects/{pid}/repositories",
            json={"role": "frontend", "sourceType": "local", "path": str(SAMPLE_JAVA / "frontend")},
        ).status_code
        == 201
    )
    be = client.post(
        f"/api/projects/{pid}/repositories",
        json={"role": "backend", "sourceType": "local", "path": str(SAMPLE_JAVA / "backend")},
    )
    assert be.status_code == 201
    sync = client.post(f"/api/repository-sets/{be.json()['id']}/sync")
    assert sync.status_code == 200
    pipe = client.post(
        f"/api/projects/{pid}/pipeline/analyze-to-scenarios",
        json={"serviceId": "customer-search"},
    )
    assert pipe.status_code == 200, pipe.text
    body = pipe.json()
    assert body["status"] == "complete", body
    assert body.get("contractIds"), body
    sid = body["scenarioIds"][0]
    got = client.get(f"/api/scenarios/{sid}/component-contract")
    assert got.status_code == 200
    result = got.json()["result"]
    assert len(result["outputs"]) == 4
    assert any(i["field"] == "customerId" for i in result["inputs"])


def test_post_contract_from_fixture_scenario() -> None:
    """Store a synthetic scenario + analyses, then POST contract."""
    from app.services.analysis_models import AnalysisSummary
    from app.services.interaction_graph_models import InteractionGraphSummary
    from app.services.scenario_models import ScenarioSummary
    from app.services.repository_models import utc_now

    fe, be, graph = _fe_be_graph()
    store = get_platform_store()
    fe_id = "AN-FE-test07"
    be_id = "AN-BE-test07"
    graph_id = "IG-test07"
    store.save_analysis(
        AnalysisSummary(
            id=fe_id,
            projectId="PRJ-t07",
            role="frontend",
            status="complete",
            createdAt=utc_now().isoformat(),
            result=fe,
        )
    )
    store.save_analysis(
        AnalysisSummary(
            id=be_id,
            projectId="PRJ-t07",
            role="backend",
            status="complete",
            createdAt=utc_now().isoformat(),
            result=be,
        )
    )
    store.save_graph(
        InteractionGraphSummary(
            graphId=graph_id,
            projectId="PRJ-t07",
            frontendAnalysisId=fe_id,
            backendAnalysisId=be_id,
            serviceId="customer-search",
            status="complete",
            nodeCount=graph.get("nodeCount") or len(graph.get("nodes") or []),
            edgeCount=graph.get("edgeCount") or len(graph.get("edges") or []),
            createdAt=utc_now().isoformat(),
            result=graph,
        )
    )
    scn = generate_scenarios(graph, service_id="customer-search", project_id="PRJ-t07")[0]
    store.save_scenario(
        ScenarioSummary(
            scenarioId=scn["scenarioId"],
            serviceId="customer-search",
            projectId="PRJ-t07",
            graphId=graph_id,
            name=scn["name"],
            status=scn["status"],
            createdAt=utc_now().isoformat(),
            result=scn,
        )
    )
    res = client.post(f"/api/scenarios/{scn['scenarioId']}/component-contract", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outputCount"] == 4
    assert body["inputCount"] >= 1
