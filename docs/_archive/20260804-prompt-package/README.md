# AI Code-to-E2E 관통 테스트 플랫폼 파일럿 구현 프롬프트 패키지

이 패키지는 다음 1차 목표를 실제 파일럿으로 구현하기 위한 **Phase별 코딩 프롬프트**입니다.

> 개발 저장소의 Frontend·Backend 소스를 정적 분석해 A 화면의 컴포넌트 이벤트부터 Backend 요청·응답, B 화면 이동과 데이터 바인딩까지 하나의 시나리오로 생성하고, **agent-browser MCP**로 실제 관통 테스트를 수행해 DOM snapshot·스크린샷·Network·로그를 증적화한 뒤 고객 HITL 승인을 받는다.

## 지원 대상

### Frontend
- TypeScript / JavaScript
- React
- Next.js
- (분석 보조) 기존 Playwright Test — Evidence 추출용, 실행 엔진 아님

### Backend
- Java
- Spring Boot
- JUnit
- MockMvc
- REST Assured

### 플랫폼 구현 기술
- Python / FastAPI / Pydantic
- Node.js / TypeScript Compiler API / ts-morph
- Java / JavaParser + Symbol Solver
- **Browser Runner: agent-browser MCP** (DOM snapshot + screenshot; Playwright MCP는 보완 경로)
- PostgreSQL / Redis
- 로컬 파일 또는 S3 호환 Object Storage
- OpenAI-compatible 로컬 LLM endpoint: GPT-OSS 또는 Gemma 계열

## 사용 방법

1. `index.md`에서 실행 순서와 선행조건을 확인합니다.
2. 코딩 Agent는 프로젝트 루트에서 `00_common_context.md`와 `00_pilot_definition_of_done.md`를 먼저 읽습니다.
3. 한 번의 Agent 세션에는 한 개 Phase 프롬프트만 투입하는 것을 권장합니다.
4. 각 Phase는 계획만 작성하지 말고 **코드 구현, 테스트 실행, 문서화, 완료 보고**까지 수행해야 합니다.
5. Phase 종료 시 `templates/phase_completion_report.md` 형식으로 결과를 남깁니다.
6. 이전 Phase의 Gate가 실패했다면 다음 Phase로 넘어가지 않고 원인을 수정합니다.
7. 모든 설계 변경은 `AGENTS.md`와 `docs/20260804/` 아래 결정 기록에 반영합니다.

## 핵심 원칙

- DOM/스크린샷 기반 추측은 보조 수단입니다.
- 사실 추출은 AST, Symbol, Route, API, DTO, 기존 테스트에서 결정론적으로 수행합니다.
- LLM은 추출된 구조를 해석해 시나리오 의미, 누락 검증, 설명을 생성합니다.
- LLM 출력은 JSON Schema 검증을 통과해야 저장됩니다.
- 자동 테스트 PASS는 고객 승인과 동일하지 않습니다.
- 모든 실행은 Commit SHA, Scenario Version, Input Profile, Test Run ID로 재현 가능해야 합니다.
- 테스트 진척률·개발자 평가·팀별 점수는 1차 범위에서 제외합니다.
