#!/usr/bin/env python3
"""interaction_graph / compose_graph — build A→API→B graph from analyses+mapping (no LLM)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _load(src: Any) -> dict[str, Any]:
    if isinstance(src, dict):
        return src
    path = Path(str(src)).expanduser().resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def _ev(
    *,
    repo: str,
    commit: str | None,
    file: str | None,
    line: int | None,
    extractor: str,
) -> dict[str, Any]:
    return {
        "repositoryId": repo,
        "commitSha": commit or "unknown",
        "file": file or "missing_data",
        "startLine": int(line or 1),
        "endLine": int(line or 1),
        "extractor": extractor,
    }


def _node(
    nodes: dict[str, dict],
    *,
    nid: str,
    ntype: str,
    name: str,
    attributes: dict[str, Any],
    evidence: list[dict[str, Any]],
    confidence: float,
    verification: str = "static-confirmed",
) -> str:
    if nid in nodes:
        return nid
    nodes[nid] = {
        "id": nid,
        "type": ntype,
        "name": name,
        "attributes": attributes,
        "evidence": evidence,
        "confidence": confidence,
        "verificationStatus": verification,
    }
    return nid


def _canonical_field(*candidates: Any) -> str:
    """DOM 이름(customer-id / customer_id_input)을 계약 필드 이름(customerId)으로 정규화한다.

    추정이 아니라 표기 변환이다. Contract·DTO 필드와 join하려면 표기를 맞춰야 한다.
    """
    for candidate in candidates:
        raw = str(candidate or "").strip()
        if not raw:
            continue
        raw = raw.removesuffix("-input").removesuffix("_input").removesuffix("Input")
        parts = [p for p in raw.replace("_", "-").replace(".", "-").split("-") if p]
        if not parts:
            continue
        head, *rest = parts
        return head[:1].lower() + head[1:] + "".join(p[:1].upper() + p[1:] for p in rest)
    return ""


def _route_matches(pattern: str, route: str) -> bool:
    """`/customers/:param` 과 `/customers/:customerId` 처럼 파라미터 이름만 다른 경로를 맞춘다."""
    a = [seg for seg in str(pattern or "").split("/") if seg]
    b = [seg for seg in str(route or "").split("/") if seg]
    if len(a) != len(b) or not a:
        return False
    for left, right in zip(a, b):
        dynamic = left.startswith(":") or left.startswith("{")
        other_dynamic = right.startswith(":") or right.startswith("{")
        # 파라미터 자리끼리만 서로 맞춘다. `:param` 을 정적 세그먼트(search)에
        # 맞추면 A 화면과 B 화면이 뒤섞인다.
        if dynamic != other_dynamic:
            return False
        if dynamic:
            continue
        if left.lower() != right.lower():
            return False
    return True


def _path_params(path: str) -> list[str]:
    """Path template placeholders — deterministic parse, no inference."""
    return [seg[1:-1] for seg in path.split("/") if seg.startswith("{") and seg.endswith("}")]


def _dto_fields(dtos: Any, dto_name: Any) -> list[dict[str, Any]]:
    """Field list for a DTO name when the analyzer extracted one. Empty → missing_data."""
    if not dtos or not dto_name:
        return []
    wanted = str(dto_name)
    for dto in dtos:
        if not isinstance(dto, dict):
            continue
        if str(dto.get("name") or dto.get("dtoName") or "") != wanted:
            continue
        fields = dto.get("fields") or dto.get("properties") or []
        return [f for f in fields if isinstance(f, dict)]
    return []


def _edge(
    edges: list[dict],
    *,
    eid: str,
    frm: str,
    to: str,
    etype: str,
    confidence: float,
    evidence: list[dict[str, Any]],
    condition: str | None = None,
    data_mappings: list[dict] | None = None,
) -> None:
    # Edge ids derive from method+path, which collide when several controllers
    # expose the same endpoint. Ids must stay unique for rewire/PATCH and for
    # stable rendering keys.
    taken = {e["id"] for e in edges}
    if eid in taken:
        if any(
            e["id"] == eid and e["from"] == frm and e["to"] == to and e["type"] == etype
            for e in edges
        ):
            return
        suffix = 2
        while f"{eid}-{suffix}" in taken:
            suffix += 1
        eid = f"{eid}-{suffix}"
    edges.append(
        {
            "id": eid,
            "from": frm,
            "to": to,
            "type": etype,
            "condition": condition,
            "dataMappings": data_mappings or [],
            "confidence": confidence,
            "evidence": evidence,
        }
    )


def _is_probe_path(path: str) -> bool:
    p = (path or "").lower()
    return any(
        token in p
        for token in ("/health", "/healthy", "/ready", "/version", "/live", "/ping", "/actuator")
    )


def _safe_id(prefix: str, *parts: str) -> str:
    raw = "-".join(str(p) for p in parts if p)
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-").lower()
    return f"{prefix}-{cleaned[:72] or uuid4().hex[:8]}"


LOGIN_ROUTE_HINTS = ("login", "signin", "sign-in")


def build_auth_context(frontend: dict[str, Any], nodes: dict[str, dict]) -> dict[str, Any]:
    """세션 선행조건 판정 재료를 그래프에 싣는다 (D-015).

    전부 정적 분석 근거만 사용한다 — 추정한 경로·selector는 넣지 않고
    없으면 `missingData`로 남긴다.
    """
    screens = list(frontend.get("screens") or [])
    forms = list(frontend.get("actionForms") or [])
    markers = list(frontend.get("sessionMarkers") or [])

    login_screen = next(
        (
            s
            for s in screens
            if any(hint in str(s.get("route") or "").lower() for hint in LOGIN_ROUTE_HINTS)
            and any(
                str(i.get("type") or "").lower() == "password" for i in (s.get("inputs") or [])
            )
        ),
        None,
    )
    login_controls: dict[str, Any] = {}
    if login_screen:
        inputs = list(login_screen.get("inputs") or [])
        id_ctl = next(
            (
                i
                for i in inputs
                if str(i.get("type") or "").lower() in {"text", "email"}
                or "user" in str(i.get("field") or "").lower()
            ),
            None,
        )
        pw_ctl = next((i for i in inputs if str(i.get("type") or "").lower() == "password"), None)
        submit_ctl = next(
            (i for i in inputs if str(i.get("type") or "").lower() == "submit"), None
        )
        login_controls = {
            "idSelector": (id_ctl or {}).get("selector"),
            "passwordSelector": (pw_ctl or {}).get("selector"),
            "submitSelector": (submit_ctl or {}).get("selector"),
        }

    guarded = [
        {
            "route": str(s.get("route")),
            "methods": [str(m).upper() for m in (s.get("methods") or [])],
            "nodeId": next(
                (
                    nid
                    for nid, n in nodes.items()
                    if (n.get("attributes") or {}).get("route") == s.get("route")
                ),
                None,
            ),
            "evidence": s.get("authGuardEvidence"),
        }
        for s in screens
        if s.get("authGuarded")
    ]
    guarded_routes = [g["route"] for g in guarded]

    # 직접 URL 진입이 불가능한 경로 — GET이 허용되지 않으면 화면의 트리거를 눌러야 한다
    post_only = [
        {
            "route": str(s.get("route")),
            "methods": [str(m).upper() for m in (s.get("methods") or [])],
        }
        for s in screens
        if (s.get("methods") and "GET" not in [str(m).upper() for m in s["methods"]])
    ]
    post_only_routes = [p["route"] for p in post_only]

    action_triggers = [
        {
            "route": f.get("action"),
            "method": f.get("method"),
            "formSelector": f.get("formSelector"),
            "triggerSelector": f.get("triggerSelector"),
            "triggerLabel": f.get("triggerLabel"),
            "openerSelector": f.get("openerSelector"),
            "openerLabel": f.get("openerLabel"),
            "modalSelector": f.get("modalSelector"),
            "modalTitle": f.get("modalTitle"),
            "sourceRoute": f.get("sourceRoute"),
            "destinationRoute": f.get("destinationRoute"),
            "formControls": list(f.get("formControls") or [])[:12],
            "outputBindings": list(f.get("outputBindings") or [])[:12],
            "resultMessages": list(f.get("resultMessages") or [])[:8],
            "numericEffect": f.get("numericEffect"),
            "evidence": f.get("evidence"),
        }
        for f in forms
        if str(f.get("action") or "").split("?")[0] in set(guarded_routes) | set(post_only_routes)
    ]
    # 트리거가 어느 화면에서 눌리는지 — 마커와 같은 템플릿(공유 navigation)이면 인증 화면 어디서나 가능
    marker_selectors = [m.get("selector") for m in markers if m.get("selector")]

    missing: list[str] = []
    if not login_screen:
        missing.append("authContext.loginRoute")
    elif not all(login_controls.get(k) for k in ("idSelector", "passwordSelector", "submitSelector")):
        missing.append("authContext.loginControls")
    if not marker_selectors:
        missing.append("authContext.sessionMarkers")

    return {
        "loginRoute": (login_screen or {}).get("route"),
        "loginControls": login_controls,
        "authGuardedRoutes": guarded_routes,
        "authGuarded": guarded,
        "postOnlyRoutes": post_only_routes,
        "actionTriggers": action_triggers,
        "sessionMarkers": marker_selectors[:6],
        "sessionMarkerEvidence": markers[:6],
        "missingData": missing,
    }


def compose_graph(
    frontend: dict[str, Any],
    backend: dict[str, Any],
    mapping: dict[str, Any],
    *,
    project_id: str | None = None,
    repository_set_id: str | None = None,
    graph_id: str | None = None,
) -> dict[str, Any]:
    """Compose multi-flow graph from all evidenced screens/API calls/endpoints.

    customer-search is no longer the sole template — every non-probe BE endpoint
    and FE screen/apiCall becomes a node. Missing UI evidence stays unresolved.
    """
    fe_commit = frontend.get("commitSha") or "fe-unknown"
    be_commit = backend.get("commitSha") or "be-unknown"
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    unresolved: list[dict] = list(frontend.get("unresolved") or [])[:20]

    # --- screens ---
    screen_ids: dict[str, str] = {}
    # 분석기 산출물 id → 그래프 노드 id (FE bindings가 이 id로 연결을 알려준다)
    alias: dict[str, str] = {}
    for screen in frontend.get("screens") or []:
        route = str(screen.get("route") or "")
        if not route:
            continue
        nid = _safe_id("node-screen", route)
        ev = screen.get("evidence") or {}
        _node(
            nodes,
            nid=nid,
            ntype="screen",
            name=str(screen.get("name") or route),
            attributes={
                "route": route,
                "role": "screen",
                "inputs": list(screen.get("inputs") or [])[:12],
                "uiElements": list(screen.get("uiElements") or screen.get("inputs") or [])[:12],
                "targetFile": screen.get("targetFile") or (screen.get("evidence") or {}).get("file"),
                "template": screen.get("template"),
                "submitTestId": screen.get("submitTestId"),
                "navigationLinks": list(screen.get("navigationLinks") or [])[:12],
                "entryActions": list(screen.get("entryActions") or [])[:12],
                "actionForms": list(screen.get("actionForms") or [])[:8],
                "outputBindings": list(screen.get("outputBindings") or [])[:12],
                # 세션 선행조건 판정 근거 (D-015) — 허용 메서드·인증 게이트
                "methods": [str(m).upper() for m in (screen.get("methods") or [])],
                "authGuarded": bool(screen.get("authGuarded")),
                "authGuardEvidence": screen.get("authGuardEvidence"),
            },
            evidence=[
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "screen",
                )
            ],
            confidence=float(ev.get("confidence") if isinstance(ev.get("confidence"), (int, float)) else 0.85),
        )
        screen_ids[route] = nid
        if screen.get("id"):
            alias[str(screen["id"])] = nid

    # Evinced template navigation becomes screen → UI event → destination screen.
    # This is deliberately a second pass because every target screen id must exist.
    for screen in frontend.get("screens") or []:
        source_route = str(screen.get("route") or "")
        source_id = screen_ids.get(source_route)
        if not source_id:
            continue
        for link in screen.get("navigationLinks") or []:
            target_route = str(link.get("targetRoute") or "")
            selector = str(link.get("selector") or "")
            target_id = screen_ids.get(target_route)
            if not target_id or not selector:
                continue
            ev = link.get("evidence") or {}
            event_id = _safe_id("node-ui-event", source_route, selector, target_route)
            evidence = [
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "jinja-navigation-link",
                )
            ]
            _node(
                nodes,
                nid=event_id,
                ntype="event",
                name=str(link.get("label") or "화면 이동 버튼"),
                attributes={
                    "selector": selector,
                    "sourceRoute": source_route,
                    "targetRoute": target_route,
                    "role": "navigation-trigger",
                },
                evidence=evidence,
                confidence=float(ev.get("confidence") or 0.95),
            )
            _edge(
                edges,
                eid=_safe_id("edge-screen-event", source_route, selector),
                frm=source_id,
                to=event_id,
                etype="triggers",
                confidence=0.95,
                evidence=evidence,
                condition="happy_path",
            )
            _edge(
                edges,
                eid=_safe_id("edge-event-screen", selector, target_route),
                frm=event_id,
                to=target_id,
                etype="navigates_to",
                confidence=0.95,
                evidence=evidence,
                condition="happy_path",
            )

    # --- FE API calls ---
    call_ids: dict[str, str] = {}
    for call in frontend.get("apiCalls") or []:
        method = str(call.get("method") or "GET").upper()
        path = str(call.get("normalizedPath") or call.get("path") or "")
        if not path or _is_probe_path(path):
            continue
        nid = _safe_id("node-fe-api", method, path)
        ev = call.get("evidence") or {}
        _node(
            nodes,
            nid=nid,
            ntype="frontend_api_call",
            name=f"{method} {path}",
            attributes={
                "method": method,
                "path": path,
                "normalizedPath": path,
                "screenRoute": call.get("screenRoute") or call.get("fromRoute"),
                "triggerTestId": call.get("triggerTestId"),
                "pathParams": _path_params(path),
                "requestFields": list(call.get("requestFields") or call.get("payloadFields") or []),
            },
            evidence=[
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "api-call",
                )
            ],
            confidence=float(ev.get("confidence") if isinstance(ev.get("confidence"), (int, float)) else 0.8),
        )
        call_ids[f"{method} {path}"] = nid
        if call.get("id"):
            alias[str(call["id"])] = nid
        from_route = call.get("screenRoute") or call.get("fromRoute")
        if from_route and from_route in screen_ids:
            _edge(
                edges,
                eid=_safe_id("edge-screen-call", from_route, method, path),
                frm=screen_ids[from_route],
                to=nid,
                etype="triggers",
                confidence=0.8,
                evidence=nodes[nid]["evidence"],
                condition="happy_path",
            )

    # --- BE endpoints ---
    ep_ids: dict[str, str] = {}
    business_eps: list[dict[str, Any]] = []
    for ep in backend.get("endpoints") or []:
        method = str(ep.get("method") or "GET").upper()
        path = str(ep.get("path") or "")
        if not path:
            continue
        if _is_probe_path(path):
            continue
        business_eps.append(ep)
        nid = _safe_id("node-be", method, path, ep.get("id") or "")
        ev = ep.get("evidence") or {}
        _node(
            nodes,
            nid=nid,
            ntype="backend_endpoint",
            name=f"{method} {path}",
            attributes={
                "method": method,
                "path": path,
                "handler": ep.get("handler") or ep.get("controller"),
                "endpointId": ep.get("id"),
                "controller": ep.get("controller"),
                "handlerMethod": ep.get("handlerMethod"),
                "pathParams": _path_params(path),
                "requestDtoName": ep.get("requestDto") or ep.get("requestType"),
                "responseDtoName": ep.get("responseDto") or ep.get("responseType"),
                "statusCandidates": list(ep.get("statusCandidates") or []),
                "serviceCalls": list(ep.get("serviceCalls") or []),
            },
            evidence=[
                _ev(
                    repo="backend",
                    commit=be_commit,
                    file=ev.get("file") or ep.get("file"),
                    line=ev.get("line") or ep.get("line"),
                    extractor=ev.get("extractor") or "spring-endpoint",
                )
            ],
            confidence=0.9,
        )
        ep_ids[f"{method} {path}"] = nid
        # request/response dto shells when present
        req_name = ep.get("requestDto") or ep.get("requestType")
        resp_name = ep.get("responseDto") or ep.get("responseType")
        if req_name:
            rid = _safe_id("node-req", method, path)
            _node(
                nodes,
                nid=rid,
                ntype="request_dto",
                name=str(req_name),
                attributes={
                    "endpoint": path,
                    "method": method,
                    "dtoName": str(req_name),
                    "fields": _dto_fields(backend.get("requestDtos"), req_name),
                },
                evidence=nodes[nid]["evidence"],
                confidence=0.75,
            )
            _edge(
                edges,
                eid=_safe_id("edge-be-req", method, path),
                frm=nid,
                to=rid,
                etype="contains",
                confidence=0.75,
                evidence=nodes[nid]["evidence"],
            )
        if resp_name:
            sid = _safe_id("node-resp", method, path)
            _node(
                nodes,
                nid=sid,
                ntype="response_dto",
                name=str(resp_name),
                attributes={
                    "endpoint": path,
                    "method": method,
                    "dtoName": str(resp_name),
                    "fields": _dto_fields(backend.get("responseDtos"), resp_name),
                },
                evidence=nodes[nid]["evidence"],
                confidence=0.75,
            )
            _edge(
                edges,
                eid=_safe_id("edge-be-resp", method, path),
                frm=nid,
                to=sid,
                etype="contains",
                confidence=0.75,
                evidence=nodes[nid]["evidence"],
            )

    # --- UI 체인 (screen → input → event → validation → api) ---
    # 바이블 Phase 05의 노드 체인이다. FE 분석기가 이미 inputs/events/validations/
    # routeTransitions/bindings를 근거와 함께 뽑아두므로 발명 없이 그대로 노드화한다.
    def _screen_for(file: str | None) -> str | None:
        """같은 소스 파일에서 나온 화면 노드에 붙인다 (근거 파일 일치만 사용)."""
        if file:
            for nid_ in screen_ids.values():
                for ev_ in nodes[nid_]["evidence"]:
                    if ev_.get("file") == file:
                        return nid_
        return next(iter(screen_ids.values()), None)

    input_ids: dict[str, str] = {}
    for item in (frontend.get("inputs") or [])[:60]:
        kind = str(item.get("kind") or "input").lower()
        if kind in {"form"}:
            continue
        ev = item.get("evidence") or {}
        field = _canonical_field(item.get("name"), item.get("testId"), item.get("label"))
        if not field:
            continue
        nid = _safe_id("node-input", field, str(ev.get("line") or ""))
        is_trigger = kind == "button" or str((item.get("constraints") or {}).get("type") or "") == "submit"
        _node(
            nodes,
            nid=nid,
            ntype="event" if is_trigger else "input",
            name=field,
            attributes={
                "domName": item.get("name"),
                "testId": item.get("testId"),
                "label": item.get("label"),
                "kind": kind,
                "required": bool(item.get("required")),
                "constraints": item.get("constraints") or {},
            },
            evidence=[
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "jsx-input",
                )
            ],
            confidence=float(ev.get("confidence") if isinstance(ev.get("confidence"), (int, float)) else 0.8),
        )
        input_ids[str(item.get("id") or nid)] = nid
        alias[str(item.get("id") or nid)] = nid
        owner = _screen_for(ev.get("file"))
        if owner:
            _edge(
                edges,
                eid=_safe_id("edge-screen-input", owner, field),
                frm=owner,
                to=nid,
                etype="contains",
                confidence=0.8,
                evidence=nodes[nid]["evidence"],
            )
            # 화면 노드도 입력 목록을 갖고 있어야 실행 단계(fill)를 만들 수 있다
            attrs = nodes[owner]["attributes"]
            declared = list(attrs.get("inputs") or [])
            if not any((d or {}).get("name") == field for d in declared if isinstance(d, dict)):
                declared.append(
                    {
                        "name": field,
                        "kind": kind,
                        "testId": item.get("testId"),
                        "required": bool(item.get("required")),
                    }
                )
            attrs["inputs"] = declared[:20]
            if is_trigger and item.get("testId") and not attrs.get("submitTestId"):
                attrs["submitTestId"] = item.get("testId")

    event_ids: dict[str, str] = {}
    for item in (frontend.get("events") or [])[:40]:
        ev = item.get("evidence") or {}
        label = str(item.get("event") or "event")
        nid = _safe_id("node-event", label, str(ev.get("line") or ""))
        _node(
            nodes,
            nid=nid,
            ntype="event",
            name=label,
            attributes={
                "handlerName": item.get("handlerName"),
                "handlerResolved": bool(item.get("handlerResolved")),
            },
            evidence=[
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "jsx-event",
                )
            ],
            confidence=float(ev.get("confidence") if isinstance(ev.get("confidence"), (int, float)) else 0.8),
        )
        event_ids[str(item.get("id") or nid)] = nid
        alias[str(item.get("id") or nid)] = nid
        owner = _screen_for(ev.get("file"))
        if owner:
            _edge(
                edges,
                eid=_safe_id("edge-screen-event", owner, label, str(ev.get("line") or "")),
                frm=owner,
                to=nid,
                etype="contains",
                confidence=0.75,
                evidence=nodes[nid]["evidence"],
            )
        # 같은 파일의 입력 → 이벤트 (사용자가 값을 넣고 이 이벤트를 일으킨다)
        for src_id, src_nid in input_ids.items():
            if nodes[src_nid]["type"] != "input":
                continue
            if nodes[src_nid]["evidence"][0].get("file") != ev.get("file"):
                continue
            _edge(
                edges,
                eid=_safe_id("edge-input-event", src_nid, nid),
                frm=src_nid,
                to=nid,
                etype="triggers",
                confidence=0.7,
                evidence=nodes[nid]["evidence"],
            )

    validation_ids: dict[str, str] = {}
    for item in (frontend.get("validations") or [])[:40]:
        ev = item.get("evidence") or {}
        field = _canonical_field(item.get("field")) or str(item.get("field") or "validation")
        nid = _safe_id("node-validation", field, str(item.get("kind") or ""))
        _node(
            nodes,
            nid=nid,
            ntype="validation",
            name=field,
            attributes={
                "field": field,
                "kind": item.get("kind"),
                "expression": item.get("expression"),
                "required": bool(item.get("required")),
            },
            evidence=[
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "validation",
                )
            ],
            confidence=float(ev.get("confidence") if isinstance(ev.get("confidence"), (int, float)) else 0.8),
        )
        validation_ids[str(item.get("id") or nid)] = nid
        alias[str(item.get("id") or nid)] = nid
        # 검증 실패 분기 — 화면에 머문다
        owner = _screen_for(nodes[nid]["evidence"][0].get("file")) or next(iter(screen_ids.values()), None)
        if owner:
            _edge(
                edges,
                eid=_safe_id("edge-validation-block", nid, owner),
                frm=nid,
                to=owner,
                etype="branches_to",
                confidence=0.7,
                evidence=nodes[nid]["evidence"],
                condition="validation_failed",
            )
        # 통과하면 API 호출로 이어진다
        for call_nid in call_ids.values():
            _edge(
                edges,
                eid=_safe_id("edge-validation-call", nid, call_nid),
                frm=nid,
                to=call_nid,
                etype="triggers",
                confidence=0.7,
                evidence=nodes[nid]["evidence"],
                condition="happy_path",
            )
            break

    transition_ids: dict[str, str] = {}
    for item in (frontend.get("routeTransitions") or [])[:40]:
        ev = item.get("evidence") or {}
        to_route = str(item.get("to") or "")
        if not to_route:
            continue
        nid = _safe_id("node-transition", to_route, str(item.get("kind") or ""))
        _node(
            nodes,
            nid=nid,
            ntype="route_transition",
            name=to_route,
            attributes={
                "to": to_route,
                "kind": item.get("kind"),
                "fromHint": item.get("fromHint"),
            },
            evidence=[
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "route-transition",
                )
            ],
            confidence=float(ev.get("confidence") if isinstance(ev.get("confidence"), (int, float)) else 0.8),
        )
        transition_ids[str(item.get("id") or nid)] = nid
        alias[str(item.get("id") or nid)] = nid
        target = next(
            (snid for sroute, snid in screen_ids.items() if _route_matches(to_route, sroute)),
            None,
        )
        if target:
            _edge(
                edges,
                eid=_safe_id("edge-transition-screen", nid, target),
                frm=nid,
                to=target,
                etype="navigates_to",
                confidence=0.8,
                evidence=nodes[nid]["evidence"],
                condition="happy_path",
            )

    # FE 분석기가 알려준 실제 연결 (event→api / event→route / validation→input)
    relation_edge = {
        "event-triggers-api": ("triggers", "happy_path"),
        "event-triggers-route": ("navigates_to", "happy_path"),
        "validation-on-input": ("validates", None),
    }
    for link in (frontend.get("bindings") or [])[:120]:
        etype_cond = relation_edge.get(str(link.get("relation") or ""))
        if not etype_cond:
            continue
        frm = alias.get(str(link.get("from") or ""))
        to = alias.get(str(link.get("to") or ""))
        if not frm or not to:
            continue
        if str(link.get("relation")) == "validation-on-input":
            frm, to = to, frm  # 입력 → 검증 방향으로 읽는다
        ev = link.get("evidence") or {}
        _edge(
            edges,
            eid=_safe_id("edge-fe-bind", frm, to, str(link.get("relation") or "")),
            frm=frm,
            to=to,
            etype=etype_cond[0],
            confidence=float(ev.get("confidence") if isinstance(ev.get("confidence"), (int, float)) else 0.7),
            evidence=[
                _ev(
                    repo="frontend",
                    commit=fe_commit,
                    file=ev.get("file"),
                    line=ev.get("line"),
                    extractor=ev.get("extractor") or "binding",
                )
            ],
            condition=etype_cond[1],
        )

    # --- BE service 호출 + 응답 바인딩 ---
    for ep in business_eps[:24]:
        method = str(ep.get("method") or "GET").upper()
        path = str(ep.get("path") or "")
        be_nid = ep_ids.get(f"{method} {path}")
        if not be_nid:
            continue
        for svc in (ep.get("serviceCalls") or [])[:6]:
            sid = _safe_id("node-service", str(svc))
            _node(
                nodes,
                nid=sid,
                ntype="service",
                name=str(svc),
                attributes={"endpoint": path, "method": method, "call": str(svc)},
                evidence=nodes[be_nid]["evidence"],
                confidence=0.8,
            )
            _edge(
                edges,
                eid=_safe_id("edge-be-service", method, path, str(svc)),
                frm=be_nid,
                to=sid,
                etype="calls",
                confidence=0.8,
                evidence=nodes[be_nid]["evidence"],
            )
        # 응답 DTO 필드 → B 화면 바인딩
        resp_name = ep.get("responseDto") or ep.get("responseType")
        resp_nid = next(
            (
                n["id"]
                for n in nodes.values()
                if n["type"] == "response_dto"
                and (n["attributes"].get("endpoint") == path)
                and (n["attributes"].get("method") == method)
            ),
            None,
        )
        target_screen = None
        for tnid in transition_ids.values():
            for edge in edges:
                if edge["from"] == tnid and edge["type"] == "navigates_to":
                    target_screen = edge["to"]
                    break
            if target_screen:
                break
        for field in _dto_fields(backend.get("responseDtos"), resp_name)[:12]:
            fname = str(field.get("jsonName") or field.get("name") or "")
            if not fname:
                continue
            bid = _safe_id("node-binding", path, fname)
            _node(
                nodes,
                nid=bid,
                ntype="binding",
                name=fname,
                attributes={
                    "field": fname,
                    "type": field.get("type"),
                    "endpoint": path,
                    "targetScreen": (nodes[target_screen]["attributes"].get("route") if target_screen else None),
                },
                evidence=nodes[be_nid]["evidence"],
                confidence=0.7,
                verification="inferred",
            )
            if resp_nid:
                _edge(
                    edges,
                    eid=_safe_id("edge-resp-binding", path, fname),
                    frm=resp_nid,
                    to=bid,
                    etype="binds_to",
                    confidence=0.7,
                    evidence=nodes[be_nid]["evidence"],
                    data_mappings=[{"from": f"{resp_name}.{fname}", "to": f"screen.{fname}"}],
                )
            if target_screen:
                _edge(
                    edges,
                    eid=_safe_id("edge-binding-screen", path, fname),
                    frm=bid,
                    to=target_screen,
                    etype="binds_to",
                    confidence=0.65,
                    evidence=nodes[be_nid]["evidence"],
                    condition="happy_path",
                )
        # 실패 분기 — 상태 후보가 있으면 A 화면으로 되돌아온다
        if any("NOT_FOUND" in str(s).upper() for s in (ep.get("statusCandidates") or [])):
            back = next(iter(screen_ids.values()), None)
            if back:
                _edge(
                    edges,
                    eid=_safe_id("edge-notfound", method, path),
                    frm=be_nid,
                    to=back,
                    etype="returns",
                    confidence=0.7,
                    evidence=nodes[be_nid]["evidence"],
                    condition="customer_not_found",
                )

    # --- confirmed mappings ---
    confirmed_count = 0
    for row in mapping.get("mappings") or []:
        if row.get("status") != "confirmed":
            continue
        method = str(row.get("method") or "GET").upper()
        path = str(row.get("normalizedPath") or row.get("path") or "")
        if not path:
            continue
        confirmed_count += 1
        fe_nid = call_ids.get(f"{method} {path}")
        be_nid = ep_ids.get(f"{method} {path}")
        if not be_nid and row.get("backendEndpointId"):
            for key, nid in ep_ids.items():
                if row["backendEndpointId"] in key or row["backendEndpointId"] in (
                    nodes[nid].get("attributes", {}).get("endpointId") or ""
                ):
                    be_nid = nid
                    break
        if fe_nid and be_nid:
            _edge(
                edges,
                eid=_safe_id("edge-map", method, path),
                frm=fe_nid,
                to=be_nid,
                etype="calls",
                confidence=0.9,
                evidence=nodes[be_nid]["evidence"],
                condition="happy_path",
            )
    if confirmed_count == 0 and business_eps:
        unresolved.append(
            {
                "kind": "missing_mapping",
                "symbol": "confirmed_mappings",
                "reason": "no confirmed FE↔BE mappings — BE endpoints kept as draft flows",
            }
        )
    if not screen_ids:
        unresolved.append(
            {
                "kind": "missing_screen",
                "symbol": "*",
                "reason": "FE screens empty — Jinja/Flask routes may need FE extractor",
            }
        )

    # primary path: screen → FE call → BE → dto → binding (first evidenced business flow)
    primary_path: list[str] = []
    branches: list[dict[str, str]] = [{"id": "happy_path", "label": "정상 경로", "condition": "happy_path"}]
    seen_branch_ids: set[str] = {"happy_path"}
    for idx, ep in enumerate(business_eps[:24]):
        method = str(ep.get("method") or "GET").upper()
        path = str(ep.get("path") or "")
        key = f"{method} {path}"
        be_nid = ep_ids.get(key)
        fe_nid = call_ids.get(key)
        if not be_nid:
            continue
        branch_id = _safe_id("flow", method, path, str(idx))
        # Guarantee uniqueness even if path collapses (e.g. post--transactions)
        if branch_id in seen_branch_ids:
            branch_id = f"{branch_id}-{idx}"
        seen_branch_ids.add(branch_id)
        branches.append(
            {
                "id": branch_id,
                "label": key,
                "condition": branch_id,
            }
        )
        if not primary_path:
            # Prefer a screen that matches path tokens
            screen_nid = None
            hint = path.lower()
            for route, nid in screen_ids.items():
                r = route.lower()
                if any(
                    tok in hint and tok in r
                    for tok in (
                        "login",
                        "deposit",
                        "payment",
                        "home",
                        "signup",
                        "balance",
                        "transaction",
                        "customer",
                        "search",
                    )
                ):
                    screen_nid = nid
                    break
            if not screen_nid and screen_ids:
                screen_nid = next(iter(screen_ids.values()))
            if screen_nid:
                primary_path.append(screen_nid)
            if fe_nid:
                primary_path.append(fe_nid)
            primary_path.append(be_nid)
            for child_type in ("request_dto", "response_dto"):
                for n in nodes.values():
                    if n.get("type") == child_type and (n.get("attributes") or {}).get("endpoint") == path:
                        if (n.get("attributes") or {}).get("method") == method:
                            primary_path.append(n["id"])
            for n in nodes.values():
                if n.get("type") == "binding" and n["id"] not in primary_path:
                    primary_path.append(n["id"])
                    if len([x for x in primary_path if nodes.get(x, {}).get("type") == "binding"]) >= 2:
                        break

    # If customer-search artifacts exist, still attach as one branch (compat)
    if "/customers/search" in screen_ids or "POST /api/customers/search" in call_ids:
        compat_id = "customer_search"
        if compat_id not in seen_branch_ids:
            seen_branch_ids.add(compat_id)
            branches.append(
                {
                    "id": compat_id,
                    "label": "고객 조회",
                    "condition": compat_id,
                }
            )

    # Compat shim: keep old node id variables unused by continuing into legacy
    # block only when multi-graph produced nothing — fall through below.
    if nodes:
        gid = graph_id or f"IG-{uuid4().hex[:12]}"
        return {
            "schemaVersion": "interaction-graph/v1",
            "graphId": gid,
            "projectId": project_id,
            "repositorySetId": repository_set_id or "RS-unknown",
            "version": "1",
            "commitRefs": {"frontend": fe_commit, "backend": be_commit},
            "nodes": list(nodes.values()),
            "edges": edges,
            "authContext": build_auth_context(frontend, nodes),
            "unresolved": unresolved,
            "primaryPath": primary_path,
            "branches": branches,
            "serviceId": "multi",
            "figmaRef": {
                "fileKey": "qpZeClozlSVQd6j8Od8P9x",
                "kitNodeId": "0:1",
                "exampleNodeId": "1:319",
                "screenFormNodeId": "1:368",
            },
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    # Empty evidence — still return a valid graph shell (no invented customer-search)
    gid = graph_id or f"IG-{uuid4().hex[:12]}"
    return {
        "schemaVersion": "interaction-graph/v1",
        "graphId": gid,
        "projectId": project_id,
        "repositorySetId": repository_set_id or "RS-unknown",
        "version": "1",
        "commitRefs": {"frontend": fe_commit, "backend": be_commit},
        "nodes": [],
        "edges": [],
        "authContext": build_auth_context(frontend, {}),
        "unresolved": unresolved
        + [{"kind": "empty_graph", "symbol": "*", "reason": "no screens/apiCalls/endpoints"}],
        "primaryPath": [],
        "branches": [{"id": "happy_path", "label": "정상 경로", "condition": "happy_path"}],
        "serviceId": "multi",
        "figmaRef": {
            "fileKey": "qpZeClozlSVQd6j8Od8P9x",
            "kitNodeId": "0:1",
            "exampleNodeId": "1:319",
            "screenFormNodeId": "1:368",
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }



def find_paths(graph: dict[str, Any], from_id: str, to_id: str, *, limit: int = 20) -> list[list[str]]:
    adj: dict[str, list[str]] = {}
    for edge in graph.get("edges") or []:
        adj.setdefault(edge["from"], []).append(edge["to"])
    results: list[list[str]] = []

    def dfs(node: str, path: list[str], seen: set[str]) -> None:
        if len(results) >= limit:
            return
        if node == to_id:
            results.append(path[:])
            return
        for nxt in adj.get(node, []):
            if nxt in seen:
                continue
            seen.add(nxt)
            path.append(nxt)
            dfs(nxt, path, seen)
            path.pop()
            seen.remove(nxt)

    dfs(from_id, [from_id], {from_id})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8") or "{}")
    try:
        frontend = _load(payload.get("frontendAnalysis") or payload.get("frontendAnalysisPath"))
        backend = _load(payload.get("backendAnalysis") or payload.get("backendAnalysisPath"))
        mapping = _load(payload.get("apiMapping") or payload.get("apiMappingPath"))
    except Exception as exc:  # noqa: BLE001
        print(f"failed to load inputs: {exc}", file=sys.stderr)
        return 2

    graph = compose_graph(
        frontend,
        backend,
        mapping,
        project_id=payload.get("projectId"),
        repository_set_id=payload.get("repositorySetId"),
        graph_id=payload.get("graphId"),
    )

    artifact_path = payload.get("artifactPath")
    if artifact_path:
        out_art = Path(str(artifact_path)).expanduser().resolve()
        out_art.parent.mkdir(parents=True, exist_ok=True)
        out_art.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
        graph["artifactPath"] = str(out_art)

    output = {
        "ok": True,
        "skill": "interaction_graph",
        "tool": "compose_graph",
        "graphId": graph["graphId"],
        "artifactPath": graph.get("artifactPath"),
        "nodeCount": len(graph["nodes"]),
        "edgeCount": len(graph["edges"]),
        "result": graph,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "graphId": graph["graphId"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
