"""Phase 13 — 건별 시나리오 테스트 UX.

추천값 실행 · 단일 override · unresolved 확인 · 실행 중 cancel · auto pass/fail ·
이전 입력 재사용 · stale version 차단 · Progress(Type 4) 재료를 검증한다.
브라우저 실행은 stub으로 대체하고, 관측 계약만 확인한다 (Pass/Fail 단정 없음).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import REPO_ROOT
from app.main import app
from app.services import run_service as run_service_module
from app.services.component_contract_models import ComponentContractSummary
from app.services.input_recommend_models import InputProfileSummary, RecommendationSummary
from app.services.repository_models import ProjectCreate
from app.services.scenario_models import ScenarioSummary

client = TestClient(app)
PREVIEW_SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "run_preview.schema.json"
RUN_SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "run.schema.json"

SCENARIO_ID = "SCN-p13"


@pytest.fixture(autouse=True)
def fresh_store():
    bootstrap_runtime()
    store = get_platform_store()
    for attr in (
        "_projects",
        "_sets",
        "_analyses",
        "_graphs",
        "_scenarios",
        "_contracts",
        "_recommendations",
        "_profiles",
        "_runs",
        "_backend_events",
        "_backend_seq",
        "_binding_results",
        "_evidence_manifests",
        "_environments",
    ):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    yield


class _StubAdapterResponse:
    status = "error"
    stepResults: list[dict] = []


class _StubAdapter:
    """LangGraph 경로를 건너뛰고 직접 skill tool fallback을 타게 한다."""

    def execute(self, *args, **kwargs) -> _StubAdapterResponse:
        return _StubAdapterResponse()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed(
    *,
    unresolved_field: bool = False,
    unsatisfiable_pattern: bool = False,
    scenario_version: str = "2",
) -> str:
    store = get_platform_store()
    project = store.create_project(ProjectCreate(name="Phase13", ownerUserId="TEST"))
    scenario = ScenarioSummary(
        scenarioId=SCENARIO_ID,
        projectId=project.id,
        serviceId="customer-search",
        name="고객 조회 A→B",
        version=scenario_version,
        status="EXECUTABLE",
        result={
            "scenarioId": SCENARIO_ID,
            "name": "고객 조회 A→B",
            "version": scenario_version,
            "status": "EXECUTABLE",
            "source": {"screen": "CustomerSearch", "route": "/customers/search"},
            "destination": {"screen": "CustomerDetail", "routePattern": "/customers/"},
            "sourceRefs": {"commitRefs": {"frontend": "abc1234567", "backend": "def7654321"}},
            "steps": [
                {"id": "S1", "action": "navigate", "target": {"route": "/customers/search"}},
                {
                    "id": "S2",
                    "action": "fill",
                    "target": {"strategy": "testId", "value": "customer-id-input"},
                    "valueFrom": "inputs.customerId",
                },
                {
                    "id": "S3",
                    "action": "click",
                    "target": {"strategy": "testId", "value": "customer-search-submit"},
                    "request": {"method": "GET", "path": "/api/customers/{customerId}"},
                },
                {
                    "id": "S4",
                    "action": "verify_navigation",
                    "expect": {"routePattern": "/customers/"},
                },
            ],
            "unresolved": [],
        },
    )
    store.save_scenario(scenario)

    contract_inputs = [
        {
            "field": "customerId",
            "required": True,
            "type": "string",
            "locator": {"strategy": "testId", "value": "customer-id-input"},
            "events": ["change"],
        }
    ]
    if unresolved_field:
        extra = {
            "field": "branchCode",
            "required": True,
            "type": "string",
            "locator": {"strategy": "testId", "value": "branch-code-input"},
            "events": ["change"],
            "reviewRequired": True,
        }
        if unsatisfiable_pattern:
            extra["pattern"] = r"^BR-[A-Z]{3}-\d{6}$"
        contract_inputs.append(extra)
    store.save_contract(
        ComponentContractSummary(
            contractId="CC-p13",
            scenarioId=SCENARIO_ID,
            projectId=project.id,
            result={
                "contractId": "CC-p13",
                "scenarioId": SCENARIO_ID,
                "screenA": {"name": "CustomerSearch", "route": "/customers/search"},
                "screenB": {"name": "CustomerDetail", "routePattern": "/customers/"},
                "inputs": contract_inputs,
                "actions": [],
            },
        )
    )
    store.save_recommendation(
        RecommendationSummary(
            recommendationId="REC-p13",
            scenarioId=SCENARIO_ID,
            projectId=project.id,
            contractId="CC-p13",
            defaultCount=1,
            recommendationCount=2,
            createdAt=_now(),
            result={
                "recommendationId": "REC-p13",
                "defaults": {"customerId": "CUS-1001"},
                "recommendations": [
                    {
                        "field": "customerId",
                        "value": "CUS-1001",
                        "displayValue": "CUS-1001",
                        "category": "happy_path",
                        "expectedPath": "detail_success",
                        "rationale": "Fixture 합성 고객",
                        "sources": [{"source": "fixture", "rank": 1}],
                        "selectedByDefault": True,
                        "reviewRequired": False,
                        "uncertain": False,
                        "masked": False,
                    },
                    {
                        "field": "customerId",
                        "value": "CUS-9999",
                        "displayValue": "CUS-9999",
                        "category": "not_found",
                        "expectedPath": "not_found",
                        "rationale": "미존재 고객",
                        "sources": [{"source": "schema", "rank": 4}],
                        "selectedByDefault": False,
                        "reviewRequired": False,
                        "uncertain": False,
                        "masked": False,
                    },
                ],
            },
        )
    )
    store.save_profile(
        InputProfileSummary(
            profileId="IP-p13",
            scenarioId=SCENARIO_ID,
            projectId=project.id,
            name="건별 프로필",
            version="3",
            status="APPROVED",
            caseCount=1,
            recommendationId="REC-p13",
            result={
                "profileId": "IP-p13",
                "version": "3",
                "cases": [{"caseId": "CASE-1", "inputs": {"customerId": "CUS-1001"}}],
            },
        )
    )
    return project.id


def _install_stub(monkeypatch, fake) -> None:
    monkeypatch.setattr(run_service_module, "PlatformRunnerAdapter", _StubAdapter)
    monkeypatch.setattr(run_service_module, "execute_scenario", fake)


def _fake_result(
    *,
    status: str,
    step_status: str = "ok",
    progress_path: Path | None = None,
    run_id: str = "",
) -> dict:
    steps = [
        {"stepId": "H0", "action": "set_headers", "status": "ok"},
        {"stepId": "S1", "action": "navigate", "status": "ok"},
        {
            "stepId": "S2",
            "action": "fill",
            "status": step_status,
            "observationSummary": "입력 필드를 찾지 못했습니다" if step_status == "error" else "입력 완료",
            "refOrLocator": "[data-testid=customer-id-input]",
        },
    ]
    if progress_path:
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
            json.dumps(
                {
                    "runId": run_id,
                    "status": status,
                    "plannedTotal": 5,
                    "completedCount": len(steps),
                    "steps": steps,
                }
            ),
            encoding="utf-8",
        )
    return {
        "ok": status != "AUTO_FAILED",
        "status": status,
        "runId": run_id,
        "steps": steps,
        "screenshots": ["a.png", "b.png"],
        "snapshots": ["a.txt"],
        "missing_data": [] if step_status == "ok" else ["locator:S2"],
        "observationSummary": "기술 실행 관측 완료. Pass/Fail·배포는 HITL에서 확정합니다.",
        "hitlRequired": True,
        "autoPassForbidden": True,
    }


def _passing_stub(**kwargs):
    return _fake_result(
        status="AUTO_PASSED",
        progress_path=kwargs.get("progress_path"),
        run_id=kwargs.get("run_id", ""),
    )


def _failing_stub(**kwargs):
    return _fake_result(
        status="AUTO_FAILED",
        step_status="error",
        progress_path=kwargs.get("progress_path"),
        run_id=kwargs.get("run_id", ""),
    )


def _await_terminal(run_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        res = client.get(f"/api/runs/{run_id}")
        assert res.status_code == 200
        body = res.json()
        if body["status"] in {"WAITING_FOR_REVIEW", "AUTO_FAILED", "CANCELLED"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"run did not settle: {body.get('status')}")


# --------------------------------------------------------------------- preview


def test_preview_summarizes_without_full_form() -> None:
    """기본 진입에 전체 폼 대신 요약·불확실 항목만 제공한다."""
    _seed()
    res = client.post(f"/api/scenarios/{SCENARIO_ID}/run-preview", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    Draft202012Validator(json.loads(PREVIEW_SCHEMA.read_text(encoding="utf-8"))).validate(body)

    assert body["aScreen"]["screen"] == "CustomerSearch"
    assert body["bScreen"]["routePattern"] == "/customers/"
    assert {"method": "GET", "path": "/api/customers/{customerId}"} in [
        {"method": a["method"], "path": a["path"]} for a in body["expectedApis"]
    ]
    assert body["scenarioVersion"] == "2"
    assert body["inputProfileVersion"] == "3"
    assert body["commitRefs"]["frontend"] == "abc1234567"

    field = next(f for f in body["fields"] if f["field"] == "customerId")
    assert field["value"] == "CUS-1001"
    assert field["confidence"] == "confirmed"
    assert field["category"] == "happy_path"
    # 대안 후보를 함께 제공해 category / expected branch 수정이 가능하다
    assert any(c["category"] == "not_found" for c in field["candidates"])
    # 조회성 GET만 있으므로 destructive 신호가 없다
    assert body["destructive"] is False
    # 실행 전 스텝 계획을 A입력 → 요청 → B관측 단계로 제공한다
    assert [s["stage"] for s in body["plannedSteps"]] == [
        "a_input",
        "a_input",
        "request",
        "b_ui",
    ]
    assert body["reviewFieldCount"] == 0


def test_preview_binds_synthesized_value_when_code_has_no_value() -> None:
    """코드에 값 근거가 없어도 필드 정의로 실행 가능한 값을 만들어 붙인다.

    테스트 자동화 도구는 「데이터가 없어 못 채웠다」로 끝내면 안 된다. 값은 rule이 만들고
    (재현 가능), 합성값임을 라벨로 남겨 사람이 수정·확정한다.
    """
    _seed(unresolved_field=True)
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/run-preview", json={}).json()
    branch = next(f for f in body["fields"] if f["field"] == "branchCode")
    assert branch["confidence"] == "inferred"
    assert branch["synthesized"] is True
    assert branch["value"]
    assert not any("branchCode" in item for item in body["missingData"])
    assert body["reviewFieldCount"] == 0
    assert body["inferredFieldCount"] == 1


def test_preview_keeps_field_unresolved_when_format_cannot_be_satisfied() -> None:
    """형식 제약을 만족하는 값을 만들 수 없으면 추정하지 않고 사람에게 넘긴다."""
    _seed(unresolved_field=True, unsatisfiable_pattern=True)
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/run-preview", json={}).json()
    branch = next(f for f in body["fields"] if f["field"] == "branchCode")
    assert branch["confidence"] == "unresolved"
    assert branch["value"] in (None, "")
    assert any("branchCode" in item for item in body["missingData"])
    assert body["reviewFieldCount"] == 1


def test_preview_scopes_inputs_to_what_the_scenario_fills() -> None:
    """화면 구성만 확인하는 시나리오에 저장소 전체 입력을 확인 숙제로 붙이지 않는다.

    Contract는 저장소 전체(모든 화면) 입력을 담고 있어, 입력 step이 없는 시나리오에
    그대로 붙이면 「index 화면 확인」에 회원가입 필드까지 채우라고 요구하게 된다.
    """
    _seed(unresolved_field=True)
    store = get_platform_store()
    scenario = store.get_scenario(SCENARIO_ID)
    body = dict(scenario.result)
    body["inputs"] = []
    # 생성기는 호출이 없을 때 「없음」 placeholder를 넣는다 — 실제 호출로 오인하면 안 된다.
    body["request"] = {"method": "없음", "path": "없음", "body": "없음"}
    body["steps"] = [
        {"id": "S1", "action": "navigate", "target": {"route": "/"}},
        {"id": "S2", "action": "assert_visible", "target": {"selectors": ["#a", "#b"]}},
    ]
    store.save_scenario(scenario.model_copy(update={"result": body}))

    preview = client.post(f"/api/scenarios/{SCENARIO_ID}/run-preview", json={}).json()
    assert preview["fields"] == []
    assert preview["reviewFieldCount"] == 0
    assert preview["missingData"] == []


def test_preview_prefers_scenario_declared_inputs() -> None:
    """시나리오 DSL이 입력을 선언하면 Contract 전체가 아니라 그 입력만 묻는다."""
    _seed(unresolved_field=True)
    store = get_platform_store()
    scenario = store.get_scenario(SCENARIO_ID)
    body = dict(scenario.result)
    body["inputs"] = [
        {
            "name": "customerId",
            "required": True,
            "locator": {"strategy": "testId", "value": "customer-id-input"},
        }
    ]
    store.save_scenario(scenario.model_copy(update={"result": body}))

    preview = client.post(f"/api/scenarios/{SCENARIO_ID}/run-preview", json={}).json()
    assert [f["field"] for f in preview["fields"]] == ["customerId"]


def test_preview_destructive_flag_for_mutating_call() -> None:
    _seed()
    store = get_platform_store()
    scenario = store.get_scenario(SCENARIO_ID)
    body = dict(scenario.result)
    body["steps"] = [
        {
            "id": "S3",
            "action": "click",
            "request": {"method": "DELETE", "path": "/api/customers/{customerId}"},
        }
    ]
    store.save_scenario(scenario.model_copy(update={"result": body}))
    preview = client.post(f"/api/scenarios/{SCENARIO_ID}/run-preview", json={}).json()
    assert preview["destructive"] is True
    assert any("DELETE" in reason for reason in preview["destructiveReasons"])


# ------------------------------------------------------------------ run launch


def test_run_with_recommended_values(monkeypatch) -> None:
    """추천값 그대로 실행 — override 없이 추천 default가 그대로 실행 입력이 된다."""
    _seed()
    _install_stub(monkeypatch, _passing_stub)
    res = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs",
        json={"mode": "interactive", "inputProfileId": "IP-p13"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    Draft202012Validator(json.loads(RUN_SCHEMA.read_text(encoding="utf-8"))).validate(body)
    assert body["mode"] == "interactive"
    assert body["inputs"]["customerId"] == "CUS-1001"
    assert body["overrides"] == {}
    assert body["scenarioVersion"] == "2"
    assert body["inputProfileVersion"] == "3"
    # 실행 전에도 스텝 목록이 있어 Progress Type 4를 즉시 그릴 수 있다
    assert body["plannedStepCount"] >= 5

    settled = _await_terminal(body["runId"])
    assert settled["status"] == "WAITING_FOR_REVIEW"


def test_single_value_override(monkeypatch) -> None:
    """1개 값만 수정해도 나머지는 추천값을 유지한다."""
    _seed()
    _install_stub(monkeypatch, _passing_stub)
    body = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs",
        json={
            "mode": "interactive",
            "inputProfileId": "IP-p13",
            "overrides": {"customerId": "CUS-9999"},
        },
    ).json()
    assert body["inputs"]["customerId"] == "CUS-9999"
    assert body["overrides"] == {"customerId": "CUS-9999"}
    _await_terminal(body["runId"])


def test_override_can_be_saved_as_new_profile_version() -> None:
    """수정값은 새 Input Profile 버전으로 저장할 수 있다 (승인 확정은 HITL)."""
    _seed()
    created = client.post(
        f"/api/scenarios/{SCENARIO_ID}/input-profiles",
        json={"name": "건별 수정본", "overrides": {"customerId": "CUS-9999"}},
    )
    assert created.status_code == 200, created.text
    profile = created.json()
    first_case = profile["result"]["cases"][0]
    assert first_case["inputs"]["customerId"] == "CUS-9999"
    assert first_case["category"] == "user_override"
    assert first_case["reviewRequired"] is True

    approved = client.post(f"/api/input-profiles/{profile['profileId']}/approve", json={})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"


# ------------------------------------------------------------ live progress · cancel


def test_live_step_progress_during_interactive_run(monkeypatch) -> None:
    """실행 중 step 진행과 진행률을 관측할 수 있다 (Progress Type 4 재료)."""
    _seed()
    release = {"go": False}

    def slow_stub(**kwargs):
        progress_path = kwargs.get("progress_path")
        run_id = kwargs.get("run_id", "")
        if progress_path:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(
                json.dumps(
                    {
                        "runId": run_id,
                        "status": "RUNNING",
                        "plannedTotal": 5,
                        "completedCount": 2,
                        "steps": [
                            {"stepId": "H0", "action": "set_headers", "status": "ok"},
                            {"stepId": "S1", "action": "navigate", "status": "ok"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
        deadline = time.time() + 5
        while not release["go"] and time.time() < deadline:
            time.sleep(0.02)
        return _fake_result(status="AUTO_PASSED", progress_path=progress_path, run_id=run_id)

    _install_stub(monkeypatch, slow_stub)
    run_id = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs", json={"mode": "interactive"}
    ).json()["runId"]

    observed = {}
    deadline = time.time() + 5
    while time.time() < deadline:
        observed = client.get(f"/api/runs/{run_id}").json()
        if observed["progressPercent"] > 0:
            break
        time.sleep(0.05)
    assert observed["status"] == "RUNNING"
    assert 0 < observed["progressPercent"] < 100
    assert [s["stepId"] for s in observed["steps"]][:2] == ["H0", "S1"]
    # 진행 중에는 다음 대기 스텝을 현재 스텝으로 노출한다
    assert observed["currentStepId"] == "S2"

    release["go"] = True
    settled = _await_terminal(run_id)
    assert settled["progressPercent"] == 100


def test_cancel_during_interactive_run(monkeypatch) -> None:
    """실행 중 취소 — 취소 요청 후 상태가 CANCELLED로 유지된다."""
    _seed()

    def cancellable_stub(**kwargs):
        evidence_dir = kwargs["evidence_dir"]
        flag = Path(evidence_dir) / "CANCEL"
        deadline = time.time() + 5
        while not flag.exists() and time.time() < deadline:
            time.sleep(0.02)
        return _fake_result(
            status="CANCELLED",
            progress_path=kwargs.get("progress_path"),
            run_id=kwargs.get("run_id", ""),
        )

    _install_stub(monkeypatch, cancellable_stub)
    run_id = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs", json={"mode": "interactive"}
    ).json()["runId"]

    cancelled = client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    settled = _await_terminal(run_id)
    assert settled["status"] == "CANCELLED"
    # 이미 종료된 실행은 다시 취소되지 않는다
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409


# ----------------------------------------------------------- auto pass · auto fail


def test_auto_pass_never_becomes_hitl_pass(monkeypatch) -> None:
    _seed()
    _install_stub(monkeypatch, _passing_stub)
    run_id = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs", json={"mode": "interactive"}
    ).json()["runId"]
    settled = _await_terminal(run_id)
    assert settled["status"] == "WAITING_FOR_REVIEW"
    assert settled["hitlRequired"] is True
    assert settled["failedStepId"] is None
    assert "HITL" in (settled["observationSummary"] or "")


def test_auto_fail_exposes_failed_step_first(monkeypatch) -> None:
    """실패 시 실패 Step·원인·locator를 먼저 확인할 수 있다."""
    _seed()
    _install_stub(monkeypatch, _failing_stub)
    run_id = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs", json={"mode": "interactive"}
    ).json()["runId"]
    settled = _await_terminal(run_id)
    assert settled["status"] == "AUTO_FAILED"
    assert settled["failedStepId"] == "S2"
    failed = next(s for s in settled["steps"] if s["stepId"] == "S2")
    assert failed["status"] == "error"
    assert "찾지 못했습니다" in (failed["observationSummary"] or "")
    assert settled["outcomeKind"] in {"fe_error", "be_error", "business_error"}


# ------------------------------------------------------------------- retest reuse


def test_previous_input_reuse_on_retest(monkeypatch) -> None:
    """재실행 시 이전 실행 입력을 선택적으로 재사용한다."""
    _seed()
    _install_stub(monkeypatch, _passing_stub)
    first = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs",
        json={"mode": "interactive", "overrides": {"customerId": "CUS-9999"}},
    ).json()
    _await_terminal(first["runId"])

    again = client.post(f"/api/runs/{first['runId']}/retest", json={})
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["runId"] != first["runId"]
    assert body["inputs"]["customerId"] == "CUS-9999"
    assert body["reusedFromRunId"] == first["runId"]
    _await_terminal(body["runId"])

    # preview 도 이전 실행을 재사용 후보로 제시한다
    preview = client.post(
        f"/api/scenarios/{SCENARIO_ID}/run-preview",
        json={"reuseFromRunId": first["runId"]},
    ).json()
    assert preview["previousRun"]["runId"] is not None
    assert (
        next(f for f in preview["fields"] if f["field"] == "customerId")["value"]
        == "CUS-9999"
    )


# ------------------------------------------------------------- stale version 방지


def test_stale_scenario_version_rejected(monkeypatch) -> None:
    _seed(scenario_version="2")
    _install_stub(monkeypatch, _passing_stub)
    res = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs",
        json={"mode": "interactive", "scenarioVersion": "1"},
    )
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["currentVersion"] == "2"
    assert detail["requestedVersion"] == "1"
    # stale 요청은 Run을 만들지 않는다
    assert client.get("/api/runs").json() == []


def test_stale_input_profile_version_rejected(monkeypatch) -> None:
    _seed()
    _install_stub(monkeypatch, _passing_stub)
    res = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs",
        json={
            "mode": "interactive",
            "inputProfileId": "IP-p13",
            "inputProfileVersion": "2",
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["currentVersion"] == "3"


def test_matching_versions_are_accepted(monkeypatch) -> None:
    _seed()
    _install_stub(monkeypatch, _passing_stub)
    res = client.post(
        f"/api/scenarios/{SCENARIO_ID}/runs",
        json={
            "mode": "interactive",
            "inputProfileId": "IP-p13",
            "scenarioVersion": "2",
            "inputProfileVersion": "3",
        },
    )
    assert res.status_code == 200
    _await_terminal(res.json()["runId"])


def test_batch_mode_stays_synchronous(monkeypatch) -> None:
    """기존 일괄 경로는 동기 응답을 유지한다 (호환)."""
    _seed()
    _install_stub(monkeypatch, _passing_stub)
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/runs", json={}).json()
    assert body["mode"] == "batch"
    assert body["status"] == "WAITING_FOR_REVIEW"
    assert body["progressPercent"] == 100
