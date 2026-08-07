# Repository-Based AI Test Automation Platform 구현 프롬프트

## 0. 역할

당신은 **Senior Software Architect, Static Code Analysis Engineer, QA Automation Architect,agent-broswer Expert**입니다.

현재 프로젝트에 다음 기능을 구현하십시오.

> GitHub, GitLab, SVN 또는 로컬 저장소를 연결하고, 저장소 및 실행 중인 개발 서버의 코드를 분석하여 테스트 시나리오를 생성한 뒤, 실제 테스트를 실행하고 스크린샷·요청값·응답값·코드 근거를 증적으로 연결하는 AI 기반 테스트 자동화 플랫폼

단순 데모 수준이 아니라, 이후 여러 언어와 프레임워크를 확장할 수 있는 구조로 구현해야 합니다.

---

# 1. 최종 목표

사용자는 다음 순서로 테스트 자동화를 수행할 수 있어야 합니다.

1. 프로젝트를 등록한다.
2. GitHub, GitLab, SVN 또는 로컬 경로로 저장소를 연결한다.
3. 실행 중인 개발 서버의 IP, Port, URL을 입력한다. 
  -> 여기서는 예시로 https://cymbal-bank.fsi.cymbal.dev/ 를 타겟서버로 해주세요
4. 저장소의 전체 코드 구조를 분석한다.
5. 분석 대상 파일과 제외할 파일을 트리 화면에서 선택한다.
6. 화면, 컴포넌트, 입력 필드, 버튼, 이벤트, API, 백엔드 로직을 연결한다.
7. 분석 결과를 근거로 테스트 시나리오를 생성한다.
8. 사용자가 생성된 시나리오를 검토하고 승인한다.
9.  승인된 시나리오를agent-broswer 기반으로 실제 실행한다.
10. 각 테스트 단계별 스크린샷, 네트워크 요청·응답, 실행 로그, 코드 근거를 수집한다.
11. 실행 결과와 증적을 하나의 테스트 결과 화면에서 확인한다.
12. 실패한 테스트는 원인, 실패 위치, 관련 코드, 요청·응답, 스크린샷을 함께 제공한다.

---

# 2. 핵심 원칙

## 2.1 사실 기반 시나리오 생성

LLM이 저장소 내용을 추측하여 시나리오를 생성하면 안 됩니다.

다음 순서를 반드시 준수하십시오.

```text
Repository 연결
→ 파일 및 프레임워크 탐지
→ AST 및 정적 코드 분석
→ 화면·이벤트·API·백엔드 관계 구조화
→ 분석 근거 저장
→ 구조화된 분석 결과를 LLM에 전달
→ 테스트 시나리오 생성
→ 사용자 검토 및 승인
→agent-broswer 실행
→ 증적 수집
```

LLM은 다음 역할에 집중해야 합니다.

- 구조화된 분석 결과를 테스트 시나리오로 변환
- 정상, 오류, 경계값, 권한, 보안, 회귀 시나리오 확장
- 사람이 이해할 수 있는 테스트 목적과 기대 결과 작성
- 테스트 실패 원인 요약
- 코드 근거와 실행 증적 연결 설명

다음 작업은 일반 코드, Parser 또는 Rule Engine이 담당해야 합니다.

- 파일 탐색
- 프로젝트 유형 탐지
- AST 분석
- Route 추출
- API 호출 추출
- 입력 필드 및 Validation 추출
- 화면과 API 연결
- 요청·응답 스키마 추출
- 테스트 실행
- Assertion 판정
- 스크린샷 및 Trace 저장

---

# 3. 고품질 테스트 수행 및 증적 기준

고품질 테스트를 위해 반드시 아래 순서로 테스트를 진행하고 증적을 남겨야 합니다.

## 3.1 코드 분석

- 연결된 저장소 또는 서버 코드를 분석한다.
- 저장소의 루트부터 하위 프로젝트를 탐색한다.
- 언어, 프레임워크, 빌드 도구, 실행 구조를 감지한다.
- 프런트엔드 화면, 컴포넌트, 라우트, 입력 필드, 버튼, 이벤트를 추출한다.
- API 호출부와 백엔드 Endpoint를 연결한다.
- 요청 DTO, 응답 DTO, Validation, 상태코드, 예외처리를 분석한다.
- 분석한 모든 항목에 원본 파일 경로와 코드 위치를 연결한다.
- 분석할 수 없는 항목은 추측하지 말고 `UNRESOLVED` 상태로 표시한다.

## 3.2 테스트 시나리오 생성

- 분석된 코드만을 근거로 테스트 시나리오를 생성한다.
- 화면 테스트, Validation 테스트, API 테스트, E2E 테스트를 구분한다.
- 정상, 오류, 경계값, 권한, 인증, 보안, 네트워크 실패 시나리오를 포함한다.
- 각 시나리오에 근거가 된 파일, 함수, Route, Selector, API를 연결한다.
- 동일 목적의 중복 시나리오는 제거한다.
- 테스트 데이터가 필요한 경우 변수로 정의한다.
- 실제 코드에서 확인되지 않은 기대 결과는 `ASSUMPTION`으로 표시한다.

## 3.3 실제 테스트 실행

- 승인된 테스트 시나리오를 실제 실행 중인 개발 서버에 수행한다.
-agent-broswer를 기본 E2E 실행 엔진으로 사용한다.
- UI 동작과 API 통신을 함께 검증한다.
- 각 주요 테스트 단계의 실행 전·후 스크린샷을 저장한다.
- 브라우저 Console Error를 수집한다.
- Network Request와 Response를 수집한다.
- 실패 시agent-broswer Trace, Screenshot, DOM Snapshot, 실행 로그를 저장한다.
- 민감정보는 마스킹하여 증적에 저장한다.
- 실행 서버와 코드 버전이 일치하는지 확인할 수 있도록 Commit Hash를 기록한다.

## 3.4 결과 및 증적 연결

각 테스트 결과에는 반드시 다음 정보가 연결되어야 합니다.

- 테스트 시나리오 ID
- 테스트 제목
- 테스트 목적
- 대상 화면
- 실행 URL
- 실행 환경
- 저장소 URL
- Branch
- Commit Hash
- 대상 코드 파일
- 코드 라인 또는 Symbol
- UI Selector
- 연결 API
- 요청값
- 응답값
- 기대 결과
- 실제 결과
- 단계별 실행 로그
- 단계별 스크린샷
-agent-broswer Trace
- Browser Console Log
- Network Log
- 시작 시간
- 종료 시간
- 소요 시간
- 성공, 실패, 중단 상태
- 실패 원인
- 재현 절차
- LLM 분석 설명
- 사용자 검토 상태

---

# 4. 프로젝트 등록 기능

프로젝트 등록 단계에서 다음 정보를 입력받아야 합니다.

## 4.1 기본 프로젝트 정보

| 필드 | 필수 | 설명 |
|---|---:|---|
| 프로젝트명 | Y | 테스트 대상 프로젝트 이름 |
| 프로젝트 설명 | N | 업무 및 시스템 설명 |
| 프로젝트 유형 | Y | Web, API, Full Stack, Microservice |
| 담당자 | N | 프로젝트 담당자 |
| 태그 | N | 검색 및 분류용 태그 |

## 4.2 저장소 연결 정보

| 필드 | 필수 | 설명 |
|---|---:|---|
| 저장소 유형 | Y | GitHub, GitLab, SVN, Local Path |
| 저장소 URL 또는 로컬 절대경로 | Y | 코드 저장 위치 |
| 인증 방식 | 조건부 | Public, PAT, SSH Key, ID/PASSWORD |
| Branch | Y | 분석할 Branch |
| Commit Hash | N | 미입력 시 Branch 최신 Commit |
| Root Path | N | Monorepo 내 분석 시작 경로 |
| Include Pattern | N | 분석 포함 경로 |
| Exclude Pattern | N | 제외 경로 |
| Submodule 포함 여부 | N | Git Submodule 분석 여부 |

인증정보는 암호화하여 저장하고 로그나 화면에 원문을 출력하지 마십시오.

## 4.3 실행 중인 개발 서버 정보

**실제 테스트 실행을 위해 프로젝트 등록 단계에서 반드시 개발 서버 정보를 추가 입력받아야 합니다.**

사용자 안내 문구:

> 실제 테스트 실행을 위해 현재 기동되어 있는 개발 서버의 IP, Port 또는 접속 가능한 URL 정보를 입력해 주세요.

필수 입력 필드:

| 필드 | 필수 | 예시 | 설명 |
|---|---:|---|---|
| 환경 이름 | Y | Local, DEV, QA, STG | 테스트 대상 환경 |
| Frontend Base URL | 조건부 | `http://127.0.0.1:3000` | 브라우저 테스트 시작 URL |
| Frontend IP | N | `127.0.0.1` | URL 분리 입력 시 사용 |
| Frontend Port | N | `3000` | URL 분리 입력 시 사용 |
| Backend Base URL | 조건부 | `http://127.0.0.1:8000` | API 검증 대상 URL |
| Backend IP | N | `127.0.0.1` | URL 분리 입력 시 사용 |
| Backend Port | N | `8000` | URL 분리 입력 시 사용 |
| Health Check URL | N | `/health` | 서버 기동 확인 경로 |
| API Base Path | N | `/api` | 공통 API Prefix |
| HTTPS 여부 | N | true/false | 인증서 처리 판단 |
| 인증서 검증 여부 | N | true/false | 사설 인증서 환경 지원 |
| Proxy 정보 | N | 사내 Proxy | 폐쇄망 환경 지원 |
| 접속 제한 설명 | N | VPN 필요 | 테스트 실행 제약사항 |
| 테스트 계정 사용 여부 | N | true/false | 인증 테스트 수행 여부 |
| 테스트 계정 참조 키 | 조건부 | `DEV_ADMIN` | Secret 원문 저장 금지 |

다음 검증을 수행하십시오.

1. URL 형식 검증
2. IP와 Port 범위 검증
3. 서버 연결 가능 여부 확인
4. Health Check 수행
5. Frontend 초기 화면 응답 확인
6. Backend API 응답 확인
7. 저장소 분석 결과의 Route와 실행 서버 URL 매핑
8. 서버 미기동 시 테스트 실행 차단
9. 코드 분석만 수행할 수 있는 옵션 제공
10. 사설 인증서와 폐쇄망 환경을 고려한 설정 제공

프로젝트는 여러 실행 환경을 등록할 수 있어야 합니다.

```text
Local
DEV
QA
STG
```

각 테스트 실행 시 어떤 환경을 사용했는지 반드시 기록하십시오.

---

# 5. 저장소 연결 및 분석 기능

## 5.1 지원 저장소

- GitHub Public Repository
- GitHub Private Repository
- GitLab Public Repository
- GitLab Private Repository
- SVN Repository
- 로컬 절대경로
- ZIP 업로드
- 향후 사내 형상관리 시스템 확장이 가능한 Adapter 구조

## 5.2 저장소 연결 처리

저장소 연결 시 다음 정보를 저장하십시오.

```json
{
  "repository_id": "repo_xxx",
  "repository_type": "github",
  "repository_url": "https://github.com/GoogleCloudPlatform/bank-of-anthos.git",
  "branch": "main",
  "commit_hash": "resolved_commit_hash",
  "checkout_path": "./workspace/repositories/repo_xxx",
  "root_path": ".",
  "include_patterns": [],
  "exclude_patterns": [
    ".git/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    "coverage/**",
    "__pycache__/**"
  ],
  "last_analyzed_at": null
}
```

## 5.3 코드 트리 화면

저장소 분석 후 파일을 트리 형태로 출력하십시오.

예시:

```text
☑ src
  ☑ frontend
    ☑ templates
      ☑ login.html
      ☑ signup.html
    ☑ static
      ☑ scripts
        ☑ login.js
    ☑ frontend.py
  ☑ accounts
    ☑ userservice
      ☑ userservice.py
☐ tests
☐ docs
☐ vendor
```

요구사항:

- 폴더와 파일별 체크박스
- 전체 선택과 전체 해제
- 분석 제외
- 테스트 생성 제외
- 기존 테스트 코드 별도 표시
- 자동 제외 권장 항목 표시
- 파일별 분석 상태 표시
- 파일별 추출된 화면, API, 함수, 모델 개수 표시
- 변경 파일만 재분석
- 사용자가 확정한 분석 범위를 저장

---

# 6. 코드 분석 엔진

## 6.1 권장 기술

| 대상 | 권장 분석기 |
|---|---|
| 공통 다중 언어 | Tree-sitter |
| Python | Python AST |
| Java | JavaParser 또는 Spoon |
| JavaScript/TypeScript | TypeScript Compiler API 또는 ts-morph |
| React JSX/TSX | Babel Parser 또는 ts-morph |
| HTML | HTML Parser |
| Jinja | Jinja Parser |
| Spring Boot | Annotation 및 Symbol 분석 |
| Flask/FastAPI | Decorator 및 Route 분석 |
| API 호출 | fetch, axios, requests, RestTemplate, WebClient 분석 |
| GraphQL | Query, Mutation, Schema, Resolver 분석 |

Parser는 인터페이스 기반으로 구현하십시오.

```typescript
interface LanguageAnalyzer {
  supports(filePath: string, content: string): boolean;
  analyze(context: AnalysisContext): Promise<FileAnalysisResult>;
}
```

## 6.2 추출 대상

### Frontend

- Page Route
- Component
- Form
- Input
- Button
- Link
- Modal
- Table
- Tab
- Selector 후보
- Event Handler
- Validation Rule
- Error Message
- API 호출
- 화면 이동
- 인증 필요 여부
- 권한 조건
- 로딩 상태
- 빈 데이터 상태
- 오류 상태

### Backend

- Controller 또는 Route
- HTTP Method
- Path
- Request Parameter
- Path Variable
- Header
- Request Body
- DTO
- Response DTO
- Status Code
- Validation
- Exception Handler
- 인증 및 권한
- Service 호출
- Repository 호출
- DB Model
- 외부 API 호출

## 6.3 분석 관계 그래프

다음 관계를 표현할 수 있어야 합니다.

```text
Repository
└─ Project
   ├─ Screen
   │  └─ UIElement
   │     └─ Event
   ├─ Component
   ├─ Route
   ├─ ApiCall
   ├─ ApiEndpoint
   ├─ Function
   ├─ DataModel
   ├─ ValidationRule
   └─ TestScenario
```

대표 관계:

```text
SCREEN_CONTAINS_ELEMENT
COMPONENT_RENDERS_COMPONENT
ELEMENT_TRIGGERS_EVENT
EVENT_CALLS_API
EVENT_NAVIGATES_ROUTE
API_CALL_MATCHES_ENDPOINT
ENDPOINT_HANDLED_BY_FUNCTION
FUNCTION_CALLS_SERVICE
SERVICE_READS_MODEL
VALIDATION_APPLIES_TO_INPUT
SCENARIO_COVERS_SCREEN
SCENARIO_COVERS_API
SCENARIO_DERIVED_FROM_CODE
```

파일럿에서는 SQLite를 사용하되, Repository Interface를 통해 향후 PostgreSQL 또는 Graph DB로 교체할 수 있게 구현하십시오.

---

# 7. 테스트 시나리오 생성

## 7.1 시나리오 유형

최소 다음 유형을 생성하십시오.

- UI 렌더링 테스트
- 필수 입력 Validation
- 입력 형식 Validation
- 최소값 및 최대값
- 경계값
- 정상 처리
- 잘못된 값
- 존재하지 않는 데이터
- 인증 실패
- 권한 부족
- Session 만료
- API 오류
- Network 오류
- 서버 오류
- 중복 요청
- 빈 데이터
- 대용량 데이터
- 화면 이동
- 새로고침
- 뒤로가기
- 중복 클릭
- XSS 등 기본 입력 보안
- E2E 업무 흐름
- 회귀 테스트

## 7.2 테스트 시나리오 표시 형식

사용자가 요청한 다음 형태를 기본 UI로 제공하십시오.

```text
1. 로그인 페이지 화면 입력

- 페이지 첫 화면에서 로그인을 진행할 수 있는 ID와 Password 입력란이 표시되는지 확인한다.
- 적합한 값이 입력되었을 때 Validation을 통과하는지 확인한다.
- 부적합한 값이 입력되었을 때 Validation 메시지가 발생하는지 확인한다.

대상 화면: /login
대상 컴포넌트: LoginPage
대상 요소:
- Username: #login-username
- Password: #login-password
- Sign in: button[type="submit"]

연결 API:
- Frontend: POST /login
- Backend: GET /login

요청값:
- username: ${VALID_USERNAME}
- password: ${VALID_PASSWORD}

기대 응답:
- HTTP 200
- token 필드 반환

기대 화면 결과:
- token 쿠키 생성
- /home 이동

코드 근거:
- src/frontend/templates/login.html
- src/frontend/static/scripts/login.js
- src/frontend/frontend.py
- src/accounts/userservice/userservice.py
```

## 7.3 시나리오 데이터 모델

```typescript
type TestScenarioStatus =
  | "DRAFT"
  | "REVIEWED"
  | "APPROVED"
  | "REJECTED"
  | "GENERATED"
  | "RUNNING"
  | "PASSED"
  | "FAILED"
  | "BLOCKED";

interface TestScenario {
  id: string;
  projectId: string;
  title: string;
  description: string;
  category: "UI" | "VALIDATION" | "API" | "E2E" | "SECURITY" | "REGRESSION";
  priority: "P0" | "P1" | "P2" | "P3";
  status: TestScenarioStatus;
  preconditions: string[];
  testData: Record<string, unknown>;
  steps: TestStep[];
  expectedResults: string[];
  targetScreens: ScreenReference[];
  targetApis: ApiReference[];
  codeEvidence: CodeEvidence[];
  assumptions: string[];
  confidence: number;
  generatedBy: string;
  analysisVersion: string;
  createdAt: string;
  updatedAt: string;
}
```

## 7.4 생성 품질 규칙

- 모든 시나리오는 최소 하나 이상의 코드 근거를 가져야 한다.
- 코드 근거가 없으면 생성하지 않거나 `ASSUMPTION`으로 표시한다.
- 요청값과 기대 응답은 가능한 경우 코드에서 자동 추출한다.
- 값이 확인되지 않으면 임의의 운영 데이터를 생성하지 않는다.
- Password, Token, 주민번호, 계좌번호 등은 마스킹한다.
- Selector는 `data-testid`를 우선 사용한다.
- `data-testid`가 없으면 role, label, id, name, text 순으로 안정적인 Selector를 선택한다.
- 불안정한 CSS 경로는 낮은 신뢰도로 표시한다.
- 시나리오 중복도를 계산한다.
- 시나리오별 코드 커버리지 범위를 표시한다.
- 시나리오별 생성 신뢰도를 표시한다.

---

# 8. 시나리오 검토 및 승인

실제 테스트 코드는 자동 생성하되, 실행 전 사용자 검토 단계를 제공하십시오.

기능:

- 시나리오 조회
- 코드 근거 조회
- UI와 API 연결 확인
- 테스트 단계 수정
- 입력값 수정
- 기대 결과 수정
- 시나리오 삭제
- 시나리오 승인
- 다중 승인
- 재생성
- 변경 이력
- 댓글 또는 검토 메모
- 승인자와 승인 시간 기록

승인되지 않은 시나리오는 기본적으로 실제 서버에 실행하지 마십시오.

---

# 9.agent-broswer 테스트 생성 및 실행

## 9.1 기본 원칙

-agent-broswer Test를 기본으로 사용한다.
- 시나리오에서 agent-broswer 코드를 생성한다.
- 생성된 코드는 프로젝트별 디렉터리에 저장한다.
- 공통 Fixture와 Page Object를 분리한다.
- Base URL은 프로젝트 실행 환경 설정에서 가져온다.
- 테스트 데이터와 Secret은 코드에 하드코딩하지 않는다.
- 병렬 실행 가능 여부를 프로젝트별로 설정한다.
- 데이터 충돌 가능성이 있는 테스트는 직렬 실행한다.
- Retry는 환경별로 설정한다.
- 실행 중 Network와 Console 이벤트를 수집한다.

## 9.2 디렉터리 예시

```text
workspace/
└─ projects/
   └─ {project_id}/
      ├─ repository/
      ├─ analysis/
      ├─ scenarios/
      ├─ generated-tests/
      │  ├─ fixtures/
      │  ├─ pages/
      │  └─ specs/
      └─ artifacts/
         └─ {test_run_id}/
            ├─ screenshots/
            ├─ traces/
            ├─ videos/
            ├─ network/
            ├─ console/
            └─ result.json
```

## 9.3 단계별 스크린샷

다음 시점에 스크린샷을 남긴다.

- 테스트 시작 직후
- 주요 화면 진입 후
- 입력값 입력 후
- 버튼 클릭 전
- 버튼 클릭 후
- Validation 발생 후
- API 응답 처리 후
- 성공 결과 화면
- 실패 발생 시점

스크린샷 파일명 예시:

```text
{scenario_id}_{step_number}_{timestamp}_{status}.png
```

## 9.4 Network 증적

각 테스트별로 다음을 수집한다.

```json
{
  "method": "POST",
  "url": "http://localhost:3000/login",
  "requestHeaders": {},
  "requestBody": {
    "username": "masked-user",
    "password": "***"
  },
  "status": 200,
  "responseHeaders": {},
  "responseBody": {
    "token": "***"
  },
  "startedAt": "2026-08-05T13:00:00+09:00",
  "durationMs": 154
}
```

민감정보 마스킹 규칙을 공통 모듈로 구현하십시오.

## 9.5 테스트 실패 처리

실패 시 다음 정보를 생성한다.

- 실패한 Step
- 실패 Assertion
- 기대값
- 실제값
- 현재 URL
- 대상 Selector
- 마지막 API 요청
- 마지막 API 응답
- Console Error
- Screenshot
- Trace
- 관련 코드 근거
- 가능한 원인
- 재현 방법
- 수정 후보 파일
- 재실행 가능 여부

LLM은 수집된 사실만을 바탕으로 실패 원인을 설명해야 하며, 확정할 수 없는 내용은 가능성으로 구분해야 합니다.

---

# 10. 테스트 결과 화면

## 10.1 테스트 실행 목록

다음 정보를 표시하십시오.

- 실행 ID
- 프로젝트
- 환경
- Branch
- Commit Hash
- 실행자
- 시작 시간
- 종료 시간
- 전체 시나리오 수
- 성공 수
- 실패 수
- 차단 수
- 성공률
- 소요 시간

## 10.2 테스트 상세

왼쪽에는 테스트 Step, 오른쪽에는 증적을 표시하십시오.

```text
[테스트 단계]
1. /login 접속                       PASS
2. Username 입력                     PASS
3. Password 입력                     PASS
4. Sign in 클릭                      PASS
5. POST /login 확인                  PASS
6. User Service 응답 확인            PASS
7. /home 이동 확인                   FAIL

[증적]
- Step Screenshot
- Before/After 비교
- Request
- Response
- Console
- Trace
- 코드 근거
- 실패 원인
```

## 10.3 코드 근거 표시

```text
파일: src/frontend/frontend.py
Symbol: login()
Line: 120-148

근거 설명:
Frontend의 POST /login 처리는 User Service의 /login API를 호출하고,
성공 시 token 쿠키를 저장한 뒤 /home으로 이동한다.
```

가능한 경우 원본 코드 뷰어에서 해당 라인을 하이라이트하십시오.

---

# 11. 사용자 화면

최소 다음 화면을 구현하십시오.

1. 프로젝트 목록
2. 프로젝트 등록
3. 저장소 연결
4. 실행 환경 등록
5. 연결 테스트
6. 저장소 코드 트리
7. 분석 범위 선택
8. 코드 분석 진행 상태
9. 분석 결과
10. 화면과 API 관계 그래프
11. 테스트 시나리오 생성 요청
12. 생성된 시나리오 목록
13. 시나리오 상세 및 코드 근거
14. 시나리오 검토 및 승인
15. 테스트 실행
16. 테스트 실행 현황
17. 테스트 결과
18. 단계별 증적
19. 실패 원인 분석
20. 프로젝트 설정

---

# 12. 권장 기술 스택

특별한 기존 제약이 없다면 다음을 기본으로 사용하십시오.

## Frontend

- TypeScript
- React
- Next.js
- Tailwind CSS
- shadcn/ui
- Zustand 또는 React Query
- Monaco Editor
- React Flow

## Backend

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- Background Task 또는 Worker Queue
- WebSocket 또는 Server-Sent Events

## 분석

- Tree-sitter
- Python AST
- ts-morph
- JavaParser 또는 Spoon
- HTML Parser
- GraphQL Parser

## 테스트

-agent-broswer Test
-agent-broswer Trace Viewer
- APIRequestContext
- Axe-core 선택 적용

## 저장소

파일럿:

- SQLite
- Local File Storage

확장:

- PostgreSQL
- Object Storage
- Redis
- Graph DB 선택 가능

---

# 13. 로컬 파일럿 저장 정책

파일럿 환경은 로컬 실행을 기준으로 합니다.

## localStorage 저장 대상

- 코드 트리 펼침 상태
- 사용자 필터
- 선택한 Tab
- 임시 UI 설정

## SQLite 저장 대상

- 프로젝트
- 저장소 설정
- 실행 환경
- 분석 이력
- 파일 분석 결과
- 관계 그래프
- 테스트 시나리오
- 승인 이력
- 테스트 실행 이력
- 증적 Metadata

## 파일시스템 저장 대상

- Clone Repository
- 생성된 테스트 코드
- Screenshot
- Trace
- Video
- Network Log
- Console Log
- Report

---

# 14. API 설계 예시

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{projectId}
PUT    /api/projects/{projectId}

POST   /api/projects/{projectId}/repositories
POST   /api/projects/{projectId}/repositories/validate
POST   /api/projects/{projectId}/repositories/clone

POST   /api/projects/{projectId}/environments
GET    /api/projects/{projectId}/environments
POST   /api/projects/{projectId}/environments/{environmentId}/health-check

POST   /api/projects/{projectId}/analysis/start
GET    /api/projects/{projectId}/analysis/status
GET    /api/projects/{projectId}/analysis/tree
PUT    /api/projects/{projectId}/analysis/scope
GET    /api/projects/{projectId}/analysis/result
GET    /api/projects/{projectId}/analysis/graph

POST   /api/projects/{projectId}/scenarios/generate
GET    /api/projects/{projectId}/scenarios
GET    /api/scenarios/{scenarioId}
PUT    /api/scenarios/{scenarioId}
POST   /api/scenarios/{scenarioId}/approve
POST   /api/scenarios/{scenarioId}/reject

POST   /api/projects/{projectId}/test-runs
GET    /api/test-runs/{testRunId}
GET    /api/test-runs/{testRunId}/status
GET    /api/test-runs/{testRunId}/results
GET    /api/test-results/{testResultId}
GET    /api/test-results/{testResultId}/artifacts
```

---

# 15. 주요 데이터 모델

최소 다음 Entity를 설계하십시오.

```text
Project
RepositoryConnection
ExecutionEnvironment
AnalysisJob
AnalyzedFile
CodeSymbol
Screen
UIElement
EventHandler
FrontendRoute
ApiCall
ApiEndpoint
ValidationRule
DataModel
CodeRelation
TestScenario
TestScenarioStep
ScenarioApproval
GeneratedTest
TestRun
TestResult
TestStepResult
TestArtifact
NetworkEvidence
ConsoleEvidence
CodeEvidence
```

모든 주요 데이터에는 다음 공통 필드를 적용하십시오.

```text
id
created_at
updated_at
created_by
version
status
```

---

# 16. 보안 및 운영 요구사항

- Repository Token과 Password를 암호화한다.
- Secret을 로그에 출력하지 않는다.
- 테스트 계정 정보는 Secret Reference로 관리한다.
- Request와 Response의 민감정보를 마스킹한다.
- 저장소 경로 조작 공격을 방지한다.
- 허용된 Workspace 밖의 파일을 읽지 않는다.
- 임의 Shell Command 실행을 제한한다.
- 생성된 테스트 코드 실행 전 안전 검사를 수행한다.
- 테스트 대상 Host Allowlist를 제공한다.
- 운영 환경 실행은 기본 차단한다.
- 실행 환경에 `production` 경고 및 추가 승인 절차를 둔다.
- 삭제, 송금, 결제 등 위험 작업은 별도 승인 또는 Mock 모드를 지원한다.
- 테스트 데이터 정리 절차를 제공한다.
- 감사 로그를 남긴다.

---

# 17. 구현 Phase

작업을 다음 Phase로 분리하십시오.

## Phase 1. 프로젝트 기반 구조

- Frontend와 Backend 프로젝트 생성
- SQLite 연결
- 프로젝트 CRUD
- 저장소 연결 모델
- 실행 환경 등록
- 서버 Health Check
- 기본 화면 구성

## Phase 2. 저장소 연결

- GitHub Public Clone
- Local Path 연결
- Branch와 Commit Hash 조회
- 코드 트리 생성
- Include와 Exclude 선택
- 연결 오류 처리

## Phase 3. 코드 분석

- 언어 및 프레임워크 탐지
- Python, JavaScript, TypeScript, HTML 우선 지원
- Frontend Route 추출
- UI Element 추출
- API Call 추출
- Backend Endpoint 추출
- 코드 근거 저장
- 관계 그래프 생성

## Phase 4. 시나리오 생성

- 분석 결과를 LLM 입력용 JSON으로 변환
- 테스트 시나리오 생성
- 정상, 오류, 경계값 시나리오 확장
- 중복 제거
- 코드 근거 연결
- 시나리오 검토 및 승인 UI

## Phase 5.agent-broswer 생성 및 실행

- 시나리오에서agent-broswer 코드 생성
- Base URL 연결
- 테스트 실행
- 실행 상태 실시간 표시
- Screenshot와 Trace 저장
- Network와 Console 수집

## Phase 6. 결과와 증적

- 테스트 실행 결과 목록
- 단계별 결과
- Screenshot Viewer
- Request와 Response Viewer
- Trace 연결
- 코드 근거 Viewer
- 실패 원인 요약

## Phase 7. 품질 고도화

- 변경 파일 증분 분석
- 회귀 테스트 자동 추천
- GraphQL 분석
- Java와 Spring 분석
- GitLab과 SVN 연결
- 테스트 데이터 관리
- 병렬 실행
- 리포트 Export

각 Phase 완료 시 다음을 제공하십시오.

- 구현 파일 목록
- 주요 설계 설명
- 실행 방법
- 테스트 방법
- 완료된 요구사항
- 미완료 요구사항
- 알려진 제약사항

---

# 18. Bank of Anthos 파일럿 기준

초기 파일럿 저장소:

```text
https://github.com/GoogleCloudPlatform/bank-of-anthos.git
```

우선 분석 대상:

```text
src/frontend
src/accounts/userservice
src/accounts/contacts
src/ledger
```

우선 생성할 사용자 흐름:

1. 로그인
2. 회원가입
3. 홈 화면 조회
4. 계좌 잔액 조회
5. 연락처 조회 및 등록
6. 송금
7. 입금
8. 로그아웃

로그인 시나리오 예시:

```yaml
scenario_id: LOGIN-E2E-001
title: 정상 로그인
category: E2E
target_screen: /login
preconditions:
  - 활성 상태의 테스트 사용자가 존재한다
inputs:
  username: ${VALID_USERNAME}
  password: ${VALID_PASSWORD}
ui_elements:
  - name: Username
    selector: "#login-username"
  - name: Password
    selector: "#login-password"
  - name: Sign in
    selector: "button[type='submit']"
api_flow:
  - caller: frontend
    method: POST
    path: /login
  - caller: frontend
    target: userservice
    method: GET
    path: /login
expected_results:
  - User Service가 성공 응답을 반환한다
  - token 쿠키가 생성된다
  - /home으로 이동한다
evidence:
  - 시작 화면 스크린샷
  - 입력 완료 스크린샷
  - 로그인 클릭 후 스크린샷
  - Request와 Response
  - 최종 /home 화면
  - 관련 코드 파일과 Symbol
```

---

# 19. 완료 조건

다음 조건을 모두 충족해야 1차 파일럿이 완료된 것으로 판단합니다.

- 프로젝트를 등록할 수 있다.
- 저장소 URL을 입력하고 Clone할 수 있다.
- Branch와 Commit Hash를 확인할 수 있다.
- 실행 중인 개발 서버의 IP, Port 또는 URL을 등록할 수 있다.
- Frontend와 Backend 서버 Health Check를 수행할 수 있다.
- 저장소 코드 트리를 출력할 수 있다.
- 사용자가 분석 대상 코드를 선택하거나 제외할 수 있다.
- Python, JavaScript, TypeScript, HTML 코드를 분석할 수 있다.
- 로그인 화면의 입력 필드와 Validation을 추출할 수 있다.
- 로그인 화면과 Backend API 관계를 연결할 수 있다.
- 코드 분석 근거가 포함된 테스트 시나리오를 생성할 수 있다.
- 사용자가 시나리오를 검토하고 승인할 수 있다.
- 승인된 시나리오를agent-broswer로 실행할 수 있다.
- 테스트 단계별 스크린샷을 저장할 수 있다.
- Request와 Response를 확인할 수 있다.
- 실패 시 Trace와 Console Log를 확인할 수 있다.
- 테스트 결과와 관련 코드 근거를 같은 화면에서 확인할 수 있다.
- 실행한 환경, Branch, Commit Hash가 결과에 기록된다.
- 민감정보가 증적에서 마스킹된다.
- 전체 기능을 로컬 환경에서 실행할 수 있다.

---

# 20. Cursor 작업 규칙

다음 규칙을 준수하며 구현하십시오.

1. 먼저 현재 프로젝트 구조와 기존 코드를 분석한다.
2. 기존 기능을 삭제하거나 대규모로 변경하기 전에 영향도를 확인한다.
3. 기능을 작고 검증 가능한 단위로 나누어 구현한다.
4. 각 Phase마다 실제 실행 가능한 코드를 제공한다.
5. Mock 화면만 만들지 말고 Backend API와 연결한다.
6. 하드코딩된 데모 데이터보다 실제 저장소 분석 결과를 사용한다.
7. 오류를 숨기지 말고 사용자에게 원인과 해결 방법을 표시한다.
8. 모든 비동기 작업은 상태와 진행률을 표시한다.
9. 모든 주요 함수와 API에 명확한 타입을 적용한다.
10. 분석 결과에는 반드시 파일 경로와 Symbol 근거를 포함한다.
11. 테스트 시나리오에는 반드시 코드 근거를 포함한다.
12. 테스트 결과에는 반드시 실행 증적을 포함한다.
13. 보안상 위험한 기능은 기본 비활성화한다.
14. 구현 후 Lint, Type Check, Unit Test, Integration Test를 실행한다.
15. 문서를 최신 상태로 유지한다.

---

# 21. 첫 번째 작업 지시

이 프롬프트를 받은 후 바로 전체 코드를 한 번에 생성하지 마십시오.

먼저 다음을 수행하십시오.

1. 현재 Workspace 구조를 분석한다.
2. 기존 기술 스택과 재사용 가능한 코드를 정리한다.
3. 요구사항과 현재 구조의 차이를 분석한다.
4. 구현 아키텍처를 제안한다.
5. 디렉터리 구조를 제안한다.
6. 데이터 모델을 제안한다.
7. API 목록을 제안한다.
8. Phase별 구현 계획을 작성한다.
9. 위험 요소와 선행 조건을 작성한다.
10. `docs/implementation-plan.md`에 결과를 저장한다.

그 다음 Phase 1부터 순차적으로 구현하십시오.

각 Phase가 끝날 때마다 다음 형식으로 보고하십시오.

```markdown
## Phase 완료 보고

### 구현 완료
- ...

### 생성 또는 수정 파일
- ...

### 실행 방법
```bash
...
```

### 검증 결과
- Lint:
- Type Check:
- Unit Test:
- Integration Test:

### 미완료 또는 제약사항
- ...

### 다음 Phase
- ...
```

최종적으로 사용자가 프로젝트를 등록하고, 저장소와 개발 서버를 연결하고, 코드 분석을 통해 생성된 시나리오를 실제 실행한 뒤, 스크린샷과 상세 근거를 확인할 수 있는 상태를 완성하십시오.
