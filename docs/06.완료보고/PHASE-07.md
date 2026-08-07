# Phase 07 — 컴포넌트계약 완료 보고

## 1. 기본 정보

- Phase: 07.컴포넌트계약
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 관련 이전 Phase: 02 Frontend분석 · 06 시나리오DSL
- 회차 요약: `docs/report/20260804/07_1.md`

## 2. 구현 요약

시나리오 A/B 화면의 Input/Output Component Contract를 Skill Hub 결정론 Builder로 생성한다.

- Locator 우선순위(testId→role→label→id/name→css)와 불안정 Locator 경고
- Zod/FE + BE Bean Validation 병합 및 mismatch 표시
- B 화면 4필드 바인딩(customerId/Name/riskLevel/status) + normalize
- Screenshot hook·mask region (실행 전 preview 자리)
- UI Adapter SDK 예시(`BizInput`/`BizButton`) JSON/YAML
- Console 시나리오 상세에 A/B Contract 카드
- Pipeline `analyze-to-scenarios`에 contract 스텝 추가

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/skills/component_contract/` | Skill + build_contract.py |
| `backend/app/workflow_definitions/wf_component_contract.yml` | Workflow Hub |
| `backend/app/capability_definitions/capabilities.yml` | `QA.CODE.COMPONENT_CONTRACT` |
| `backend/app/services/component_contract_*.py` | 모델·서비스 |
| `backend/app/api/component_contracts.py` | REST |
| `backend/app/services/pipeline.py` | contract 스텝 |
| `packages/adapter-sdk/` | UI Adapter types + examples |
| `docs/03.계약과예시/schemas/component_contract.schema.json` | Schema SSOT |
| `frontend/components/ComponentContractCards.tsx` | A/B UI |
| `frontend/components/ScenarioTable.tsx` | 상세 연동 |
| `backend/tests/test_component_contract_phase07.py` | Gate 테스트 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| Hub 경로 | Skill + Workflow + PlatformRunner | 서비스 내 직결만 | D-012 Hub 강제 |
| Adapter 기본 | JSON 예시 | YAML only | tool runtime `python3`에서 PyYAML 비의존 |
| Pipeline | scenario 후 contract 자동 | 수동 API만 | Console 체인 연속성 |
| Design Spec | hint only | Locator 확정 | D-006 |

## 5. API·Schema 변경

- 추가 API:
  - `POST /api/scenarios/{id}/component-contract`
  - `GET /api/scenarios/{id}/component-contract`
  - `GET /api/component-contracts/{contractId}`
- JSON Schema: `component_contract.schema.json` (docs → packages sync)
- PipelineResult: `contractIds[]` additive

## 6. 실행한 명령

```bash
cd packages/contracts && node scripts/sync-schemas.mjs
cd backend && .venv/bin/python -m pytest tests/test_component_contract_phase07.py -q
cd backend && .venv/bin/python -m pytest tests/ -q
```

## 7. 테스트 결과

| 테스트 영역 | 명령 | 결과 | 비고 |
|---|---|---|---|
| Phase 07 | `pytest tests/test_component_contract_phase07.py -q` | 10 passed | Hub·schema·locator·BizInput·B4·API |
| Full suite | `pytest tests/ -q` | 45 passed, 1 skipped | |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| A 고객조회 필수 입력 계약 | PASS | customerId required + pattern + testId |
| fill/blur/click 이벤트 | PASS | inputs.events · actions.click |
| 안정적 Locator | PASS | testId 우선 · css는 warning |
| B 4개 응답 필드 Binding | PASS | outputs 4건 |
| FE/BE 제약 불일치 표시 | PASS | validationMismatches 필드 |
| Custom Component Adapter | PASS | BizInput mapping + adapter-sdk |

## 9. 보안·개인정보 검토

- Secret 미저장
- Screenshot mask에 identifier 후보 포함
- Pass/Fail 단정 없음

## 10. 알려진 제약

- FE analyzer가 detail testId를 inputs로 안 뽑으면 Adapter/Graph Evidence로 B binding
- Design Spec annotation join은 hint 경로만 (업로드 UI 미연결)
- 추천값 자체는 Phase 08 범위

## 11. 다음 Phase 전달사항

- Phase **08.입력값추천**: Input Contract `recommendationReady=false` 필드를 채움
- API: `GET/POST .../component-contract` 결과의 `inputs[]`
- Adapter path 기본: `packages/adapter-sdk/examples/ui-adapter.customer-search.json`

## 12. 문서 변경

- `docs/06.완료보고/PHASE-07.md` (본 문서)
- `docs/report/20260804/07_1.md`
- `docs/index.md` · `AGENTS.md` · `docs/continue/NEXT.md` → 08
- `docs/03.계약과예시/07.ComponentContract스키마.md`
