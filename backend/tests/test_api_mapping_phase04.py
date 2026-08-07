from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import ARTIFACTS_ANALYSIS, BACKEND_ROOT, REPO_ROOT, SKILL_HUB
from app.main import app
from app.skills.api_map.script.map_apis import build_mappings, normalize_path

SAMPLE_FE = REPO_ROOT / "sample-targets" / "customer-portal-fe"
SAMPLE_BE = REPO_ROOT / "sample-targets" / "customer-service-be"
FIXTURE_FE = REPO_ROOT / "artifacts" / "analysis" / "AN-FE-5305d8bde832" / "frontend.json"
FIXTURE_BE = REPO_ROOT / "artifacts" / "analysis" / "AN-BE-5115c351b091" / "backend.json"


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
    if hasattr(store, "_graphs"):
        store._graphs.clear()
    if hasattr(store, "_scenarios"):
        store._scenarios.clear()
    yield


client = TestClient(app)


def test_normalize_path_variants() -> None:
    assert normalize_path("http://127.0.0.1:8080/api/customers/search") == "/api/customers/search"
    assert normalize_path("/api/customers/${id}") == "/api/customers/{id}"
    assert normalize_path("/api/customers/:customerId") == "/api/customers/{customerId}"
    assert normalize_path("/api/customers/{customerId}") == "/api/customers/{customerId}"


def test_api_map_skill_textbook() -> None:
    skill_md = (SKILL_HUB / "api_map" / "SKILL.md").read_text(encoding="utf-8")
    for header in ("## 1. Skill Purpose", "## 14. Changelog", "QA.CODE.API_MAP", "script: script/map_apis.py"):
        assert header in skill_md


def test_api_map_workflow_hub() -> None:
    import yaml

    data = yaml.safe_load(
        (BACKEND_ROOT / "app" / "workflow_definitions" / "wf_api_map.yml").read_text(encoding="utf-8")
    )
    assert data["workflow_id"] == "wf_api_map"
    assert data["required_capabilities"][0]["capability_id"] == "QA.CODE.API_MAP"


def test_build_mappings_from_fixtures() -> None:
    assert FIXTURE_FE.is_file() and FIXTURE_BE.is_file()
    fe = json.loads(FIXTURE_FE.read_text(encoding="utf-8"))
    be = json.loads(FIXTURE_BE.read_text(encoding="utf-8"))
    result = build_mappings(fe, be, project_id="PRJ-test")
    assert result["schemaVersion"] == "api-mapping/v1"
    confirmed = [m for m in result["mappings"] if m["status"] == "confirmed"]
    assert confirmed, result["summary"]
    mapping = confirmed[0]
    assert mapping["method"] == "POST"
    assert mapping["normalizedPath"] == "/api/customers/search"
    assert mapping["backendEndpointId"]
    assert any(f.get("frontendField") == "customerId" for f in mapping["requestFieldMappings"])
    res_names = {f.get("backendField") for f in mapping["responseFieldMappings"]}
    assert {"customerName", "riskLevel", "status"} <= res_names
    assert isinstance(mapping["mismatches"], list)


def test_ambiguous_not_auto_confirmed() -> None:
    fe = {
        "apiCalls": [
            {
                "id": "fe-1",
                "method": "GET",
                "normalizedPath": "/api/items/{id}",
                "path": "/api/items/1",
                "evidence": {"file": "a.ts", "line": 1},
            }
        ],
        "validations": [],
        "inputs": [],
    }
    be = {
        "endpoints": [
            {
                "id": "be-1",
                "method": "GET",
                "path": "/api/items/{id}",
                "requestDto": None,
                "responseDto": None,
                "evidence": {"file": "A.java", "line": 1},
            },
            {
                "id": "be-2",
                "method": "GET",
                "path": "/api/items/{itemId}",
                "requestDto": None,
                "responseDto": None,
                "evidence": {"file": "B.java", "line": 1},
            },
        ],
        "requestDtos": [],
        "responseDtos": [],
        "validations": [],
    }
    # After normalize both become /api/items/{id} and /api/items/{itemId} — different.
    # Force same normalized path:
    be["endpoints"][1]["path"] = "/api/items/{id}"
    result = build_mappings(fe, be)
    assert result["mappings"][0]["status"] == "ambiguous"
    assert result["mappings"][0]["backendEndpointId"] is None
    assert len(result["mappings"][0]["candidates"]) >= 2


@pytest.mark.skipif(not (SAMPLE_FE.is_dir() and SAMPLE_BE.is_dir()), reason="samples missing")
def test_api_mapping_api_on_live_analyses() -> None:
    project = client.post("/api/projects", json={"name": "Map pilot"}).json()
    pid = project["id"]

    fe = client.post(
        "/api/analyses/frontend",
        json={"projectId": pid, "workspacePath": str(SAMPLE_FE), "commitSha": "fe-map"},
    )
    assert fe.status_code == 200, fe.text
    assert fe.json()["status"] == "complete", fe.json().get("error")

    be = client.post(
        "/api/analyses/backend",
        json={"projectId": pid, "workspacePath": str(SAMPLE_BE), "commitSha": "be-map"},
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
    body = mapped.json()
    assert body["summary"]["confirmed"] >= 1
    assert any(
        m["normalizedPath"] == "/api/customers/search" and m["status"] == "confirmed"
        for m in body["mappings"]
    )
    mapping_id = next(m["mappingId"] for m in body["mappings"] if m["status"] == "confirmed")

    listed = client.get(f"/api/analyses/{pid}/api-mappings")
    assert listed.status_code == 200
    assert len(listed.json()) >= 1

    patched = client.patch(
        f"/api/api-mappings/{mapping_id}",
        json={"status": "confirmed", "note": "manual review ok"},
    )
    assert patched.status_code == 200
    assert patched.json()["auditTrail"]
    assert patched.json()["auditTrail"][-1]["note"] == "manual review ok"

    artifact = Path(body["artifactPath"])
    assert artifact.is_file()
    assert ARTIFACTS_ANALYSIS in artifact.parents or "api-mapping.json" in artifact.name
