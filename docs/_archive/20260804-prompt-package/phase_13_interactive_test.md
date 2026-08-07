# Phase 13 — 건별 시나리오 테스트 UX

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


사용자가 시나리오 1건을 선택해 자동 추천값을 최소 피로로 확인·수정하고, 실제 관통 테스트를 실행하며, 결과와 증적을 한 화면에서 확인하게 한다.


## 선행조건


- Phase 08~12 완료
- 시나리오와 추천 Input Profile 존재


## 구현 범위


- Scenario detail
- recommendation review
- selective edit
- run launch
- live status
- result/evidence
- retest


## 상세 구현 요구사항


1. 기본 진입 시 모든 필드를 편집 폼으로 펼치지 않는다.
2. 자동 확정된 값은 요약 표시하고, 불확실/필수 확인 항목만 강조한다.
3. 기본 CTA는 `추천값으로 실행`이다.
4. 사용자는 값, category, expected branch를 수정할 수 있다.
5. 수정값은 임시 Case 또는 새 Input Profile version으로 저장할 수 있다.
6. 실행 전 다음을 요약한다.
   - A 화면
   - 입력값
   - 예상 API
   - 예상 B 화면/분기
   - destructive 여부
7. 실행 중 Step progress와 현재 Evidence를 보여준다.
8. 실행 후 자동 기술 결과와 HITL 대기 상태를 분리해 표시한다.
9. 실패 시 가장 먼저 실패 Step, 원인, Screenshot, 재실행 옵션을 보여준다.
10. 동일 Scenario 재실행 시 이전 입력을 선택적으로 재사용한다.
11. 시나리오·입력·Commit version을 명확히 표시한다.
12. 접근성 키보드 조작과 오류 메시지를 제공한다.


## API·계약·데이터


필수 API는 기존 Scenario/Input/Run/Evidence API를 조합한다.  
건별 실행 요청에 다음을 포함한다.

```json
{
  "scenarioId": "...",
  "scenarioVersion": "...",
  "inputProfileId": "...",
  "overrides": {},
  "mode": "interactive"
}
```


## UI 요구사항


권장 화면 순서:

1. 상단 A→B Flow
2. 자동 인식된 필수 입력
3. 추천 테스트 구성
4. 불확실 항목
5. `추천값으로 실행`
6. 실행 Step Timeline
7. 자동 검증 결과
8. Evidence
9. `HITL 검증으로 이동`


## 필수 테스트


- 추천값 그대로 실행
- 1개 값 override
- unresolved 항목 확인
- 실행 중 cancel
- auto pass
- auto fail
- previous input reuse
- 접근성
- stale scenario/input version 방지


## 완료 기준


- [ ] 사용자가 기본 추천값으로 3클릭 이내 실행을 시작할 수 있다.
- [ ] 전체 입력 폼을 강제로 확인하지 않는다.
- [ ] 불확실 항목만 명확히 요청한다.
- [ ] 실행 상태와 실패 원인을 확인할 수 있다.
- [ ] 결과에서 Evidence와 HITL로 이동할 수 있다.
- [ ] 재실행 시 version mismatch를 방지한다.


## 제외 범위


- 배치 스케줄
- HITL 최종 승인 구현


## 산출물


- 건별 실행 UI
- orchestration API 보강
- UX 테스트
- 접근성 점검


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-13.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
