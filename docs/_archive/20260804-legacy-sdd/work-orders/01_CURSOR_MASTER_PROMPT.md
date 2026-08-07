# Cursor Master Prompt — AI Hackerton 테스트자동화 플랫폼 (SDD)

당신은 20년차 숙련된 엔터프라이즈·SI 플랫폼 아키텍처 총괄입니다.

지금부터 `AI_Hackertorn` 프로젝트의 **AI 테스트시나리오 자동생성 · INPUT 증강 · FLOW 제공** 플랫폼을
Skill-Driven Development(SDD) 표준으로 구현하기 위한 구조를 따른다.

단순 샘플이 아니라, 확장 가능한 **Skill-Driven Agent Architecture** Backend 중심 구조를 만든다.

> 작업 시작 시 반드시 [`docs/index.md`](../index.md)를 먼저 읽고, index가 가리키는 상세만 따른다.

---

## 1. 최종 아키텍처 결정

```text
1. Workflow와 Skill만 관리형 Hub로 둔다.
2. Graph는 코드 레벨의 공통 실행 엔진으로 유지한다.
3. graph_manifest.yml / Graph Registry를 만들지 않는다.
4. 모든 Workflow는 기본적으로 공통 plan_execution_graph로 실행한다.
5. Graph 분기는 workflow_id가 아니라 execution_policy.execution_pattern 기준
   graph_resolver.py 한 곳에서만 처리한다.
6. LangChain Deep Agent는 Core 구현 옵션일 뿐 Hub/Plan/Validator를 우회하지 않는다.
```

상세: [`../architecture/DECISIONS.md`](../architecture/DECISIONS.md)

---

## 2. 최종 디렉토리 명칭

```text
backend/app/utils/  = 일반 Backend 공통 유틸리티
backend/app/core/   = AI Agent Core Runtime
```

금지:

```text
backend/app/agent_core/
backend/app/core/config.py
```

---

## 3. 프로젝트 목표 (순서)

```text
1. 문서 SSOT (docs/index.md, AGENTS, .cursor/rules) 유지
2. backend, frontend 폴더를 Phase에 따라 생성한다
3. Backend는 Plan Execution Runtime(LangGraph 또는 동등) + SDD Hub 구조
4. Agent 실행 기준은 workflow_definitions/*.yml + skills/*/SKILL.md
5. SKILL.md는 실행 명세서이며, script/*.py는 Tool CLI 구현체
6. 서버 기동 시 Loader가 Workflow Hub / Skill Hub를 사전 로드
7. Core 흐름: route → workflow mapping → skill selection → plan → execute → review → reduce
8. Frontend는 시나리오 목록 + FLOW 편집 + 결과/KPI 검증 화면
9. 모든 출력은 정해진 JSON Schema Artifact로 연동 가능해야 한다
```

제품 North Star: [`../product/00_NORTH_STAR.md`](../product/00_NORTH_STAR.md)

---

## 4. Backend 목표 디렉토리 구조

구현 Phase에서 아래를 생성한다. (본 문서 Phase에서는 코드 생성하지 않음)

```text
backend/
├─ app/
│  ├─ main.py
│  ├─ api/routes/ · api/schemas/
│  ├─ utils/          # config, logger, exceptions, json/yaml/path
│  ├─ core/           # router, planner, orchestrator, registries, tool_runtime,
│  │                 # reviewer, reducer, memory, llm/
│  ├─ workflow_definitions/
│  ├─ langgraph_runtime/
│  │  ├─ graph_resolver.py
│  │  └─ graphs/plan_execution_graph.py
│  ├─ agents/ · agents/specs/
│  ├─ skills/{agent_name}/SKILL.md · script/
│  ├─ schemas/ · prompts/ · domain/test_automation/ · services/
├─ runtime/{session_id}/{request_id}/
├─ tests/
└─ requirements.txt
```

상세: [`../standards/BACKEND_STRUCTURE.md`](../standards/BACKEND_STRUCTURE.md)

---

## 5. 구현 대상 Capability · Agent (가칭)

| capability_id | Agent 가칭 | 역할 |
|---|---|---|
| `TEST.REPO.SYNC` | repo_sync | 저장소 엔드포인트 연결·동기화 |
| `TEST.CODE.ANALYZE` | code_analyze | 코드·주석·의존 신호 분석 |
| `TEST.SCENARIO.UNIT_GENERATE` | unit_scenario | 단위 시나리오 초안 |
| `TEST.SCENARIO.INTEGRATION_PLAN` | integration_plan | A→B→C 통합 Plan (**핵심**) |
| `TEST.PARAM.AUGMENT` | param_augment | INPUT 생성·증강 |
| `TEST.RUN.EXECUTE` | test_runner | 시나리오 실행 · **통합 FE는 Vercel MCP(DOM·스크린샷)** |
| `TEST.FLOW.COMPOSE` | flow_compose | FLOW 그래프 조립 |
| `TEST.QUALITY.KPI` | quality_kpi | 성공/실패·품질지표 · 스크린샷/DOM 관측 연결 |

Workflow는 agent 이름을 고정하지 않고 `required_capabilities`만 선언한다.

---

## 6. Workflow Definition 표준

위치: `backend/app/workflow_definitions/*.yml`  
Workflow는 LangGraph Graph가 아니다.

필수 개념 필드:

```yaml
workflow_id:
version:
name:
description:
trigger_intents:
business_goal:
required_capabilities:   # canonical capability_id 객체
logical_steps:
execution_policy:
  execution_pattern: plan_execute_review_reduce
output_contract:
decision_boundary:
  ai_role: scenario_draft_and_execution_support
  human_role: final_pass_fail_and_approval
```

few-shot: [`few-shot/template_workflow.yml`](./few-shot/template_workflow.yml)

---

## 7. SKILL.md 표준

위치: `backend/app/skills/{agent_name}/SKILL.md`  
frontmatter + 본문 섹션(Purpose … Changelog) 준수.  
few-shot: [`few-shot/template_skill.md`](./few-shot/template_skill.md)

---

## 8. script/*.py 표준

```text
argparse · main · __main__ · --input · --output
JSON/HTML 산출 · stderr+non-zero · 사용자 문장 직접 생성 금지
```

---

## 9. Frontend 목표

```text
1. Repo connect/sync UI
2. Scenario list (unit | integration)
3. FLOW editor (Figma User-Flow-Kit 계약)
4. Run results + Quality KPI
5. Human-only Pass/Fail / 승인 액션
```

상세: [`../standards/FRONTEND_FLOW_UI.md`](../standards/FRONTEND_FLOW_UI.md)

---

## 10. Guardrail

```text
1. AI는 Pass/Fail·배포를 최종 확정하지 않는다.
2. 근거 없는 의존관계·파라미터 추정 금지 → missing_data
3. Evidence/Artifact 없는 품질 단정 금지
4. 계산·파싱·집계는 script/rule
5. Graph Hub 금지
6. Deep Agent로 Hub 우회 금지
7. 통합 FE 검증: Vercel MCP로 DOM 입력/후속 결과 관측 + 단계별 스크린샷
   (입력 직후 · 결과 화면 최소 2장). DOM 없으면 missing_data
8. Vercel MCP / Playwright MCP는 사용자 동의 후
9. raw CoT / raw_prompt audit 금지
```

통합 FE step 프롬프트·Skill 계약에 넣을 최소 체크리스트:

```text
1) vercel-mcp open
2) DOM snapshot → 입력값 대조
3) action
4) DOM snapshot → 후속 결과 대조
5) screenshot 저장 (step별 권장)
6) 관측 요약만 · Pass/Fail 단정 금지
```

상세: [`.cursor/rules/02-test-automation-domain.mdc`](../../.cursor/rules/02-test-automation-domain.mdc) §5.1 · §7  
화면 계약: [`../standards/FRONTEND_FLOW_UI.md`](../standards/FRONTEND_FLOW_UI.md) §5

---

## 11. Logging

[`03_LOGGING.md`](./03_LOGGING.md) · `utils/logger.py` 공용만 사용.

---

## 12. Phase 진행

[`00_WORK_ORDER_INDEX.md`](./00_WORK_ORDER_INDEX.md)의 현재 Phase만 수행한다.
범위를 임의 확장하지 않는다.
완료 시 `docs/report/`에 보고하고, 컨텍스트 유실 시 `chain/`에 memory를 남긴다.
