# PHASE 01 보고 — 개발 지침 SSOT 작성

작성일: 2026-08-03  
대상: `AI_Hackertorn`  
범위: 문서 · `.cursor/rules` · `AGENTS.md` (앱 코드 제외)

---

## 왜 이렇게 했는가

NH_AML 교보재의 SDD 패턴( Hub 2개 · utils/core · Plan Runtime · few-shot · Phase index )을
테스트자동화 인터뷰 v0.1에 맞게 이식하되, AML Context AI 등 도메인 전용 규칙은 제외했다.

인터뷰에 비어 있던 Agent/Backend/Frontend `>` 링크를
**단일 입구 `docs/index.md` + standards 상세**로 채웠다.
Cursor가 컨텍스트를 잃어도 index → AGENTS → mdc → Phase 순으로 복귀하도록 계약을 고정했다.

Runtime은 교보재와 동일하게 Workflow/Skill Hub + 공통 Plan Graph를 절대 구조로 두고,
인터뷰의 Deep Agent는 Hub 우회 없는 Core 옵션으로만 문서화했다.

---

## 근거 · Reasoning

| 결정 | 근거 |
|---|---|
| `docs/index.md` 단일 입구 | 사용자 요청: 색인 md + 하위 상세만 따르도록 |
| mdc 3종 (00/01/02) | 교보재 00·01 대응 + 도메인 Guardrail 분리 |
| product North Star | 인터뷰 핵심 난제(A→B→C)를 Phase 최상위로 고정 |
| Non-goals에 실기동 E2E 단계화 | 인터뷰는 핵심이나 1차 문서 Phase에서 코드 일괄 완성 금지 |
| few-shot을 통합 Plan Skill 예시로 | North Star와 직결되는 템플릿이 필요 |

---

## 사용자가 알아야 할 사항

1. **작업은 항상 [`docs/index.md`](../../index.md)부터** 시작한다.
2. `backend/`/`frontend/`는 아직 없다. Phase 02+에서 Master Prompt의 트리를 따른다.
3. Cursor에서 `AI_Hackertorn` 폴더를 워크스페이스로 열어야 `.cursor/rules`가 적용된다.
4. 원 인터뷰 메모(NH_AML `docs/report/.../테스트자동화_AI_hackerton.md`)의 상세는
   이 저장소 index/standards를 가리키도록 갱신한다.
5. Figma·Playwright는 표준 문서에 계약만 있음. MCP 실사용은 구현 Phase + 사용자 동의.

---

## 산출물 목록

```text
docs/index.md
docs/product/*
docs/architecture/*
docs/standards/*
docs/work-orders/* (01 Master Prompt, few-shot 보강 포함)
AGENTS.md · README.md · CURSOR_APPLY_INSTRUCTIONS.md
.cursor/rules/00 · 01 · 02
```

```핵심 내용
Phase 01: AI_Hackertorn에 docs/index.md 중심 SDD 개발 지침 SSOT를 구축했다.
교보재 Hub/Runtime 규칙을 유지하고, 인터뷰의 시나리오·A→B→C·FLOW·HITL을
product/standards/mdc에 반영했다. 앱 코드 스캐폴딩은 후속 Phase다.
```

**요약: 문서 SSOT·Cursor 규칙·AGENTS 컨텍스트 앵커 완료. 다음 작업은 Phase 02 Registry/Schema 또는 backend 스캐폴딩.**
