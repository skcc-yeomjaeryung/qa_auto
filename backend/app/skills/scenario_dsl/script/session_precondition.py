#!/usr/bin/env python3
"""세션 선행조건 보강 — 로그인 뒤 화면은 로그인 단계를 시나리오에 포함한다 (D-015).

계약: `docs/03.계약과예시/08.세션선행조건과판정계약.md`
지침: `backend/app/prompts/scenario/session_precondition_system.md`

판정은 전부 **정적 분석 근거(graph.authContext)** 로만 한다.
근거가 없으면 만들지 않고 `missing_data`로 남긴다. 계정 값은 참조로만 가리킨다.
"""
from __future__ import annotations

from typing import Any

LOGOUT_TOKENS = ("logout", "signout", "sign-out", "logoff")

# 계약이 정한 인증 뒤 업무 — 잔액·송금·거래내역·내 정보는 로그인 세션 안에서만 성립한다
# (docs/03.계약과예시/08.세션선행조건과판정계약.md §2.2-1)
AUTH_SENSITIVE_TOKENS = (
    "balance",
    "transaction",
    "transfer",
    "payment",
    "deposit",
    "contact",
    "profile",
    "account",
)

# 데이터를 만드는 경로 — 트리거 클릭을 기본 차단한다 (destructive 기본 차단)
DESTRUCTIVE_ROUTE_TOKENS = (
    "deposit",
    "payment",
    "transfer",
    "withdraw",
    "delete",
    "signup",
)

LOGIN_ID_REF = "environment.loginId"
LOGIN_SECRET_REF = "environment.loginSecret"

SESSION_POLICIES = (
    "no_auth",
    "login_then_reuse",
    "reuse_existing_session",
    "fresh_login_required",
)


def _routes_of(scenario: dict[str, Any]) -> list[str]:
    routes: list[str] = []
    source_route = str((scenario.get("source") or {}).get("route") or "")
    if source_route and source_route != "missing_data":
        routes.append(source_route)
    request_path = str((scenario.get("request") or {}).get("path") or "")
    if request_path and request_path not in {"missing_data", "없음"}:
        routes.append(request_path)
    for step in scenario.get("steps") or []:
        route = str(((step.get("target") or {}).get("route")) or "")
        if route and route not in routes and route != "missing_data":
            routes.append(route)
        path = str(((step.get("request") or {}).get("path")) or "")
        if path and path not in routes:
            routes.append(path)
    return routes


def _is_logout(routes: list[str]) -> bool:
    return any(token in r.lower() for r in routes for token in LOGOUT_TOKENS)


def _login_steps(
    *, login_route: str, controls: dict[str, Any], markers: list[str]
) -> list[dict[str, Any]]:
    """실제 사용자 이벤트로 로그인한다 — 쿠키·DOM 주입은 하지 않는다."""
    steps: list[dict[str, Any]] = [
        {
            "id": "S0-login",
            "action": "navigate",
            "target": {"route": login_route},
            "timeoutMs": 15000,
            "precondition": True,
            "title": "로그인 화면을 엽니다",
            "reason": "대상 화면이 로그인 뒤에 있어 먼저 로그인합니다",
            "evidenceRefs": ["graph:authContext.loginRoute"],
        },
        {
            "id": "S0-login-id",
            "action": "fill",
            "target": {"strategy": "css", "value": controls["idSelector"]},
            "valueRef": LOGIN_ID_REF,
            "timeoutMs": 8000,
            "precondition": True,
            "title": "연결 정보의 계정 ID를 입력합니다",
            "evidenceRefs": ["graph:authContext.loginControls.idSelector"],
        },
        {
            "id": "S0-login-pw",
            "action": "fill",
            "target": {"strategy": "css", "value": controls["passwordSelector"]},
            "valueRef": LOGIN_SECRET_REF,
            "masked": True,
            "timeoutMs": 8000,
            "precondition": True,
            "title": "연결 정보의 계정 비밀번호를 입력합니다",
            "evidenceRefs": ["graph:authContext.loginControls.passwordSelector"],
        },
        {
            "id": "S0-login-submit",
            "action": "click",
            "target": {"strategy": "css", "value": controls["submitSelector"]},
            "timeoutMs": 15000,
            "precondition": True,
            "title": "로그인을 제출합니다",
            "evidenceRefs": ["graph:authContext.loginControls.submitSelector"],
        },
    ]
    if markers:
        steps.append(
            {
                "id": "S0-login-verify",
                "action": "assert_visible",
                "target": {"selectors": markers[:4]},
                "timeoutMs": 10000,
                "precondition": True,
                "blocking": True,
                "sessionCheck": True,
                "title": "로그인 세션이 생겼는지 화면에서 확인합니다",
                "reason": "세션 확인이 실패하면 본 단계를 진행하지 않습니다",
                "evidenceRefs": ["graph:authContext.sessionMarkers"],
            }
        )
    return steps


def apply_session_precondition(
    scenario: dict[str, Any], *, auth_context: dict[str, Any] | None
) -> dict[str, Any]:
    """시나리오 한 건에 세션 선행조건·판정 기준을 붙인다 (결정론)."""
    ctx = dict(auth_context or {})
    scn = dict(scenario)
    routes = _routes_of(scn)
    guarded_routes = {str(r) for r in (ctx.get("authGuardedRoutes") or [])}
    post_only_routes = {str(r) for r in (ctx.get("postOnlyRoutes") or [])}
    markers = [str(m) for m in (ctx.get("sessionMarkers") or []) if m]
    controls = dict(ctx.get("loginControls") or {})
    login_route = str(ctx.get("loginRoute") or "")
    triggers = list(ctx.get("actionTriggers") or [])

    matched_guarded = [r for r in routes if r in guarded_routes]
    logout_case = _is_logout(routes)
    # 잔액·송금·거래내역 등 계약이 인증 뒤로 정한 업무 (case ID·경로 토큰으로 판별)
    blob = f"{scn.get('caseId') or ''} {' '.join(routes)}".lower()
    sensitive = [token for token in AUTH_SENSITIVE_TOKENS if token in blob]
    # 로그아웃은 예외 없이 로그인 세션을 전제한다
    auth_required = bool(matched_guarded) or logout_case or bool(sensitive)

    unresolved = list(scn.get("unresolved") or [])
    missing: list[str] = []
    basis = [f"graph:authContext.authGuardedRoutes:{r}" for r in matched_guarded]
    if logout_case and not matched_guarded:
        basis.append("route:logout")
    if sensitive and not matched_guarded:
        basis.append(f"contract:authSensitive:{sensitive[0]}")

    login_ready = bool(login_route) and all(
        controls.get(key) for key in ("idSelector", "passwordSelector", "submitSelector")
    )
    steps = list(scn.get("steps") or [])
    pre: list[dict[str, Any]] = []
    if auth_required:
        if login_ready:
            pre = _login_steps(login_route=login_route, controls=controls, markers=markers)
            if not markers:
                missing.append("authContext.sessionMarkers")
        else:
            missing.append("authContext.loginControls" if login_route else "authContext.loginRoute")

    adjustments: list[dict[str, Any]] = []
    # GET 직접 진입이 허용되지 않는 경로는 인증 여부와 무관하게 화면 트리거로 수행한다
    validation_only = bool((scn.get("caseVariant") or {}).get("validationOnly"))
    # Native constraint cases intentionally stop before submit.  Their top-level request
    # describes the business contract but is not an instruction to invoke that POST.
    # Prepending a route trigger here would mutate data before the invalid input is checked.
    direct_entry_blocked = [] if validation_only else [r for r in routes if r in post_only_routes]
    if direct_entry_blocked:
        target_route = direct_entry_blocked[0]
        modeled_user_event = any(
            str(step.get("action") or "").lower() == "click"
            and str((step.get("request") or {}).get("path") or "").split("?", 1)[0] == target_route
            for step in steps
            if isinstance(step, dict)
        )
        if modeled_user_event:
            # The business-journey composer already placed opener → form inputs →
            # submit in user order.  Do not prepend a second submit before its inputs.
            direct_entry_blocked = []
    if direct_entry_blocked:
        target_route = direct_entry_blocked[0]
        trigger = next(
            (t for t in triggers if str(t.get("route") or "").split("?")[0] == target_route),
            None,
        )
        # 서버가 GET 직접 진입을 허용하지 않는 경로 — URL 이동으로는 동작이 성립하지 않는다
        steps = [
            s
            for s in steps
            if not (
                str(s.get("action") or "").lower() == "navigate"
                and str((s.get("target") or {}).get("route") or "") == target_route
            )
        ]
        if trigger and trigger.get("triggerSelector"):
            main_steps: list[dict[str, Any]] = []
            if trigger.get("openerSelector"):
                # 접힌 메뉴 안의 트리거 — 메뉴를 먼저 열어야 실제 사용자 이벤트가 성립한다
                main_steps.append(
                    {
                        "id": "S1-open",
                        "action": "click",
                        "target": {"strategy": "css", "value": trigger["openerSelector"]},
                        "timeoutMs": 10000,
                        "title": "동작이 들어있는 메뉴를 엽니다",
                        "preserveTitle": True,
                        "evidenceRefs": ["graph:authContext.actionTriggers.openerSelector"],
                    }
                )
            main_steps.append(
                {
                    "id": "S1",
                    "action": "click",
                    "target": {"strategy": "css", "value": trigger["triggerSelector"]},
                    "timeoutMs": 15000,
                    "title": f"화면의 「{trigger.get('triggerLabel') or '동작'}」을 클릭합니다",
                    "preserveTitle": True,
                    "reason": (
                        f"{target_route} 는 직접 URL 진입이 허용되지 않아 화면의 실제 트리거를 누릅니다"
                    ),
                    "request": {"method": trigger.get("method") or "POST", "path": target_route},
                    "destructive": any(
                        token in target_route.lower() for token in DESTRUCTIVE_ROUTE_TOKENS
                    ),
                    "evidenceRefs": ["graph:authContext.actionTriggers"],
                }
            )
            steps = [*main_steps, *steps]
            adjustments.append(
                {
                    "route": target_route,
                    "change": "route_to_user_event",
                    "detail": f"{target_route} 직접 진입 대신 {trigger['triggerSelector']} 클릭",
                }
            )
        else:
            missing.append(f"authContext.actionTriggers:{target_route}")
            adjustments.append(
                {
                    "route": target_route,
                    "change": "direct_entry_removed",
                    "detail": "직접 진입은 서버가 거부하고, 화면 트리거 근거가 없습니다",
                }
            )

    if logout_case and markers:
        steps.append(
            {
                "id": "S9-logout-effect",
                "action": "assert_absent",
                "target": {"selectors": markers[:4]},
                "timeoutMs": 10000,
                "sessionCheck": True,
                "expectSessionEnded": True,
                "title": "로그아웃 후 인증 전용 요소가 사라졌는지 확인합니다",
                "evidenceRefs": ["graph:authContext.sessionMarkers"],
            }
        )

    if logout_case and any(item.get("change") == "route_to_user_event" for item in adjustments):
        # The generic flow seed may have marked its original submit locator unresolved.
        # Once authContext supplies the actual opener + logout trigger, that item is no
        # longer unresolved and must not keep the executable scenario in a warning state.
        unresolved = [
            item
            for item in unresolved
            if not (
                str(item.get("kind") or "") == "missing_locator"
                and str(item.get("symbol") or "").lower() in {"submit", "trigger", "logout"}
            )
        ]

    scn["authRequired"] = auth_required
    scn["sessionPolicy"] = "login_then_reuse" if auth_required else "no_auth"
    scn["authBasis"] = basis
    scn["steps"] = [*pre, *steps]
    scn["preconditionStepIds"] = [s["id"] for s in pre]
    if adjustments:
        scn["mainStepAdjustments"] = adjustments
    scn["verdictCriteria"] = _verdict_criteria(
        scn,
        auth_required=auth_required,
        logout_case=logout_case,
        markers=markers,
        controls=controls,
    )
    for item in missing:
        unresolved.append(
            {
                "kind": "missing_session_evidence",
                "symbol": item,
                "reason": "세션 선행조건 근거가 분석 산출물에 없습니다 (추정하지 않음)",
            }
        )
    scn["unresolved"] = unresolved
    if missing:
        scn["sessionMissingData"] = missing
    return scn


def _verdict_criteria(
    scenario: dict[str, Any],
    *,
    auth_required: bool,
    logout_case: bool,
    markers: list[str],
    controls: dict[str, Any],
) -> list[dict[str, Any]]:
    """무엇이 보이면 기대대로인가 — 화면에서 관측 가능한 문장으로만 쓴다."""
    criteria: list[dict[str, Any]] = [
        dict(item)
        for item in (scenario.get("verdictCriteria") or [])
        if isinstance(item, dict)
    ]
    if auth_required and markers and not any(item.get("id") == "C-session" for item in criteria):
        criteria.append(
            {
                "id": "C-session",
                "check": "session_established",
                "expected": "로그인 후 인증 사용자 전용 요소가 화면에 보인다",
                "selectors": markers[:4],
            }
        )
    if logout_case and not any(item.get("id") == "C-logout" for item in criteria):
        expect_selectors = [
            s
            for s in (controls.get("idSelector"), controls.get("passwordSelector"))
            if s
        ]
        criteria.append(
            {
                "id": "C-logout",
                "check": "logout_effect",
                "expected": "로그아웃 후 로그인 화면으로 돌아가고 인증 전용 요소가 사라진다",
                "selectors": expect_selectors,
                "absentSelectors": markers[:4],
            }
        )
    visible = [
        s
        for a in (scenario.get("assertions") or [])
        if str(a.get("type") or "") == "dom-visible"
        for s in (a.get("selectors") or [])
        if s
    ]
    if visible and not any(item.get("id") == "C-controls" for item in criteria):
        criteria.append(
            {
                "id": "C-controls",
                "check": "controls_visible",
                "expected": "분석이 확인한 화면 컨트롤이 모두 보인다",
                "selectors": visible[:8],
            }
        )
    request = scenario.get("request") or {}
    method = str(request.get("method") or "")
    path = str(request.get("path") or "")
    observes_response = any(
        str(step.get("action") or "") in {"wait_for_response", "verify_response"}
        for step in (scenario.get("steps") or [])
    )
    if (
        method
        and path
        and observes_response
        and method not in {"없음", "missing_data"}
        and path not in {"없음", "missing_data"}
        and not any(item.get("id") == "C-response" for item in criteria)
    ):
        criteria.append(
            {
                "id": "C-response",
                "check": "request_accepted",
                "expected": f"{method} {path} 요청이 거부되지 않고 응답이 관측된다",
                "request": {"method": method, "path": path},
            }
        )
    return criteria
