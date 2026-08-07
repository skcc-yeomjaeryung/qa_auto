#!/usr/bin/env python3
"""browser_execute / execute_run — DSL → agent-browser CLI (observational; no HITL Pass)."""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.llm.llm_client import get_llm_client

logger = logging.getLogger("qa_auto.browser_execute")

GENERATOR_VERSION = "browser-execute/1.0.0"
# 파일럿 샌드박스 기본 대상 — SSOT: app/services/environment_models.PILOT_SANDBOX_BASE_URL
DEFAULT_BASE = "https://cymbal-bank.fsi.cymbal.dev/home"
_SENSITIVE_HEADER_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "apikey",
    "api_key",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def route_url(base_url: str, route: str) -> str:
    """baseUrl에 진입 경로(`/home`)가 붙어 있어도 절대 route는 origin 기준으로 연다."""
    base = (base_url or DEFAULT_BASE).strip()
    path = route or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*://[^/]+)", base)
    origin = match.group(1) if match else base.rstrip("/")
    return f"{origin}{path}"


def _sanitize_trace_headers(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (headers or {}).items():
        compact = key.lower().replace("-", "").replace("_", "")
        if any(frag.replace("_", "") in compact for frag in _SENSITIVE_HEADER_FRAGMENTS):
            out[key] = "***"
        else:
            out[key] = value
    return out


def _sensitive_key(key: str) -> bool:
    compact = str(key or "").lower().replace("-", "").replace("_", "")
    return any(fragment.replace("_", "") in compact for fragment in _SENSITIVE_HEADER_FRAGMENTS)


def _masked_url(value: str) -> str:
    """Keep an evidenced URL while removing credentials and sensitive query values."""
    parsed = urlparse(str(value or ""))
    query = urlencode(
        [(key, "***" if _sensitive_key(key) else val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)]
    )
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, parsed.params, query, ""))


def _safe_network_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    """Persist only correlation/content metadata; never browser cookies or credentials."""
    allowed = {
        "content-type",
        "content-length",
        "x-test-run-id",
        "x-scenario-id",
        "x-scenario-version",
        "x-test-case-id",
        "x-input-profile-id",
        "x-envoy-upstream-service-time",
    }
    return {
        str(key): "***" if _sensitive_key(str(key)) else str(value)[:500]
        for key, value in (headers or {}).items()
        if str(key).lower() in allowed
    }


def _expected_network_requests(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    expected: list[dict[str, str]] = []
    for step in steps:
        request = step.get("request") if isinstance(step.get("request"), dict) else {}
        method = str(request.get("method") or "").upper()
        path = str(request.get("path") or "").split("?", 1)[0]
        if method and path and method not in {"없음", "MISSING_DATA"} and path not in {"없음", "missing_data"}:
            item = {"method": method, "path": path}
            if item not in expected:
                expected.append(item)
    return expected


def collect_network_evidence(
    *,
    session: str,
    base_url: str,
    expected: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the agent-browser request log and retain a small, masked same-origin trace.

    The request list already contains the browser-observed method/path/status.  We do not
    request response bodies because an HTML page can echo demo credentials in form values.
    """
    response = _run_cli(["network", "requests", "--json"], session=session, timeout=20)
    if not response.get("ok"):
        return [], []
    try:
        payload = json.loads(response.get("stdout") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return [], []
    rows = list(((payload.get("data") or {}).get("requests") or []))
    base = urlparse(base_url)
    base_origin = (base.scheme.lower(), (base.hostname or "").lower(), base.port)
    kept: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        parsed = urlparse(str(raw.get("url") or ""))
        origin = (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port)
        if origin != base_origin:
            continue
        method = str(raw.get("method") or "GET").upper()
        path = parsed.path or "/"
        resource_type = str(raw.get("resourceType") or "")
        expected_match = next(
            (
                spec
                for spec in expected
                if spec["method"] == method
                and (path == spec["path"] or path.rstrip("/") == spec["path"].rstrip("/"))
            ),
            None,
        )
        if not expected_match and resource_type.lower() not in {"document", "xhr", "fetch"}:
            continue
        record = {
            "networkId": f"NET-{len(kept) + 1:03d}",
            "requestId": str(raw.get("requestId") or "")[:120],
            "timestamp": raw.get("timestamp"),
            "method": method,
            "url": _masked_url(str(raw.get("url") or "")),
            "path": path,
            "resourceType": resource_type,
            "status": raw.get("status"),
            "mimeType": str(raw.get("mimeType") or "")[:160] or None,
            "requestHeaders": _safe_network_headers(raw.get("headers")),
            "responseHeaders": _safe_network_headers(raw.get("responseHeaders")),
            "expectedRequest": bool(expected_match),
            "expected": expected_match,
            "source": "agent-browser-network",
            "sanitized": True,
        }
        kept.append(record)
        if expected_match and isinstance(record.get("status"), int):
            matched.append(record)
        if len(kept) >= 50:
            break
    # agent-browser reports a form POST followed by its redirect target with the same
    # requestId.  The POST row can have status=null while the final Document row carries
    # the observed 2xx.  Preserve both facts instead of inventing a POST status.
    by_request_id: dict[str, list[dict[str, Any]]] = {}
    for record in kept:
        if record.get("requestId"):
            by_request_id.setdefault(str(record["requestId"]), []).append(record)
    for record in kept:
        if not record.get("expectedRequest"):
            continue
        status = record.get("status")
        if isinstance(status, int):
            if record not in matched:
                matched.append(record)
            continue
        redirect = next(
            (
                candidate
                for candidate in by_request_id.get(str(record.get("requestId") or ""), [])
                if candidate is not record and isinstance(candidate.get("status"), int)
            ),
            None,
        )
        if redirect:
            record["redirectObserved"] = True
            record["redirectUrl"] = redirect.get("url")
            record["effectiveStatus"] = redirect.get("status")
            record["statusBasis"] = "redirect_final_document"
            matched.append(record)
    return kept, matched


def resolve_dsl_steps(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the DSL steps this tool will execute (SSOT for planned step lists)."""
    dsl_steps = list(scenario.get("steps") or [])
    if dsl_steps:
        return dsl_steps
    route = (scenario.get("source") or {}).get("route") or "/customers/search"
    return [
        {"id": "S1", "action": "navigate", "target": {"route": route}},
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
        },
        {"id": "S4", "action": "verify_navigation", "expect": {"routePattern": "/customers/"}},
    ]


def write_progress(
    progress_path: Path | None,
    *,
    run_id: str,
    steps: list[dict[str, Any]],
    planned_total: int,
    status: str,
) -> None:
    """Publish incremental step progress so Console can render live Type 4 progress."""
    if not progress_path:
        return
    try:
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
            json.dumps(
                {
                    "runId": run_id,
                    "status": status,
                    "plannedTotal": planned_total,
                    "completedCount": len(steps),
                    "steps": steps,
                    "updatedAt": _now(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("progress publish failed run=%s", run_id)


def _load_json(src: Any) -> dict[str, Any]:
    if isinstance(src, dict):
        return src
    if not src:
        return {}
    path = Path(str(src)).expanduser().resolve()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _cli() -> str:
    return shutil.which("agent-browser") or "agent-browser"


def _run_cli(
    args: list[str],
    *,
    session: str,
    timeout: int = 60,
) -> dict[str, Any]:
    cmd = [_cli(), "--session", session, *args]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            try:
                stdout, stderr = proc.communicate(timeout=3)
            except Exception:  # noqa: BLE001
                stdout, stderr = "", "timeout"
            return {
                "ok": False,
                "cmd": cmd,
                "stdout": stdout or "",
                "stderr": stderr or "timeout",
                "exitCode": 124,
            }
    except FileNotFoundError:
        return {
            "ok": False,
            "cmd": cmd,
            "stdout": "",
            "stderr": "agent-browser CLI not found",
            "exitCode": 127,
        }
    return {
        "ok": proc.returncode == 0,
        "cmd": cmd,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "exitCode": proc.returncode if proc.returncode is not None else 1,
    }


def _close_browser_session(session: str, *, timeout: int = 30) -> None:
    """Best-effort session cleanup that never masks the run result or primary error."""
    try:
        closed = _run_cli(["close"], session=session, timeout=timeout)
    except Exception:  # noqa: BLE001 — cleanup must not replace the primary failure
        logger.exception("agent-browser session cleanup raised session=%s", session)
        return
    if not closed.get("ok"):
        logger.warning(
            "agent-browser session cleanup incomplete session=%s exit=%s error=%s",
            session,
            closed.get("exitCode"),
            str(closed.get("stderr") or "")[:300],
        )


def _wait_url_contains(session: str, token: str, *, timeout_s: int = 10) -> dict[str, Any]:
    """Poll get url instead of hanging wait --url."""
    import time

    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        res = _run_cli(["get", "url"], session=session, timeout=5)
        last = (res.get("stdout") or "").strip()
        if token and token in last:
            return {"ok": True, "stdout": last, "stderr": "", "exitCode": 0, "cmd": ["poll-url"]}
        time.sleep(0.35)
    return {"ok": False, "stdout": last, "stderr": "url-poll-timeout", "exitCode": 124, "cmd": ["poll-url"]}


def _wait_visible(session: str, selector: str, *, timeout_s: float = 3.0) -> dict[str, Any]:
    """Bounded condition poll; avoids the CLI wait command hanging a run."""
    import time

    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {"ok": False, "stdout": "", "stderr": "not-visible"}
    while time.monotonic() < deadline:
        last = _run_cli(["is", "visible", selector], session=session, timeout=4)
        if last.get("ok") and "true" in str(last.get("stdout") or "").lower():
            return last
        time.sleep(0.1)
    return last


def _selector(target: dict[str, Any] | None) -> str | None:
    if not target:
        return None
    strategy = str(target.get("strategy") or "").lower()
    value = target.get("value") or target.get("route")
    if value is None:
        return None
    value = str(value)
    if strategy in {"testid", "test_id", "data-testid"}:
        return f'[data-testid="{value}"]'
    if strategy in {"role"}:
        name = target.get("name") or value
        return f'role={value}[name="{name}"]' if name != value else f"role={value}"
    if strategy in {"label"}:
        return f'text="{value}"'
    if strategy in {"css", "selector"}:
        return value
    if strategy in {"name"}:
        return f'[name="{value}"]'
    if strategy in {"id"}:
        return f"#{value}"
    # navigate targets use route
    if target.get("route"):
        return None
    return value


def _resolve_input_value(step: dict[str, Any], inputs: dict[str, Any]) -> Any:
    if "value" in step and step["value"] is not None:
        return step["value"]
    ref = str(step.get("valueFrom") or "")
    if ref.startswith("inputs."):
        key = ref.split(".", 1)[1]
        if key in inputs and inputs.get(key) is not None:
            return inputs.get(key)
    elif ref in inputs and inputs.get(ref) is not None:
        return inputs[ref]
    # Boundary/negative variants carry an evidence-derived value in the DSL.  It is
    # a safer fallback than synthesizing an unrelated generic value, but explicit
    # runtime inputs above always win so operators can reproduce with overrides.
    if "caseInput" in step and step.get("caseInput") is not None:
        return step.get("caseInput")
    return inputs.get("customerId")


# 세션 선행조건 단계가 가리키는 계정 참조 (D-015) — 값은 시나리오에 저장하지 않는다
CREDENTIAL_REFS = {
    "environment.loginid": "loginId",
    "environment.loginsecret": "loginPassword",
    "environment.loginpassword": "loginPassword",
}


def resolve_credential_ref(step: dict[str, Any], connection: dict[str, Any]) -> tuple[Any, str] | None:
    """`valueRef`가 가리키는 연결 계정 값을 꺼낸다. 값이 없으면 만들지 않는다."""
    ref = str(step.get("valueRef") or "").strip().lower()
    if not ref:
        return None
    key = CREDENTIAL_REFS.get(ref)
    if not key:
        return None
    value = connection.get(key)
    if value in (None, ""):
        return None
    label = "연결 정보에 등록된 계정 ID" if key == "loginId" else "연결 정보에 등록된 계정 비밀번호"
    return value, label


def _find_ref(snapshot_text: str, *, test_id: str | None = None, role_hint: str | None = None) -> str | None:
    if not snapshot_text:
        return None
    if test_id:
        # look for nearby ref lines mentioning testid or name
        for line in snapshot_text.splitlines():
            if test_id in line and "@e" in line:
                m = re.search(r"(@e\d+)", line)
                if m:
                    return m.group(1)
    if role_hint:
        for line in snapshot_text.splitlines():
            if role_hint.lower() in line.lower() and "@e" in line:
                m = re.search(r"(@e\d+)", line)
                if m:
                    return m.group(1)
    return None


def _referenced_value(reference: str, inputs: dict[str, Any], observed: dict[str, Any]) -> Any:
    ref = str(reference or "")
    if ref.startswith("inputs."):
        return inputs.get(ref.split(".", 1)[1])
    return observed.get(ref)


def _decimal_from_text(value: Any) -> Decimal | None:
    text = str(value or "").replace(",", "")
    match = re.search(r"[-+]?\s*(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        number = Decimal(match.group(1))
        return -number if text.strip().startswith("-") else number
    except InvalidOperation:
        return None


def _json_object_from_cli_output(value: Any) -> dict[str, Any] | None:
    """Read the first JSON object from agent-browser output without guessing values."""
    text = str(value or "").strip()
    if not text:
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _submission_precondition(*, session: str, selector: str) -> dict[str, Any] | None:
    """Observe native form constraints before an explicitly allowed destructive submit.

    ``checkValidity`` is read-only with respect to target business data.  It lets the
    runner distinguish an exhausted/invalid test fixture from an application failure
    before clicking a submit control that the browser itself will reject.
    """
    script = (
        "(() => {"
        f"const control=document.querySelector({json.dumps(selector)});"
        "const form=control && (control.form || control.closest('form'));"
        "if(!form) return null;"
        "const invalid=Array.from(form.elements || []).filter((el) => "
        "typeof el.checkValidity === 'function' && !el.checkValidity()).map((el) => ({"
        "name:el.name || el.id || el.type || 'field', value:el.value || '',"
        "min:el.min || null, max:el.max || null, message:el.validationMessage || ''}));"
        "return {valid:form.checkValidity(), invalid};"
        "})()"
    )
    checked = _run_cli(["eval", script], session=session, timeout=10)
    if not checked.get("ok"):
        return None
    return _json_object_from_cli_output(checked.get("stdout"))


def _submission_precondition_observation(payload: dict[str, Any]) -> str:
    invalid = [item for item in (payload.get("invalid") or []) if isinstance(item, dict)]
    details: list[str] = []
    for item in invalid[:3]:
        name = str(item.get("name") or "입력값")
        value = "***" if _sensitive_key(name) else str(item.get("value") or "값 없음")
        bounds = [
            f"최소 {item.get('min')}" if item.get("min") not in (None, "") else "",
            f"최대 {item.get('max')}" if item.get("max") not in (None, "") else "",
        ]
        constraint = " · ".join(part for part in bounds if part)
        message = str(item.get("message") or "브라우저 입력 제약 불충족")
        details.append(f"{name}={value}" + (f" ({constraint})" if constraint else "") + f" — {message}")
    suffix = "; ".join(details) or "현재 화면의 입력 제약을 충족하지 못했습니다"
    return (
        "현재 테스트 계정·화면 상태로 제출할 수 없어 실행 전에 중단했습니다. "
        f"{suffix}. 대상 서비스 요청은 전송되지 않았습니다"
    )


def _selected_label(value: Any) -> str | None:
    """Read a user-visible label from an evidenced select value without inventing it."""
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        label = value.get("label") or value.get("name")
        return str(label).strip() if label else None
    raw = str(value).strip()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        label = parsed.get("label") or parsed.get("name")
        return str(label).strip() if label else None
    match = re.search(r"['\"](?:label|name)['\"]\s*:\s*['\"]([^'\"]+)['\"]", raw)
    return match.group(1).strip() if match else None


def _numeric_delta_matches(before: Decimal, after: Decimal, expected: Decimal) -> bool:
    """Compare currency-like deltas at cent precision without a one-cent false positive."""
    cent = Decimal("0.01")
    return (after - before).quantize(cent) == expected.quantize(cent)


FILLABLE_ROLES = ("textbox", "searchbox", "spinbutton", "combobox")
SUBMIT_NAME_HINTS = ("submit", "sign in", "sign up", "login", "로그인", "확인", "동의", "continue", "다음")
AUTHENTICATED_NAME_HINTS = (
    "logout",
    "log out",
    "sign out",
    "account",
    "profile",
    "user",
    "로그아웃",
    "내 계정",
    "사용자",
)
# 실행이 데이터를 만드는 화면 — DOM 자동 바인딩에서 섬밋까지 하지 않는다 (destructive 기본 차단)
DESTRUCTIVE_ROUTE_HINTS = ("signup", "deposit", "payment", "transfer", "delete", "withdraw")
# 접근성 이름이 없는 컨트롤(- textbox [required, ref=e4]: value)도 관측 대상이다.
_SNAPSHOT_LINE = re.compile(r"^\s*-\s*([a-zA-Z]+)(?:\s+\"([^\"]*)\")?(\s*\[.*)$")


def parse_dom_controls(snapshot_text: str) -> list[dict[str, Any]]:
    """snapshot(-i) 텍스트에서 실제 화면에 있는 컨트롤만 뽑는다 (추정 금지 · 관측만)."""
    controls: list[dict[str, Any]] = []
    for line in (snapshot_text or "").splitlines():
        match = _SNAPSHOT_LINE.match(line)
        if not match:
            continue
        role, name, rest = match.group(1).lower(), (match.group(2) or "").strip(), match.group(3)
        if role not in FILLABLE_ROLES and role != "button":
            continue
        ref = re.search(r"ref=(e\d+)", rest)
        value = rest.split(":", 1)[1].strip() if ":" in rest else ""
        controls.append(
            {
                "role": role,
                "name": name,
                "ref": f"@{ref.group(1)}" if ref else None,
                "currentValue": value,
                "observedLine": line.strip()[:200],
            }
        )
    return controls


def is_password_control(name: str) -> bool:
    key = name.lower().replace(" ", "")
    return any(part in key for part in ("password", "passwd", "pwd", "비밀번호"))


def is_masked_value(value: str) -> bool:
    """브라우저가 값을 가린 입력(비밀번호)인지 관측값으로 판별한다."""
    text = (value or "").strip()
    return len(text) >= 3 and set(text) <= {"•", "*", "●", "·"}


def login_controls(controls: list[dict[str, Any]]) -> tuple[dict | None, dict | None]:
    """로그인 화면의 ID·비밀번호 입력을 이름 → 관측 순서로 찾아낸다.

    Cymbal/Bank of Anthos 처럼 접근성 이름이 없는 입력이 있어 이름만으로는 못 찾는다.
    이때는 화면에 보이는 입력 순서와 마스킹 관측(●●●)만 근거로 삼는다.
    """
    fillable = [c for c in controls if c["role"] in FILLABLE_ROLES]
    pw = next((c for c in fillable if is_password_control(c["name"])), None)
    if pw is None:
        pw = next((c for c in fillable if is_masked_value(str(c.get("currentValue") or ""))), None)
    ident = next(
        (c for c in fillable if is_login_id_control(c["name"]) and not is_password_control(c["name"])),
        None,
    )
    if ident is None and pw is not None:
        # 비밀번호 앞에 있는 첫 입력이 계정 입력이다 (DOM 순서 관측)
        before = [c for c in fillable if c is not pw]
        ident = before[0] if before else None
    if ident is None and pw is None and len(fillable) >= 2:
        ident, pw = fillable[0], fillable[1]
    return ident, pw


def authenticated_session_observed(snapshot_text: str) -> bool:
    """Return True only when the observed DOM supports reusing an existing session.

    Opening a login route can immediately redirect an already-authenticated browser to
    the application home.  In that case replaying generated credential selectors creates
    a false failure.  We require both (1) no observed login input pair and (2) an observed
    account/user/logout control before skipping the login precondition.
    """
    controls = parse_dom_controls(snapshot_text)
    ident, password = login_controls(controls)
    if ident is not None or password is not None:
        return False
    observed_names = " ".join(str(item.get("name") or "").lower() for item in controls)
    return bool(observed_names) and any(hint in observed_names for hint in AUTHENTICATED_NAME_HINTS)


def is_login_id_control(name: str) -> bool:
    key = name.lower().replace(" ", "")
    return any(part in key for part in ("username", "userid", "loginid", "아이디", "email", "id"))


def credential_for(control_name: str, connection: dict[str, Any]) -> tuple[Any, str] | None:
    """연결 계정으로 채울 수 있는 컨트롤이면 (값, 근거)를 돌려준다."""
    if is_password_control(control_name) and connection.get("loginPassword"):
        return connection["loginPassword"], "환경에 등록된 연결 계정 비밀번호"
    if is_login_id_control(control_name) and connection.get("loginId"):
        return connection["loginId"], "환경에 등록된 연결 계정 ID"
    return None


# 인증·메서드 거부 신호 (D-015)
#
# 숫자만으로 판정하지 않는다 — 화면의 금액·건수에 우연히 섞인 숫자를 오류로 읽으면
# 반대 방향의 오판이 된다. 상태 코드는 오류 문구와 함께 나올 때만 근거로 쓴다.
DENIAL_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (r"method\s+not\s+allowed", "method_not_allowed", "허용되지 않은 요청 방식"),
    (r"allowlist\s+methods", "method_not_allowed", "허용된 요청 방식 아님"),
    (r"(?:error|http|status)\s*[: ]?\s*405", "method_not_allowed", "HTTP 405"),
    (r"\b401\s+unauthorized\b|\bunauthorized\b", "session_missing", "인증되지 않음"),
    (r"\b403\s+forbidden\b|\bforbidden\b", "session_missing", "권한 없음"),
    (r"internal\s+server\s+error", "server_error", "서버 오류"),
    (r"(?:error|http|status)\s*[: ]?\s*50[0-9]\b", "server_error", "서버 오류 응답"),
    # agent-browser snapshot은 `heading \"Not Found\" [level=1]`처럼 접근성
    # 메타데이터를 같은 줄 뒤에 붙인다. 줄 끝 일치만 사용하면 실제 Flask 404를
    # 놓치므로, Flask 기본 문구와 HTTP 404 표기를 우선 근거로 삼는다.
    (
        r"the\s+requested\s+url\s+was\s+not\s+found\s+on\s+the\s+server",
        "not_found",
        "요청한 화면을 서버에서 찾지 못함",
    ),
    (r"(?:error|http|status)\s*[: ]?\s*404\b", "not_found", "HTTP 404"),
    (r"(?:heading|title)\s+[\"']?not\s+found\b", "not_found", "화면을 찾지 못함"),
)


def detect_denial(snapshot_text: str) -> dict[str, str] | None:
    """화면에 거부 응답이 렌더됐는지 관측한다 (오류 문구 기준)."""
    text = (snapshot_text or "").lower()
    if not text:
        return None
    for pattern, kind, detail in DENIAL_PATTERNS:
        hit = re.search(pattern, text, re.MULTILINE)
        if hit:
            return {"kind": kind, "detail": detail, "signal": hit.group(0).strip()[:40]}
    return None


def synthesize_for(control_name: str) -> tuple[Any, str] | None:
    """필드 이름 기반 합성값 (input_recommend와 같은 규칙을 재사용)."""
    try:
        _ensure_backend_path()
        from app.skills.input_recommend.script.recommend import synthesize_value
    except Exception:  # noqa: BLE001
        return None
    made = synthesize_value({"field": control_name, "type": "string"})
    if not made:
        return None
    value, rationale = made
    return value, rationale


def _ensure_backend_path() -> None:
    backend_root = Path(__file__).resolve().parents[4]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))


def llm_bind_controls(
    *,
    controls: list[dict[str, Any]],
    scenario: dict[str, Any],
    url: str,
) -> dict[str, dict[str, Any]]:
    """DOM 관측 컨트롤에 대해 LLM이 테스트 입력값을 제안한다. 실패하면 빈 dict."""
    targets = [c for c in controls if c["role"] in FILLABLE_ROLES and not is_password_control(c["name"])]
    if not targets:
        return {}
    try:
        _ensure_backend_path()
        from app.core.llm.llm_client import get_llm_client
        from app.core.prompts import PromptCatalog

        system, _ = PromptCatalog().render_system("run/bind_dom_inputs_system.md")
        if not system:
            return {}
        user = json.dumps(
            {
                "url": url,
                "caseId": scenario.get("caseId"),
                "testType": scenario.get("testType"),
                "screen": (scenario.get("source") or {}).get("screen"),
                "controls": [
                    {"name": c["name"], "role": c["role"], "observed": c["observedLine"]}
                    for c in targets
                ],
            },
            ensure_ascii=False,
        )
        parsed = get_llm_client().chat_json(system=system, user=user, timeout_s=25.0)
    except Exception:  # noqa: BLE001 — LLM 미가동은 결정론 경로로 대체한다
        logger.info("llm dom bind unavailable; using deterministic synthesis")
        return {}
    if not isinstance(parsed, dict):
        return {}
    raw = parsed.get("bindings")
    if not isinstance(raw, list):
        return {}
    allowed = {c["name"] for c in targets}
    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        value = item.get("value")
        if name not in allowed or value is None:
            continue
        if not isinstance(value, (str, int, float)):
            continue
        out[name] = {
            "value": str(value),
            "rationale": str(item.get("rationale") or "LLM 제안값")[:200],
        }
    return out


def mask_secret_values(payload: dict[str, Any], secrets: list[str]) -> dict[str, Any]:
    """증적·결과 JSON에 연결 비밀번호가 남지 않게 치환한다."""
    real = [s for s in secrets if s]
    if not real:
        return payload
    dumped = json.dumps(payload, ensure_ascii=False)
    for secret in real:
        dumped = dumped.replace(secret, "***")
    return json.loads(dumped)


def evaluate_verdict(
    *,
    scenario: dict[str, Any],
    steps: list[dict[str, Any]],
    session_established: bool | None,
    session_ended: bool | None,
    blocked_by_precondition: bool,
    denied_signals: list[dict[str, Any]],
    binding_values: dict[str, Any],
    missing: list[str],
    input_precondition_invalid: bool = False,
) -> dict[str, Any]:
    """기대 결과와 관측을 항목별로 대조한다 (결정론 · script).

    「Endpoint 도달」·「예외 없음」·「스크린샷 존재」는 성공 근거로 쓰지 않는다 (D-015).
    판단할 근거가 없으면 `undetermined`로 남기고 Pass/Fail은 사람이 확정한다.
    """
    criteria = [c for c in (scenario.get("verdictCriteria") or []) if isinstance(c, dict)]
    auth_required = bool(scenario.get("authRequired"))
    visible = {str(s) for s in (binding_values.get("visibleControls") or [])}
    direct_criteria = {
        str(key): value
        for key, value in (binding_values.get("criterionObservations") or {}).items()
        if isinstance(value, dict)
    }
    results: list[dict[str, Any]] = []

    def add(cid: str, check: str, expected: str, met: str, observed: str) -> None:
        results.append(
            {
                "id": cid,
                "check": check,
                "expected": expected,
                "result": met,
                "observed": observed,
            }
        )

    for crit in criteria:
        cid = str(crit.get("id") or crit.get("check") or "C")
        check = str(crit.get("check") or "")
        expected = str(crit.get("expected") or "")
        directly_observed = direct_criteria.get(cid)
        if directly_observed:
            add(
                cid,
                check,
                expected,
                str(directly_observed.get("result") or "undetermined"),
                str(directly_observed.get("observed") or "직접 관측 사유가 없습니다"),
            )
        elif check == "session_established":
            if session_established is True:
                add(cid, check, expected, "met", "로그인 후 인증 전용 요소를 화면에서 관측했습니다")
            elif session_established is False:
                add(cid, check, expected, "not_met", "로그인 세션을 확인하지 못했습니다")
            else:
                add(cid, check, expected, "undetermined", "세션 확인 단계를 실행하지 못했습니다")
        elif check == "logout_effect":
            if blocked_by_precondition:
                add(cid, check, expected, "undetermined", "선행 로그인이 성립하지 않아 로그아웃을 수행하지 못했습니다")
            elif session_ended is True:
                add(cid, check, expected, "met", "로그아웃 후 인증 전용 요소가 사라졌습니다")
            elif session_ended is False:
                add(cid, check, expected, "not_met", "로그아웃 후에도 인증 전용 요소가 남아 있습니다")
            else:
                add(cid, check, expected, "undetermined", "로그아웃 결과를 확인하는 단계가 실행되지 않았습니다")
        elif check == "controls_visible":
            wanted = [str(s) for s in (crit.get("selectors") or [])]
            if not wanted:
                add(cid, check, expected, "undetermined", "확인 대상 컨트롤 근거가 없습니다")
                continue
            absent = [s for s in wanted if s not in visible]
            if not absent and visible:
                add(cid, check, expected, "met", f"컨트롤 {len(wanted)}건을 화면에서 관측했습니다")
            elif visible:
                add(cid, check, expected, "not_met", f"미확인 컨트롤 {', '.join(absent[:3])}")
            else:
                add(cid, check, expected, "undetermined", "표시 확인 단계가 실행되지 않았습니다")
        elif check == "request_accepted":
            denial = denied_signals[0] if denied_signals else None
            matched_network = [
                row
                for row in (binding_values.get("matchedNetworkRequests") or [])
                if isinstance(row, dict)
            ]
            if denial:
                add(cid, check, expected, "not_met", f"요청이 거부됐습니다 ({denial['detail']})")
            elif input_precondition_invalid:
                add(cid, check, expected, "undetermined", "현재 테스트 계정 상태가 입력 제약을 충족하지 않아 요청을 보내지 않았습니다")
            elif blocked_by_precondition:
                add(cid, check, expected, "undetermined", "선행 로그인이 성립하지 않아 요청을 수행하지 못했습니다")
            elif any(str(m).startswith("route:") for m in missing):
                add(cid, check, expected, "undetermined", "화면 경로 근거가 없어 요청을 수행하지 못했습니다")
            elif any("submit_blocked_destructive" in str(m) for m in missing):
                add(cid, check, expected, "undetermined", "데이터를 만드는 동작이라 자동 실행을 차단했습니다")
            elif matched_network:
                observed_request = matched_network[-1]
                status = observed_request.get("status")
                effective_status = status if isinstance(status, int) else observed_request.get("effectiveStatus")
                result = "met" if isinstance(effective_status, int) and 200 <= effective_status < 400 else "not_met"
                status_text = (
                    f"redirect 최종 HTTP {effective_status}"
                    if observed_request.get("statusBasis") == "redirect_final_document"
                    else f"HTTP {effective_status}"
                )
                add(
                    cid,
                    check,
                    expected,
                    result,
                    f"agent-browser 네트워크에서 {observed_request.get('method')} {observed_request.get('path')} · {status_text}를 관측했습니다",
                )
            else:
                add(cid, check, expected, "undetermined", "agent-browser 네트워크에서 대상 요청·응답을 확인하지 못했습니다")
        else:
            add(cid, check or "unknown", expected, "undetermined", "판정 규칙이 없는 항목입니다")

    not_met = [r for r in results if r["result"] == "not_met"]
    undetermined = [r for r in results if r["result"] == "undetermined"]
    met = [r for r in results if r["result"] == "met"]

    # 계약이 정한 값만 쓴다 — expected_met / expected_not_met / undetermined
    if input_precondition_invalid:
        verdict = "expected_not_met"
        reason = "현재 테스트 계정 상태가 화면 입력 제약을 충족하지 않아 제출 요청을 보내지 않았습니다"
    elif blocked_by_precondition:
        verdict = "expected_not_met"
        reason = "선행 로그인 세션이 성립하지 않아 본 단계를 진행하지 않았습니다"
    elif not results:
        verdict = "undetermined"
        reason = "대조할 기대 결과 기준이 없어 판정하지 않았습니다"
    elif not_met:
        verdict = "expected_not_met"
        reason = " · ".join(r["observed"] for r in not_met[:2])
    elif met and not undetermined:
        verdict = "expected_met"
        reason = " · ".join(r["observed"] for r in met[:2])
    elif met:
        # 일부만 관측된 실행을 성공으로 올리지 않는다
        verdict = "undetermined"
        reason = (
            " · ".join(r["observed"] for r in met[:1])
            + f" · 확인하지 못한 항목 {len(undetermined)}건"
        )
    else:
        verdict = "undetermined"
        reason = " · ".join(r["observed"] for r in undetermined[:2])

    blocking: list[dict[str, str]] = []
    if input_precondition_invalid:
        blocking.append(
            {
                "kind": "input_precondition_invalid",
                "detail": "현재 테스트 계정의 잔액·허용 범위가 실행 입력을 수용하지 않아 브라우저가 제출을 차단했습니다",
                "suggestedFix": "테스트 계정의 선행 데이터를 초기화·충전하거나 현재 허용 범위 안의 입력값으로 다시 실행하세요",
            }
        )
    if blocked_by_precondition:
        blocking.append(
            {
                "kind": "session_missing",
                "detail": "로그인 세션 확인 단계가 통과하지 못했습니다",
                "suggestedFix": "연결 정보의 계정으로 로그인이 되는지 확인하세요",
            }
        )
    for signal in denied_signals:
        kind = str(signal.get("kind") or "unknown")
        fix = (
            "직접 URL 진입 대신 화면의 실제 동작 버튼을 누르는 단계로 바꾸세요"
            if kind == "method_not_allowed"
            else "거부 사유를 확인한 뒤 시나리오 선행조건·입력을 보완하세요"
        )
        if kind == "session_missing":
            fix = "선행 로그인 단계를 시나리오에 추가하세요"
        elif kind == "not_found":
            fix = "분석된 화면 경로와 실행 서버의 실제 라우팅을 확인하세요"
        elif kind == "server_error":
            fix = "서버 로그와 요청 입력을 확인한 뒤 다시 실행하세요"
        blocking.append(
            {"kind": kind, "detail": str(signal.get("detail") or ""), "suggestedFix": fix}
        )
    for item in results:
        if item["result"] == "not_met" and item["check"] == "logout_effect":
            blocking.append(
                {
                    "kind": "no_state_change",
                    "detail": item["observed"],
                    "suggestedFix": "로그아웃이 실제로 수행되는 화면 트리거를 사용하세요",
                }
            )
    if not results:
        blocking.append(
            {
                "kind": "unknown",
                "detail": "기대 결과 기준이 시나리오에 없습니다",
                "suggestedFix": "분석 근거로 verdictCriteria 를 채우세요",
            }
        )
    if auth_required and session_established is None:
        blocking.append(
            {
                "kind": "session_missing",
                "detail": "세션 확인 단계가 실행되지 않았습니다",
                "suggestedFix": "선행 로그인·세션 확인 단계를 시나리오에 포함하세요",
            }
        )

    blocked_cause = blocking[0]["kind"] if blocking else None
    return {
        "verdict": verdict,
        "reason": reason,
        "verdictReason": reason,
        "criteria": results,
        "criteriaResults": results,
        "blockingIssues": blocking,
        "blockedCause": blocked_cause,
        "deniedSignals": denied_signals,
        "coverageNote": (
            f"확인하지 못한 항목 {len(undetermined)}건" if undetermined else "기준 항목 전부 관측"
        ),
        "remediation": [b["suggestedFix"] for b in blocking if b.get("suggestedFix")],
        "humanDecisionRequired": True,
        "hitlRequired": True,
    }


def _execute_scenario_impl(
    *,
    scenario: dict[str, Any],
    inputs: dict[str, Any],
    base_url: str,
    run_id: str,
    consent: bool,
    evidence_dir: Path,
    headers: dict[str, str] | None = None,
    headed: bool = False,
    session: str | None = None,
    progress_path: Path | None = None,
    connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not consent:
        return {
            "ok": False,
            "status": "CANCELLED",
            "runId": run_id,
            "error": "agent-browser consent required",
            "steps": [],
            "missing_data": ["user_consent"],
            "observationSummary": "실행 차단: 사용자 동의 없음",
        }

    session = session or f"run-{run_id[:12]}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    headers = dict(headers or {})
    headers.setdefault("X-Test-Run-ID", run_id)
    headers.setdefault("X-Scenario-ID", str(scenario.get("scenarioId") or ""))
    headers.setdefault("X-Scenario-Version", str(scenario.get("version") or "1"))
    if headers.get("X-Test-Case-ID") in (None, ""):
        headers["X-Test-Case-ID"] = f"TC-{run_id[-8:]}"
    # Never persist secrets into evidence (Authorization/Cookie/Token/Password).
    headers = _sanitize_trace_headers(headers)

    steps_out: list[dict[str, Any]] = []
    missing: list[str] = []
    screenshots: list[str] = []
    snapshots: list[str] = []
    binding_values: dict[str, Any] = {}
    cancelled = False
    connection = dict(connection or {})
    # DOM에서 관측해 실제로 채운 입력 — 화면·플로우가 「무엇을 넣었는지」 보여주는 근거
    dom_bindings: list[dict[str, Any]] = []
    dom_controls: list[dict[str, Any]] = []
    submitted_shot: str | None = None
    result_shot: str | None = None
    # 세션 선행조건 관측 (D-015) — 로그인 세션이 실제로 생겼는지, 어디서 막혔는지
    session_established: bool | None = None
    session_ended: bool | None = None
    blocked_by_precondition = False
    input_precondition_invalid = False
    precondition_session_reused = False
    criteria_obs: dict[str, dict[str, Any]] = {}
    denied_signals: list[dict[str, Any]] = []
    network_requests: list[dict[str, Any]] = []
    matched_network_requests: list[dict[str, Any]] = []

    def remember_visible_controls(selectors: list[str]) -> None:
        """Accumulate direct visibility probes without losing earlier session markers.

        A run can assert the login-session markers first and page controls later.  Using
        ``setdefault`` kept only the first group, which made the final verdict claim that
        a control was missing even though its assert step had observed it.
        """
        current = [str(item) for item in (binding_values.get("visibleControls") or []) if item]
        binding_values["visibleControls"] = list(dict.fromkeys([*current, *selectors]))

    # cancel flag file
    cancel_flag = evidence_dir / "CANCEL"
    open_args = ["open", route_url(base_url, str((scenario.get("source") or {}).get("route") or "/"))]
    if headed:
        open_args = ["--headed", *open_args]

    dsl_steps = resolve_dsl_steps(scenario)
    expected_network = _expected_network_requests(dsl_steps)
    planned_total = len(dsl_steps) + 1  # + header seed step

    def record_step(
        step_id: str,
        action: str,
        mcp_tool: str,
        *,
        status: str,
        ref: str | None = None,
        started: str,
        ended: str,
        snapshot_path: str | None = None,
        screenshot_path: str | None = None,
        observation: str = "",
        network_refs: list[str] | None = None,
        missing_data: list[str] | None = None,
    ) -> None:
        steps_out.append(
            {
                "stepId": step_id,
                "action": action,
                "mcpTool": mcp_tool,
                "refOrLocator": ref,
                "status": status,
                "startedAt": started,
                "endedAt": ended,
                "snapshotPath": snapshot_path,
                "screenshotPath": screenshot_path,
                "networkRefs": network_refs or [],
                "observationSummary": observation,
                "missingData": missing_data or [],
            }
        )
        write_progress(
            progress_path,
            run_id=run_id,
            steps=steps_out,
            planned_total=planned_total,
            status="RUNNING",
        )

    # Prefer page localStorage for FE-forwarded tracing headers.
    # Avoid browser-level set headers here — extra request headers can break CORS preflight
    # on sample FE→BE calls. Headers are seeded after open via localStorage (+ FE forward).
    started = _now()
    record_step(
        "H0",
        "set_headers",
        "agent_browser_set_headers",
        status="ok",
        started=started,
        ended=_now(),
        observation="Test Run headers deferred to localStorage after open (CORS-safe)",
    )
    capture_started = _run_cli(["network", "requests", "--clear"], session=session, timeout=10)
    if not capture_started.get("ok"):
        missing.append("network_capture_start")

    # open once for navigate
    nav_done = False
    last_snapshot = ""
    shot_idx = 0

    for step_index, step in enumerate(dsl_steps):
        if cancel_flag.exists():
            cancelled = True
            break
        step_id = str(step.get("id") or f"S{len(steps_out)+1}")
        action = str(step.get("action") or "").lower()
        started = _now()
        target = step.get("target") if isinstance(step.get("target"), dict) else {}
        sel = _selector(target)
        status = "ok"
        obs = ""
        ref = sel
        snap_path = None
        shot_path = None
        mcp = "agent_browser_snapshot"

        if precondition_session_reused and step.get("precondition"):
            is_session_check = bool(step.get("sessionCheck"))
            if is_session_check:
                session_established = True
            record_step(
                step_id,
                action,
                mcp,
                status="ok" if is_session_check else "skipped",
                ref=ref,
                started=started,
                ended=_now(),
                observation=(
                    "기존 로그인 세션을 화면에서 확인했습니다"
                    if is_session_check
                    else "기존 로그인 세션을 재사용해 계정 입력 단계를 건너뛰었습니다"
                ),
            )
            continue

        try:
            if action == "navigate":
                route = str((target or {}).get("route") or (scenario.get("source") or {}).get("route") or "/")
                mcp = "agent_browser_open"
                if route.strip().casefold() in {"missing_data", "없음", "n/a", "none"}:
                    # 분석이 화면 경로를 확정하지 못한 시나리오 — 없는 주소를 열어
                    # 「도달했다」로 남기지 않는다 (D-015)
                    status = "warning"
                    obs = "화면 경로가 분석에서 확정되지 않아 이동하지 않았습니다"
                    missing.append(f"route:{step_id}")
                    record_step(
                        step_id,
                        action,
                        mcp,
                        status=status,
                        started=started,
                        ended=_now(),
                        observation=obs,
                        missing_data=["scenario.route"],
                    )
                    continue
                url = route_url(base_url, route)
                res = _run_cli(["open", url] if not headed else ["--headed", "open", url], session=session, timeout=90)
                nav_done = True
                if not res["ok"]:
                    status = "error"
                    obs = res["stderr"] or res["stdout"] or "open failed"
                else:
                    obs = f"opened {url}"
                    # Seed FE localStorage with full correlation set (Phase 10).
                    # Target FE should forward these on API calls; sample Spring allows CORS headers.
                    seed_keys = [
                        "X-Test-Run-ID",
                        "X-Scenario-ID",
                        "X-Scenario-Version",
                        "X-Test-Case-ID",
                        "X-Input-Profile-ID",
                    ]
                    for hk in seed_keys:
                        hv = headers.get(hk)
                        if not hv:
                            continue
                        js = (
                            f"localStorage.setItem({json.dumps(hk)}, {json.dumps(str(hv))});"
                            f"localStorage.getItem({json.dumps(hk)})"
                        )
                        _run_cli(["eval", js], session=session)
                # snapshot before fill
                snap = _run_cli(["snapshot", "-i"], session=session)
                last_snapshot = snap.get("stdout") or ""
                snap_path = str(evidence_dir / f"{step_id}.snapshot.txt")
                Path(snap_path).write_text(last_snapshot, encoding="utf-8")
                snapshots.append(snap_path)
                # 진입한 화면 캡쳐 — 플로우 노드가 「어떤 화면인지」를 그림으로 보여준다.
                shot_idx += 1
                shot_path = str(evidence_dir / f"{shot_idx:02d}-{step_id}-screen.png")
                if _run_cli(["screenshot", shot_path], session=session, timeout=20)["ok"] and Path(
                    shot_path
                ).is_file():
                    screenshots.append(shot_path)
                else:
                    shot_path = None
                    missing.append(f"screenshot:{step_id}")

                # 거부 신호 관측 — 도달했다고 성공이 아니다 (D-015)
                denial = detect_denial(last_snapshot)
                if denial:
                    status = "warning"
                    obs = f"{obs}; 서버가 요청을 거부했습니다 ({denial['detail']})"
                    denied_signals.append({**denial, "stepId": step_id, "route": route})
                    missing.append(f"denied:{step_id}")

                if (
                    step.get("precondition")
                    and "login" in route.lower()
                    and authenticated_session_observed(last_snapshot)
                ):
                    precondition_session_reused = True
                    session_established = True
                    obs = (
                        f"{obs}; 로그인 입력 화면 대신 인증된 사용자 메뉴를 관측해 기존 세션을 재사용합니다"
                    )

                # 로그인 게이트 통과 — 요청한 화면이 아니라 로그인 화면이 열렸을 때만 수행한다
                current = (_run_cli(["get", "url"], session=session, timeout=8).get("stdout") or "").strip()
                needs_login = (
                    "login" in current.lower()
                    and "login" not in route.lower()
                    and bool(connection.get("loginId"))
                    and bool(connection.get("loginPassword"))
                )
                if needs_login:
                    controls = parse_dom_controls(last_snapshot)
                    id_ctl, pw_ctl = login_controls(controls)
                    submit_ctl = next(
                        (
                            c
                            for c in controls
                            if c["role"] == "button"
                            and any(hint in c["name"].lower() for hint in SUBMIT_NAME_HINTS)
                        ),
                        None,
                    )
                    if id_ctl and pw_ctl and submit_ctl:
                        _run_cli(
                            ["fill", str(id_ctl["ref"] or f'text="{id_ctl["name"]}"'), str(connection["loginId"])],
                            session=session,
                        )
                        _run_cli(
                            [
                                "fill",
                                str(pw_ctl["ref"] or f'text="{pw_ctl["name"]}"'),
                                str(connection["loginPassword"]),
                            ],
                            session=session,
                        )
                        # 입력 직후 증적 — 어떤 값이 화면에 들어갔는지 사람이 볼 수 있어야 한다
                        shot_idx += 1
                        login_shot = str(evidence_dir / f"{shot_idx:02d}-{step_id}-login-submitted.png")
                        if _run_cli(["screenshot", login_shot], session=session, timeout=20)["ok"] and Path(
                            login_shot
                        ).is_file():
                            screenshots.append(login_shot)
                            submitted_shot = login_shot
                        dom_bindings.append(
                            {
                                "field": id_ctl["name"] or "login_id",
                                "value": str(connection["loginId"]),
                                "source": "connection_account",
                                "rationale": "환경에 등록된 연결 계정 ID",
                                "filled": True,
                            }
                        )
                        dom_bindings.append(
                            {
                                "field": pw_ctl["name"] or "login_password",
                                "value": "***",
                                "source": "connection_account",
                                "rationale": "환경에 등록된 연결 계정 비밀번호",
                                "filled": True,
                            }
                        )
                        _run_cli(["click", str(submit_ctl["ref"] or f'text="{submit_ctl["name"]}"')], session=session)
                        _run_cli(["wait", "--load", "networkidle"], session=session, timeout=20)
                        # 로그인 후 원래 요청 화면으로 다시 진입
                        _run_cli(["open", url], session=session, timeout=60)
                        snap = _run_cli(["snapshot", "-i"], session=session)
                        last_snapshot = snap.get("stdout") or ""
                        Path(str(evidence_dir / f"{step_id}-after-login.snapshot.txt")).write_text(
                            last_snapshot, encoding="utf-8"
                        )
                        # 로그인 통과 후 화면 캡쳐 — 플로우 노드가 실제 대상 화면을 보여준다
                        shot_idx += 1
                        after_shot = str(evidence_dir / f"{shot_idx:02d}-{step_id}-screen-after-login.png")
                        if _run_cli(["screenshot", after_shot], session=session, timeout=20)["ok"] and Path(
                            after_shot
                        ).is_file():
                            screenshots.append(after_shot)
                            shot_path = after_shot
                        after_url = (
                            _run_cli(["get", "url"], session=session, timeout=8).get("stdout") or ""
                        ).strip()
                        obs = f"{obs}; 연결 계정({connection['loginId']})으로 로그인 후 재진입 → {after_url}"
                    else:
                        missing.append("login_form_not_observed")
                        obs = f"{obs}; 로그인 화면으로 이동했지만 로그인 컨트롤을 관측하지 못했습니다"

            elif action == "fill":
                if not nav_done:
                    route = str((scenario.get("source") or {}).get("route") or "/customers/search")
                    _run_cli(["open", route_url(base_url, route)], session=session, timeout=90)
                    nav_done = True
                mcp = "agent_browser_fill"
                value = _resolve_input_value(step, inputs)
                field_name = str(step.get("valueFrom") or "").replace("inputs.", "") or str(
                    (target or {}).get("value") or ""
                )
                value_source = "input_profile"
                bind_reason = "실행 요청 입력값"
                value_strategy = str(step.get("valueStrategy") or "")
                strategy_observation_missing = False
                if value_strategy in {"observed_balance", "observed_balance_plus_step"}:
                    observed_balance = _decimal_from_text(binding_values.get("beforeValue"))
                    constraint_step = _decimal_from_text(step.get("valueStrategyStep")) or Decimal("1")
                    if observed_balance is not None:
                        value = observed_balance + (
                            constraint_step if value_strategy == "observed_balance_plus_step" else Decimal("0")
                        )
                        value_source = "runtime_observation"
                        bind_reason = (
                            "실행 직전 화면 잔액 + 분석된 step"
                            if value_strategy == "observed_balance_plus_step"
                            else "실행 직전 화면 잔액"
                        )
                    else:
                        value = None
                        strategy_observation_missing = True
                        value_source = "missing_data"
                        bind_reason = "실행 직전 기준값을 화면에서 관측하지 못했습니다"
                        missing.append(f"runtime_observation:{field_name or 'value'}")
                # 세션 선행조건 단계는 연결 계정 참조만 쓴다 (값 생성 금지 · D-015)
                credential_step = bool(str(step.get("valueRef") or ""))
                if credential_step:
                    cred_ref = resolve_credential_ref(step, connection)
                    field_name = field_name or ("계정 비밀번호" if step.get("masked") else "계정 ID")
                    if cred_ref:
                        value, bind_reason = cred_ref
                        value_source = "connection_account"
                    else:
                        value = ""
                        value_source = "missing_data"
                        bind_reason = "연결 정보에 계정이 등록되지 않아 값을 만들지 않았습니다"
                        missing.append(
                            "connection.loginSecret" if step.get("masked") else "connection.loginId"
                        )
                if (
                    not credential_step
                    and not strategy_observation_missing
                    and (value is None or value == "")
                    and not step.get("allowEmpty")
                ):
                    # 값이 비어 있으면 연결 계정 → 이름 기반 합성으로 채운다 (근거 기록)
                    cred = credential_for(field_name, connection)
                    made = cred or synthesize_for(field_name)
                    if made:
                        value, bind_reason = made
                        value_source = "connection_account" if cred else "derived_synthetic"
                    else:
                        value = ""
                        value_source = "missing_data"
                        bind_reason = "코드·DOM·연결 계정에서 값을 찾지 못했습니다"
                snap = _run_cli(["snapshot", "-i"], session=session)
                last_snapshot = snap.get("stdout") or ""
                snap_path = str(evidence_dir / f"{step_id}-pre.snapshot.txt")
                Path(snap_path).write_text(last_snapshot, encoding="utf-8")
                snapshots.append(snap_path)
                test_id = str((target or {}).get("value") or "")
                ref_token = _find_ref(last_snapshot, test_id=test_id, role_hint="textbox")
                # Prefer CSS testId for controlled React inputs (more reliable than stale @refs)
                fill_target = sel if sel and "data-testid" in str(sel) else (ref_token or sel)
                if strategy_observation_missing:
                    status = "error"
                    obs = "runtime observation required by valueStrategy was not available"
                elif not fill_target:
                    status = "error"
                    missing.append(f"locator:{step_id}")
                    obs = "fill target not found in snapshot"
                else:
                    res = _run_cli(["fill", str(fill_target), str(value)], session=session)
                    ref = fill_target
                    secret_field = is_password_control(field_name) or bool(step.get("masked"))
                    dom_bindings.append(
                        {
                            "stepId": step_id,
                            "field": field_name or str(fill_target),
                            "locator": str(fill_target),
                            "value": "***" if secret_field else str(value),
                            "source": value_source,
                            "rationale": bind_reason,
                            "filled": bool(res["ok"]),
                        }
                    )
                    if not res["ok"]:
                        status = "error"
                        obs = res["stderr"] or res["stdout"] or "fill failed"
                    else:
                        shown = "***" if secret_field else str(value)
                        obs = f"입력 {field_name or fill_target} = {shown} ({bind_reason})"
                    # post fill snapshot + screenshot (입력 직후)
                    snap2 = _run_cli(["snapshot", "-i"], session=session)
                    last_snapshot = snap2.get("stdout") or ""
                    post = evidence_dir / f"{step_id}-post.snapshot.txt"
                    post.write_text(last_snapshot, encoding="utf-8")
                    snapshots.append(str(post))
                    shot_idx += 1
                    shot_path = str(evidence_dir / f"{shot_idx:02d}-after-input.png")
                    shot = _run_cli(["screenshot", shot_path], session=session, timeout=20)
                    if shot["ok"] and Path(shot_path).is_file():
                        screenshots.append(shot_path)
                    else:
                        # annotate fallback
                        shot = _run_cli(
                            ["screenshot", "--annotate", shot_path], session=session, timeout=20
                        )
                        if shot["ok"] and Path(shot_path).is_file():
                            screenshots.append(shot_path)
                        else:
                            missing.append(f"screenshot:{step_id}")

            elif action == "select":
                mcp = "agent_browser_select"
                if not sel:
                    status = "error"
                    obs = "선택할 목록의 화면 식별자가 없습니다"
                    missing.append(f"locator:{step_id}")
                else:
                    value = _resolve_input_value(step, inputs)
                    if step.get("valueStrategy") == "first_enabled":
                        html_result = _run_cli(["get", "html", sel], session=session, timeout=10)
                        option = re.search(
                            r"<option(?![^>]*\bdisabled\b)[^>]*\bvalue\s*=\s*['\"]([^'\"]+)['\"]",
                            str(html_result.get("stdout") or ""),
                            re.IGNORECASE,
                        )
                        value = option.group(1) if option else None
                    if value in (None, ""):
                        status = "warning"
                        obs = "화면에 선택 가능한 목록 값이 없어 선택하지 못했습니다"
                        missing.append(f"select_value:{step_id}")
                    else:
                        selected = _run_cli(["select", sel, str(value)], session=session, timeout=15)
                        if not selected.get("ok"):
                            status = "error"
                            obs = selected.get("stderr") or selected.get("stdout") or "목록 선택 실패"
                        else:
                            capture_as = str(step.get("captureAs") or "")
                            if capture_as:
                                binding_values[capture_as] = str(value)
                            obs = f"화면 목록에서 제공된 항목을 선택했습니다 ({capture_as or sel})"

            elif action in {"capture_value", "capture_collection"}:
                mcp = "agent_browser_get_text"
                capture_as = str(step.get("captureAs") or step_id)
                captured = _run_cli(["get", "text", sel], session=session, timeout=10) if sel else {"ok": False}
                value = str(captured.get("stdout") or "").strip()
                if captured.get("ok") and value:
                    binding_values[capture_as] = value
                    obs = f"업무 수행 전 화면 상태를 기록했습니다 ({capture_as})"
                else:
                    status = "warning"
                    obs = f"업무 수행 전 화면 상태를 기록하지 못했습니다 ({capture_as})"
                    missing.append(f"capture:{step_id}")

            elif action in {"verify_numeric_delta", "verify_collection_change"}:
                mcp = "agent_browser_get_text"
                expect = step.get("expect") if isinstance(step.get("expect"), dict) else {}
                criterion_id = str(step.get("criterionId") or step_id)
                current_result = _run_cli(["get", "text", sel], session=session, timeout=10) if sel else {"ok": False}
                current_text = str(current_result.get("stdout") or "").strip()
                before = str(_referenced_value(str(expect.get("beforeRef") or ""), inputs, binding_values) or "")
                met = False
                if action == "verify_numeric_delta":
                    delta = _referenced_value(str(expect.get("deltaFrom") or ""), inputs, binding_values)
                    before_number = _decimal_from_text(before)
                    after_number = _decimal_from_text(current_text)
                    delta_number = _decimal_from_text(delta)
                    direction = str(expect.get("direction") or "unknown")
                    signed_delta = (
                        -delta_number
                        if delta_number is not None and direction == "decrease"
                        else delta_number
                    )
                    met = bool(
                        current_result.get("ok")
                        and before_number is not None
                        and after_number is not None
                        and signed_delta is not None
                        and direction in {"increase", "decrease"}
                        and _numeric_delta_matches(before_number, after_number, signed_delta)
                    )
                    obs = (
                        f"화면 값 변화 확인: {before_number} → {after_number} (입력 변화량 {signed_delta})"
                        if met
                        else f"화면 값 변화 불일치: 이전 {before or '근거 없음'} · 이후 {current_text or '근거 없음'} · 입력 {delta or '근거 없음'}"
                    )
                else:
                    contains = _referenced_value(str(expect.get("containsFrom") or ""), inputs, binding_values)
                    selected = _referenced_value(str(expect.get("selectedFrom") or ""), inputs, binding_values)
                    selected_label = _selected_label(selected)
                    changed = bool(current_result.get("ok") and before and current_text and before != current_text)
                    wanted_number = _decimal_from_text(contains)
                    observed_numbers = [_decimal_from_text(item) for item in re.findall(r"[-+]?\s*\$?\s*[\d,]+(?:\.\d+)?", current_text)]
                    contains_value = wanted_number is None or any(
                        number is not None and abs(number) == abs(wanted_number) for number in observed_numbers
                    )
                    label_present = not selected_label or selected_label.lower() in current_text.lower()
                    met = changed and contains_value and label_present
                    obs = (
                        (
                            "업무 결과 목록에 이번 실행의 새 행·입력값"
                            f"·선택 항목 라벨({selected_label})이 함께 관측됐습니다"
                            if selected_label
                            else "업무 결과 목록에 이번 실행의 새 행과 입력값이 함께 관측됐습니다"
                        )
                        if met
                        else "업무 전후 목록 변화·실행 입력값·선택 항목 라벨 반영을 모두 확인하지 못했습니다"
                    )
                criteria_obs[criterion_id] = {
                    "result": "met" if met else "not_met",
                    "observed": obs,
                    "evidence": [f"step:{step_id}"],
                }
                if not met:
                    status = "warning"
                    missing.append(f"criterion:{criterion_id}")

            elif (
                action == "click"
                and step.get("destructive")
                and not bool((scenario.get("runPolicy") or {}).get("allowDestructive"))
            ):
                # 데이터를 만드는 트리거는 기본 차단 — 관측만 남긴다
                mcp = "agent_browser_click"
                status = "skipped"
                obs = (
                    f"{(step.get('request') or {}).get('path') or '대상'} 는 데이터를 생성할 수 있어"
                    " 자동 클릭을 차단했습니다"
                )
                missing.append("submit_blocked_destructive")

            elif action == "click":
                mcp = "agent_browser_click"
                form_state = (
                    _submission_precondition(session=session, selector=sel)
                    if step.get("destructive") and sel
                    else None
                )
                if form_state is not None and form_state.get("valid") is False:
                    status = "skipped"
                    input_precondition_invalid = True
                    missing.append("input_precondition_invalid")
                    obs = _submission_precondition_observation(form_state)
                    snap = _run_cli(["snapshot", "-i"], session=session)
                    last_snapshot = snap.get("stdout") or last_snapshot
                    snap_path = str(evidence_dir / f"{step_id}-precondition.snapshot.txt")
                    Path(snap_path).write_text(last_snapshot, encoding="utf-8")
                    snapshots.append(snap_path)
                    shot_idx += 1
                    shot_path = str(evidence_dir / f"{shot_idx:02d}-{step_id}-precondition.png")
                    if _run_cli(["screenshot", shot_path], session=session, timeout=20).get("ok") and Path(
                        shot_path
                    ).is_file():
                        screenshots.append(shot_path)
                    else:
                        shot_path = None
                        missing.append(f"screenshot:{step_id}")
                else:
                    snap = _run_cli(["snapshot", "-i"], session=session)
                    last_snapshot = snap.get("stdout") or ""
                    snap_path = str(evidence_dir / f"{step_id}-pre.snapshot.txt")
                    Path(snap_path).write_text(last_snapshot, encoding="utf-8")
                    snapshots.append(snap_path)
                    test_id = str((target or {}).get("value") or "")
                    ref_token = _find_ref(last_snapshot, test_id=test_id, role_hint="button") or sel
                    if not ref_token:
                        status = "error"
                        missing.append(f"locator:{step_id}")
                        obs = "click target not found"
                    else:
                        click_target = ref_token if str(ref_token).startswith("@") else (sel or ref_token)
                    # Prefer stable CSS testId when available (refs go stale across re-renders)
                        if sel and "data-testid" in str(sel):
                            click_target = sel
                        res = _run_cli(["click", str(click_target)], session=session)
                        ref = click_target
                        if not res["ok"]:
                            status = "error"
                            obs = res["stderr"] or res["stdout"] or "click failed"
                        else:
                            obs = f"clicked {click_target}"
                    # Prefer URL poll for A→B (avoid hanging wait --url)
                        concrete = str(inputs.get("customerId") or "").strip()
                        if concrete:
                            wait_url = _wait_url_contains(session, concrete, timeout_s=8)
                            if wait_url.get("ok"):
                                obs = f"{obs}; url={wait_url.get('stdout')}"
                            else:
                                obs = f"{obs}; url-wait pending ({wait_url.get('stdout')})"
                    # 입력 섬밋 직후 화면 — 증적 필수 2컷 중 하나
                        shot_idx += 1
                        shot_path = str(evidence_dir / f"{shot_idx:02d}-{step_id}-submitted.png")
                        if _run_cli(["screenshot", shot_path], session=session, timeout=20)["ok"] and Path(
                            shot_path
                        ).is_file():
                            screenshots.append(shot_path)
                            submitted_shot = shot_path
                        else:
                            shot_path = None
                            missing.append(f"screenshot:{step_id}")
                    # 클릭 후 화면이 거부 응답이면 성공으로 보지 않는다 (D-015)
                        post = _run_cli(["snapshot", "-i"], session=session)
                        last_snapshot = post.get("stdout") or last_snapshot
                        denial = detect_denial(last_snapshot)
                        if denial:
                            status = "warning"
                            obs = f"{obs}; 서버가 요청을 거부했습니다 ({denial['detail']})"
                            denied_signals.append(
                                {**denial, "stepId": step_id, "route": str((step.get("request") or {}).get("path") or "")}
                            )
                            missing.append(f"denied:{step_id}")

            elif action in {"wait_for_response", "wait"}:
                mcp = "agent_browser_wait_for_load"
                req = step.get("request") if isinstance(step.get("request"), dict) else {}
                _run_cli(["wait", "--load", "networkidle"], session=session, timeout=20)
                res = _run_cli(["get", "url"], session=session, timeout=8)
                current = (res.get("stdout") or "").strip()
                # 응답이 화면에 거부로 렌더됐는지 확인한다 — 도달만으로 정상이 아니다 (D-015)
                after = _run_cli(["snapshot", "-i"], session=session)
                last_snapshot = after.get("stdout") or last_snapshot
                snap_path = str(evidence_dir / f"{step_id}.snapshot.txt")
                Path(snap_path).write_text(last_snapshot, encoding="utf-8")
                snapshots.append(snap_path)
                denial = detect_denial(last_snapshot)
                if denial:
                    status = "warning"
                    obs = (
                        f"{str(req.get('method') or '')} {str(req.get('path') or '')} 요청 후 화면에"
                        f" 거부 응답이 보입니다 ({denial['detail']})"
                    ).strip()
                    denied_signals.append(
                        {**denial, "stepId": step_id, "route": str(req.get("path") or "")}
                    )
                    missing.append(f"denied:{step_id}")
                elif not res["ok"]:
                    status = "warning"
                    obs = "요청 후 화면 주소를 확인하지 못했습니다"
                else:
                    obs = f"요청 후 화면 = {current}"

            elif action in {"verify_navigation", "verify_binding"}:
                mcp = "agent_browser_snapshot"
                expect = step.get("expect") if isinstance(step.get("expect"), dict) else {}
                pattern = str(expect.get("routePattern") or "")
                if action == "verify_binding" and sel:
                    timeout_ms = int(step.get("timeoutMs") or 5000)
                    wait = _run_cli(
                        ["wait", "--selector", sel],
                        session=session,
                        timeout=max(2, int(timeout_ms / 1000) + 2),
                    )
                    if not wait.get("ok"):
                        status = "warning"
                if action == "verify_navigation":
                    concrete = str(inputs.get("customerId") or "").strip()
                    if concrete:
                        _wait_url_contains(session, concrete, timeout_s=4)
                snap = _run_cli(["snapshot", "-i"], session=session)
                last_snapshot = snap.get("stdout") or ""
                snap_path = str(evidence_dir / f"{step_id}.snapshot.txt")
                Path(snap_path).write_text(last_snapshot, encoding="utf-8")
                snapshots.append(snap_path)
                url_res = _run_cli(["get", "url"], session=session)
                current_url = (url_res.get("stdout") or "").strip()
                matched = True
                if pattern:
                    # Prefer concrete input id in URL when available (avoids /customers/search false positive)
                    concrete = str(inputs.get("customerId") or "").strip()
                    if concrete and concrete in current_url:
                        matched = True
                    else:
                        parts = []
                        for seg in pattern.split("/"):
                            if seg.startswith(":") and len(seg) > 1:
                                parts.append(r"[^/]+")
                            else:
                                parts.append(re.escape(seg))
                        regex = ".*/?" + "/".join(p for p in parts if p != "") + ".*"
                        matched = bool(re.search(regex, current_url))
                        # reject staying on search page for detail patterns
                        if matched and "/search" in current_url and ":customerId" in pattern:
                            matched = False
                if pattern and not matched:
                    missing.append(f"route:{pattern}")
                    status = "warning"
                    obs = f"url={current_url}; expected pattern {pattern} not confirmed"
                else:
                    obs = f"url={current_url}"
                if action == "verify_navigation" and step.get("criterionId"):
                    criterion_id = str(step.get("criterionId"))
                    criteria_obs[criterion_id] = {
                        "result": "met" if matched else "not_met",
                        "observed": (
                            f"기대 경로 {pattern}에 도달했습니다 ({current_url})"
                            if matched
                            else f"기대 경로 {pattern}에 도달하지 못했습니다 ({current_url})"
                        ),
                        "evidence": [f"step:{step_id}"],
                    }
                if action == "verify_binding":
                    field = str(expect.get("field") or "")
                    text_result = _run_cli(
                        ["get", "text", sel],
                        session=session,
                        timeout=max(2, int(step.get("timeoutMs") or 5000) // 1000),
                    )
                    observed = (text_result.get("stdout") or "").strip()
                    if field and text_result.get("ok") and observed:
                        binding_values[field] = observed
                        obs = f"binding {field}={observed}; {obs}"
                    else:
                        missing.append(f"ui_binding:{field or step_id}")
                        status = "warning"
                        obs = f"binding {field or step_id}=missing_data; {obs}"
                shot_idx += 1
                shot_path = str(evidence_dir / f"{shot_idx:02d}-result.png")
                shot = _run_cli(["screenshot", "--annotate", shot_path], session=session)
                if shot["ok"] and Path(shot_path).is_file():
                    screenshots.append(shot_path)
                else:
                    missing.append(f"screenshot:{step_id}")

            elif action == "assert_invalid":
                mcp = "agent_browser_eval_validity"
                criterion_id = str(step.get("criterionId") or step_id)
                if not sel:
                    status = "warning"
                    obs = "유효성 확인 대상 selector가 없습니다"
                    missing.append(f"selector:{step_id}")
                    met = False
                else:
                    script = (
                        "(() => { const el = document.querySelector("
                        + json.dumps(sel)
                        + "); return el ? {valid: el.checkValidity(), message: el.validationMessage} : null; })()"
                    )
                    checked = _run_cli(["eval", script], session=session, timeout=10)
                    payload = str(checked.get("stdout") or "")
                    met = bool(checked.get("ok") and re.search(r'"valid"\s*:\s*false', payload, re.I))
                    obs = (
                        "브라우저 입력 제약이 유효하지 않은 값을 요청 전에 차단했습니다"
                        if met
                        else "브라우저 입력 제약의 거부 상태를 확인하지 못했습니다"
                    )
                    if not met:
                        status = "warning"
                        missing.append(f"criterion:{criterion_id}")
                criteria_obs[criterion_id] = {
                    "result": "met" if met else "not_met",
                    "observed": obs,
                    "evidence": [f"step:{step_id}"],
                }

            elif action in {"assert_visible", "assert_text", "assert_absent"}:
                # 화면 구성 확인 · 세션 확인 — 기대 요소가 DOM에 있는지(없는지) 관측한다
                mcp = "agent_browser_snapshot"
                expect_absent = action == "assert_absent"
                selectors = [
                    str(s)
                    for s in ((target or {}).get("selectors") or ([sel] if sel else []))
                    if s
                ][:8]
                snap = _run_cli(["snapshot", "-i"], session=session)
                last_snapshot = snap.get("stdout") or ""
                snap_path = str(evidence_dir / f"{step_id}.snapshot.txt")
                Path(snap_path).write_text(last_snapshot, encoding="utf-8")
                snapshots.append(snap_path)
                dom_controls = parse_dom_controls(last_snapshot) or dom_controls
                if not selectors:
                    status = "warning"
                    obs = "기대 컨트롤 목록이 없어 관측 대상을 특정하지 못했습니다"
                    missing.append(f"selectors:{step_id}")
                else:
                    found: list[str] = []
                    absent: list[str] = []
                    follows_click = bool(
                        step_index > 0
                        and str(dsl_steps[step_index - 1].get("action") or "").lower() == "click"
                    )
                    for selector in selectors:
                        # Modal transitions and async rendering must be awaited by a
                        # visible-selector condition.  An immediate probe could inspect
                        # the hidden modal between the opener click and Bootstrap's
                        # transition completion, then let later commands interact with
                        # controls that the user never actually saw.
                        probe = (
                            _wait_visible(session, selector, timeout_s=3.0)
                            if follows_click and not expect_absent
                            else _run_cli(["is", "visible", selector], session=session, timeout=10)
                        )
                        visible = probe["ok"] and "true" in (probe.get("stdout") or "").lower()
                        (found if visible else absent).append(selector)
                    if action == "assert_text":
                        expect = step.get("expect") if isinstance(step.get("expect"), dict) else {}
                        wanted_text = str(expect.get("contains") or expect.get("text") or "")
                        text_result = _run_cli(["get", "text", selectors[0]], session=session, timeout=10)
                        observed_text = str(text_result.get("stdout") or "").strip()
                        met = bool(text_result.get("ok") and wanted_text and wanted_text in observed_text)
                        criterion_id = str(step.get("criterionId") or step_id)
                        obs = (
                            f"후속 화면 문구 관측: {wanted_text}"
                            if met
                            else f"기대 문구 미확인: {wanted_text or '근거 없음'}"
                        )
                        criteria_obs[criterion_id] = {
                            "result": "met" if met else "not_met",
                            "observed": obs,
                            "evidence": [f"step:{step_id}"],
                        }
                        if met:
                            remember_visible_controls(found)
                        else:
                            status = "warning"
                            missing.append(f"criterion:{criterion_id}")
                    elif expect_absent:
                        # 로그아웃처럼 「사라져야 정상」인 확인
                        if found:
                            status = "warning"
                            missing.extend(f"still_visible:{s}" for s in found)
                        obs = f"사라짐 확인 {len(absent)}/{len(selectors)}건" + (
                            f" · 아직 보임 {', '.join(found[:3])}" if found else ""
                        )
                        if step.get("sessionCheck"):
                            session_ended = not found
                    elif step.get("sessionCheck"):
                        # 세션 마커는 any-of — 접힌 메뉴 안의 마커까지 전부 보일 필요는 없다
                        remember_visible_controls(found)
                        session_established = bool(found)
                        obs = (
                            f"로그인 세션 확인 — 인증 전용 요소 {len(found)}/{len(selectors)}건 관측"
                            if found
                            else "로그인 세션을 확인하지 못했습니다 (인증 전용 요소 없음)"
                        )
                        if not found:
                            status = "error" if step.get("blocking") else "warning"
                            missing.append("session_not_established")
                            if step.get("blocking"):
                                blocked_by_precondition = True
                    else:
                        remember_visible_controls(found)
                        if absent:
                            status = "warning"
                            missing.extend(f"ui_control:{s}" for s in absent)
                        obs = f"표시 확인 {len(found)}/{len(selectors)}건" + (
                            f" · 미확인 {', '.join(absent[:3])}" if absent else ""
                        )
                shot_idx += 1
                shot_path = str(evidence_dir / f"{shot_idx:02d}-{step_id}-composition.png")
                if _run_cli(["screenshot", shot_path], session=session, timeout=20)["ok"] and Path(
                    shot_path
                ).is_file():
                    screenshots.append(shot_path)
                else:
                    shot_path = None
                    missing.append(f"screenshot:{step_id}")

            else:
                mcp = "agent_browser_snapshot"
                status = "skipped"
                obs = f"unsupported action {action}"
                missing.append(f"action:{action}")

        except Exception as exc:  # noqa: BLE001
            status = "error"
            obs = str(exc)
            # failure screenshot
            shot_idx += 1
            shot_path = str(evidence_dir / f"{shot_idx:02d}-failure.png")
            _run_cli(["screenshot", shot_path], session=session)
            if Path(shot_path).is_file():
                screenshots.append(shot_path)
            snap = _run_cli(["snapshot", "-i"], session=session)
            snap_path = str(evidence_dir / f"{step_id}-failure.snapshot.txt")
            Path(snap_path).write_text(snap.get("stdout") or "", encoding="utf-8")
            snapshots.append(snap_path)

        record_step(
            step_id,
            action,
            mcp,
            status=status,
            ref=ref,
            started=started,
            ended=_now(),
            snapshot_path=snap_path,
            screenshot_path=shot_path,
            observation=obs,
            missing_data=[m for m in missing if m == "input_precondition_invalid" or m.endswith(step_id) or m.startswith(f"locator:{step_id}") or m.startswith(f"screenshot:{step_id}") or m.startswith(f"route:")],
        )

        if blocked_by_precondition:
            # 선행 조건(로그인 세션)이 성립하지 않으면 본 단계를 실행하지 않는다 (D-015)
            break

        if input_precondition_invalid:
            # The browser would not submit this form. Continuing with success/delta/list
            # assertions would only create three duplicate symptoms for one root cause.
            break

        if status == "error" and action in {"navigate", "fill", "click"}:
            # continue to capture failure evidence on next soft steps; break hard errors on open
            if action == "navigate":
                break

    # ── DOM 관측 기반 입력 바인딩 ────────────────────────────────────────────
    # 화면 구성 확인(UI) 케이스는 DSL에 fill 단계가 없다. 그래서 실제 화면을 관측해
    # 입력 컨트롤을 찾고, 연결 계정·LLM 제안·이름 규칙 순서로 값을 채운 뒤 증적을 남긴다.
    has_fill_step = any(str(s.get("action") or "").lower() == "fill" for s in dsl_steps)
    route_hint = str((scenario.get("source") or {}).get("route") or "").lower()
    case_id = str(scenario.get("caseId") or "").upper()
    service_id = str(scenario.get("serviceId") or "").lower()
    ui_composition_only = "-UI-" in case_id or service_id.endswith("-ui")
    if nav_done and not cancelled and not has_fill_step and not ui_composition_only:
        started = _now()
        snap = _run_cli(["snapshot", "-i"], session=session)
        last_snapshot = snap.get("stdout") or ""
        probe_path = evidence_dir / "dom-probe.snapshot.txt"
        probe_path.write_text(last_snapshot, encoding="utf-8")
        snapshots.append(str(probe_path))
        dom_controls = parse_dom_controls(last_snapshot)
        fillables = [c for c in dom_controls if c["role"] in FILLABLE_ROLES]
        llm_map = (
            llm_bind_controls(controls=fillables, scenario=scenario, url=route_url(base_url, route_hint))
            if fillables
            else {}
        )
        filled_count = 0
        # 접근성 이름이 없는 입력은 DOM 순서·마스킹 관측으로 계정 입력인지 판별한다
        ident_ctl, pw_ctl_probe = login_controls(dom_controls)
        for index, control in enumerate(fillables):
            name = control["name"]
            # 이름 없는 입력도 사람이 읽을 라벨은 있어야 한다 (관측 위치 기준)
            label = name or (
                "계정 비밀번호"
                if control is pw_ctl_probe
                else "계정 ID"
                if control is ident_ctl
                else f"{index + 1}번째 입력({control['ref'] or 'ref 없음'})"
            )
            cred = credential_for(name, connection)
            observed_value = str(control.get("currentValue") or "")
            if not cred and not name:
                if control is pw_ctl_probe and connection.get("loginPassword"):
                    cred = (connection["loginPassword"], "화면에서 가려진 입력(●●●)으로 관측 · 연결 계정 비밀번호")
                elif control is ident_ctl and connection.get("loginId"):
                    cred = (connection["loginId"], "로그인 입력 순서로 관측 · 연결 계정 ID")
            if cred:
                value, reason, source = cred[0], cred[1], "connection_account"
            elif observed_value and not is_masked_value(observed_value):
                # 화면이 이미 채워둔 값 — 추정이 아니라 관측값이므로 그대로 쓴다
                value = observed_value
                reason = "화면에 이미 입력된 값을 관측해 그대로 사용"
                source = "dom_observed_default"
            elif name in llm_map:
                value, reason, source = llm_map[name]["value"], llm_map[name]["rationale"], "llm_dom_bind"
            else:
                made = synthesize_for(name)
                if not made:
                    dom_bindings.append(
                        {
                            "stepId": "D1",
                            "field": label,
                            "locator": control["ref"] or label,
                            "value": None,
                            "source": "missing_data",
                            "rationale": "DOM 이름·화면 관측값에서 값을 만들 근거가 없습니다",
                            "filled": False,
                        }
                    )
                    missing.append(f"dom_input:{label}")
                    continue
                value, reason, source = made[0], made[1], "derived_synthetic"
            locator = control["ref"] or f'text="{name}"'
            res = _run_cli(["fill", str(locator), str(value)], session=session)
            secret_field = is_password_control(name) or control is pw_ctl_probe
            dom_bindings.append(
                {
                    "stepId": "D1",
                    "field": label,
                    "locator": str(locator),
                    "value": "***" if secret_field else str(value),
                    "source": source,
                    "rationale": reason,
                    "filled": bool(res["ok"]),
                }
            )
            if res["ok"]:
                filled_count += 1
        if fillables:
            shot_idx += 1
            input_shot = str(evidence_dir / f"{shot_idx:02d}-input-completed.png")
            if _run_cli(["screenshot", input_shot], session=session, timeout=20)["ok"] and Path(
                input_shot
            ).is_file():
                screenshots.append(input_shot)
                submitted_shot = submitted_shot or input_shot
            record_step(
                "D1",
                "dom_bind",
                "agent_browser_fill",
                status="ok" if filled_count else "warning",
                started=started,
                ended=_now(),
                snapshot_path=str(probe_path),
                screenshot_path=input_shot if Path(input_shot).is_file() else None,
                observation=(
                    f"화면에서 입력 컨트롤 {len(fillables)}개 관측 · {filled_count}개 자동 입력"
                    if filled_count
                    else f"입력 컨트롤 {len(fillables)}개 관측 · 값 바인딩 근거 부족"
                ),
            )
            # 섬밋은 데이터를 만들 수 있으므로 destructive 화면에서는 하지 않는다
            destructive = any(hint in route_hint for hint in DESTRUCTIVE_ROUTE_HINTS)
            submit = next(
                (
                    c
                    for c in dom_controls
                    if c["role"] == "button"
                    and any(hint in c["name"].lower() for hint in SUBMIT_NAME_HINTS)
                ),
                None,
            )
            started = _now()
            if destructive:
                record_step(
                    "D2",
                    "submit_skipped",
                    "agent_browser_click",
                    status="skipped",
                    started=started,
                    ended=_now(),
                    observation=f"{route_hint} 화면은 데이터를 생성할 수 있어 자동 섬밋을 차단했습니다",
                    missing_data=["submit_blocked_destructive"],
                )
                missing.append("submit_blocked_destructive")
            elif submit and filled_count:
                res = _run_cli(["click", str(submit["ref"] or f'text="{submit["name"]}"')], session=session)
                _run_cli(["wait", "--load", "networkidle"], session=session, timeout=15)
                url_res = _run_cli(["get", "url"], session=session, timeout=8)
                shot_idx += 1
                result_shot = str(evidence_dir / f"{shot_idx:02d}-result.png")
                if _run_cli(["screenshot", result_shot], session=session, timeout=20)["ok"] and Path(
                    result_shot
                ).is_file():
                    screenshots.append(result_shot)
                else:
                    result_shot = None
                    missing.append("screenshot:D2")
                snap2 = _run_cli(["snapshot", "-i"], session=session)
                after = evidence_dir / "D2.snapshot.txt"
                after.write_text(snap2.get("stdout") or "", encoding="utf-8")
                snapshots.append(str(after))
                record_step(
                    "D2",
                    "submit",
                    "agent_browser_click",
                    status="ok" if res["ok"] else "warning",
                    ref=str(submit["ref"] or submit["name"]),
                    started=started,
                    ended=_now(),
                    snapshot_path=str(after),
                    screenshot_path=result_shot,
                    observation=f"「{submit['name']}」 클릭 후 화면 = {(url_res.get('stdout') or '').strip()}",
                )

    # 결과 화면 증적은 최소 1컷 보장 (입력 직후 + 결과 2컷 원칙)
    if nav_done and not result_shot:
        shot_idx += 1
        tail = str(evidence_dir / f"{shot_idx:02d}-result.png")
        if _run_cli(["screenshot", "--full", tail], session=session, timeout=20)["ok"] and Path(tail).is_file():
            screenshots.append(tail)
            result_shot = tail

    current_url_result = _run_cli(["get", "url"], session=session, timeout=8)
    current_url = (current_url_result.get("stdout") or "").strip()
    network_requests, matched_network_requests = collect_network_evidence(
        session=session,
        base_url=base_url,
        expected=expected_network,
    )
    if not network_requests:
        missing.append("network_requests")
    expected_by_key = {
        (str(row.get("method") or "").upper(), str(row.get("path") or "")): row
        for row in matched_network_requests
    }
    for step in steps_out:
        request = next(
            (
                raw.get("request")
                for raw in dsl_steps
                if str(raw.get("id") or "") == str(step.get("stepId") or "")
                and isinstance(raw.get("request"), dict)
            ),
            None,
        )
        if not request:
            continue
        key = (
            str(request.get("method") or "").upper(),
            str(request.get("path") or "").split("?", 1)[0],
        )
        network = expected_by_key.get(key)
        if network:
            step["networkRefs"] = [str(network.get("networkId"))]
    binding_values["matchedNetworkRequests"] = matched_network_requests

    errored = any(s["status"] == "error" for s in steps_out)
    # 기대 결과 대조 판정 — 「도달」은 성공 근거가 아니다 (D-015)
    binding_values["criterionObservations"] = criteria_obs
    verdict = evaluate_verdict(
        scenario=scenario,
        steps=steps_out,
        session_established=session_established,
        session_ended=session_ended,
        blocked_by_precondition=blocked_by_precondition,
        input_precondition_invalid=input_precondition_invalid,
        denied_signals=denied_signals,
        binding_values=binding_values,
        missing=missing,
    )
    if cancelled:
        final_status = "CANCELLED"
    elif errored or verdict["verdict"] == "expected_not_met":
        final_status = "AUTO_FAILED"
    else:
        final_status = "WAITING_FOR_REVIEW"

    summary = {
        # 스크립트가 끝까지 실행됐다는 사실과 기대 결과 충족은 다르다.
        # 기대 불충족은 반드시 ok=false로 보존해 상위 계층이 정상 관측으로
        # 다시 승격하지 못하게 한다.
        "ok": (
            not errored
            and not cancelled
            and verdict["verdict"] != "expected_not_met"
        ),
        "status": final_status,
        "runId": run_id,
        "scenarioId": scenario.get("scenarioId"),
        "browserRunner": "agent-browser-cli",
        "generatorVersion": GENERATOR_VERSION,
        "baseUrl": base_url,
        "inputs": inputs,
        "headers": {k: v for k, v in headers.items()},
        "steps": steps_out,
        "screenshots": screenshots,
        "snapshots": snapshots,
        "networkRequests": network_requests,
        "matchedNetworkRequests": matched_network_requests,
        "currentUrl": current_url,
        "bindingValues": binding_values,
        # 실행이 실제로 화면에 넣은 값과 근거 (비밀번호는 ***)
        "inputBindings": dom_bindings,
        "domControls": dom_controls,
        "submittedScreenshot": submitted_shot,
        "resultScreenshot": result_shot,
        "connection": {
            "browser": connection.get("browser") or "chrome",
            "loginId": connection.get("loginId"),
            "hasLoginSecret": bool(connection.get("loginPassword")),
        },
        "missing_data": sorted(set(missing)),
        # 세션 선행조건·기대결과 판정 (D-015)
        "sessionPolicy": str(scenario.get("sessionPolicy") or ("login_then_reuse" if scenario.get("authRequired") else "no_auth")),
        "authRequired": bool(scenario.get("authRequired")),
        "sessionEstablished": session_established,
        "sessionEnded": session_ended,
        "verdict": verdict,
        "observationSummary": verdict["reason"],
        "hitlRequired": True,
        "autoPassForbidden": True,
        "evidenceDir": str(evidence_dir),
        "generatedAt": _now(),
    }
    # 연결 비밀번호는 결과·증적 어디에도 남기지 않는다
    summary = mask_secret_values(summary, [str(connection.get("loginPassword") or "")])
    (evidence_dir / "run-result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_progress(
        progress_path,
        run_id=run_id,
        steps=steps_out,
        planned_total=planned_total,
        status=final_status,
    )
    return summary


def execute_scenario(
    *,
    scenario: dict[str, Any],
    inputs: dict[str, Any],
    base_url: str,
    run_id: str,
    consent: bool,
    evidence_dir: Path,
    headers: dict[str, str] | None = None,
    headed: bool = False,
    session: str | None = None,
    progress_path: Path | None = None,
    connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one scenario and always release an opened agent-browser session."""
    resolved_session = session or f"run-{run_id[:12]}"
    kwargs = {
        "scenario": scenario,
        "inputs": inputs,
        "base_url": base_url,
        "run_id": run_id,
        "consent": consent,
        "evidence_dir": evidence_dir,
        "headers": headers,
        "headed": headed,
        "session": resolved_session,
        "progress_path": progress_path,
        "connection": connection,
    }
    # No browser process is opened when consent is absent.  In particular, do not
    # close a caller-provided reusable session that this invocation did not acquire.
    if not consent:
        return _execute_scenario_impl(**kwargs)
    try:
        return _execute_scenario_impl(**kwargs)
    finally:
        _close_browser_session(resolved_session)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = _load_json(args.input)
    if not isinstance(payload, dict):
        print("input must be object", file=sys.stderr)
        return 2

    scenario = payload.get("scenario") or _load_json(payload.get("scenarioPath"))
    if not isinstance(scenario, dict) or not scenario:
        print("scenario required", file=sys.stderr)
        return 2

    run_id = str(payload.get("runId") or f"RUN-{uuid4().hex[:12]}")
    evidence = Path(
        str(payload.get("evidenceDir") or Path(__file__).resolve().parents[5] / "artifacts" / "evidence" / "runs" / run_id)
    ).expanduser().resolve()

    result = execute_scenario(
        scenario=scenario,
        inputs=dict(payload.get("inputs") or {}),
        base_url=str(payload.get("baseUrl") or os.environ.get("QA_SAMPLE_FE_URL") or DEFAULT_BASE),
        run_id=run_id,
        consent=bool(payload.get("consent")),
        evidence_dir=evidence,
        headers=dict(payload.get("headers") or {}),
        headed=bool(payload.get("headed")),
        session=payload.get("session"),
        connection=dict(payload.get("connection") or {}),
        progress_path=(
            Path(str(payload["progressPath"])).expanduser().resolve()
            if payload.get("progressPath")
            else None
        ),
    )

    # The browser runner captures the screen; the project-selected VLM turns the
    # final screenshot into a structured observation. It never decides HITL Pass/Fail.
    visual_path = str(result.get("resultScreenshot") or "")
    if visual_path and Path(visual_path).is_file() and os.environ.get("LLM_ENABLED") == "1":
        image_bytes = Path(visual_path).read_bytes()
        visual_observation = get_llm_client().vision_json(
            system=(
                "당신은 실행 증적 화면 관측 보조자입니다. 화면에 실제로 보이는 제목, 상태, "
                "주요 컨트롤만 JSON으로 기록하고 Pass/Fail을 확정하지 마세요."
            ),
            prompt=(
                "agent-browser가 남긴 최종 화면입니다. "
                '{"screenTitle":"", "visibleStates":[], "controls":[], "uncertainties":[]} 형식으로 답하세요.'
            ),
            image_data_url=f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}",
            timeout_s=60.0,
        )
        if visual_observation:
            result["visualObservation"] = visual_observation
            result["visualObservationModel"] = os.environ.get("LLM_MODEL")
        else:
            result.setdefault("missing_data", []).append("visual_model_observation")
        (evidence / "run-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    wrapper = {
        "ok": result.get("ok"),
        "skill": "browser_execute",
        "tool": "execute_run",
        "runId": run_id,
        "status": result.get("status"),
        "artifactPath": str(evidence / "run-result.json"),
        "result": result,
    }
    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wrapper, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result.get("status"), "runId": run_id}))
    return 0 if result.get("status") != "CANCELLED" or result.get("ok") else 0


if __name__ == "__main__":
    raise SystemExit(main())
