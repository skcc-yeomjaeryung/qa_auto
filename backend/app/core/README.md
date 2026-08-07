# QA_AUTO 단일 Core 책임 구조

`app/core/`는 Workflow Hub와 Skill Hub를 실행하는 유일한 Control Plane이다. `corev2`를 만들지 않는다.
2026-08-07 완전 통합에서 구 wrapper 경로를 제거했으며 아래 책임 경로만 사용한다.

## 실행 흐름

```text
API / Console
  → AgentRuntime
  → LangGraph: route → plan → execute → review → reduce → response
  → Workflow Registry → Agent Registry → Skill Registry
  → ModelSelector → ToolRuntime → Skill script / worker
  → Artifact + 구조화 Agent Trace
```

## 책임 경계

| 경로 | 단일 책임 |
|---|---|
| `runtime/` | 메뉴와 서비스가 호출하는 안정된 Core facade |
| `router/` | 등록 Workflow 라우팅 |
| `planning/` | capability 기반 Agent·Skill·Tool·모델 선택, `plan/v2` 생성 |
| `execution/` | `dependsOn` 순서, 선행 결과 전달, 단계 실행 이벤트 |
| `quality/` | Evidence/Schema 검토와 다음 단계용 결과 축약 |
| `models/` | 모델 등록, `/v1/models` health, 정책 기반 결정 |
| `observability/` | Trace와 구조화 결정 감사 로그 |
| `context/` | 큰 입력을 한 번 저장하고 Plan에는 참조만 전달 |
| `prompts/` | `app/prompts/` 역할 프롬프트의 LangChain 로더·버전·해시 |
| `catalog/` | Named Agent 허용 Skill 경계 |
| `workflow_registry/` | Workflow Hub 로드 |
| `skill_registry/` | Skill Hub 로드 |
| `capability_registry/` | capability 계약 로드 |
| `tool_runtime/` | Plan에 확정된 Tool 실행과 선택 모델 환경 주입 |
| `llm/` | OpenAI-compatible LLM/VLM/embedding 통신 |

## 모델 결정 규칙

1. 프로젝트는 모델 ID 대신 `auto`, `cost_saver`, `balanced`, `highest_quality`, `internal_only` 중 운영 정책을 저장한다.
2. Skill이 `capabilities`, 최소 context, structured output, tool calling, 품질 profile을 요구한다.
3. Core가 비활성·배포 정책 위반·capability 부족·context 부족·health down 후보를 먼저 제외한다.
4. 남은 후보만 품질·신뢰도·속도·비용 가중치와 health penalty로 정렬한다.
5. 선택 모델은 표시용 메타데이터로 끝나지 않고 Tool subprocess의 `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_ENABLED`에 주입된다.
6. Tool subprocess는 서버와 같은 Python interpreter를 사용하며, Provider 응답 ID·처리 시간·사용량을 비밀값 없는 호출 영수증으로 부모 Runtime에 반환한다.
7. 적합한 모델이 없거나 호출·구조 검증에 실패하고 Skill이 허용하면 결정론 fallback을 사용한다. 모델 선택과 모델 실사용은 별도 상태다.

모델 profile은 SQLite에 저장한다. API Key 원문은 운영체제 Keychain에 저장하고 SQLite·API 응답·Agent Trace에는 노출하지 않는다.
테스트 환경 또는 `QA_AUTO_MODEL_SECRET_STORE=memory`를 명시한 경우에만 메모리 fallback을 사용한다.

## 관측과 프라이버시

Agent Trace는 후보 점수, 제외 사유, 선택 결과, 실제 모델 호출 영수증, Plan, Skill/Tool 상태, Artifact, Review, Reduce 결과를 기록한다.
모델의 비공개 사고과정(chain-of-thought)은 수집하거나 노출하지 않는다. 운영자가 재현할 수 있는 구조화 근거만 제공한다.
`secret`, `password`, `token`, `apiKey`, `authorization`, `cookie` 계열 필드는 저장 전에 마스킹된다.
Prometheus/Grafana는 `/metrics`의 `qa_auto_model_invocations_total`, `qa_auto_model_tokens_total`,
`qa_auto_model_selected_without_invocation`을 사용한다. 모델 선택 건수만으로 사용량을 계산하지 않는다.

## 프롬프트 관리

역할 프롬프트의 SSOT는 `app/prompts/`다. Core와 서비스는 `PromptCatalog`를 통해 LangChain
`ChatPromptTemplate` 또는 system prompt를 로드하고, 버전과 SHA-256을 함께 남긴다. 런타임은 영어
`*_system.md`만 참조하며, 동일 이름의 `*_system_KOR.md`는 사람 검토용 원문 보관본이다. 소스 코드 안에
역할 시스템 프롬프트를 직접 작성하지 않는다. 상세 정책은 `app/prompts/README.md`를 따른다.

## 단일 import 규칙

Core 역할은 다음 공식 경로에서만 가져온다.

- `Planner` → `app.core.planning`
- `Orchestrator` → `app.core.execution`
- `Reviewer`, `Reducer` → `app.core.quality`

구 `planner`, `orchestrator`, `reviewer`, `reducer` package와 re-export는 존재하지 않는다.
이 이름으로 새 package를 다시 만들지 않으며, 외부 호출부는 `AgentRuntime`을 안정된 facade로 사용한다.
