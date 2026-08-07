# 파일럿 전체 Definition of Done

## 1. 대표 인수 시나리오

샘플 대상 시스템은 다음 업무를 제공한다.

### A 화면: 고객조회

- Route: `/customers/search`
- 필수 입력: `customerId`
- 형식: `C` + 숫자 5자리
- 조회 버튼 클릭 시 실제 브라우저 이벤트 발생
- Frontend가 `POST /api/customers/search` 호출

### Backend

- `CustomerSearchRequest` 수신
- Bean Validation 수행
- 정상 고객, 제한 고객, 미존재 고객 분기
- `CustomerResponse` 반환
- Test Run ID를 포함한 Structured Log 생성

### B 화면: 고객상세

- Route: `/customers/{customerId}`
- 응답값 `customerId`, `customerName`, `riskLevel`, `status` 바인딩
- 화면과 API 값 비교 가능
- 제한 고객은 별도 Route 또는 상태 표시

## 2. 파일럿 성공 조건

다음 조건을 모두 만족해야 한다.

### 저장소 및 분석
- Frontend와 Backend Repository를 URL 또는 Local Path로 등록할 수 있다.
- 분석은 특정 Commit SHA로 고정된다.
- Frontend Analyzer가 A 화면, 입력, 이벤트, API 호출, Route 전환, B 화면 바인딩을 추출한다.
- Backend Analyzer가 Endpoint, DTO, Validation, Response, 테스트를 추출한다.
- Frontend API와 Backend Endpoint가 자동 매핑된다.

### 시나리오
- Interaction Graph에서 `A → Event → API → Controller → Response → B → Binding` 경로가 보인다.
- 각 Node/Edge는 Evidence와 Confidence를 가진다.
- 실행 가능한 Scenario DSL이 생성되고 Schema 검증을 통과한다.
- 필수 입력, 추천값, 기대 출력, Assertion이 표시된다.

### 실행
- **agent-browser MCP**가 A 화면에서 실제 `fill`, `press`, `click` 등 사용자 이벤트를 수행한다.
- Backend가 동일한 `X-Test-Run-ID`로 Request와 Response를 로그에 남긴다.
- B 화면 이동과 데이터 바인딩을 snapshot/UI 관측으로 검증한다. (없으면 `missing_data`)
- 정상, 경계, 오류, 업무상태 데이터를 실행할 수 있다.
- AI는 Pass/Fail을 최종 확정하지 않고 HITL로 넘긴다.

### 증적
- 각 Run은 Scenario Version, Commit SHA, Input Profile을 기록한다.
- 최소 3장의 Screenshot을 제공한다. (입력 직후·결과 화면 포함)
- Step별 DOM snapshot evidence를 제공한다.
- Frontend Network Request/Response를 제공한다.
- Backend Structured Log를 제공한다.
- Assertion 결과를 제공한다.
- Evidence Manifest의 파일 Hash를 제공한다.

### 실행 모드
- 건별 모드에서 추천값을 검토·수정할 수 있다.
- 배치 모드에서 승인된 Input Profile로 자동 실행할 수 있다.
- 배치의 불확실 데이터와 destructive scenario 정책을 설정할 수 있다.

### HITL
- 자동 PASS 후 상태는 `WAITING_FOR_REVIEW`가 된다.
- 고객은 필드별 결과와 Screenshot을 확인한다.
- 승인, 반려, 데이터 수정 후 재실행을 선택할 수 있다.
- 승인자, 시각, 의견, 이전 결과가 Audit Trail에 저장된다.
- 기술 PASS와 고객 승인 상태가 분리된다.

## 3. 비기능 인수 조건

- 외부 인터넷 연결 없이 Sample Target과 플랫폼을 실행할 수 있다.
- 모든 Secret과 개인정보 필드는 마스킹된다.
- 동일 Commit/Scenario/Input으로 재실행할 수 있다.
- 핵심 API에 OpenAPI 문서가 있다.
- 분석 결과와 시나리오는 JSON Schema로 검증된다.
- Python, Node, Java 테스트가 CI 또는 단일 로컬 명령으로 실행된다.
- 실패 시 사용자가 원인을 확인할 수 있고 무음 실패가 없다.

## 4. 최종 데모 순서

1. Frontend와 Backend 저장소 등록
2. Commit 선택
3. 분석 실행
4. 생성된 A→B Flow 확인
5. 시나리오 상세에서 필수 입력과 추천값 확인
6. 건별 테스트 실행
7. A 입력, API Request, Backend Response, B 화면을 순서대로 확인
8. Evidence Package 열람
9. 배치 테스트 실행
10. HITL 검증함에서 승인 또는 반려
11. Audit Trail 확인
