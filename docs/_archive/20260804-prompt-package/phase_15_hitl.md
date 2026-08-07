# Phase 15 — 고객 HITL 값 검증·승인·반려·재실행

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


모든 자동 테스트 결과를 기술적 PASS와 고객 업무 승인으로 분리하고, 고객이 값과 증적을 검증한 후 승인·반려·재실행하도록 강제한다.


## 선행조건


- Phase 12 Evidence 완성
- Phase 13 건별 실행
- Phase 14 배치 실행


## 구현 범위


- Review queue
- field-level validation
- approval/rejection
- retest request
- bulk review
- audit trail
- role/permission
- immutable history


## 상세 구현 요구사항


1. 자동 기술 상태가 PASS여도 최종 상태는 `WAITING_FOR_REVIEW`다.
2. 고객 검증 화면에 다음을 한 번에 제공한다.
   - Scenario/Commit/Input Profile
   - A 입력값
   - Frontend/Backend Request
   - Backend Response
   - B 화면 Screenshot
   - 필드별 Binding Assertion
   - 자동 기술 결과
3. 검증 항목:
   - 값 일치
   - 업무 규칙 적합
   - 화면 표현 적합
   - 분기 적합
4. 고객 선택:
   - APPROVED
   - REJECTED
   - RETEST_REQUESTED
   - DATA_CORRECTION_REQUIRED
5. 반려는 reason type, 대상 필드, 기대값, 실제값, comment를 구조화한다.
6. 재실행은 이전 Evidence를 덮어쓰지 않고 새 Run을 생성해 lineage로 연결한다.
7. Reviewer role과 권한을 적용한다.
8. 동일 사용자가 자신이 생성한 결과를 승인할 수 있는지 프로젝트 정책으로 설정한다.
9. Batch에서는 exception-first 검토와 선택적 일괄 승인을 지원하되, 핵심 시나리오는 전수 검증 정책을 지원한다.
10. 승인 기록은 수정하지 않고 새 결정 이벤트로 append한다.
11. 승인 취소/정정은 별도 이벤트와 사유를 남긴다.
12. 고객이 검증하지 않은 결과를 `완료`로 표시하지 않는다.
13. 고객 피로도를 낮추기 위해 변경된 필드, 실패, 저신뢰, 업무 중요 항목을 우선 강조한다.


## API·계약·데이터


상태 예시:

```text
AUTO_PASSED
  → WAITING_FOR_REVIEW
    → APPROVED
    → REJECTED
    → RETEST_REQUESTED
    → DATA_CORRECTION_REQUIRED
```

필수 API:
- `GET /api/reviews`
- `GET /api/reviews/{id}`
- `POST /api/reviews/{id}/decisions`
- `POST /api/reviews/{id}/retest`
- `POST /api/reviews/bulk-decisions`
- `GET /api/reviews/{id}/audit`


## UI 요구사항


HITL 검증함:

- 우선순위/상태 필터
- 건별 또는 Batch 묶음
- A 입력 ↔ Backend Response ↔ B Screenshot 비교
- 필드별 체크
- 자동 Assertion과 고객 검증을 구분
- 승인/반려/재실행 CTA
- Audit Trail
- 미검증 건수는 표시하되 1차 범위의 테스트 진척률로 표현하지 않는다.


## 필수 테스트


- auto pass→waiting
- approve
- reject with field mismatch
- retest lineage
- data correction
- bulk approval
- critical scenario no bulk
- permission
- maker-checker policy
- immutable audit
- decision correction
- stale evidence/version


## 완료 기준


- [ ] 기술 PASS가 자동 승인되지 않는다.
- [ ] 고객이 A 입력, Backend 응답, B 화면을 함께 검증한다.
- [ ] 필드별 승인/반려 사유가 저장된다.
- [ ] 재실행이 새 Run과 Evidence를 만든다.
- [ ] Batch도 검증 대상 묶음으로 처리된다.
- [ ] 권한과 Audit Trail이 적용된다.
- [ ] 미검증 결과를 완료로 오인하지 않는다.


## 제외 범위


- 법적 전자서명
- 외부 고객 포털 SSO 전체 구축
- 자동 고객 승인


## 산출물


- HITL Workflow
- Review API/UI
- Audit Trail
- 권한 정책
- 통합 테스트


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-15.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
