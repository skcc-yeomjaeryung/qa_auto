# 다음 세션 진행 방향 (핸드오프)

- 작성일: 2026-08-08
- 직전: Phase **13.건별테스트** Gate 완료 (`docs/06.완료보고/PHASE-13.md` · `docs/report/20260805/13_4.md`)
- 진행: Phase **14.배치테스트** 사용자 화면별 수용 검증 계속 (`docs/report/20260808/14_7.md`) — 근거 기반 예측 시나리오 보강과 동일 Run의 시나리오·그래프·실행 이력·HITL 리포트 상태 관통 일관성 적용

---

## 1. 다음 Phase

| 항목 | 값 |
|---|---|
| Phase | **14.배치테스트** |
| 문서 | [`../04.Phase실행바이블/14.배치테스트.md`](../04.Phase실행바이블/14.배치테스트.md) |

---

## 2. 읽기 순서

```text
1. docs/continue/NEXT.md
2. docs/index.md
3. AGENTS.md
4. docs/04.Phase실행바이블/14.배치테스트.md
5. docs/06.완료보고/PHASE-13.md
```

---

## 3. Phase 13에서 넘겨줄 계약

| 항목 | 값 |
|---|---|
| 건별 실행 | `POST /api/scenarios/{scenarioId}/runs` (`mode`·`consent`·`environmentId`·`overrides`·`reuseFromRunId`) |
| 실행 조회 | `GET /api/runs/{runId}` — `result.runNarrative` · `result.inputBindings` · 단계별 스크린샷 |
| 취소 | `POST /api/runs/{runId}/cancel` · 세트 단위 `POST /api/scenario-sets/{setId}/stop` |
| 실행 준비 | `GET /api/scenarios/{scenarioId}/run-preview` — `inferred`(자동 생성값) · `missing_data` 구분 |
| 환경 | `browser` · `loginId` 필수 · 비밀번호는 `hasLoginSecret` 로만 노출 |
| 증적 | 화면 진입 · 입력 섬밋 · 결과 화면 최소 3장 + Evidence Package(12) |

---

## 4. Phase 14 주의

- 배치는 **무인 실행**이다. 건별 콘솔의 확인 단계(consent·override)를 배치 경로에 그대로 요구하지 않는다.
- 동시 실행 상한·큐·부분 실패 집계를 먼저 정하고 UI를 붙인다 (Progress Type 1/5).
- 배치 Complete ≠ HITL Pass. 기술 상태와 승인 상태를 절대 합치지 않는다.
- 실행 시각은 목록·상세 모두 `yyyy-mm-dd hh:mm:ss` (`frontend/lib/datetime.ts` 공통 포맷).
- 목록 화면은 체크박스·선택 삭제·화면 내 검색(`ScreenSearch`) 공통 구성을 따른다.

### Console 경로 격상 (2026-08-06 · `docs/report/20260806/14_1.md`)

| 항목 | 값 |
|---|---|
| 테스트 시나리오 메뉴 | `/scenarios` (구 `플로우` 격상. 구 `테스트 시나리오` 메뉴·`ScenarioTable` 제거) |
| 그룹 목록 | `/scenarios?setId=…` — 일괄 실행 · 종료 · 삭제는 이 단계 푸터 |
| 상세 | `/scenarios?setId=…&scenarioId=…` — 좌측 목록 유지 + 우측 슬라이드 (`ScenarioDetailPanel`) |
| 의존관계 그래프 | 같은 URL + `view=graph` — 시나리오 단위 부분집합 |
| 구 경로 | `/flow` 는 쿼리 보존 리다이렉트만 (신규 링크에 쓰지 않는다) |
| scoped 그래프 API | `GET /api/scenarios/{scenarioId}/interaction-graph` — `evidenceRefs`·`evidenceIndex` 기반, 근거 없으면 `missingData` |

- 배치 화면도 이 경로 체계 위에 올린다. `/flow` 를 신규 진입점으로 되돌리지 않는다.
- 좌측 메뉴는 **1depth**만 둔다 (그룹 트리 제거 · `docs/report/20260806/14_2.md`). 그룹 선택은 `/scenarios` 그룹 화면에서 한다.
- 상세는 `[화면 구성 확인][실행 흐름][예상 테스트 결과]` 3탭이며, 케이스 ID·selector·RUN/commit 같은 기술 정보는
  접이식 `기술 상세`에만 둔다. 배치 결과 화면도 같은 눈높이를 따른다.

### 세션 선행조건 · 기대결과 판정 (D-015 · 2026-08-06 · `docs/report/20260806/14_2.md` · 실행경로 `14_3.md`)

계약 SSOT: [`../03.계약과예시/08.세션선행조건과판정계약.md`](../03.계약과예시/08.세션선행조건과판정계약.md)

| 항목 | 값 |
|---|---|
| 세션 판별 프롬프트 | `backend/app/prompts/scenario/session_precondition_system.md` |
| 판정 프롬프트 | `backend/app/prompts/run/verify_expected_result_system.md` |
| 시나리오 계약 | `scenario_dsl` v1.1.0 — `authRequired` · `sessionPolicy` · `verdictCriteria[]` |
| 실행 계약 | `browser_execute` v1.2.0 — `sessionEstablished` · `verdict` |
| 정책 값 | `no_auth` · `login_then_reuse` · `reuse_existing_session` · `fresh_login_required` |

- **도달 = 성공 금지.** 화면·Endpoint 접근, 무예외, 스크린샷 존재만으로 성공을 만들지 않는다.
- 인증 뒤 화면(로그아웃·잔액·송금·거래내역·내 정보)은 선행 로그인 단계를 시나리오에 포함하고 같은 세션으로 진행한다.
- 계정은 연결정보 참조(`environment.loginId` / `environment.loginSecret`)만 쓴다. 값 생성·출력 금지.
- 배치 실행에서 `reuse_existing_session` 시나리오는 세션을 만든 시나리오 뒤 순서를 보장한다.

실행경로 적용 상태 (`docs/report/20260806/14_3.md`):

| 구간 | 붙은 것 |
|---|---|
| FE 분석 | 허용 method · 인증 가드 · 동작 form(여는 버튼 포함) · 세션 마커 |
| Graph | `graph.authContext` (로그인 경로·컨트롤·가드/POST전용 라우트·트리거·세션 마커) |
| 시나리오 | `session_precondition` — 선행 로그인 5단계 · POST전용 경로는 화면 트리거로 대체 · `assert_absent` · `verdictCriteria` |
| 실행 | 연결 계정 참조 로그인 · 세션 확인 blocking · 거부 문구 관측 · `evaluate_verdict` |
| 목록/요약 | 판정 기반 상태 — 도달만으로 「정상 관측」 금지 |
| 화면 | 상세에 선행조건 카드 · 판정 기준 대조 목록 |

- 화면 경로가 `missing_data`인 시나리오는 없는 주소를 열지 않고 `undetermined`로 남긴다.
- 남은 것: 배치 실행의 세션 승계 순서 정렬 · 모달/접힌 컨트롤 판정 기준.

### 파일럿 샌드박스 연결 (고정 · 사용자 지정)

| 항목 | 값 |
|---|---|
| 연결 URL | `https://cymbal-bank.fsi.cymbal.dev` (origin. 진입 화면 `/home` 은 health path) |
| 연결 BROWSER | `chrome` |
| 연결 ID | `testuser` |
| 연결 PASSWORD | 파일럿 데모 계정 (환경 secret 저장소에만 보관 · 응답 미노출) |
| Backend SSOT | `app/services/environment_models` (`CYMBAL_BANK_ORIGIN` · `PILOT_SANDBOX_*`) |
| Frontend SSOT | `frontend/lib/pilotTarget.ts` · `ProjectsWorkbench` 연결 기본값 |

- 로컬 `127.0.0.1:5173` 을 기본값으로 되돌리지 않는다 (`local-vite` 프리셋으로만 남긴다).
- 절대 경로(`/login` 등)는 **origin 기준**으로 해석한다 (`route_url` · `build_health_url`).
- health check는 TLS 검증을 끄지 않고 OS 신뢰 저장소(`truststore`)를 사용한다.
- `npm run build` 는 `.next-build` 로 나간다. dev 서버의 `.next` 를 덮어쓰지 않는다.

---

## 5. Guardrail 리마인드

- Secret/PII 미저장 · 마스킹 유지
- Pass/Fail·배포 확정 금지 (HITL)
- 근거 없는 값 확정 금지 → `missing_data` (단, 테스트 입력은 필드 근거 기반 `inferred` 합성 허용 · 표시 필수)
- Endpoint 도달만으로 성공 플래그·증적을 남기지 않는다 (D-015)
- Playwright MCP는 보완·문의 후. FE 관측 기본은 agent-browser

---

## 6. 14_6 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 대시보드 | `GET /api/dashboard/summary` · `X-User-Id` 범위 실데이터 · 빈 성공률은 `null` |
| 시나리오 분류 | `ScenarioSummary.businessPath` L1/L2/L3 · `assignedRole` · 근거 없으면 결정적 fallback |
| 생성 방식 | `POST /api/console/generate-scenarios` · `sourceMode=ai|test_data_csv` · CSV 자연어 입력은 AI 보강 후 HITL 대기 |
| 실행 계정 | 환경 기본 계정 또는 실행 세션 메모리 계정 · `role` 필수 · 비밀번호 응답/증적/LLM/SQLite 금지 |
| 일괄 진행 | `GET /api/console/bulk-runs/events?runIds=...` SSE · `progress`/`complete` |
| 배치 | `/api/batches` · version pin · Rate Limit · resource lock · infra/product retry · flaky · pause/resume/cancel |
| 공통 목록 | `TableBulkDeleteForm` CSV import/export · table-layout 고정 · action wrap |
| 연결 자동 분석 | Step 2에서 연결 45% → 자동 분석 72% → 완료 100%, 완료 뒤 `분석 메뉴`/`다음 · 실행 환경` 선택 |
| 동기화 자동 분석 | 수동/5분 주기 sync 뒤 `bulk-analyze`, 프로젝트 행의 중복 분석 버튼 제거 |
| CSV 다운로드 | 공통 표는 `/api/csv-export` attachment 응답, 템플릿은 `/templates/*.csv` |
| 인앱 브라우저 Gate | 1920×1080/1440px·AI 14건 생성·SSE·취소·CSV·console error 0 검증 완료 |

- 브라우저 증적은 `artifacts/evidence/phase14-dashboard-scenario/browser/`, 상세 판독은 `VERIFICATION.md`를 따른다.
- 기존 Phase 7 component-contract 회귀는 14_7 전체 회귀에서 해소됐다. Phase 14 포인터는 사용자의 화면별 수용 검증이 계속되는 동안 유지한다.

---

## 7. 14_7 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 저장소 분석 | 서버 스택이어도 화면·Flask(Frontend) 분석을 항상 수행하고 Backend와 한 그룹으로 표시 |
| 판정 | Flask 404/Not Found는 blocking, `expected_not_met`은 자동 실패 표시. 도달만으로 정상 관측 금지 |
| 업무 Progress | L1/L2 카드 상시 Progress + 클릭 시 우측 완료/진행/오류 상세 |
| 실행·증적 | 실행 ID 우측 drawer에 판정·단계·증적·ZIP 통합, `/evidence`는 `/runs?view=evidence`로 이동 |
| HITL | 검토 우선순위와 누락/부분 증적을 우측 drawer에 제시. 최종 Pass/Fail 자동 확정 금지 |
| 시나리오 그래프 | DSL의 navigate/fill/click/verify/API를 순서 노드로 표시 |
| 신규 회원가입 생성 | Jinja CTA 근거가 있으면 진입 화면 → CTA 클릭 → 가입 화면 → 입력/제출/API. 근거 없는 단계 생성 금지 |
| 회귀 | Backend 171 passed, 6 skipped · Frontend production build PASS |

- 브라우저 증적: `artifacts/evidence/phase14-ui-hardening/browser/`.
- 상세 판독: `artifacts/evidence/phase14-ui-hardening/VERIFICATION.md`.

---

## 8. 14_8 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 업무 시나리오 | UI 원자 케이스가 아니라 로그인 선행조건 → 업무 CTA/입력 → API → 성공 문구 → 상태 delta → 신규 목록 행을 한 시나리오로 생성 |
| 최종 생성본 | `IG-6d877df71b56` · 14건 · 입금 `SCN-deposit-e2e-001-67e32d0f` · 17단계 |
| 업무 제목 | 코드에서 관측한 후속 상태를 조합한 이름을 narration·Console에서 보존 |
| 실행 | destructive 동의 후 실제 select/fill/click, 사전 값·목록 capture, 수치·신규 행 검증 |
| 결과 분리 | 시나리오에는 기준·입력·간략 결과, 실행 이력에는 단계·증적·원인·조치·담당자 전달문 |
| 판정 | 직접 criterion 관측 우선, 도달만으로 성공 금지, 최종 Pass/Fail은 HITL |
| 읽기 재시도 | GET/HEAD/OPTIONS만 네트워크·429·502/503/504 제한 재시도. 쓰기 요청은 재시도 금지 |
| 실실행 증적 | `RUN-0041491ff634` · amount 30 · Deposit successful · 135→165 · External Bank +$30 |
| 회귀 | Backend 175 passed, 6 skipped · Frontend production build PASS |

- 브라우저 증적: `artifacts/evidence/phase14-business-journey-result/`.
- 상세 판독: `artifacts/evidence/phase14-business-journey-result/VERIFICATION.md`.
- 현재 로컬 LLM endpoint는 연결 거부 상태다. 프롬프트는 보강됐지만, 14_8 실데이터 검증은 결정론 fallback 기준이다.

---

## 9. 14_9 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 그래프 | 행 전환선은 카드 사이 gutter, 조건 라벨은 선 위, 우측 상단 `-`·`+`·`맞춤` |
| 단계 I/O | DSL의 browser/HTTP operation·계획 입력·최근 실행 관측만 표시. 실행 전 output은 `observed:false` |
| 단계 상태 | 시나리오 scoped graph 단위 저장·복원, 재처리는 저장된 `runInputs` 또는 `valueSource/value` 사용 |
| 런타임 탐색 | 등록 계정 로그인·GET 화면·DOM snapshot·스크린샷·비파괴 modal opener·BE 계약 수집 |
| 자율 생성 근거 | `frontend_code` + `backend_contract` + `live_dom` + `screenshot` |
| 탐색 안전장치 | 업무 form submit 금지, POST route 직접 GET 금지, secret/currentValue 저장 금지 |
| 최신 생성본 | `SCN-deposit-e2e-001-8f98cab1` · 입금 업무 17단계 · runtime discovery complete |
| 회귀 | Backend 177 passed, 6 skipped · Frontend production build PASS |

- 브라우저 증적: `artifacts/evidence/phase14-flow-runtime-discovery/flow-step-runtime.png`.
- 상세 판독: `artifacts/evidence/phase14-flow-runtime-discovery/VERIFICATION.md`.
- 로컬 LLM endpoint는 계속 연결 거부 상태다. 생성 입력·프롬프트 보강은 완료됐지만 이번 실데이터 narration은 결정론 fallback이다.

---

## 10. 14_10 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 기존 개수 보정 | `IG-7fe5b31b7c34` 원본 14행 중 동일 graph/case 중복을 목록에서 제외해 고유 13건 표시, 원본 증적 유지 |
| 금융 분류 | payment/transfer/결제/이체/송금은 `금융 거래/송금 담당`; 기존 그룹도 입금·송금 각 1건 |
| 최신 생성본 | `IG-6d877df71b56` · 고유 23건 · 금융 12건(입금 6, 송금 6) |
| 케이스 행렬 | 실제 min/max/required/dynamic balance 근거만 정상·경계·예외로 확장, 고정 개수 없음 |
| 잔액 입력 | 실행 직전 `beforeValue`를 `observed_balance`/`observed_balance_plus_step`으로 계산, 절대 잔액 복사 금지 |
| 증적 | 실행 상세 이미지 원본 확대·개별 다운로드·`현재 증적 ZIP` |
| 패키지 미생성 상태 | A→Backend→B 관측, raw 파일 수, 누락, 무결성·마스킹 적용 시점을 먼저 표시 |
| FLOW 재처리 | 단일 실행 SSE Progress · 선택 단계 고정 강조 · 선행환경 복원 · 후속 step 순차 강조 |
| 회귀 | Backend 178 passed, 6 skipped · Frontend production build PASS |

- 브라우저 증적: `artifacts/evidence/phase14-scenario-evidence-replay/`.
- 상세 판독: `artifacts/evidence/phase14-scenario-evidence-replay/VERIFICATION.md`.
- 로컬 LLM endpoint는 연결 거부 상태다. Prompt/생성 계약은 보강됐지만 이번 23건은 결정론 fallback 결과다.

---

## 11. 14_11 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 프로젝트 연결 | 고정 최대 폭 없이 가용 폭 사용, 본문/안내는 1.7fr/0.8fr, 960px 이하 단일 열 |
| 프로젝트 상세 | 프로젝트·연결 저장소·실행 환경을 실제 API 데이터 기반 전폭 카드 그리드로 표시 |
| 긴 값 | URL·경로·commit은 카드 내부 줄바꿈, 화면 가로 오버플로 금지 |
| 완료 화면 | 성공 카드와 다음 작업 영역의 고정 최대 폭 제거 |
| FLOW 상태 | 런타임 새로고침 성공 시 오래된 오류 메시지 제거 |
| 시각 증적 | 프로젝트 연결·상세·FLOW·실행 이력·HITL을 1920×1080으로 캡처 |
| 검증 | Frontend production build PASS · Frontend/Backend HTTP 200 · 최종 캡처 console error 0 |

- 브라우저 증적: `artifacts/evidence/phase14-project-layout-captures/`.
- 상세 판독: `artifacts/evidence/phase14-project-layout-captures/VERIFICATION.md`.

---

## 12. 14_28 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 시나리오 일괄 실행 | SSE가 완료·성공 관측·실패 관측·취소를 집계하고 `실행 관측` 셀의 공통 진행 막대에 반영 |
| 실행 집계 범위 | 현재 실행 대상 시나리오 ID만 실시간 집계해 이전 실행 이력과 혼합하지 않음 |
| 분석 진행 | Frontend/Backend analyzer의 실제 파일 처리 snapshot을 `fileTotal/fileCompleted/fileFailed/progressPercent`로 제공하고 `분석 진행` 셀에 표시 |
| 공통 진행 셀 | Figma TableBlock `77:139379`의 barchart 상태 셀 의도를 `TableProgressCell`로 공통화 |
| FLOW | 가로·세로 스크롤과 방향키·Page Up/Down·Home/End 탐색 지원 |
| 그래프 CTA | 의존관계 그래프는 보라색 주 행동 버튼 |
| 판정 분리 | 성공/실패 수는 기술 관측 집계이며 HITL 최종 Pass/Fail이 아님 |
| 회귀 | Backend app 231 passed, 6 skipped · Frontend analyzer 9 passed, 1 skipped · Frontend production build PASS |

- 상세 보고: `docs/report/20260807/14_28.md`.
- 저장소 전체 pytest는 제거된 legacy backend-analyzer Skill import 때문에 collection 단계에서 중단되며, 애플리케이션 테스트 Gate와 분리해 기록한다.

---

## 12. 14_12 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 관리 메뉴 | `MANAGE > 스케줄링` · `/manage/schedules` · 프로젝트 범위 고정 |
| 스케줄 저장 | SQLite KV · 고유 ID·한글명·시나리오·환경·Cron·기간·시간대·최근 실행·Progress |
| 등록 편의 | 프로젝트/그룹 picker · 자연어→Cron · 캘린더 기간 · 템플릿/CSV import/export |
| 실행 안전 | 소유자·프로젝트·환경 범위 검증 · destructive 차단 · 중복 실행 skip · Complete ≠ HITL Pass |
| Runs/HITL | 프로젝트→시나리오 그룹 필터, 첫 열은 그룹→시나리오 ID→한글명→실행 ID |
| 프로젝트 Step 4 | CSV/PPT/PPTX 드래그앤드롭 · 처리 Progress · 완료/부분/오류 · 추가/삭제 |
| 문서 처리 | CSV 정형화 · PPTX 텍스트+VLM OCR · embedding API/local fallback · FAISS local index |
| Context Agent | `QA.CODE.PROJECT_CONTEXT_DISCOVER`가 `wf_scenario_dsl` 선행 단계에서 found/not_found 분기 |
| 문서 Guardrail | Graph·DOM·API와 join된 내용만 후보 사용, 문서 단독 확정 금지, 충돌은 unresolved |
| 회귀 | Backend 184 passed, 6 skipped · Frontend production build PASS · 1920×1080 8장 증적 |

- 브라우저 증적: `artifacts/evidence/phase14-schedule-context/`.
- 상세 판독: `artifacts/evidence/phase14-schedule-context/VERIFICATION.md`.
- 다음 수용 Gate: 실제 설계 PPTX의 VLM 추출 품질, 예약 시각 자동 실행, 완료 상태와 HITL 연결 확인.

---

## 13. 14_13 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 단일 Core | `corev2` 금지, `core/runtime·planning·execution·quality·models·context·prompts·observability·catalog` 책임 분리 |
| 호환 경로 | 14_14에서 구 planner/orchestrator/reviewer/reducer wrapper를 완전 제거, 공식 경로는 planning/execution/quality |
| 공통 Runtime | 분석·매핑·그래프·시나리오·입력 추천·실행은 `PlatformRunnerAdapter → AgentRuntime → LangGraph` |
| Plan | `plan/v2`, capability→Agent 허용 검증→Skill/Tool→모델 요구사항, dependency와 선택 이유 저장 |
| 모델 관리 | `/manage/models`, OpenAI-compatible endpoint·`/v1/models` health·capability/context/지원 기능/점수 |
| 프로젝트 정책 | `auto·cost_saver·balanced·highest_quality·internal_only`, 테스터는 원시 모델 ID를 고르지 않음 |
| 모델 결정 | 하드 필터 후 정책 가중 점수, 결정론 tie-break, 선택 endpoint/model을 Tool subprocess에 실제 주입 |
| Prompt | `backend/app/prompts/` SSOT, LangChain `PromptCatalog`, version+SHA-256 |
| Agent Trace | `/manage/agents`, 후보 점수·제외 사유·선택·Plan·Skill/Tool·Artifact·Review·Reduce |
| 프라이버시 | chain-of-thought 미수집/미노출, 모델 API key SQLite/Trace 미저장, 민감 key 마스킹 |
| Context | 큰 입력 한 번 저장 후 reference 전달, dependency Artifact/필요 결과만 merge |
| 회귀 | Backend 188 passed, 6 skipped · Frontend production build PASS · Browser console error 0 |

- 브라우저 증적: `artifacts/evidence/phase14-core-agentic/browser/`.
- 상세 판독: `artifacts/evidence/phase14-core-agentic/VERIFICATION.md`.
- 상세 보고: `docs/report/20260806/14_13.md`.
- 남은 Core Gate: 실제 dependency-ready 병렬 실행, checkpoint/실패 단계 재개, 운영 Secret Provider. 구현 전 rate limit/resource lock/event ordering 계약을 먼저 확정한다.

---

## 14. 14_14 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| Core 완전 통합 | 구 `core/planner·orchestrator·reviewer·reducer` package 제거, 공식 경로는 `planning·execution·quality·runtime` |
| Import 영향도 | `backend/app` Python 150개 AST 파싱, 구 import 0건, 공식 Core import 10건 |
| 실프로젝트 | `PRJ-bfa4d679548a`, public Bank of Anthos 저장소와 Cymbal Bank 실행 환경 |
| 분석 | Frontend `AN-FE-f4ef41b8d9ec` + Backend `AN-BE-2cefcb69652c`, 상세에서 양쪽 전체 소스 트리 확인 |
| 시나리오 | `IG-fb06ccb46e61` · 고유 23건 · 입금 6/송금 6 포함 |
| 최종 실행 | `RUN-ba3206ba5256` · browser constraint와 인증 marker 기준 충족 · HITL 대기 |
| Evidence/HITL | 확대·다운로드·ZIP·Package와 누락/마스킹 확인, 최종 승인 자동 확정 금지 |
| Agent Trace | `PLAN-8b1a0424761e`, 모델 후보/제외 사유·3-step Plan·Skill·Review·Reduce |
| 회귀 | Backend 191 passed, 6 skipped · Frontend production build PASS · Browser console error 0 |

- 상세 보고: `docs/report/20260807/14_14.md`.
- 브라우저/실데이터 증적: `artifacts/evidence/phase14-core-full-integration/VERIFICATION.md`.
- 등록된 로컬 LLM endpoint가 연결되지 않아 실제 narration은 결정론 fallback이다. public/사내 LLM 실호출 비교는 사용 가능한 endpoint와 API key profile 등록 후 수행한다.
- 다음 Core Gate는 dependency-ready 병렬 실행, checkpoint 재개, 운영 Secret Provider다. Phase 포인터는 배치 수용 검증을 위해 14로 유지한다.

---

## 15. 14_15 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 최종 시나리오 | `IG-f921ecf54c13` · 21건 · unresolved 0 · 입금 6/송금 6 |
| 최종 배치 | `BAT-cc48a15c7b7d` · 안전 실행 13 · 정책 제외 8 · 기술 실패 0 |
| 기술 검증 | `TECHNICALLY_MATCHED` 13/13 · Binding missing 0 · 예상 밖 Run missing 0 |
| Evidence | 13/13 complete · Artifact SHA-256 204/204 · ZIP 13/13 |
| 브라우저 | runner/Agent Trace 13/13 `agent-browser-cli` · `agent_browser_*` 도구 영수증 |
| 외부 대상 | 내부 서버 로그 제약은 `external_network_only` / `외부 대상 관측 범위`로 표시 |
| 승인 상태 | 기술 품질 Gate 완료, 최종 Pass/Fail·품질 승인은 HITL 대기 |
| 회귀 | Backend 207 passed, 6 skipped · Frontend production build PASS |

- 상세 증적: `artifacts/evidence/phase14-quality-credibility/VERIFICATION.md`.
- 다음 Gate: 격리 계정·초기화 가능한 데이터 환경에서 destructive 8건 실행 후 사람 HITL 승인.

---

## 16. 14_16 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 브라우저 세션 수명 | 시나리오 실행은 성공·실패·예외와 무관하게 공개 실행 함수의 `finally`에서 agent-browser 세션 종료 |
| 정리 오류 | 세션 종료 자체 오류는 로그로 관측하되 원래 실행 결과·주 실패를 덮어쓰지 않음 |
| 동의 없음 | 브라우저를 열지 않은 요청은 호출자가 제공한 재사용 세션을 임의 종료하지 않음 |
| 런타임 탐색 | 기존 `discover_runtime_screens`의 `try/finally` 종료 계약 유지 |
| 증분 분석 UX | 동기화 직후·대시보드 프로젝트 카드의 변경분/영향 시나리오/다음 행동은 상세계획만 작성, 아직 미구현 |
| 회귀 | 브라우저 실행·세션 선행조건 관련 `27 passed, 1 skipped`; Backend 전체는 별도 기존 파이프라인 2건 실패 관측 |

- 계획: `docs/07.작업메모리/20260807-incremental-analysis-dashboard-plan.md`.
- 회차 보고: `docs/report/20260807/14_16.md`.
- 다음 구현 시 계획의 `SourceSnapshot`·`ChangeSet`·`ImpactSummary` 계약부터 확정하고 UI를 붙인다.

---

## 17. 14_17 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 관리 화면 헤더 | `PageShell` 내부는 공통 `content-header`·`h2`·`muted` 설명 구조 사용 |
| 대상 화면 | `/manage/models`, `/manage/agents`의 제목·설명·검색창 정렬 통일 |
| 레이아웃 | header 고정·center 스크롤 계약 유지, 문서 단위 가로 넘침 없음 |
| 검증 | Frontend production build 완료 · 로컬 Console 두 화면 error 0 관측 |

- 회차 보고: `docs/report/20260807/14_17.md`.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 18. 14_18 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 메뉴 목록 테이블 | `CommonDataTable`만 번호·열 정렬·등록/수정 일시·10건 페이징·선택·프로세스 열을 소유 |
| 화면별 금지 | 메뉴 화면에서 별도 column width·paging·수직 table scroll 속성을 만들지 않음 |
| 적용 화면 | 프로젝트·분석·시나리오 그룹·실행 이력·HITL·증적·스케줄·모델·Agent |
| 시각 계약 | 셀은 말줄임으로 숨기지 않고 줄바꿈, 테이블은 수평 overflow만 허용, CENTER가 수직 스크롤 소유 |
| 프로젝트 시간 | Project API가 `createdAt`·`updatedAt` 반환, 이름/설명/정책·저장소·journey 변경 시 `updatedAt` 갱신 |
| 프로젝트 수용 | `PRJ-453cf7c5bcb9` 생성, STEP 1~5·저장소 자동 분석·환경 Health·이름 수정·수정 시각 반영 확인 |
| 프로젝트 wizard | 넘치는 본문은 위에서 시작하고 footer 높이를 고려한 scroll padding 적용, 선택 입력이 고정 footer 아래에 가리지 않음 |
| FLOW | CENTER만 수직 스크롤, graph/inspector의 중첩 수직 scroll cap 제거, 노드 선택 후 inspector로 이동·focus |
| FLOW 접근성 | 그래프 focus 가능, 좌우 방향키·Home·End로 수평 이동 |
| 검증 | Frontend production build PASS · Project API pytest 7 passed · 실제 브라우저 정렬/200건 페이징/STEP 1~5/FLOW 확인 |

- 회차 보고: `docs/report/20260807/14_18.md`.
- 로컬 Backend는 변경된 Project timestamp 계약으로 재시작되어 `127.0.0.1:8000`에서 실행 중이다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 19. 14_19 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 공통 도구막대 | 전체·선택·조회·페이지·필터·검색·CSV·삭제·정렬을 `CommonDataTable` 한 영역에 병합 |
| AI 목록 안내 | 화면마다 반복되던 공통 AI 어시스턴트 배너 제거, 실제 AI 기능 문맥에서만 AI 표현 사용 |
| 핵심/태그 | 첫 데이터 열 강조, capability·분석 요약·핵심 상태를 짧은 색상 태그로 표시 |
| 고정 열 | 등록/수정 일시 184px, 프로세스 196px, 프로세스 버튼 가로 정렬 |
| 가변 열 | 일반 데이터 열은 공통 폭 배분, header separator 드래그로 조절·더블클릭 초기화 |
| 팝업 | 실행 증적 상세는 요약·단계·증적 탭과 고정 header/footer 사용 |
| Figma | `2762:78956` 테이블 밀도·`2471:21438` 팝업 탭 구조를 공통 컴포넌트에 반영 |
| Codex MCP | 프로젝트 `.codex/config.toml`에 next-devtools·agent-browser 변환, 두 서버 enabled 확인 |
| 검증 | Frontend production build PASS · 17 routes · 1920/1280 실제 브라우저 레이아웃 확인 |

- 회차 보고: `docs/report/20260807/14_19.md`.
- 신규 메뉴 목록은 화면별 toolbar·검색 header·열 너비·paging을 만들지 않는다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 20. 14_20 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| table/CENTER | 목록이 짧아도 공통 table shell이 footer 직전까지 채우며 화면별 높이를 두지 않음 |
| 검색 | 공통 toolbar의 돋보기·입력값은 32px 필드 안에서 한 줄 중앙 정렬 |
| 시나리오 bottom | 체크 그룹 수와 연동되는 보라색 `선택 N개 그룹 일괄 실행` 결정 CTA |
| HITL 목록 | 시나리오 한글명·자동 실행 상태·증적 상태만 우선 표시, ID·긴 설명은 drawer로 이동 |
| HITL bottom | 한 실행 선택 시 `선택 1건 증적 검토` 활성, 최종 판정은 담당자 범위 |
| 우측 상세 | 긴 제목 자연 줄바꿈, 보라색 굵은 시나리오명, 활성 탭 보라색·흰색 |
| TOP 탭 | 활성 workspace tab을 보라색 배경·흰색 텍스트로 명시 |
| 검증 | Frontend build PASS · 17 routes · 1920/1280 실제 화면 · browser error/warning 0 |

- 회차 보고: `docs/report/20260807/14_20.md`.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 21. 14_21 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 모델 선택/사용 | `model_selected`는 후보 결정일 뿐, `model_invocation_completed` 영수증이 있어야 실사용으로 집계 |
| Tool Runtime | Backend `sys.executable`로 Skill subprocess 실행, 선택 모델 endpoint/model/key 주입 |
| 호출 영수증 | Provider response ID·duration·prompt/completion/total token만 저장, prompt/response/secret 제외 |
| 시나리오 narration | 3건 단위 Qwen 호출, `llm·llm_partial·deterministic` 출처 보존 |
| Agent 화면 | 실제 호출/응답 미사용/호출 안 함/과거 확인 불가 구분 |
| Prometheus | `/metrics`에서 모델 호출·token·duration·선택 후 미호출 제공 |
| 실호출 증적 | `PLAN-QWEN-VERIFY-034803` · Qwen3.6-27B-FP8 · 3,507 token · `llm` |
| 팝업 공통화 | Figma 매핑 `Button·InputField·ButtonLink`, 고정 header/footer와 단일 목록 scroll |
| 회귀 | Backend 214 passed, 6 skipped · Frontend production build PASS |

- 회차 보고: `docs/report/20260807/14_21.md`.
- 기존 deterministic 21건은 자동 덮어쓰지 않는다. 사용자가 재생성을 선택하면 신규 호출 영수증과 출처를 확인한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 22. 14_22 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 프로젝트 상세 | `{프로젝트명} › 프로젝트 상세` 인라인 제목, 내부 ID 안내 제거, 핵심 정보 1280×720 한 화면 우선 노출 |
| 수정 STEP | 5개 STEP 직접 이동, 기존 값 사전 입력, 환경은 기존 row PATCH |
| 저장소 수정 | `repositorySetId` 기반 제자리 source/name 갱신 후 sync·분석, 같은 원본 재연결 idempotent |
| 기존 중복 | 참조 무결성을 위해 내부 set은 보존하되 URL/path identity 기준 화면 1개로 통합 |
| 실행 이력 | 시나리오 select·customerId·화면 내 실행 form 제거, 실행 시작은 시나리오 상세로 단일화 |
| 분석 이름 | 내부 ID 대신 `{프로젝트명} 분석 그룹` 표시 |
| 공통 정렬 | `CommonDataTable` 등록/수정 timestamp 최신순 기본, Backend 목록도 최신순 반환 |
| 회귀 | Repository/API 10 passed · Backend 217 passed, 6 skipped · Frontend production build PASS |

- 회차 보고: `docs/report/20260807/14_22.md`.
- 실제 DB 전환 시 timestamp DESC ORDER BY와 인덱스를 유지한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 23. 14_23 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 생성 시작 | `초안 만들기` 직후 선택 팝업을 닫고 CENTER 진행 팝업으로 즉시 전환 |
| 진행 정보 | D-009 Progress Type 1 · 경과 시간 · 분석 범위 · 생성 방식 · AI pulse 표시 |
| 대기 문구 | 코드/화면/API/입력/검증 문맥의 고정 문구 50개를 3초 주기로 순환 |
| 게이지 진실성 | 동기 API 내부 진행률은 예상값으로 명시, 서버 응답 전 92% cap, 완료 응답만 100% |
| 완료 상태 | 생성 건수·`닫기`·`테스트 시나리오로 이동`, 자동 이동 제거 |
| 오류 상태 | 오류 메시지·`닫기`·`다시 선택하기` |
| React 품질 | 생성 상태 단일화, resource-selection 병렬, 프로젝트별 모델 생성 순차, timer cleanup |
| 검증 | 50개 문구·3초 순환·진행/완료 팝업·1280×720 overflow 0 · Frontend build PASS |

- 회차 보고: `docs/report/20260807/14_23.md`.
- 실제 token/단계 진행률과 서버 취소가 필요하면 job API + SSE 계약을 별도 추가한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 24. 14_24 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 모델 역할 | general · embedding · vision · advanced · image_generation |
| 프로젝트 생성/수정 | 프로젝트 이름 다음 `모델 설정`을 둔 6 STEP, 수정은 원하는 STEP 직접 이동 |
| 선택 방식 | 기본 AI 자동 추천, 역할별 고정은 검색 가능한 공통 CENTER 팝업 사용 |
| 외부 모델 | GPT-5는 advanced/vision, GPT Image 2는 image_generation 전용; Key가 없으면 선택 불가 사유 표시 |
| Secret | API Key는 SQLite/profile/log에 저장하지 않고 현재 서버 메모리에서만 사용 |
| Agent 감사 | 후보 평가·선택·미호출·실제 호출 완료/실패와 provider request ID·token·duration 분리 |
| 실 프로젝트 | `PRJ-5c3ec8d6daa0` · Graph 62/60 · 시나리오 21건 |
| 실 브라우저 | `RUN-dd496442ce5c` · 8/8 단계 · screenshot 8 · snapshot 12 |
| 실 Vision 호출 | `PLAN-e0a3a9902810` · Qwen 1회 · 8,849 token · 화면 관측 구조화 |
| Evidence | `EVID-RUN-dd496442ce5c` · hash 16/16 · 파일 손상/유실 0 · input_profile missing으로 partial |
| 회귀 | Backend 220 passed, 6 skipped · Frontend production build PASS · Browser console error/warn 0 |

- 회차 보고: `docs/report/20260807/14_24.md`.
- 대화에 노출된 OpenAI Key는 폐기/회전한 뒤 모델 관리에서 새 Key를 입력해야 한다.
- 새 Key 입력 후 GPT-5/GPT Image 2 Health와 external provider 실제 호출 Gate를 이어서 수행한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 25. 14_25 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 최고 품질 선택 | OpenAI 프로필이 정상일 때 GPT-5 94.5점으로 Qwen 80.25점보다 우선 선택 |
| GPT-5 실행 | 1건 단위 · reasoning minimal · completion 8,192 · 전체 narration 140초 budget |
| 부분 완료 | 유효 LLM 응답을 반영하고 남은 항목만 코드·Graph 근거 규칙으로 보완, `llm_partial` 기록 |
| 라우팅 일관성 | Agent workflow 뒤 전역 기본 LLM 재호출 제거, 선택 모델과 실제 호출 모델 일치 |
| 재생성 | project+case 기준 최신 row 갱신·목록 중복 제거, 기존 ID history는 보존 |
| 생성 UX | 시작 전에 선택 모델 preview, 진행 팝업에 모델명·선택 사유, 서버 오류 메시지 보존 |
| 결과 검토 | 대기 건수 있을 때만 보라색 강조, aria-label 건수 연동, 클릭 시 `/hitl` |
| 실검증 | `PLAN-644f83ea362f` · GPT-5 성공 6회 · 46,319 tokens · 시나리오 21건 |
| 회귀 | Backend 226 passed, 6 skipped · Frontend production build PASS · Browser error/warn 0 |

- 회차 보고: `docs/report/20260807/14_25.md`.
- 외부 모델 Key는 메모리 전용이므로 Backend 재시작 후 모델 관리에서 재입력·Health Check한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 26. 14_26 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 프로젝트 장식 | 파스텔 폴더 SVG를 카드 우측 하단에 배치, 정보가 아닌 decorative asset |
| 불투명도 | 기본 16% · hover 23% · 좁은 화면 13%, 본문보다 낮은 z-index |
| 프로젝트명 | 19~22px responsive · 800 weight · navy, 장식 전까지 제목 폭 제한 |
| 인사 문구 | 프론트 규칙 데이터 50개 중 Web Crypto로 하나 선택 |
| 세션 안정성 | 사용자별 sessionStorage 보존, 화면 이동·새로고침 중 동일 문구 유지 |
| 접근성 | 폴더 alt 비움·aria-hidden·pointer event 차단 |
| 검증 | Frontend build PASS · 1280×720 overflow 0 · browser error/warn 0 |

- 회차 보고: `docs/report/20260807/14_26.md`.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 27. 14_27 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| REPORT AGENT | `wf_run_report` → `QA.RUN.REPORT_GENERATE` → `run_report/generate_run_report` |
| 입력 SSOT | 실행 이력·시나리오·BindingValidation·EvidenceManifest만 사용, AML 입력/판단 미사용 |
| Structured Output | `run-report/v1` · JSON Schema + Pydantic strict validation |
| 판정 Guardrail | `PENDING_HUMAN_REVIEW` 고정, 자동 Pass/Fail·승인 금지 |
| 저장 | `artifacts/reports/runs/{runId}/report.json|html` |
| API | `/api/runs/{runId}/report` 생성·조회, `/download?format=html|json` |
| HITL UI | 실행 리포트·기술 검증·증적 패키지 3탭, 목록 CTA `증적/리포트 검토` |
| 실검증 | `RUN-dd496442ce5c` → `RPT-dd496442ce5c` · Trace `PLAN-d38a03f65cfc` · HTML 다운로드 200 |
| 회귀 | Backend 229 passed, 6 skipped · Frontend production build PASS |

- 회차 보고: `docs/report/20260807/14_27.md`.
- Evidence `partial`과 기술 검증 0건은 원본을 임의 보정하지 않고 담당자 확인 항목으로 노출한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 29. 14_29 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 누락 근거 | 원시 코드는 JSON 감사 데이터에만 유지, UI·HTML은 사용자용 확인 대상·안내 표시 |
| 다운로드 | 실행 리포트·기술 검증·증적 패키지를 하나의 HTML에 포함 |
| 증적 내용 | Artifact 16건의 경로·크기·마스킹·해시와 대표 화면 3장을 포함 |
| 행별 SSE | 실행 직후 대기 상태를 만들고 progress·current step·result를 각 시나리오 행에 반영 |
| 결과 표현 | `관측 불가` 대신 정상 관측·확인 필요·실행 완료/검토 대기로 명확히 구분 |
| 연결 복구 | EventSource 자동 재연결 유지, 복구 중 마지막 행 상태 보존 |
| 미선택 안내 | 상세 CENTER에 큰 선택 안내·설명·방향 아이콘 표시 |
| 실검증 | `RUN-a6dd19ba5bc8` · HTML 111,322 bytes · 증적 16 · 이미지 3 · raw code 노출 0 |
| 회귀 | Backend 231 passed, 6 skipped · Frontend production build PASS · Browser error/warn 0 |

- 회차 보고: `docs/report/20260807/14_29.md`.
- 실제 신규 일괄 실행 시 사용자 승인 범위에서 대기→부분 진행→완료 SSE 수용 확인을 이어간다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 30. 14_30 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 송금 실패 원인 | 수동 송금 성공과 자동 실행 안전 정책 차단을 분리, 대상 서비스 오류로 오인시키지 않음 |
| 제출 정책 | 데이터 변경 제출은 배치 기본 제외, 건별 실행의 명시적 1회 승인으로 재검증 |
| ID 복사 | 시나리오 좌측 목록 제목을 Ctrl+클릭하면 실제 scenarioId 복사·완료 안내 |
| 실행 이력 | 시나리오 ID를 연한 파란색 링크로 표시하고 원본 시나리오로 이동 |
| 검색 필드 | 그룹·시나리오 ID·한글명·실행 ID·상태·요약·결과 변경 선택 검색 |
| 검색 규칙 | 영문 대소문자를 구분하지 않는 부분 일치 |
| AI 관측 요약 | 무슨 문제·왜 발생·어떻게 해결 3단계와 재검증 조건·담당자 전달문 표시 |
| 과거 실행 보정 | 저장된 포괄 진단 대신 불변 실행 증적에서 원인을 다시 계산 |
| 회귀 | Backend 232 passed, 6 skipped · Frontend production build PASS · 실제 브라우저 수용 확인 |

- 회차 보고: `docs/report/20260807/14_30.md`.
- 잔액이 있는 계정에서 데이터 변경 1회 실행을 명시 승인해 성공 안내·잔액·거래 행을 재검증한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 31. 14_31 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 공통 호스트 | 앱 전역 단일 토스트, 최대 3개·자동 닫힘·수동 닫기·접근성 상태 알림 |
| 상태 갱신 | 같은 작업 ID로 시작 → 완료/실패를 같은 자리에서 갱신 |
| 시나리오 일괄 실행 | 클릭 즉시 그룹명 포함 준비 알림, 실제 Run 생성 후 건수 포함 시작 알림 |
| 배치 관리 | 실행·일시정지·재개·취소 요청 시작·완료·실패 알림 |
| CSV | 모든 공통 테이블의 가져오기·내보내기에 즉시 토스트 적용 |
| 다운로드 | HITL 리포트·JSON·증적 ZIP·개별 증적·Evidence Package에 공통 피드백 적용 |
| 문구 원칙 | 요청 접수와 처리 완료를 구분하며 시작 토스트를 성공으로 표현하지 않음 |
| 회귀 | Frontend production build PASS · 실제 브라우저 CSV/일괄 실행/리포트 수용 확인 |

- 회차 보고: `docs/report/20260807/14_31.md`.
- 신규 대량·다운로드 기능은 화면별 메시지를 만들지 않고 `showActionToast` 공통 계약을 사용한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 33. 14_33 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 외부 모델 Secret | 운영체제 Keychain에 영속 저장, SQLite·API 응답·화면·로그에 원문 미노출 |
| 재시작 복원 | 모델 ID로 Keychain 값을 복원해 `hasApiKey=true` 유지 |
| 상태 정확성 | 외부 모델 Key가 없으면 과거 정상 상태를 지우고 `미확인 · API Key 등록 필요` 표시 |
| 수정 UX | `API Key 안전 저장됨` 배지, 빈 값 수정은 기존 Key 유지, 원문 재표시 금지 |
| GPT-5 실검증 | `MODEL-3d19a61a8150` · 저장 200 · OpenAI models 200 · 재시작 후 Health `up` |
| 보안 검증 | Keychain 164자 · SQLite 원문 없음 · 응답 원문 없음 |
| 회귀 | Backend 234 passed, 6 skipped · Frontend production build PASS · Browser 저장/재시작 확인 |

- 회차 보고: `docs/report/20260807/14_33.md`.
- 외부에 노출된 운영 Key는 교체 후 모델 수정 화면에서 재등록한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 34. 14_34 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 리포트 본문 | 진행률·관측 분포·A→API→B 여정·기술 검증·핵심 화면 증적 중심, 원시 JSON/로그 본문 금지 |
| Progress | Figma Progress Kit Type 1의 상태 원·수치·8px 막대 패턴을 인쇄 가능한 CSS로 변환 |
| 화면 증적 | Evidence Package 대표 화면 3장 + Run 단계별 전체 캡처 12/12장 포함 |
| 파일 증적 | 16개 artifact는 파일명·크기·마스킹·SHA-256 인벤토리로 누락 없이 표시 |
| 인쇄/PDF | `pre`·내부 스크롤 없이 page-break·썸네일·대표 화면 구조 사용 |
| 캐릭터 | 대시보드 QA 로봇을 리포트 헤더 도우미로 재사용 |
| 판정 | 기술 상태와 `PENDING_HUMAN_REVIEW` 분리, 자동 Pass/Fail·승인 생성 금지 |
| 실검증 | `RUN-576cd6cf4076` · 이미지 16 · 캡처 12 · 인벤토리 16 · raw log 0 · 정상 다운로드 SHA 일치 |
| 회귀 | Report Agent 4 passed · Backend 234 passed, 6 skipped · HITL 브라우저 다운로드 확인 |

- 회차 보고: `docs/report/20260807/14_34.md`.
- HTML은 검토용 시각 요약이며 JSON/증적 ZIP은 원본 감사 자료로 유지한다.
- Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 35. 14_35 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 증적 건수 | 패키지 파일 16건과 시각 증적 15장(대표 3 + 실행 단계 12)을 구분해 표시 |
| 파일 무결성 | 실제 파일 누락만 `partial`, 실행 의미상 미관측 항목은 별도 제약·안내로 분리 |
| 연쇄 증상 | 제출 전 중단으로 생긴 성공 문구·목록·값 미관측은 독립 장애가 아니라 한 원인의 영향으로 축약 |
| 입력 증적 | 실제 Run 입력과 사용자의 수정 입력을 Evidence Package input profile에 연결 |
| 제출 선행조건 | native form 유효성 검사 후 불가능한 입력은 POST 전에 한 가지 원인·해결 방법으로 중단 |
| 수치 관측 | 기대 변화는 센트 단위 정확 비교, 0.00→0.00을 -0.01과 일치 처리하지 않음 |
| 이미지 확대 | `data:image` 새 페이지 이동 금지, 리포트 내부 dialog에서 원본 크기 확인 |
| 근본 원인 | 잔액 0.00에서 min 0.01/max 0.00 송금 불가; 테스트 데이터 선행조건 부족으로 진단 |
| 실제 재검증 | 입금 1.00 후 송금 0.01, 1.00→0.99·새 거래·HTTP 200·missingData 0 기술 관측 |
| 회귀 | Backend 238 passed, 6 skipped · Frontend production build PASS · Browser 확대/HITL 확인 |

- 회차 보고: `docs/report/20260807/14_35.md`.
- 샌드박스 검증으로 입금 1.00과 송금 0.01을 실제 생성했으며 검증 직후 계좌 잔액은 0.99다.
- 기술 관측과 최종 HITL 승인을 분리하며, Phase 포인터는 사용자 화면별 수용 검증이 계속되는 동안 14로 유지한다.

---

## 36. 14_36 최신 구현 계약

| 영역 | 현재 계약 |
|---|---|
| 원격 main 교체 | 기존 `37555efe` 소스를 빈 트리 `972d7359`로 교체한 뒤 현재 워크스페이스 스냅샷을 신규 기준으로 푸시 |
| 문서 진입점 | `docs/index.md`가 개발 지침과 메뉴별 기능·Workflow 지침을 함께 관리 |
| 메뉴 문서 | `docs/08.메뉴와워크플로우/`에 9개 좌측 메뉴의 Route·API·Workflow·HITL 경계 기록 |
| Agentic Core | `PlatformRunnerAdapter → AgentRuntime → LangGraph route→plan→execute→review→reduce→response` 단일 진입 |
| 공식 package | `runtime·planning·execution·quality`; 제거된 구 wrapper package 재도입 금지 |
| 모델 Secret | profile=SQLite, API Key 원문=운영체제 Keychain, API·Trace·SQLite 원문 미노출 |
| README | 프로젝트 설명·설치·기동·설정·메뉴 기능·검증·안전 원칙을 현재 코드 기준으로 전면 정비 |
| 데모 시나리오 | `docs/09.데모영상/AI해커톤_5분_데모_시나리오.md` — 30초 오프닝, 전 메뉴, 77초 핵심 시나리오, 15초 ROI/감사 |
| Git 제외 | `artifacts/**` 런타임 증적 1.3만 파일은 로컬 보존, 소스 스냅샷에는 미포함 |
| 회귀 | Backend 238 passed, 6 skipped · FE analyzer 9 passed, 1 skipped · Frontend production build PASS |

- 메뉴 기능·Route·API·Workflow를 바꾸면 `docs/08.메뉴와워크플로우/`를 같은 변경에서 갱신한다.
- HITL 화면은 현재 리포트·기술 검증·증적 검토를 제공하며, 승인/반려 저장은 Phase 15 계약과 함께 추가한다.
- Phase 14 완료 보고는 만들지 않았고 사용자 화면별 수용 검증 포인터를 유지한다.
