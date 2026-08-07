# Phase 02 — Frontend분석 완료 보고 (SDD Skill Hub 재편)

> **재구현 (2026-08-04):** 구 `workers/`·`apps/control-plane` Analysis API는 D-012 backend 폐기와 함께 무효.  
> 본 보고는 **01 Gate 이후** Skill Hub `frontend_analyze` + `backend/workers/frontend-analyzer` 재편 결과다.

## 1. 기본 정보

- Phase: 02.Frontend분석
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 기준 Branch: main
- 기준 Commit: 37555ef (작업 시점 HEAD; 산출물은 working tree)
- 관련 이전 Phase: 01.저장소연결 (`PHASE-01.md`, Gate PASS)
- 회차 요약: `docs/report/20260804/02_3.md`
- 핸드오프: `docs/continue/NEXT.md`

## 2. 구현 요약

- Capability `QA.CODE.FRONTEND_ANALYZE` · Skill `frontend_analyze` · Workflow `wf_frontend_analyze`를 교보재 few-shot 포맷으로 Hub에 등록했다.
- AST 분석 본체는 `backend/workers/frontend-analyzer` (ts-morph)에 두고, Skill script가 CLI로 호출한다.
- API `POST /api/analyses/frontend` 는 services에서 workspace/pin 메타만 해석한 뒤 **Hub Workflow** (`wf_frontend_analyze`)를 실행한다 (services에 AST 우회 없음).
- 산출물은 `artifacts/analysis/AN-FE-*/frontend.json` (`frontend-analysis/v1`) + in-memory AnalysisSummary.
- Console `/analysis` 는 기존 FE 분석 API 계약을 그대로 사용한다.
- Backend 분석 API는 Phase 03용으로 501 stub.

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/workers/frontend-analyzer/` | ts-morph 분석기·Golden Fixture·테스트 |
| `backend/app/skills/frontend_analyze/` | Skill Hub + script |
| `backend/app/workflow_definitions/wf_frontend_analyze.yml` | Workflow Hub |
| `backend/app/capability_definitions/capabilities.yml` | capability 등록 |
| `backend/app/agents/specs/platform_runner.yml` | allowed_skills 확장 |
| `backend/app/services/frontend_analysis.py` · `analysis_models.py` | Hub 호출·요약 저장 |
| `backend/app/api/analyses.py` | Analysis REST API |
| `backend/tests/test_frontend_analysis_phase02.py` | Gate 테스트 |
| `docs/06.완료보고/PHASE-02.md` | 본 재구현 Gate 보고 |
| `docs/report/20260804/02_3.md` | 회차 요약 |
| `docs/index.md` / `AGENTS.md` / `docs/continue/NEXT.md` | 포인터·핸드오프 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| AST 위치 | `backend/workers/` + Skill script | services 직접 분석 | D-012 · NEXT: Hub 우회 금지 |
| 실행 경로 | `wf_frontend_analyze` → ToolRuntime | API→npx 직행 | Plan/Review/Reduce 경로 유지 |
| AST 엔진 | ts-morph | TSC API 단독 | 기존 Gate·Golden 재사용 |
| Playwright | Evidence parser only | 실행 엔진 | Runtime은 Phase 09 agent-browser |
| BE API | 501 stub | Phase 02에 BE까지 | 한 세션 = 한 Phase |

## 5. API·Schema 변경

- API:
  - `POST /api/analyses/frontend`
  - `GET /api/analyses/{id}`
  - `GET /api/analyses/{id}/frontend`
  - `GET /api/analyses/{id}/frontend/screens`
  - `GET /api/analyses/{id}/frontend/components/{componentId}`
  - `GET /api/analyses/{id}/frontend/unresolved`
  - `POST /api/analyses/backend` → 501 (Phase 03)
- JSON Schema: `frontend_analysis.schema.json` (`frontend-analysis/v1`) 유지
- DB Migration: 없음 (in-memory)

## 6. 실행한 명령

```bash
cd backend/workers/frontend-analyzer && npm install && npm test
# 10 passed

cd backend && .venv/bin/python -m pytest tests/ -q
# 17 passed
```

## 7. 테스트 결과

| 테스트 영역 | 명령 | 결과 | 비고 |
|---|---|---|---|
| Analyzer golden/sample | `npm test` | 10 passed | Next/Pages/RHF/API/Playwright + sample FE |
| Backend Hub/API | `pytest tests/` | 17 passed | 00b+01+02 |
| Live sample API | pytest sample | complete | `/customers/search` · POST search |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| A 고객조회 Route·주요 컴포넌트 | PASS | `/customers/search` · `SearchPage` |
| customerId 필수·형식 제약 | PASS | zod/validation on customerId |
| 조회 이벤트·Handler 연결 | PASS | `onSubmit` resolved |
| `POST /api/customers/search` | PASS | apiCalls normalizedPath |
| B 화면 Route·오류 분기 후보 | PASS | `/customers/:customerId` · Navigate · error UI |
| Playwright Evidence 연결 | PASS | `e2e/customer-search.spec.ts` steps |
| Commit SHA·파일 라인 | PASS | result.commitSha + evidence.* |
| 해석 실패 조용히 누락 금지 | PASS | unresolved 배열 · dynamic fixture |

**Gate 판정: PASS**

## 9. 보안·개인정보 검토

- Secret/Token 미수집. 원본 전체 소스를 LLM에 전달하지 않음.
- Artifact는 구조화 JSON만 저장.

## 10. 알려진 제약

- cross-file const URL(path alias import) 해석은 부분적 — 동적/미해결은 unresolved
- Analysis 결과는 in-memory (재시작 시 소멸), artifact 파일은 디스크 유지
- Backend 분석은 Phase 03로 연기 (API 501)
- React Query는 호출 존재 수준 추출 제한 유지

## 11. 다음 Phase 전달사항

- 입력: `artifacts/analysis/*/frontend.json` 또는 `GET /api/analyses/{id}/frontend`
- 사용할 필드: screens, apiCalls, routeTransitions, validations, bindings, unresolved
- 다음 Phase: **03.Backend분석** — Skill Hub `backend_spring_analyze` 재편 후 FE apiCalls join 준비
- 주의: FE commitSha와 workspacePath를 분석 artifact에 함께 보관할 것

## 12. 문서 변경

- `AGENTS.md` / `docs/index.md`: 포인터 02 → 03
- `docs/continue/NEXT.md`: 03 핸드오프
- Architecture/ADR: 신규 ADR 없음
