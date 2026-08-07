"""D-015 실행경로 회귀 고정 — 선행 로그인 단계와 기대 결과 판정.

지침(프롬프트·SKILL)이 아니라 **실제 실행 산출물**이 규칙을 지키는지 본다.

1. 인증 뒤 화면·로그아웃 시나리오에 선행 로그인 단계가 붙는다
2. GET 직접 진입이 막힌 경로는 URL 이동이 아니라 화면 트리거 클릭으로 바뀐다
3. 세션 확인이 실패하면 도달했더라도 성공으로 판정되지 않는다

계약: docs/03.계약과예시/08.세션선행조건과판정계약.md
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from app.core.paths import SKILL_HUB
from app.services.run_models import RunSummary
from app.services.run_service import _normalize_derived_outcome

AUTH_CONTEXT: dict[str, Any] = {
    "loginRoute": "/login",
    "loginControls": {
        "idSelector": "#login-username",
        "passwordSelector": "#login-password",
        "submitSelector": "button[type='submit']",
    },
    "authGuardedRoutes": ["/home", "/logout"],
    "postOnlyRoutes": ["/logout"],
    "actionTriggers": [
        {
            "route": "/logout",
            "method": "POST",
            "triggerSelector": "#logout-form a",
            "triggerLabel": "Sign out",
            "openerSelector": "#accountDropdown",
        }
    ],
    "sessionMarkers": ["#accountDropdown", "#account-user-name"],
}


def _load(skill: str, module: str):
    path = SKILL_HUB / skill / "script" / f"{module}.py"
    spec = importlib.util.spec_from_file_location(f"{skill}_{module}", path)
    assert spec and spec.loader, f"스킬 스크립트를 열 수 없습니다: {path}"
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _logout_scenario() -> dict[str, Any]:
    return {
        "caseId": "LOGOUT-E2E-001",
        "source": {"route": "/logout"},
        "request": {"method": "POST", "path": "/logout"},
        "steps": [
            {"id": "S1", "action": "navigate", "target": {"route": "/logout"}},
            {"id": "S2", "action": "wait_for_response", "request": {"method": "POST", "path": "/logout"}},
        ],
    }


def test_logout_scenario_gets_login_precondition_and_trigger_click() -> None:
    mod = _load("scenario_dsl", "session_precondition")
    scn = mod.apply_session_precondition(_logout_scenario(), auth_context=AUTH_CONTEXT)

    assert scn["authRequired"] is True
    assert scn["sessionPolicy"] == "login_then_reuse"
    assert scn["preconditionStepIds"][:1] == ["S0-login"]

    actions = [(s["id"], s["action"]) for s in scn["steps"]]
    ids = [i for i, _ in actions]
    # 로그인 → 세션 확인 → 메뉴 열기 → 로그아웃 클릭 순서를 지킨다
    assert ids.index("S0-login") < ids.index("S0-login-verify") < ids.index("S1")
    assert ("S1-open", "click") in actions and ("S1", "click") in actions

    # /logout 직접 URL 이동은 남지 않는다 (서버가 GET 을 허용하지 않는 경로)
    assert not any(
        s["action"] == "navigate" and (s.get("target") or {}).get("route") == "/logout"
        for s in scn["steps"]
    )
    assert any(s["action"] == "assert_absent" for s in scn["steps"])

    checks = {c["check"] for c in scn["verdictCriteria"]}
    assert {"session_established", "logout_effect", "request_accepted"} <= checks


def test_login_credentials_are_referenced_not_synthesized() -> None:
    mod = _load("scenario_dsl", "session_precondition")
    scn = mod.apply_session_precondition(_logout_scenario(), auth_context=AUTH_CONTEXT)
    fills = [s for s in scn["steps"] if s["action"] == "fill"]
    assert [s["valueRef"] for s in fills] == ["environment.loginId", "environment.loginSecret"]
    assert all("value" not in s for s in fills), "계정 값을 시나리오에 심지 않는다"


def test_missing_login_evidence_is_marked_not_guessed() -> None:
    mod = _load("scenario_dsl", "session_precondition")
    scn = mod.apply_session_precondition(_logout_scenario(), auth_context={})
    assert scn["authRequired"] is True
    assert scn["preconditionStepIds"] == []
    assert scn["sessionMissingData"], "근거가 없으면 missing_data 로 남긴다"


def test_session_failure_is_not_recorded_as_success() -> None:
    """도달했더라도 세션 확인이 막히면 기대 충족으로 판정하지 않는다."""
    mod = _load("browser_execute", "execute_run")
    scenario = {
        "authRequired": True,
        "sessionPolicy": "login_then_reuse",
        "verdictCriteria": [
            {"id": "C-session", "check": "session_established", "expected": "인증 전용 요소가 보인다"},
            {"id": "C-logout", "check": "logout_effect", "expected": "인증 전용 요소가 사라진다"},
        ],
    }
    verdict = mod.evaluate_verdict(
        scenario=scenario,
        steps=[{"stepId": "S0-login-verify", "action": "assert_visible", "status": "failed"}],
        session_established=False,
        session_ended=False,
        blocked_by_precondition=True,
        denied_signals=[{"kind": "method_not_allowed", "detail": "Allowlist methods"}],
        binding_values={},
        missing=["session:S0-login-verify"],
    )
    assert verdict["verdict"] == "expected_not_met"
    assert verdict["blockingIssues"]
    assert verdict["reason"]


def test_all_criteria_met_reports_expected_met() -> None:
    mod = _load("browser_execute", "execute_run")
    scenario = {
        "authRequired": True,
        "verdictCriteria": [
            {"id": "C-session", "check": "session_established", "expected": "인증 전용 요소가 보인다"},
            {"id": "C-logout", "check": "logout_effect", "expected": "인증 전용 요소가 사라진다"},
        ],
    }
    verdict = mod.evaluate_verdict(
        scenario=scenario,
        steps=[
            {"stepId": "S0-login-verify", "action": "assert_visible", "status": "ok"},
            {"stepId": "S9-logout-effect", "action": "assert_absent", "status": "ok"},
        ],
        session_established=True,
        session_ended=True,
        blocked_by_precondition=False,
        denied_signals=[],
        binding_values={},
        missing=[],
    )
    assert verdict["verdict"] == "expected_met"
    assert not verdict["blockingIssues"]


def test_flask_not_found_snapshot_is_a_blocking_signal() -> None:
    mod = _load("browser_execute", "execute_run")
    snapshot = '''
- heading "Not Found" [level=1]
- paragraph: The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.
'''
    denial = mod.detect_denial(snapshot)
    assert denial is not None
    assert denial["kind"] == "not_found"


def test_existing_authenticated_session_is_observed_without_replaying_login_selectors() -> None:
    mod = _load("browser_execute", "execute_run")
    assert mod.authenticated_session_observed('- button "Test User" [expanded=false, ref=e2]') is True


def test_login_form_is_not_mistaken_for_an_existing_session() -> None:
    mod = _load("browser_execute", "execute_run")
    snapshot = '''
- textbox "Username" [ref=e1]
- textbox "Password" [ref=e2]
- button "Login" [ref=e3]
'''
    assert mod.authenticated_session_observed(snapshot) is False


def test_boundary_case_input_precedes_unrelated_synthetic_fallback() -> None:
    mod = _load("browser_execute", "execute_run")
    step = {"valueFrom": "inputs.amount", "caseInput": "0"}
    assert mod._resolve_input_value(step, {"customerId": "CUS-1001"}) == "0"
    assert mod._resolve_input_value(step, {"amount": "0.01"}) == "0.01"


def test_request_accepted_requires_actual_agent_browser_network_observation() -> None:
    mod = _load("browser_execute", "execute_run")
    scenario = {
        "verdictCriteria": [
            {"id": "C-response", "check": "request_accepted", "expected": "POST /deposit 응답"}
        ]
    }
    without_network = mod.evaluate_verdict(
        scenario=scenario,
        steps=[{"stepId": "S2", "action": "wait_for_response", "status": "ok"}],
        session_established=None,
        session_ended=None,
        blocked_by_precondition=False,
        denied_signals=[],
        binding_values={},
        missing=[],
    )
    assert without_network["verdict"] == "undetermined"
    with_network = mod.evaluate_verdict(
        scenario=scenario,
        steps=[{"stepId": "S2", "action": "wait_for_response", "status": "ok"}],
        session_established=None,
        session_ended=None,
        blocked_by_precondition=False,
        denied_signals=[],
        binding_values={
            "matchedNetworkRequests": [
                {"method": "POST", "path": "/deposit", "status": 302, "networkId": "NET-001"}
            ]
        },
        missing=[],
    )
    assert with_network["verdict"] == "expected_met"


def test_network_evidence_is_same_origin_masked_and_expected(monkeypatch) -> None:
    mod = _load("browser_execute", "execute_run")
    raw = {
        "success": True,
        "data": {
            "requests": [
                {
                    "requestId": "1",
                    "method": "POST",
                    "url": "https://target.test/deposit?token=secret&source=ui",
                    "resourceType": "Document",
                    "status": 302,
                    "mimeType": "text/html",
                    "headers": {"Cookie": "session=secret", "Content-Type": "application/x-www-form-urlencoded"},
                    "responseHeaders": {"Set-Cookie": "session=secret", "Content-Type": "text/html"},
                },
                {
                    "requestId": "2",
                    "method": "GET",
                    "url": "https://third-party.test/tracker",
                    "resourceType": "Fetch",
                    "status": 200,
                },
            ]
        },
    }
    monkeypatch.setattr(
        mod,
        "_run_cli",
        lambda *args, **kwargs: {"ok": True, "stdout": __import__("json").dumps(raw), "stderr": ""},
    )
    rows, matched = mod.collect_network_evidence(
        session="run-test",
        base_url="https://target.test/home",
        expected=[{"method": "POST", "path": "/deposit"}],
    )
    assert len(rows) == len(matched) == 1
    assert rows[0]["url"] == "https://target.test/deposit?token=%2A%2A%2A&source=ui"
    assert "Cookie" not in rows[0]["requestHeaders"]
    assert "Set-Cookie" not in rows[0]["responseHeaders"]
    assert rows[0]["expectedRequest"] is True


def test_network_redirect_chain_keeps_original_post_and_observed_final_status(monkeypatch) -> None:
    mod = _load("browser_execute", "execute_run")
    raw = {
        "success": True,
        "data": {
            "requests": [
                {
                    "requestId": "redirect-1",
                    "method": "POST",
                    "url": "https://target.test/login",
                    "resourceType": "Document",
                    "status": None,
                },
                {
                    "requestId": "redirect-1",
                    "method": "GET",
                    "url": "https://target.test/home",
                    "resourceType": "Document",
                    "status": 200,
                },
            ]
        },
    }
    monkeypatch.setattr(
        mod,
        "_run_cli",
        lambda *args, **kwargs: {
            "ok": True,
            "stdout": __import__("json").dumps(raw),
            "stderr": "",
        },
    )
    rows, matched = mod.collect_network_evidence(
        session="run-test",
        base_url="https://target.test/login",
        expected=[{"method": "POST", "path": "/login"}],
    )
    assert len(rows) == 2
    assert len(matched) == 1
    assert matched[0]["method"] == "POST"
    assert matched[0]["status"] is None
    assert matched[0]["effectiveStatus"] == 200
    assert matched[0]["statusBasis"] == "redirect_final_document"


def test_selected_account_label_is_read_from_observed_option_value() -> None:
    mod = _load("browser_execute", "execute_run")
    assert (
        mod._selected_label(
            '{"account_num":"9099791699","routing_num":"123","label":"External Bank"}'
        )
        == "External Bank"
    )


def test_legacy_expected_not_met_run_is_not_presented_as_success() -> None:
    stale = RunSummary(
        runId="RUN-stale-404",
        scenarioId="SCN-consent",
        status="WAITING_FOR_REVIEW",
        outcomeKind="success",
        outcomeSummary="정상 관측",
        result={
            "verdict": {
                "verdict": "expected_not_met",
                "reason": "요청한 화면을 서버에서 찾지 못했습니다",
                "blockedCause": "not_found",
            }
        },
    )
    normalized = _normalize_derived_outcome(stale)
    assert normalized.status == "AUTO_FAILED"
    assert normalized.outcomeKind == "be_error"


def test_legacy_server_error_url_overrides_incorrect_expected_met() -> None:
    stale = RunSummary(
        runId="RUN-stale-server-error",
        scenarioId="SCN-consent-e2e",
        status="WAITING_FOR_REVIEW",
        outcomeKind="success",
        outcomeSummary="정상 관측",
        result={
            "verdict": {"verdict": "expected_met", "reason": "요청 후 화면 관측"},
            "steps": [
                {
                    "stepId": "S2",
                    "action": "click",
                    "status": "ok",
                    "observationSummary": (
                        "clicked button[type='submit']; url-wait pending "
                        "(https://example.test/None#error=server_error)"
                    ),
                }
            ],
        },
    )
    normalized = _normalize_derived_outcome(stale)
    assert normalized.status == "AUTO_FAILED"
    assert normalized.outcomeKind == "be_error"
    assert "서버 오류" in normalized.outcomeSummary


def test_direct_visibility_evidence_repairs_legacy_generic_selector_false_failure() -> None:
    """1/1 직접 관측을 일반 selector 문자열 비교가 뒤집지 못하게 한다."""
    stale = RunSummary(
        runId="RUN-consent-visible",
        scenarioId="SCN-consent-ui",
        status="AUTO_FAILED",
        outcomeKind="business_error",
        outcomeSummary="미확인 컨트롤 button[type='submit']",
        result={
            "verdict": {
                "verdict": "expected_not_met",
                "reason": "미확인 컨트롤 button[type='submit']",
                "criteriaResults": [
                    {
                        "id": "C-controls",
                        "check": "controls_visible",
                        "result": "not_met",
                        "observed": "button[type='submit'] 문자열이 session marker 목록에 없음",
                    }
                ],
                "blockingIssues": [{"kind": "controls_visible"}],
            },
            "steps": [
                {
                    "stepId": "S2",
                    "action": "assert_visible",
                    "status": "ok",
                    "observationSummary": "표시 확인 1/1건",
                }
            ],
        },
    )
    normalized = _normalize_derived_outcome(stale)
    assert normalized.status == "WAITING_FOR_REVIEW"
    assert normalized.outcomeKind == "success"
    assert normalized.result["verdict"]["verdict"] == "expected_met"
    assert normalized.result["runDiagnosis"]["outcome"] == "success"
    assert "미확인 컨트롤" not in normalized.result["runNarrative"]
    assert normalized.result["runNarrativeMode"] == "evidence-reconciled"


def test_destructive_policy_block_is_explained_as_execution_policy_not_service_error() -> None:
    stale = RunSummary(
        runId="RUN-payment-policy-blocked",
        scenarioId="SCN-payment",
        status="AUTO_FAILED",
        outcomeKind="business_error",
        outcomeSummary="기대 문구 미확인: Payment successful",
        missingData=["submit_blocked_destructive"],
        result={
            "missing_data": ["submit_blocked_destructive"],
            "verdict": {
                "verdict": "expected_not_met",
                "reason": "기대 문구 미확인: Payment successful",
                "criteriaResults": [
                    {
                        "id": "C-success-message",
                        "result": "not_met",
                        "observed": "기대 문구 미확인: Payment successful",
                    }
                ],
            },
            "steps": [
                {
                    "stepId": "S8",
                    "action": "click",
                    "status": "skipped",
                    "observationSummary": "/payment 는 데이터를 생성할 수 있어 자동 클릭을 차단했습니다",
                    "missingData": ["submit_blocked_destructive"],
                }
            ],
            "runDiagnosis": {
                "outcome": "failure",
                "causeCategory": "unknown",
                "causeSummary": "기대 문구 미확인",
                "mode": "deterministic",
            },
        },
    )

    normalized = _normalize_derived_outcome(stale)
    diagnosis = normalized.result["runDiagnosis"]

    assert diagnosis["causeCategory"] == "destructive_policy_blocked"
    assert "제출이 실행되지 않아" in diagnosis["problemSummary"]
    assert "대상 서비스 오류가 아니라 실행 정책" in diagnosis["causeSummary"]
    assert diagnosis["actions"][0]["owner"] == "QA 실행 담당"
    assert "1회 테스트를 명시적으로 승인" in diagnosis["actions"][0]["action"]


def test_invalid_test_account_precondition_has_one_user_facing_root_cause() -> None:
    stale = RunSummary(
        runId="RUN-input-precondition",
        scenarioId="SCN-payment",
        status="AUTO_FAILED",
        outcomeKind="business_error",
        outcomeSummary="성공 안내를 확인하지 못했습니다",
        missingData=["input_precondition_invalid"],
        result={
            "missing_data": ["input_precondition_invalid"],
            "verdict": {
                "verdict": "expected_not_met",
                "blockingIssues": [
                    {
                        "kind": "input_precondition_invalid",
                        "detail": "현재 테스트 계정의 잔액·허용 범위가 입력을 수용하지 않습니다",
                    }
                ],
            },
            "steps": [
                {
                    "stepId": "S8",
                    "action": "click",
                    "status": "skipped",
                    "observationSummary": "amount=0.01 (최소 0.01 · 최대 0.00) — 요청은 전송되지 않았습니다",
                    "missingData": ["input_precondition_invalid"],
                }
            ],
        },
    )

    diagnosis = _normalize_derived_outcome(stale).result["runDiagnosis"]

    assert diagnosis["causeCategory"] == "input_precondition_invalid"
    assert diagnosis["actions"][0]["owner"] == "QA 테스트 데이터·실행환경 담당"
    assert "초기화·충전" in diagnosis["actions"][0]["action"]
    assert "하나의 선행조건 문제" in diagnosis["problemSummary"]


def test_skill_scripts_are_present() -> None:
    for skill, module in (
        ("scenario_dsl", "session_precondition"),
        ("browser_execute", "execute_run"),
    ):
        assert Path(SKILL_HUB / skill / "script" / f"{module}.py").is_file()
