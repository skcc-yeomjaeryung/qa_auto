# 메뉴와 Workflow 기능 인덱스

이 폴더는 Web Console의 **메뉴 하나를 사용자 Workflow 하나**로 보고, 화면 Route·주요 조작·Backend API·Agentic Workflow·증적·HITL 경계를 함께 관리한다.

## 공통 실행 구조

```text
사용자 메뉴 조작
  → Next.js Route/Component
  → FastAPI API/Service
  → PlatformRunnerAdapter → AgentRuntime
  → LangGraph route → plan → execute → review → reduce → response
  → Workflow Registry → Named Agent 허용 범위 → Skill/Tool → Model/Rule
  → 구조화 결과·Artifact·Agent Trace
```

CRUD·목록·집계 조회는 직접 API로 처리할 수 있다. 분석, 매핑, Graph, Scenario, 입력 추천,
브라우저 실행, 리포트처럼 Agentic 판단이나 Tool 실행이 필요한 기능은 등록 Workflow를 경유해야 한다.

## 메뉴 매핑

| 그룹 | 메뉴 | Route | 사용자 Workflow | 주요 Agentic Workflow | 상세 |
|---|---|---|---|---|---|
| MENU | 대시보드 | `/` | 전체 상태 파악 → 다음 작업 이동 | 없음(실데이터 집계) | [01](./01.대시보드.md) |
| MENU | 프로젝트 | `/projects` | 프로젝트→모델→저장소→환경→보조자료→확인 | 연결 뒤 분석 Workflow 연쇄 | [02](./02.프로젝트.md) |
| WORK | 분석 | `/analysis` | 분석 결과·소스 확인 → 시나리오 생성 | `wf_frontend_analyze`, `wf_backend_spring_analyze`, `wf_api_map`, `wf_interaction_graph`, `wf_scenario_dsl` | [03](./03.분석.md) |
| WORK | 테스트 시나리오 | `/scenarios` | 그룹→시나리오→3탭/Graph→실행·재처리 | `wf_scenario_dsl`, `wf_component_contract`, `wf_input_recommend`, `wf_browser_execute` | [04](./04.테스트시나리오.md) |
| OTHERS | 실행 이력 | `/runs` | 실행 선택 → 단계·원인·증적 확인 | 생성은 `wf_browser_execute`, 조회는 Run API | [05](./05.실행이력.md) |
| OTHERS | HITL 승인 | `/hitl` | 검토 대기 선택 → 기술 검증·증적·리포트 | `wf_run_report` | [06](./06.HITL승인.md) |
| MANAGE | 스케줄링 | `/manage/schedules` | 시나리오·환경·Cron 고정 → 반복 실행 | 예약 실행 시 Browser Run 경로 | [07](./07.스케줄링.md) |
| MANAGE | 모델 관리 | `/manage/models` | 내부/외부 모델 등록 → Health/Capability 관리 | Model Registry/Selector | [08](./08.모델관리.md) |
| MANAGE | Agent 모니터링 | `/manage/agents` | Workflow Trace → 모델·Plan·Skill·결과 감사 | 모든 Workflow Trace | [09](./09.Agent모니터링.md) |

`/batches`는 Phase 14 배치 API/UI 구현 Route지만 현재 좌측 메뉴에는 직접 노출되지 않는다. 사용자는
테스트 시나리오의 일괄 실행과 스케줄링에서 대량 실행 여정을 시작한다. `/evidence`는 `/runs?view=evidence`로 이동하고,
`/flow`는 `/scenarios` 쿼리 보존 리다이렉트다.

## Workflow Hub 카탈로그

| Workflow | 핵심 Capability | 대표 Skill | 사용 메뉴 |
|---|---|---|---|
| `wf_health_smoke` | `QA.PLATFORM.HEALTH_PING` | `health_ping` | 운영 Health |
| `wf_frontend_analyze` | `QA.CODE.FRONTEND_ANALYZE` | `frontend_analyze` | 프로젝트·분석 |
| `wf_backend_spring_analyze` | `QA.CODE.BACKEND_SPRING_ANALYZE` | `backend_spring_analyze` | 프로젝트·분석 |
| `wf_api_map` | `QA.CODE.API_MAP` | `api_map` | 분석 |
| `wf_interaction_graph` | `QA.CODE.INTERACTION_GRAPH` | `interaction_graph` | 분석·테스트 시나리오 |
| `wf_scenario_dsl` | Context 탐색·DSL·Narration | `project_context_discover`, `scenario_dsl`, `scenario_narrate` | 분석·테스트 시나리오 |
| `wf_component_contract` | `QA.CODE.COMPONENT_CONTRACT` | `component_contract` | 테스트 시나리오 |
| `wf_input_recommend` | `QA.CODE.INPUT_RECOMMEND` | `input_recommend` | 테스트 시나리오·배치 |
| `wf_browser_execute` | `QA.CODE.BROWSER_EXECUTE` | `browser_execute` | 테스트 시나리오·실행·스케줄 |
| `wf_run_report` | `QA.RUN.REPORT_GENERATE` | `run_report` | HITL 승인 |

## 변경 동기화 규칙

메뉴 기능을 변경하면 같은 커밋에서 다음을 확인한다.

1. `frontend/lib/nav.ts`의 메뉴명·Route와 본 인덱스가 같은가.
2. 화면의 주요 CTA와 해당 메뉴 문서의 사용자 Workflow가 같은가.
3. API 추가·변경이 메뉴 문서와 OpenAPI/Pydantic 계약에 반영됐는가.
4. Agentic 기능이 `PlatformRunnerAdapter → AgentRuntime`과 등록 Workflow를 경유하는가.
5. Workflow/Skill/Capability 변경이 Hub YAML, `SKILL.md`, Registry 교차검증, 본 카탈로그에 반영됐는가.
6. 기술 완료·관측 상태를 HITL 최종 Pass로 표현하지 않는가.
7. Secret·PII·chain-of-thought가 UI·API·Trace·SQLite에 노출되지 않는가.

구현 SSOT는 코드이며, 운영 정책 SSOT는 [`../index.md`](../index.md)와
[`../02.아키텍처/05.BackendSDD구조.md`](../02.아키텍처/05.BackendSDD구조.md)다.
