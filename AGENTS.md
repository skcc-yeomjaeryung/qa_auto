# AGENTS.md — AI_TEST Code-to-E2E 관통 테스트 플랫폼

이 문서는 이 저장소에서 작업하는 개발자와 AI 코딩 에이전트가 **방향을 잃지 않도록**
붙드는 컨텍스트 앵커다.  
정책·Phase·계약의 진실원은 항상 [`docs/index.md`](docs/index.md)다.

## 컨텍스트 유실 방지 (강제)

```text
1. 작업 시작 = docs/continue/NEXT.md (핸드오프) → docs/index.md
2. index가 링크한 상세 지침만 따른다
3. 현재 Phase 문서 범위를 넘기지 않는다 (한 세션 = 한 Phase)
4. 컨텍스트가 흐려지면 docs/07.작업메모리/ 에 memory 작성 후
   docs/index.md 읽기 순서를 다시 수행한다
5. Phase 완료 시 docs/06.완료보고/ 에 보고한다
6. 세션 종료 시 docs/continue/NEXT.md 를 다음 Phase에 맞게 갱신한다
```

### 현재 Phase 포인터

| 항목 | 값 |
|---|---|
| 현재 실행 Phase | **14.배치테스트** ([`docs/index.md`](docs/index.md)와 동기) |
| 문서 | [`docs/04.Phase실행바이블/14.배치테스트.md`](docs/04.Phase실행바이블/14.배치테스트.md) |
| 규칙 | 한 세션 = 한 Phase · Gate 실패 시 다음 금지 |
| 비고 | 13 PASS · 건별 실행 콘솔 · DOM 입력 바인딩 · 섬밋/결과 증적 |

### 읽기 순서 (필수 — `docs/index.md`와 동일)

```text
1. docs/continue/NEXT.md                 ← 직전 세션 핸드오프
2. docs/index.md                         ← SSOT 인덱스
3. AGENTS.md                             ← 지금 여기
4. docs/00.읽는법/*
5. docs/01.제품과완료기준/*
6. docs/04.Phase실행바이블/README.md
7. 현재 Phase 문서 1개만 실행
```

alwaysApply Cursor Rules (작업 중 자동 적용, 별도 순차 열람 불필요):

- [`.cursor/rules/00-absolute-sdd-architecture.mdc`](.cursor/rules/00-absolute-sdd-architecture.mdc) — 구조·실행 Guardrail
- [`.cursor/rules/01-ai-answer-format.mdc`](.cursor/rules/01-ai-answer-format.mdc) — 답변 포맷
- [`.cursor/rules/02-test-automation-domain.mdc`](.cursor/rules/02-test-automation-domain.mdc) — 도메인 · agent-browser · HITL · Figma
- [`.cursor/rules/03-post-report.mdc`](.cursor/rules/03-post-report.mdc) — 날짜·회차 `docs/report/` 작업 요약
- [`.cursor/rules/04-frontend-agent-browser.mdc`](.cursor/rules/04-frontend-agent-browser.mdc) — FE UX 고도화 시 agent-browser auto-run · localStorage/SQLite · 레이아웃 Guardrail

Agent 체크리스트 상세: [`docs/00.읽는법/02.Agent작업규칙.md`](docs/00.읽는법/02.Agent작업규칙.md)

---

## 1. 프로젝트 목적

`QA_AUTO`는 대형 SI에서 **개발 PL / QA / 고객 승인자**가
Frontend·Backend 저장소를 연결하고, AI로 **Code-to-E2E 관통 테스트**를 수행하는 파일럿이다.

한 문장 약속 ([`docs/01.제품과완료기준/01.한문장약속.md`](docs/01.제품과완료기준/01.한문장약속.md)):

```text
개발 저장소의 Frontend·Backend 소스를 정적 분석해
A 화면의 컴포넌트 이벤트부터 Backend 요청·응답,
B 화면 이동과 데이터 바인딩까지 하나의 시나리오로 생성하고,
agent-browser MCP로 실제 관통 테스트를 수행해
DOM snapshot·스크린샷·Network·로그를 증적화한 뒤
고객 HITL 승인을 받는다.
```

### Console 주 여정

```text
프로젝트 생성 → 저장소 연결 → 시나리오 생성 → 시나리오 목록 → 일괄/개별 테스트
```

진행·완료·스텝 UI: [`docs/02.아키텍처/04.진행상태UI.md`](docs/02.아키텍처/04.진행상태UI.md) (D-009)

### 핵심 가치 사슬

```text
① 시나리오 생성 (FE/BE 분석 · Graph · Scenario DSL)
② 입력 추천 · agent-browser 실행 · 추적 · 바인딩 · Evidence
③ 건별/배치 · HITL 승인
```

### 프로젝트 핵심 난제

```text
의존관계 분석 → 유의미한 A→API→B 통합 시나리오 →
agent-browser 실행 → 증적 → HITL
```

Swagger식 API 파라미터 테스트만으로 끝내지 않는다.  
**Backend + Frontend 화면 연계**를 포함한다.  
통합 FE 검증은 **agent-browser MCP(DOM snapshot + 스크린샷)** 가 기본이다.  
Playwright MCP/Test는 보완·레거시 또는 대상 저장소 Evidence 추출용이다.

완료 기준: [`docs/01.제품과완료기준/03.파일럿완료기준.md`](docs/01.제품과완료기준/03.파일럿완료기준.md)

---

## 2. 문서 SSOT

```text
docs/                         = 유일한 바이블 (SSOT)
docs/04.Phase실행바이블/      = 순차 실행 본체
docs/08.메뉴와워크플로우/     = Console 메뉴별 기능·Workflow 운영 설명
docs/09.데모영상/             = 데모 영상 시나리오·촬영 체크리스트
docs/_archive/                = 구 SDD·교보재 원본 (참조만)
```

정책을 archive나 옛 프롬프트 패키지에서 바꾸지 않는다.

---

## 3. Phase 실행

```text
현재 Phase = docs/index.md 의 포인터
권장 DAG   = docs/04.Phase실행바이블/README.md
완료 보고  = docs/06.완료보고/PHASE-XX.md
템플릿     = docs/05.템플릿/01.Phase완료보고서.md
```

Gate 실패 시 다음 Phase로 가지 않는다.  
계획만 쓰지 말고 구현·테스트·문서·완료 보고까지 수행한다.

---

## 4. 플랫폼 기술 (요약)

| 영역 | 기술 |
|---|---|
| Control Plane | `backend/` · FastAPI + **SDD Hub/core/LangGraph** (D-012) |
| Web Console | `frontend/` · Next.js · React · TypeScript |
| FE Analyzer | Skill Hub → `backend/workers/frontend-analyzer` · ts-morph |
| BE Analyzer | Skill Hub → Spring 대상 Python Tool (D-010 · D-012 재편) |
| Browser Runner | **agent-browser MCP** (Playwright MCP = 보완·레거시) |
| Graph 저장 | PostgreSQL Node/Edge |
| Queue/Cache | Redis |
| 계약 | `docs/03.계약과예시/schemas/` |
| VCS 1차 | GitHub URL + Local Path (D-007) |

모노레포 책임 경계: [`docs/02.아키텍처/02.모노레포구조.md`](docs/02.아키텍처/02.모노레포구조.md)  
의사결정: [`docs/02.아키텍처/03.의사결정기록.md`](docs/02.아키텍처/03.의사결정기록.md) (D-001~D-012)  
Backend SDD: [`docs/02.아키텍처/05.BackendSDD구조.md`](docs/02.아키텍처/05.BackendSDD구조.md)

### Agentic Core 절대 경계 (D-016)

```text
메뉴/API
  → PlatformRunnerAdapter
  → AgentRuntime
  → LangGraph route → plan → execute → review → reduce → response
  → Workflow/Skill Registry → ToolRuntime → Skill script/worker
```

- 외부 서비스가 호출하는 안정 facade는 `backend/app/core/runtime/AgentRuntime` 하나다.
- Core 공식 책임은 `planning`·`execution`·`quality`·`runtime`이다. 제거된
  `core/planner`·`core/orchestrator`·`core/reviewer`·`core/reducer` wrapper를 재도입하지 않는다.
- 분석·API 매핑·Interaction Graph·Scenario DSL·입력 추천·브라우저 실행·리포트는
  반드시 `backend/app/workflow_definitions/`에 등록된 Workflow와 `backend/app/skills/`를 경유한다.
- CRUD service는 허용하지만 Agentic 판단, 모델 선택, Skill 실행을 service에 중복 구현하지 않는다.
- Plan은 `plan/v2`로 검증하고 capability → Named Agent 허용 범위 → Skill/Tool → 모델 순서로 결정한다.
- 모델 **선택**과 Provider **실호출 완료 영수증**은 별도 상태로 기록한다. 비공개 사고과정은 저장하지 않는다.
- 모델 profile은 SQLite에, API Key 원문은 운영체제 Keychain에 저장한다. API·Trace·SQLite에는 원문을 남기지 않는다.
- 메뉴와 Workflow의 운영 매핑은 [`docs/08.메뉴와워크플로우/index.md`](docs/08.메뉴와워크플로우/index.md)가 진실원이다.

---

## 5. Structured Output · LLM

- 입출력은 Schema로 검증한다.
- LLM은 요약·설명·후보 추천만 한다.
- Commit/파일/라인·Endpoint·기대값을 근거 없이 확정하지 않는다.
- LLM 출력은 JSON Schema 검증과 Evidence 참조 후에만 저장한다.
- Design Spec·Excel은 매핑 **후보**만 — 단독 확정 금지 (D-006).
- 신뢰도·`unresolved` 규칙: [`docs/01.제품과완료기준/02.공통컨텍스트.md`](docs/01.제품과완료기준/02.공통컨텍스트.md) §6

---

## 6. 도메인 Guardrail

```text
1. AI는 Pass/Fail·배포를 최종 확정하지 않는다.
2. AI는 시나리오·INPUT·실행 관측 재료를 제공한다.
3. 최종 품질/승인은 사람(PL/QA/고객)이 한다.
4. Evidence 없는 품질 단정 금지.
5. 없는 값은 추정하지 않고 missing_data.
6. 통합 FE: agent-browser로 DOM·스크린샷 관측 (입력 직후 + 결과 화면).
7. agent-browser / Playwright / Figma MCP 사용 전 사용자 문의. 무단 파괴적 크롤 금지.
8. Design Spec(PPT/이미지)·Excel/CSV는 보조 Evidence다.
   코드 Graph·Contract와 join되기 전에 Scenario/INPUT/기대값을 확정하지 않는다.
9. Interaction Graph / FLOW UI는 Figma User Flow Kit을 MCP로 참조한다
   (file qpZeClozlSVQd6j8Od8P9x · kit 0:1 · Example 1:319). 임의 Flow UI 금지 (D-008).
10. 여정·시나리오·실행 Progress는 Figma Progress Bar UI Kit을 MCP로 참조한다
    (file HLWN6f7fxSVMIxoZtW6SIc · 799:98620). Complete ≠ HITL Pass (D-009).
11. 임의 sleep 금지 — snapshot/selector/network 조건 대기.
12. DOM 직접 값 주입 금지 — fill/click 등 실제 사용자 이벤트만.
13. Secret·Token·개인정보는 저장하지 않는다. Pilot/Sandbox만. destructive 기본 차단.
```

제외 범위: [`docs/01.제품과완료기준/04.범위와제외항목.md`](docs/01.제품과완료기준/04.범위와제외항목.md)

### 보조 Evidence · 계약

| 항목 | 문서 |
|---|---|
| Design Spec / Excel 정책 | [`docs/01.제품과완료기준/02.공통컨텍스트.md`](docs/01.제품과완료기준/02.공통컨텍스트.md) §2.1 |
| DesignSpec Schema | [`docs/03.계약과예시/04.DesignSpec스키마.md`](docs/03.계약과예시/04.DesignSpec스키마.md) |
| TestDataSheet Schema | [`docs/03.계약과예시/05.TestDataSheet스키마.md`](docs/03.계약과예시/05.TestDataSheet스키마.md) |
| Flow UI (Figma) | [`docs/04.Phase실행바이블/05.InteractionGraph.md`](docs/04.Phase실행바이블/05.InteractionGraph.md) |
| Progress UI (Figma) | [`docs/02.아키텍처/04.진행상태UI.md`](docs/02.아키텍처/04.진행상태UI.md) |
| 브라우저 실행 | [`docs/04.Phase실행바이블/09.브라우저실행.md`](docs/04.Phase실행바이블/09.브라우저실행.md) |

---

## 7. 영역별 바로가기

| 영역 | 상세 |
|---|---|
| 바이블 표지 | [`docs/index.md`](docs/index.md) |
| 제품·DoD | [`docs/01.제품과완료기준/`](docs/01.제품과완료기준/) |
| 아키텍처 | [`docs/02.아키텍처/`](docs/02.아키텍처/) |
| Phase 실행 | [`docs/04.Phase실행바이블/`](docs/04.Phase실행바이블/) |
| 계약·예시 | [`docs/03.계약과예시/`](docs/03.계약과예시/) |
| 브라우저 실행 | [`docs/04.Phase실행바이블/09.브라우저실행.md`](docs/04.Phase실행바이블/09.브라우저실행.md) |
| 작업 memory | [`docs/07.작업메모리/`](docs/07.작업메모리/) |
| 완료 보고 | [`docs/06.완료보고/`](docs/06.완료보고/) |
| 회차 요약 | [`docs/report/`](docs/report/) (`YYYYMMDD/{phase}_{n}.md`) |
| 모노레포 | [`docs/02.아키텍처/02.모노레포구조.md`](docs/02.아키텍처/02.모노레포구조.md) (D-011: `frontend/` · `backend/`) |
| 메뉴·Workflow | [`docs/08.메뉴와워크플로우/`](docs/08.메뉴와워크플로우/) |
| 데모 영상 | [`docs/09.데모영상/`](docs/09.데모영상/) |
