<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
frontmatter + 본문 §1~§14 필수.
-->
---
name: interaction_graph
agent: platform_runner
version: 1.0.0
description: FE/BE 분석과 API 매핑을 결합해 A→API→B Interaction Graph를 결정론적으로 조립한다.
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.INTERACTION_GRAPH
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - interaction_graph_result
capability_aliases:
  - qa.code.interaction_graph
  - interaction.graph
selectors: {}
selection_rationale: >
  Interaction Graph 전용 Skill. FE+BE+api-mapping artifact를 결정론 규칙으로 조립한다.
inputs:
  - name: interaction_graph_request
    type: json
    required: true
outputs:
  - name: interaction_graph_result
    type: json
tools:
  - name: compose_graph
    script: script/compose_graph.py
    input: sample_input/compose_request.json
    output: output/interaction_graph_result.json
    order: 1
    description: FE/BE/map JSON으로 A→API→B Node/Edge·분기를 조립한다 (결정론, LLM 미사용).
---
# Interaction Graph Skill

## 1. Skill Purpose

Phase 02 `frontend.json`, Phase 03 `backend.json`, Phase 04 `api-mapping.json`을 입력으로
`screen(A) → … → screen(B) → binding` Interaction Graph를 조립한다.
Flow UI(Figma User Flow Kit D-008)가 바인딩할 Node/Edge·branch·Evidence를 산출한다.

## 2. When to use

- Workflow가 `QA.CODE.INTERACTION_GRAPH`를 요구할 때
- FE/BE 분석과 confirmed API 매핑이 준비된 뒤 A→B 흐름 시각화가 필요할 때

사용하지 않을 때:

- FE/BE/map artifact가 없을 때
- 실제 브라우저 실행·Pass/Fail 확정이 필요할 때

## 3. Inputs

- `interaction_graph_request` JSON:
  - `frontendAnalysisPath` 또는 `frontendAnalysis` (required)
  - `backendAnalysisPath` 또는 `backendAnalysis` (required)
  - `apiMappingPath` 또는 `apiMapping` (required)
  - `projectId` / `repositorySetId` / `graphId` / `artifactPath` (optional)

## 4. Outputs

- `interaction_graph_result`: `{ ok, graphId, nodeCount, edgeCount, result }`
- `result.schemaVersion` = `interaction-graph/v1`
- Node/Edge Evidence·confidence·verificationStatus 포함
- Pass/Fail 판정 필드 없음

## 5. Tools

- `compose_graph.py`: CLI `--input`/`--output`, 결정론 그래프 조립·경로 DFS

## 6. Process

1. FE/BE/map JSON 로드
2. Screen A/B · input · event · validation · FE API · BE endpoint · DTO · service · route · binding 조립
3. happy / validation_failed / customer_not_found branch 표시
4. 안정적 Node ID로 중복 병합
5. LLM 호출 없음

## 7. Guardrails

- 근거 없는 Endpoint·바인딩 확정 금지 → `unresolved` / `missing_data`
- Pass/Fail 최종 확정 금지
- Graph Hub / `graph_manifest` 사용 금지
- Hub에 없는 tool 호출 금지

## 8. Error Handling

입력 artifact 부재·JSON 파싱 실패 시 stderr + non-zero.

## 9. Examples

`sample_input/compose_request.json` → `output/interaction_graph_result.json`

## 10. Non-goals

- Scenario DSL 생성 (Phase 06)
- 브라우저 실행 / HITL
- Figma 디자인 생성

## 11. Observability

`skill=interaction_graph`, `tool=compose_graph`, `graphId`, `nodeCount`, `edgeCount` 로그

## 12. Ownership

qa_auto_platform. `capability_id` 변경 시 Capability Registry 동시 갱신.

## 13. Compatibility

Workflow `wf_interaction_graph`의 `step_01`과 매칭.
Figma ref: fileKey `qpZeClozlSVQd6j8Od8P9x` · kit `0:1` · Example `1:319`.

## 14. Changelog

- 1.0.0: Phase 05 Skill Hub · 결정론 A→API→B 조립
