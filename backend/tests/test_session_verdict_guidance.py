"""D-015 — 세션 선행조건 · 기대 결과 판정 지침 회귀 고정.

로그인 없이 `/logout` 만 열고도 "Endpoint 에 접근했다"는 이유로 성공 증적이 남은
결함을 다시 만들지 않기 위해, 지침(시스템 프롬프트 · SKILL 계약)이 자리에 있고
핵심 규칙 문구가 빠지지 않았는지 확인한다.

지침 본문의 표현은 다듬을 수 있으나, 여기서 확인하는 계약 키워드는 유지해야 한다.
계약: docs/03.계약과예시/08.세션선행조건과판정계약.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.paths import REPO_ROOT, SKILL_HUB

PROMPTS = REPO_ROOT / "backend" / "app" / "prompts"
SESSION_PROMPT = PROMPTS / "scenario" / "session_precondition_system.md"
VERDICT_PROMPT = PROMPTS / "run" / "verify_expected_result_system.md"
SUMMARY_PROMPT = PROMPTS / "run" / "summarize_run_system.md"
BIND_PROMPT = PROMPTS / "run" / "bind_dom_inputs_system.md"
NARRATE_PROMPT = PROMPTS / "scenario" / "narrate_bind_system.md"
CONTRACT_DOC = REPO_ROOT / "docs" / "03.계약과예시" / "08.세션선행조건과판정계약.md"
RUNTIME_PROMPTS = tuple(sorted(PROMPTS.rglob("*_system.md")))

SESSION_POLICIES = (
    "no_auth",
    "login_then_reuse",
    "reuse_existing_session",
    "fresh_login_required",
)
VERDICTS = ("expected_met", "expected_not_met", "undetermined")


def _text(path: Path) -> str:
    assert path.is_file(), f"지침 파일 없음: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "path",
    [SESSION_PROMPT, VERDICT_PROMPT, SUMMARY_PROMPT, BIND_PROMPT, NARRATE_PROMPT, CONTRACT_DOC],
)
def test_guidance_files_exist(path: Path) -> None:
    assert _text(path).strip()


def test_session_prompt_requires_login_precondition() -> None:
    text = _text(SESSION_PROMPT)
    for policy in SESSION_POLICIES:
        assert policy in text, f"sessionPolicy 값 누락: {policy}"
    assert "Every logout scenario requires prior login" in text
    assert "Continue the main scenario in the same browser session" in text
    assert "environment.loginId" in text and "environment.loginSecret" in text
    assert "authRequired" in text and "preconditionSteps" in text


def test_verdict_prompt_forbids_endpoint_reach_as_success() -> None:
    text = _text(VERDICT_PROMPT)
    for verdict in VERDICTS:
        assert verdict in text, f"verdict 값 누락: {verdict}"
    assert "Reachability is not success" in text
    assert "Allowlist" in text  # 관측된 결함 신호를 실패로 다룬다
    assert "coverageNote" in text and "blockingIssues" in text
    assert "session_missing" in text


def test_summary_prompt_carries_verdict_reason() -> None:
    text = _text(SUMMARY_PROMPT)
    assert "verdict" in text
    assert "evidence-based reason" in text
    assert "Do not describe page/endpoint reachability as success" in text


def test_bind_prompt_uses_registered_account_reference() -> None:
    text = _text(BIND_PROMPT)
    assert "environment.loginSecret" in text
    assert "Never generate login credentials" in text


def test_runtime_system_prompts_have_korean_archives() -> None:
    assert len(RUNTIME_PROMPTS) == 11
    for runtime_prompt in RUNTIME_PROMPTS:
        archive = runtime_prompt.with_name(f"{runtime_prompt.stem}_KOR.md")
        runtime_text = _text(runtime_prompt)
        archive_text = _text(archive)
        assert runtime_text.splitlines()[0] == archive_text.splitlines()[0]
        assert any("가" <= char <= "힣" for char in archive_text)
        assert not any("가" <= char <= "힣" for char in runtime_text)
        assert "Model compatibility" in runtime_text or "model" in runtime_text.lower()


def test_skill_contracts_reference_guidance() -> None:
    dsl_skill = _text(SKILL_HUB / "scenario_dsl" / "SKILL.md")
    assert "sessionPolicy" in dsl_skill
    assert "session_precondition_system.md" in dsl_skill
    assert "verdictCriteria" in dsl_skill

    browser_skill = _text(SKILL_HUB / "browser_execute" / "SKILL.md")
    assert "verify_expected_result_system.md" in browser_skill
    assert "verdict" in browser_skill
    assert "Allowlist methods" in browser_skill
