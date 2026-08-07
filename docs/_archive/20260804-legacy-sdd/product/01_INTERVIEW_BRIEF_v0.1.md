# 인터뷰 브리프 v0.1 — 테스트시나리오 자동생성 · FLOW 플랫폼

작성일: 2026-08-03  
원문(교보재 쪽 메모): `NH_AML_SDD_CURSOR_WORK_ORDER_FINAL/docs/report/2026-08-03/테스트자동화_AI_hackerton.md`  
상세 지침 색인: [`docs/index.md`](../index.md)

---

## 1. 미션

대형 SI 통합 사업을 이끌어 온 플랫폼 총괄 관점에서,
AI Hackerton에 보여줄 **테스트자동화 플랫폼**을 만든다.

주 사용자: **개발 PL**, **QA 테스트품질담당자**.

---

## 2. 중요 아키텍처 (영역별 지침 링크)

각 영역 개발 시 아래 상세 지침을 **반드시** 따른다.
(빈 링크는 `docs/index.md`로 대체한다.)

| 영역 | 지침 |
|---|---|
| 1) Agent | [`docs/standards/AGENT_RUNTIME.md`](../standards/AGENT_RUNTIME.md) · [`docs/index.md#agent`](../index.md#agent) |
| 2) Backend | [`docs/standards/BACKEND_STRUCTURE.md`](../standards/BACKEND_STRUCTURE.md) · [`docs/index.md#backend`](../index.md#backend) |
| 3) Frontend | [`docs/standards/FRONTEND_FLOW_UI.md`](../standards/FRONTEND_FLOW_UI.md) · [`docs/index.md#frontend`](../index.md#frontend) |

공통 절대규칙: [`.cursor/rules/00-absolute-sdd-architecture.mdc`](../../.cursor/rules/00-absolute-sdd-architecture.mdc)

---

## 3. 플랫폼 목표

- 다수 개발자가 올린 공용 저장소(git/svn) 소스에 대해 AI로 테스트를 쉽게 한다.
- 플랫폼이 저장소 **엔드포인트**로 연결하고 **소스를 동기화**한다.
- 동기화 소스 기반으로 아래 3기능을 제공한다.

---

## 4. 기능 1 — 테스트 시나리오 생성

저장소에 업로드된 파일 기반으로 시나리오를 자동 생성한다.
주 언어는 **JAVA**이나 다른 언어도 있을 수 있다. 따라서 언어·파일 유형에 덜 묶인 분석이 중요하다.

필수 포인트:

- 코드(주석·formatter를 강하게 쓰도록 유도)를 분석한다.
- 대상 저장소의 backend / frontend를 AI가 **기동**해 정확한 테스트를 수행할 수 있어야 한다 (단계적 구현, Non-goals 참고).
- 시나리오는 **단위 테스트** 또는 **통합 테스트**일 수 있다.
- Swagger식 API 파라미터 테스트만이 아니라 **화면과 연결**된 테스트가 필요하다.
  - 통합 FE 기본: **Vercel MCP** — DOM으로 입력값·후속 결과 관측 + 단계별 스크린샷 evidence.
  - Playwright MCP는 보완·동등 경로. MCP 사용 전 사용자 동의.
- **단위 테스트**: 하나의 거래/서비스 ID 단위 (Java Class, Python `.py` 등).
- **통합 테스트**: A파일 → B파일 → C파일처럼 의존·연속성이 있으면
  AI가 A→B→C 순차 호출 Plan을 **직접** 세운다.

> **프로젝트 핵심:** 의존관계 분석 → 유의미한 통합 시나리오 생성·실행·결과 도출.

도메인 Guardrail: [`.cursor/rules/02-test-automation-domain.mdc`](../../.cursor/rules/02-test-automation-domain.mdc)

---

## 5. 기능 2 — INPUT 생성·증강 · 테스트 수행

- 기능 1의 단위/통합 시나리오 결과물을 기반으로 INPUT 데이터를 자동 생성·증강한다.
- 시나리오 기반 테스트를 수행하고 결과를 확인한다.
- 성공/실패를 사용자가 **시각적 목록**으로 본다.
- 확인 가능한 **품질지표**를 보여준다.

---

## 6. 기능 3 — 등록 시나리오 FLOW 제공

- 기능 1로 만든 시나리오 목록을 확인하고, 클릭 시 **FLOW 기반 UI/UX**를 제공한다.
- 등록된 시나리오 정보로 화면에서:
  - 재처리
  - 파라미터 입력·수정
  - 플로우 컴포넌트 배치 편집
  을 자유롭게 할 수 있어야 한다.

### Figma 참조 (FLOW 컴포넌트)

Figma MCP로 아래를 참고한다. 계약 상세: [`FRONTEND_FLOW_UI.md`](../standards/FRONTEND_FLOW_UI.md)

| 요소 | URL |
|---|---|
| Overview A | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=1-319 |
| Overview B | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=0-1 |
| Conditions | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=1-531 |
| Nodes | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=7-511 |
| Comments | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=1-499 |
| Screens | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=1-289 |
| Arrows/Solid | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=1-88 |
| Arrows/Dotted | https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-?node-id=1-230 |

---

## 7. Capability 초안 (구현 시 canonical ID)

```text
TEST.REPO.SYNC
TEST.CODE.ANALYZE
TEST.SCENARIO.UNIT_GENERATE
TEST.SCENARIO.INTEGRATION_PLAN
TEST.PARAM.AUGMENT
TEST.RUN.EXECUTE
TEST.FLOW.COMPOSE
TEST.QUALITY.KPI
```

Hub/Capability 규칙: [`HUB_CAPABILITY_AND_SKILL.md`](../standards/HUB_CAPABILITY_AND_SKILL.md)
