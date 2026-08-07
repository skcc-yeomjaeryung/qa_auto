# Phase 11 — 바인딩검증 완료 보고

## 1. 기본 정보

- Phase: 11.바인딩검증
- 작업일: 2026-08-05
- 담당 Agent/개발자: Cursor Agent
- 기준 Branch: 현재 작업 브랜치
- 관련 이전 Phase: 07 컴포넌트계약 · 09 브라우저실행 · 10 Backend추적
- 회차 요약: `docs/report/20260805/11_1.md`

## 2. 구현 요약

A 화면 입력, Frontend Request, Backend Request/Response, B 화면 관측값을
필드 단위 lineage로 비교하는 결정론적 Binding Validator를 구현했다.

- Phase 07 Output Contract의 `responsePath` · `uiLocator` · `normalize` 재사용
- `customerId` 5단계 lineage와 `customerName/riskLevel/status` Response↔UI 비교
- trim/case/number/currency/timezone/null-empty/enum label 정규화
- hard 기술 assertion(HTTP/route/schema)과 soft 필드 assertion 분리
- 기술 일치와 `businessReviewRequired` 분리 (최종 품질 판단은 HITL)
- 불일치 expected/actual · screenshot/snapshot/region evidence 저장
- 민감 필드는 비교 결과와 UI에 `***`로 마스킹
- 결과 JSON을 Run evidence와 SQLite catalog에 저장
- Phase 10 Timeline의 B Binding 항목을 저장된 검증 결과·artifact에 연결
- agent-browser 실행기가 비동기 locator 대기 후 `bindingValues`를 수집
- Run 상세에 9열 필드 lineage 표와 기술 비교 실행 CTA 제공

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `packages/contracts/schemas/binding_validation.schema.json` | HITL 재사용 결과 계약 |
| `backend/app/schemas/binding_validation.py` | Pydantic 입출력 |
| `backend/app/services/binding_normalization.py` | 결정론적 정규화 |
| `backend/app/services/binding_validation.py` | lineage resolver · assertion |
| `backend/app/api/binding_validation.py` | validate/assertions API |
| `backend/app/services/repository_store.py` | 결과·Backend event SQLite 영속 |
| `backend/app/services/telemetry/service.py` | Timeline B Binding 결과 연결 |
| `backend/app/skills/browser_execute/script/execute_run.py` | selector wait · UI 값 수집 |
| `frontend/components/BindingAssertionsTable.tsx` | 필드별 비교 UI |
| `frontend/app/runs/[runId]/page.tsx` | Run 상세 연결 |
| `frontend/app/styles.css` | 금융 SaaS형 dense table |
| `backend/tests/test_binding_validation_phase11.py` | 필수 Gate 테스트 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| 비교 엔진 | script/rule 기반 결정론 | LLM 판정 | 값·정규화 수치 확정은 rule |
| 자동 결과 문구 | MATCH/MISMATCH/PARTIAL | 업무 Pass/Fail | HITL 최종 판단과 분리 |
| UI 관측 | agent-browser selector wait + get text | OCR | DOM 근거 원칙 |
| missing 값 | `MISSING_DATA` | 추정/빈 문자열 보정 | Evidence 없는 추정 금지 |
| 영속 | evidence JSON + SQLite catalog | memory only | 세션 재시작 후 HITL 재사용 |

## 5. API·Schema 변경

- `POST /api/runs/{id}/validate-bindings`
- `GET /api/runs/{id}/assertions`
- `GET /api/runs/{id}/binding-validation` (Console 조회용 additive API)
- Schema: `binding_validation.schema.json`
- DB Migration: 없음 (기존 SQLite KV catalog additive field)
- 호환성 영향: 기존 Run/API에 breaking change 없음

## 6. 실행한 명령

```bash
cd backend
.venv/bin/pytest \
  tests/test_binding_validation_phase11.py \
  tests/test_backend_trace_phase10.py \
  tests/test_browser_execute_phase09.py -q
# 26 passed, 1 skipped

.venv/bin/pytest \
  tests/test_binding_validation_phase11.py \
  tests/test_backend_trace_phase10.py -q
# 21 passed

cd frontend
npx tsc --noEmit
npm run build
# Next.js build completed
```

agent-browser로 local Console `Run 상세`을 열어 다음을 DOM 기준 관측했다.

- `Input ↔ Request ↔ Response ↔ UI` 섹션
- `기술 비교 실행` CTA
- 9열 assertion 표
- 증적 없는 Run은 `부분 증적` · `missing_data`
- HITL 안내 문구

## 7. 테스트 결과

| 테스트 영역 | 명령 | 관측 결과 | 비고 |
|---|---|---|---|
| Unit/API | Phase 11 pytest | 11 passed | 필수 정규화·missing·mask |
| Regression | Phase 9~11 pytest | 26 passed · 1 skipped | 브라우저 CLI 환경 조건 skip |
| Frontend | tsc + Next build | 완료 | 타입·production build |
| Console DOM | agent-browser | 섹션·CTA·표 관측 | 실제 RUN-cancel은 partial evidence |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| customerId 관통 동일성 | 충족 관측 | `test_exact_customer_lineage_and_output_equality` |
| customerName/riskLevel/status 바인딩 | 충족 관측 | 동일 fixture · business review 분리 |
| 정규화 규칙 | 충족 관측 | trim/case/number/currency/timezone/enum/null tests |
| 기술 비교와 업무 검증 분리 | 충족 관측 | `TECHNICALLY_MATCHED` + `businessReviewRequired` |
| 불일치 값과 Evidence | 충족 관측 | masked mismatch + screenshot region test |
| HITL 입력 저장 | 충족 관측 | JSON artifact + SQLite + GET API |

> 위 결과는 기술 구현·테스트 관측이다. 고객의 최종 Pass/Fail이나 배포 승인을 뜻하지 않는다.

## 9. 보안·개인정보 검토

- Secret 노출 여부: 민감 field expected/actual/UI 모두 `***`
- PII 마스킹: 기존 screenshot mask contract 유지
- 로그 검토: Backend event도 SQLite에는 이미 마스킹된 payload 저장
- 권한 검토: 변경 API는 기존 `X-User-Id` gate 적용
- 미해결 위험: 일반 업무 필드의 PII 분류는 대상 adapter 정책 확장이 필요

## 10. 알려진 제약

- `Frontend Request`는 browser network evidence가 있거나 validate 요청으로 전달될 때 채워진다.
- 실제 대상 FE가 tracing/localStorage header와 binding locator를 지원하지 않으면 `missing_data`.
- JSONPath는 파일럿 범위의 단순 객체 경로(`$.a.b`)를 지원하며 배열/filter 문법은 제외.
- 실제 고객 대상의 업무 의미 정답은 자동 확정하지 않는다.

## 11. 다음 Phase 전달사항

- 다음 Phase: **12.증적수집**
- 입력 artifact: `artifacts/evidence/runs/{runId}/binding-validation.json`
- API: `/api/runs/{id}/binding-validation` · `/assertions`
- mismatch screenshot/snapshot/region을 Evidence Package manifest에 포함
- partial/missing_data를 숨기지 않고 HITL에 전달

## 12. 문서 변경

- `docs/index.md` · `AGENTS.md` · Cursor Phase pointer → 12
- `docs/continue/NEXT.md` → Phase 12 입력 계약
- `docs/report/20260805/11_1.md`
