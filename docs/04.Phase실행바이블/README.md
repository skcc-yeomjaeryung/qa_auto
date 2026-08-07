# 04.Phase실행바이블 — 순차 실행 본체

이 폴더가 파일럿 **실행 바이블**이다.  
한 세션에는 Phase 문서 **하나만** 투입한다.

## 권장 실행 DAG

```text
00 → 00b → 01
           ├→ 02 ─┐
           └→ 03 ─┴→ 04 → 05 → 06
                         02 → 07 → 08
                         06,08 → 09 → 10 → 11 → 12
                                           ├→ 13
                                           └→ 14
                                   12,13,14 → 15 → 99
```

> **현재 상태:** 00b 재구축 Gate와 01~13 Gate는 완료됐다. 단일 Agentic Core 공식 경로는
> `runtime·planning·execution·quality`이며, 현재 실행 포인터는 Phase 14다.

## Phase 목록

| # | 문서 | 선행 | 종료 Gate |
|---|---|---|---|
| 00 | [00.기반구축.md](./00.기반구축.md) | 없음 | 모노레포 기동 · 샘플 FE/BE |
| 00b | [00b.BackendSDD기반.md](./00b.BackendSDD기반.md) | 00 | Workflow/Skill Hub · core · LangGraph (완료) |
| 01 | [01.저장소연결.md](./01.저장소연결.md) | 00b | Commit 고정 수집 (+선택 Design Spec/Excel) |
| 02 | [02.Frontend분석.md](./02.Frontend분석.md) | 01 | FE 추출 (Skill Hub 재편) |
| 03 | [03.Backend분석.md](./03.Backend분석.md) | 01 | Spring BE 추출 (Skill Hub 재편, D-010·D-012) |
| 04 | [04.API매핑.md](./04.API매핑.md) | 02,03 | FE↔BE 매핑 (**00b 후 재개**) |
| 05 | [05.InteractionGraph.md](./05.InteractionGraph.md) | 04 | A→B Graph · Flow UI(Figma Kit) |
| 06 | [06.시나리오DSL.md](./06.시나리오DSL.md) | 05 | 실행 DSL (+Design Spec join 후보) |
| 07 | [07.컴포넌트계약.md](./07.컴포넌트계약.md) | 02,06 | 입력·Locator 계약 (+annotation 힌트) |
| 08 | [08.입력값추천.md](./08.입력값추천.md) | 03,07 | Input Profile (+Excel Catalog) |
| 09 | [09.브라우저실행.md](./09.브라우저실행.md) | 06,08 | **agent-browser** A→B |
| 10 | [10.Backend추적.md](./10.Backend추적.md) | 03,09 | Run ID 관통 로그 |
| 11 | [11.바인딩검증.md](./11.바인딩검증.md) | 09,10 | UI 바인딩 비교 |
| 12 | [12.증적수집.md](./12.증적수집.md) | 09~11 | Evidence Package |
| 13 | [13.건별테스트.md](./13.건별테스트.md) | 08~12 | 건별 UI |
| 14 | [14.배치테스트.md](./14.배치테스트.md) | 08~12 | 배치 실행 (**현재**) |
| 15 | [15.HITL승인.md](./15.HITL승인.md) | 12~14 | HITL · Audit |
| 99 | [99.통합인수검증.md](./99.통합인수검증.md) | 00~15 | 인수 데모 |

## 완료 체크 (매 Phase)

- [ ] 구현 코드
- [ ] 단위 테스트
- [ ] 통합 테스트 또는 실행 검증
- [ ] API/OpenAPI 변경
- [ ] Schema 변경
- [ ] 샘플 데이터 또는 Fixture
- [ ] 보안·마스킹 검토
- [ ] `AGENTS.md` 갱신 여부
- [ ] `docs/06.완료보고/PHASE-XX.md`
- [ ] 알려진 제약과 다음 Phase 전달사항
- [ ] `docs/index.md` 현재 Phase 포인터 갱신

## 기본 Console 체인 Gate (횡단)

```text
GitHub monorepo URL (subdir FE/BE)
  → Sync · Commit pin
  → pipeline analyze-to-scenarios
  → 테스트 시나리오 목록 (/scenarios?setId=)
  → 시나리오 상세 슬라이드 (&scenarioId=)
  → 시나리오 단위 의존관계 그래프 (&view=graph)
```

- DoD: [`../01.제품과완료기준/03.파일럿완료기준.md`](../01.제품과완료기준/03.파일럿완료기준.md)
- Phase 06이 여정 glue(시나리오·pipeline·의존관계 그래프 serviceId)를 담당한다.
- 검증 대상 예: [bank-of-anthos](https://github.com/GoogleCloudPlatform/bank-of-anthos.git) (`src/frontend` + Java ledger subdir)

## 현재 포인터

[`../index.md`](../index.md)의 **현재 Phase 포인터**가 진실원이다.
