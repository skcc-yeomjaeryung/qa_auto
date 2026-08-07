#!/usr/bin/env python3
"""Extract Flask/Jinja screen routes + HTML UI controls (e.g. bank-of-anthos login)."""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

ROUTE_RE = re.compile(
    r"""@(?:app|bp|blueprint)\.route\(\s*['"]([^'"]+)['"](?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?""",
    re.IGNORECASE,
)
RENDER_RE = re.compile(r"""render_template\(\s*['"]([^'"]+)['"]""")

# 인증 게이트 근거 — 핸들러 본문에서 토큰 검증·로그인 리다이렉트를 관측한다 (D-015).
AUTH_GUARD_RE = re.compile(
    r"""(?:verify_token|login_required|current_user\.is_authenticated|token_required|"""
    r"""jwt_required|@login_required)""",
    re.IGNORECASE,
)
# 인증 실패 처리 — 로그인 화면으로 되돌리거나 401/403으로 거부하면 인증 뒤 경로다
AUTH_DENY_RE = re.compile(
    r"""(?:login_page|url_for\(\s*['"]login['"]|redirect\([^)]*login|abort\(\s*40[13]\b"""
    r"""|status_code\s*=\s*40[13]\b)""",
    re.IGNORECASE,
)
# 템플릿의 POST form — 로그아웃처럼 「직접 URL 진입이 불가능한」 동작의 실제 트리거 근거.
FORM_RE = re.compile(
    r"""<form([^>]*)>(.*?)</form>""",
    re.IGNORECASE | re.DOTALL,
)
ATTR_RE = re.compile(r"""([a-zA-Z_:.-]+)\s*=\s*['"]([^'"]*)['"]""")
TRIGGER_RE = re.compile(
    r"""<(a|button)([^>]*)>(.*?)</\1>""",
    re.IGNORECASE | re.DOTALL,
)


class _FormControlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict[str, Any]] = []
        self._label_for: dict[str, str] = {}
        self._current_label_for: str | None = None
        self._label_buf: list[str] = []
        self._current_button: dict[str, Any] | None = None
        self._button_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        if tag == "label":
            self._current_label_for = ad.get("for") or None
            self._label_buf = []
            return
        if tag == "input":
            el_id = ad.get("id") or ""
            name = ad.get("name") or el_id
            if not name and not el_id:
                return
            selector = f"#{el_id}" if el_id else f"input[name='{name}']"
            label = self._label_for.get(el_id) or self._label_for.get(name) or name or el_id
            self.controls.append(
                {
                    "name": label,
                    "field": name or el_id,
                    "selector": selector,
                    "type": ad.get("type") or "text",
                    "required": "required" in ad,
                    "pattern": ad.get("pattern") or None,
                    "min": ad.get("min") or None,
                    "max": ad.get("max") or None,
                    "step": ad.get("step") or None,
                    "kind": "input",
                }
            )
            return
        if tag == "select":
            el_id = ad.get("id") or ""
            name = ad.get("name") or el_id
            if not name and not el_id:
                return
            selector = f"#{el_id}" if el_id else f"select[name='{name}']"
            self.controls.append(
                {
                    "name": self._label_for.get(el_id) or self._label_for.get(name) or name,
                    "field": name,
                    "selector": selector,
                    "type": "select",
                    "required": "required" in ad,
                    "kind": "select",
                }
            )
            return
        if tag == "button":
            btn_type = (ad.get("type") or "submit").lower()
            el_id = ad.get("id") or ""
            if btn_type == "submit" or "sign" in (ad.get("class") or "").lower():
                test_id = ad.get("data-testid") or ""
                field_name = ad.get("name") or ""
                form_action = ad.get("formaction") or ""
                if el_id:
                    selector = f"#{el_id}"
                elif test_id:
                    selector = f"button[data-testid='{test_id}']"
                elif field_name:
                    selector = f"button[name='{field_name}']"
                elif form_action:
                    # Jinja 변수 전의 정적 prefix는 실제 렌더 뒤에도 유지된다. 같은 form에
                    # Approve/Deny 버튼이 있어도 각각 식별할 수 있다.
                    static_prefix = form_action.split("{{", 1)[0].rstrip("&?")
                    selector = (
                        f"button[formaction^='{static_prefix}']"
                        if static_prefix
                        else "button[type='submit']"
                    )
                else:
                    selector = "button[type='submit']"
                control = {
                    "name": "Sign in" if "sign" in (ad.get("class") or "").lower() else "Submit",
                    "field": field_name or el_id or "submit",
                    "selector": selector,
                    "type": "submit",
                    "required": False,
                    "kind": "button",
                    "accessibleName": None,
                }
                self.controls.append(control)
                self._current_button = control
                self._button_buf = []
            return
        if tag == "a" and ad.get("id"):
            # secondary CTA (e.g. create account) — optional
            return

    def handle_data(self, data: str) -> None:
        if self._current_label_for is not None:
            self._label_buf.append(data)
        if self._current_button is not None:
            self._button_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._current_label_for is not None:
            text = " ".join(self._label_buf).strip()
            if text:
                self._label_for[self._current_label_for] = text
            self._current_label_for = None
            self._label_buf = []
        if tag == "button" and self._current_button is not None:
            text = " ".join(" ".join(self._button_buf).split()).strip()
            if text:
                self._current_button["name"] = text
                self._current_button["accessibleName"] = text
                if self._current_button.get("field") == "submit":
                    self._current_button["field"] = text
            self._current_button = None
            self._button_buf = []


def _parse_template_controls(html_path: Path) -> list[dict[str, Any]]:
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    parser = _FormControlParser()
    try:
        parser.feed(text)
    except Exception:  # noqa: BLE001
        return []
    # Prefer explicit login ids when present
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in parser.controls:
        # CSS identity is preferred.  A generic selector can legitimately identify
        # multiple controls, so retain distinct accessible names instead of collapsing
        # every submit button into one synthetic "Submit" control.
        key = f"{c['selector']}::{c.get('accessibleName') or c.get('name') or ''}"
        if key in seen:
            continue
        seen.add(key)
        # Fix Sign in label from button text if generic
        if c.get("kind") == "button" and c.get("selector") == "button[type='submit']":
            if re.search(r">\s*Sign in\s*<", text, re.I):
                c["name"] = "Sign in"
        out.append(c)
    return out


def _parse_form_controls(form_html: str, form_selector: str | None) -> list[dict[str, Any]]:
    parser = _FormControlParser()
    try:
        parser.feed(form_html)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in parser.controls:
        control = dict(item)
        if (
            form_selector
            and control.get("kind") == "button"
            and control.get("selector") == "button[type='submit']"
        ):
            control["selector"] = f"{form_selector} button[type='submit']"
        key = f"{control.get('selector')}::{control.get('accessibleName') or control.get('name')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(control)
    return out


def _parse_output_bindings(html_path: Path, workspace: Path) -> list[dict[str, Any]]:
    """Preserve Jinja-rendered state containers for post-action assertions."""
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rel = str(html_path.relative_to(workspace))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"""<([a-zA-Z][\w:-]*)\b([^>]*\bid\s*=\s*['\"]([^'\"]+)['\"][^>]*)>""",
        text,
    ):
        close_at = text.find(f"</{match.group(1)}>", match.end())
        if close_at < 0:
            continue
        body = text[match.end() : close_at]
        if "{{" not in body and "{%" not in body:
            continue
        expressions = re.findall(r"(?:\{\{|\{%)(.*?)(?:\}\}|%\})", body, re.DOTALL)
        identifiers: list[str] = []
        for expression in expressions:
            for token in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", expression):
                if token in {"if", "elif", "else", "endif", "for", "in", "endfor", "none", "true", "false"}:
                    continue
                if token not in identifiers:
                    identifiers.append(token)
        if not identifiers:
            continue
        selector = f"#{match.group(3)}"
        if selector in seen:
            continue
        seen.add(selector)
        out.append(
            {
                "selector": selector,
                "bindings": identifiers[:8],
                "kind": "collection" if "for " in body else "value",
                "evidence": {
                    "file": rel,
                    "line": text[: match.start()].count("\n") + 1,
                    "extractor": "jinja-output-binding",
                    "confidence": 0.9,
                },
            }
        )
    return out


def _modal_context(text: str, form_start: int, form_body: str) -> dict[str, Any]:
    """Find an evidenced modal and the UI control that opens it."""
    modal: tuple[int, dict[str, str]] | None = None
    for match in re.finditer(r"<div\b([^>]*)>", text[:form_start], re.IGNORECASE):
        attrs = {k.lower(): v for k, v in ATTR_RE.findall(match.group(1))}
        if attrs.get("id") and "modal" in str(attrs.get("class") or "").lower():
            modal = (match.start(), attrs)
    if not modal:
        return {}
    modal_start, attrs = modal
    modal_id = attrs["id"]
    target = f"#{modal_id}"
    opener_selector = None
    opener_label = None
    for match in re.finditer(r"<([a-zA-Z][\w:-]*)\b([^>]*)>", text[:modal_start], re.IGNORECASE):
        tag_attrs = {k.lower(): v for k, v in ATTR_RE.findall(match.group(2))}
        if tag_attrs.get("data-target") != target:
            continue
        opener_selector = _selector_for(tag_attrs, fallback_tag=match.group(1).lower()) or f"[data-target='{target}']"
        tag = match.group(1).lower()
        nearby = text[match.end() : match.end() + 800]
        # The opener itself owns the accessible label.  Stopping only at the next
        # </div> accidentally swallowed an adjacent modal when the opener was a button.
        label_source = nearby.split(f"</{tag}>", 1)[0]
        label = re.sub(r"<[^>]+>", " ", label_source)
        opener_label = " ".join(html_lib.unescape(label).split()) or None
    modal_evidence = text[modal_start:form_start] + form_body
    title_match = re.search(
        r"<[^>]*class\s*=\s*['\"][^'\"]*modal-title[^'\"]*['\"][^>]*>(.*?)</[^>]+>",
        modal_evidence,
        re.IGNORECASE | re.DOTALL,
    )
    title = " ".join(re.sub(r"<[^>]+>", " ", title_match.group(1)).split()) if title_match else None
    return {
        "modalSelector": target,
        "modalTitle": html_lib.unescape(title) if title else None,
        "openerSelector": opener_selector,
        "openerLabel": opener_label,
    }


def _parse_navigation_links(html_path: Path, workspace: Path) -> list[dict[str, Any]]:
    """Extract only evidenced, internal navigation CTAs from a Jinja template.

    A signup journey must not begin at an invented URL.  When the source contains
    `<a href="/signup" id="create-account-btn">`, preserve the source template,
    selector and target route so the scenario DSL can model screen → click → screen.
    """
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rel = str(html_path.relative_to(workspace))
    links: list[dict[str, Any]] = []
    for match in TRIGGER_RE.finditer(text):
        if match.group(1).lower() != "a":
            continue
        attrs = {k.lower(): v for k, v in ATTR_RE.findall(match.group(2))}
        href = str(attrs.get("href") or "").strip()
        if not href.startswith("/") or href.startswith("//"):
            continue
        selector = _selector_for(attrs, fallback_tag="a")
        if not selector:
            continue
        label = re.sub(r"<[^>]+>", " ", match.group(3))
        label = " ".join(label.split()) or href
        links.append(
            {
                "label": label,
                "selector": selector,
                "targetRoute": href.split("?", 1)[0].split("#", 1)[0] or "/",
                "evidence": {
                    "file": rel,
                    "line": text[: match.start()].count("\n") + 1,
                    "extractor": "jinja-navigation-link",
                    "confidence": 0.95,
                },
            }
        )
    return links


def _selector_for(attrs: dict[str, str], *, fallback_tag: str) -> str | None:
    if attrs.get("id"):
        return f"#{attrs['id']}"
    if attrs.get("data-testid"):
        return f"[data-testid='{attrs['data-testid']}']"
    if attrs.get("name"):
        return f"{fallback_tag}[name='{attrs['name']}']"
    return None


def _dropdown_opener(text: str, form_start: int) -> str | None:
    """form을 감싼 접힌 메뉴의 여는 컨트롤을 찾는다.

    Bootstrap 계열은 `<div class="dropdown-menu" aria-labelledby="accountDropdown">`처럼
    여는 컨트롤 id를 명시한다. 근거가 이렇게 있을 때만 선행 클릭 단계를 만든다.
    """
    head = text[max(0, form_start - 600) : form_start]
    hits = re.findall(
        r"""<[^>]*(?:dropdown-menu|collapse)[^>]*aria-labelledby\s*=\s*['"]([^'"]+)['"]""",
        head,
        re.IGNORECASE,
    )
    if hits:
        return f"#{hits[-1]}"
    return None


def _parse_action_forms(html_path: Path, workspace: Path) -> list[dict[str, Any]]:
    """POST form과 그 안의 실제 클릭 트리거를 추출한다.

    로그아웃처럼 서버가 GET 직접 진입을 거부하는 동작은 URL 이동이 아니라
    이 form의 트리거를 클릭해야 성립한다 (D-015 · 실제 사용자 이벤트).
    """
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rel = str(html_path.relative_to(workspace))
    out: list[dict[str, Any]] = []
    for match in FORM_RE.finditer(text):
        attrs = {k.lower(): v for k, v in ATTR_RE.findall(match.group(1))}
        method = (attrs.get("method") or "GET").upper()
        action = attrs.get("action") or ""
        if method == "GET" or not action.startswith("/"):
            continue
        form_selector = _selector_for(attrs, fallback_tag="form")
        body = match.group(2)
        trigger_selector = None
        trigger_label = None
        fallback_trigger: tuple[str, str | None] | None = None
        for t in TRIGGER_RE.finditer(body):
            t_attrs = {k.lower(): v for k, v in ATTR_RE.findall(t.group(2))}
            label = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", t.group(3))).split())
            is_submit = t.group(1).lower() == "button" and (t_attrs.get("type") or "submit").lower() == "submit"
            selector = _selector_for(t_attrs, fallback_tag=t.group(1).lower())
            if not selector and form_selector:
                selector = f"{form_selector} button[type='submit']" if is_submit else f"{form_selector} {t.group(1).lower()}"
            if selector and is_submit:
                trigger_selector = selector
                trigger_label = label or None
                break
            if selector and fallback_trigger is None:
                fallback_trigger = (selector, label or None)
        if not trigger_selector and fallback_trigger:
            trigger_selector, trigger_label = fallback_trigger
        if not trigger_selector and form_selector:
            trigger_selector = f"{form_selector} button[type='submit']"
        line = text[: match.start()].count("\n") + 1
        modal_context = _modal_context(text, match.start(), body)
        opener_selector = modal_context.get("openerSelector") or _dropdown_opener(text, match.start())
        out.append(
            {
                "action": action,
                "method": method,
                "formSelector": form_selector,
                "triggerSelector": trigger_selector,
                "triggerLabel": trigger_label,
                "formControls": _parse_form_controls(match.group(0), form_selector),
                **modal_context,
                # 접힌 메뉴 안의 트리거는 먼저 그 메뉴를 열어야 눌린다
                "openerSelector": opener_selector,
                "evidence": {
                    "file": rel,
                    "line": line,
                    "extractor": "jinja-form-action",
                    "confidence": 0.85 if trigger_selector else 0.6,
                },
            }
        )
    return out


def _parse_conditional_blocks(html_path: Path, workspace: Path) -> list[dict[str, Any]]:
    """`{% if %}` 블록과 그 안의 id 요소·POST form action을 함께 모은다.

    조건부 블록 중 **인증 전용 동작(form)** 을 품은 블록만 나중에 세션 마커로 채택한다.
    조건 없이 항상 보이는 요소는 세션 근거가 되지 못한다 (D-015).
    """
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rel = str(html_path.relative_to(workspace))
    out: list[dict[str, Any]] = []
    for block in re.finditer(r"\{%\s*if\s+([^%]+)%\}(.*?)\{%\s*endif\s*%\}", text, re.DOTALL):
        body = block.group(2)
        actions = [
            (attrs.get("action") or "").split("?")[0]
            for attrs in (
                {k.lower(): v for k, v in ATTR_RE.findall(f.group(1))} for f in FORM_RE.finditer(body)
            )
            if (attrs.get("method") or "GET").upper() != "GET"
        ]
        ids = [
            f"#{el.group(1)}"
            for el in re.finditer(r"""<[a-zA-Z]+[^>]*\bid\s*=\s*['"]([^'"]+)['"]""", body)
        ]
        if not ids:
            continue
        out.append(
            {
                "condition": block.group(1).strip(),
                "formActions": [a for a in actions if a.startswith("/")],
                "selectors": ids,
                "evidence": {
                    "file": rel,
                    "line": text[: block.start()].count("\n") + 1,
                    "extractor": "jinja-auth-block",
                    "confidence": 0.75,
                },
            }
        )
    return out


def _find_templates_dir(workspace: Path) -> Path | None:
    candidates = [
        workspace / "src" / "frontend" / "templates",
        workspace / "frontend" / "templates",
        workspace / "templates",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    # shallow search
    for p in workspace.rglob("templates"):
        if p.is_dir() and any(p.glob("*.html")):
            return p
    return None


def _controls_for_template(
    tmpl_name: str | None,
    tmpl_dir: Path | None,
    workspace: Path,
    tmpl_controls: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], str | None]:
    if not tmpl_name:
        return [], None
    inputs = list(
        tmpl_controls.get(tmpl_name)
        or tmpl_controls.get(f"src/frontend/templates/{tmpl_name}")
        or []
    )
    target_file = None
    if tmpl_dir and (tmpl_dir / tmpl_name).is_file():
        target_file = str((tmpl_dir / tmpl_name).relative_to(workspace))
    elif tmpl_dir:
        hits = list(tmpl_dir.rglob(tmpl_name))
        if hits:
            target_file = str(hits[0].relative_to(workspace))
            if not inputs:
                inputs = _parse_template_controls(hits[0])
    return inputs, target_file


def _guess_template_name(route: str, tmpl_dir: Path | None) -> str | None:
    """When render_template is far from @route, guess login.html from /login."""
    if not tmpl_dir:
        return None
    stem = route.strip("/").split("/")[0] if route.strip("/") else "index"
    if not stem:
        stem = "index"
    candidate = f"{stem}.html"
    if (tmpl_dir / candidate).is_file():
        return candidate
    return None


def _function_window(text: str, start: int) -> str:
    """Slice from route decorator through roughly the next route/def boundary."""
    # Prefer large window so render_template after auth redirects is visible
    end = min(len(text), start + 4500)
    nxt = ROUTE_RE.search(text, start + 1)
    if nxt and nxt.start() < end:
        end = nxt.start()
    return text[start:end]


def extract_flask_screens(
    workspace: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    screens: list[dict[str, Any]] = []
    api_calls: list[dict[str, Any]] = []
    py_files = list(workspace.rglob("*.py"))
    def is_test_source(path: Path) -> bool:
        """Exclude test sources without treating a workspace parent named `test-*` as test code."""
        try:
            relative = path.relative_to(workspace)
        except ValueError:
            relative = path
        parts = [part.lower() for part in relative.parts]
        return (
            any(part in {"test", "tests", "__tests__"} for part in parts[:-1])
            or relative.name.lower().startswith(("test_", "tests_"))
            or relative.name.lower().endswith(("_test.py", "_tests.py"))
        )

    preferred = [
        p
        for p in py_files
        if p.name in {"frontend.py", "app.py", "main.py", "routes.py"}
        and not is_test_source(p)
        and ".github" not in str(p)
    ]
    scan = preferred or [
        p for p in py_files if not is_test_source(p) and ".github" not in str(p)
    ][:40]

    tmpl_dir = _find_templates_dir(workspace)
    tmpl_controls: dict[str, list[dict[str, Any]]] = {}
    tmpl_navigation: dict[str, list[dict[str, Any]]] = {}
    tmpl_outputs: dict[str, list[dict[str, Any]]] = {}
    action_forms: list[dict[str, Any]] = []
    conditional_blocks: list[dict[str, Any]] = []
    if tmpl_dir:
        template_files = sorted(tmpl_dir.rglob("*.html"))
        for template_index, html in enumerate(template_files, start=1):
            rel = str(html.relative_to(workspace))
            controls = _parse_template_controls(html)
            if controls:
                tmpl_controls[html.name] = controls
                tmpl_controls[rel] = controls
            links = _parse_navigation_links(html, workspace)
            if links:
                tmpl_navigation[html.name] = links
                tmpl_navigation[rel] = links
            outputs = _parse_output_bindings(html, workspace)
            if outputs:
                tmpl_outputs[html.name] = outputs
                tmpl_outputs[rel] = outputs
            action_forms.extend(_parse_action_forms(html, workspace))
            conditional_blocks.extend(_parse_conditional_blocks(html, workspace))
            if progress_callback:
                progress_callback(template_index, len(template_files))

    for path in scan:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(workspace))
        for match in ROUTE_RE.finditer(text):
            route = match.group(1)
            if route in {"/version", "/ready", "/healthy", "/live", "/ping", "/whereami"}:
                continue
            methods_raw = match.group(2) or "'GET'"
            methods = [m.strip().strip("'\"") for m in methods_raw.split(",") if m.strip()]
            line = text[: match.start()].count("\n") + 1
            window = _function_window(text, match.start())
            handler_match = re.search(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", window)
            handler_name = handler_match.group(1) if handler_match else None
            result_messages = list(
                dict.fromkeys(
                    re.findall(r"\bmsg\s*=\s*['\"]([^'\"]+)['\"]", window, re.IGNORECASE)
                )
            )
            destination_handlers = list(
                dict.fromkeys(re.findall(r"url_for\(\s*['\"]([^'\"]+)['\"]", window))
            )
            if re.search(r"['\"]toAccountNum['\"]\s*:\s*account_id\b", window):
                numeric_effect = "increase"
            elif re.search(r"['\"]fromAccountNum['\"]\s*:\s*account_id\b", window):
                numeric_effect = "decrease"
            else:
                numeric_effect = None
            tmpl = RENDER_RE.search(window)
            tmpl_name = tmpl.group(1) if tmpl else _guess_template_name(route, tmpl_dir)
            # GET pages own the template; POST /login has no render_template
            if not tmpl and any(m.upper() == "GET" for m in methods):
                tmpl_name = tmpl_name or _guess_template_name(route, tmpl_dir)
            name = tmpl_name.replace(".html", "") if tmpl_name else (route.strip("/") or "root")
            inputs, target_file = _controls_for_template(tmpl_name, tmpl_dir, workspace, tmpl_controls)
            # 인증 게이트 — 핸들러 본문에 토큰 검증이 있고 로그인으로 되돌리면 로그인 뒤 화면이다.
            # 로그인·가입 화면 자체는 인증 전 진입점이므로 게이트로 보지 않는다.
            guard_hit = AUTH_GUARD_RE.search(window)
            entry_route = route.rstrip("/").split("/")[-1].lower() in {"login", "signup", "signin", "register"}
            auth_guarded = bool(guard_hit) and bool(AUTH_DENY_RE.search(window)) and not entry_route
            screens.append(
                {
                    "name": name,
                    "route": route,
                    "methods": methods,
                    "authGuarded": auth_guarded,
                    "authGuardEvidence": (
                        {
                            "file": rel,
                            "line": line + window[: guard_hit.start()].count("\n"),
                            "symbol": guard_hit.group(0),
                            "extractor": "flask-auth-guard",
                            "confidence": 0.85,
                        }
                        if auth_guarded
                        else None
                    ),
                    "template": tmpl_name,
                    "handler": handler_name,
                    "resultMessages": result_messages,
                    "destinationHandlers": destination_handlers,
                    "numericEffect": numeric_effect,
                    "targetFile": target_file,
                    "inputs": inputs,
                    "uiElements": [
                        {
                            "name": i.get("name"),
                            "selector": i.get("selector"),
                            "kind": i.get("kind"),
                            "type": i.get("type"),
                            "field": i.get("field"),
                        }
                        for i in inputs
                    ],
                    "evidence": {
                        "file": target_file or rel,
                        "line": line,
                        "extractor": "flask-jinja-ui" if inputs else "flask-route",
                        "confidence": 0.9 if inputs else 0.82,
                        "routeFile": rel,
                    },
                }
            )
            for method in methods:
                m = method.upper()
                if m in {"POST", "PUT", "PATCH", "DELETE"}:
                    api_calls.append(
                        {
                            "method": m,
                            "path": route,
                            "normalizedPath": route,
                            "screenRoute": route,
                            "evidence": {
                                "file": rel,
                                "line": line,
                                "extractor": "flask-form-route",
                                "confidence": 0.75,
                            },
                        }
                    )

    # Also emit screens from templates not linked by route (best-effort by filename)
    known_routes = {s["route"] for s in screens}
    if tmpl_dir:
        for html in tmpl_dir.glob("*.html"):
            stem = html.stem
            if stem in {"shared"} or html.name.startswith("_"):
                continue
            guess_route = f"/{stem}" if stem != "index" else "/"
            if guess_route in known_routes:
                # Enrich existing route if it still lacks controls
                continue
            controls = _parse_template_controls(html)
            if not controls:
                continue
            rel = str(html.relative_to(workspace))
            screens.append(
                {
                    "name": stem,
                    "route": guess_route,
                    "methods": ["GET"],
                    "template": html.name,
                    "targetFile": rel,
                    "inputs": controls,
                    "uiElements": [
                        {
                            "name": i.get("name"),
                            "selector": i.get("selector"),
                            "kind": i.get("kind"),
                            "type": i.get("type"),
                            "field": i.get("field"),
                        }
                        for i in controls
                    ],
                    "evidence": {
                        "file": rel,
                        "line": 1,
                        "extractor": "jinja-template-ui",
                        "confidence": 0.7,
                    },
                }
            )

    by_route: dict[str, dict[str, Any]] = {}
    for s in screens:
        prev = by_route.get(s["route"])
        if not prev:
            by_route[s["route"]] = s
            continue
        # Merge GET+POST same path: keep richest UI + union methods
        merged_methods = sorted(
            {*(prev.get("methods") or []), *(s.get("methods") or [])},
            key=lambda m: (m != "GET", m),
        )
        richer = s if len(s.get("inputs") or []) > len(prev.get("inputs") or []) else prev
        other = prev if richer is s else s
        merged = dict(richer)
        merged["methods"] = merged_methods
        # GET(화면)·POST(제출)가 같은 경로면 어느 쪽에서든 인증 게이트를 관측했으면 게이트다
        merged["authGuarded"] = bool(richer.get("authGuarded")) or bool(other.get("authGuarded"))
        merged["authGuardEvidence"] = richer.get("authGuardEvidence") or other.get("authGuardEvidence")
        if not merged.get("template") and other.get("template"):
            merged["template"] = other["template"]
        if not merged.get("targetFile") and other.get("targetFile"):
            merged["targetFile"] = other["targetFile"]
        if not merged.get("inputs") and other.get("inputs"):
            merged["inputs"] = other["inputs"]
            merged["uiElements"] = other.get("uiElements") or []
        by_route[s["route"]] = merged

    # Fill any still-empty screens from template filename guess
    if tmpl_dir:
        for route, s in list(by_route.items()):
            if s.get("inputs"):
                continue
            guess = _guess_template_name(route, tmpl_dir)
            if not guess:
                continue
            inputs, target_file = _controls_for_template(guess, tmpl_dir, workspace, tmpl_controls)
            if not inputs:
                continue
            s["template"] = guess
            s["targetFile"] = target_file
            s["inputs"] = inputs
            s["uiElements"] = [
                {
                    "name": i.get("name"),
                    "selector": i.get("selector"),
                    "kind": i.get("kind"),
                    "type": i.get("type"),
                    "field": i.get("field"),
                }
                for i in inputs
            ]
            s["evidence"] = {
                **(s.get("evidence") or {}),
                "file": target_file or (s.get("evidence") or {}).get("file"),
                "extractor": "flask-jinja-ui",
                "confidence": 0.88,
            }

    # Join template CTAs to source/target routes only after GET/POST route rows are
    # merged. This keeps navigation evidence deterministic and avoids duplicate links.
    entry_actions: dict[str, list[dict[str, Any]]] = {}
    for source_route, source in by_route.items():
        template = str(source.get("template") or "")
        target_file = str(source.get("targetFile") or "")
        links = tmpl_navigation.get(target_file) or tmpl_navigation.get(template) or []
        source["outputBindings"] = list(
            tmpl_outputs.get(target_file) or tmpl_outputs.get(template) or []
        )
        source["navigationLinks"] = [
            {**link, "sourceRoute": source_route}
            for link in links
            if str(link.get("targetRoute") or "") in by_route
        ]
        for link in source["navigationLinks"]:
            entry_actions.setdefault(str(link["targetRoute"]), []).append(link)
    for target_route, actions in entry_actions.items():
        # Prefer the root/login entry path when several templates link to one page.
        by_route[target_route]["entryActions"] = sorted(
            actions,
            key=lambda item: (str(item.get("sourceRoute")) not in {"/", "/login"}, str(item.get("sourceRoute"))),
        )

    # A POST route is often submitted from a modal that lives on a different GET
    # screen.  Preserve that source screen and its post-action output containers.
    for form in action_forms:
        evidence_file = str((form.get("evidence") or {}).get("file") or "")
        candidates = [
            item
            for item in by_route.values()
            if evidence_file
            and evidence_file in {str(item.get("targetFile") or ""), str(item.get("template") or "")}
            and "GET" in [str(method).upper() for method in (item.get("methods") or [])]
        ]
        source = max(
            candidates,
            key=lambda item: (bool(item.get("authGuarded")), str(item.get("route") or "") != "/"),
            default=None,
        )
        if source:
            form["sourceRoute"] = source.get("route")
            form["outputBindings"] = list(source.get("outputBindings") or [])
            target = by_route.get(str(form.get("action") or "").split("?", 1)[0]) or {}
            form["resultMessages"] = list(target.get("resultMessages") or [])
            form["numericEffect"] = target.get("numericEffect")
            destination_handlers = list(target.get("destinationHandlers") or [])
            destination = next(
                (
                    item
                    for item in by_route.values()
                    if item.get("handler") in destination_handlers
                ),
                None,
            )
            form["destinationRoute"] = (destination or source).get("route")
            source.setdefault("actionForms", []).append(form)

    # 세션 마커 — 인증 게이트 경로로 제출하는 form을 품은 조건부 블록의 요소만 채택한다.
    # (로그인 화면의 조건부 블록은 인증 전이므로 제외된다)
    auth_actions = {
        s["route"] for s in by_route.values() if s.get("authGuarded") and "GET" not in (s.get("methods") or [])
    } | {s["route"] for s in by_route.values() if s.get("authGuarded")}
    marker_seen: set[str] = set()
    markers: list[dict[str, Any]] = []
    for block in conditional_blocks:
        if not any(a in auth_actions for a in block.get("formActions") or []):
            continue
        for selector in block["selectors"]:
            if selector in marker_seen:
                continue
            marker_seen.add(selector)
            markers.append(
                {
                    "selector": selector,
                    "condition": block["condition"],
                    "evidence": block["evidence"],
                }
            )

    return {
        "screens": list(by_route.values()),
        "apiCalls": api_calls,
        "components": [],
        "inputs": [i for s in by_route.values() for i in (s.get("inputs") or [])],
        "actionForms": action_forms,
        "sessionMarkers": markers,
        "extractor": "flask-jinja",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8") or "{}")
    workspace = Path(str(payload.get("workspacePath") or ".")).expanduser().resolve()
    result = extract_flask_screens(workspace)
    out = {
        "ok": True,
        "skill": "frontend_analyze",
        "tool": "extract_flask_screens",
        "result": result,
        "screenCount": len(result["screens"]),
        "apiCallCount": len(result["apiCalls"]),
        "inputCount": len(result.get("inputs") or []),
    }
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "screens": out["screenCount"], "inputs": out["inputCount"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
