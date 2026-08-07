# Phase 05 — InteractionGraph 완료 보고 (SDD)

> **작업일 2026-08-04:** Phase 04 이후 D-012 Hub 위에 Interaction Graph · Figma Flow UI를 구현했다.

## 1. 기본 정보

- Phase: 05.InteractionGraph
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 관련 이전 Phase: 04 API매핑 PASS
- 회차 요약: `docs/report/20260804/05_1.md`
- 핸드오프: `docs/continue/NEXT.md`

## 2. 구현 요약

- Capability `QA.CODE.INTERACTION_GRAPH` · Skill `interaction_graph` · Workflow `wf_interaction_graph`를 교보재 포맷으로 Hub에 등록했다.
- 결정론 script `compose_graph.py`가 FE + BE + api-mapping을 결합해  
  `screen(A) → input → event → validation → frontend_api_call → backend_endpoint → request_dto → service → response_dto → route_transition → screen(B) → binding` 을 조립한다.
- 분기: `happy_path` · `validation_failed` · `customer_not_found`(404).
- API: `POST /api/analyses/{projectId}/interaction-graphs`, `GET /api/interaction-graphs`, `GET …/{graphId}`, `GET …/paths?from=&to=`.
- Flow UI (`/flow`)는 Figma User Flow Kit(D-008) MCP 대조 후 구현  
  (browser chrome 화면 카드 · Accent `#3300FF` · Arrow `#1A1A1A` · pill · Conditions · Comments/Warning).
- services는 Hub Workflow만 호출한다 (그래프 조립 로직은 Skill script).

## 3. Figma MCP 대조 (D-008)

| 항목 | 값 |
|---|---|
| fileKey | `qpZeClozlSVQd6j8Od8P9x` |
| Kit Components | node `0:1` (Screens `1:289`, Arrows, Conditions `1:531`, Comments `1:499`, Nodes `7:511`) |
| Example FLOW | node `1:319` |
| Form screen | node `1:368` |
| Evidence | `artifacts/evidence/phase05-figma/` (`FIGMA_REF.md`, screenshots) |

MCP: `get_metadata(0:1)` · `get_screenshot(1:319)` · `get_design_context(1:368, 1:675)`.

## 4. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/skills/interaction_graph/` | Skill Hub + compose_graph |
| `backend/app/workflow_definitions/wf_interaction_graph.yml` | Workflow Hub |
| `backend/app/capability_definitions/capabilities.yml` | capability |
| `backend/app/services/interaction_graph*.py` | Hub 호출·요약 저장 |
| `backend/app/api/interaction_graphs.py` | REST API |
| `backend/tests/test_interaction_graph_phase05.py` | Gate 테스트 |
| `frontend/components/flow/FlowCanvas.tsx` · `app/flow/page.tsx` | Flow UI |
| `frontend/app/styles.css` · `lib/nav.ts` | kit 스킨 · 내비 |
| `artifacts/evidence/phase05-figma/` | Figma 대조 증적 |
| `docs/06.완료보고/PHASE-05.md` · `docs/report/20260804/05_1.md` | 보고 |
| `docs/index.md` / `AGENTS.md` / `docs/continue/NEXT.md` | 포인터 → 06 |

## 5. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| 조립 위치 | Skill script | services | D-012 Hub 우회 금지 |
| 사실 추출 | 결정론 규칙 | LLM 그래프 | Phase Gate · Evidence |
| Flow 스킨 | Figma kit CSS | 임의 flowchart 테마 | D-008 |
| Graph Hub | 사용 안 함 | graph_manifest | 절대 금지 |

## 6. API·Schema 변경

- `POST /api/analyses/{projectId}/interaction-graphs`
- `GET /api/interaction-graphs?projectId=`
- `GET /api/interaction-graphs/{graphId}`
- `GET /api/interaction-graphs/{graphId}/paths?from=&to=`
- Schema: `interaction-graph/v1` (`packages/contracts/schemas/interaction_graph.schema.json`)

## 7. 실행한 명령

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
# 32 passed
```

## 8. 테스트 결과

| 영역 | 결과 | 비고 |
|---|---|---|
| Skill/Workflow textbook | PASS | §1–14 · capability |
| Fixture compose + schema | PASS | Draft202012Validator |
| A→B path / cycle-safe DFS | PASS | find_paths |
| Live FE→BE→map→graph API | PASS | sample-targets |
| Full backend suite | 32 passed | 00b–05 |

## 9. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| A→B 정상 관통 경로 표시 | PASS | primaryPath + Flow UI |
| customerId Input→Request 연결 | PASS | dataMappings / edges |
| Response→B binding | PASS | binding nodes |
| 정상·검증·404 분기 | PASS | branches + conditions |
| Edge Evidence·Confidence | PASS | schema + UI panel |
| Schema 검증 | PASS | jsonschema |
| Flow UI Figma kit 대응 | PASS | MCP + CSS + FIGMA_REF |
| 완료 보고 Figma 인용 | PASS | 본 문서 §3 |

## 10. 알려진 제약

- Graph는 고객조회(search→detail) 샘플 경로에 특화된 결정론 조립이다. 일반 프로젝트 다경로 확장은 Phase 이후.
- Flow UI는 kit 언어를 CSS로 이식했다 (Tailwind 미도입).
- Pass/Fail·HITL 승인은 포함하지 않는다.

## 11. 다음 Phase 전달사항

- 다음: **06.시나리오DSL** — Interaction Graph를 Scenario DSL로 변환.
- 입력 후보: `artifacts/analysis/IG-*/interaction-graph.json`.
- Figma Progress UI(D-009)는 여정 UI 단계에서 별도 대조.

## 12. AGENTS.md 변경

- 현재 Phase 포인터를 **06.시나리오DSL**로 갱신 (index·NEXT와 동기).
