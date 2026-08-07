# Phase 09 — 브라우저실행 완료 보고

## 1. 기본 정보

- Phase: 09.브라우저실행
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 관련 이전 Phase: 06 Scenario DSL · 08 입력값추천
- 회차 요약: `docs/report/20260804/09_1.md` (Console UX 선행) · `09_2.md` (Gate)

## 2. 구현 요약

Scenario DSL과 Input을 agent-browser CLI Adapter로 실행해
A 화면 fill → Search click → Backend 호출 → B 화면(`/customers/:id`)까지 관통한다.

- Skill Hub `browser_execute` + Workflow `wf_browser_execute`
- Run lifecycle: QUEUED → RUNNING → WAITING_FOR_REVIEW / CANCELLED
- 사용자 consent 필수 · 미동의 시 실행 차단
- 입력 직후·결과 화면 Screenshot ≥2 · DOM snapshot 보존
- Test Run Header는 FE localStorage → fetch 주입 (CORS-safe: 기본 `X-Test-Run-ID`)
- Console `/runs`: consent · Progress Type 1/4 · step 관측 요약
- Right panel 기본 접힘
- AI는 관측만 · Pass/Fail 단정 문구 없음 (HITL 대기)

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/skills/browser_execute/` | Skill + execute_run.py Adapter |
| `backend/app/workflow_definitions/wf_browser_execute.yml` | Workflow Hub |
| `backend/app/capability_definitions/capabilities.yml` | EXECUTE / BROWSER_EXECUTE |
| `backend/app/api/scenario_runs.py` | Run REST |
| `backend/app/services/run_*.py` | Run 모델·서비스 |
| `docs/03.계약과예시/schemas/run.schema.json` | Run Schema |
| `frontend/app/runs/` · `RunsWorkbench.tsx` | 실행 UI |
| `frontend/components/RightPanelContext.tsx` | 기본 접힘 |
| `sample-targets/customer-portal-fe` · `customer-service-be` | tracing header · CORS |
| `backend/tests/test_browser_execute_phase09.py` | Gate 테스트 |
| `artifacts/evidence/phase09-browser/` | 스크린샷·snapshot |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| 실행 엔진 | agent-browser CLI (MCP 동등 명령) | Playwright Test Runner | Phase 강제 · D-012 Skill script |
| Header 주입 | localStorage → FE fetch | browser set-headers | set-headers가 CORS/A→B 깨짐 |
| 성공 기술 상태 | WAITING_FOR_REVIEW | AUTO_PASSED | HITL · Pass 단정 금지 |
| URL 대기 | get url poll | wait --url | wait --url 데몬 hang |
| Locator | data-testid CSS 우선 | @ref only | React re-render stale ref |

## 5. API·Schema 변경

- 추가 API:
  - `POST/GET /api/scenarios/{id}/runs`
  - `GET /api/runs` · `GET /api/runs/{runId}` · `GET .../steps`
  - `POST /api/runs/{runId}/cancel`
- JSON Schema: `run.schema.json` (packages sync)
- Hub: workflows 9 · skills 9 · capabilities 12

## 6. 실행한 명령

```bash
cd backend && .venv/bin/python -m pytest tests/test_browser_execute_phase09.py -q
cd backend && .venv/bin/python -m pytest tests/ -q
# live A→B (Sample FE :5173 · BE :8080)
# execute_scenario → WAITING_FOR_REVIEW · missing_data=[]
```

## 7. 테스트 결과

| 테스트 영역 | 명령 | 결과 | 비고 |
|---|---|---|---|
| Phase 09 | `pytest tests/test_browser_execute_phase09.py -q` | 6 passed | consent·Hub·cancel·schema |
| Full suite | `pytest tests/ -q` | 63 passed, 1 skipped | |
| Live A→B | execute_scenario CUS-1001 | WAITING_FOR_REVIEW | URL `/customers/CUS-1001` · Kim Pilot |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| A 화면 입력 이벤트 | PASS | fill `[data-testid=customer-id-input]` · `01-after-input.png` |
| 조회 버튼 → Backend | PASS | click submit · BE 응답 후 detail |
| B 화면 도달 | PASS | `/customers/CUS-1001` · `02-result.png` |
| Test Run Header | PASS | localStorage `X-Test-Run-ID` → FE fetch |
| Step 결과 저장 | PASS | run steps + observationSummary |
| 실패 시 screenshot/snapshot | PASS | consent/cancel · missing_data 경로 |
| Screenshot ≥2 | PASS | `artifacts/evidence/phase09-browser/` |
| Pass/Fail 단정 없음 | PASS | status=`WAITING_FOR_REVIEW` · Console HITL 톤 |

## 9. 보안·개인정보 검토

- Secret/Token 미저장
- Synthetic customer only (CUS-1001)
- Consent 없이 브라우저 실행 차단
- destructive crawl 기본 차단

## 10. 알려진 제약

- 추가 tracing 헤더(`X-Scenario-ID` 등)는 sample BE CORS 재기동 후에만 동시 주입 권장
- agent-browser `wait --url`는 hang 이슈로 poll로 대체
- In-memory Run store는 프로세스 reload 시 초기화
- Backend 로그 수집·Binding 비교·고객 HITL UI는 후속 Phase

## 11. 다음 Phase 전달사항

- Phase **10.Backend추적**: Run Header로 BE 로그/요청 추적 연결
- Run API: `/api/scenarios/{id}/runs` · `/api/runs/{id}`
- Evidence: `artifacts/evidence/runs/` · `phase09-browser/`
- Console `/runs` consent 흐름 유지

## 12. AGENTS.md 변경

- 현재 Phase 포인터 → **10.Backend추적**
