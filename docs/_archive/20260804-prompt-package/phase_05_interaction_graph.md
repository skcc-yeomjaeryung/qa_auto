# Phase 05 — A→B Frontend–Backend Interaction Graph 생성과 시각화

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


분석 결과와 API 매핑을 결합해 A 화면에서 B 화면까지의 관통 흐름, 필수 데이터, 분기, Evidence, Confidence를 언어 중립 Interaction Graph로 생성한다.


## 선행조건


- Phase 04 완료
- Interaction Graph JSON Schema 사용 가능


## 구현 범위


- Graph Builder
- Node/Edge 정규화
- 경로 탐색
- 분기와 unresolved edge
- A→B Flow 상세 API
- Web Console Flow 시각화


## 상세 구현 요구사항


1. 최소 경로:
   `screen(A) → input → event → validation → frontend_api_call → backend_endpoint → request_dto → service → response_dto → route_transition → screen(B) → binding`
2. 각 Node/Edge는 Evidence, Confidence, verificationStatus를 가진다.
3. 동일 코드 요소의 중복 Node를 안정적 ID로 병합한다.
4. 정상/제한/오류 경로를 별도 branch로 표시한다.
5. 입력 필드에서 Backend Request, Response, B Binding까지 Data Lineage를 표현한다.
6. Graph는 특정 Frontend/Backend Commit 조합에 종속된다.
7. Graph 생성 시 Schema 검증을 수행한다.
8. Cycle과 동적 dispatch는 시각화하되 무한 경로 탐색을 막는다.
9. Graph 상세에서 파일/라인 Evidence를 열 수 있다.
10. 시각화는 A/B 화면을 강조하고 API/Backend 구간을 구분한다.
11. Graph 생성 결과가 LLM 호출 없이도 설명 가능한 기본 라벨을 제공한다.


## API·계약·데이터


- `schemas/interaction_graph.schema.json` 준수
- 필수 API:
  - `POST /api/analyses/{id}/interaction-graphs`
  - `GET /api/interaction-graphs`
  - `GET /api/interaction-graphs/{graphId}`
  - `GET /api/interaction-graphs/{graphId}/paths?from=&to=`


## UI 요구사항


시나리오 상세의 전 단계로 다음을 제공한다.

- A 화면 카드: Route, Screenshot placeholder, 입력
- 이벤트
- API Request
- Backend Controller/DTO/Service
- API Response
- B 화면 카드: Route, 바인딩 필드
- branch tab
- Evidence panel
- Confidence 및 unresolved badge

큰 Graph에서도 사용자가 핵심 경로를 먼저 보고 세부 Node를 확장하도록 한다.


## 필수 테스트


- 고객조회 정상 경로
- 제한 고객 분기
- Backend 404/validation 오류 분기
- 중복 Node 병합
- cycle 방지
- missing evidence
- Schema validation
- commit 조합 변경 시 graph version 분리


## 완료 기준


- [ ] A→B 정상 관통 경로가 한 화면에 표시된다.
- [ ] `customerId`가 Frontend Input에서 Backend Request까지 연결된다.
- [ ] Backend Response가 B 화면 필드로 연결된다.
- [ ] 정상·제한·오류 경로가 구분된다.
- [ ] 모든 Edge의 근거와 Confidence를 볼 수 있다.
- [ ] Graph JSON이 Schema 검증을 통과한다.


## 제외 범위


- 테스트 실행
- 추천값 생성
- HITL


## 산출물


- Graph Builder
- Interaction Graph 저장/버전
- Graph API
- Flow UI
- Graph Golden Test


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-05.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
