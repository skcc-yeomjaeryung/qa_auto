# Frontend · FLOW UI 표준 (React)

색인: [`../index.md#frontend`](../index.md#frontend)

---

## 1. 원칙

- React 기반
- 시나리오 목록 → 상세 **FLOW 뷰**가 핵심 UX
- FLOW에서 **재처리 · 파라미터 수정 · 컴포넌트 배치 편집**이 가능해야 한다
- 성공/실패 목록 · 품질지표를 시각적으로 제공한다
- 최종 Pass/Fail 확정 UI는 **사람 액션**으로 분리한다 (AI 단정 문구 금지)

---

## 2. 화면 골격 (MVP 개념)

```text
Repo Connect / Sync
Scenario List (unit | integration)
Scenario FLOW Editor
  - Nodes / Conditions / Screens / Arrows / Comments
Run Results + Quality KPI
```

---

## 3. Figma 계약 (User-Flow-Kit)

디자인 구현 시 **Figma MCP**로 레이어를 확인한다.

| 레이어 | node 참고 |
|---|---|
| Kit overview | `node-id=1-319`, `node-id=0-1` |
| Conditions | `node-id=1-531` |
| Nodes | `node-id=7-511` |
| Comments | `node-id=1-499` |
| Screens | `node-id=1-289` |
| Arrows/Solid | `node-id=1-88` |
| Arrows/Dotted | `node-id=1-230` |

파일:  
https://www.figma.com/design/qpZeClozlSVQd6j8Od8P9x/User-Flow-Kit--Community---Copy-

문서에 URL만 복사하고 끝내지 말고, 구현 Phase에서 MCP로 Layers를 대조한다.

---

## 4. FLOW 데이터 계약 (개념)

```text
flow_graph:
  nodes[]: { id, type, label, scenario_ref, screen_ref? }
  edges[]: { from, to, style: solid|dotted, condition_ref? }
  conditions[]: { id, expression_or_label }
  comments[]: { id, anchor, text }
  params[]: { key, value, source: inferred|user }
```

사람 편집분은 revision으로 남기고, AI 초안과 구분한다.

---

## 5. 통합 FE 검증 — Vercel MCP (기본) · Playwright (보완)

통합 시나리오가 Frontend를 거치면 **Vercel MCP**를 기본 검증 경로로 둔다.
상세 Guardrail: [`.cursor/rules/02-test-automation-domain.mdc`](../../.cursor/rules/02-test-automation-domain.mdc) §5.1 · §7

```text
open → DOM(입력값) → action → DOM(후속 결과) → screenshot(evidence)
```

| 항목 | 규칙 |
|---|---|
| 입력값 | expected INPUT ↔ DOM value/selected/checked 대조. 없으면 `missing_data` |
| 후속 결과 | 다음 화면의 관측 가능 DOM만 근거 |
| 스크린샷 | 최소 “입력 직후” + “결과 화면”. step마다 권장. runtime artifact로 저장 |
| FLOW 연결 | Screen 노드와 `step_id` / `screen_id`로 스크린샷·DOM 관측을 연결 |
| HITL | AI는 관측 요약만. Pass/Fail·배포는 사람 |

보완:

- Playwright MCP는 컴포넌트·E2E 세부 자동화 보완 경로다.
- **Vercel MCP / Playwright MCP 사용 전 사용자에게 사용 여부를 문의**한다.
- 무단으로 대상 시스템을 공격적으로 크롤/파괴하지 않는다.

---

## 6. Context AI (후속)

1차 MVP에서 AML식 ScreenContext를 이식하지 않는다.
화면 KPI Q&A가 필요해지면 NH 교보재 Context AI 패턴을 **후속**으로 도입한다.
(`docs/product/BACKLOG_AND_NON_GOALS.md` B05)
