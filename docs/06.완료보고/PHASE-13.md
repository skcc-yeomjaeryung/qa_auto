# PHASE-13 완료 보고 — 건별 시나리오 테스트 UX

## 1. 기본 정보

- Phase: **13.건별테스트**
- 작업일: 2026-08-05
- 담당 Agent/개발자: Cursor Agent (사용자 지시 기반)
- 기준 Branch: `main` (working tree)
- 기준 Commit: `37555ef` 이후 미커밋 작업 트리
- 관련 이전 Phase: 08(입력값추천) · 09(브라우저실행) · 10(Backend추적) · 11(바인딩검증) · 12(증적수집)

## 2. 구현 요약

시나리오 1건을 골라 **추천값 확인 → 실행 → 결과·증적 확인 → 승인 검토 이동**까지
한 화면에서 마치도록 건별 테스트 콘솔을 완성했다.

- 진입 시 편집 폼을 강제하지 않고, 확인이 필요한 항목만 강조한다. 기본 CTA는 `추천값으로 실행`이다.
- 코드 근거가 없어 비어 있던 입력은 필드명·타입·제약 기반 **자동 생성값(inferred)** 으로 바인딩하고,
  화면에서 「자동 생성값 N건 · 수정 가능」으로 구분 표시한다. 형식 제약을 만족할 수 없으면 `missing_data`로 남긴다.
- 실행 중에는 Progress Type 4로 단계 진행을 보여주고, 실행 후에는 기술 상태와 HITL 대기를 분리해 표시한다.
  실행 시각은 `yyyy-mm-dd hh:mm:ss`로 출력한다.
- 실행기(agent-browser)가 **DOM을 탐색해 입력을 직접 바인딩**한다. 접근성 이름이 없는 입력도
  DOM 순서·마스킹(●●●) 관측으로 계정 입력을 판별하고, 환경에 등록한 연결 계정으로 로그인 게이트를 통과한다.
- 증적은 화면 진입 · 입력 직후(섬밋) · 결과 화면을 최소 3장 남기고, 스크린샷은 클릭하면 팝업(라이트박스)으로 확대된다.
- 프로젝트 개발환경 연결에 **연결 URL · 연결 BROWSER · 연결 ID · 연결 PASSWORD** 를 필수로 받는다.
  비밀번호는 API 응답·카탈로그에 노출하지 않고 별도 secret 저장소에만 둔다(`hasLoginSecret`만 노출).
- 플로우 화면은 **플로우 그룹 → 시나리오 → 단계 흐름** 3단 테이블로 정리하고, 다른 화면과 같은
  체크박스·선택 삭제·화면 내 검색·실행 시각 컬럼을 갖췄다.
- 전역 검색 입력을 제거하고, 각 화면 제목 오른쪽에 화면 속성 기준 검색을 붙였다.

또한 바이블 Phase 05 계약과 어긋나 있던 Interaction Graph 노드 체인을 복원했다
(`screen → input → event → validation → frontend_api_call → backend_endpoint → request_dto/response_dto → service → binding → screen(B)`).
FE 분석기가 이미 근거와 함께 뽑아둔 inputs/events/validations/routeTransitions/bindings를 발명 없이 노드화했다.

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/skills/browser_execute/script/execute_run.py` | DOM 컨트롤 파싱(이름 없는 입력 포함) · 로그인 게이트 · 입력 자동 바인딩 · 섬밋/결과 스크린샷 · secret 마스킹 |
| `backend/app/skills/input_recommend/script/recommend.py` | 필드명·타입 기반 값 합성(`synthesize_value`) · PII 마스킹 일원화 · 추천 ID에 scenarioId 포함(덮어쓰기 버그 수정) |
| `backend/app/skills/interaction_graph/script/compose_graph.py` | Phase 05 노드 체인 복원(input·event·validation·service·route_transition·binding) · 라우트 파라미터 매칭 교정 |
| `backend/app/skills/scenario_dsl/script/generate_dsl.py` | 중복 시나리오 결정론적 제거(서명 기반) |
| `backend/app/services/scenario_service.py` | 중복 시나리오 LLM 검토(규칙 검증 통과분만 제거) |
| `backend/app/services/run_service.py` | 환경 연결(브라우저·계정) 실행기 전달 · 실행 요약(LLM/결정론) 생성 |
| `backend/app/services/run_preview_service.py` | 미기재 입력 자동 생성값 바인딩 · 민감 필드 표시 마스킹 |
| `backend/app/services/environment_models.py` · `repository_store.py` | `browser`·`loginId`·`loginPassword`(별도 secret 저장) · Cymbal 프리셋 |
| `backend/app/services/console_service.py` | 플로우 런타임의 내부 오류 문구 위생 처리 |
| `backend/app/prompts/run/*.md` · `backend/app/prompts/scenario/dedupe_scenarios_system.md` | DOM 입력 바인딩 · 실행 요약 · 중복 제거 시스템 프롬프트 |
| `frontend/components/ScenarioRunConsole.tsx` | 직전 실행 결과 자동 표시 · 자동 생성값 표시 · 실행 시각·실행 요약 |
| `frontend/components/flow/FlowListWorkbench.tsx` | 플로우 그룹 → 시나리오 → 흐름 3단 · 체크박스·선택 삭제·검색·시각 |
| `frontend/components/flow/ScenarioFlowBoard.tsx` | 단계 카드(캡쳐·입력값/결과·1시 방향 재처리) · 실행 전용 단계(바인딩·섬밋) 표시 |
| `frontend/components/AnalysisWorkbench.tsx` | 저장소 분석 전체 건수 평면 테이블 + 상세(소스 탐색) 분리 |
| `frontend/components/ProjectsWorkbench.tsx` | 연결 URL/BROWSER/ID/PASSWORD 필수 입력 · 환경 상세 표시 |
| `frontend/components/{EvidenceGallery,ImageLightbox,ScreenSearch}.tsx` | 스크린샷 팝업 확대 · 화면별 검색 공통 컴포넌트 |
| `frontend/lib/{datetime,evidenceLabels,scenarioGuide}.ts` | `yyyy-mm-dd hh:mm:ss` 공통 포맷 · 증적 한글 라벨 · 흐름 노드 생성 |
| `packages/contracts/schemas/*` · `docs/03.계약과예시/schemas/scenario_dsl.schema.json` | `run_preview`(inferred/synthesized) · `execution_environment`(browser/loginId/hasLoginSecret) · DSL `assert_visible`/`assert_text` |
| `frontend/e2e/{flow-canvas,interactive-run}.spec.ts` | 3단 플로우 탐색 · 입력 없는 케이스 접근성 검증 |
| `backend/tests/*` | 환경 프리셋·그래프 체인·시나리오 서비스ID·저장소 세트 ID 기준 정정 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| 근거 없는 입력 처리 | 필드명·타입·제약 기반 **결정론 합성** 후 `inferred` 표시 | LLM이 값 생성 | 재현성 확보 · 환각 방지. 테스트 도구는 값이 없으면 진행 자체가 막힌다 |
| 이름 없는 DOM 입력 | DOM **순서 + 마스킹 관측**으로 계정 입력 판별 | 이름만으로 매칭(미바인딩) | Cymbal/BoA 로그인 입력은 접근성 이름이 없다. 관측 근거만 사용 |
| 연결 비밀번호 저장 | 별도 secret KV(`platform_env_secrets_v1`) · 응답은 `hasLoginSecret`만 | 환경 레코드에 함께 저장 | Secret 미노출 Guardrail 준수(실행 시점에만 조회) |
| 중복 시나리오 제거 | 서명 기반 결정론 제거 + LLM 검토(규칙 재검증) | LLM 단독 판단 | 커버리지 손실 방지. LLM 제안은 규칙 통과분만 반영 |
| 플로우 화면 구조 | 그룹 → 시나리오 → 흐름 3단 테이블 | 단일 목록 + 무한 스크롤 | 스크롤 없이 전체 건수 파악 · 타 화면과 동일 공통 컴포넌트 |
| 그래프 노드 체인 | Phase 05 문서 체인 복원(분석기 산출물 그대로) | 단순 5종 유지 | 바이블 SSOT 계약. binding 노드가 없어 바인딩 시나리오가 생성되지 않던 문제도 함께 해소 |

## 5. API·Schema 변경

- 추가/변경 API
  - `POST/PATCH /api/projects/{id}/environments` — `browser` · `loginId` · `loginPassword`(응답 제외) 수용, 응답에 `hasLoginSecret`
  - `POST /api/scenarios/{id}/runs` — 실행 시 환경 연결 정보(브라우저·계정)를 실행기에 전달
  - `GET /api/runs/{id}` — `result.runNarrative` · `result.inputBindings` · `result.submittedScreenshot` · `result.resultScreenshot` 관측 재료 추가
- DB Migration: 없음 (SQLite KV — 환경 secret 전용 키 추가)
- JSON Schema
  - `run_preview.schema.json` — `confidence: inferred`, `synthesized`, `inferredFieldCount`
  - `execution_environment.schema.json` — `browser`, `loginId`, `hasLoginSecret`
  - `scenario_dsl.schema.json` — `assert_visible`, `assert_text` (실행기가 이미 수행하던 동작의 계약 반영)
- 호환성 영향: 추가 필드 중심(additive). 기존 실행 결과는 신규 필드가 비어도 화면이 동작한다.

## 6. 실행한 명령

```bash
# Backend
cd backend && .venv/bin/pytest -q

# Frontend
cd frontend && npx tsc --noEmit
cd frontend && npm run build           # NEXT_DIST_DIR=.next-build (dev 캐시 분리)
cd frontend && npx playwright test --reporter=line

# 실측 실행 (파일럿 샌드박스)
curl -s -X POST http://127.0.0.1:8000/api/projects/PRJ-ca98a9a3c742/environments \
  -H 'X-User-Id: TEST' -H 'Content-Type: application/json' \
  -d '{"name":"Pilot Sandbox","frontendBaseUrl":"https://cymbal-bank.fsi.cymbal.dev","browser":"chrome","loginId":"testuser","loginPassword":"***"}'
curl -s -X POST http://127.0.0.1:8000/api/scenarios/SCN-consent-ui-001-68b9d567/runs \
  -H 'X-User-Id: TEST' -H 'Content-Type: application/json' \
  -d '{"mode":"interactive","consent":true,"environmentId":"ENV-0b4ae3f30586"}'
```

## 7. 테스트 결과

| 테스트 영역 | 명령 | 결과 | 비고 |
|---|---|---|---|
| Unit·Integration | `.venv/bin/pytest -q` | 135 passed · 6 skipped | skip = 로컬 sample 저장소/원격 clone 의존 |
| Typecheck | `npx tsc --noEmit` | 통과 | — |
| Build | `npm run build` | 통과 | dev 서버 캐시와 분리(`.next-build`) |
| E2E | `npx playwright test` | 17 passed | 3단 플로우 탐색·접근성 케이스 반영 후 전체 통과 |
| Contract | pytest 내 JSON Schema 검증 | 통과 | interaction_graph · scenario_dsl · run_preview |

수정한 실패 테스트와 원인:

- `test_environments_phase1::test_environment_presets_include_cymbal` — 프리셋 연결 URL이 사용자 지정 origin으로 바뀜. 진입 화면(`/home`)은 health path로 분리하고 기대값 정정.
- `test_interaction_graph_phase05::test_compose_graph_from_fixtures_schema` — 그래프 노드 체인 누락(코드가 SSOT와 불일치). 코드를 문서 계약에 맞게 복원하고, 테스트의 하드코딩 노드 id는 라우트 기반 조회로 교체.
- `test_scenario_chain_phase06::test_generate_dsl_schema` — serviceId는 그래프 관측에서 파생된다. 인자 동일성 단정 대신 전 시나리오 스키마 검증으로 교체.
- `test_input_recommend_phase08::test_pipeline_includes_recommend` — 같은 계약을 공유하는 두 시나리오가 동일 `recommendationId`를 만들어 뒤 저장이 앞을 덮었다. 추천 ID 재료에 scenarioId 추가.

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| 추천값으로 3클릭 이내 실행 시작 | PASS(관측) | `run-with-recommended` 단일 CTA · e2e `interactive-run.spec.ts:26` |
| 전체 입력 폼 강제 없음 | PASS(관측) | `toggle-input-edit` 기본 접힘 · 동 e2e |
| 불확실 항목만 요청 | PASS(관측) | `uncertain-items` · 자동 생성값/미해결 구분 표시 |
| 실행 상태·실패 원인 확인 | PASS(관측) | Progress Type 4 · 실패 단계 패널 · 단계별 관측 요약 |
| Evidence·HITL 이동 | PASS(관측) | `현재 증적` 갤러리(팝업 확대) · `HITL 검증으로 이동` |
| 재실행 version mismatch 방지 | PASS(관측) | stale 409 처리 · 이전 입력 재사용 체크박스 |
| Figma Progress Kit(Type 4/1) 표시 | PASS(관측) | `run-progress-type4` · `Complete ≠ HITL Pass` 문구 |
| 입력 섬밋·결과 스크린샷 증적 | PASS(관측) | RUN-c967bb409bfd: `02-S1-login-submitted.png` · `06-result.png` |
| DOM 탐색 + 판단으로 입력 직접 바인딩 | PASS(관측) | 동 실행 `inputBindings` 4건(연결 계정 근거 기록) |
| 실행 데이터·결과 요약 출력 | PASS(관측) | `runNarrative`(LLM 미구성 시 결정론 요약) |

Pass/Fail·배포 확정은 담당자(개발PL·QA·고객)가 승인 검토에서 수행한다. 위 표는 기술 관측 결과다.

## 9. 보안·개인정보 검토

- Secret 노출: 연결 비밀번호는 환경 API 응답·카탈로그·실행 결과에서 제외(`mask_secret_values`). 화면에는 `등록됨(***)`만 표시.
- PII 마스킹: password/ssn 등 민감 필드는 표시값 `***`, 실행에만 실제 합성값 사용.
- 로그: 내부 traceback·파일시스템 경로가 사용자 화면에 남지 않도록 런타임 오류 문구를 위생 처리.
- 권한: 프로젝트·환경 변경은 `X-User-Id` 필요.
- 미해결 위험: 파일럿 샌드박스(Bank of Anthos 데모) 공개 계정이 프리셋에 하드코딩되어 있다. 실고객 환경에는 그대로 쓰지 않는다.

## 10. 알려진 제약

- LLM endpoint 미구성 환경에서는 실행 요약·DOM 바인딩 판단이 **결정론 폴백**으로 동작한다(모드 표시: `deterministic`).
- `/consent` 등 OAuth 성격 경로는 샌드박스가 로그인 화면으로 되돌리는 경우가 있어, 결과 화면 관측이 로그인 화면일 수 있다. 관측값 그대로 보고한다.
- 그래프 노드 체인 복원으로 노드 수가 늘었다. 대형 저장소에서는 노드 상한(입력/이벤트/전이 각 40~60)에서 잘린다.
- 배치 스케줄·HITL 최종 승인은 이 Phase 범위가 아니다(14·15).

## 11. 다음 Phase 전달사항

- 입력 계약: `POST /api/scenarios/{id}/runs` (`mode`, `consent`, `environmentId`, `overrides`, `reuseFromRunId`)
- 사용할 API: `GET /api/runs/{id}` (`result.inputBindings`·`runNarrative`·스크린샷 경로) · `GET /api/runs/{id}/evidence`
- 주의할 제약: 실행 전 프로젝트에 **연결 URL·BROWSER·ID·PASSWORD** 가 등록된 환경이 있어야 로그인 게이트를 통과한다.
- 미해결 항목: 배치(14) 진행 시 그룹 단위 취소·동시 실행 상한, LLM endpoint 구성 시 요약/바인딩 품질 재관측.

## 12. 문서 변경

- `AGENTS.md`: 변경 없음 (Phase 포인터는 `docs/index.md`·`docs/continue/NEXT.md`에서 갱신)
- Architecture: 변경 없음
- ADR: 신규 ADR 없음 (기존 D-006·D-009 정책 유지)
- 운영 문서: `docs/03.계약과예시/schemas/scenario_dsl.schema.json` 동기화 · `docs/report/20260805/13_4.md` 회차 요약
