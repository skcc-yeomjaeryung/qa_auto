"""Phase 1 — ExecutionEnvironment CRUD + health-check + run baseUrl resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.main import app
from app.services.environment_models import (
    CYMBAL_BANK_HOME_PATH,
    CYMBAL_BANK_FRONTEND_URL,
    CYMBAL_BANK_ORIGIN,
    PILOT_SANDBOX_LOGIN_ID,
    PILOT_SANDBOX_BASE_URL,
    HealthStatus,
)
from app.services.environment_service import EnvironmentService, build_health_url
from app.services.run_models import RunCreateRequest
from app.services.run_service import BrowserRunService
from app.services.scenario_models import ScenarioSummary


@pytest.fixture(autouse=True)
def fresh_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = get_platform_store()
    store._projects.clear()
    store._sets.clear()
    store._files.clear()
    store._commit_cache.clear()
    store._tokens.clear()
    if hasattr(store, "_environments"):
        store._environments.clear()
    if hasattr(store, "_scenarios"):
        store._scenarios.clear()
    if hasattr(store, "_runs"):
        store._runs.clear()
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    from app.utils import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


client = TestClient(app)


def test_pilot_sandbox_default_is_cymbal_home() -> None:
    # 연결 URL은 origin이다 (사용자 지정). 진입 화면 /home 은 health path로 붙인다.
    assert PILOT_SANDBOX_BASE_URL == "https://cymbal-bank.fsi.cymbal.dev"
    assert (
        build_health_url(PILOT_SANDBOX_BASE_URL, CYMBAL_BANK_HOME_PATH)
        == "https://cymbal-bank.fsi.cymbal.dev/home"
    )
    assert (
        build_health_url(PILOT_SANDBOX_BASE_URL, "/login")
        == "https://cymbal-bank.fsi.cymbal.dev/login"
    )


def test_run_falls_back_to_pilot_sandbox_when_no_environment() -> None:
    svc = EnvironmentService(get_platform_store())
    url, env = svc.resolve_base_url(
        environment_id=None, project_id=None, explicit_base_url=None
    )
    assert env is None
    assert url.rstrip("/") == PILOT_SANDBOX_BASE_URL.rstrip("/")


def test_explicit_local_url_still_wins_when_no_environment() -> None:
    """기본값은 파일럿 샌드박스지만, 호출자가 명시한 로컬 대상은 그대로 존중한다."""
    svc = EnvironmentService(get_platform_store())
    url, env = svc.resolve_base_url(
        environment_id=None,
        project_id=None,
        explicit_base_url="http://127.0.0.1:5173",
    )
    assert env is None
    assert url.rstrip("/") == "http://127.0.0.1:5173"


def test_environment_presets_include_cymbal() -> None:
    res = client.get("/api/environment-presets")
    assert res.status_code == 200
    keys = {p["key"] for p in res.json()}
    assert "cymbal-bank" in keys
    cymbal = next(p for p in res.json() if p["key"] == "cymbal-bank")
    # 연결 URL은 사용자가 지정한 origin 그대로다. 진입 화면(/home)은 health path로 둔다.
    assert cymbal["frontendBaseUrl"].rstrip("/") == CYMBAL_BANK_ORIGIN.rstrip("/")
    assert cymbal["healthCheckPath"] == CYMBAL_BANK_HOME_PATH
    # 실행에 반드시 필요한 연결 정보 (브라우저·계정)까지 프리셋이 채워준다
    assert cymbal["browser"] == "chrome"
    assert cymbal["loginId"] == PILOT_SANDBOX_LOGIN_ID
    assert cymbal["loginPassword"]


def test_create_environment_and_health_check() -> None:
    project = client.post("/api/projects", json={"name": "Env Pilot"}).json()
    project_id = project["id"]

    create = client.post(
        f"/api/projects/{project_id}/environments",
        json={
            "name": "Cymbal Bank (FSI)",
            "frontendBaseUrl": CYMBAL_BANK_FRONTEND_URL,
            "healthCheckPath": "/",
            "verifyTls": True,
        },
    )
    assert create.status_code == 201, create.text
    env = create.json()
    assert env["id"].startswith("ENV-")
    assert env["hostAllowlisted"] is True
    assert env["https"] is True

    listed = client.get(f"/api/projects/{project_id}/environments")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fake_fe = {
        "url": CYMBAL_BANK_FRONTEND_URL,
        "reachable": True,
        "statusCode": 200,
        "latencyMs": 12,
        "healthy": True,
        "error": None,
    }
    with patch("app.services.environment_service._probe_url", return_value=fake_fe):
        health = client.post(f"/api/environments/{env['id']}/health-check")
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["status"] == HealthStatus.up.value
    assert body["hostAllowlisted"] is True

    got = client.get(f"/api/environments/{env['id']}").json()
    assert got["lastHealthStatus"] == "up"


def test_reject_invalid_url() -> None:
    project = client.post("/api/projects", json={"name": "Bad URL"}).json()
    res = client.post(
        f"/api/projects/{project['id']}/environments",
        json={"name": "X", "frontendBaseUrl": "ftp://example.com/"},
    )
    # scheme must be http/https → 422
    assert res.status_code == 422


def test_run_resolves_environment_base_url() -> None:
    store = get_platform_store()
    project = client.post("/api/projects", json={"name": "Run Env"}).json()
    env_res = client.post(
        f"/api/projects/{project['id']}/environments",
        json={
            "name": "Cymbal",
            "frontendBaseUrl": CYMBAL_BANK_FRONTEND_URL,
        },
    )
    assert env_res.status_code == 201
    env = env_res.json()

    scenario = ScenarioSummary(
        scenarioId="SCN-env-test",
        projectId=project["id"],
        serviceId="svc-login",
        name="login",
        result={"steps": []},
    )
    store.save_scenario(scenario)

    svc = BrowserRunService(store)

    def _fake_execute(*_a, **_k):
        class R:
            status = "complete"
            stepResults = [
                {
                    "output": {
                        "result": {
                            "status": "WAITING_FOR_REVIEW",
                            "steps": [],
                            "screenshotCount": 0,
                            "snapshotCount": 0,
                            "missingData": [],
                            "observationSummary": "stub",
                        }
                    }
                }
            ]

        return R()

    with patch("app.services.run_service.PlatformRunnerAdapter") as adapter_cls:
        adapter_cls.return_value.execute.side_effect = _fake_execute
        run = svc.start_run(
            "SCN-env-test",
            RunCreateRequest(environmentId=env["id"], baseUrl="http://127.0.0.1:5173"),
        )

    assert run.baseUrl.rstrip("/") == CYMBAL_BANK_FRONTEND_URL.rstrip("/")
    assert run.environmentId == env["id"]
    assert run.environmentName == "Cymbal"


def test_resolve_prefers_project_default_environment() -> None:
    store = get_platform_store()
    project = client.post("/api/projects", json={"name": "Default Env"}).json()
    client.post(
        f"/api/projects/{project['id']}/environments",
        json={
            "name": "Cymbal",
            "frontendBaseUrl": CYMBAL_BANK_FRONTEND_URL,
        },
    )
    svc = EnvironmentService(store)
    url, env = svc.resolve_base_url(
        environment_id=None,
        project_id=project["id"],
        explicit_base_url="http://127.0.0.1:5173",
    )
    assert env is not None
    assert url.rstrip("/") == CYMBAL_BANK_FRONTEND_URL.rstrip("/")
