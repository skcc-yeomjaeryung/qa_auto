# Repository-Based AI Test Automation — Implementation Plan

- 작성일: 2026-08-05
- 상위 명세: [`CURSOR_REPOSITORY_TEST_AUTOMATION_PROMPT.md`](./CURSOR_REPOSITORY_TEST_AUTOMATION_PROMPT.md)
- 기존 SSOT: [`index.md`](./index.md) · [`AGENTS.md`](../AGENTS.md) · ADR D-001~D-014
- 대상 Workspace: 현재 Git repository root
- 파일럿 저장소: `https://github.com/GoogleCloudPlatform/bank-of-anthos.git`
- 파일럿 실행 서버(기본값): `https://cymbal-bank.fsi.cymbal.dev` (연결 URL = origin · 진입 화면 `/home` 은 health path)

> 본 문서는 프롬프트 §21 지시(분석 → 갭 → 아키텍처·모델·API·Phase 계획)의 산출물이다.  
> **전면 재작성 금지** — 기존 Phase 00b~09 구현을 재사용하고, 갭만 순차 보강한다.

---

## 1. 현재 Workspace 구조 분석

```text
qa_auto/
├── frontend/                 # Next.js 15 · React 19 Web Console (:3000)
├── backend/                  # FastAPI + SDD Hub/core/LangGraph (:8000)
│   ├── app/api/              # HTTP routers
│   ├── app/services/         # domain + SQLite persist
│   ├── app/skills/           # Skill Hub (10 skills)
│   ├── app/workflow_definitions/  # Workflow Hub (9 workflows)
│   ├── app/core/             # runtime·planning·execution·quality + registries
│   ├── app/langgraph_runtime/
│   └── workers/              # frontend-analyzer(ts-morph) · backend-analyzer(javalang)
├── packages/
│   ├── contracts/            # JSON Schema
│   ├── adapter-sdk/
│   └── test-data-catalog/
├── artifacts/                # analysis · evidence · test-runs · e2e
├── .data/                    # platform_store.sqlite3 · workspaces/REPO-*
├── infra/                    # docker-compose postgres/redis (앱 미연결)
├── sample-targets/           # 비움 (외부 GitHub/Local로 연결)
├── docs/                     # SSOT 바이블 + 본 계획
└── scripts/                  # make up-dev / down-dev
```

### Console 화면 (현존)

| 경로 | 상태 |
|---|---|
| `/` `/login` `/projects` `/analysis` `/scenarios` `/runs` | 동작 (`/flow`는 `/scenarios` 리다이렉트) |
| `/evidence` `/hitl` | placeholder |
| 프로젝트 하위 연결 위자드 · 코드 트리 · 실행 상세 | 동작 (부분) |

### Phase Gate (docs SSOT)

| Phase | 상태 |
|---|---|
| 00b ~ 09 | Gate 완료 보고 존재 |
| **10.Backend추적** | **현재 포인터 · Gate 미완** |
| 11 ~ 15, 99 | 문서만 · 미완료 |

---

## 2. 기존 기술 스택 · 재사용 자산

### 2.1 스택 (확정 · 유지)

| 영역 | 기술 | 비고 |
|---|---|---|
| Console | Next.js ^15.3 · React ^19 · TypeScript ^5.8 | Tailwind 기반 SaaS 셸 (D-013) |
| Control Plane | Python ≥3.12 · FastAPI ≥0.115 · Pydantic ≥2.8 | |
| Agent Runtime | LangGraph ≥0.2 · LangChain-core ≥0.3 | Graph Hub 금지 (D-012) |
| FE Analyzer | ts-morph ^25 (worker) | + Flask HTML screen extract |
| BE Analyzer | javalang (Spring) · Python AST 보조 | Bank of Anthos Flask도 부분 지원 |
| Browser | **agent-browser CLI Skill** (`browser_execute`) | D-002 · MCP는 에이전트 검증용 |
| Persist | SQLite (`.data/platform_store.sqlite3`) + 파일 artifacts | Repository Interface로 교체 가능 |
| E2E (플랫폼 자체) | Playwright ^1.54 (Console 회귀) | 대상 앱 실행 엔진 아님 (D-003) |

### 2.2 재사용 API · Skill (삭제·우회 금지)

**핵심 API**

- `POST/GET/PATCH /api/projects` · repositories · repository-sets
- `POST /api/console/connect` · `bulk-analyze` · `generate-scenarios` · `bulk-runs`
- `GET/PUT /api/console/analyses/{id}/tree|file` · `resource-selection`
- `POST /api/analyses/frontend|backend` · api-mappings · interaction-graphs
- `POST/GET /api/scenarios` · input-profiles · runs · evidence
- `POST /api/runs/execute` (SDD plan)

**Skills / Workflows**

`frontend_analyze` · `backend_spring_analyze` · `api_map` · `interaction_graph` · `scenario_dsl` · `scenario_narrate` · `component_contract` · `input_recommend` · `browser_execute` · `health_ping`

**계약 스키마** (`packages/contracts/schemas/`)

`project` · `frontend_analysis` · `backend_analysis` · `api_mapping` · `interaction_graph` · `scenario_dsl` · `component_contract` · `input_*` · `run` · `evidence_manifest` · `plan` · Design Spec / TestDataSheet

---

## 3. 요구사항 vs 현재 구조 갭 분석

상위 명세 §1·§19 완료조건 기준.

| # | 요구 | 현재 | 갭 |
|---|---|---|---|
| G1 | 프로젝트 등록 | ✅ CRUD + SQLite | 유형·담당자·태그 필드 빈약 |
| G2 | GitHub/GitLab/SVN/Local | ⚠️ github + local only (D-007) | GitLab/SVN = 2차 · Adapter 슬롯만 |
| G3 | **실행 환경(IP/Port/URL) 등록** | ❌ Run `baseUrl` 하드코딩 기본값 `:5173` | **1순위** — `ExecutionEnvironment` 1급 모델 |
| G4 | 타겟 예시 `https://cymbal-bank.fsi.cymbal.dev/` | ❌ 미연결 | 환경 기본 프리셋 + Health Check |
| G5 | Health Check (FE/BE) | ⚠️ 플랫폼 `/health`만 | 대상 환경 health-check API |
| G6 | 코드 트리 · include/exclude | ✅ 부분 | 선택 범위→분석기 강제 필터 검증·강화 |
| G7 | Python/JS/TS/HTML 분석 | ✅ | Bank of Anthos Flask+Jinja 보강 |
| G8 | 로그인 필드·Validation 추출 | ⚠️ 부분 | LOGIN-E2E-001 수준 근거 연결 |
| G9 | FE↔BE API 관계 | ✅ api_map | 추적 헤더 join = Phase 10 |
| G10 | 시나리오 + 코드 근거 | ✅ | 승인(approve/reject) API 빈약 |
| G11 | agent-browser 실행 | ✅ | 환경 baseUrl 연동 · Network 수집 강화 |
| G12 | 단계별 스크린샷·Req/Res·Trace | ⚠️ 스크린샷/snapshot 중심 | Evidence Package (Phase 12) |
| G13 | 결과+코드 근거 동일 화면 | ⚠️ runs 상세 | `/evidence` 실화면 · 코드 하이라이트 |
| G14 | Branch/Commit 결과 기록 | ⚠️ repo에 있음 | Run 메타에 강제 기록 |
| G15 | 민감정보 마스킹 | ⚠️ 부분 | Network/Evidence 마스킹 정책 통일 |
| G16 | HITL 승인 | ⚠️ WAITING_FOR_REVIEW | Phase 15 · `/hitl` stub 제거 |
| G17 | Design Spec/Excel 업로드 | ❌ 스키마만 | 보조 Evidence (D-006) 후순위 |

**결론:** 플랫폼 골격(00b~09)은 이미 파일럿 가능 수준이다.  
상위 명세와의 핵심 불일치는 **실행 환경 1급 등록·Health Check·cymbal-bank 타겟 연동·시나리오 승인·증적/HITL 완성**이다.

---

## 4. 구현 아키텍처 제안

### 4.1 원칙

```text
기존 유지:
  Frontend(Console) ↔ Backend(SDD Control Plane) ↔ Skill/Workflow Hub
  → workers(분석) → artifacts → agent-browser 실행 → Evidence → HITL

신규/보강:
  Project
    ├─ RepositoryConnection(s)     # 기존 Repository / RepositorySet
    ├─ ExecutionEnvironment(s)     # NEW — Local/DEV/QA + cymbal-bank
    ├─ AnalysisJob / scope         # 기존 analyses + resource-selection
    ├─ Graph / Scenario            # 기존
    └─ TestRun → Evidence Package  # 보강
```

### 4.2 런타임 흐름 (상위 명세 §2.1 정렬)

```text
Repository 연결
→ 파일·프레임워크 탐지 (stack_detect)
→ AST/정적 분석 (Skill workers)
→ Screen·Event·API·Endpoint 구조화
→ 분석 근거 artifacts 저장
→ (선택) LLM narrate/bind — 후보만
→ 시나리오 검토·승인 (HITL)
→ ExecutionEnvironment.baseUrl 로 agent-browser 실행
→ DOM snapshot · screenshot · network · logs 증적
→ 사람 Pass/Fail (AI 단정 금지)
```

### 4.3 Adapter 경계

| Adapter | 1차 | 2차 |
|---|---|---|
| VcsAdapter | GitHub · Local | GitLab · SVN · ZIP |
| LanguageAnalyzer | TS/JS(ts-morph) · Python AST · HTML · Spring(javalang) · Flask | Tree-sitter 통합 · GraphQL |
| BrowserRunner | agent-browser CLI Skill | MCP 직접 오케스트레이션(옵션) |
| PersistStore | SQLite KV + files | PostgreSQL · Object Storage |

### 4.4 Guardrail (불변)

- AI Pass/Fail·배포 단정 금지 (HITL)
- `missing_data` / `UNRESOLVED` / `ASSUMPTION` 추정 금지
- Secret·Token·PII 미저장 · 마스킹
- Graph Hub / `graph_manifest` 금지
- destructive action 기본 차단 · Host Allowlist
- 계산·파싱·그래프 수치 = script/rule

---

## 5. 디렉터리 구조 제안

**현 모노레포 유지 (D-011).** 추가만 허용.

```text
backend/app/
├── api/
│   ├── environments.py          # NEW — 실행 환경 CRUD · health-check
│   └── … (기존 유지)
├── services/
│   ├── environment_models.py    # NEW
│   ├── environment_service.py   # NEW
│   └── … 
├── skills/…                     # 기존 + (후속) network_capture 보강
└── workers/…                    # 기존

frontend/
├── app/
│   ├── projects/                # 위자드에 Environment 스텝 추가
│   ├── evidence/                # stub → 실화면 (Phase 6)
│   └── hitl/                    # stub → 실화면 (Phase 6/HITL)
└── components/
    └── environments/            # NEW — EnvironmentForm · HealthBadge

packages/contracts/schemas/
└── execution_environment.schema.json   # NEW

artifacts/
├── analysis/ · scenarios/ · evidence/ · test-runs/   # 기존 정책 유지

docs/
├── CURSOR_REPOSITORY_TEST_AUTOMATION_PROMPT.md  # 상위 명세
└── implementation-plan.md                      # 본 문서
```

금지: `apps/` · 루트 `workers/` 재도입 · Graph Hub.

---

## 6. 데이터 모델 제안

공통 필드: `id`, `createdAt`, `updatedAt`, `createdBy?`, `version`, `status`.

### 6.1 신규 · 보강 Entity

```text
ExecutionEnvironment
  id, projectId
  name                  # Local | DEV | QA | STG | Cymbal
  frontendBaseUrl       # 기본값 https://cymbal-bank.fsi.cymbal.dev (origin)
  backendBaseUrl?       
  healthCheckPath       # 기본 /home (절대 경로는 origin 기준으로 해석)
  apiBasePath?
  https, verifyTls
  proxy?
  accessNotes?          # VPN 등
  testAccountRefKey?    # Secret 원문 금지
  hostAllowlisted: bool
  lastHealthStatus: unknown|up|down
  lastHealthAt?
  lastHealthDetail?     # statusCode, latencyMs, error (마스킹)

ScenarioApproval
  scenarioId, decision: approved|rejected|needs_revision
  reviewer, comment, decidedAt

# Run 보강 필드
TestRun += environmentId, environmentName,
           repositoryUrl, branch, commitSha,
           frontendBaseUrl, backendBaseUrl?
```

### 6.2 기존 Entity 매핑 (프롬프트 §15)

| 프롬프트 Entity | 현재 대응 |
|---|---|
| Project | `Project` |
| RepositoryConnection | `Repository` / `RepositorySet` |
| AnalysisJob | analyses + console analyses |
| Screen / UIElement / ApiCall / ApiEndpoint | FE/BE analysis artifacts + api_mapping |
| CodeRelation | interaction_graph edges |
| TestScenario / Step | scenario_dsl |
| TestRun / Result / Artifact | run + evidence_manifest |
| NetworkEvidence / ConsoleEvidence | Phase 12 보강 대상 |
| CodeEvidence | scenario codeRefs + analysis symbols |

`UNRESOLVED` / `ASSUMPTION` / `missing_data` 상태를 분석·시나리오 필드에 명시적으로 유지한다.

---

## 7. API 목록 제안

### 7.1 기존 유지 (대표)

```text
POST/GET/PATCH/DELETE  /api/projects
POST/GET               /api/projects/{id}/repositories
POST/GET               /api/repository-sets/{id}/sync|status|files|tree
POST/GET               /api/analyses/...
POST/GET               /api/scenarios...
POST/GET               /api/scenarios/{id}/runs
GET                    /api/runs/{runId}/evidence
POST                   /api/console/connect|bulk-analyze|generate-scenarios|bulk-runs
```

### 7.2 신규 (Phase 1 우선)

```text
POST   /api/projects/{projectId}/environments
GET    /api/projects/{projectId}/environments
GET    /api/environments/{environmentId}
PATCH  /api/environments/{environmentId}
DELETE /api/environments/{environmentId}
POST   /api/environments/{environmentId}/health-check
```

### 7.3 후속 정렬 (프롬프트 §14 별칭 · 점진 도입)

| 프롬프트 경로 | 전략 |
|---|---|
| `/analysis/start\|status\|tree\|scope` | 기존 analyses/console에 facade 또는 문서 매핑 |
| `/scenarios/{id}/approve\|reject` | ScenarioApproval 추가 (시나리오 Phase) |
| `/test-runs` | 기존 `/api/runs` 유지 · alias 선택 |

호환성: 기존 클라이언트·E2E를 깨지 않도록 **additive**만 허용.

---

## 8. Phase별 구현 계획

프롬프트 §17 Phase와 **기존 Gate Phase**를 병기한다.  
이미 Gate 통과한 항목은 “재구현”이 아니라 **갭 클로즈 체크리스트**로 다룬다.

### Phase 1 — 프로젝트 기반 · 실행 환경 (즉시)

**목표:** 프로젝트 CRUD + **ExecutionEnvironment** + Health Check + Console 등록 UI  
**파일럿 프리셋(기본값):** Frontend Base URL = `https://cymbal-bank.fsi.cymbal.dev` · Browser `chrome` · 연결 ID `testuser` (비밀번호는 secret 저장)

| 작업 | 상태 목표 |
|---|---|
| `execution_environment` 스키마·Pydantic·SQLite | NEW |
| environments API + health-check (URL/IP/Port 검증) | NEW |
| ProjectsWorkbench 위자드에 환경 스텝 | NEW |
| Run 생성 시 `environmentId` → baseUrl 주입 | 연결 |
| 프로젝트 유형/태그 필드 (경량) | 보강 |
| Lint / unit / API 테스트 | 필수 |

기존 완료로 인정: FE/BE 스캐폴딩 · SQLite · 프로젝트 CRUD · 기본 화면.

### Phase 2 — 저장소 연결 강화

- Bank of Anthos GitHub clone 경로 안정화 (이미 동작 → E2E 고정)
- 코드 트리 + include/exclude → analyzer 입력 강제
- Branch/Commit 조회 UI 노출
- 연결 오류 메시지 개선
- VcsAdapter 인터페이스 정리 (GitLab/SVN 스텁만)

### Phase 3 — 코드 분석 고도화

- LOGIN 화면 HTML/JS/Python 추출 품질 (Bank of Anthos)
- UI Element · Validation · API Call 근거 라인
- Interaction Graph ↔ 코드 근거 뷰
- `UNRESOLVED` 표기 강제

### Phase 4 — 시나리오 생성 · 승인

- LOGIN-E2E-001 형태 시나리오 템플릿 정렬
- approve / reject / needs_revision
- 중복 제거 · ASSUMPTION 표시
- 시나리오 상세 UI (코드 근거 패널)

### Phase 5 — agent-browser 실행

- 환경 baseUrl = cymbal-bank (또는 Local)
- Host Allowlist · production 경고
- 단계별 screenshot 의무 (입력 직후 + 결과)
- Network/Console 수집 강화
- Run에 commitSha/branch/environment 기록

### Phase 6 — 결과 · 증적

- `/evidence` 실화면 · Step ↔ Artifact 분할 뷰
- Request/Response Viewer + 마스킹
- 코드 근거 하이라이트
- Trace/Console 연결
- 실패 원인 요약 (LLM 후보 · HITL)

### Phase 7 — 품질 고도화 (후순위)

- 증분 분석 · 회귀 추천 · GraphQL · GitLab/SVN · 병렬 실행 · Export
- docs SSOT Phase 10~15 Gate와 동기화 완료

### docs SSOT Phase와의 동기

| 프롬프트 Phase | docs Gate Phase | 비고 |
|---|---|---|
| 1 | 01 + 환경 보강 | 본 세션 착수 |
| 2 | 01 강화 | |
| 3 | 02~05 | 대부분 완료 · BoA 품질 |
| 4 | 06~08 + 승인 | |
| 5 | 09 + 환경 연동 | |
| 6 | 10~12 | Backend추적·바인딩·증적 |
| 7 | 13~15 · 99 | HITL·배치·인수 |

---

## 9. 위험 요소 · 선행 조건

### 위험

| 위험 | 영향 | 완화 |
|---|---|---|
| cymbal-bank 외부 의존 (VPN/인증/가용성) | Health·E2E 실패 | Local BoA 병행 · health 실패 시 분석-only 모드 |
| Bank of Anthos ≠ Spring-only | BE 분석 공백 | Flask/Python analyzer 경로 유지·보강 |
| 전면 API rename | 기존 E2E 파괴 | additive only |
| Secret 유출 | 보안 | token exclude · 마스킹 · allowlist |
| AI Pass 단정 | 정책 위반 | WAITING_FOR_REVIEW · HITL UI |
| kind/Colima 등 로컬 k8s 불안정 | 로컬 타겟 실패 | 원격 cymbal-bank를 1차 실행 타겟으로 |

### 선행 조건

1. Backend `:8000` · Frontend `:3000` 기동 (`make up-dev` 또는 기존 프로세스)
2. agent-browser CLI 사용 가능
3. 파일럿 저장소 네트워크 (GitHub clone)
4. cymbal-bank URL 접근 가능 여부 사전 Health Check (실패 시 `missing_data`/down 표기, 추정 금지)
5. 파괴적 크롤·운영 송금 시나리오는 Mock/승인 게이트

### 비범위 (1차)

- SVN/GitLab 정식 수집기 (D-007)
- Postgres Graph DB 전환
- Design Spec/Excel 단독 시나리오 확정
- 운영(production) 환경 자동 실행

---

## 10. 다음 실행 순서

```text
✅ §21 분석·계획 → docs/implementation-plan.md (본 문서)
→ Phase 1 구현: ExecutionEnvironment + Health Check + Console UI + Run 연동
→ Phase 2 … 순차 Gate
→ 각 Phase 종료 시 프롬프트 보고 포맷 + docs/report/YYYYMMDD/{phase}_{n}.md
```

### Phase 1 완료 정의 (최소)

- [x] 프로젝트에 실행 환경 1개 이상 등록 가능
- [x] 기본 프리셋으로 cymbal-bank URL 선택 가능
- [x] Health Check 결과가 up/down/error로 저장·표시
- [x] 시나리오 Run이 선택한 환경의 `frontendBaseUrl`을 사용
- [x] 단위/API 테스트 + Lint 관측 기록 (`tests/test_environments_phase1.py` 5 passed)
- [x] Secret 미저장 확인 (`testAccountSecret` exclude · ref key만 유지)

---

## 11. 핵심 근거

- 상위 명세: `docs/CURSOR_REPOSITORY_TEST_AUTOMATION_PROMPT.md` §1·§4·§14~§21
- 기존 SSOT: `docs/index.md` (Phase 10) · ADR D-002·D-007·D-011·D-012
- 코드 실체: `backend/app/api/*` · `skills/*` · `frontend/app/*` · `.data/platform_store.sqlite3`
- Gate: `docs/06.완료보고/PHASE-00b` ~ `PHASE-09` 존재 · `PHASE-10` 없음
- 현재 Run 기본값: `run_models.py` / `console_models.py` `baseUrl=http://127.0.0.1:5173`
- `SourceType` = `github` \| `local` only (`repository_models.py`)
- bank_project 워크스페이스 경로: 조사 시점 **부재** (`missing_data` — 로컬 BoA 클론은 `.data/workspaces/REPO-*` 사용)

---

**요약:** 기존 qa_auto(Phase 09까지)를 뼈대로 두고, 상위 명세의 핵심 갭인 실행 환경·cymbal-bank Health·승인·증적/HITL을 Phase 1부터 순차 보강한다. 전면 재작성은 하지 않는다.
