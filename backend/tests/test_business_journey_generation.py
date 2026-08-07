"""업무 목표 단위 Code-to-E2E 생성 회귀.

컴포넌트별 원자 케이스가 아니라 로그인 세션에서 CTA·입력·서버 처리·후속 상태를
하나의 여정으로 연결하는지 실제 Flask/Jinja 근거로 검증한다.
"""
from __future__ import annotations

from pathlib import Path

from app.skills.frontend_analyze.script.extract_flask_screens import extract_flask_screens
from app.skills.interaction_graph.script.compose_graph import compose_graph
from app.skills.scenario_dsl.script.generate_dsl import generate_scenarios
from app.skills.scenario_narrate.script.narrate_and_bind import _deterministic_enrich


def _write_fixture(workspace: Path) -> None:
    templates = workspace / "templates"
    templates.mkdir(parents=True)
    (templates / "login.html").write_text(
        """
        <form action="/login" method="POST">
          <label for="login-username">User ID</label>
          <input id="login-username" name="username" type="text" required>
          <label for="login-password">Password</label>
          <input id="login-password" name="password" type="password" required>
          <button type="submit">Sign in</button>
        </form>
        <a id="create-account-btn" href="/signup">Create an Account</a>
        """,
        encoding="utf-8",
    )
    (templates / "signup.html").write_text(
        """
        <form id="signup-form" action="/signup" method="POST">
          <label for="signup-username">User ID</label>
          <input id="signup-username" name="username" type="text" required>
          <label for="signup-password">Password</label>
          <input id="signup-password" name="password" type="password" required>
          <button type="submit">Create account</button>
        </form>
        """,
        encoding="utf-8",
    )
    (templates / "index.html").write_text(
        """
        {% if user %}
          <div id="account-user-name">{{ user }}</div>
          <form id="logout-form" action="/logout" method="POST">
            <button type="submit">Sign out</button>
          </form>
        {% endif %}
        <div id="alert-message">{{ message }}</div>
        <span id="current-balance">{{ balance }}</span>
        <table id="transaction-table"><tbody id="transaction-list">
          {% for t in history %}<tr><td>{{ t.label }}</td><td>{{ t.amount }}</td></tr>{% endfor %}
        </tbody></table>
        <button data-toggle="modal" data-target="#depositFunds">Deposit Funds</button>
        <div class="modal" id="depositFunds">
          <h2 class="modal-title">Make a Deposit</h2>
          <form id="deposit-form" action="/deposit" method="POST">
            <label for="accounts">External Account</label>
            <select id="accounts" name="account"><option value="bank-1">External Bank</option></select>
            <label for="deposit-amount">Deposit Amount</label>
            <input id="deposit-amount" name="amount" type="number" min="0.01" max="500000" step="0.01" required>
            <button type="button">Close</button>
            <button type="submit">Deposit</button>
          </form>
        </div>
        <button data-toggle="modal" data-target="#sendPayment">Send Payment</button>
        <div class="modal" id="sendPayment">
          <h2 class="modal-title">Send a Payment</h2>
          <form id="payment-form" action="/payment" method="POST">
            <label for="payment-accounts">Recipient</label>
            <select id="payment-accounts" name="account_num"><option value="acct-1">Test Recipient</option></select>
            <label for="payment-amount">Transaction Amount</label>
            <input id="payment-amount" name="amount" type="number" min="0.01" max="{{ balance / 100 }}" step="0.01" required>
            <button type="button">Close</button>
            <button type="submit">Send</button>
          </form>
        </div>
        """,
        encoding="utf-8",
    )
    (templates / "consent.html").write_text(
        """
        <form action="/consent" method="POST">
          <button type="submit" formaction="/consent/approve">Approve</button>
          <button type="submit" formaction="/consent/deny">Deny</button>
        </form>
        """,
        encoding="utf-8",
    )
    (workspace / "app.py").write_text(
        """
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    return redirect(url_for('home'))

@app.route('/signup', methods=['GET'])
def signup_page():
    return render_template('signup.html')

@app.route('/signup', methods=['POST'])
def signup():
    return redirect(url_for('home'))

@app.route('/home', methods=['GET'])
def home():
    token = verify_token()
    if not token:
        return redirect(url_for('login'))
    return render_template('index.html', user='masked', balance='$100.00', history=[])

@app.route('/deposit', methods=['POST'])
def deposit():
    token = verify_token()
    if not token:
        return redirect(url_for('login'))
    account_id = 'masked'
    payload = {'toAccountNum': account_id}
    return redirect(url_for('home'), msg='Deposit successful')

@app.route('/payment', methods=['POST'])
def payment():
    token = verify_token()
    if not token:
        return redirect(url_for('login'))
    return redirect(url_for('home'), msg='Payment successful')

@app.route('/logout', methods=['POST'])
def logout():
    token = verify_token()
    if not token:
        return redirect(url_for('login'))
    return redirect(url_for('login'))

@app.route('/consent', methods=['GET'])
def consent_page():
    return render_template('consent.html')

@app.route('/consent', methods=['POST'])
def consent():
    return redirect(url_for('home'))
        """,
        encoding="utf-8",
    )


def test_deposit_is_generated_as_one_business_journey(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    frontend = extract_flask_screens(tmp_path)
    graph = compose_graph(
        frontend,
        {"commitSha": "be-fixture", "endpoints": []},
        {"mappings": []},
        project_id="PRJ-business",
        graph_id="IG-business",
    )

    scenarios = generate_scenarios(graph, project_id="PRJ-business")
    deposit = next(row for row in scenarios if (row.get("request") or {}).get("path") == "/deposit")
    assert deposit["businessJourney"] is True
    assert deposit["userEventJourney"] is True
    assert deposit["name"] == "입금 후 완료 안내·잔액·거래내역 정상 반영 확인"
    narrated = _deterministic_enrich(deposit)
    assert narrated["name"] == deposit["name"]
    assert narrated["serviceLabelKo"] == "입금"

    steps = deposit["steps"]
    actions = [step["action"] for step in steps]
    titles = [step["title"] for step in steps]
    assert actions[:5] == ["navigate", "fill", "fill", "click", "assert_visible"]
    assert titles[5:] == [
        "업무 시작 화면을 엽니다",
        "업무 수행 전 현재 값을 기록합니다",
        "업무 수행 전 목록 상태를 기록합니다",
        "「Deposit Funds」 업무 버튼을 클릭합니다",
        "「Make a Deposit」이 열렸는지 확인합니다",
        "「External Account」에서 화면에 제공된 항목 하나를 선택합니다",
        "「Deposit Amount」에 테스트 값을 입력합니다",
        "「Deposit」을 실행합니다",
        "POST /deposit 처리와 후속 화면 갱신을 기다립니다",
        "처리 후 기대 화면으로 이동했는지 확인합니다",
        "후속 화면에 「Deposit successful」 안내가 표시되는지 확인합니다",
        "업무 전 값에 입력 금액이 반영됐는지 확인합니다",
        "목록에 이번 업무 결과 행과 입력값이 반영됐는지 확인합니다",
    ]

    amount = next(item for item in deposit["inputs"] if item["name"] == "amount")
    assert amount["constraints"] == {"min": "0.01", "max": "500000", "step": "0.01"}
    delta = next(step for step in steps if step["action"] == "verify_numeric_delta")
    history = next(step for step in steps if step["action"] == "verify_collection_change")
    assert delta["expect"] == {
        "beforeRef": "beforeValue",
        "deltaFrom": "inputs.amount",
        "direction": "increase",
    }
    assert history["target"]["value"] == "#transaction-list"
    assert history["expect"]["selectedFrom"] == "selected.account"
    assert history["expect"]["freshRow"] is True
    assert {item["check"] for item in deposit["verdictCriteria"]} >= {
        "session_established",
        "success_message",
        "numeric_delta",
        "collection_change",
        "request_accepted",
        "destination_route",
    }


def test_signup_journey_starts_from_evidenced_login_cta_and_has_no_false_unresolved(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    frontend = extract_flask_screens(tmp_path)
    graph = compose_graph(
        frontend,
        {"commitSha": "be-fixture", "endpoints": []},
        {"mappings": []},
        project_id="PRJ-business",
        graph_id="IG-business",
    )
    signup = next(
        row
        for row in generate_scenarios(graph, project_id="PRJ-business")
        if (row.get("request") or {}).get("path") == "/signup"
    )
    assert signup["source"]["route"] == "/login"
    main_steps = [step for step in signup["steps"] if not step.get("precondition")]
    assert [step["action"] for step in main_steps[:3]] == [
        "navigate",
        "click",
        "verify_navigation",
    ]
    assert main_steps[1]["target"]["value"] == "#create-account-btn"
    assert not signup.get("unresolved")
    assert any(item["check"] == "destination_route" for item in signup["verdictCriteria"])


def test_login_uses_environment_credentials_without_persisted_input_values(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    frontend = extract_flask_screens(tmp_path)
    graph = compose_graph(
        frontend,
        {"commitSha": "be-fixture", "endpoints": []},
        {"mappings": []},
        project_id="PRJ-business",
        graph_id="IG-business",
    )
    login = next(
        row
        for row in generate_scenarios(graph, project_id="PRJ-business")
        if (row.get("request") or {}).get("path") == "/login"
    )
    fills = [step for step in login["steps"] if step.get("action") == "fill"]
    assert {step.get("valueRef") for step in fills} == {
        "environment.loginId",
        "environment.loginSecret",
    }
    assert next(step for step in fills if step.get("valueRef") == "environment.loginSecret")[
        "masked"
    ] is True
    assert login["inputs"] == []


def test_backend_only_endpoint_is_not_published_as_browser_e2e_draft(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    frontend = extract_flask_screens(tmp_path)
    graph = compose_graph(
        frontend,
        {"commitSha": "be-fixture", "endpoints": []},
        {"mappings": []},
        project_id="PRJ-business",
        graph_id="IG-business",
    )
    graph["nodes"].append(
        {
            "id": "node-be-balance-only",
            "type": "backend_endpoint",
            "name": "GET /balances/{accountId}",
            "attributes": {"method": "GET", "path": "/balances/{accountId}"},
        }
    )
    scenarios = generate_scenarios(graph, project_id="PRJ-business")
    assert not any(
        (row.get("request") or {}).get("path") == "/balances/{accountId}"
        for row in scenarios
    )


def test_same_type_submit_buttons_keep_accessible_identity(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    frontend = extract_flask_screens(tmp_path)
    consent = next(screen for screen in frontend["screens"] if screen["route"] == "/consent")
    buttons = [item for item in consent["inputs"] if item.get("kind") == "button"]
    assert {(item["accessibleName"], item["selector"]) for item in buttons} == {
        ("Approve", "button[formaction^='/consent/approve']"),
        ("Deny", "button[formaction^='/consent/deny']"),
    }
    graph = compose_graph(
        frontend,
        {"commitSha": "be-fixture", "endpoints": []},
        {"mappings": []},
        project_id="PRJ-business",
        graph_id="IG-business",
    )
    consent = next(
        row
        for row in generate_scenarios(graph, project_id="PRJ-business")
        if (row.get("request") or {}).get("path") == "/consent"
    )
    submit = next(step for step in consent["steps"] if step.get("action") == "click")
    assert submit["destructive"] is True
    assert submit["request"] == {"method": "POST", "path": "/consent"}


def test_business_journey_is_grounded_with_live_dom_and_screenshot_evidence(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    frontend = extract_flask_screens(tmp_path)
    graph = compose_graph(
        frontend,
        {"commitSha": "be-fixture", "endpoints": []},
        {"mappings": []},
        project_id="PRJ-business",
        graph_id="IG-business",
    )
    graph["runtimeDiscovery"] = {
        "status": "complete",
        "mode": "agent-browser-read-only",
        "generatedAt": "2026-08-06T00:00:00Z",
        "guardrail": "business form submit not executed",
        "pages": [
            {
                "route": "/home",
                "snapshotPath": "/evidence/home.snapshot.txt",
                "screenshotPath": "/evidence/home.png",
                "domControls": [{"role": "button", "name": "Deposit Funds", "ref": "@e7"}],
                "safeInteractions": [
                    {
                        "selector": "[data-target='#depositFunds']",
                        "action": "open_non_submit_ui",
                        "observed": True,
                    }
                ],
            }
        ],
        "backendContracts": [{"method": "POST", "path": "/deposit"}],
    }

    scenarios = generate_scenarios(graph, project_id="PRJ-business")
    deposit = next(row for row in scenarios if (row.get("request") or {}).get("path") == "/deposit")
    open_modal = next(step for step in deposit["steps"] if "Deposit Funds" in step.get("title", ""))
    assert open_modal["target"]["runtimeObserved"] is True
    assert any(ref.startswith("runtime:dom:/home:") for ref in open_modal["evidenceRefs"])
    assert any(ref.startswith("runtime:screenshot:/home:") for ref in open_modal["evidenceRefs"])
    assert any(ref.startswith("runtime:interaction:/home:") for ref in open_modal["evidenceRefs"])
    assert deposit["generationEvidence"]["sourceTypes"] == [
        "frontend_code",
        "backend_contract",
        "live_dom",
        "screenshot",
    ]
    assert deposit["generationEvidence"]["backendContracts"] == [
        {"method": "POST", "path": "/deposit"}
    ]


def test_financial_forms_expand_to_evidenced_case_matrix(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    frontend = extract_flask_screens(tmp_path)
    graph = compose_graph(
        frontend,
        {"commitSha": "be-fixture", "endpoints": []},
        {"mappings": []},
        project_id="PRJ-business",
        graph_id="IG-business",
    )

    ui_scenarios = [
        row for row in generate_scenarios(graph, project_id="PRJ-business")
        if row.get("testType") == "UI 구성"
    ]
    home_ui = next(row for row in ui_scenarios if (row.get("source") or {}).get("route") == "/home")
    composition_step = next(
        step
        for step in home_ui["steps"]
        if step.get("action") == "assert_visible" and not step.get("precondition")
    )
    selectors = set(composition_step["target"]["selectors"])
    assert "#deposit-amount" not in selectors
    assert "#accounts" not in selectors
    assert "[data-target='#depositFunds']" in selectors
    assert "#account-user-name" in selectors

    scenarios = generate_scenarios(graph, project_id="PRJ-business")
    deposits = [row for row in scenarios if (row.get("request") or {}).get("path") == "/deposit"]
    payments = [row for row in scenarios if (row.get("request") or {}).get("path") == "/payment"]

    assert len(deposits) == 6
    assert len(payments) == 6
    assert {row.get("caseVariant", {}).get("key") for row in deposits} >= {
        "minimum_boundary",
        "below_minimum",
        "required_missing",
        "maximum_boundary",
        "above_maximum",
    }
    assert {row.get("caseVariant", {}).get("key") for row in payments} >= {
        "minimum_boundary",
        "below_minimum",
        "required_missing",
        "observed_balance_boundary",
        "above_observed_balance",
    }
    above_balance = next(
        row for row in payments if row.get("caseVariant", {}).get("key") == "above_observed_balance"
    )
    below_minimum = next(
        row for row in deposits if row.get("caseVariant", {}).get("key") == "below_minimum"
    )
    amount_fill = next(step for step in above_balance["steps"] if step.get("action") == "fill" and step.get("valueFrom") == "inputs.amount")
    assert amount_fill["valueStrategy"] == "observed_balance_plus_step"
    assert above_balance["steps"][-1]["action"] == "assert_invalid"
    assert not any(step.get("destructive") for step in above_balance["steps"])
    assert not any(step.get("destructive") for step in below_minimum["steps"])
    assert "request_accepted" not in {
        item.get("check") for item in below_minimum.get("verdictCriteria", [])
    }
    assert "165" not in str(above_balance)
    assert all(
        row.get("coverageMatrix", {}).get("fixedScenarioLimit") is False
        for row in [*deposits, *payments]
    )
