# PHASE 01. 표준 스캐폴딩 · 문서 SSOT

## 목적

SDD 구조가 흔들리지 않도록 **마스터 색인 · AGENTS · Cursor Rules · 제품/아키텍처/표준 문서**를 확정한다.
이 Phase에서는 `backend/`/`frontend/` 앱 코드를 깊게 구현하지 않는다.

마스터 색인: [`../../index.md`](../../index.md)

---

## 절대 반영 사항

```text
1. agent_core 폴더 금지
2. core = Agent Runtime, utils = 공통 유틸
3. Workflow Hub + Skill Hub만 관리형 Hub
4. Graph Manifest / Graph Registry 금지
5. 작업 입구는 docs/index.md
6. Deep Agent는 Core 옵션 — Hub 우회 금지
```

---

## 산출물 체크리스트

### Root

- [x] `AGENTS.md` — 방향성 · 컨텍스트 유실 방지
- [x] `README.md` — index 입구
- [x] `CURSOR_APPLY_INSTRUCTIONS.md`
- [x] `.gitignore` · `.cursorignore`

### `.cursor/rules`

- [x] `00-absolute-sdd-architecture.mdc`
- [x] `01-ai-answer-format.mdc`
- [x] `02-test-automation-domain.mdc`
- [x] `.cursor/plans/` 자리

### `docs/`

- [x] `index.md` — 마스터 색인 (Agent/Backend/Frontend 앵커)
- [x] `product/00_NORTH_STAR.md`
- [x] `product/01_INTERVIEW_BRIEF_v0.1.md`
- [x] `product/BACKLOG_AND_NON_GOALS.md`
- [x] `architecture/PLATFORM_OVERVIEW.md`
- [x] `architecture/DECISIONS.md`
- [x] `standards/AGENT_RUNTIME.md`
- [x] `standards/BACKEND_STRUCTURE.md`
- [x] `standards/FRONTEND_FLOW_UI.md`
- [x] `standards/HUB_CAPABILITY_AND_SKILL.md`
- [x] `standards/AI_ANSWER_OUTPUT_FORMAT.md`
- [x] `work-orders/00_WORK_ORDER_INDEX.md`
- [x] `work-orders/01_CURSOR_MASTER_PROMPT.md`
- [x] `work-orders/02_FINAL_ARCHITECTURE_DECISIONS.md`
- [x] `work-orders/03_LOGGING.md`
- [x] `work-orders/few-shot/template_workflow.yml`
- [x] `work-orders/few-shot/template_skill.md`
- [x] `work-orders/chain/` · `report/` · `templates/`

### 후속 (본 Phase 비범위)

- [ ] `backend/` 표준 트리 생성
- [ ] `frontend/` 표준 트리 생성

---

## 인수 기준

1. Agent가 `docs/index.md`만 보고 Agent/Backend/Frontend 상세로 진입할 수 있다.
2. 인터뷰 빈 `>` 링크가 index 앵커·standards로 대체되어 있다.
3. SDD 절대규칙(mdc)과 도메인 Guardrail(mdc)이 alwaysApply로 존재한다.
4. North Star에 A→B→C 핵심 난제와 HITL이 명시되어 있다.
5. backend/frontend 코드 없이도 다음 Phase 착수 문서가 준비되어 있다.

---

## 완료 보고

[`../../report/2026-08-03/PHASE_01_DOCS_SSOT.md`](../../report/2026-08-03/PHASE_01_DOCS_SSOT.md)
