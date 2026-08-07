# 최종 아키텍처 의사결정 (작업지시서 요약)

전체 본문: [`../architecture/DECISIONS.md`](../architecture/DECISIONS.md)

---

## 1. utils vs core

```text
utils = 공통 유틸리티
core  = Agent Core Runtime
```

`agent_core` 폴더 금지. 공통 config는 utils.

---

## 2. agents vs skills

```text
agents/{name}/agent.py = Thin Wrapper (Named Execution Boundary)
skills/{name}/SKILL.md + script = 명세 + Tool
```

---

## 3. Workflow ≠ Graph

```text
workflow_definitions/*.yml = 업무 지침 (Hub)
langgraph_runtime/         = Plan 실행 엔진 (코드)
```

Graph Hub / graph_manifest 금지.

---

## 4. Capability C안

Workflow `required_capabilities` ↔ Skill `provided_capabilities`  
canonical capability_id. parent만 일치 시 자동 실행 금지.

---

## 5. Deep Agent

Core 구현 옵션만 허용. Hub/Plan/Validator 우회 금지.

---

## 6. 도메인

```text
Sync → Analyze → Unit + Integration(A→B→C)
  → Param → Run → KPI → FLOW(사람 편집)
```

HITL: Pass/Fail·배포는 사람.
