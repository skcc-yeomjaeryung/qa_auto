# AI Hackerton SDD Cursor 작업지시서 인덱스

> 마스터 색인(항상 우선): [`../index.md`](../index.md)

이 문서는 **Phase 단위 작업**의 색인이다.
한 번에 모든 기능을 구현하지 않는다.

---

## 0. Phase 착수 전 읽기

```text
1. docs/index.md
2. AGENTS.md
3. .cursor/rules/00-absolute-sdd-architecture.mdc
4. .cursor/rules/02-test-automation-domain.mdc
5. docs/product/00_NORTH_STAR.md
6. docs/work-orders/01_CURSOR_MASTER_PROMPT.md
7. docs/work-orders/02_FINAL_ARCHITECTURE_DECISIONS.md
8. docs/work-orders/03_LOGGING.md
9. 현재 Phase 작업지시서
```

---

## 1. 디렉토리 원칙

```text
backend/app/utils/                 = 공통 유틸리티
backend/app/core/                  = Agent Core Runtime
backend/app/workflow_definitions/  = Workflow Hub
backend/app/skills/                = Skill Hub
backend/app/langgraph_runtime/     = Plan 실행 Runtime
backend/app/agents/                = Sub Agent Wrapper
```

- `agent_core` 금지 · Graph Hub 금지

---

## 2. Phase 체크리스트

| Phase | 작업지시서 | 목표 | 완료 |
|---|---|---|---|
| 01 | `phases/PHASE_01_STANDARD_SCAFFOLDING.md` | 문서 SSOT · Cursor Rules · AGENTS · index | [x] |
| 02 | (예정) Registry / Schema / Validator | Workflow·Skill 로드·검증 | [ ] |
| 03 | (예정) Core Runtime + Plan Graph | route→plan→execute→review→reduce | [ ] |
| 04 | (예정) Repo Sync · Code Analyze · Unit Scenario | 동기화·단위 시나리오 Skill | [ ] |
| 05 | (예정) Integration Plan · Param · Run | A→B→C · INPUT · 실행 | [ ] |
| 06 | (예정) FLOW UI · KPI | React FLOW · 품질지표 | [ ] |
| 07 | (예정) Test · Acceptance | 인수 · 회귀 | [ ] |

---

## 3. Core Runtime 구성요소

```text
Router · Planner · Orchestrator
Workflow Registry · Skill Registry · Tool Runtime
Reviewer · Reducer · Memory / Runtime Workspace
LLM Client (공용)
```

위치: `backend/app/core/`

---

## 4. Few-shot / Chain / Report

```text
few-shot/   = Workflow·Skill 구조 기준
chain/      = Phase memory (컨텍스트 유실 방지)
docs/report/= Phase 완료 보고
```

---

## 5. 영역별 표준 (바로가기)

| 영역 | 문서 |
|---|---|
| Agent | [`../standards/AGENT_RUNTIME.md`](../standards/AGENT_RUNTIME.md) |
| Backend | [`../standards/BACKEND_STRUCTURE.md`](../standards/BACKEND_STRUCTURE.md) |
| Frontend | [`../standards/FRONTEND_FLOW_UI.md`](../standards/FRONTEND_FLOW_UI.md) |
| Hub/Capability | [`../standards/HUB_CAPABILITY_AND_SKILL.md`](../standards/HUB_CAPABILITY_AND_SKILL.md) |
