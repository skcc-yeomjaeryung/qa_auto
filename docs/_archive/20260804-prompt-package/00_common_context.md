# 공통 구현 컨텍스트

## 1. 제품 정의

이 프로젝트는 **AI 기반 Code-to-E2E 관통 테스트 플랫폼 파일럿**이다.

플랫폼은 개발자의 Frontend와 Backend 저장소를 읽고 다음을 수행한다.

1. A 화면의 컴포넌트, 입력 속성, 이벤트, Route, API 호출을 정적 분석한다.
2. Backend Controller, DTO, Validation, Service 진입점, Response, 기존 테스트를 정적 분석한다.
3. Frontend API 호출과 Backend Endpoint를 연결한다.
4. `A 화면 → 컴포넌트 이벤트 → API Request → Backend 처리 → API Response → B 화면 이동 → UI 바인딩` 흐름을 Interaction Graph로 생성한다.
5. Graph를 실행 가능한 Scenario DSL로 변환한다.
6. 필수 입력과 제약을 추출하고 추천 테스트 데이터를 생성한다.
7. **agent-browser MCP**로 실제 입력·클릭·Blur·Submit 이벤트를 발생시키고 DOM snapshot·스크린샷을 수집한다.
8. Frontend Network와 Backend Structured Log를 Correlation ID로 연결한다.
9. Backend Response와 B 화면 표시값을 검증한다.
10. Screenshot, DOM snapshot, Network, Backend Log, Assertion을 Evidence Package로 만든다.
11. 건별·배치 테스트를 제공한다.
12. 자동 검증 후 반드시 고객 HITL 승인 또는 반려를 받는다.

## 2. 1차 범위에서 제외

- 테스트 진척률 계산
- 개발자별 품질 점수
- 팀별 순위
- 미래 결함 예측
- 운영 Merge 자동 차단
- 운영 데이터 변경
- 모든 개발언어 지원
- DOM 또는 이미지 정보만으로 확정 시나리오 생성
- LLM의 근거 없는 기대값 확정

## 3. 대상 기술

### 분석 대상 Frontend
- TypeScript / JavaScript
- React
- Next.js App Router 및 Pages Router
- React Hook Form, Zod/Yup은 우선 지원
- fetch, Axios, React Query는 우선 지원
- (선택) 기존 Playwright Test — 대상 저장소 Evidence 추출용

### 분석 대상 Backend
- Java 17 이상
- Spring Boot 3.x 우선
- Spring MVC
- Bean Validation
- JUnit 5
- MockMvc
- REST Assured

### 플랫폼 기술
- Control Plane: Python 3.12, FastAPI, Pydantic v2
- Web Console: Next.js, React, TypeScript
- Frontend Analyzer Worker: Node.js, TypeScript Compiler API, ts-morph
- Backend Analyzer Worker: Java, JavaParser + Symbol Solver
- Browser Runner: **agent-browser MCP** (기본). Playwright MCP는 보완·레거시 경로이며 사용 전 사용자 문의
- Database: PostgreSQL
- Queue/Cache: Redis
- Evidence: Local filesystem을 기본으로 하되 S3-compatible adapter 인터페이스 제공 (screenshot + DOM snapshot + network)
- LLM: OpenAI-compatible local endpoint. GPT-OSS 또는 Gemma 계열을 설정으로 교체
- Common fallback parser: Tree-sitter. 단, 의미 분석의 주 도구로 사용하지 않는다.

## 4. 권장 모노레포 구조

```text
apps/
  control-plane/            # Python FastAPI
  web-console/              # Next.js UI

workers/
  frontend-analyzer/        # Node/TypeScript
  backend-analyzer/         # Java
  agent-browser-runner/     # agent-browser MCP Adapter / Run Worker

packages/
  contracts/                # JSON Schema, generated models
  adapter-sdk/              # 사내 UI/API 프레임워크 확장점
  test-data-catalog/        # 초기 Best Practice 데이터

sample-targets/
  customer-portal-fe/       # A 고객조회 → B 고객상세
  customer-service-be/      # Spring Boot API

infra/
  docker-compose.yml
  postgres/
  redis/

docs/20260804/
  architecture/
  decisions/
  phase-reports/

artifacts/
  analysis/
  scenarios/
  test-runs/
  evidence/
```

기존 프로젝트 구조가 있다면 강제로 재배치하지 말고, 같은 책임 경계를 유지하도록 매핑한다.

## 5. 언어 중립 공통 모델

### Interaction Graph Node 예시

- `screen`
- `component`
- `input`
- `event`
- `validation`
- `frontend_api_call`
- `backend_endpoint`
- `request_dto`
- `service`
- `response_dto`
- `route_transition`
- `binding`
- `assertion`

### Edge 예시

- `contains`
- `triggers`
- `validates`
- `calls`
- `receives`
- `returns`
- `navigates_to`
- `binds_to`
- `asserts`
- `branches_to`

모든 Node와 Edge는 가능한 경우 아래 메타데이터를 가진다.

```json
{
  "evidence": [
    {
      "repositoryId": "customer-portal-fe",
      "commitSha": "abc123",
      "file": "src/app/customers/search/page.tsx",
      "startLine": 32,
      "endLine": 51,
      "extractor": "nextjs-router-adapter"
    }
  ],
  "confidence": 0.95,
  "verificationStatus": "static-confirmed"
}
```

## 6. 신뢰도 원칙

| 근거 | 기본 신뢰도 |
|---|---:|
| 명시적 코드 + 기존 테스트 Assertion 일치 | 0.95~1.00 |
| 정적 코드에서 직접 Route/API 확인 | 0.85~0.95 |
| Symbol을 일부 해결하지 못한 정적 추론 | 0.60~0.84 |
| Runtime 검증으로 보강 | 최대 1.00 |
| DOM/문구 기반 추론만 존재 | 최대 0.49 |
| LLM 의미 추론만 존재 | 자동 확정 금지 |

신뢰도 0.70 미만의 Edge는 `unresolved`로 저장하고 건별 실행에서 확인하거나 Runtime 검증 대상으로 표시한다.

## 7. LLM 역할과 금지사항

### LLM이 수행
- Graph의 업무 의미 요약
- 시나리오 제목과 설명
- 기존 테스트 통합
- 누락된 Assertion 후보 추천
- 입력 Semantic Type 후보 추천
- 실패 로그 요약
- 고객 검증 질문 생성

### LLM이 수행하지 않음
- Commit/파일/라인 등 사실 조작
- 존재하지 않는 Endpoint 확정
- 근거 없는 기대값 확정
- 테스트 성공 여부 판정
- HITL 승인 대행
- 원본 전체 저장소를 매 요청마다 Context에 주입

LLM 출력은 반드시 JSON Schema 검증을 통과하고, 원본 Evidence ID를 참조해야 저장한다.

## 8. 실행 추적 헤더

모든 관통 테스트 요청에는 다음 헤더를 사용한다.

```http
X-Test-Run-ID: RUN-...
X-Scenario-ID: customer-search-detail-001
X-Scenario-Version: 1.0.0
X-Test-Case-ID: TC-...
X-Input-Profile-ID: PROFILE-...
```

Spring Filter/Interceptor는 이 값을 MDC와 Structured Log에 전달한다.

## 9. 보안·개인정보

- Secret, Password, Token, Cookie, Authorization Header는 저장하지 않는다.
- Request/Response 필드별 마스킹 정책을 제공한다.
- 실제 고객 개인정보 대신 합성·마스킹 테스트 데이터를 사용한다.
- Evidence 다운로드는 권한 검사를 거친다.
- 저장소 Token은 암호화하거나 Secret Store adapter로 관리한다.
- 외부 LLM API 호출을 기본 금지하고 로컬 endpoint만 허용한다.
- 테스트 대상은 Pilot/Sandbox 환경으로 제한한다.
- destructive action은 기본 차단한다.

## 10. 테스트와 품질 규칙

- 정적 분석기에는 Fixture Repository 기반 Golden Test를 작성한다.
- API와 Schema에는 Contract Test를 작성한다.
- agent-browser 실행에는 실패 시 Screenshot과 DOM snapshot을 자동 보존한다. (입력 직후·결과 화면 최소 2장)
- agent-browser / Playwright MCP 사용 전 사용자에게 문의한다. 무단 파괴적 크롤 금지.
- AI는 관측 요약만 제공하고 Pass/Fail·배포는 HITL이 한다. DOM에 없으면 `missing_data`.
- Python, Node, Java 모듈 모두 lint/test 명령을 제공한다.
- 외부 네트워크 없이 재현 가능한 로컬 테스트 경로를 제공한다.
- 테스트에서 임의 `sleep`을 사용하지 말고 snapshot/selector/network 조건 기반 대기를 사용한다.
- DOM에 직접 값을 주입하지 말고 agent-browser의 fill/click 등 실제 사용자 이벤트를 사용한다.
- Mock은 단위 테스트에는 허용되지만 통합 인수 Gate에서는 실제 Sample FE/BE를 사용한다.

## 11. UI 최소 화면

1. 프로젝트/저장소 등록
2. 분석 실행 및 결과
3. 시나리오 목록
4. 시나리오 상세 A→B Flow
5. 입력 추천값 검토
6. 건별 테스트 실행
7. 배치 테스트 실행
8. Evidence Viewer
9. HITL 검증함
10. 감사 로그

## 12. 공통 구현 명령

각 Phase는 아래를 준수한다.

- 계획만 작성하지 말고 구현한다.
- 기존 코드를 우선 읽고 중복 구현하지 않는다.
- 변경 전후 테스트를 실행한다.
- 실패를 숨기지 않는다.
- 기능 플래그 또는 설정으로 단계적 활성화한다.
- 공개 API 변경 시 OpenAPI와 계약 Schema를 함께 갱신한다.
- 아키텍처 또는 규칙 변경 시 `AGENTS.md`를 갱신한다.
- 모든 Phase 결과를 `docs/20260804/phase-reports/PHASE-XX.md`에 남긴다.
