# Backend 구조 표준 (Python)

색인: [`../index.md#backend`](../index.md#backend)

---

## 1. 목표 트리 (후속 Phase에서 생성)

코드는 아직 만들지 않는다. **앞으로 이 트리를 따른다.**

```text
backend/
├─ app/
│  ├─ main.py
│  ├─ api/
│  │  ├─ routes/
│  │  └─ schemas/          # HTTP DTO
│  ├─ utils/                 # config, logger, exceptions, json/yaml/path
│  ├─ core/                  # Agent Core Runtime
│  │  ├─ router/
│  │  ├─ planner/
│  │  ├─ orchestrator/
│  │  ├─ workflow_registry/
│  │  ├─ skill_registry/
│  │  ├─ tool_runtime/
│  │  ├─ reviewer/
│  │  ├─ reducer/
│  │  ├─ memory/
│  │  └─ llm/               # client, prompt_loader, messages, structured_output
│  ├─ workflow_definitions/  # Workflow Hub *.yml
│  ├─ langgraph_runtime/
│  │  ├─ graph_resolver.py
│  │  ├─ graphs/plan_execution_graph.py
│  │  ├─ nodes/
│  │  ├─ edges/
│  │  └─ state/
│  ├─ agents/
│  │  ├─ specs/
│  │  └─ {agent_name}/agent.py
│  ├─ skills/
│  │  └─ {agent_name}/
│  │     ├─ SKILL.md
│  │     ├─ script/
│  │     ├─ sample_input/
│  │     └─ output/          # 로컬 샘플만
│  ├─ schemas/               # 내부 Structured Output
│  │  └─ base.py
│  ├─ prompts/{area}/
│  ├─ domain/test_automation/
│  └─ services/
├─ runtime/{session_id}/{request_id}/
│  ├─ inputs/
│  ├─ intermediate/
│  ├─ outputs/
│  ├─ reports/
│  └─ traces/
├─ tests/
├─ requirements.txt
└─ README.md
```

---

## 2. 계약

| 규칙 | 내용 |
|---|---|
| Structured Output | Pydantic, `extra=forbid` 권장 |
| LLM Client | 싱글턴/팩토리, 모듈별 재생성 금지 |
| Prompts | `prompts/`만, 하드코딩 금지 |
| Logging | `utils/logger.py` + `log_event` JSON |
| Hub 로드 | 기동 시 Workflow/Skill 사전 로드 |
| Graph Hub | 금지 |

---

## 3. API 경계 (개념)

```text
/api/chat 또는 /api/runs     = 업무 요청 진입 (독자 Agent 엔드포인트 난립 금지)
/api/repos                   = 저장소 연결·동기화 상태
/api/scenarios               = 시나리오 CRUD·목록
/api/flows                   = FLOW 그래프 조회·편집
/api/runs/{id}/results       = 실행 결과·KPI
```

신규 Chat/LLM 클라이언트를 화면마다 만들지 않는다. 공통 Core를 통한다.

---

## 4. Runtime Workspace

실제 산출물은 `backend/runtime/{session_id}/{request_id}/`에만 저장한다.
`skills/*/output/`은 개발자 로컬 샘플용이다.
