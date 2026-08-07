# North Star — AI Hackerton 테스트자동화 플랫폼

> 이 문서가 제품 가치의 **최상위 정의**다.  
> Phase·Skill·UI는 이 느낌을 구현하기 위한 수단이다.  
> 상세 색인: [`docs/index.md`](../index.md)

---

## 1. 한 문장 제품 약속

```text
공용 저장소 코드를 연결하면,
AI가 단위·통합 테스트 시나리오와 INPUT을 만들고,
FLOW로 고치고 돌리며,
성공·실패·품질지표를 사람이 한눈에 본다.
최종 Pass/Fail·배포 결정은 사람이 한다.
```

---

## 2. 주 사용자

| 역할 | 하고 싶은 일 |
|---|---|
| 개발 PL | 다수 개발자 산출물의 진행·품질을 추적·관리 |
| QA 테스트품질담당자 | 시나리오·실행 결과·품질지표로 품질을 관리 |

숙련자만 쓰는 CLI 도구가 아니라, **저장소 연결 → 시나리오 → FLOW → 결과**가
화면에서 이어지는 플랫폼이어야 한다.

---

## 3. 핵심 가치 사슬 (3단)

```text
① 테스트 시나리오 생성
   - 저장소 동기화 · 코드(주석/포맷 유도) 분석
   - 단위 테스트 (Class / .py 등 단일 거래·서비스 단위)
   - 통합 테스트 (A→B→C 의존·연속 호출 Plan)  ← ★ 프로젝트 핵심

② INPUT 파라미터 생성·증강 · 테스트 수행
   - 시나리오 기반 INPUT 자동 생성·증강
   - 실행 후 성공/실패 시각 목록 · 품질지표

③ FLOW UI 제공
   - 시나리오 목록 → 클릭 시 FLOW 뷰
   - 재처리 · 파라미터 수정 · 컴포넌트 배치 편집
```

---

## 4. 프로젝트 핵심 난제 (가장 집중)

```text
AI가 코드 의존관계를 분석해
유의미한 통합 테스트 시나리오(A→B→C)를 세우고
실행하여 결과를 도출하는 것
```

단순 Swagger/API 파라미터 테스트에 그치지 않는다.
**Backend + Frontend 화면 연계**까지 포함한다.
통합 FE는 **Vercel MCP**로 DOM 기반 입력값·후속 수행 결과를 관측하고,
단계별 **스크린샷 evidence**를 남긴다 (Pass/Fail 최종은 사람).

---

## 5. As-Is vs To-Be

| | As-Is (전형 SI) | To-Be (이 플랫폼) |
|--|----------------|-------------------|
| 시나리오 | 사람이 수작업 작성 | 저장소 코드 기반 AI 초안 |
| 통합 테스트 | 의존관계를 사람이 기억 | AI가 A→B→C Plan 제안 |
| 데이터 | 수작업 fixture | INPUT 생성·증강 |
| 실행 결과 | 로그 파편 | 성공/실패·품질 KPI 보드 |
| 편집 | 문서/스크립트 직접 수정 | FLOW UI에서 배치·파라미터 수정 |
| 최종 판단 | (암묵) | **명시적 HITL** — Pass/Fail·배포는 사람 |

---

## 6. SDD와의 관계

구현은 Skill-Driven Development로 한다.

```text
Workflow = 무엇을 해야 하는가 (시나리오 생성·실행·FLOW 등 업무 목표)
Skill    = 그 안에서 실행 가능한 기능 (동기화·분석·파라미터·실행…)
Plan     = Executor가 돌릴 JSON
Runtime  = 공통 Plan Execution Graph (Graph Hub 아님)
```

상세: [`docs/architecture/DECISIONS.md`](../architecture/DECISIONS.md),
[`.cursor/rules/00-absolute-sdd-architecture.mdc`](../../.cursor/rules/00-absolute-sdd-architecture.mdc)

---

## 7. 데모에서 반드시 보여야 할 것

```text
① 저장소 엔드포인트 연결 · 동기화
② 단위 + 통합(A→B→C) 시나리오 생성
③ INPUT 증강 · 실행 · 성공/실패 목록 · 품질지표
④ FLOW UI에서 파라미터·배치 수정 후 재처리
⑤ “최종 승인은 사람” 구간이 분명함
```
