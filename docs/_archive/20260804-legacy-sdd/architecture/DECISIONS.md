# 최종 아키텍처 의사결정 — AI Hackerton

교보재: NH_AML `docs/work-orders/02_FINAL_ARCHITECTURE_DECISIONS.md` 패턴  
작업지시서 요약본: [`../work-orders/02_FINAL_ARCHITECTURE_DECISIONS.md`](../work-orders/02_FINAL_ARCHITECTURE_DECISIONS.md)

---

## 1. 디렉토리 명칭

```text
backend/app/utils/  = 공통 유틸리티 (config, logger, exceptions, …)
backend/app/core/   = Agent Core Runtime (router, planner, orchestrator, registries, …)
```

금지: `backend/app/agent_core/`, `backend/app/core/config.py`

---

## 2. Sub Agent 위치

```text
backend/app/agents/{agent_name}/agent.py   = Named Execution Boundary (Thin Wrapper)
backend/app/skills/{agent_name}/SKILL.md   = 실행 명세
backend/app/skills/{agent_name}/script/*.py = Tool CLI
```

---

## 3. Workflow와 Execution Graph 분리

```text
workflow_definitions/*.yml  = 업무 목표 / capability / logical steps
langgraph_runtime/          = Plan 실행 State·Node·Edge
```

Workflow ≠ Graph. Graph Hub를 만들지 않는다.

---

## 4. 관리형 Hub

```text
관리형 Hub: Workflow Hub, Skill Hub
코드 Runtime: 공통 plan_execution_graph
비-Hub: capability_definitions, agents/specs (거버넌스·taxonomy)
```

---

## 5. Graph 실행

- 기본: 모든 Workflow → 공통 Plan Execution Graph
- 분기 필요 시: `execution_policy.execution_pattern` 기준 `graph_resolver.py` 한 곳만
- `workflow_id` if/else를 Router/Planner/Node에 분산 금지

---

## 6. Capability 매칭 (C안)

1. Workflow는 Skill/Agent ID를 직접 고정하지 않는다.
2. Workflow `required_capabilities` = canonical capability_id
3. Skill `provided_capabilities` = canonical capability_id
4. Planner는 Registry 매칭 → Validator 통과 Plan만 실행
5. parent capability만 일치하면 자동 실행하지 않는다.

---

## 7. Deep Agent (LangChain) 허용 조건

인터뷰에서 Deep Agent lib 사용을 허용한다. 단:

```text
허용: Core Runtime 내부 구현 옵션 (특정 Skill/Tool 오케스트레이션 보조)
금지: Workflow Hub / Skill Hub / Plan / Validator 를 우회하는 병렬 Agent 스택
금지: “자율 multi-agent가 서로 협업” 제품 서사로 Hub를 대체
```

외부 설명: *중앙 Planner가 Capability를 Skill에 매핑하고,
PlanExecutor가 Named Sub-agent Adapter로 Step을 실행한다.*

---

## 8. 도메인 결정

```text
Repo Sync → Code Analyze
  → Unit Scenario + Integration Plan(A→B→C)
  → Param Augment → Execute → Quality KPI
  → FLOW UI (사람 편집)
```

최종 Pass/Fail·배포는 사람(HITL).

---

## 9. Frontend

- React
- FLOW UI는 Figma User-Flow-Kit 레이어 계약을 따른다
- 통합 FE 검증 기본: **Vercel MCP** — DOM 입력/후속 결과 관측 + 단계별 스크린샷 evidence
- Playwright MCP는 보완 경로. Vercel/Playwright MCP는 사용자 동의 후에만 사용
- 상세: [`.cursor/rules/02-test-automation-domain.mdc`](../../.cursor/rules/02-test-automation-domain.mdc) §5.1 · [`../standards/FRONTEND_FLOW_UI.md`](../standards/FRONTEND_FLOW_UI.md) §5

---

## 10. Structured Output · LLM

- 입출력은 Pydantic Schema (`extra=forbid` 권장)
- JSON 오브젝트 기반 연동(필수)
- LLM Client 싱글턴/팩토리 재사용
- 프롬프트는 `backend/app/prompts/` 분리, 코드 하드코딩 금지
