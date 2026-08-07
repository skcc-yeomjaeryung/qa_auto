# Agent Runtime 표준

색인: [`../index.md#agent`](../index.md#agent)  
절대규칙: [`.cursor/rules/00-absolute-sdd-architecture.mdc`](../../.cursor/rules/00-absolute-sdd-architecture.mdc)

---

## 1. 원칙

```text
Workflow = 업무적으로 반드시 거쳐야 하는 구조
Skill    = 그 구조 안에서 실행 가능한 기능
Planner  = Workflow ↔ Skill 바인딩 (정책 재발명 금지)
Agent    = Named Execution Boundary (자율 Agent 아님)
```

금지:

- Workflow 안에 Skill 실행 방식 기술
- Skill 안에 승인 흐름·업무 정책 Engine
- Planner가 Hub에 없는 자산 발명

---

## 2. 구성요소 위치

```text
backend/app/core/                 = Router, Planner, Orchestrator, Registries, ToolRuntime, Reviewer, Reducer, Memory
backend/app/workflow_definitions/ = Workflow Hub
backend/app/skills/{name}/        = Skill Hub (SKILL.md + script)
backend/app/agents/{name}/        = Thin Wrapper
backend/app/agents/specs/*.yml    = AgentSpec (허용 Skill·금지 행위)
backend/app/langgraph_runtime/    = Plan Execution Graph (코드)
```

---

## 3. Plan JSON (최소)

```text
plan_id, workflow_id
steps[].step_id
steps[].agent / skill / tool
steps[].input_artifacts / output_artifacts
steps[].depends_on / execution_mode
```

script 경로는 Plan에 넣지 않는다. `skill + tool` → SKILL.md → ToolResolver.

---

## 4. script Tool CLI

```text
argparse · main() · __main__
--input / --output
JSON(또는 HTML) 산출
실패 시 stderr + non-zero
사용자 응답 문장 직접 생성 금지
```

계산·파싱·의존그래프 확정 수치·집계는 **script/rule**에서 수행한다. LLM은 초안·설명·구조화 보조.

---

## 5. Deep Agent 옵션

LangChain Deep Agent를 Core 안에서 쓸 수 있다.

```text
OK : Plan step이 허용한 Skill/Tool 범위 내 보조 실행
NG : Hub 우회, 독자 Chat/Agent 엔드포인트로 업무 분기
NG : Graph Hub / 자율 multi-agent 서사로 SDD 대체
```

---

## 6. 도메인 Agent 후보 (MVP)

| agent (가칭) | 주 capability |
|---|---|
| `repo_sync` | `TEST.REPO.SYNC` |
| `code_analyze` | `TEST.CODE.ANALYZE` |
| `unit_scenario` | `TEST.SCENARIO.UNIT_GENERATE` |
| `integration_plan` | `TEST.SCENARIO.INTEGRATION_PLAN` |
| `param_augment` | `TEST.PARAM.AUGMENT` |
| `test_runner` | `TEST.RUN.EXECUTE` |
| `flow_compose` | `TEST.FLOW.COMPOSE` |
| `quality_kpi` | `TEST.QUALITY.KPI` |

이름은 구현 Phase에서 Schema에 맞게 확정한다. Workflow는 agent 이름이 아니라 capability로 선언한다.

---

## 7. Few-shot

- [`../work-orders/few-shot/template_workflow.yml`](../work-orders/few-shot/template_workflow.yml)
- [`../work-orders/few-shot/template_skill.md`](../work-orders/few-shot/template_skill.md)
