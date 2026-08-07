# 파일럿 구현 Phase 색인

## 목표 흐름

```text
GitHub/Local Repository
  → Frontend AST 분석
  → Backend AST 분석
  → Frontend↔Backend API 매핑
  → A→B Interaction Graph
  → 실행 가능한 Scenario DSL
  → 입력값 추천 및 증강
  → agent-browser MCP 실제 이벤트 (DOM snapshot + screenshot)
  → Backend 요청·응답 추적
  → B 화면 데이터 바인딩 검증
  → 증적 패키지 생성
  → 건별/배치 실행
  → 고객 HITL 승인
```

## 선행 문서

- `README.md`
- `00_common_context.md`
- `00_pilot_definition_of_done.md`
- `schemas/interaction_graph.schema.json`
- `schemas/scenario_dsl.schema.json`
- `schemas/evidence_manifest.schema.json`
- `examples/customer_search_to_detail.scenario.yaml`

## Phase 목록

| 순서 | 프롬프트 | 대응 필수 기능 | 선행 Phase | 종료 Gate |
|---:|---|---|---|---|
| 00 | `phase_00_foundation.md` | 공통 기반·샘플 대상 시스템 | 없음 | 전체 모노레포 기동, 샘플 FE/BE 연동 |
| 01 | `phase_01_repository_connection.md` | 1. GitHub Repository 연결 | 00 | URL/Local 경로로 두 저장소 수집 및 Commit 고정 |
| 02 | `phase_02_frontend_analysis.md` | 2. TypeScript·React·Next.js 분석 | 01 | 화면·컴포넌트·이벤트·입력·API·Route 추출 |
| 03 | `phase_03_backend_analysis.md` | 3. Java·Spring Boot 분석 | 01 | Endpoint·DTO·Validation·응답·테스트 추출 |
| 04 | `phase_04_api_mapping.md` | 4. Frontend–Backend API 매핑 | 02, 03 | HTTP Method/Path/Schema 기반 매핑과 불일치 표시 |
| 05 | `phase_05_interaction_graph.md` | 5. A→B Interaction Graph 생성 | 04 | A→API→Backend→B 흐름과 분기 시각화 |
| 06 | `phase_06_scenario_dsl.md` | 6. 시나리오 DSL 생성 | 05 | Schema 검증 가능한 실행 DSL 생성·버전 관리 |
| 07 | `phase_07_component_contract.md` | 7. 컴포넌트 필수속성 추출 | 02, 06 | 필수 입력·Locator·제약·출력 바인딩 계약 생성 |
| 08 | `phase_08_input_recommendation.md` | 8. 추천 입력값 생성 | 03, 07 | 정상·경계·오류·업무상태 추천값과 근거 제공 |
| 09 | `phase_09_browser_execution.md` | 9. 실제 브라우저 이벤트 실행 | 06, 08 | A 화면 입력부터 B 화면 이동까지 agent-browser MCP 실행 |
| 10 | `phase_10_backend_trace.md` | 10. Backend Request·Response 추적 | 03, 09 | 동일 Test Run ID로 브라우저와 Spring 로그 연결 |
| 11 | `phase_11_binding_validation.md` | 11. B 화면 바인딩 검증 | 09, 10 | Input↔Request↔Response↔UI 값 비교 |
| 12 | `phase_12_evidence_collection.md` | 12. Screenshot·Trace·로그 수집 | 09~11 | 재현 가능한 Evidence Package와 Manifest 생성 |
| 13 | `phase_13_interactive_test.md` | 13. 건별 테스트 | 08~12 | 추천값 검토·수정·실행·결과 확인 UI |
| 14 | `phase_14_batch_test.md` | 14. 배치 테스트 | 08~12 | 승인된 Input Profile로 무인 반복·병렬 실행 |
| 15 | `phase_15_hitl.md` | 15. HITL 승인·반려·재실행 | 12~14 | 자동 PASS와 고객 승인 분리, Audit Trail 저장 |
| 99 | `phase_99_integrated_pilot_validation.md` | 통합 파일럿 인수검증 | 00~15 | 고객조회 A→B 관통 데모와 전체 인수조건 통과 |

## 권장 실행 방식

```text
00 → 01
      ├→ 02 ─┐
      └→ 03 ─┴→ 04 → 05 → 06
                    02 → 07 → 08
                    06,08 → 09 → 10 → 11 → 12
                                      ├→ 13
                                      └→ 14
                              12,13,14 → 15 → 99
```

## 공통 산출물 위치

```text
docs/20260804/
  decisions/
  architecture/
  phase-reports/
  api/
  schemas/

artifacts/
  analysis/
  scenarios/
  test-runs/
  evidence/
```

## Phase 완료 체크 규칙

각 Phase 완료 시 반드시 다음을 남깁니다.

- [ ] 구현 코드
- [ ] 단위 테스트
- [ ] 통합 테스트 또는 실행 검증
- [ ] API/OpenAPI 변경
- [ ] Schema 변경
- [ ] 샘플 데이터 또는 Fixture
- [ ] 보안·마스킹 검토
- [ ] `AGENTS.md` 갱신 여부
- [ ] `docs/20260804/phase-reports/PHASE-XX.md`
- [ ] 알려진 제약과 다음 Phase 전달사항
