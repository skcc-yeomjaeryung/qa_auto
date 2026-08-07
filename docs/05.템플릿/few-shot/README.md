# Few-shot — Workflow · SKILL.md 작성 기준 (교보재)

QA_AUTO Hub 자산 작성 시 **반드시** 아래 템플릿 구조·수준을 따른다.  
원본: `docs/_archive/20260804-legacy-sdd/work-orders/few-shot/`

| 파일 | 용도 |
|---|---|
| [`template_workflow.yml`](./template_workflow.yml) | Workflow Hub `workflow_definitions/*.yml` |
| [`template_skill.md`](./template_skill.md) | Skill Hub `skills/*/SKILL.md` |

## 강제 규칙

1. Workflow에 Graph/노드/엣지 필드를 넣지 않는다 (Workflow ≠ Graph).
2. Workflow는 Skill/Agent ID를 직접 고정하지 않는다 — `required_capabilities` / `logical_steps.required_capability` 만.
3. `required_capabilities` 항목은 `{ capability_id: ... }` 객체 형태를 권장 (교보재 기준).
4. SKILL.md frontmatter + 본문 **§1~§14** 섹션을 모두 포함한다.
5. `tools[].script` 는 CLI (`--input` / `--output`) 이고, `sample_input/` · `output/` 경로를 계약에 명시한다.
6. 계산·사실 확정은 script. LLM은 요약·후보만.

Backend 구조: [`../../02.아키텍처/05.BackendSDD구조.md`](../../02.아키텍처/05.BackendSDD구조.md)
