# Hub · Capability · AgentSpec

색인: [`../index.md`](../index.md)

---

## Hub vs 비-Hub

| 자산 | Hub? | 누가 고치나 |
|---|---|---|
| `workflow_definitions/*.yml` | **예** | 업무 목표·단계·intent |
| `skills/*/SKILL.md` | **예** | capability·tool 계약 |
| `capability_definitions/*.yml` | 아니오 | 플랫폼 — 신규 capability_id |
| `agents/specs/*.yml` | 아니오 | 플랫폼 — 허용 Skill·금지 행위 |
| `agents/*/agent.py` | 아니오 | 개발 — thin wrapper |

Catalog/멘션/Draft에 올리는 업무 자산은 Hub 2개뿐이다.

---

## Capability 매칭 흐름

```mermaid
sequenceDiagram
  participant W as WorkflowHub
  participant C as CapabilityRegistry
  participant S as SkillHub
  participant P as Planner
  participant A as AgentSpec
  participant X as Adapter

  W->>P: logical_step.required_capabilities
  P->>C: normalize capability_id
  C-->>P: canonical ID or fail
  P->>S: exact provided_capabilities match
  S-->>P: selected Skill plus tools
  P->>A: resolve_execution_agent
  A-->>P: Plan.agent id
  Note over P: Plan JSON 확정
  X->>A: allowed_skills gate
  X->>S: tool script 실행
```

---

## 규칙

- alias는 정규화용이며 실행 기준이 아니다.
- parent capability만 일치하면 자동 실행하지 않는다.
- 경쟁 Skill은 `selectors` / `priority`로 결정론 선택 (LLM 미사용).
- few-shot: [`../work-orders/few-shot/`](../work-orders/few-shot/)
