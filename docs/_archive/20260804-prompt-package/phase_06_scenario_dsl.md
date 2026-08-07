# Phase 06 — Interaction Graph 기반 실행 가능한 Scenario DSL 생성

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


Interaction Graph에서 실제 **agent-browser MCP** 실행과 Backend/UI 검증에 사용할 Scenario DSL을 생성하고 버전·근거·미해결 항목을 관리한다.


## 선행조건


- Phase 05 완료
- Scenario DSL JSON Schema 사용 가능
- 로컬 LLM Adapter 설정 또는 deterministic fake adapter


## 구현 범위


- Graph→DSL 결정론적 변환
- LLM 보조 설명/Assertion 추천
- Schema validation
- Scenario versioning
- 초안/확정 상태
- YAML/JSON export


## 상세 구현 요구사항


1. 결정론적으로 생성 가능한 다음 항목은 LLM에 맡기지 않는다.
   - Route
   - Locator 후보
   - Event type
   - HTTP method/path
   - Request/Response field mapping
   - Evidence
2. LLM은 시나리오 제목, 업무 설명, 의미 기반 assertion 후보, 고객 검증 질문을 생성한다.
3. LLM 입력은 Graph subset과 Evidence reference만 사용한다.
4. LLM 출력은 Schema 검증과 Evidence reference 검증을 거친다.
5. 불확실한 expected value는 `unresolved` 또는 `reviewRequired`로 남긴다.
6. Scenario는 source commit 조합, graph version, 생성기 version을 기록한다.
7. 변경된 Graph에서 Scenario diff를 생성한다.
8. 시나리오 상태:
   - `DRAFT`
   - `READY_FOR_INPUT`
   - `EXECUTABLE`
   - `DEPRECATED`
9. Step은 안정적 ID와 timeout/retry policy를 가진다.
10. Assertion은 hard/soft/business-review로 분리한다.
11. 생성된 DSL을 사람이 읽을 수 있는 Flow 요약과 함께 제공한다.


## API·계약·데이터


- `schemas/scenario_dsl.schema.json` 준수
- 필수 API:
  - `POST /api/interaction-graphs/{id}/scenarios`
  - `GET /api/scenarios`
  - `GET /api/scenarios/{id}`
  - `POST /api/scenarios/{id}/validate`
  - `POST /api/scenarios/{id}/versions`
  - `GET /api/scenarios/{id}/diff?from=&to=`


## UI 요구사항


- 시나리오 목록
- 생성 근거 Graph
- A→B Flow
- Step 상세
- Input/Expected Output
- Assertion
- unresolved/reviewRequired
- Version diff
- YAML/JSON 다운로드


## 필수 테스트


- 동일 Graph에서 deterministic 결과
- Graph branch별 Scenario 생성
- LLM invalid JSON
- Evidence 없는 LLM assertion 거부
- Schema violation
- Scenario version diff
- unresolved expected value


## 완료 기준


- [ ] 고객조회 A→B Scenario DSL이 생성된다.
- [ ] 각 Step이 Graph Evidence를 참조한다.
- [ ] 실제 실행에 필요한 Route, Locator, API, Binding이 포함된다.
- [ ] 근거 없는 기대값은 확정되지 않는다.
- [ ] DSL이 JSON Schema 검증을 통과한다.
- [ ] 버전과 변경점을 확인할 수 있다.


## 제외 범위


- 실제 테스트 데이터 확정
- Browser 실행
- 고객 승인


## 산출물


- Scenario Generator
- LLM Adapter와 검증기
- Scenario API/UI
- 버전 관리
- DSL 예제와 테스트


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-06.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
