# Phase 04 — API매핑 완료 보고 (SDD 재개)

> **재개 (2026-08-04):** 02·03 Skill Hub 재편 완료 후 Phase 04를 D-012 backend 위에 재구현했다.

## 1. 기본 정보

- Phase: 04.API매핑
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 관련 이전 Phase: 02·03 Skill Hub 재편 PASS
- 회차 요약: `docs/report/20260804/04_3.md`
- 핸드오프: `docs/continue/NEXT.md`

## 2. 구현 요약

- Capability `QA.CODE.API_MAP` · Skill `api_map` · Workflow `wf_api_map`를 교보재 포맷으로 Hub에 등록했다.
- 결정론 script `map_apis.py`가 FE apiCalls ↔ BE endpoints를 Method + normalized path로 join한다.
- `${id}` / `:id` / `{id}` path 정규화, baseURL 제거, 다중 후보는 `ambiguous`(자동 확정 금지).
- Request/Response 필드 매핑·validation mismatch·수동 PATCH Audit Trail을 제공한다.
- API: `POST/GET /api/analyses/{projectId}/api-mappings`, `PATCH /api/api-mappings/{mappingId}`.
- Console Analysis에 “Map FE↔BE APIs” 및 매핑 결과 테이블을 추가했다.
- services는 Hub Workflow만 호출한다 (join 로직은 Skill script).

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/skills/api_map/` | Skill Hub + map_apis script |
| `backend/app/workflow_definitions/wf_api_map.yml` | Workflow Hub |
| `backend/app/capability_definitions/capabilities.yml` | capability |
| `backend/app/services/api_mapping*.py` | Hub 호출·요약 저장 |
| `backend/app/api/api_mappings.py` | REST API |
| `backend/tests/test_api_mapping_phase04.py` | Gate 테스트 |
| `frontend/components/AnalysisWorkbench.tsx` | 매핑 UI |
| `packages/contracts/schemas/api_mapping.schema.json` | 계약 |
| `docs/06.완료보고/PHASE-04.md` · `docs/report/20260804/04_3.md` | 보고 |
| `docs/index.md` / `AGENTS.md` / `docs/continue/NEXT.md` | 포인터 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| 매칭 | Method + normalized path | LLM 확정 | Phase 요구 · 결정론 |
| 다중 후보 | `ambiguous` · endpointId null | 최고점 자동 확정 | Gate: 자동 확정 금지 |
| `{id}` path | projectId | 별도 mapping parent | FE/BE analysis id와 구분 |
| join 위치 | Skill script | services | D-012 Hub 우회 금지 |

## 5. API·Schema 변경

- `POST /api/analyses/{projectId}/api-mappings`
- `GET /api/analyses/{projectId}/api-mappings`
- `GET /api/api-mappings/sets/{mappingSetId}`
- `PATCH /api/api-mappings/{mappingId}` (수동 확정 + auditTrail)
- Schema: `api-mapping/v1`

## 6. 실행한 명령

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
# 26 passed
```

## 7. 테스트 결과

| 영역 | 결과 | 비고 |
|---|---|---|
| Unit normalize/ambiguous/fixtures | PASS | test_api_mapping_phase04 |
| Live FE+BE+map API | PASS | sample-targets join |
| Full backend suite | 26 passed | 00b–04 |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| 고객조회 FE 호출 ↔ BE Endpoint | PASS | POST `/api/customers/search` confirmed |
| customerId 요청 필드 연결 | PASS | requestFieldMappings |
| customerName/riskLevel/status 응답 연결 | PASS | responseFieldMappings |
| Validation 불일치 필드별 표시 | PASS | mismatches[] |
| 다중 후보 자동 확정 금지 | PASS | status=ambiguous |
| 매핑 근거·Confidence | PASS | matchReasons · confidence · evidence |

**Gate 판정: PASS**

## 9. 보안·개인정보 검토

- Secret 미수집. 분석 artifact JSON만 join.
- LLM 사실 확정 경로 없음.

## 10. 알려진 제약

- OpenAPI operationId 우선 매칭은 입력에 OpenAPI가 있을 때만 (현재 sample 없음)
- FE responseType이 null이면 Detail testId·BE DTO 교집합으로 응답 필드를 보강
- 매핑 결과는 in-memory + artifact 파일

## 11. 다음 Phase 전달사항

- 입력: `artifacts/analysis/MAPSET-*/api-mapping.json` + FE/BE analysis
- 다음: **05.InteractionGraph** — Figma User Flow Kit 필수 (D-008)
- confirmed mapping의 안정적 mappingId를 Graph가 참조

## 12. 문서 변경

- `AGENTS.md` / `docs/index.md`: 포인터 04 → 05
- `docs/continue/NEXT.md`: 05 핸드오프
