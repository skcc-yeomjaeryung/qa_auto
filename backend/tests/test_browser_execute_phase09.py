from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import REPO_ROOT, SKILL_HUB
from app.main import app
from app.skills.browser_execute.script import execute_run as browser_execute
from app.skills.browser_execute.script.execute_run import execute_scenario, route_url
from app.skills.scenario_dsl.script.generate_dsl import generate_scenarios
from app.skills.api_map.script.map_apis import build_mappings
from app.skills.interaction_graph.script.compose_graph import compose_graph

FIXTURE_FE = REPO_ROOT / "artifacts" / "analysis" / "AN-FE-5305d8bde832" / "frontend.json"
FIXTURE_BE = REPO_ROOT / "artifacts" / "analysis" / "AN-BE-5115c351b091" / "backend.json"
SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "run.schema.json"
HAS_CLI = shutil.which("agent-browser") is not None


@pytest.fixture(autouse=True)
def fresh_store():
    bootstrap_runtime()
    store = get_platform_store()
    for attr in (
        "_projects",
        "_sets",
        "_files",
        "_commit_cache",
        "_tokens",
        "_analyses",
        "_mapping_sets",
        "_graphs",
        "_scenarios",
        "_contracts",
        "_recommendations",
        "_profiles",
        "_runs",
    ):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    yield


client = TestClient(app)


def _scenario() -> dict:
    fe = json.loads(FIXTURE_FE.read_text(encoding="utf-8"))
    be = json.loads(FIXTURE_BE.read_text(encoding="utf-8"))
    mapping = build_mappings(fe, be, project_id="PRJ-br")
    graph = compose_graph(fe, be, mapping, project_id="PRJ-br", graph_id="IG-br")
    return generate_scenarios(graph, service_id="customer-search", project_id="PRJ-br")[0]


def test_route_url_uses_origin_for_absolute_routes() -> None:
    """진입 경로(`/home`)가 붙은 baseUrl에서도 절대 route는 origin 기준으로 연다."""
    base = "https://cymbal-bank.fsi.cymbal.dev/home"
    assert route_url(base, "/login") == "https://cymbal-bank.fsi.cymbal.dev/login"
    assert route_url(base, "customers/search") == "https://cymbal-bank.fsi.cymbal.dev/customers/search"
    assert route_url("http://127.0.0.1:5173/", "/customers/search") == "http://127.0.0.1:5173/customers/search"


def test_numeric_delta_requires_the_actual_cent_change() -> None:
    assert browser_execute._numeric_delta_matches(Decimal("1.00"), Decimal("0.99"), Decimal("-0.01"))
    assert not browser_execute._numeric_delta_matches(Decimal("0.00"), Decimal("0.00"), Decimal("-0.01"))


def test_submission_precondition_reports_native_form_constraints(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_execute,
        "_run_cli",
        lambda *_args, **_kwargs: {
            "ok": True,
            "stdout": '{"valid":false,"invalid":[{"name":"amount","value":"0.01","min":"0.01","max":"0.00","message":"Please enter a valid amount."}]}',
        },
    )

    state = browser_execute._submission_precondition(session="pytest", selector="#submit")

    assert state and state["valid"] is False
    observation = browser_execute._submission_precondition_observation(state)
    assert "최소 0.01" in observation
    assert "최대 0.00" in observation
    assert "요청은 전송되지 않았습니다" in observation


def test_browser_skill_textbook() -> None:
    skill_md = (SKILL_HUB / "browser_execute" / "SKILL.md").read_text(encoding="utf-8")
    assert "QA.CODE.BROWSER_EXECUTE" in skill_md
    assert "## 14. Changelog" in skill_md
    wf = (
        REPO_ROOT / "backend" / "app" / "workflow_definitions" / "wf_browser_execute.yml"
    ).read_text(encoding="utf-8")
    assert "QA.CODE.BROWSER_EXECUTE" in wf


def test_hub_loaded() -> None:
    health = client.get("/health").json()
    assert health["hubCounts"]["skills"] >= 9
    assert health["hubCounts"]["workflows"] >= 9


def test_consent_always_granted_by_platform() -> None:
    """Console policy: consent=False from client is overridden; run is not blocked."""
    from app.services.repository_models import utc_now
    from app.services.scenario_models import ScenarioSummary

    scn = _scenario()
    store = get_platform_store()
    store.save_scenario(
        ScenarioSummary(
            scenarioId=scn["scenarioId"],
            serviceId="customer-search",
            projectId="PRJ-br",
            name=scn["name"],
            status=scn["status"],
            createdAt=utc_now().isoformat(),
            result=scn,
        )
    )
    res = client.post(
        f"/api/scenarios/{scn['scenarioId']}/runs",
        json={"consent": False, "inputs": {"customerId": "CUS-1001"}},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # Platform forces consent=True — must not cancel for missing user consent.
    assert body["status"] != "CANCELLED" or "user_consent" not in (body.get("missingData") or [])
    assert body.get("consent") is True or "user_consent" not in (body.get("missingData") or [])


def test_schema_run() -> None:
    sample = {
        "runId": "RUN-x",
        "scenarioId": "SCN-x",
        "status": "WAITING_FOR_REVIEW",
        "consent": True,
        "steps": [
            {
                "stepId": "S1",
                "action": "navigate",
                "status": "ok",
            }
        ],
    }
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(sample)


def test_execute_scenario_closes_session_after_success(monkeypatch, tmp_path: Path) -> None:
    close_calls: list[tuple[list[str], str, int]] = []
    monkeypatch.setattr(
        browser_execute,
        "_execute_scenario_impl",
        lambda **_kwargs: {"ok": True, "status": "WAITING_FOR_REVIEW"},
    )
    monkeypatch.setattr(
        browser_execute,
        "_run_cli",
        lambda args, *, session, timeout=60: (
            close_calls.append((args, session, timeout))
            or {"ok": True, "exitCode": 0, "stderr": ""}
        ),
    )

    result = browser_execute.execute_scenario(
        scenario={"scenarioId": "SCN-finally"},
        inputs={},
        base_url="https://target.test",
        run_id="RUN-finally-success",
        consent=True,
        evidence_dir=tmp_path,
        session="pytest-finally-success",
    )

    assert result["status"] == "WAITING_FOR_REVIEW"
    assert close_calls == [(["close"], "pytest-finally-success", 30)]


def test_execute_scenario_closes_session_after_exception(monkeypatch, tmp_path: Path) -> None:
    close_calls: list[tuple[list[str], str, int]] = []

    def fail(**_kwargs):
        raise RuntimeError("browser step failed")

    monkeypatch.setattr(browser_execute, "_execute_scenario_impl", fail)
    monkeypatch.setattr(
        browser_execute,
        "_run_cli",
        lambda args, *, session, timeout=60: (
            close_calls.append((args, session, timeout))
            or {"ok": True, "exitCode": 0, "stderr": ""}
        ),
    )

    with pytest.raises(RuntimeError, match="browser step failed"):
        browser_execute.execute_scenario(
            scenario={"scenarioId": "SCN-finally"},
            inputs={},
            base_url="https://target.test",
            run_id="RUN-finally-error",
            consent=True,
            evidence_dir=tmp_path,
            session="pytest-finally-error",
        )

    assert close_calls == [(["close"], "pytest-finally-error", 30)]


def test_cleanup_failure_does_not_replace_run_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        browser_execute,
        "_execute_scenario_impl",
        lambda **_kwargs: {"ok": True, "status": "WAITING_FOR_REVIEW"},
    )

    def close_raises(*_args, **_kwargs):
        raise OSError("cleanup transport unavailable")

    monkeypatch.setattr(browser_execute, "_run_cli", close_raises)

    result = browser_execute.execute_scenario(
        scenario={"scenarioId": "SCN-finally"},
        inputs={},
        base_url="https://target.test",
        run_id="RUN-finally-cleanup-error",
        consent=True,
        evidence_dir=tmp_path,
        session="pytest-finally-cleanup-error",
    )

    assert result["status"] == "WAITING_FOR_REVIEW"


def test_no_consent_does_not_close_unacquired_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        browser_execute,
        "_run_cli",
        lambda *_args, **_kwargs: pytest.fail("close must not run without browser consent"),
    )

    result = browser_execute.execute_scenario(
        scenario={"scenarioId": "SCN-finally"},
        inputs={},
        base_url="https://target.test",
        run_id="RUN-finally-no-consent",
        consent=False,
        evidence_dir=tmp_path,
        session="caller-owned-session",
    )

    assert result["status"] == "CANCELLED"
    assert result["missing_data"] == ["user_consent"]


@pytest.mark.skipif(not HAS_CLI, reason="agent-browser CLI missing")
def test_execute_happy_path_live(tmp_path: Path) -> None:
    import urllib.request

    try:
        urllib.request.urlopen("http://127.0.0.1:5173/customers/search", timeout=2)
    except Exception:
        pytest.skip("sample FE not running on :5173")

    scn = _scenario()
    result = execute_scenario(
        scenario=scn,
        inputs={"customerId": "CUS-1001"},
        base_url="http://127.0.0.1:5173",
        run_id="RUN-test-live",
        consent=True,
        evidence_dir=tmp_path / "ev",
        headed=False,
        session="pytest-phase09",
    )
    assert result["status"] in {"WAITING_FOR_REVIEW", "AUTO_FAILED"}
    assert len(result.get("screenshots") or []) >= 1
    assert any(s["action"] == "fill" for s in result["steps"])
    # never claim HITL pass
    assert result.get("autoPassForbidden") is True
    assert "HITL" in (result.get("observationSummary") or "")


def test_cancel_endpoint() -> None:
    from app.services.repository_models import utc_now
    from app.services.run_models import RunSummary

    store = get_platform_store()
    store.save_run(
        RunSummary(
            runId="RUN-cancel",
            scenarioId="SCN-c",
            status="RUNNING",
            createdAt=utc_now().isoformat(),
            evidenceDir=str(REPO_ROOT / "artifacts" / "evidence" / "runs" / "RUN-cancel"),
        )
    )
    res = client.post("/api/runs/RUN-cancel/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "CANCELLED"
