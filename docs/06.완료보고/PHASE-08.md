# Phase 08 — 입력값추천 완료 보고

## 1. 기본 정보

- Phase: 08.입력값추천
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 관련 이전 Phase: 03 Backend분석 · 07 컴포넌트계약
- 회차 요약: `docs/report/20260804/08_1.md`

## 2. 구현 요약

Component Contract·Fixture·existing test·Schema·Best Practice Catalog를 결합해
건별 추천 INPUT과 배치용 Input Profile을 결정론적으로 생성한다.

- 소스 우선순위: Fixture → existing test → schema → sheet → catalog (Sheet/Design Spec은 보조)
- 정상/제한/미존재/형식오류/필수누락/경계 카테고리
- 식별자 무작위 생성 금지 · seed·generator version 기록
- PII 필드 마스킹 · destructive 제외
- pairwise 축소 + budget
- Console 시나리오 상세: Recommend / Profile / Approve
- Pipeline `analyze-to-scenarios`에 `input_recommend` 스텝 추가

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/skills/input_recommend/` | Skill + recommend.py |
| `backend/app/workflow_definitions/wf_input_recommend.yml` | Workflow Hub |
| `backend/app/capability_definitions/capabilities.yml` | `QA.CODE.INPUT_RECOMMEND` |
| `backend/app/services/input_recommend_*.py` | 모델·서비스 |
| `backend/app/api/input_profiles.py` | REST |
| `backend/app/services/pipeline.py` | recommend 스텝 |
| `packages/test-data-catalog/` | Fixture + BP catalog |
| `docs/03.계약과예시/schemas/input_*.schema.json` | Schema SSOT |
| `frontend/components/InputRecommendPanel.tsx` | 건별·배치 UI |
| `frontend/components/ScenarioTable.tsx` | 상세 연동 |
| `backend/tests/test_input_recommend_phase08.py` | Gate 테스트 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| Hub 경로 | Skill + Workflow + PlatformRunner | 서비스 직결만 | D-012 Hub 강제 |
| 식별자 | Fixture/static만 | 랜덤 CUS-* | Phase 요구사항 4 |
| Sheet | reviewRequired | hard expected | D-006 보조 Evidence |
| Profile 승인 | HITL Approve API | 자동 APPROVED | 기대값 자동 확정 금지 |

## 5. API·Schema 변경

- 추가 API:
  - `POST/GET /api/scenarios/{id}/recommend-inputs`
  - `GET/POST /api/scenarios/{id}/input-profiles`
  - `POST /api/input-profiles/{id}/approve`
  - `POST /api/input-profiles/{id}/generate-cases`
- JSON Schema: `input_recommendation.schema.json`, `input_profile.schema.json`
- PipelineResult: `recommendationIds[]` additive

## 6. 실행한 명령

```bash
cd packages/contracts && node scripts/sync-schemas.mjs
cd backend && .venv/bin/python -m pytest tests/test_input_recommend_phase08.py -q
cd backend && .venv/bin/python -m pytest tests/ -q
```

## 7. 테스트 결과

| 테스트 영역 | 명령 | 결과 | 비고 |
|---|---|---|---|
| Phase 08 | `pytest tests/test_input_recommend_phase08.py -q` | 12 passed | Hub·우선순위·seed·mask·API·pipeline |
| Full suite | `pytest tests/ -q` | 57 passed, 1 skipped | |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| 정상/제한/미존재/형식오류 추천 | PASS | categories 테스트 · catalog/fixture |
| 출처·근거 표시 | PASS | sources + rationale · Console panel |
| 건별 기본값 자동 | PASS | defaults.customerId=CUS-1001 |
| 승인 배치 Profile | PASS | approve API · status APPROVED |
| 예산 내 조합 | PASS | budget≤N · pairwise cases |
| 민감정보 미노출 | PASS | password → `***` |

## 9. 보안·개인정보 검토

- Fixture/Catalog는 synthetic만
- PII 힌트 필드 마스킹
- Secret/Token 저장 없음
- destructive data 미생성

## 10. 알려진 제약

- In-memory store는 reload 시 초기화
- Excel/Design Spec 업로드 연동은 스키마·정책만 (파일 업로드 UI는 후속)
- LLM semantic suggestion은 미구현 (순위 6 자리만)

## 11. 다음 Phase 전달사항

- Phase **09.브라우저실행**: 승인/건별 INPUT을 agent-browser fill에 연결
- Recommend defaults·Profile cases를 실행 step INPUT으로 전달
- MCP 사용 전 사용자 문의 유지

## 12. AGENTS.md 변경

- 현재 Phase 포인터 → **09.브라우저실행**
