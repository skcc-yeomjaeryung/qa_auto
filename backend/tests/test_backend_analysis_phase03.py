from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import BACKEND_ANALYZER_WORKER, BACKEND_ROOT, SKILL_HUB
from app.main import app

REPO = Path(__file__).resolve().parents[2]
SAMPLE_BE = REPO / "sample-targets" / "customer-service-be"


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


def test_backend_skill_textbook_sections() -> None:
    skill_md = (SKILL_HUB / "backend_spring_analyze" / "SKILL.md").read_text(encoding="utf-8")
    for header in (
        "## 1. Skill Purpose",
        "## 14. Changelog",
        "QA.CODE.BACKEND_SPRING_ANALYZE",
        "script: script/analyze.py",
        "JavaParser",
    ):
        assert header in skill_md


def test_backend_workflow_hub() -> None:
    import yaml

    path = BACKEND_ROOT / "app" / "workflow_definitions" / "wf_backend_spring_analyze.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["workflow_id"] == "wf_backend_spring_analyze"
    assert data["required_capabilities"][0]["capability_id"] == "QA.CODE.BACKEND_SPRING_ANALYZE"


def test_worker_is_python_not_javaparser() -> None:
    assert (BACKEND_ANALYZER_WORKER / "app" / "cli.py").is_file()
    assert (BACKEND_ANALYZER_WORKER / "pyproject.toml").is_file()
    assert not list(BACKEND_ANALYZER_WORKER.rglob("**/JavaParser*"))
    assert not (BACKEND_ANALYZER_WORKER / "build.gradle").exists()


@pytest.mark.skipif(not SAMPLE_BE.is_dir(), reason="sample BE missing")
def test_backend_analysis_api_on_sample() -> None:
    project = client.post("/api/projects", json={"name": "BE analysis"}).json()
    response = client.post(
        "/api/analyses/backend",
        json={
            "projectId": project["id"],
            "workspacePath": str(SAMPLE_BE),
            "commitSha": "test-be",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "complete", body.get("error")
    assert body["role"] == "backend"
    analysis_id = body["id"]
    assert body["endpointCount"] >= 1
    assert body["fileTotal"] >= 1
    assert body["fileCompleted"] == body["fileTotal"]
    assert body["progressPercent"] == 100

    endpoints = client.get(f"/api/analyses/{analysis_id}/backend/endpoints").json()
    assert any(e["method"] == "POST" and e["path"] == "/api/customers/search" for e in endpoints)

    full = client.get(f"/api/analyses/{analysis_id}/backend").json()
    assert any(d["name"] == "CustomerSearchRequest" for d in full["requestDtos"])
    assert any(d["name"] == "CustomerResponse" for d in full["responseDtos"])
    assert any(v["field"] == "customerId" for v in full["validations"])
    assert any(t.get("framework") == "mockmvc" for t in full["existingTests"])
    assert Path(body["artifactPath"]).is_file()

    ep = next(e for e in endpoints if e["path"] == "/api/customers/search")
    detail = client.get(f"/api/analyses/{analysis_id}/backend/endpoints/{ep['id']}")
    assert detail.status_code == 200
    unresolved = client.get(f"/api/analyses/{analysis_id}/backend/unresolved").json()
    assert isinstance(unresolved, list)
