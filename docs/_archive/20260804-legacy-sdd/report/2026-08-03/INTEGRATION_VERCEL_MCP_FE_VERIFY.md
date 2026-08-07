# 보고 — 통합 FE 검증: Vercel MCP(DOM · 스크린샷)

작성일: 2026-08-03  
대상: `AI_Hackertorn`  
범위: 도메인 규칙 · Master Prompt · SSOT 문서 동기화 (앱 코드 제외)

---

## 왜 이렇게 했는가

통합 테스트의 핵심 난제(A→B→C)가 API-only로 끝나면 North Star의
“Backend + Frontend 화면 연계”가 빠진다.
관측 근거를 **DOM 입력값 / 후속 화면 결과 / 단계별 스크린샷**으로 고정하면
LLM 추정 없이 HITL이 Pass/Fail을 판단할 재료가 생긴다.

Vercel MCP를 통합 FE **기본** 경로로 두고, Playwright는 보완으로 남겨
기존 Non-goals(무단 MCP)·단계적 실기동(M10)과 충돌하지 않게 했다.

---

## 근거 · Reasoning

| 결정 | 근거 |
|---|---|
| Vercel MCP = 통합 FE 기본 | DOM 입력·후속 결과 대조 + screenshot evidence |
| 최소 스크린샷 2장 | 입력 직후 · 결과 화면 — 관측 공백 방지 |
| DOM 없으면 `missing_data` | 추정 금지 Guardrail과 동일 |
| AI Pass 단정 금지 | 스크린샷 일치만으로도 최종 확정하지 않음 |
| Skill few-shot에 `fe_verify` 힌트 | Plan 산출 시 RUN.EXECUTE가 탈 계약 명시 |
| MCP 사용 전 사용자 문의 | 기존 Playwright 정책과 동일하게 유지 |

---

## 사용자가 알아야 할 사항

1. Cursor에 **Vercel MCP**가 아직 연결되지 않았다면, 구현/실사용 Phase 전에 MCP 등록이 필요하다.
2. 현재는 **문서·규칙 계약**만 강화했다. `TEST.RUN.EXECUTE` 실구현은 후속 Phase.
3. 통합 Plan의 FE step은 `open → DOM 입력 → action → DOM 결과 → screenshot` 체크리스트를 따른다.
4. Pass/Fail·배포는 여전히 사람(개발PL/QA) 책임이다.

---

## 산출물

```text
.cursor/rules/02-test-automation-domain.mdc   §5.1 · §7
.cursor/rules/00-absolute-sdd-architecture.mdc §12
docs/work-orders/01_CURSOR_MASTER_PROMPT.md    Guardrail · Capability
docs/standards/FRONTEND_FLOW_UI.md             §5
docs/architecture/DECISIONS.md · PLATFORM_OVERVIEW.md
docs/product/* · AGENTS.md · docs/index.md
docs/work-orders/few-shot/template_skill.md
```

---

```핵심 내용
통합 FE 검증 SSOT: Vercel MCP로 DOM 입력/후속 결과 관측 + 단계별 스크린샷 evidence.
Playwright는 보완. HITL·missing_data·사용자 동의 MCP는 유지.
```

**요약: 통합 테스트의 FE 관측을 Vercel MCP(DOM·스크린샷) 체계로 문서·프롬프트에 고정했다.**
