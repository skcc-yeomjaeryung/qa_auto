"""LOGIN-UI-001 style case generation from Flask/Jinja login.html evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "skills" / "frontend_analyze" / "script"))
sys.path.insert(0, str(ROOT / "app" / "skills" / "scenario_dsl" / "script"))

from extract_flask_screens import extract_flask_screens  # noqa: E402
from generate_dsl import generate_scenarios  # noqa: E402


def _boa_workspace() -> Path | None:
    base = ROOT.parent / ".data" / "workspaces"
    if not base.is_dir():
        return None
    for p in sorted(base.iterdir()):
        login = p / "src" / "frontend" / "templates" / "login.html"
        if login.is_file():
            return p
    return None


def test_flask_extract_login_selectors():
    ws = _boa_workspace()
    if not ws:
        return  # skip silently when workspace cache absent
    result = extract_flask_screens(ws)
    login = next(s for s in result["screens"] if s.get("route") == "/login")
    selectors = {i.get("selector") for i in login.get("inputs") or []}
    assert "#login-username" in selectors
    assert "#login-password" in selectors
    assert "button[type='submit']" in selectors
    assert login.get("targetFile", "").endswith("login.html")
    signup = next(s for s in result["screens"] if s.get("route") == "/signup")
    entry = next(a for a in signup.get("entryActions") or [] if a.get("sourceRoute") == "/login")
    assert entry["selector"] == "#create-account-btn"
    assert entry["targetRoute"] == "/signup"
    assert entry["evidence"]["extractor"] == "jinja-navigation-link"


def test_signup_e2e_starts_from_evidenced_navigation_cta():
    graph = {
        "graphId": "G-signup-entry",
        "version": "1",
        "nodes": [
            {
                "id": "node-screen-signup",
                "type": "screen",
                "name": "signup",
                "attributes": {
                    "route": "/signup",
                    "entryActions": [
                        {
                            "sourceRoute": "/login",
                            "targetRoute": "/signup",
                            "selector": "#create-account-btn",
                            "evidence": {
                                "file": "src/frontend/templates/login.html",
                                "line": 82,
                            },
                        }
                    ],
                    "uiElements": [
                        {
                            "name": "Username",
                            "selector": "#signup-username",
                            "kind": "input",
                            "field": "username",
                        },
                        {
                            "name": "Create Account",
                            "selector": "button[type='submit']",
                            "kind": "button",
                            "type": "submit",
                        },
                    ],
                },
                "evidence": [{"file": "src/frontend/templates/signup.html"}],
            },
            {
                "id": "node-be-signup",
                "type": "backend_endpoint",
                "name": "POST /signup",
                "attributes": {"method": "POST", "path": "/signup"},
                "evidence": [{"file": "src/frontend/frontend.py"}],
            },
        ],
        "edges": [],
    }
    scenarios = generate_scenarios(graph, project_id="PRJ-signup")
    signup = next(s for s in scenarios if str(s.get("caseId") or "").startswith("SIGNUP-E2E"))
    steps = signup["steps"]
    assert steps[0]["action"] == "navigate"
    assert steps[0]["target"]["route"] == "/login"
    assert steps[1]["action"] == "click"
    assert steps[1]["target"]["value"] == "#create-account-btn"
    assert steps[2]["action"] == "verify_navigation"
    assert steps[2]["expect"]["routePattern"] == "/signup"
    assert steps[3]["action"] == "fill"


def test_generate_login_ui_001_case_analysis():
    graph = {
        "graphId": "G-login-ui-test",
        "version": "1",
        "nodes": [
            {
                "id": "node-screen-login",
                "type": "screen",
                "name": "login",
                "attributes": {
                    "route": "/login",
                    "targetFile": "src/frontend/templates/login.html",
                    "template": "login.html",
                    "uiElements": [
                        {
                            "name": "Username",
                            "selector": "#login-username",
                            "kind": "input",
                            "type": "text",
                            "field": "username",
                        },
                        {
                            "name": "Password",
                            "selector": "#login-password",
                            "kind": "input",
                            "type": "password",
                            "field": "password",
                        },
                        {
                            "name": "Sign in",
                            "selector": "button[type='submit']",
                            "kind": "button",
                            "type": "submit",
                            "field": "submit",
                        },
                    ],
                    "inputs": [],
                },
                "evidence": [{"file": "src/frontend/templates/login.html"}],
            }
        ],
        "edges": [],
    }
    scenarios = generate_scenarios(graph, project_id="PRJ-test")
    ui = next(s for s in scenarios if s.get("caseId") == "LOGIN-UI-001")
    ca = ui["caseAnalysis"]
    assert ca["testType"] == "UI 구성"
    assert ca["targetScreen"] == "/login"
    assert ca["targetFile"] == "src/frontend/templates/login.html"
    assert ca["usernameSelector"] == "#login-username"
    assert ca["passwordSelector"] == "#login-password"
    assert ca["submitSelector"] == "button[type='submit']"
    assert ca["connectedApi"] == "없음"
    assert ca["requestValues"] == "없음"
    assert "Sign in" in ca["expectedResult"]
    assert ui["request"]["method"] == "없음"
    assert ui["journeyGroup"] == "LOGIN"
    assert ui["journeyTitle"] == "로그인 화면 구성"
    assert isinstance(ui["journeyOrder"], int)
    # Do not invent LOGIN-UI-002 without distinct evidence
    assert not any(s.get("caseId") == "LOGIN-UI-002" for s in scenarios)


def _ui_screen(node_id: str, route: str, name: str, elements: list[dict]) -> dict:
    return {
        "id": node_id,
        "type": "screen",
        "name": name,
        "attributes": {
            "route": route,
            "targetFile": f"src/frontend/templates/{name}.html",
            "uiElements": elements,
        },
        "evidence": [{"file": f"src/frontend/templates/{name}.html"}],
    }


def test_human_journey_order_index_home_before_login():
    """INDEX/HOME UI before LOGIN; UI before E2E within same group."""
    login_elements = [
        {"name": "Username", "selector": "#login-username", "kind": "input", "field": "username"},
        {"name": "Password", "selector": "#login-password", "kind": "input", "type": "password", "field": "password"},
        {"name": "Sign in", "selector": "button[type='submit']", "kind": "button", "type": "submit"},
    ]
    home_elements = [
        {"name": "Balance", "selector": "#home-balance", "kind": "text", "field": "balance"},
    ]
    index_elements = [
        {"name": "Welcome", "selector": "#index-welcome", "kind": "text", "field": "welcome"},
    ]
    graph = {
        "graphId": "G-journey-order",
        "version": "1",
        "nodes": [
            _ui_screen("node-screen-login", "/login", "login", login_elements),
            _ui_screen("node-screen-home", "/home", "home", home_elements),
            _ui_screen("node-screen-index", "/", "index", index_elements),
            {
                "id": "node-be-login",
                "type": "backend_endpoint",
                "name": "POST /login",
                "attributes": {"method": "POST", "path": "/login"},
                "evidence": [{"file": "src/backend/login.py"}],
            },
        ],
        "edges": [],
    }
    scenarios = generate_scenarios(graph, project_id="PRJ-journey")
    by_case = {s["caseId"]: s for s in scenarios if s.get("caseId")}

    assert "INDEX-UI-001" in by_case
    assert "HOME-UI-001" in by_case
    assert "LOGIN-UI-001" in by_case

    assert by_case["INDEX-UI-001"]["journeyOrder"] < by_case["HOME-UI-001"]["journeyOrder"]
    assert by_case["HOME-UI-001"]["journeyOrder"] < by_case["LOGIN-UI-001"]["journeyOrder"]

    login_e2e = next(
        (s for s in scenarios if s.get("caseId", "").startswith("LOGIN-E2E")),
        None,
    )
    if login_e2e:
        assert by_case["LOGIN-UI-001"]["journeyOrder"] < login_e2e["journeyOrder"]
        assert login_e2e["journeyGroup"] == "LOGIN"

    # List itself is journey-sorted
    orders = [s["journeyOrder"] for s in scenarios]
    assert orders == sorted(orders)
    assert scenarios[0]["journeyGroup"] == "INDEX"
