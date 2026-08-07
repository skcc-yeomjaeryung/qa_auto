# Phase 06 — 시나리오DSL · Console 체인 glue 완료 보고

## 1. 기본 정보

- Phase: 06.시나리오DSL (+ Console 체인 Gate)
- 작업일: 2026-08-04
- 담당: Cursor Agent
- 회차 요약: `docs/report/20260804/06_1.md`
- 검증 GitHub: [bank-of-anthos](https://github.com/GoogleCloudPlatform/bank-of-anthos.git)

## 2. 구현 요약

- Skill Hub `scenario_dsl` · Workflow `wf_scenario_dsl` · capability `QA.CODE.SCENARIO_DSL`
- Graph→DSL 결정론 변환 + `serviceId=customer-search`
- API: scenarios CRUD/validate/versions/diff · `POST .../pipeline/analyze-to-scenarios` · `GET /api/flows/by-service/{serviceId}`
- Repository `subdir` 지원 (동일 GitHub URL × FE/BE 서브경로)
- Console: Projects GitHub+subdir · 원샷 파이프라인 · Scenarios API 목록 · 상세 FLOW 딥링크
- sample_java 모노레포(frontend/backend, :5173/:8081) 재구성·스모크 완료 (Local golden path)

## 3. bank-of-anthos 관측

| 단계 | 관측 |
|---|---|
| Sync FE `src/frontend` | complete · Python stack · 45 files |
| Sync BE `src/ledger/ledgerwriter` | complete · Maven/Java · 24 files |
| Pipeline | complete (observation) |
| Graph | nodes=4 edges=0 (고객조회 React/Spring 경로와 불일치 → unresolved 다수 가능) |
| Scenario | 1건 생성 · serviceId 딥링크 가능 |

Pass/Fail 단정 없음. Analyzer는 TS/React·Spring 고객조회 파일럿에 최적화되어 있어 BoA는 inventory/pipeline 체인 검증 용도로 사용.

## 4. 변경 파일 (요지)

| 경로 | 목적 |
|---|---|
| `backend/app/skills/scenario_dsl/` | Scenario Skill |
| `backend/app/services/pipeline.py` · `scenario_*.py` | 원샷·시나리오 |
| `backend/app/api/{scenarios,pipeline,flows}.py` | REST |
| `repository_models/sync` `subdir` | 모노레포 |
| `frontend/components/ProjectsWorkbench.tsx` 등 | Console 체인 UI |
| `docs/01…/03.파일럿완료기준.md` 등 | 체인 Gate SSOT |

## 5. 테스트

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

- scenario skill/schema · sample_java local pipeline · flow lookup
- bank-of-anthos live sync+pipeline (수동/스크립트 관측)

## 6. Acceptance

| Criteria | 결과 |
|---|---|
| Scenario DSL Hub/API | PASS |
| GitHub+subdir Sync | PASS (BoA) |
| Pipeline → scenario list | PASS |
| FLOW serviceId | PASS |
| BoA A→API→B 완전 Graph | partial / missing_data (스택 불일치) |
| sample_java golden pipeline | PASS |

## 7. agent-browser MCP

이번 Gate에서는 **사용하지 않음**. BoA는 K8s 배포 URL이 있어야 화면 관측이 의미 있다.  
사용자 승인 후 Phase 09 또는 배포 URL이 있을 때 사용 권장.

## 8. 다음 Phase

- **07.컴포넌트계약** (또는 Progress UI D-009 보강)
- BoA 전용 FE analyzer는 범위 밖 (별도 결정 필요)
