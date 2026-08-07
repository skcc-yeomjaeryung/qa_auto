# AI Hackerton — 개발 지침 마스터 색인

> **모든 Cursor Agent / 개발자는 작업 시작 시 이 파일을 먼저 읽는다.**  
> 이후 아래 표가 가리키는 **상세 지침만** 따른다. 추측으로 Hub/구조를 만들지 않는다.

저장소: `AI_Hackertorn`  
제품: AI 테스트시나리오 자동생성 · INPUT 증강 · FLOW · 품질결과 플랫폼 (SDD)

---

## 0. 읽기 순서 (고정)

```text
1. 이 파일 (docs/index.md)
2. AGENTS.md                         — 방향성 · Guardrail · 컨텍스트 앵커
3. .cursor/rules/00-absolute-sdd-architecture.mdc
4. .cursor/rules/01-ai-answer-format.mdc
5. .cursor/rules/02-test-automation-domain.mdc
6. docs/product/00_NORTH_STAR.md
7. docs/architecture/PLATFORM_OVERVIEW.md
8. docs/work-orders/01_CURSOR_MASTER_PROMPT.md
9. docs/work-orders/00_WORK_ORDER_INDEX.md 의 현재 Phase 작업지시서
```

컨텍스트가 흐려지면: `docs/work-orders/chain/`에 memory를 남긴 뒤 위 순서를 다시 읽는다.

---

## 1. 제품 / 인터뷰

| 문서 | 내용 |
|---|---|
| [`product/00_NORTH_STAR.md`](./product/00_NORTH_STAR.md) | 한 문장 약속 · 3단 가치 사슬 · 핵심 난제 |
| [`product/01_INTERVIEW_BRIEF_v0.1.md`](./product/01_INTERVIEW_BRIEF_v0.1.md) | 인터뷰 v0.1 구조화 · Figma 링크 |
| [`product/BACKLOG_AND_NON_GOALS.md`](./product/BACKLOG_AND_NON_GOALS.md) | MVP in/out · Non-goals |

---

## 2. 아키텍처 표준

| 문서 | 내용 |
|---|---|
| [`architecture/PLATFORM_OVERVIEW.md`](./architecture/PLATFORM_OVERVIEW.md) | 종단 흐름 · Capability 맵 |
| [`architecture/DECISIONS.md`](./architecture/DECISIONS.md) | 확정 의사결정 |
| [`standards/HUB_CAPABILITY_AND_SKILL.md`](./standards/HUB_CAPABILITY_AND_SKILL.md) | Hub vs Spec vs Capability |
| [`standards/AI_ANSWER_OUTPUT_FORMAT.md`](./standards/AI_ANSWER_OUTPUT_FORMAT.md) | 답변 시각 포맷 |

---

## 3. Agent / Backend / Frontend 지침

인터뷰 문서의 “상세는 아래 지침” 링크는 **이 섹션**이다.

<a id="agent"></a>

### Agent

적합한 Workflow 기반 Skill 조합으로 Agent(Named Execution Boundary)를 구성한다.
LangChain Deep Agent는 **Core 구현 옵션**이며 Hub/Plan/Validator를 우회하지 않는다.

- [`standards/AGENT_RUNTIME.md`](./standards/AGENT_RUNTIME.md)
- [`standards/HUB_CAPABILITY_AND_SKILL.md`](./standards/HUB_CAPABILITY_AND_SKILL.md)
- [`.cursor/rules/00-absolute-sdd-architecture.mdc`](../.cursor/rules/00-absolute-sdd-architecture.mdc)

<a id="backend"></a>

### Backend

Python 기반 Agent 시스템. `utils` vs `core`, Workflow/Skill Hub, Plan Execution Runtime.

- [`standards/BACKEND_STRUCTURE.md`](./standards/BACKEND_STRUCTURE.md)
- [`architecture/DECISIONS.md`](./architecture/DECISIONS.md)
- [`work-orders/03_LOGGING.md`](./work-orders/03_LOGGING.md)

<a id="frontend"></a>

### Frontend

React. 시나리오 목록 · FLOW 편집(Figma User-Flow-Kit) · 결과/KPI · HITL.

- [`standards/FRONTEND_FLOW_UI.md`](./standards/FRONTEND_FLOW_UI.md)
- [`.cursor/rules/02-test-automation-domain.mdc`](../.cursor/rules/02-test-automation-domain.mdc)

---

## 4. 핵심 개발 프롬프트

| 문서 | 내용 |
|---|---|
| [`work-orders/01_CURSOR_MASTER_PROMPT.md`](./work-orders/01_CURSOR_MASTER_PROMPT.md) | Cursor Master Prompt (목표·트리·Capability·Guardrail) |
| [`work-orders/02_FINAL_ARCHITECTURE_DECISIONS.md`](./work-orders/02_FINAL_ARCHITECTURE_DECISIONS.md) | 아키텍처 결정 요약 |
| [`../CURSOR_APPLY_INSTRUCTIONS.md`](../CURSOR_APPLY_INSTRUCTIONS.md) | 적용 시 읽기 순서 |

---

## 5. Phase 작업

| 문서 | 내용 |
|---|---|
| [`work-orders/00_WORK_ORDER_INDEX.md`](./work-orders/00_WORK_ORDER_INDEX.md) | Phase 체크리스트 |
| [`work-orders/phases/`](./work-orders/phases/) | Phase별 작업지시서 |

현재 권장 Phase: **01 표준 스캐폴딩(문서 SSOT)**  
→ [`work-orders/phases/PHASE_01_STANDARD_SCAFFOLDING.md`](./work-orders/phases/PHASE_01_STANDARD_SCAFFOLDING.md)

---

## 6. Few-shot / Chain / Report

| 경로 | 용도 |
|---|---|
| [`work-orders/few-shot/`](./work-orders/few-shot/) | Workflow/Skill 구조 기준 |
| [`work-orders/chain/`](./work-orders/chain/) | Phase memory |
| [`report/`](./report/) | Phase 완료 보고 |
| [`templates/`](./templates/) | 기타 템플릿 자리 |

---

## 7. Root · Cursor Rules

| 경로 | 용도 |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | 프로젝트 방향성 · 컨텍스트 앵커 |
| [`../README.md`](../README.md) | 사람용 입구 |
| [`../.cursor/rules/`](../.cursor/rules/) | alwaysApply 절대 규칙 |
| [`../.cursor/plans/`](../.cursor/plans/) | Cursor plan 자리 |

---

## 8. 절대 금지 (요약)

```text
- Graph Hub / graph_manifest
- Hub 없는 Workflow/Skill/Tool 발명
- Pass/Fail·배포 AI 최종 확정 (스크린샷·DOM만으로도 단정 금지)
- 근거 없는 의존·파라미터 추정
- Deep Agent로 SDD Hub 우회
- 화면마다 독자 LLM/Chat 엔드포인트
- Vercel MCP / Playwright MCP 무단 사용
```

상세 Non-goals: [`product/BACKLOG_AND_NON_GOALS.md`](./product/BACKLOG_AND_NON_GOALS.md)
