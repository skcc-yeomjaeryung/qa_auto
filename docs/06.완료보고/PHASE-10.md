# Phase 10 — Backend추적 완료 보고

## 1. 기본 정보

- Phase: 10.Backend추적
- 작업일: 2026-08-05
- 담당 Agent/개발자: Cursor Agent
- 기준 Commit: `37555ef` (작업 시점 HEAD · 보고 후 커밋 별도)
- 관련 이전 Phase: 03 Backend분석 · 09 브라우저실행
- 회차 요약: `docs/report/20260805/10_26.md`

## 2. 구현 요약

동일 Test Run ID로 Browser 관측과 Spring Backend structured log를 연결한다.

- Correlation headers: `X-Test-Run-ID` · `X-Scenario-ID` · `X-Test-Case-ID` · `X-Input-Profile-ID`
- Browser 실행 시 localStorage에 전체 헤더 시드 · evidence에서 Secret 헤더 마스킹
- Control Plane ingest: `POST /api/test-telemetry/backend`
- Timeline merge: `GET /api/runs/{id}/timeline` · events: `GET .../backend-events`
- Adapter 분리: memory store · file JSONL · http_ingest · otel stub
- 마스킹/truncation · requestSequence · missing log → partial evidence
- 외부 대상: `POST .../backend-trace/external` → network-only 제약 표시
- Sample Spring: `sample-targets/spring-telemetry-demo` (Filter · Interceptor · MDC · ingest)
- Run 상세 UI에 관통 타임라인 + 마스킹 필드 표시
- AI는 관측만 · Pass/Fail 단정 없음

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `packages/contracts/schemas/backend_telemetry.schema.json` | Telemetry 계약 |
| `backend/app/schemas/telemetry.py` | Pydantic 모델 |
| `backend/app/services/telemetry/*` | masking · adapters · service |
| `backend/app/api/telemetry.py` | ingest · timeline · events API |
| `backend/app/services/repository_store.py` | event 저장 · sequence |
| `backend/app/services/run_models.py` · `run_service.py` | trace 필드 · header · await |
| `backend/app/skills/browser_execute/script/execute_run.py` | 헤더 시드 · sanitize |
| `sample-targets/spring-telemetry-demo/` | Spring Filter/MDC/ingest |
| `frontend/components/RunTraceTimeline.tsx` · `runs/[runId]/page.tsx` | Timeline UI |
| `backend/tests/test_backend_trace_phase10.py` | Gate 테스트 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| Ingest 경로 | HTTP POST to Control Plane | 파일만 | Pilot 단순 · API Gate 명시 |
| OTel | stub adapter | 실 OTLP | 분산 tracing 제외 범위 |
| Header 주입 | localStorage 시드 유지 | browser set-headers | CORS 안전 (Phase 09 결정) |
| 로그 대기 | short poll + partial | 무한 대기 | Gate 11 |
| Spring 샘플 | 독립 sample-target | 플랫폼 내장 | 대상/플랫폼 분리 |

## 5. API·Schema 변경

- 추가 API:
  - `POST /api/test-telemetry/backend`
  - `GET /api/runs/{runId}/timeline`
  - `GET /api/runs/{runId}/backend-events`
  - `POST /api/runs/{runId}/backend-trace/external`
- JSON Schema: `backend_telemetry.schema.json`
- Run 모델 additive: `backendTraceStatus` · `partialEvidence` · `testCaseId` · `inputProfileId`

## 6. 실행한 명령

```bash
cd backend && .venv/bin/pytest tests/test_backend_trace_phase10.py -q
# 10 passed

cd backend && .venv/bin/pytest tests/test_browser_execute_phase09.py -q
# 5 passed, 1 skipped

export JAVA_HOME=/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home
cd sample-targets/spring-telemetry-demo && mvn -q -DskipTests package
# jar 생성 확인
```

## 7. 테스트 결과

| 테스트 영역 | 명령 | 결과 | 비고 |
|---|---|---|---|
| Unit/API | `pytest tests/test_backend_trace_phase10.py` | 10 passed | masking·seq·partial·isolation |
| Regression | `pytest tests/test_browser_execute_phase09.py` | 5 passed · 1 skipped | |
| Sample build | `mvn -DskipTests package` | jar OK | 런타임 smoke는 수동 |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| Browser Request와 Backend Log가 동일 Run ID로 연결 | PASS (관측) | ingest + timeline · `test_ingest_and_backend_events_api` |
| Backend Request/Response DTO 확인 | PASS (관측) | events API payload · masking |
| HTTP 상태·처리시간 기록 | PASS (관측) | `status` · `durationMs` |
| Secret/PII 마스킹 | PASS (관측) | `test_request_response_masking_and_truncation` |
| 동시 실행 로그 미혼선 | PASS (관측) | `test_concurrent_run_isolation` |
| 로그 누락 시 partial evidence | PASS (관측) | `test_missing_backend_log_timeout_partial` |

> HITL Pass/배포 확정 아님. 기술 Gate 관측 기준.

## 9. 보안·개인정보 검토

- Secret 노출 여부: Authorization/Cookie/Token/Password 마스킹
- PII: 허용 필드만 수집 · truncation
- 로그: structured JSON · MDC cleanup (Spring Filter finally)
- 미해결 위험: 대상 FE가 localStorage 헤더를 실제 fetch에 붙이지 않으면 Backend 연결 불가 → partial

## 10. 알려진 제약

- OTel 실수출 없음 (stub)
- 외부 수정 불가 BE는 network-only 제약 플래그로 표시
- Spring 샘플 기동·실호출 smoke는 로컬 JAVA_HOME 필요
- 분산 마이크로서비스 전체 tracing 제외

## 11. 다음 Phase 전달사항

- Phase: **11.바인딩검증**
- 입력: timeline의 Backend Response DTO + Browser DOM/screenshot
- API: `/api/runs/{id}/timeline` · `/api/runs/{id}/backend-events`
- 주의: partial evidence면 바인딩 비교도 missing_data 가능
- 미해결: Network HAR 정식 수집은 Phase 12와 정렬

## 12. 문서 변경

- `docs/index.md` · `AGENTS.md` 포인터 → 11
- `docs/continue/NEXT.md` 갱신
- `docs/report/20260805/10_26.md`
