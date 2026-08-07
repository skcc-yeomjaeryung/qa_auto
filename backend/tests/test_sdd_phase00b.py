from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.bootstrap import bootstrap_runtime
from app.core.paths import BACKEND_ROOT
from app.main import app


def setup_module() -> None:
    bootstrap_runtime()


client = TestClient(app)


def test_health_reports_hub_counts() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["hubCounts"]["workflows"] >= 1
    assert body["hubCounts"]["skills"] >= 1
    assert body["hubCounts"]["capabilities"] >= 1


def test_execute_health_ping_smoke() -> None:
    res = client.post(
        "/api/runs/execute",
        json={"workflowId": "wf_health_smoke", "inputs": {"hello": "world"}},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "complete"
    assert body["plan"]["workflowId"] == "wf_health_smoke"
    assert body["plan"]["steps"][0]["stepId"] == "step_01"
    assert body["plan"]["steps"][0]["skill"] == "health_ping"
    assert body["plan"]["steps"][0]["tool"] == "ping"
    assert body["stepResults"][0]["output"]["ok"] is True
    assert body["stepResults"][0]["output"]["echo"]["hello"] == "world"
    assert "HITL not decided" in body["summary"]


def test_unknown_workflow_rejected() -> None:
    res = client.post("/api/runs/execute", json={"workflowId": "wf_not_in_hub"})
    assert res.status_code == 404


def test_no_graph_manifest() -> None:
    assert not (BACKEND_ROOT / "app" / "graph_manifest.yml").exists()
    assert not list(Path(BACKEND_ROOT / "app").rglob("graph_manifest.yml"))


def test_skill_follows_textbook_sections() -> None:
    skill_md = (BACKEND_ROOT / "app" / "skills" / "health_ping" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for header in (
        "## 1. Skill Purpose",
        "## 14. Changelog",
        "provided_capabilities:",
        "script: script/ping.py",
        "sample_input/ping_request.json",
    ):
        assert header in skill_md


def test_workflow_follows_textbook_fields() -> None:
    import yaml

    path = BACKEND_ROOT / "app" / "workflow_definitions" / "wf_health_smoke.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["workflow_id"] == "wf_health_smoke"
    assert "trigger_intents" in data
    assert "business_goal" in data
    assert "execution_policy" in data
    assert data["execution_policy"]["execution_pattern"] == "plan_execute_review_reduce"
    assert data["required_capabilities"][0]["capability_id"] == "QA.PLATFORM.HEALTH_PING"
    assert data["logical_steps"][0]["required_capability"] == "QA.PLATFORM.HEALTH_PING"
    assert "graph" not in data and "nodes" not in data
