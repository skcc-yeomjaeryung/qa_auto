#!/usr/bin/env python3
"""scenario_dsl / generate_dsl — Graph → N Scenario DSLs (deterministic, no invented facts)."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

try:  # CLI(스크립트) 실행과 서비스 import 양쪽을 지원한다
    from .session_precondition import apply_session_precondition
except ImportError:  # pragma: no cover - CLI 직접 실행 경로
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from session_precondition import apply_session_precondition  # type: ignore[no-redef]


def _load(src: Any) -> dict[str, Any]:
    if isinstance(src, dict):
        return src
    return json.loads(Path(str(src)).expanduser().resolve().read_text(encoding="utf-8"))


def _node_map(graph: dict[str, Any]) -> dict[str, dict]:
    return {n["id"]: n for n in (graph.get("nodes") or [])}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return (cleaned or "flow")[:48]


def _is_probe(path: str) -> bool:
    p = (path or "").lower()
    return any(
        token in p
        for token in ("/health", "/healthy", "/ready", "/version", "/live", "/ping", "/actuator")
    )


def _attrs(node: dict[str, Any] | None) -> dict[str, Any]:
    return dict((node or {}).get("attributes") or {})


def _service_id_for(method: str, path: str, fallback: str | None = None) -> str:
    base = path.strip("/").replace("{", "").replace("}", "")
    parts = [p for p in base.split("/") if p and p not in {"api", "v1", "v2"}]
    name = parts[-1] if parts else (fallback or "api")
    return _slug(f"{method.lower()}-{name}")


def _token_from_route(route: str, name: str | None = None) -> str:
    r = (route or "").strip().lower()
    if r in ("", "/", "/index", "/index.html"):
        return "INDEX"
    blob = f"{r} {name or ''}".lower()
    for token in (
        "login",
        "deposit",
        "payment",
        "signup",
        "consent",
        "home",
        "balance",
        "transfer",
        "transaction",
        "account",
    ):
        if token in blob:
            return token.upper()
    slug = _slug(route.strip("/") or name or "screen").upper().replace("-", "_")
    return (slug.split("_")[0] if slug else "SCREEN")[:16]


# Human journey order for BoA-like apps: INDEX → HOME → LOGIN → SIGNUP → …
_JOURNEY_GROUP_RANK: dict[str, int] = {
    "INDEX": 10,
    "HOME": 20,
    "LOGIN": 30,
    "SIGNUP": 40,
    "DEPOSIT": 50,
    "PAYMENT": 60,
    "CONSENT": 70,
    "BALANCE": 80,
    "TRANSFER": 90,
    "TRANSACTION": 100,
    "ACCOUNT": 110,
}

_KIND_RANK: dict[str, int] = {"UI": 0, "E2E": 1, "API": 2}

_GROUP_LABEL_KO: dict[str, str] = {
    "INDEX": "인덱스",
    "HOME": "홈",
    "LOGIN": "로그인",
    "SIGNUP": "가입",
    "DEPOSIT": "입금",
    "PAYMENT": "송금",
    "CONSENT": "동의",
    "BALANCE": "잔액",
    "TRANSFER": "송금",
    "TRANSACTION": "거래",
    "ACCOUNT": "계좌",
}


def _parse_case_id(case_id: str) -> tuple[str, str, int]:
    """LOGIN-UI-001 → (LOGIN, UI, 1)."""
    parts = [p for p in str(case_id or "").split("-") if p]
    if len(parts) >= 3 and parts[-1].isdigit():
        seq = int(parts[-1])
        kind = parts[-2].upper()
        group = parts[0].upper()
        if kind in _KIND_RANK or kind in {"UI", "E2E", "API"}:
            return group, kind, seq
    if parts:
        return parts[0].upper(), "OTHER", 999
    return "OTHER", "OTHER", 999


def _journey_title(group: str, kind: str, fallback_name: str | None = None) -> str:
    label = _GROUP_LABEL_KO.get(group, group)
    if kind == "UI":
        return f"{label} 화면 구성"
    if kind == "E2E":
        return f"{label} 관통"
    if kind == "API":
        return f"{label} API"
    if fallback_name:
        return str(fallback_name)
    return f"{label} 시나리오"


def _infer_journey_group(scn: dict[str, Any]) -> tuple[str, str, int]:
    case_id = str(scn.get("caseId") or (scn.get("caseAnalysis") or {}).get("caseId") or "")
    group, kind, seq = _parse_case_id(case_id)
    if group and group != "OTHER":
        return group, kind, seq
    route = str((scn.get("source") or {}).get("route") or "")
    group = _token_from_route(route, str(scn.get("name") or ""))
    test_type = str(scn.get("testType") or (scn.get("caseAnalysis") or {}).get("testType") or "")
    if "UI" in test_type or (case_id and "-UI-" in case_id):
        kind = "UI"
    elif "E2E" in test_type or "관통" in test_type or (case_id and "-E2E-" in case_id):
        kind = "E2E"
    elif case_id and "-API-" in case_id:
        kind = "API"
    else:
        kind = "OTHER"
    return group, kind, seq


def apply_human_journey_order(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort scenarios into a human journey and stamp journeyGroup/Order/Title."""

    def sort_key(scn: dict[str, Any]) -> tuple[Any, ...]:
        group, kind, seq = _infer_journey_group(scn)
        rank = _JOURNEY_GROUP_RANK.get(group, 500)
        kind_rank = _KIND_RANK.get(kind, 3)
        case_id = str(scn.get("caseId") or "")
        return (rank, kind_rank, seq, case_id, str(scn.get("scenarioId") or ""))

    ordered = sorted(scenarios, key=sort_key)
    for i, scn in enumerate(ordered, start=1):
        group, kind, _seq = _infer_journey_group(scn)
        scn["journeyGroup"] = group
        scn["journeyOrder"] = i
        scn["journeyTitle"] = _journey_title(group, kind, scn.get("name"))
    return ordered


def _case_id(prefix: str, kind: str, seq: int = 1) -> str:
    """e.g. LOGIN-UI-001, LOGIN-E2E-001"""
    return f"{prefix}-{kind}-{seq:03d}"


def _ui_elements(screen: dict[str, Any] | None) -> list[dict[str, Any]]:
    attrs = _attrs(screen)
    raw = attrs.get("uiElements") or attrs.get("inputs") or (screen or {}).get("uiElements") or (screen or {}).get("inputs") or []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"name": item, "selector": item})
    return out


def _scenario_ui_composition(
    *,
    graph: dict[str, Any],
    project_id: str | None,
    screen: dict[str, Any],
    seq: int = 1,
) -> dict[str, Any]:
    """UI 구성 케이스 — LOGIN-UI-001 형태 (API 없음, selector·기대표시)."""
    attrs = _attrs(screen)
    route = str(attrs.get("route") or "missing_data")
    token = _token_from_route(route, str(screen.get("name") or ""))
    case_id = _case_id(token, "UI", seq)
    elements = _ui_elements(screen)
    # A screen composition check observes what is visible immediately after navigation.
    # Controls inside a closed modal belong to the modal business journey, not to the
    # initial screen.  Requiring them here produced false product failures.
    target_file_key = str(attrs.get("targetFile") or attrs.get("template") or "")
    related_attrs = [
        _attrs(node)
        for node in (graph.get("nodes") or [])
        if isinstance(node, dict)
        and node.get("type") == "screen"
        and target_file_key
        and str(_attrs(node).get("targetFile") or _attrs(node).get("template") or "")
        == target_file_key
    ]
    action_forms = [
        item
        for related in ([attrs] + related_attrs)
        for item in (related.get("actionForms") or [])
        if isinstance(item, dict)
    ]
    modal_control_selectors = {
        str(control.get("selector"))
        for form in action_forms
        if form.get("modalSelector")
        for control in (form.get("formControls") or [])
        if isinstance(control, dict) and control.get("selector")
    }
    elements = [
        item
        for item in elements
        if str(item.get("selector") or "") not in modal_control_selectors
        and str(item.get("type") or "").lower() != "hidden"
        and not (
            token in {"INDEX", "HOME"}
            and str(item.get("selector") or "") == "button[type='submit']"
        )
    ]
    for form in action_forms:
        if not form.get("modalSelector") or not form.get("openerSelector"):
            continue
        elements.append(
            {
                "name": form.get("openerLabel") or form.get("modalTitle") or "업무 열기",
                "field": form.get("openerLabel") or "modal-opener",
                "selector": form.get("openerSelector"),
                "kind": "button",
                "type": "button",
            }
        )
    modal_scoped = {
        *modal_control_selectors,
        *{
            str(form.get("formSelector"))
            for form in action_forms
            if form.get("modalSelector") and form.get("formSelector")
        },
    }
    for output in [
        item
        for related in ([attrs] + related_attrs)
        for item in (related.get("outputBindings") or [])
    ]:
        if not isinstance(output, dict):
            continue
        selector = str(output.get("selector") or "")
        if not selector or selector in modal_scoped or selector == "#alert-message":
            continue
        if any(str(item.get("selector") or "") == selector for item in elements):
            continue
        elements.append(
            {
                "name": "화면 결과 영역",
                "field": "screen-output",
                "selector": selector,
                "kind": "output",
                "type": "display",
            }
        )
    unique_elements: list[dict[str, Any]] = []
    seen_selectors: set[str] = set()
    for item in elements:
        selector = str(item.get("selector") or "")
        if not selector or selector in seen_selectors:
            continue
        seen_selectors.add(selector)
        unique_elements.append(item)
    elements = unique_elements
    target_file = (
        attrs.get("targetFile")
        or attrs.get("template")
        or ((screen.get("evidence") or [{}])[0].get("file") if isinstance(screen.get("evidence"), list) else None)
        or (screen.get("evidence") or {}).get("file")
        or "missing_data"
    )
    if isinstance(target_file, str) and target_file.endswith(".html") is False and attrs.get("template"):
        # prefer full relative path when available
        pass

    username_sel = next(
        (e.get("selector") for e in elements if "user" in str(e.get("selector") or e.get("field") or e.get("name") or "").lower()),
        None,
    )
    password_sel = next(
        (e.get("selector") for e in elements if "pass" in str(e.get("selector") or e.get("field") or e.get("name") or "").lower()),
        None,
    )
    submit_sel = next(
        (
            e.get("selector")
            for e in elements
            if e.get("kind") == "button" or e.get("type") == "submit" or "submit" in str(e.get("selector") or "").lower()
        ),
        None,
    )

    visible_labels = [str(e.get("name") or e.get("field") or e.get("selector")) for e in elements if e.get("name") or e.get("selector")]
    expected = (
        ", ".join(visible_labels) + " 이(가) 표시되어야 함"
        if visible_labels
        else "화면 주요 UI 컨트롤이 표시되어야 함"
    )

    steps: list[dict[str, Any]] = [
        {
            "id": "S1",
            "action": "navigate",
            "target": {"route": route},
            "timeoutMs": 10000,
            "evidenceRefs": [f"graph:{screen.get('id')}"],
        },
        {
            "id": "S2",
            "action": "assert_visible",
            "target": {"selectors": [e.get("selector") for e in elements if e.get("selector")][:8]},
            "timeoutMs": 5000,
            "evidenceRefs": [f"graph:{screen.get('id')}"],
        },
    ]

    label_ko = _GROUP_LABEL_KO.get(token, token)

    case_analysis = {
        "caseId": case_id,
        "testType": "UI 구성",
        "targetScreen": route,
        "targetFile": target_file,
        "usernameSelector": username_sel or "없음",
        "passwordSelector": password_sel or "없음",
        "submitSelector": submit_sel or "없음",
        "connectedApi": "없음",
        "requestValues": "없음",
        "expectedResult": expected,
        "uiElements": elements,
    }

    return {
        "scenarioId": f"SCN-{case_id.lower()}-{uuid4().hex[:8]}",
        "caseId": case_id,
        "serviceId": f"{token.lower()}-ui",
        "serviceLabelKo": f"{label_ko} UI",
        "name": f"{case_id} {label_ko} 화면 구성 확인",
        "description": f"{case_id} — 대상 화면 {route} UI 구성 관측. Pass/Fail은 HITL이 확정합니다.",
        "version": "1",
        "status": "READY_FOR_INPUT" if elements else "DRAFT",
        "projectId": project_id,
        "testType": "UI 구성",
        "caseAnalysis": case_analysis,
        "sourceRefs": {
            "graphId": graph.get("graphId"),
            "graphVersion": str(graph.get("version") or "1"),
            "commitRefs": dict(graph.get("commitRefs") or {}),
        },
        "source": {
            "screen": screen.get("name") or route,
            "route": route,
            "targetFile": target_file,
        },
        "destination": {"screen": "n/a", "routePattern": "n/a"},
        "request": {"method": "없음", "path": "없음", "body": "없음"},
        "response": {"status": "없음", "body": "없음"},
        "bindings": {"connectedApi": "없음"},
        "inputs": [],
        "steps": steps,
        "assertions": [
            {
                "id": "A1",
                "type": "dom-visible",
                "severity": "soft",
                "selectors": [e.get("selector") for e in elements if e.get("selector")][:8],
                "reviewRequired": True,
            }
        ],
        "evidencePolicy": {
            "screenshots": True,
            "snapshots": True,
            "network": False,
            "browserRunner": "agent-browser-mcp",
        },
        "hitlPolicy": {"requireHumanPassFail": True, "autoPassForbidden": True},
        "unresolved": []
        if elements
        else [{"kind": "missing_ui", "symbol": route, "reason": "uiElements missing_data"}],
        "evidenceIndex": [
            {
                "nodeId": screen.get("id"),
                "file": target_file,
                "extractor": "flask-jinja-ui",
            }
        ],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _scenario_from_flow(
    *,
    graph: dict[str, Any],
    service_id: str,
    project_id: str | None,
    screen: dict[str, Any] | None,
    call: dict[str, Any] | None,
    endpoint: dict[str, Any] | None,
    bindings: list[dict[str, Any]],
    extra_unresolved: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    unresolved: list[dict[str, Any]] = list(extra_unresolved or [])
    route = _attrs(screen).get("route")
    method = str(
        _attrs(call).get("method")
        or _attrs(endpoint).get("method")
        or ""
    ).upper()
    path = str(
        _attrs(call).get("normalizedPath")
        or _attrs(call).get("path")
        or _attrs(endpoint).get("path")
        or ""
    )
    if not screen:
        unresolved.append(
            {
                "kind": "missing_screen",
                "symbol": path or service_id,
                "reason": "FE screen evidence missing — UI steps marked missing_data",
            }
        )
    if not call and not endpoint:
        unresolved.append(
            {
                "kind": "missing_api",
                "symbol": service_id,
                "reason": "no API node in graph",
            }
        )

    status = "READY_FOR_INPUT" if screen and (call or endpoint) and method and path else "DRAFT"
    if unresolved and not (screen and (call or endpoint)):
        status = "DRAFT"

    steps: list[dict[str, Any]] = []
    step_i = 1
    entry_actions = list(_attrs(screen).get("entryActions") or [])
    entry = next(
        (
            item
            for item in entry_actions
            if isinstance(item, dict)
            and item.get("sourceRoute")
            and item.get("selector")
            and item.get("targetRoute") == route
        ),
        None,
    )
    if route and entry:
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        evidence_ref = (
            f"file:{evidence.get('file')}:{evidence.get('line') or 1}"
            if evidence.get("file")
            else f"graph:{screen.get('id')}"
        )
        steps.extend(
            [
                {
                    "id": f"S{step_i}",
                    "action": "navigate",
                    "target": {"route": str(entry["sourceRoute"])},
                    "timeoutMs": 10000,
                    "evidenceRefs": [evidence_ref],
                },
                {
                    "id": f"S{step_i + 1}",
                    "action": "click",
                    "target": {"strategy": "css", "value": str(entry["selector"])},
                    "timeoutMs": 5000,
                    "evidenceRefs": [evidence_ref],
                },
                {
                    "id": f"S{step_i + 2}",
                    "action": "verify_navigation",
                    "expect": {"routePattern": route},
                    "timeoutMs": 5000,
                    "evidenceRefs": [evidence_ref, f"graph:{screen.get('id')}"],
                },
            ]
        )
        step_i += 3
    elif route:
        steps.append(
            {
                "id": f"S{step_i}",
                "action": "navigate",
                "target": {"route": route},
                "timeoutMs": 10000,
                "evidenceRefs": [f"graph:{screen.get('id')}" if screen else "missing_data"],
            }
        )
        step_i += 1
    else:
        steps.append(
            {
                "id": f"S{step_i}",
                "action": "navigate",
                "target": {"route": "missing_data"},
                "timeoutMs": 10000,
                "evidenceRefs": ["missing_data"],
                "note": "screen route unavailable",
            }
        )
        step_i += 1

    inputs_spec: list[dict[str, Any]] = []
    ui_inputs = _ui_elements(screen) or list(_attrs(screen).get("inputs") or [])
    for inp in ui_inputs[:8]:
        if not isinstance(inp, dict):
            continue
        if inp.get("kind") == "button" or inp.get("type") == "submit":
            continue
        field = str(inp.get("field") or inp.get("name") or inp.get("testId") or f"field{step_i}")
        selector = inp.get("selector") or inp.get("testId") or inp.get("name")
        if not selector:
            continue
        if inp.get("selector"):
            strategy, value = "css", str(inp["selector"])
        elif inp.get("testId"):
            strategy, value = "testId", str(inp["testId"])
        else:
            strategy, value = "name", str(inp.get("name") or field)
        steps.append(
            {
                "id": f"S{step_i}",
                "action": "fill",
                "target": {"strategy": strategy, "value": value},
                "valueFrom": f"inputs.{field}",
                "timeoutMs": 5000,
                "evidenceRefs": [f"graph:input-{field}"],
            }
        )
        step_i += 1
        inputs_spec.append(
            {
                "name": field,
                "type": "string",
                "required": bool(inp.get("required", True)),
                "semanticType": "form_field",
                "constraints": {},
                "locator": {"strategy": strategy, "value": value},
                "events": ["fill"],
                "reviewRequired": True,
            }
        )

    submit = _attrs(screen).get("submitTestId") or _attrs(call).get("triggerTestId")
    destructive_submit = any(
        token in f"{path} {service_id}".lower()
        for token in ("signup", "deposit", "payment", "transfer", "withdraw", "delete", "consent")
    )
    submit_sel = next(
        (
            e.get("selector")
            for e in ui_inputs
            if isinstance(e, dict)
            and (e.get("kind") == "button" or e.get("type") == "submit")
            and e.get("selector")
        ),
        None,
    )
    if submit:
        steps.append(
            {
                "id": f"S{step_i}",
                "action": "click",
                "target": {"strategy": "testId", "value": str(submit)},
                "request": {"method": method, "path": path},
                "destructive": destructive_submit,
                "timeoutMs": 5000,
                "evidenceRefs": ["graph:submit"],
            }
        )
        step_i += 1
    elif submit_sel:
        steps.append(
            {
                "id": f"S{step_i}",
                "action": "click",
                "target": {"strategy": "css", "value": str(submit_sel)},
                "request": {"method": method, "path": path},
                "destructive": destructive_submit,
                "timeoutMs": 5000,
                "evidenceRefs": ["graph:submit"],
            }
        )
        step_i += 1
    elif screen and method and path and not submit and not submit_sel:
        unresolved.append(
            {
                "kind": "missing_locator",
                "symbol": "submit",
                "reason": "submit control selector missing_data",
            }
        )

    if method and path:
        steps.append(
            {
                "id": f"S{step_i}",
                "action": "wait_for_response",
                "request": {"method": method, "path": path},
                "timeoutMs": 10000,
                "evidenceRefs": [
                    f"graph:{(call or endpoint or {}).get('id') or 'api'}",
                ],
            }
        )
        step_i += 1
    else:
        unresolved.append(
            {
                "kind": "missing_api",
                "symbol": service_id,
                "reason": "method/path missing_data",
            }
        )

    for bind in bindings[:4]:
        field = bind.get("name") or _attrs(bind).get("field") or "field"
        test_id = _attrs(bind).get("testId")
        if not test_id:
            unresolved.append(
                {
                    "kind": "missing_binding_locator",
                    "symbol": str(field),
                    "reason": "binding testId missing_data",
                }
            )
            continue
        steps.append(
            {
                "id": f"S{step_i}",
                "action": "verify_binding",
                "target": {"strategy": "testId", "value": str(test_id)},
                "expect": {"field": field},
                "timeoutMs": 5000,
                "evidenceRefs": [f"graph:{bind.get('id')}"],
            }
        )
        step_i += 1

    evidence_refs = []
    for node in (screen, call, endpoint, *bindings[:4]):
        if not node:
            continue
        for ev in node.get("evidence") or []:
            evidence_refs.append(
                {
                    "nodeId": node.get("id"),
                    "file": ev.get("file"),
                    "startLine": ev.get("startLine"),
                    "extractor": ev.get("extractor"),
                }
            )

    label_bits = []
    blob = f"{service_id} {path} {route or ''}"
    for token, ko in (
        ("customer", "고객"),
        ("search", "조회"),
        ("login", "로그인"),
        ("deposit", "입금"),
        ("payment", "결제"),
        ("balance", "잔액"),
        ("transaction", "거래"),
        ("transfer", "송금"),
        ("account", "계좌"),
    ):
        if token in blob.lower() and ko not in label_bits:
            label_bits.append(ko)
    service_label = " ".join(label_bits) if label_bits else service_id.replace("-", " ")
    token = _token_from_route(str(route or path or service_id), service_id)
    case_id = _case_id(token, "E2E", 1) if method and path else _case_id(token, "API", 1)

    request_body: dict[str, Any]
    if inputs_spec:
        request_body = {inp["name"]: "reviewRequired" for inp in inputs_spec}
    else:
        # Do not invent body keys — mark review when API exists without form fields
        request_body = {"reviewRequired": True}

    request_seed = {
        "method": method or "missing_data",
        "path": path or "missing_data",
        "headers": {"X-Scenario-ID": case_id},
        "body": request_body,
    }
    binding_fields = {
        str(b.get("name") or _attrs(b).get("field")): "reviewRequired"
        for b in bindings[:4]
        if b.get("name") or _attrs(b).get("field")
    }
    response_seed = {
        "status": "reviewRequired",
        "body": binding_fields or {"reviewRequired": True},
    }

    ui = _ui_elements(screen)
    case_analysis = {
        "caseId": case_id,
        "testType": "E2E 관통" if screen and method and path else "API",
        "targetScreen": route or "missing_data",
        "targetFile": _attrs(screen).get("targetFile") or _attrs(screen).get("template") or "missing_data",
        "usernameSelector": next(
            (e.get("selector") for e in ui if "user" in str(e.get("selector") or "").lower()),
            "없음",
        ),
        "passwordSelector": next(
            (e.get("selector") for e in ui if "pass" in str(e.get("selector") or "").lower()),
            "없음",
        ),
        "submitSelector": next(
            (e.get("selector") for e in ui if e.get("type") == "submit" or e.get("kind") == "button"),
            "없음",
        ),
        "connectedApi": f"{method} {path}" if method and path else "missing_data",
        "requestValues": "reviewRequired (HITL 확정 전)",
        "expectedResult": "응답·후속 화면 관측 후 HITL 확정",
        "uiElements": ui,
    }

    return {
        "scenarioId": f"SCN-{case_id.lower()}-{uuid4().hex[:8]}",
        "caseId": case_id,
        "serviceId": service_id,
        "serviceLabelKo": service_label,
        "name": f"{case_id} {service_label} 관통",
        "description": f"{case_id} — Graph Evidence 기반 Scenario DSL 초안. Pass/Fail은 HITL이 확정합니다.",
        "version": "1",
        "status": status,
        "projectId": project_id,
        "testType": case_analysis["testType"],
        "caseAnalysis": case_analysis,
        "sourceRefs": {
            "graphId": graph.get("graphId"),
            "graphVersion": str(graph.get("version") or "1"),
            "commitRefs": dict(graph.get("commitRefs") or {}),
        },
        "source": {
            "screen": (screen or {}).get("name") or "missing_data",
            "route": route or "missing_data",
            "targetFile": case_analysis["targetFile"],
        },
        "destination": {
            "screen": "missing_data",
            "routePattern": "missing_data",
        },
        "request": request_seed,
        "response": response_seed,
        "bindings": binding_fields or {"reviewRequired": True},
        "inputs": inputs_spec,
        "steps": steps,
        "assertions": [
            {
                "id": "A1",
                "type": "network-status",
                "severity": "soft",
                "actualFrom": "lastResponse.status",
                "reviewRequired": True,
            }
        ],
        "evidencePolicy": {
            "screenshots": True,
            "snapshots": True,
            "network": True,
            "browserRunner": "agent-browser-mcp",
        },
        "hitlPolicy": {
            "requireHumanPassFail": True,
            "autoPassForbidden": True,
        },
        "unresolved": unresolved,
        "evidenceIndex": evidence_refs,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _scenario_from_action_journey(
    *,
    graph: dict[str, Any],
    service_id: str,
    project_id: str | None,
    screen: dict[str, Any],
    action_form: dict[str, Any],
    call: dict[str, Any] | None,
    endpoint: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compose one business goal across UI action → API → downstream screen state.

    This is intentionally evidence-driven: the form, opener, controls, success message,
    and post-action containers all come from the analyzed template/handler.  Missing
    links stay unresolved rather than being filled with an app-specific recipe.
    """
    attrs = _attrs(screen)
    route = str(action_form.get("sourceRoute") or attrs.get("route") or "missing_data")
    method = str(
        action_form.get("method")
        or _attrs(call).get("method")
        or _attrs(endpoint).get("method")
        or ""
    ).upper()
    path = str(
        action_form.get("action")
        or _attrs(call).get("normalizedPath")
        or _attrs(call).get("path")
        or _attrs(endpoint).get("path")
        or ""
    ).split("?", 1)[0]
    token = _token_from_route(path or route, service_id)
    case_id = _case_id(token, "E2E", 1)
    service_label = _GROUP_LABEL_KO.get(token, service_id.replace("-", " "))
    controls = [item for item in (action_form.get("formControls") or []) if isinstance(item, dict)]
    outputs = [item for item in (action_form.get("outputBindings") or []) if isinstance(item, dict)]
    messages = [str(item) for item in (action_form.get("resultMessages") or []) if item]
    entry_actions = [
        item
        for item in (attrs.get("entryActions") or [])
        if isinstance(item, dict)
        and str(item.get("targetRoute") or "").rstrip("/") == route.rstrip("/")
        and item.get("selector")
    ]
    entry_action = entry_actions[0] if entry_actions else None
    journey_start_route = str((entry_action or {}).get("sourceRoute") or route)
    success_message = next((item for item in messages if "success" in item.lower()), None)
    amount_control = next(
        (
            item
            for item in controls
            if any(
                hint in str(item.get("field") or item.get("name") or "").lower()
                for hint in ("amount", "금액", "price")
            )
            and item.get("selector")
        ),
        None,
    )
    balance_output = next(
        (
            item
            for item in outputs
            if "balance" in " ".join(str(value) for value in item.get("bindings") or []).lower()
        ),
        None,
    )
    collection_candidates = [
        item
        for item in outputs
        if item.get("kind") == "collection"
        and any(
            hint in " ".join(str(value) for value in item.get("bindings") or []).lower()
            for hint in ("history", "transaction", "list")
        )
    ]
    collection_output = next(
        (item for item in collection_candidates if "list" in str(item.get("selector") or "").lower()),
        collection_candidates[0] if collection_candidates else None,
    )
    message_output = next(
        (
            item
            for item in outputs
            if any("message" in str(value).lower() for value in item.get("bindings") or [])
        ),
        None,
    )

    steps: list[dict[str, Any]] = []

    def add(action: str, title: str, **extra: Any) -> None:
        steps.append(
            {
                "id": f"S{len(steps) + 1}",
                "action": action,
                "title": title,
                "preserveTitle": True,
                "timeoutMs": int(extra.pop("timeoutMs", 10000)),
                **extra,
            }
        )

    add(
        "navigate",
        "업무 시작 화면을 엽니다",
        target={"route": journey_start_route},
        evidenceRefs=[f"graph:{screen.get('id')}"],
    )
    if entry_action:
        add(
            "click",
            f"「{entry_action.get('label') or '다음 화면'}」을 클릭합니다",
            target={"strategy": "css", "value": str(entry_action["selector"])},
            evidenceRefs=["graph:screen.entryActions"],
        )
        add(
            "verify_navigation",
            "업무 입력 화면으로 이동했는지 확인합니다",
            expect={"routePattern": route},
            evidenceRefs=["graph:screen.entryActions.targetRoute"],
        )
    if balance_output and balance_output.get("selector"):
        add(
            "capture_value",
            "업무 수행 전 현재 값을 기록합니다",
            target={"strategy": "css", "value": str(balance_output["selector"])},
            captureAs="beforeValue",
            evidenceRefs=["graph:output-binding:before"],
        )
    if collection_output and collection_output.get("selector"):
        add(
            "capture_collection",
            "업무 수행 전 목록 상태를 기록합니다",
            target={"strategy": "css", "value": str(collection_output["selector"])},
            captureAs="beforeCollection",
            evidenceRefs=["graph:output-binding:collection-before"],
        )
    opener = str(action_form.get("openerSelector") or "")
    if opener:
        add(
            "click",
            f"「{action_form.get('openerLabel') or service_label}」 업무 버튼을 클릭합니다",
            target={"strategy": "css", "value": opener},
            evidenceRefs=["graph:action-form:opener"],
        )
    modal = str(action_form.get("modalSelector") or "")
    if modal:
        add(
            "assert_visible",
            f"「{action_form.get('modalTitle') or '업무 입력 화면'}」이 열렸는지 확인합니다",
            target={"selectors": [modal]},
            evidenceRefs=["graph:action-form:modal"],
        )

    inputs_spec: list[dict[str, Any]] = []
    selected_refs: list[str] = []
    for control in controls:
        selector = str(control.get("selector") or "")
        if not selector or control.get("kind") == "button" or str(control.get("type") or "") == "hidden":
            continue
        field = str(control.get("field") or control.get("name") or "field")
        if control.get("kind") == "select" or control.get("type") == "select":
            selected_ref = f"selected.{field}"
            add(
                "select",
                f"「{control.get('name') or field}」에서 화면에 제공된 항목 하나를 선택합니다",
                target={"strategy": "css", "value": selector},
                valueStrategy="first_enabled",
                captureAs=selected_ref,
                evidenceRefs=["graph:action-form:select"],
            )
            selected_refs.append(selected_ref)
            continue
        # Optional fields hidden behind a secondary branch do not belong to the default
        # successful journey. Required controls and the primary amount/value field do.
        if not control.get("required") and control is not amount_control:
            continue
        credential_ref = None
        if token.lower() == "login":
            lowered = field.lower()
            if any(hint in lowered for hint in ("username", "loginid", "login_id", "user_id")):
                credential_ref = "environment.loginId"
            elif any(hint in lowered for hint in ("password", "passwd", "pwd")):
                credential_ref = "environment.loginSecret"
        fill_payload: dict[str, Any] = {
            "target": {"strategy": "css", "value": selector},
            "evidenceRefs": ["graph:action-form:input"],
        }
        if credential_ref:
            fill_payload["valueRef"] = credential_ref
            if credential_ref.endswith("loginSecret"):
                fill_payload["masked"] = True
        else:
            fill_payload["valueFrom"] = f"inputs.{field}"
        add(
            "fill",
            f"「{control.get('name') or field}」에 테스트 값을 입력합니다",
            **fill_payload,
        )
        constraints = {
            key: control.get(key)
            for key in ("min", "max", "step", "pattern")
            if control.get(key) not in (None, "")
        }
        if credential_ref:
            continue
        inputs_spec.append(
            {
                "name": field,
                "type": "number" if str(control.get("type") or "").lower() == "number" else "string",
                "required": bool(control.get("required", True)),
                "semanticType": "business_input",
                "constraints": constraints,
                "locator": {"strategy": "css", "value": selector},
                "events": ["fill"],
                "reviewRequired": True,
            }
        )

    submit_control = next(
        (
            control
            for control in controls
            if control.get("kind") == "button"
            and str(control.get("type") or "").lower() in {"submit", "button", ""}
            and control.get("selector")
        ),
        {},
    )
    submit = str(action_form.get("triggerSelector") or submit_control.get("selector") or "")
    if submit:
        add(
            "click",
            f"「{action_form.get('triggerLabel') or submit_control.get('accessibleName') or submit_control.get('name') or service_label}」을 실행합니다",
            target={"strategy": "css", "value": submit},
            request={"method": method, "path": path},
            destructive=any(
                token in f"{path} {service_id}".lower()
                for token in ("signup", "deposit", "payment", "transfer", "withdraw", "delete", "consent")
            ),
            evidenceRefs=["graph:action-form:submit"],
        )
    add(
        "wait_for_response",
        f"{method} {path} 처리와 후속 화면 갱신을 기다립니다",
        request={"method": method, "path": path},
        evidenceRefs=[f"graph:{(call or endpoint or {}).get('id') or 'api'}"],
    )
    criteria: list[dict[str, Any]] = []
    destination_route = str(action_form.get("destinationRoute") or "")
    if destination_route:
        cid = "C-destination-route"
        add(
            "verify_navigation",
            "처리 후 기대 화면으로 이동했는지 확인합니다",
            expect={"routePattern": destination_route},
            criterionId=cid,
            evidenceRefs=["graph:action-form:destinationRoute"],
        )
        criteria.append(
            {
                "id": cid,
                "check": "destination_route",
                "expected": f"처리 후 {destination_route} 화면으로 이동한다",
            }
        )
    if success_message and message_output and message_output.get("selector"):
        cid = "C-success-message"
        add(
            "assert_text",
            f"후속 화면에 「{success_message}」 안내가 표시되는지 확인합니다",
            target={"strategy": "css", "value": str(message_output["selector"])},
            expect={"contains": success_message},
            criterionId=cid,
            evidenceRefs=["graph:result-message"],
        )
        criteria.append(
            {"id": cid, "check": "success_message", "expected": f"후속 화면에 {success_message} 안내가 보인다"}
        )
    if amount_control and balance_output and balance_output.get("selector"):
        cid = "C-state-delta"
        add(
            "verify_numeric_delta",
            "업무 전 값에 입력 금액이 반영됐는지 확인합니다",
            target={"strategy": "css", "value": str(balance_output["selector"])},
            expect={
                "beforeRef": "beforeValue",
                "deltaFrom": f"inputs.{amount_control.get('field') or 'amount'}",
                "direction": str(action_form.get("numericEffect") or "unknown"),
            },
            criterionId=cid,
            evidenceRefs=["graph:output-binding:delta"],
        )
        criteria.append(
            {
                "id": cid,
                "check": "numeric_delta",
                "expected": (
                    "업무 전 값에 실행 입력값만큼 증가가 반영된다"
                    if action_form.get("numericEffect") == "increase"
                    else "업무 전 값에 실행 입력값만큼 감소가 반영된다"
                    if action_form.get("numericEffect") == "decrease"
                    else "업무 전후 값에 실행 입력값에 대응하는 변화가 반영된다"
                ),
            }
        )
    if collection_output and collection_output.get("selector"):
        cid = "C-collection-change"
        add(
            "verify_collection_change",
            "목록에 이번 업무 결과 행과 입력값이 반영됐는지 확인합니다",
            target={"strategy": "css", "value": str(collection_output["selector"])},
            expect={
                "beforeRef": "beforeCollection",
                "containsFrom": f"inputs.{amount_control.get('field') or 'amount'}" if amount_control else None,
                "selectedFrom": selected_refs[0] if selected_refs else None,
                "freshRow": True,
            },
            criterionId=cid,
            evidenceRefs=["graph:output-binding:collection-after"],
        )
        criteria.append(
            {
                "id": cid,
                "check": "collection_change",
                "expected": "업무 결과 목록에 이번 실행의 새 행·선택 항목 라벨·입력값이 반영된다",
            }
        )

    unresolved: list[dict[str, Any]] = []
    for symbol, available in (
        # A direct form page does not need an opener.  Modal forms and cross-screen
        # journeys do, and entryActions is the evidenced cross-screen opener.
        ("action opener", bool(opener or entry_action or not modal)),
        ("form submit", bool(submit)),
        ("post-action state", bool(criteria)),
    ):
        if not available:
            unresolved.append(
                {"kind": "missing_journey_evidence", "symbol": symbol, "reason": "코드 분석에서 업무 여정 근거를 찾지 못했습니다"}
            )
    body = {item["name"]: "reviewRequired" for item in inputs_spec}
    for control in controls:
        if control.get("kind") == "select" and control.get("field"):
            body[str(control["field"])] = "selected_from_screen"
    target_file = str(attrs.get("targetFile") or attrs.get("template") or "missing_data")
    expected_parts = [item["expected"] for item in criteria]
    outcome_labels: list[str] = []
    if success_message:
        outcome_labels.append("완료 안내")
    if balance_output:
        outcome_labels.append("잔액")
    if collection_output:
        outcome_labels.append("거래내역")
    if not outcome_labels:
        outcome_labels.append("후속 화면")
    business_name = f"{service_label} 후 {'·'.join(outcome_labels)} 정상 반영 확인"
    return {
        "scenarioId": f"SCN-{case_id.lower()}-{uuid4().hex[:8]}",
        "caseId": case_id,
        "serviceId": service_id,
        "serviceLabelKo": service_label,
        "name": business_name,
        "description": (
            f"{action_form.get('openerLabel') or service_label} 시작부터 {method} {path} 처리, "
            "후속 화면의 값·목록 변화까지 한 실행에서 관측하는 업무 여정입니다. 최종 판정은 HITL이 확정합니다."
        ),
        "version": "1",
        "status": "READY_FOR_INPUT" if method and path and submit else "DRAFT",
        "projectId": project_id,
        "testType": "업무 E2E 관통",
        "businessJourney": True,
        "userEventJourney": True,
        "caseAnalysis": {
            "caseId": case_id,
            "testType": "업무 E2E 관통",
            "targetScreen": route,
            "targetFile": target_file,
            "usernameSelector": "연결 계정 참조",
            "passwordSelector": "연결 계정 참조",
            "submitSelector": submit or "없음",
            "connectedApi": f"{method} {path}",
            "requestValues": ", ".join(body) or "화면 제공값",
            "expectedResult": " · ".join(expected_parts) or "후속 화면 상태 근거 확인 필요",
            "uiElements": controls,
        },
        "sourceRefs": {
            "graphId": graph.get("graphId"),
            "graphVersion": str(graph.get("version") or "1"),
            "commitRefs": dict(graph.get("commitRefs") or {}),
        },
        "source": {
            "screen": (
                f"{entry_action.get('sourceRoute')} → {screen.get('name') or route}"
                if entry_action
                else screen.get("name") or route
            ),
            "route": journey_start_route,
            "targetFile": target_file,
        },
        "destination": {
            "screen": "후속 업무 화면",
            "routePattern": str(action_form.get("destinationRoute") or route),
        },
        "request": {"method": method, "path": path, "headers": {"X-Scenario-ID": case_id}, "body": body},
        "response": {"status": "reviewRequired", "body": {"screenStateChanged": bool(criteria)}},
        "bindings": {"beforeAfter": [item.get("selector") for item in outputs if item.get("selector")]},
        "inputs": inputs_spec,
        "steps": steps,
        "assertions": [
            {"id": item["id"], "type": item["check"], "severity": "hard", "reviewRequired": True}
            for item in criteria
        ],
        "verdictCriteria": criteria,
        "evidencePolicy": {"screenshots": True, "snapshots": True, "network": True, "browserRunner": "agent-browser-mcp"},
        "hitlPolicy": {"requireHumanPassFail": True, "autoPassForbidden": True},
        "unresolved": unresolved,
        "evidenceIndex": [action_form.get("evidence") or {}],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _decimal_constraint(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not text or "{{" in text or "}}" in text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _variant_case_id(case_id: str, seq: int) -> str:
    parts = str(case_id or "SCENARIO-E2E-001").split("-")
    if parts and parts[-1].isdigit():
        parts[-1] = f"{seq:03d}"
        return "-".join(parts)
    return f"{case_id}-{seq:03d}"


def _business_variant(
    base: dict[str, Any],
    *,
    seq: int,
    key: str,
    label: str,
    category: str,
    field: str,
    value: Any = None,
    value_strategy: str | None = None,
    validation_only: bool = False,
) -> dict[str, Any]:
    """Clone one evidenced journey into a distinct input-coverage case."""
    scenario = deepcopy(base)
    case_id = _variant_case_id(str(base.get("caseId") or "SCENARIO-E2E-001"), seq)
    scenario["scenarioId"] = f"SCN-{case_id.lower()}-{uuid4().hex[:8]}"
    scenario["caseId"] = case_id
    scenario["name"] = f"{base.get('name') or base.get('serviceLabelKo') or '업무'} · {label}"
    scenario["caseVariant"] = {
        "key": key,
        "category": category,
        "source": "frontend_constraint+runtime_dom+backend_contract",
        "field": field,
        "validationOnly": validation_only,
    }
    scenario["categoryHints"] = ["E2E", category]
    scenario["inputDefaults"] = {field: value} if value_strategy is None else {}
    scenario["inputStrategies"] = {field: value_strategy} if value_strategy else {}
    scenario["description"] = (
        f"{base.get('description') or ''} 분석된 입력 제약을 사용해 「{label}」 관측을 추가한 케이스입니다."
    ).strip()
    request = dict(scenario.get("request") or {})
    headers = dict(request.get("headers") or {})
    headers["X-Scenario-ID"] = case_id
    request["headers"] = headers
    body = dict(request.get("body") or {})
    body[field] = value_strategy or value
    request["body"] = body
    scenario["request"] = request

    steps = list(scenario.get("steps") or [])
    fill_index = next(
        (
            index
            for index, step in enumerate(steps)
            if str(step.get("action") or "") == "fill"
            and str(step.get("valueFrom") or "") == f"inputs.{field}"
        ),
        None,
    )
    if fill_index is not None:
        fill_step = steps[fill_index]
        fill_step["caseInput"] = value
        if value_strategy:
            fill_step["valueStrategy"] = value_strategy
            input_spec = next(
                (
                    item
                    for item in (base.get("inputs") or [])
                    if isinstance(item, dict) and str(item.get("name") or "") == field
                ),
                {},
            )
            strategy_constraints = input_spec.get("constraints") if isinstance(input_spec.get("constraints"), dict) else {}
            fill_step["valueStrategyStep"] = strategy_constraints.get("step") or "1"
        if value == "":
            fill_step["allowEmpty"] = True
        if validation_only:
            target = deepcopy(fill_step.get("target") or {})
            steps = steps[: fill_index + 1]
            criterion_id = f"C-{key}"
            steps.append(
                {
                    "id": f"S{len(steps) + 1}",
                    "action": "assert_invalid",
                    "title": f"「{label}」 입력이 브라우저 제약에 의해 거부되는지 확인합니다",
                    "preserveTitle": True,
                    "target": target,
                    "expect": {"valid": False, "constraintSource": "frontend"},
                    "criterionId": criterion_id,
                    "timeoutMs": 5000,
                    "evidenceRefs": list(fill_step.get("evidenceRefs") or []),
                }
            )
            scenario["verdictCriteria"] = [
                {
                    "id": criterion_id,
                    "check": "native_constraint_rejection",
                    "expected": f"{label} 입력은 업무 요청 전에 화면 제약에서 거부된다",
                }
            ]
            scenario["assertions"] = [
                {
                    "id": criterion_id,
                    "type": "native_constraint_rejection",
                    "severity": "hard",
                    "reviewRequired": True,
                }
            ]
            scenario["destination"] = {
                "screen": (scenario.get("source") or {}).get("screen") or "입력 화면",
                "routePattern": (scenario.get("source") or {}).get("route") or "missing_data",
            }
            scenario["response"] = {
                "status": "request_not_sent",
                "body": {"nativeConstraintValid": False},
                "reviewRequired": True,
            }
    scenario["steps"] = steps
    case_analysis = dict(scenario.get("caseAnalysis") or {})
    case_analysis["caseId"] = case_id
    case_analysis["testCategory"] = category
    case_analysis["inputCase"] = {field: value_strategy or value}
    case_analysis["expectedResult"] = (
        f"{label} 입력을 화면 제약에서 거부" if validation_only else f"{label} 입력으로 업무 전후 상태 관측"
    )
    scenario["caseAnalysis"] = case_analysis
    return scenario


def expand_evidenced_case_matrix(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand numeric forms by evidenced min/max/required/dynamic-balance rules."""
    expanded: list[dict[str, Any]] = []
    for scenario in scenarios:
        expanded.append(scenario)
        if not scenario.get("businessJourney"):
            continue
        amount = next(
            (
                item
                for item in (scenario.get("inputs") or [])
                if isinstance(item, dict)
                and any(token in str(item.get("name") or "").lower() for token in ("amount", "금액", "price"))
            ),
            None,
        )
        if not amount:
            continue
        field = str(amount.get("name") or "amount")
        constraints = amount.get("constraints") if isinstance(amount.get("constraints"), dict) else {}
        minimum = _decimal_constraint(constraints.get("min"))
        maximum = _decimal_constraint(constraints.get("max"))
        step = _decimal_constraint(constraints.get("step")) or Decimal("1")
        variants: list[dict[str, Any]] = []
        seq = 2
        if minimum is not None:
            variants.append(_business_variant(
                scenario, seq=seq, key="minimum_boundary", label="최소 허용값 경계",
                category="boundary", field=field, value=_format_decimal(minimum),
            ))
            seq += 1
            variants.append(_business_variant(
                scenario, seq=seq, key="below_minimum", label="최소 허용값 미만 거부",
                category="validation", field=field, value=_format_decimal(minimum - step),
                validation_only=True,
            ))
            seq += 1
        if amount.get("required"):
            variants.append(_business_variant(
                scenario, seq=seq, key="required_missing", label="필수 금액 누락 거부",
                category="validation", field=field, value="", validation_only=True,
            ))
            seq += 1
        if maximum is not None:
            variants.append(_business_variant(
                scenario, seq=seq, key="maximum_boundary", label="최대 허용값 경계",
                category="boundary", field=field, value=_format_decimal(maximum),
            ))
            seq += 1
            variants.append(_business_variant(
                scenario, seq=seq, key="above_maximum", label="최대 허용값 초과 거부",
                category="validation", field=field, value=_format_decimal(maximum + step),
                validation_only=True,
            ))
        elif "balance" in str(constraints.get("max") or "").lower():
            variants.append(_business_variant(
                scenario, seq=seq, key="observed_balance_boundary", label="실행 직전 잔액 전액 경계",
                category="boundary", field=field, value_strategy="observed_balance",
            ))
            seq += 1
            variants.append(_business_variant(
                scenario, seq=seq, key="above_observed_balance", label="실행 직전 잔액 초과 거부",
                category="business_error", field=field,
                value_strategy="observed_balance_plus_step", validation_only=True,
            ))
        coverage_matrix = {
            "source": "frontend_constraint+runtime_dom+backend_contract",
            "variants": ["happy_path", *[str(item["caseVariant"]["key"]) for item in variants]],
            "fixedScenarioLimit": False,
        }
        scenario["coverageMatrix"] = coverage_matrix
        for variant in variants:
            variant["coverageMatrix"] = deepcopy(coverage_matrix)
        expanded.extend(variants)
    return expanded


def generate_scenarios(
    graph: dict[str, Any],
    *,
    service_id: str | None = None,
    project_id: str | None = None,
    project_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Emit one scenario per evidenced API/screen flow. Never invent customer-search defaults."""
    nodes = _node_map(graph)
    screens = [n for n in nodes.values() if n.get("type") == "screen"]
    calls = [n for n in nodes.values() if n.get("type") == "frontend_api_call"]
    endpoints = [
        n
        for n in nodes.values()
        if n.get("type") == "backend_endpoint"
        and not _is_probe(str(_attrs(n).get("path") or n.get("name") or ""))
    ]
    bindings = [n for n in nodes.values() if n.get("type") == "binding"]
    edges = list(graph.get("edges") or [])

    # Map FE call → BE endpoint via edges
    call_to_be: dict[str, str] = {}
    for edge in edges:
        if edge.get("type") in {"calls", "maps_to", "invokes"}:
            frm, to = edge.get("from"), edge.get("to")
            if frm in nodes and to in nodes:
                if nodes[frm].get("type") == "frontend_api_call" and nodes[to].get("type") == "backend_endpoint":
                    call_to_be[frm] = to
                if nodes[to].get("type") == "frontend_api_call" and nodes[frm].get("type") == "backend_endpoint":
                    call_to_be[to] = frm

    screen_by_route = {
        str(_attrs(s).get("route")): s for s in screens if _attrs(s).get("route")
    }

    def action_journey(path: str, method: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        normalized = str(path or "").split("?", 1)[0]
        for candidate in screens:
            for form in _attrs(candidate).get("actionForms") or []:
                if not isinstance(form, dict):
                    continue
                if str(form.get("action") or "").split("?", 1)[0] != normalized:
                    continue
                if str(form.get("method") or "GET").upper() != method.upper():
                    continue
                return candidate, form
        return None, None

    flows: list[dict[str, Any]] = []
    used_be: set[str] = set()

    for call in calls:
        attrs = _attrs(call)
        method = str(attrs.get("method") or "GET").upper()
        path = str(attrs.get("normalizedPath") or attrs.get("path") or "")
        if not path or _is_probe(path):
            continue
        be = nodes.get(call_to_be.get(call["id"], ""), None)
        if be:
            used_be.add(be["id"])
        route_hint = str(attrs.get("screenRoute") or attrs.get("fromRoute") or "")
        journey_screen, action_form = action_journey(path, method)
        screen = journey_screen or screen_by_route.get(route_hint) or (screens[0] if len(screens) == 1 else None)
        sid = service_id if service_id and service_id != "customer-search" else _service_id_for(method, path)
        flows.append(
            {
                "service_id": sid,
                "screen": screen,
                "call": call,
                "endpoint": be,
                "bindings": bindings if screen else [],
                "action_form": action_form,
            }
        )

    for ep in endpoints:
        if ep["id"] in used_be:
            continue
        attrs = _attrs(ep)
        method = str(attrs.get("method") or "GET").upper()
        path = str(attrs.get("path") or "")
        if not path:
            continue
        sid = service_id if service_id and service_id != "customer-search" else _service_id_for(method, path)
        journey_screen, action_form = action_journey(path, method)
        # Prefer the screen that contains the evidenced user form; otherwise match a route hint.
        hint = path.lower()
        screen = journey_screen
        if not screen:
            for s in screens:
                route = str(_attrs(s).get("route") or "").lower()
                name = str(s.get("name") or "").lower()
                if any(token in hint and (token in route or token in name) for token in ("login", "deposit", "payment", "home", "signup", "balance", "transaction")):
                    screen = s
                    break
        # Backend-only endpoints remain valuable analysis/Graph evidence, but they are
        # not executable browser E2E journeys.  Publishing them in the Console created
        # duplicate DRAFT rows with missing routes and made "전체 테스트" misleading.
        # They can be promoted only after a FE call, screen or evidenced action form is linked.
        if not screen and not action_form:
            continue
        flows.append(
            {
                "service_id": sid,
                "screen": screen,
                "call": None,
                "endpoint": ep,
                "bindings": [],
                "action_form": action_form,
                "extra_unresolved": [
                    {
                        "kind": "missing_fe_api_call",
                        "symbol": f"{method} {path}",
                        "reason": "FE apiCall evidence missing — BE-only draft",
                    }
                ]
                if not screen
                else [
                    {
                        "kind": "missing_fe_api_call",
                        "symbol": f"{method} {path}",
                        "reason": "FE apiCall evidence missing — screen linked by route hint only",
                    }
                ],
            }
        )

    # Deduplicate API/E2E flows by service_id+method+path
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for flow in flows:
        method = str(
            _attrs(flow.get("call")).get("method")
            or _attrs(flow.get("endpoint")).get("method")
            or "NA"
        ).upper()
        path = str(
            _attrs(flow.get("call")).get("normalizedPath")
            or _attrs(flow.get("call")).get("path")
            or _attrs(flow.get("endpoint")).get("path")
            or _attrs(flow.get("screen")).get("route")
            or flow["service_id"]
        )
        key = f"{flow['service_id']}|{method}|{path}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            _scenario_from_action_journey(
                graph=graph,
                service_id=flow["service_id"],
                project_id=project_id,
                screen=flow["screen"],
                action_form=flow["action_form"],
                call=flow.get("call"),
                endpoint=flow.get("endpoint"),
            )
            if flow.get("action_form") and flow.get("screen")
            else _scenario_from_flow(
                graph=graph,
                service_id=flow["service_id"],
                project_id=project_id,
                screen=flow.get("screen"),
                call=flow.get("call"),
                endpoint=flow.get("endpoint"),
                bindings=list(flow.get("bindings") or []),
                extra_unresolved=list(flow.get("extra_unresolved") or []),
            )
        )

    # Always emit UI 구성 케이스 per screen with evidenced controls (LOGIN-UI-001 …).
    # One UI case per screen/token — do not invent LOGIN-UI-002 without distinct evidence.
    ui_seq: dict[str, int] = {}
    for screen in screens:
        elements = _ui_elements(screen)
        route = str(_attrs(screen).get("route") or "")
        if not elements and not route:
            continue
        if not elements:
            # Screen node without controls — still emit DRAFT UI case only if no API covered it
            continue
        token = _token_from_route(route, str(screen.get("name") or ""))
        ui_seq[token] = ui_seq.get(token, 0) + 1
        out.append(
            _scenario_ui_composition(
                graph=graph,
                project_id=project_id,
                screen=screen,
                seq=ui_seq[token],
            ),
        )

    if not out:
        # Last resort: do not invent customer-search — emit single DRAFT with graph unresolved
        draft = {
            "scenarioId": f"SCN-unresolved-{uuid4().hex[:8]}",
            "serviceId": service_id or "unresolved",
            "name": "unresolved: graph has no API/screen flows",
            "description": "Graph lacked screen/API evidence. Do not invent endpoints.",
            "version": "1",
            "status": "DRAFT",
            "projectId": project_id,
            "sourceRefs": {
                "graphId": graph.get("graphId"),
                "graphVersion": str(graph.get("version") or "1"),
                "commitRefs": dict(graph.get("commitRefs") or {}),
            },
            "source": {"screen": "missing_data", "route": "missing_data"},
            "destination": {"screen": "missing_data", "routePattern": "missing_data"},
            "inputs": [],
            "steps": [],
            "assertions": [],
            "evidencePolicy": {
                "screenshots": True,
                "snapshots": True,
                "network": True,
                "browserRunner": "agent-browser-mcp",
            },
            "hitlPolicy": {"requireHumanPassFail": True, "autoPassForbidden": True},
            "unresolved": list(graph.get("unresolved") or [])
            + [{"kind": "empty_graph", "symbol": "*", "reason": "no flow candidates"}],
            "evidenceIndex": [],
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
        fallback = apply_human_journey_order([attach_runtime_discovery_evidence(draft, graph)])
        return attach_project_context_evidence(fallback, project_context)

    # 세션 선행조건 — 로그인 뒤 화면이면 로그인 단계를 시나리오에 포함한다 (D-015)
    auth_context = graph.get("authContext") if isinstance(graph.get("authContext"), dict) else {}
    expanded = expand_evidenced_case_matrix(out)
    scoped = [apply_session_precondition(s, auth_context=auth_context) for s in expanded]
    grounded = [attach_runtime_discovery_evidence(scenario, graph) for scenario in scoped]
    ordered = apply_human_journey_order(dedupe_scenarios(grounded))
    return attach_project_context_evidence(ordered, project_context)


def attach_project_context_evidence(
    scenarios: list[dict[str, Any]], project_context: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Join relevant CSV/PPT guidance without turning document-only claims into executable facts."""
    if not isinstance(project_context, dict) or project_context.get("status") != "found":
        return scenarios
    chunks = [item for item in (project_context.get("chunks") or []) if isinstance(item, dict)]
    documents = [item for item in (project_context.get("documents") or []) if isinstance(item, dict)]
    if not chunks:
        return scenarios

    def terms(value: str) -> set[str]:
        normalized = re.sub(r"[^0-9a-z가-힣]+", " ", str(value or "").lower())
        return {token for token in normalized.split() if len(token) > 1}

    enriched: list[dict[str, Any]] = []
    for scenario in scenarios:
        source = scenario.get("source") if isinstance(scenario.get("source"), dict) else {}
        request = scenario.get("request") if isinstance(scenario.get("request"), dict) else {}
        scenario_blob = " ".join(
            str(value or "")
            for value in (
                scenario.get("scenarioId"), scenario.get("caseId"), scenario.get("serviceId"),
                scenario.get("name"), scenario.get("description"), source.get("route"), request.get("path"),
            )
        )
        scenario_terms = terms(scenario_blob)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for chunk in chunks:
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            document_scenario_id = str(metadata.get("scenarioId") or "")
            exact = bool(
                document_scenario_id
                and document_scenario_id.lower() in scenario_blob.lower()
            )
            overlap = len(scenario_terms & terms(str(chunk.get("text") or "")))
            score = (1.0 if exact else 0.0) + overlap / max(1, len(scenario_terms))
            if exact or overlap:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = [chunk for _, chunk in ranked[:3]]
        if not selected:
            enriched.append(scenario)
            continue
        next_scenario = dict(scenario)
        evidence = []
        for chunk in selected:
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            evidence.append(
                {
                    "documentId": chunk.get("documentId"),
                    "fileName": chunk.get("fileName"),
                    "chunkId": chunk.get("id"),
                    "evidenceRef": metadata.get("evidenceRef") or f"project_context:{chunk.get('documentId')}",
                    "kind": metadata.get("kind"),
                    "scenarioHint": metadata.get("scenarioHint"),
                    "requestCandidate": metadata.get("request"),
                    "responseCandidate": metadata.get("response"),
                    "text": str(chunk.get("text") or "")[:2000],
                }
            )
        next_scenario["projectContextEvidence"] = evidence
        next_scenario["supportingContext"] = {
            "status": "joined_candidate",
            "documents": [
                {key: item.get(key) for key in ("id", "fileName", "kind", "status", "summary")}
                for item in documents
            ],
            "guardrails": list(project_context.get("guardrails") or []),
            "note": "보조자료 후보입니다. 코드 Graph·DOM·API와 일치하는 내용만 실행 단계에 반영합니다.",
        }
        generation = dict(next_scenario.get("generationEvidence") or {})
        sources = list(generation.get("sourceTypes") or [])
        if any(item.get("kind") == "test_case_row" for item in evidence):
            sources.append("project_csv")
        if any(item.get("kind") in {"design_slide", "vlm_screen_observation"} for item in evidence):
            sources.append("design_ppt")
        generation["sourceTypes"] = list(dict.fromkeys([*sources, "project_supporting_context"]))
        generation["projectContextRefs"] = [item["evidenceRef"] for item in evidence]
        next_scenario["generationEvidence"] = generation
        enriched.append(next_scenario)
    return enriched


def scenario_signature(scenario: dict[str, Any]) -> str:
    """같은 화면·같은 요청·같은 단계 구성이면 같은 테스트다 (커버리지에 기여하지 않음)."""
    source = scenario.get("source") or {}
    request = scenario.get("request") or {}
    steps = [
        f"{str(step.get('action') or '')}:"
        f"{str((step.get('target') or {}).get('route') or (step.get('target') or {}).get('value') or '')}"
        for step in (scenario.get("steps") or [])
    ]
    return "|".join(
        [
            str(scenario.get("caseId") or ""),
            str(scenario.get("testType") or ""),
            str(source.get("route") or ""),
            f"{request.get('method') or ''} {request.get('path') or ''}",
            ">".join(steps),
        ]
    )


def dedupe_scenarios(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """중복 시나리오 제거 — 커버리지에 새 관측을 더하지 않는 케이스만 걷어낸다.

    같은 caseId·같은 화면·같은 요청·같은 단계 구성이면 뒤에 온 케이스를 버린다.
    남긴 케이스에는 무엇을 흡수했는지 `dedupe` 근거를 기록한다 (조용히 지우지 않는다).
    """
    kept: list[dict[str, Any]] = []
    by_signature: dict[str, dict[str, Any]] = {}
    for scenario in scenarios:
        signature = scenario_signature(scenario)
        winner = by_signature.get(signature)
        if winner is None:
            by_signature[signature] = scenario
            kept.append(scenario)
            continue
        absorbed = list(winner.get("dedupe", {}).get("absorbedScenarioIds") or [])
        absorbed.append(str(scenario.get("scenarioId") or ""))
        winner["dedupe"] = {
            "absorbedScenarioIds": absorbed,
            "signature": signature,
            "reason": "같은 화면·요청·단계 구성이라 관측이 겹칩니다",
        }
    return kept


def attach_runtime_discovery_evidence(
    scenario: dict[str, Any], graph: dict[str, Any]
) -> dict[str, Any]:
    """Join live DOM/screenshot observations to code-generated journey steps.

    Runtime discovery does not invent a journey.  It confirms which code-derived
    routes and safe CTA selectors were actually present in the running UI and keeps
    those artifacts on the generated scenario for later review/re-generation.
    """
    discovery = graph.get("runtimeDiscovery")
    if not isinstance(discovery, dict):
        return scenario
    pages = [item for item in (discovery.get("pages") or []) if isinstance(item, dict)]
    by_route = {str(item.get("route") or ""): item for item in pages if item.get("route")}
    current_route = str((scenario.get("source") or {}).get("route") or "")
    used_pages: dict[str, dict[str, Any]] = {}
    steps = list(scenario.get("steps") or [])
    for step in steps:
        target = step.get("target") if isinstance(step.get("target"), dict) else {}
        if target.get("route"):
            current_route = str(target["route"])
        page = by_route.get(current_route)
        if not page:
            continue
        used_pages[current_route] = page
        refs = list(step.get("evidenceRefs") or [])
        snapshot_path = page.get("snapshotPath")
        screenshot_path = page.get("screenshotPath")
        if snapshot_path:
            refs.append(f"runtime:dom:{current_route}:{snapshot_path}")
        if screenshot_path:
            refs.append(f"runtime:screenshot:{current_route}:{screenshot_path}")
        selector = str(target.get("value") or "")
        selector_group = {
            str(value) for value in (target.get("selectors") or []) if value
        }
        title_key = re.sub(r"[^a-z0-9가-힣]", "", str(step.get("title") or "").lower())
        interaction = next(
            (
                item
                for item in (page.get("safeInteractions") or [])
                if isinstance(item, dict)
                and item.get("observed") is True
                and (
                    str(item.get("selector") or "") == selector
                    or str(item.get("modalSelector") or "") in selector_group
                    or any(
                        re.sub(r"[^a-z0-9가-힣]", "", str(control.get("name") or "").lower())
                        and re.sub(r"[^a-z0-9가-힣]", "", str(control.get("name") or "").lower())
                        in title_key
                        for control in (item.get("domControls") or [])
                        if isinstance(control, dict)
                    )
                )
            ),
            None,
        )
        if interaction:
            target = {**target, "runtimeObserved": True}
            step["target"] = target
            observed_target = (
                selector
                or next(iter(selector_group), "")
                or str(interaction.get("modalSelector") or interaction.get("selector") or "")
            )
            refs.append(f"runtime:interaction:{current_route}:{observed_target}")
            if interaction.get("snapshotPath"):
                refs.append(f"runtime:dom:{current_route}:{interaction['snapshotPath']}")
            if interaction.get("screenshotPath"):
                refs.append(f"runtime:screenshot:{current_route}:{interaction['screenshotPath']}")
        step["evidenceRefs"] = list(dict.fromkeys(refs))

    enriched = dict(scenario)
    enriched["steps"] = steps
    enriched["generationEvidence"] = {
        "sourceTypes": ["frontend_code", "backend_contract", "live_dom", "screenshot"],
        "runtimeStatus": discovery.get("status"),
        "runtimeMode": discovery.get("mode"),
        "observedRoutes": sorted(used_pages),
        "screenshots": [
            str(page.get("screenshotPath"))
            for page in used_pages.values()
            if page.get("screenshotPath")
        ],
        "interactionScreenshots": [
            str(interaction.get("screenshotPath"))
            for page in used_pages.values()
            for interaction in (page.get("safeInteractions") or [])
            if isinstance(interaction, dict) and interaction.get("observed") and interaction.get("screenshotPath")
        ],
        "domSnapshots": [
            str(page.get("snapshotPath"))
            for page in used_pages.values()
            if page.get("snapshotPath")
        ],
        "interactionDomSnapshots": [
            str(interaction.get("snapshotPath"))
            for page in used_pages.values()
            for interaction in (page.get("safeInteractions") or [])
            if isinstance(interaction, dict) and interaction.get("observed") and interaction.get("snapshotPath")
        ],
        "backendContracts": list(discovery.get("backendContracts") or []),
        "guardrail": discovery.get("guardrail"),
    }
    case_analysis = enriched.get("caseAnalysis")
    if isinstance(case_analysis, dict) and current_route in by_route:
        case_analysis["runtimeDomControls"] = list(by_route[current_route].get("domControls") or [])
    source_refs = dict(enriched.get("sourceRefs") or {})
    source_refs["runtimeDiscovery"] = {
        "status": discovery.get("status"),
        "generatedAt": discovery.get("generatedAt"),
    }
    enriched["sourceRefs"] = source_refs
    return enriched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8") or "{}")
    try:
        graph = _load(payload.get("interactionGraph") or payload.get("interactionGraphPath"))
    except Exception as exc:  # noqa: BLE001
        print(f"failed to load graph: {exc}", file=sys.stderr)
        return 2

    raw_service = payload.get("serviceId")
    service_id = None if raw_service in (None, "", "customer-search") else str(raw_service)
    scenarios = generate_scenarios(
        graph,
        service_id=service_id,
        project_id=payload.get("projectId"),
        project_context=(payload.get("projectContext") if isinstance(payload.get("projectContext"), dict) else (payload.get("result") or {}).get("projectContext")),
    )

    project_context = (
        payload.get("projectContext")
        if isinstance(payload.get("projectContext"), dict)
        else (payload.get("result") or {}).get("projectContext")
    )

    artifact_path = payload.get("artifactPath")
    if artifact_path:
        out_art = Path(str(artifact_path)).expanduser().resolve()
        out_art.parent.mkdir(parents=True, exist_ok=True)
        out_art.write_text(
            json.dumps({"scenarios": scenarios}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    output = {
        "ok": True,
        "skill": "scenario_dsl",
        "tool": "generate_dsl",
        "serviceId": service_id or "multi",
        "scenarioCount": len(scenarios),
        "artifactPath": str(artifact_path) if artifact_path else None,
        "projectContext": project_context,
        "result": {"scenarios": scenarios, "serviceId": service_id or "multi", "projectContext": project_context},
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "count": len(scenarios)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
