# Phase 08 — 추천 테스트 입력값·Input Profile 생성과 증강

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


Component/Input Contract, Backend Validation, 기존 테스트, Fixture, 초기 Best Practice Catalog를 결합해 사용자가 피로하지 않도록 자동 추천값과 배치용 승인 Input Profile을 생성한다.


## 선행조건


- Phase 03 Backend Analysis 완료
- Phase 07 Component Contract 완료
- 초기 Best Practice Catalog 사용 가능


## 구현 범위


- Test Data Catalog
- 추천값 우선순위
- 정상/경계/오류/업무상태 데이터
- Pairwise 조합
- interactive recommendation
- approved batch profile
- 민감정보 마스킹


## 상세 구현 요구사항


1. 입력원 우선순위:
   1) 프로젝트 Fixture/Factory/Seed/Test code
   2) 테스트 전용 Data API
   3) Frontend/Backend Schema와 Validation
   4) 초기 Best Practice Catalog
   5) LLM semantic suggestion
   6) 사용자 입력
2. 기존 테스트에서 반복되는 값을 후보 대표값으로 승격하되 출처와 빈도를 기록한다.
3. 데이터 범주:
   - happy path
   - boundary
   - invalid format
   - missing required
   - business state
   - not found
   - pairwise
4. 실제 존재해야 하는 식별자는 무작위 생성하지 말고 Fixture/Data API/approved static value를 사용한다.
5. 사용자가 건별 실행 시 볼 정보:
   - 추천값
   - 추천 근거
   - 예상 경로
   - 불확실 항목
6. 배치 실행용 `Input Profile`은 승인 상태와 버전을 가진다.
7. 불확실한 기대값은 자동 배치에서 `skip`, `reviewRequired`, `usePolicyDefault` 중 정책으로 처리한다.
8. destructive data는 생성하지 않는다.
9. PII/Secret은 synthetic 또는 masked 값만 사용한다.
10. 조합 폭발을 막기 위해 pairwise와 실행 예산을 지원한다.
11. 추천 결과는 결정론적으로 재생성 가능하도록 seed와 generator version을 기록한다.


## API·계약·데이터


필수 모델:
- `TestDataCatalogEntry`
- `RecommendedValue`
- `InputProfile`
- `GenerationPolicy`
- `DataSourceEvidence`

필수 API:
- `POST /api/scenarios/{id}/recommend-inputs`
- `GET /api/scenarios/{id}/input-profiles`
- `POST /api/scenarios/{id}/input-profiles`
- `POST /api/input-profiles/{id}/approve`
- `POST /api/input-profiles/{id}/generate-cases`


## UI 요구사항


건별 모드:
- 자동 추천된 값이 기본 선택
- 근거와 예상 경로 표시
- 사용자는 필요한 값만 수정
- 불확실한 항목만 강조

배치 모드:
- 승인된 Profile 선택
- category별 건수
- 실행 예산
- unresolved 정책
- destructive 제외 표시


## 필수 테스트


- Zod/Bean Validation 기반 경계값
- 기존 Fixture 우선
- existing test hard-coded value 추출
- 식별자 무작위 생성 방지
- pairwise 축소
- deterministic seed
- PII masking
- unresolved 정책
- Input Profile version/approval


## 완료 기준


- [ ] 고객조회 정상/제한/미존재/형식오류 추천값을 생성한다.
- [ ] 각 값의 출처와 근거를 표시한다.
- [ ] 건별 모드에서 기본값이 자동 채워진다.
- [ ] 승인된 배치 Profile을 생성할 수 있다.
- [ ] 실행 횟수 예산 내에서 조합을 생성한다.
- [ ] 민감정보가 추천값이나 로그에 노출되지 않는다.


## 제외 범위


- 운영 DB 직접 조회
- 무제한 fuzzing
- 업무 기대값의 자동 최종 승인


## 산출물


- Test Data Catalog
- Recommendation Engine
- Input Profile API/UI
- Best Practice 초기 데이터
- Generator 테스트


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-08.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
