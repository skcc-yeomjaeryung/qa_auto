"""Read-only runtime screen discovery for evidence-grounded scenario generation.

The generator already has FE templates and BE contracts.  This probe adds what the
running application actually exposes: accessible DOM controls and screenshots.  It
may establish a registered login session, but it never submits a business form.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.repository_models import utc_now
from app.skills.browser_execute.script.execute_run import (
    _run_cli,
    _wait_url_contains,
    parse_dom_controls,
    route_url,
)


def _visible_signals(snapshot: str) -> list[str]:
    signals: list[str] = []
    for line in (snapshot or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        match = re.search(r'^-\s*(?:heading|button|link|dialog|combobox)\s+"([^"]+)"', stripped)
        if match and match.group(1) not in signals:
            signals.append(match.group(1)[:120])
        if len(signals) >= 40:
            break
    return signals


def _public_controls(snapshot: str) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for item in parse_dom_controls(snapshot):
        # Never retain a currentValue: a login id or other personal value may be in it.
        controls.append(
            {
                "role": item.get("role"),
                "name": item.get("name") or "(접근성 이름 없음)",
                "ref": item.get("ref"),
            }
        )
    return controls


def _routes(graph: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    auth = graph.get("authContext") if isinstance(graph.get("authContext"), dict) else {}
    post_only = {str(route) for route in (auth.get("postOnlyRoutes") or []) if route}
    login = str(auth.get("loginRoute") or "")
    if login:
        ordered.append(login)
    screens = [
        node
        for node in (graph.get("nodes") or [])
        if isinstance(node, dict) and node.get("type") == "screen"
    ]
    screens.sort(
        key=lambda node: 0
        if ((node.get("attributes") or {}).get("actionForms") or [])
        else 1
    )
    for node in screens:
        attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        route = str(attrs.get("route") or "")
        methods = {str(method).upper() for method in (attrs.get("methods") or []) if method}
        if route in post_only or (methods and "GET" not in methods):
            continue
        if route and route not in ordered:
            ordered.append(route)
    return ordered[:8]


def _screen_by_route(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict) or node.get("type") != "screen":
            continue
        attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        route = str(attrs.get("route") or "")
        if route:
            out[route] = node
    return out


def _backend_contracts(graph: dict[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict) or node.get("type") not in {
            "frontend_api_call",
            "backend_endpoint",
        }:
            continue
        attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        method = attrs.get("method") or attrs.get("httpMethod")
        path = attrs.get("normalizedPath") or attrs.get("path") or attrs.get("endpoint")
        if method or path:
            contracts.append(
                {
                    "nodeId": node.get("id"),
                    "method": method,
                    "path": path,
                    "requestFields": list(attrs.get("requestFields") or []),
                    "responseBindings": list(attrs.get("responseBindings") or []),
                }
            )
    return contracts[:40]


def discover_runtime_screens(
    *,
    graph_id: str,
    graph: dict[str, Any],
    base_url: str | None,
    connection: dict[str, Any] | None,
    artifact_dir: Path,
) -> dict[str, Any]:
    """Collect live screen evidence without executing a business transaction."""
    if not base_url:
        return {
            "status": "missing_data",
            "reason": "active frontendBaseUrl missing",
            "pages": [],
            "backendContracts": _backend_contracts(graph),
        }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    session = f"discover-{re.sub(r'[^a-zA-Z0-9]', '', graph_id)[-12:]}-{uuid4().hex[:6]}"
    pages: list[dict[str, Any]] = []
    missing: list[str] = []
    connected = dict(connection or {})
    auth = graph.get("authContext") if isinstance(graph.get("authContext"), dict) else {}
    login_controls = auth.get("loginControls") if isinstance(auth.get("loginControls"), dict) else {}
    logged_in = False
    screens = _screen_by_route(graph)

    def observe(route: str, *, suffix: str = "screen") -> tuple[str, dict[str, Any] | None]:
        index = len(pages) + 1
        opened = _run_cli(["open", route_url(base_url, route)], session=session, timeout=30)
        if not opened.get("ok"):
            missing.append(f"open:{route}")
            return "", None
        snap = _run_cli(["snapshot", "-i"], session=session, timeout=20)
        snapshot = str(snap.get("stdout") or "") if snap.get("ok") else ""
        snapshot_path = artifact_dir / f"{index:02d}-{suffix}.snapshot.txt"
        screenshot_path = artifact_dir / f"{index:02d}-{suffix}.png"
        if snapshot:
            snapshot_path.write_text(snapshot, encoding="utf-8")
        else:
            missing.append(f"snapshot:{route}")
        shot = _run_cli(["screenshot", str(screenshot_path)], session=session, timeout=20)
        if not shot.get("ok") or not screenshot_path.is_file():
            missing.append(f"screenshot:{route}")
        page = {
            "route": route,
            "url": route_url(base_url, route),
            "snapshotPath": str(snapshot_path) if snapshot_path.is_file() else None,
            "screenshotPath": str(screenshot_path) if screenshot_path.is_file() else None,
            "domControls": _public_controls(snapshot),
            "visibleSignals": _visible_signals(snapshot),
            "safeInteractions": [],
        }
        pages.append(page)
        return snapshot, page

    try:
        routes = _routes(graph)
        login_route = str(auth.get("loginRoute") or "")
        if login_route and login_route in routes:
            _snapshot, login_page = observe(login_route, suffix="login")
            login_id = connected.get("loginId")
            login_password = connected.get("loginPassword")
            id_selector = login_controls.get("idSelector")
            password_selector = login_controls.get("passwordSelector")
            submit_selector = login_controls.get("submitSelector")
            if login_id and login_password and id_selector and password_selector and submit_selector:
                filled_id = _run_cli(["fill", str(id_selector), str(login_id)], session=session, timeout=15)
                filled_pw = _run_cli(["fill", str(password_selector), str(login_password)], session=session, timeout=15)
                submitted = _run_cli(["click", str(submit_selector)], session=session, timeout=20)
                destination = str(auth.get("postLoginRoute") or auth.get("authenticatedRoute") or "/home")
                arrived = (
                    _wait_url_contains(session, destination, timeout_s=15)
                    if submitted.get("ok")
                    else {"ok": False}
                )
                logged_in = bool(
                    filled_id.get("ok")
                    and filled_pw.get("ok")
                    and submitted.get("ok")
                    and arrived.get("ok")
                )
                if login_page is not None:
                    login_page["safeInteractions"].append(
                        {
                            "selector": submit_selector,
                            "action": "login_with_registered_account",
                            "observed": logged_in,
                        }
                    )
                if not logged_in:
                    missing.append("login_session_not_established")
            else:
                missing.append("registered_login_account")

        for route in routes:
            if route == login_route:
                continue
            guarded = {str(value) for value in (auth.get("authGuardedRoutes") or [])}
            if route in guarded and not logged_in:
                missing.append(f"authenticated_route:{route}")
                continue
            snapshot, page = observe(route)
            if not page:
                continue
            screen = screens.get(route) or {}
            attrs = screen.get("attributes") if isinstance(screen.get("attributes"), dict) else {}
            for form_index, form in enumerate(attrs.get("actionForms") or []):
                if not isinstance(form, dict) or not form.get("openerSelector"):
                    continue
                selector = str(form["openerSelector"])
                clicked = _run_cli(["click", selector], session=session, timeout=15)
                modal_title = str(form.get("modalTitle") or "")
                appeared = (
                    _run_cli(["wait", "--text", modal_title], session=session, timeout=12)
                    if clicked.get("ok") and modal_title
                    else clicked
                )
                interaction = {
                    "selector": selector,
                    "label": form.get("openerLabel"),
                    "modalSelector": form.get("modalSelector"),
                    "modalTitle": form.get("modalTitle"),
                    "action": "open_non_submit_ui",
                    "observed": bool(clicked.get("ok") and appeared.get("ok")),
                }
                if interaction["observed"]:
                    snap = _run_cli(["snapshot", "-i"], session=session, timeout=20)
                    modal_snapshot = str(snap.get("stdout") or "") if snap.get("ok") else ""
                    modal_path = artifact_dir / f"{len(pages):02d}-modal-{form_index + 1}.snapshot.txt"
                    modal_shot = artifact_dir / f"{len(pages):02d}-modal-{form_index + 1}.png"
                    if modal_snapshot:
                        modal_path.write_text(modal_snapshot, encoding="utf-8")
                        interaction["domControls"] = _public_controls(modal_snapshot)
                        interaction["visibleSignals"] = _visible_signals(modal_snapshot)
                        interaction["snapshotPath"] = str(modal_path)
                    shot = _run_cli(["screenshot", str(modal_shot)], session=session, timeout=20)
                    if shot.get("ok") and modal_shot.is_file():
                        interaction["screenshotPath"] = str(modal_shot)
                page["safeInteractions"].append(interaction)
                # Reset the read-only screen before observing the next CTA.  This is a
                # GET navigation, not a business form submit.
                _run_cli(["open", route_url(base_url, route)], session=session, timeout=20)
    finally:
        _run_cli(["close"], session=session, timeout=15)

    result = {
        "status": "complete" if pages and not missing else "partial" if pages else "missing_data",
        "mode": "agent-browser-read-only",
        "graphId": graph_id,
        "loggedInWithRegisteredAccount": logged_in,
        "pages": pages,
        "backendContracts": _backend_contracts(graph),
        "missingData": missing,
        "generatedAt": utc_now().isoformat(),
        "guardrail": "business form submit not executed",
    }
    (artifact_dir / "discovery.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
