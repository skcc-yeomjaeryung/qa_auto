# Phase 14 — 승인 Input Profile 기반 배치·반복 관통 테스트

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


승인된 추천값과 실행 정책을 사용해 여러 시나리오 또는 여러 입력 Case를 무인·병렬 실행하고, 예외 중심으로 결과를 요약한다.


## 선행조건


- Phase 08 Input Profile 승인 기능
- Phase 09~12 실행/증적 완성


## 구현 범위


- Batch definition
- case generation
- queue/concurrency
- retry
- policy
- summary
- pause/cancel/resume
- exception-first review


## 상세 구현 요구사항


1. Batch는 Scenario version과 approved Input Profile version을 고정한다.
2. 입력 category별 실행 건수와 총 실행 예산을 설정한다.
3. 기본 자동 정책:
   - unresolved input: skip + notify
   - destructive scenario: exclude
   - low confidence scenario: review required
4. Worker 동시성과 프로젝트별 Rate Limit을 설정한다.
5. 동일 테스트 환경의 데이터 충돌을 피하도록 resource lock 또는 isolation key를 지원한다.
6. retry는 인프라 오류와 제품 실패를 구분한다.
7. flaky 재실행 결과를 별도 기록하고 최초 실패를 숨기지 않는다.
8. Batch 상태:
   - DRAFT
   - READY
   - RUNNING
   - PAUSED
   - COMPLETED
   - COMPLETED_WITH_FAILURES
   - CANCELLED
9. 개별 Run마다 완전한 Evidence를 생성한다.
10. 요약은 pass/fail뿐 아니라 branch, mismatch field, missing evidence, review required를 보여준다.
11. 모든 성공 건을 강제로 한 건씩 열게 하지 말고 exception-first와 일괄 검토 후보를 제공한다.
12. 배치 정의와 결과는 재현 가능해야 한다.


## API·계약·데이터


필수 모델:
- `BatchDefinition`
- `BatchCase`
- `BatchRun`
- `BatchPolicy`
- `BatchSummary`

필수 API:
- `POST /api/batches`
- `POST /api/batches/{id}/start`
- `POST /api/batches/{id}/pause`
- `POST /api/batches/{id}/resume`
- `POST /api/batches/{id}/cancel`
- `GET /api/batches/{id}`
- `GET /api/batches/{id}/summary`


## UI 요구사항


- 시나리오/Scenario Set 선택
- 승인 Input Profile 선택
- category별 건수와 총 예산
- 동시성
- unresolved/destructive 정책
- 예상 실행 Case preview
- 진행률이 아니라 실행 상태와 건수
- 실패/변경/저신뢰 우선 필터
- HITL 검증 대상 묶음 생성


## 필수 테스트


- 20건 batch
- concurrency limit
- pause/resume/cancel
- resource lock
- infra retry
- product failure no retry 또는 정책 retry
- flaky 기록
- unresolved skip
- destructive exclusion
- evidence per case
- deterministic case generation


## 완료 기준


- [ ] 승인 Profile로 사용자 입력 없이 Batch를 실행한다.
- [ ] 정해진 횟수와 category 분포를 지킨다.
- [ ] 동시성/취소/재시작이 안전하다.
- [ ] 각 Run의 Evidence가 보존된다.
- [ ] 실패·변경·저신뢰 결과를 우선 볼 수 있다.
- [ ] Batch 결과를 HITL 검증 묶음으로 전달한다.


## 제외 범위


- 장기 스케줄러 고도화
- 테스트 진척률
- 무제한 부하 테스트


## 산출물


- Batch Orchestrator
- Queue/Worker policy
- Batch API/UI
- 결과 요약
- 통합 테스트


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-14.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
