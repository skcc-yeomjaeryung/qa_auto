# Backlog & Non-Goals — AI Hackerton

North Star: [`00_NORTH_STAR.md`](./00_NORTH_STAR.md)  
인터뷰: [`01_INTERVIEW_BRIEF_v0.1.md`](./01_INTERVIEW_BRIEF_v0.1.md)

---

## MVP In (문서 Phase 이후 구현 우선순위)

| ID | 항목 | 설명 |
|---|---|---|
| M01 | 문서 SSOT · SDD 규칙 | `docs/index.md`, AGENTS, mdc (본 Phase) |
| M02 | Backend 스캐폴딩 · Registry/Schema | utils/core, Workflow/Skill Hub 로드 |
| M03 | 공통 Plan Execution Runtime | route→plan→execute→review→reduce |
| M04 | Repo Sync Skill | git/svn 엔드포인트 연결·동기화 |
| M05 | Unit Scenario Skill | Class/.py 단위 시나리오 초안 |
| M06 | Integration Plan Skill | A→B→C 의존 분석·통합 Plan (핵심) |
| M07 | Param Augment · Run | INPUT 생성·증강·실행 결과 artifact |
| M08 | Quality KPI 보드 | 성공/실패 목록·품질지표 API/UI |
| M09 | FLOW UI (Figma 계약) | 목록→FLOW·파라미터·배치 편집 |
| M10 | FE/BE 실기동 · Vercel MCP FE 검증 | 대상 앱 기동 · DOM 입력/후속 결과 · 스크린샷 evidence (단계적). Playwright는 보완 |

---

## 후속 백로그

| ID | 항목 | 설명 |
|---|---|---|
| B01 | SVN/Git 어댑터 분리 | 엔드포인트·인증·부분 sync |
| B02 | 다언어 파서 플러그인 | Java 우선, Python/기타 확장 |
| B03 | 시나리오 버전·승인 | HITL 승인 후 Hub/카탈로그 반영 |
| B04 | 야간 대량 prepare | 저장소 단위 배치 시나리오 생성 |
| B05 | ScreenContext (후속) | 화면 KPI Q&A가 필요해질 때 NH 패턴 도입 |
| B06 | Durable DB | 파일/runtime → DB |
| B07 | Offline eval harness | Golden repo로 회귀 |

---

## Non-Goals (하지 않음)

1. **AI가 테스트 Pass/Fail·배포를 최종 확정**하거나 외부 배포 gateway를 자동 호출
2. **Graph Hub / graph_manifest.yml / Graph Registry**
3. Workflow YML에 Skill 실행 방식·승인 if/else 내장
4. Skill에 업무 승인 정책 Engine 내장
5. Planner가 Hub에 없는 Workflow/Skill/Tool 발명
6. LLM이 의존그래프·커버리지 수치를 **근거 없이 추정**해 채움 → `missing_data`
7. Hub/Plan/Validator를 우회하는 **병렬 Deep Agent 프레임워크** (Deep Agent는 Core 옵션만)
8. AML Context AI / ScreenContext 규칙을 이 PoC에 그대로 이식 (후속 B05)
9. open-webui 등 외부 참조 클론을 제품 런타임에 포함
10. raw chain-of-thought / raw_prompt를 audit에 저장
11. Vercel MCP / Playwright MCP를 **사용자 동의 없이** 자동 기동
12. 스크린샷·DOM 관측만으로 AI가 Pass/Fail을 **최종 확정**
13. 1차 Phase에서 대상 고객사 전체 레포 실기동 E2E를 한꺼번에 완성 (M10은 단계적)

---

## 문서 유지 규칙

- 작업 시작: 항상 [`docs/index.md`](../index.md)
- Phase 완료: `docs/report/`에 보고
- 컨텍스트 흐림: `docs/work-orders/chain/`에 memory
