# Phase 00 — 파일럿 공통 기반과 샘플 관통 시스템 구축

## 이 프롬프트의 역할

당신은 대형 SI 프로젝트용 AI Code-to-E2E 관통 테스트 플랫폼의 수석 개발자다.  
프로젝트 루트에서 먼저 다음 문서를 읽고 현재 코드 상태를 점검하라.

- `AGENTS.md`
- `README.md`
- `index.md`
- `00_common_context.md`
- `00_pilot_definition_of_done.md`
- 관련 JSON Schema와 이전 Phase 완료 보고서

계획 문서만 작성하지 말고, **실제 구현·테스트·문서화·완료 보고까지 한 번의 작업으로 수행**하라.  
모호한 부분은 기존 코드와 공통 문서를 근거로 합리적인 기본값을 채택하고, 구현을 중단하는 질문으로 돌리지 말라.

## Phase 목표


플랫폼 모노레포의 실행 가능한 골격과 파일럿 대상 Sample Frontend/Backend를 구축한다.  
이 Phase의 결과는 이후 모든 분석기와 테스트 Runner가 재현 가능한 기준 환경으로 사용된다.


## 선행조건


- 신규 Repository이거나 기존 Repository의 초기 상태
- 로컬에 Python 3.12, Node.js LTS, Java 17+, Docker/Podman 중 하나가 존재
- 외부 패키지 반입이 필요한 폐쇄망을 고려해 lockfile과 오프라인 설치 문서를 제공


## 구현 범위


- Python FastAPI Control Plane 골격
- Next.js Web Console 골격
- TypeScript Frontend Analyzer Worker 골격
- Java Backend Analyzer Worker 골격
- agent-browser MCP Runner / Adapter 골격
- PostgreSQL/Redis 로컬 인프라
- Sample `customer-portal-fe`와 `customer-service-be`
- 공통 계약 Schema와 모델 생성 기본 구조


## 상세 구현 요구사항


1. 공통 문서의 권장 모노레포 구조를 생성하되 기존 구조가 있으면 책임 단위로 매핑한다.
2. `make`, `task`, 또는 단일 스크립트로 전체 개발환경을 기동할 수 있게 한다.
3. Sample Frontend에 다음을 구현한다.
   - `/customers/search` A 화면
   - `customerId` 입력, Zod 또는 동등 Validation
   - 실제 `onSubmit`
   - `POST /api/customers/search`
   - 정상 시 `/customers/{customerId}` B 화면 이동
   - B 화면에 `customerId`, `customerName`, `riskLevel`, `status` 표시
   - 안정적 Locator를 위한 `data-testid`
4. Sample Backend에 다음을 구현한다.
   - Spring Boot API
   - `CustomerSearchRequest`, Bean Validation
   - 정상/제한/미존재 분기
   - `CustomerResponse`
   - JUnit, MockMvc, REST Assured 예제
5. agent-browser MCP로 고객조회 정상 경로 smoke 실행 절차(또는 Adapter 단위 테스트)를 최소 1건 작성한다. Playwright 예제 테스트는 선택 사항이며 기본 실행 엔진이 아니다.
6. 공통 `X-Test-Run-ID` 헤더를 수용하는 구조를 미리 둔다.
7. 모든 모듈은 Health Check를 제공한다.
8. LLM Adapter는 OpenAI-compatible 설정 인터페이스만 구현하고, 테스트에서는 deterministic fake adapter를 허용한다.
9. 샘플 데이터는 합성 데이터만 사용한다.


## API·계약·데이터


- `packages/contracts`에서 Graph, Scenario, Run, Evidence의 기본 Schema를 관리한다.
- Python Pydantic 모델과 TypeScript 타입은 JSON Schema에서 생성하거나 일관성을 자동 검사한다.
- Java DTO는 수동 복제하지 말고 최소한 Contract Test로 일치 여부를 검증한다.
- 초기 API:
  - `GET /health`
  - `GET /api/projects`
  - `POST /api/projects`
  - `GET /api/runs`


## UI 요구사항


Web Console에 최소한 다음 placeholder 화면을 만든다.

- 프로젝트
- 분석
- 시나리오
- 실행
- Evidence
- HITL

빈 화면이 아니라 라우팅, 공통 Layout, API 연결 상태가 보이도록 한다.


## 필수 테스트


- Python: API Health 및 설정 테스트
- Node: Worker Health 및 계약 로딩 테스트
- Java: Sample Backend Controller/Validation 테스트
- agent-browser MCP: 고객조회 정상 경로 1건
- Docker Compose 또는 로컬 실행 스크립트 통합 기동 테스트


## 완료 기준


- [ ] 한 명령으로 PostgreSQL, Redis, Control Plane, Web Console, Sample FE/BE를 기동한다.
- [ ] `/customers/search`에서 실제 Backend 호출 후 B 화면으로 이동한다.
- [ ] agent-browser MCP 기반 고객조회 smoke가 통과한다.
- [ ] 모든 모듈의 버전과 Health 상태를 UI 또는 API에서 확인한다.
- [ ] 오프라인 설치/실행 문서가 있다.
- [ ] 샘플에 실제 개인정보나 Secret이 없다.


## 제외 범위


- 실제 저장소 분석 구현
- 완성된 시나리오 생성
- 배치 실행
- HITL Workflow


## 산출물


- 실행 가능한 모노레포 골격
- Sample Frontend/Backend
- 기본 계약 Schema
- 로컬 인프라
- 전체 기동 문서
- Phase 완료 보고서


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-00.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
