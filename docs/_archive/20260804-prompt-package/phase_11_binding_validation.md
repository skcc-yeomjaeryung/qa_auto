# Phase 11 — Input·Backend Request·Response·B 화면 데이터 바인딩 검증

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


A 화면 입력값, Frontend Request, Backend Request/Response, B 화면 표시값을 필드 단위로 비교해 기술적 관통 검증 결과를 생성한다.


## 선행조건


- Phase 09 Browser 실행 완료
- Phase 10 Backend Trace 완료
- Phase 07 Output Binding Contract 사용 가능


## 구현 범위


- Data lineage resolver
- JSONPath→UI Locator
- normalization
- hard/soft assertion
- technical validation result
- mismatch evidence


## 상세 구현 요구사항


1. 최소 비교 체인:
   `A input.customerId = Frontend request.customerId = Backend request.customerId = Backend response.customerId = B ui.customerId`
2. Response fields `customerName`, `riskLevel`, `status`와 B UI를 비교한다.
3. normalize rule:
   - trim
   - case
   - number formatting
   - date/time timezone
   - currency/comma
   - null/empty
   - enum display label
4. UI는 비동기 렌더링 완료 조건을 기다린 후 읽는다.
5. 기술 Assertion:
   - HTTP status
   - response schema
   - route
   - visibility
   - exact/normalized equality
6. 업무 의미가 필요한 항목은 `businessReviewRequired`로 표시하고 자동 정답 판정하지 않는다.
7. mismatch는 expected, actual, source, evidence screenshot region을 제공한다.
8. soft assertion은 여러 필드를 모두 수집하고, hard assertion은 진행 불가 조건에만 사용한다.
9. 민감 필드는 비교하되 UI와 로그에서는 마스킹 정책을 적용한다.
10. 결과는 HITL에서 재사용할 구조화 JSON으로 저장한다.


## API·계약·데이터


Validation Result 예시:

```json
{
  "runId": "RUN-001",
  "technicalStatus": "PASSED",
  "assertions": [
    {
      "field": "riskLevel",
      "source": "$.riskLevel",
      "target": "testid:risk-level",
      "expected": "HIGH",
      "actual": "HIGH",
      "result": "PASS",
      "businessReviewRequired": true
    }
  ]
}
```

필수 API:
- `POST /api/runs/{id}/validate-bindings`
- `GET /api/runs/{id}/assertions`


## UI 요구사항


Run 상세에 필드별 표를 제공한다.

- A 입력
- Frontend Request
- Backend Request
- Backend Response
- B 화면
- 자동 비교 결과
- 고객 검증 필요 여부
- mismatch Screenshot link


## 필수 테스트


- exact equality
- trim/case
- number/currency
- date timezone
- enum label
- null/empty
- async delayed binding
- missing UI field
- business review required
- masked field


## 완료 기준


- [ ] customerId 관통 동일성을 검증한다.
- [ ] customerName/riskLevel/status 바인딩을 검증한다.
- [ ] 정규화 규칙이 적용된다.
- [ ] 기술 PASS와 업무 검증 필요를 분리한다.
- [ ] 불일치 값과 Evidence를 확인할 수 있다.
- [ ] 결과가 HITL 입력으로 저장된다.


## 제외 범위


- 고객 업무 규칙의 자동 최종 판정
- 이미지 OCR 기반 값 추출


## 산출물


- Binding Validator
- Normalization library
- Assertion API/UI
- 테스트 Fixture


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-11.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
