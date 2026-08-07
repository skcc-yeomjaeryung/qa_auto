# AI_TEST 바이블 — Code-to-E2E 관통 테스트 플랫폼

> **모든 사람 · Agent는 `continue/NEXT.md`를 확인한 뒤 이 인덱스를 읽는다.**  
> 이 `docs/`가 **유일한 SSOT(Single Source of Truth)** 다.  
> 교보재 원본 스냅샷: [`_archive/20260804-prompt-package/`](./_archive/20260804-prompt-package/)  
> 구 SDD 문서: [`_archive/20260804-legacy-sdd/`](./_archive/20260804-legacy-sdd/)

---

## 한 문장 약속

```text
Frontend·Backend 저장소를 연결하면 AI가 A→API→B 시나리오를 만들고,
agent-browser MCP로 실제 관통 실행한 뒤,
DOM snapshot·스크린샷·Network·로그를 증적화하며,
최종 Pass/Fail·승인은 사람이 한다.
```

---

## 현재 Phase 포인터

| 항목 | 값 |
|---|---|
| 현재 실행 Phase | **14.배치테스트** |
| 문서 | [`04.Phase실행바이블/14.배치테스트.md`](./04.Phase실행바이블/14.배치테스트.md) |
| 규칙 | 한 세션 = 한 Phase · Gate 실패 시 다음 금지 |
| 비고 | 13 PASS · 건별 실행 콘솔 · DOM 입력 바인딩 · 섬밋/결과 증적 |

---

## 0. 읽기 순서 (고정)

```text
1. docs/continue/NEXT.md                 ← 직전 세션 핸드오프
2. docs/index.md                         ← 지금 여기
3. AGENTS.md
4. docs/00.읽는법/*
5. docs/01.제품과완료기준/*
6. docs/04.Phase실행바이블/README.md
7. 현재 Phase 문서 1개만 실행
```

컨텍스트가 흐려지면 [`07.작업메모리/`](./07.작업메모리/)에 memory를 남긴 뒤 위 순서를 다시 수행한다.  
Phase 완료 시 [`06.완료보고/`](./06.완료보고/)에 보고한다.  
**다음 세션 핸드오프:** [`continue/NEXT.md`](./continue/NEXT.md)

---

## 1. 개발 지침 문서 인덱스

| 장 | 폴더 | 역할 |
|---|---|---|
| 00 | [`00.읽는법/`](./00.읽는법/) | 바이블 사용법 · Agent 작업 규칙 |
| 01 | [`01.제품과완료기준/`](./01.제품과완료기준/) | 제품 정의 · 공통 컨텍스트 · DoD · 제외 범위 |
| 02 | [`02.아키텍처/`](./02.아키텍처/) | 종단 흐름 · 모노레포 · 의사결정 · [진행상태UI](./02.아키텍처/04.진행상태UI.md) · [Backend SDD D-012](./02.아키텍처/05.BackendSDD구조.md) |
| 03 | [`03.계약과예시/`](./03.계약과예시/) | JSON Schema · 시나리오 예시 · [세션·판정 계약 D-015](./03.계약과예시/08.세션선행조건과판정계약.md) |
| 04 | [`04.Phase실행바이블/`](./04.Phase실행바이블/) | **순차 실행 본체** (00~15, 99) |
| 05 | [`05.템플릿/`](./05.템플릿/) | Phase 완료 보고서 템플릿 |
| 06 | [`06.완료보고/`](./06.완료보고/) | Phase 완료 보고 저장소 |
| 07 | [`07.작업메모리/`](./07.작업메모리/) | 컨텍스트 유실 방지 memory |
| 08 | [`08.메뉴와워크플로우/`](./08.메뉴와워크플로우/) | Console 메뉴별 기능·Route·API·Agentic Workflow 매핑 |
| 09 | [`09.데모영상/`](./09.데모영상/) | AI 해커톤 데모 영상 시나리오·촬영 체크리스트 |
| — | [`report/`](./report/) | 날짜·회차 작업 요약 (`YYYYMMDD/{phase}_{n}.md`) |
| — | [`_archive/`](./_archive/) | 구 문서·교보재 원본 (참조만) |

개발자는 구조·정책·계약을 이 영역에서 변경한다. 기능 설명 문서가 코드의 Route·API·Workflow와
어긋나면 코드만 고치고 끝내지 말고 2번 인덱스와 해당 메뉴 문서를 함께 갱신한다.

---

## 2. 플랫폼 메뉴·Workflow 기능 인덱스

| 메뉴 | Route | 핵심 기능 | Agentic Workflow | 상세 |
|---|---|---|---|---|
| 대시보드 | `/` | 프로젝트·실행·HITL·최근 7일 요약 | 집계 조회, 직접 Workflow 없음 | [설명](./08.메뉴와워크플로우/01.대시보드.md) |
| 프로젝트 | `/projects` | 프로젝트, 모델 정책, 저장소, 환경, 보조자료 등록 | 연결 뒤 분석 Workflow 연쇄 | [설명](./08.메뉴와워크플로우/02.프로젝트.md) |
| 분석 | `/analysis` | FE/BE 소스 탐색·분석 결과·시나리오 생성 | `wf_frontend_analyze` → `wf_backend_spring_analyze` → `wf_api_map` → `wf_interaction_graph` → `wf_scenario_dsl` | [설명](./08.메뉴와워크플로우/03.분석.md) |
| 테스트 시나리오 | `/scenarios` | 그룹/상세/3탭/그래프/재처리/개별·일괄 실행 | `wf_scenario_dsl`, `wf_component_contract`, `wf_input_recommend`, `wf_browser_execute` | [설명](./08.메뉴와워크플로우/04.테스트시나리오.md) |
| 실행 이력 | `/runs` | 단계·판정 근거·증적·ZIP 확인 | 실행 결과 조회, 생성은 `wf_browser_execute` | [설명](./08.메뉴와워크플로우/05.실행이력.md) |
| HITL 승인 | `/hitl` | 검토 우선순위·기술 검증·증적·리포트 다운로드 | `wf_run_report` | [설명](./08.메뉴와워크플로우/06.HITL승인.md) |
| 스케줄링 | `/manage/schedules` | 업무시간 외 반복·대량 실행 예약 | 예약 시점에 실행 서비스·`wf_browser_execute` 경유 | [설명](./08.메뉴와워크플로우/07.스케줄링.md) |
| 모델 관리 | `/manage/models` | 내부/외부 OpenAI-compatible 모델·Capability·Health 관리 | Core Model Registry/Selector | [설명](./08.메뉴와워크플로우/08.모델관리.md) |
| Agent 모니터링 | `/manage/agents` | Plan·모델 선택·Skill/Tool·Review/Reduce Trace | 모든 등록 Workflow의 구조화 Trace | [설명](./08.메뉴와워크플로우/09.Agent모니터링.md) |

전체 매핑과 변경 규칙은 [`08.메뉴와워크플로우/index.md`](./08.메뉴와워크플로우/index.md)가 관리한다.

---

## 3. 목표 흐름

```text
Console 여정: 프로젝트 → 저장소 → 시나리오생성 → 시나리오목록 → 일괄/개별 테스트
  (Progress UI: Figma Progress Bar Kit · docs/02.아키텍처/04.진행상태UI.md)

GitHub/Local Repository
  (+ 선택: Design Spec PPT·이미지 / Excel·CSV 보조 Evidence)
  → Frontend AST 분석
  → Backend AST 분석
  → Frontend↔Backend API 매핑
  → A→B Interaction Graph
  → 실행 가능한 Scenario DSL (+ Design Spec join 후보)
  → 입력값 추천 및 증강 (Fixture → … → Excel Catalog → LLM/Design hint)
  → agent-browser MCP 실제 이벤트 (DOM snapshot + screenshot)
  → Backend 요청·응답 추적
  → B 화면 데이터 바인딩 검증
  → 증적 패키지 생성
  → 건별/배치 실행
  → 고객 HITL 승인
```

보조 입력원: [`01.제품과완료기준/02.공통컨텍스트.md`](./01.제품과완료기준/02.공통컨텍스트.md) §2.1 ·  
계약: [`03.계약과예시/04.DesignSpec스키마.md`](./03.계약과예시/04.DesignSpec스키마.md), [`03.계약과예시/05.TestDataSheet스키마.md`](./03.계약과예시/05.TestDataSheet스키마.md)

---

## 4. Phase 빠른 링크

| # | 문서 | 종료 Gate |
|---|---|---|
| 00 | [기반구축](./04.Phase실행바이블/00.기반구축.md) | 모노레포 기동, 샘플 FE/BE 연동 |
| 00b | [BackendSDD기반](./04.Phase실행바이블/00b.BackendSDD기반.md) | Workflow/Skill Hub · core · LangGraph Gate |
| 01 | [저장소연결](./04.Phase실행바이블/01.저장소연결.md) | URL/Local 수집 · Commit 고정 |
| 02 | [Frontend분석](./04.Phase실행바이블/02.Frontend분석.md) | 화면·이벤트·API·Route 추출 |
| 03 | [Backend분석](./04.Phase실행바이블/03.Backend분석.md) | Spring 대상 · Python Agent/Tool 추출 (D-010) |
| 04 | [API매핑](./04.Phase실행바이블/04.API매핑.md) | FE↔BE 매핑 · 불일치 표시 |
| 05 | [InteractionGraph](./04.Phase실행바이블/05.InteractionGraph.md) | A→API→B 흐름 시각화 (PASS · Figma User Flow Kit) |
| 06 | [시나리오DSL](./04.Phase실행바이블/06.시나리오DSL.md) | Schema DSL · Console 체인 glue (PASS) |
| 07 | [컴포넌트계약](./04.Phase실행바이블/07.컴포넌트계약.md) | 필수 입력·Locator·바인딩 계약 (PASS) |
| 08 | [입력값추천](./04.Phase실행바이블/08.입력값추천.md) | Input Profile · Catalog · 정상·경계·오류 (PASS) |
| 09 | [브라우저실행](./04.Phase실행바이블/09.브라우저실행.md) | agent-browser A→B · Run API (PASS) |
| 10 | [Backend추적](./04.Phase실행바이블/10.Backend추적.md) | Test Run ID 관통 로그 (PASS) |
| 11 | [바인딩검증](./04.Phase실행바이블/11.바인딩검증.md) | Input↔UI 값 비교 (PASS) |
| 12 | [증적수집](./04.Phase실행바이블/12.증적수집.md) | Evidence Package (PASS) |
| 13 | [건별테스트](./04.Phase실행바이블/13.건별테스트.md) | 건별 실행 UI (PASS) |
| 14 | [배치테스트](./04.Phase실행바이블/14.배치테스트.md) | 배치 무인 실행 (**현재**) |
| 15 | [HITL승인](./04.Phase실행바이블/15.HITL승인.md) | 고객 승인·Audit Trail |
| 99 | [통합인수검증](./04.Phase실행바이블/99.통합인수검증.md) | 파일럿 인수 데모 |

권장 DAG: [`04.Phase실행바이블/README.md`](./04.Phase실행바이블/README.md)

---

## 5. 절대 금지 (요약)

```text
- docs 밖(옛 프롬프트 패키지·archive)을 SSOT로 취급
- Hub에 없는 Workflow/Skill/Tool을 LLM·코드가 발명·우회 (D-012)
- Graph Hub · graph_manifest.yml · Graph Registry
- AI가 Pass/Fail·배포를 최종 확정 (DOM·스크린샷만으로도 단정 금지)
- Endpoint·화면 도달만으로 성공 기록 (D-015: 기대 결과 대조 + 사유 필수)
- 인증 뒤 화면·로그아웃을 선행 로그인 없이 실행 (D-015: 연결 정보 계정·세션 승계)
- Design Spec/Excel만으로 시나리오·INPUT·기대값 확정 (보조 hint만 허용)
- 근거 없는 의존·파라미터·기대값 추정 → missing_data
- agent-browser / Playwright MCP 무단·파괴적 사용 (사용 전 사용자 문의)
- Gate 실패인데 다음 Phase로 진행
- apps/ · 루트 workers/ 재도입 (D-011: frontend/ · backend/ 강제)
```

---

## 6. Root · Cursor Rules

| 경로 | 용도 |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | 방향성 · 컨텍스트 앵커 |
| [`../README.md`](../README.md) | 사람용 입구 |
| [`../CURSOR_APPLY_INSTRUCTIONS.md`](../CURSOR_APPLY_INSTRUCTIONS.md) | Cursor 읽기 순서 |
| [`../.cursor/rules/`](../.cursor/rules/) | alwaysApply 절대 규칙 |
| [`../.cursor/rules/03-post-report.mdc`](../.cursor/rules/03-post-report.mdc) | 날짜·회차 `docs/report/` 요약 의무 |
| [`02.아키텍처/02.모노레포구조.md`](./02.아키텍처/02.모노레포구조.md) | D-011 `frontend/` · `backend/` 루트 |
| [`02.아키텍처/05.BackendSDD구조.md`](./02.아키텍처/05.BackendSDD구조.md) | D-012 NH_AML 정렬 SDD |
| [`08.메뉴와워크플로우/index.md`](./08.메뉴와워크플로우/index.md) | 메뉴·Route·API·Workflow 운영 매핑 |
| [`09.데모영상/index.md`](./09.데모영상/index.md) | 데모 시나리오와 촬영 자산 |
| [`05.템플릿/few-shot/`](./05.템플릿/few-shot/) | Workflow·SKILL.md 교보재 작성 포맷 |
| [`07.작업메모리/20260804-backend-sdd-d012.md`](./07.작업메모리/20260804-backend-sdd-d012.md) | backend 폐기·D-012 memory |
| [`continue/NEXT.md`](./continue/NEXT.md) | 다음 세션 Phase·방향 핸드오프 |
