# QA_AUTO — AI Code-to-E2E 관통 테스트 플랫폼

QA_AUTO는 대형 SI 프로젝트의 개발 PL, QA, 고객 승인자가 개발 저장소를 연결하면 AI Agent가
Frontend 화면 이벤트부터 Backend 요청·응답, 다음 화면의 데이터 바인딩까지 분석해 테스트
시나리오 초안을 만들고, 실제 브라우저 실행과 증적 수집, 사람의 최종 검토까지 연결하는 파일럿 플랫폼입니다.

```text
GitHub/Local 저장소
  → FE/BE 정적 분석 → API 매핑 → A→API→B Interaction Graph
  → AI Agent 시나리오 초안·입력 추천
  → agent-browser 실제 입력·클릭·검증
  → DOM·스크린샷·Network·로그·SHA-256 증적
  → 실행 이력 → HITL 검토 → 리포트 다운로드
```

AI는 근거가 있는 시나리오와 관측 재료를 제공하고, 최종 Pass/Fail과 품질 승인은 사람이 결정합니다.

## 주요 기능

| 메뉴 | 제공 기능 |
|---|---|
| 대시보드 | 프로젝트, 분석 변경, 시나리오·실행·검토 대기, 최근 7일 관측 현황 요약 |
| 프로젝트 | 6 STEP 프로젝트 생성·수정, 역할별 모델 정책, GitHub/Local 저장소, 실행 환경, PPTX/CSV 보조자료 등록 |
| 분석 | FE/BE 분석 목록과 전체 소스 트리 탐색, 변경분 확인, 분석 결과 기반 시나리오 생성 |
| 테스트 시나리오 | 업무 그룹·시나리오 목록, 화면 구성/실행 흐름/예상 결과, 의존관계 그래프, 재처리, 개별·일괄 실행 |
| 실행 이력 | 기술 관측 상태, 단계별 입력·결과, 판정 근거, 화면·DOM 증적, ZIP 다운로드 |
| HITL 승인 | 검토 우선순위, 실행 리포트, 기대값↔관측값 기술 검증, 증적 패키지, HTML/JSON 다운로드 |
| 스케줄링 | 자연어→Cron, 기간·시간대·환경·시나리오 고정, 업무시간 외 반복·대량 실행, 중복·파괴 동작 보호 |
| 모델 관리 | 내부망/외부 OpenAI-compatible 모델, Capability·Context·Health·API Key 안전 저장 관리 |
| Agent 모니터링 | Workflow Plan, 모델 후보·선택·실호출, Skill/Tool, Artifact, Review/Reduce 실행 Trace 확인 |

메뉴별 Route·API·Workflow의 상세 계약은
[`docs/08.메뉴와워크플로우/index.md`](docs/08.메뉴와워크플로우/index.md)를 참고하세요.

## 기술 구조

```text
frontend/                         Next.js 15 · React 19 · TypeScript Console (:3000)
backend/                          FastAPI · Pydantic · LangGraph Control Plane (:8000)
  app/workflow_definitions/       Workflow Hub
  app/skills/                     Skill Hub + 결정론 script
  app/core/                       runtime·planning·execution·quality·model·trace
  app/langgraph_runtime/          route→plan→execute→review→reduce→response
  workers/frontend-analyzer/      ts-morph 기반 FE 분석기
packages/contracts/               JSON Schema 계약
infra/                            선택형 PostgreSQL·Redis 로컬 인프라
artifacts/                        분석·시나리오·실행·증적 산출물
docs/                             유일한 정책·Phase·기능 문서 SSOT
```

Agentic 실행의 단일 진입 경로는 다음과 같습니다.

```text
메뉴/API → PlatformRunnerAdapter → AgentRuntime → LangGraph
  → Workflow/Skill Registry → ModelSelector → ToolRuntime → Skill script/worker
```

등록되지 않은 Workflow/Skill/Tool은 실행할 수 없습니다. 모델 선택과 Provider 실제 호출 완료는
구분해 Trace에 남기며, 비공개 사고과정과 Secret 원문은 저장하지 않습니다.

## 로컬 기동

### 1. 요구사항

- macOS 또는 Linux
- Python 3.12
- Node.js 20 이상과 npm
- Git
- `uv` 권장. 없으면 표준 `venv + pip` 사용 가능
- 실제 브라우저 관통 실행 시 `agent-browser` CLI와 Chrome
- PostgreSQL·Redis는 현재 파일럿 기본 기동에 필수는 아니며 인프라 연동 검증 시 Docker 사용

### 2. 의존성 설치

```bash
git clone https://github.com/skcc-yeomjaeryung/qa_auto.git
cd qa_auto

cd backend
uv sync --extra dev
cd ../frontend
npm ci
cd ../backend/workers/frontend-analyzer
npm ci
cd ../../..
```

`uv`를 사용하지 않는 경우 Backend만 다음처럼 설치합니다.

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e 'backend[dev]'
```

### 3. 서비스 시작·종료

```bash
make up-dev
```

- Web Console: [http://127.0.0.1:3000/login](http://127.0.0.1:3000/login)
- Backend Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 데모 로그인: `TEST / 1` 또는 `TEST / 1 로 바로 로그인`
- 로그: `.data/backend.log`, `.data/frontend.log`

```bash
make down-dev
```

선택형 PostgreSQL·Redis를 함께 올리려면 다음을 실행합니다.

```bash
docker compose -f infra/docker-compose.yml up -d
```

### 4. 주요 설정

| 환경변수 | 기본값/의미 |
|---|---|
| `NEXT_PUBLIC_CONTROL_PLANE_URL` | Frontend가 사용할 Backend URL, 기본 `http://127.0.0.1:8000` |
| `LLM_ENABLED` | 모델 호출 활성화. 사용 가능한 모델이 없으면 허용된 Skill은 결정론 fallback 사용 |
| `LLM_BASE_URL` | OpenAI-compatible API base, 기본 `http://127.0.0.1:11434/v1` |
| `LLM_MODEL` | 기본 모델 ID, 기본 `llama3.2` |
| `QA_AUTO_AUTH_GUARD` | Backend 사용자 헤더 Guard. 로컬 테스트 외에는 비활성화 금지 |
| `QA_AUTO_MODEL_SECRET_STORE` | 기본 운영체제 Keychain. 테스트에서만 `memory` 명시 가능 |

모델은 Console의 `관리 → 모델 관리`에서 등록할 수 있습니다. 모델 profile은 SQLite에 저장하고,
API Key 원문은 운영체제 Keychain에만 저장합니다.

## 검증

```bash
make test-backend
make test-frontend

cd backend/workers/frontend-analyzer && npm test
cd frontend && npm run test:e2e
```

`npm run test:e2e`는 브라우저와 실행 중인 로컬 서비스가 필요한 통합 검증입니다. 문서·Backend·Frontend
변경 범위에 맞춰 필요한 Gate를 선택하되 실패를 숨기지 않습니다.

## 문서 시작점

1. [`docs/continue/NEXT.md`](docs/continue/NEXT.md) — 직전 세션 핸드오프
2. [`docs/index.md`](docs/index.md) — 개발 지침과 메뉴별 기능 문서 통합 인덱스
3. [`AGENTS.md`](AGENTS.md) — 개발자·AI Agent 공통 Guardrail
4. [`docs/04.Phase실행바이블/14.배치테스트.md`](docs/04.Phase실행바이블/14.배치테스트.md) — 현재 Phase
5. [`docs/09.데모영상/AI해커톤_5분_데모_시나리오.md`](docs/09.데모영상/AI해커톤_5분_데모_시나리오.md) — 5분 데모 진행안

## 안전 원칙

- 테스트 대상은 Pilot/Sandbox로 제한하고 destructive 동작은 기본 차단합니다.
- Secret, Password, Token, Cookie, Authorization, 실제 개인정보를 산출물·로그·Trace에 저장하지 않습니다.
- Design Spec·Excel/CSV는 보조 근거이며 코드 Graph·Contract와 연결되기 전에는 결과를 확정하지 않습니다.
- 화면이나 Endpoint에 도달했다는 사실만으로 성공을 만들지 않고 기대 결과와 실제 관측을 대조합니다.
- 기술 실행 완료와 HITL 최종 승인을 분리합니다.

문서와 구현의 최종 진실원은 [`docs/index.md`](docs/index.md)입니다.
