# Phase 03 — Backend분석 완료 보고 (SDD Skill Hub 재편)

> **재구현 (2026-08-04):** 구 worker-only 축소 SDD·`apps/control-plane` 구현은 D-012로 무효.  
> 본 보고는 **02 Gate 이후** Skill Hub `backend_spring_analyze` + Python worker 재편 결과다 (D-010).

## 1. 기본 정보

- Phase: 03.Backend분석
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 기준 Branch: main
- 관련 이전 Phase: 02.Frontend분석 (`PHASE-02.md`, Gate PASS)
- 회차 요약: `docs/report/20260804/03_3.md`
- ADR: **D-010** · **D-012**
- 핸드오프: `docs/continue/NEXT.md`

## 2. 구현 요약

- Capability `QA.CODE.BACKEND_SPRING_ANALYZE` · Skill `backend_spring_analyze` · Workflow `wf_backend_spring_analyze`를 교보재 포맷으로 Hub에 등록했다.
- AST 본체는 `backend/workers/backend-analyzer` (Python · javalang · record 정규화)에 두고 Skill script가 CLI로 호출한다.
- `POST /api/analyses/backend` 501 stub을 제거하고, services는 workspace/pin 메타만 해석한 뒤 Hub Workflow를 실행한다.
- 산출: `artifacts/analysis/AN-BE-*/backend.json` (`backend-analysis/v1`) + in-memory AnalysisSummary.
- Console `/analysis` Backend role이 동일 API 계약으로 동작한다.
- 런타임은 Python Tool이며 JavaParser JVM worker가 아니다.

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/workers/backend-analyzer/` | Python Spring 분석기·sample Gate 테스트 |
| `backend/app/skills/backend_spring_analyze/` | Skill Hub + script |
| `backend/app/workflow_definitions/wf_backend_spring_analyze.yml` | Workflow Hub |
| `backend/app/capability_definitions/capabilities.yml` | capability 등록 |
| `backend/app/agents/specs/platform_runner.yml` | allowed_skills |
| `backend/app/services/backend_analysis.py` | Hub 호출·요약 저장 |
| `backend/app/api/analyses.py` | Backend REST API (501 제거) |
| `backend/tests/test_backend_analysis_phase03.py` | Gate 테스트 |
| `docs/06.완료보고/PHASE-03.md` | 본 재구현 Gate 보고 |
| `docs/report/20260804/03_3.md` | 회차 요약 |
| `docs/index.md` / `AGENTS.md` / `docs/continue/NEXT.md` | 포인터·핸드오프 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| 분석 런타임 | Python Tool + javalang | JavaParser JVM | D-010 |
| AST 위치 | `backend/workers/` + Skill script | services 직접 분석 | D-012 Hub 우회 금지 |
| 실행 경로 | `wf_backend_spring_analyze` | API→CLI 직행 | Plan/Review/Reduce 유지 |
| Java record | 소스 정규화 후 javalang | JVM parser | 순수 Python 유지 |
| workspace | Phase 01 path만 소비 | analyzer 자체 clone | 책임 분리 |

## 5. API·Schema 변경

- `POST /api/analyses/backend` (501 → 구현)
- `GET /api/analyses/{id}/backend` · `.../endpoints` · `.../endpoints/{id}` · `.../unresolved`
- Schema: `backend-analysis/v1` 유지
- DB Migration: 없음

## 6. 실행한 명령

```bash
cd backend/workers/backend-analyzer && python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]' && .venv/bin/pytest -q
# 1 passed

cd backend && .venv/bin/python -m pytest tests/ -q
# 20 passed
```

## 7. 테스트 결과

| 영역 | 결과 | 비고 |
|---|---|---|
| BE analyzer pytest | 1 passed | sample Gate |
| Backend Hub/API pytest | 20 passed | 00b+01+02+03 |
| sample POST search | complete | endpoints·DTO·MockMvc |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| `POST /api/customers/search` | PASS | endpoints |
| `customerId` 제약 | PASS | NotBlank + Pattern |
| `CustomerResponse` 필드 | PASS | responseDtos |
| Controller→Service | PASS | serviceCalls |
| 예외/상태 분기 | PASS | NOT_FOUND_CANDIDATE / exceptions |
| MockMvc Evidence | PASS | existingTests framework=mockmvc |
| Commit + file/line | PASS | evidence.* · commitSha |
| 런타임 Python (非 JavaParser) | PASS | D-010 · worker Python · build.gradle 없음 |

**Gate 판정: PASS**

## 9. 보안·개인정보 검토

- Secret 미수집. workspace 절대경로만 사용.
- LLM 사실 확정 경로 없음 (script only).

## 10. 알려진 제약

- javalang은 Java record를 직접 지원하지 않아 정규화 전처리 사용
- Lombok 생성 멤버·AOP/Profile은 `unresolved` 또는 부분 추출
- Analysis 결과는 in-memory (재시작 시 소멸), artifact는 디스크 유지
- sample `./gradlew test` SSL 이슈는 analyzer Gate와 무관 (기존 제약)

## 11. 다음 Phase 전달사항

- 입력: `artifacts/analysis/*/backend.json` + Phase 02 `frontend.json`
- 다음: **04.API매핑** — FE apiCalls ↔ BE endpoints join
- workspace는 계속 Phase 01 sync 경로만 사용
- 02·03 Skill 재편 완료 → Phase 04 재개 허용

## 12. 문서 변경

- `AGENTS.md` / `docs/index.md`: 포인터 03 → 04
- `docs/continue/NEXT.md`: 04 핸드오프
- D-010 반영 유지
