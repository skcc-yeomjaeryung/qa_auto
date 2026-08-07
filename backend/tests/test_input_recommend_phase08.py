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
from app.skills.component_contract.script.build_contract import build_contract
from app.skills.input_recommend.script.recommend import (
    build_input_profile,
    generate_profile_cases,
    recommend_inputs,
)
from app.skills.interaction_graph.script.compose_graph import compose_graph
from app.skills.scenario_dsl.script.generate_dsl import generate_scenarios
from app.services.input_recommend_service import InputRecommendService

FIXTURE_FE = REPO_ROOT / "artifacts" / "analysis" / "AN-FE-5305d8bde832" / "frontend.json"
FIXTURE_BE = REPO_ROOT / "artifacts" / "analysis" / "AN-BE-5115c351b091" / "backend.json"
REC_SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "input_recommendation.schema.json"
PROF_SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "input_profile.schema.json"
ADAPTER = (
    REPO_ROOT / "packages" / "adapter-sdk" / "examples" / "ui-adapter.customer-search.json"
)
CATALOG = REPO_ROOT / "packages" / "test-data-catalog"
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
    store._recommendations.clear()
    store._profiles.clear()
    yield


client = TestClient(app)


def _adapter() -> dict:
    return json.loads(ADAPTER.read_text(encoding="utf-8"))


def _fe_be_contract():
    fe = json.loads(FIXTURE_FE.read_text(encoding="utf-8"))
    be = json.loads(FIXTURE_BE.read_text(encoding="utf-8"))
    mapping = build_mappings(fe, be, project_id="PRJ-ir")
    graph = compose_graph(fe, be, mapping, project_id="PRJ-ir", graph_id="IG-ir")
    contract = build_contract(
        fe, be, graph=graph, adapter=_adapter(), service_id="customer-search"
    )
    return fe, be, graph, contract


def test_input_recommend_skill_textbook() -> None:
    skill_md = (SKILL_HUB / "input_recommend" / "SKILL.md").read_text(encoding="utf-8")
    assert "QA.CODE.INPUT_RECOMMEND" in skill_md
    assert "## 14. Changelog" in skill_md
    wf = (
        REPO_ROOT / "backend" / "app" / "workflow_definitions" / "wf_input_recommend.yml"
    ).read_text(encoding="utf-8")
    assert "QA.CODE.INPUT_RECOMMEND" in wf


def test_fixture_priority_over_catalog() -> None:
    fe, be, _, contract = _fe_be_contract()
    result = recommend_inputs(
        contract=contract,
        frontend=fe,
        backend=be,
        catalog_root=CATALOG,
        service_id="customer-search",
        seed=42,
    )
    happy = [
        r
        for r in result["recommendations"]
        if r["field"] == "customerId" and r["category"] == "happy_path"
    ]
    assert happy, result["recommendations"]
    top = happy[0]
    assert top["value"] == "CUS-1001"
    sources = [s["source"] for s in top["sources"]]
    assert "fixture" in sources
    assert sources.index("fixture") == 0 or min(s["rank"] for s in top["sources"]) == 1


def test_categories_happy_restricted_not_found_invalid() -> None:
    fe, be, _, contract = _fe_be_contract()
    result = recommend_inputs(
        contract=contract,
        frontend=fe,
        backend=be,
        catalog_root=CATALOG,
        service_id="customer-search",
        seed=42,
    )
    cats = {r["category"] for r in result["recommendations"] if r["field"] == "customerId"}
    for needed in {
        "happy_path",
        "business_state",
        "not_found",
        "invalid_format",
        "missing_required",
    }:
        assert needed in cats, cats


def test_no_random_identifiers() -> None:
    fe, be, _, contract = _fe_be_contract()
    result = recommend_inputs(
        contract=contract,
        frontend=fe,
        backend=be,
        catalog_root=CATALOG,
        seed=42,
    )
    assert result["generator"]["policy"]["allowRandomIdentifiers"] is False
    for rec in result["recommendations"]:
        val = rec["value"]
        if isinstance(val, str) and val.startswith("CUS-") and rec["category"] == "happy_path":
            assert val in {"CUS-1001", "CUS-2002"}


def test_deterministic_seed() -> None:
    fe, be, _, contract = _fe_be_contract()
    a = recommend_inputs(contract=contract, frontend=fe, backend=be, catalog_root=CATALOG, seed=42)
    b = recommend_inputs(contract=contract, frontend=fe, backend=be, catalog_root=CATALOG, seed=42)
    assert a["recommendationId"] == b["recommendationId"]
    assert a["defaults"] == b["defaults"]
    c = recommend_inputs(contract=contract, frontend=fe, backend=be, catalog_root=CATALOG, seed=99)
    assert c["recommendationId"] != a["recommendationId"]


def test_pairwise_budget() -> None:
    fe, be, _, contract = _fe_be_contract()
    result = recommend_inputs(
        contract=contract, frontend=fe, backend=be, catalog_root=CATALOG, seed=42
    )
    cases, counts = generate_profile_cases(result, budget=3, seed=42)
    assert len(cases) <= 3
    assert sum(counts.values()) == len(cases)


def test_no_input_scenario_has_one_reproducible_empty_profile_case() -> None:
    result = recommend_inputs(
        contract={"contractId": "CC-no-input", "serviceId": "multi", "inputs": []},
        service_id="multi",
        scenario_id="SCN-screen",
        seed=42,
    )
    assert result["requiresInput"] is False
    profile = build_input_profile(result, scenario_id="SCN-screen", budget=1, seed=42)
    assert profile["cases"] == [
        {
            "caseId": "CASE-no-input-42-1",
            "category": "happy_path",
            "inputs": {},
            "expectedPath": "screen_observation",
            "reviewRequired": False,
            "sources": [
                {
                    "source": "scenario_contract",
                    "rank": 1,
                    "ref": "contract.inputs=[]",
                    "detail": "이 시나리오는 사용자 입력 없이 화면·동작을 관측합니다.",
                }
            ],
        }
    ]


def test_scenario_variant_overrides_generic_recommendation() -> None:
    class Scenario:
        result = {
            "inputDefaults": {"amount": "0"},
            "caseVariant": {
                "key": "below_minimum",
                "category": "validation",
                "validationOnly": True,
            },
        }

    scoped = InputRecommendService._scope_to_scenario(
        {
            "defaults": {"amount": "1000"},
            "recommendations": [{"field": "amount", "value": "1000", "category": "happy_path"}],
        },
        Scenario(),
    )
    assert scoped["defaults"] == {"amount": "0"}
    assert scoped["recommendations"][0]["value"] == "0"
    assert scoped["recommendations"][0]["expectedPath"] == "browser_validation"


def test_pii_masking() -> None:
    contract = {
        "contractId": "CC-mask",
        "serviceId": "customer-search",
        "inputs": [{"field": "password", "required": True}],
    }
    result = recommend_inputs(
        contract=contract,
        catalog_root=CATALOG,
        sheet={
            "rows": [
                {
                    "rowId": "r1",
                    "serviceOrTxnId": "customer-search",
                    "approvalStatus": "draft",
                    "request": {"password": "secret-value-xyz"},
                }
            ]
        },
        seed=42,
    )
    pwd_recs = [r for r in result["recommendations"] if r["field"] == "password"]
    assert pwd_recs == []
    assert "secret-value-xyz" not in json.dumps(result)
    assert any(
        conflict.get("kind") == "environment_credential_required"
        for conflict in result["conflicts"]
    )


def test_unresolved_skip_policy() -> None:
    fe, be, _, contract = _fe_be_contract()
    result = recommend_inputs(
        contract=contract, frontend=fe, backend=be, catalog_root=CATALOG, seed=42
    )
    cases_skip, _ = generate_profile_cases(
        result, budget=20, unresolved_policy="skip", seed=42
    )
    cases_keep, _ = generate_profile_cases(
        result, budget=20, unresolved_policy="reviewRequired", seed=42
    )
    assert len(cases_skip) <= len(cases_keep)


def test_schema_validation_recommendation_and_profile() -> None:
    fe, be, _, contract = _fe_be_contract()
    result = recommend_inputs(
        contract=contract, frontend=fe, backend=be, catalog_root=CATALOG, seed=42
    )
    Draft202012Validator(json.loads(REC_SCHEMA.read_text(encoding="utf-8"))).validate(result)
    profile = build_input_profile(result, scenario_id="SCN-x", budget=6, seed=42)
    Draft202012Validator(json.loads(PROF_SCHEMA.read_text(encoding="utf-8"))).validate(profile)


def test_hub_loaded() -> None:
    health = client.get("/health").json()
    assert health["hubCounts"]["skills"] >= 8
    assert health["hubCounts"]["workflows"] >= 8


def test_api_recommend_profile_approve() -> None:
    from app.services.analysis_models import AnalysisSummary
    from app.services.interaction_graph_models import InteractionGraphSummary
    from app.services.repository_models import utc_now
    from app.services.scenario_models import ScenarioSummary

    fe, be, graph, _ = _fe_be_contract()
    store = get_platform_store()
    fe_id, be_id, graph_id = "AN-FE-ir", "AN-BE-ir", "IG-ir-api"
    store.save_analysis(
        AnalysisSummary(
            id=fe_id,
            projectId="PRJ-ir",
            role="frontend",
            status="complete",
            createdAt=utc_now().isoformat(),
            result=fe,
        )
    )
    store.save_analysis(
        AnalysisSummary(
            id=be_id,
            projectId="PRJ-ir",
            role="backend",
            status="complete",
            createdAt=utc_now().isoformat(),
            result=be,
        )
    )
    store.save_graph(
        InteractionGraphSummary(
            graphId=graph_id,
            projectId="PRJ-ir",
            frontendAnalysisId=fe_id,
            backendAnalysisId=be_id,
            serviceId="customer-search",
            status="complete",
            nodeCount=len(graph.get("nodes") or []),
            edgeCount=len(graph.get("edges") or []),
            createdAt=utc_now().isoformat(),
            result=graph,
        )
    )
    scn = generate_scenarios(graph, service_id="customer-search", project_id="PRJ-ir")[0]
    store.save_scenario(
        ScenarioSummary(
            scenarioId=scn["scenarioId"],
            serviceId="customer-search",
            projectId="PRJ-ir",
            graphId=graph_id,
            name=scn["name"],
            status=scn["status"],
            createdAt=utc_now().isoformat(),
            result=scn,
        )
    )
    sid = scn["scenarioId"]

    rec = client.post(
        f"/api/scenarios/{sid}/recommend-inputs",
        json={"seed": 42, "buildProfile": False},
    )
    assert rec.status_code == 200, rec.text
    body = rec.json()
    assert body["recommendationCount"] >= 1
    assert body["result"]["defaults"].get("customerId") == "CUS-1001"

    prof = client.post(
        f"/api/scenarios/{sid}/input-profiles",
        json={"name": "batch-v1", "seed": 42, "budget": 5},
    )
    assert prof.status_code == 200, prof.text
    profile = prof.json()
    assert profile["status"] == "DRAFT"
    assert profile["caseCount"] <= 5
    assert profile["result"]["policy"]["excludeDestructive"] is True

    approved = client.post(
        f"/api/input-profiles/{profile['profileId']}/approve",
        json={"approvedBy": "qa-pilot"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["version"] == "1"

    regen = client.post(
        f"/api/input-profiles/{profile['profileId']}/generate-cases",
        json={"budget": 4, "seed": 42},
    )
    assert regen.status_code == 200
    assert regen.json()["caseCount"] <= 4


@pytest.mark.skipif(not (SAMPLE_JAVA / "frontend").is_dir(), reason="sample_java missing")
def test_pipeline_includes_recommend() -> None:
    project = client.post("/api/projects", json={"name": "ir-chain"}).json()
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
    # 저장소 세트 ID는 저장소 등록 응답에서 받는다 (프로젝트 생성 시점에는 아직 없다)
    set_id = be.json()["id"]
    assert client.post(f"/api/repository-sets/{set_id}/sync").status_code == 200
    pipe = client.post(
        f"/api/projects/{pid}/pipeline/analyze-to-scenarios",
        json={"serviceId": "customer-search"},
    )
    assert pipe.status_code == 200, pipe.text
    body = pipe.json()
    assert body["status"] == "complete", body
    assert body.get("recommendationIds"), body
    sid = body["scenarioIds"][0]
    got = client.get(f"/api/scenarios/{sid}/recommend-inputs")
    assert got.status_code == 200
    assert got.json()["result"]["defaults"].get("customerId")
