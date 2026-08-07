from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import BACKEND_ROOT, FRONTEND_ANALYZER_WORKER, SKILL_HUB
from app.main import app

REPO = Path(__file__).resolve().parents[2]
SAMPLE_FE = REPO / "sample-targets" / "customer-portal-fe"


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


def test_frontend_analyze_skill_textbook_sections() -> None:
    skill_md = (SKILL_HUB / "frontend_analyze" / "SKILL.md").read_text(encoding="utf-8")
    for header in (
        "## 1. Skill Purpose",
        "## 14. Changelog",
        "QA.CODE.FRONTEND_ANALYZE",
        "script: script/analyze.py",
    ):
        assert header in skill_md


def test_frontend_analyze_workflow_hub() -> None:
    import yaml

    path = BACKEND_ROOT / "app" / "workflow_definitions" / "wf_frontend_analyze.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["workflow_id"] == "wf_frontend_analyze"
    assert data["required_capabilities"][0]["capability_id"] == "QA.CODE.FRONTEND_ANALYZE"
    assert data["execution_policy"]["execution_pattern"] == "plan_execute_review_reduce"


def test_worker_present() -> None:
    assert (FRONTEND_ANALYZER_WORKER / "src" / "cli.ts").is_file()
    assert (FRONTEND_ANALYZER_WORKER / "src" / "analyze.ts").is_file()


@pytest.mark.skipif(not SAMPLE_FE.is_dir(), reason="sample FE missing")
def test_frontend_analysis_api_on_sample() -> None:
    project = client.post("/api/projects", json={"name": "FE analysis"}).json()
    response = client.post(
        "/api/analyses/frontend",
        json={
            "projectId": project["id"],
            "workspacePath": str(SAMPLE_FE),
            "commitSha": "test-commit",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "complete", body.get("error")
    analysis_id = body["id"]
    assert body["role"] == "frontend"
    assert body["screenCount"] >= 1
    assert body["fileTotal"] >= 1
    assert body["fileCompleted"] == body["fileTotal"]
    assert body["progressPercent"] == 100

    screens = client.get(f"/api/analyses/{analysis_id}/frontend/screens").json()
    assert any(s["route"] == "/customers/search" for s in screens)

    full = client.get(f"/api/analyses/{analysis_id}/frontend").json()
    assert any(
        a["method"] == "POST" and a["normalizedPath"] == "/api/customers/search"
        for a in full["apiCalls"]
    )
    assert any(v.get("field") == "customerId" or "customerId" in str(v) for v in full["validations"]) or any(
        "zod" in (v.get("kind") or "") for v in full["validations"]
    )
    unresolved = client.get(f"/api/analyses/{analysis_id}/frontend/unresolved").json()
    assert isinstance(unresolved, list)

    if full["components"]:
        cid = full["components"][0]["id"]
        detail = client.get(f"/api/analyses/{analysis_id}/frontend/components/{cid}")
        assert detail.status_code == 200

    artifact = Path(body["artifactPath"])
    assert artifact.is_file()
