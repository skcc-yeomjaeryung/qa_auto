<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
-->
---
name: scenario_narrate
agent: platform_runner
version: 1.0.0
description: Scenario DSL seed에 LLM(또는 결정론 폴백)으로 한글 서술·바인딩 후보를 보강한다 (D-014).
skill_type: analysis
language: ko
status: active
priority: 90
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.SCENARIO_NARRATE
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - scenario_narrate_result
capability_aliases:
  - qa.code.scenario_narrate
  - scenario.narrate
selectors: {}
selection_rationale: >
  시나리오 한글 서술·바인딩 후보 전용. Pass/Fail 확정 금지. Hub 미등록 자산 발명 금지.
model_requirements:
  capabilities: [chat, code]
  minimum_context: 16384
  structured_output: true
  quality_profile: scenario_generation
  allow_deterministic_fallback: true
inputs:
  - name: scenario_narrate_request
    type: json
    required: true
outputs:
  - name: scenario_narrate_result
    type: json
tools:
  - name: narrate_and_bind
    script: script/narrate_and_bind.py
    input: sample_input/narrate_request.json
    output: output/scenario_narrate_result.json
    order: 1
    description: DSL seed → 한글 서술·request/response/bindings 후보 (LLM + fallback).
---
# Scenario Narrate Skill

## 1. Skill Purpose

`generate_dsl`이 만든 Scenario DSL seed에 한글 제목·단계 서술·바인딩 후보를 보강한다.
LLM이 불가하면 결정론 폴백을 사용한다. Pass/Fail을 확정하지 않는다.

## 2. When to use

- Workflow가 `QA.CODE.SCENARIO_NARRATE`을 요구할 때
- DSL seed artifact (`artifactPath`) 또는 `scenarios[]`가 준비된 뒤

## 3. Inputs

- `artifactPath` (scenarios.json) 또는 `scenarios` / `result.scenarios`
- `interactionGraph` (optional, Evidence 컨텍스트)
- `projectId` / `serviceId` (optional)

## 4. Outputs

- `scenario_narrate_result`: `{ ok, result: { scenarios[] }, mode: llm|deterministic }`

## 5. Tools

- `narrate_and_bind.py`: CLI `--input`/`--output`

## 6. Process

1. seed scenarios 로드
2. LLM structured JSON 시도
3. Schema/Evidence 가드 후 merge
4. 실패 시 결정론 한글 라벨·request/response 시드

## 7. Guardrails

- Pass/Fail 금지
- 근거 없는 Endpoint/기대값 발명 금지 → `missing_data`
- Hub 자산 발명 금지

## 8. Error Handling

- LLM 오류 → deterministic fallback (ok=true 유지)
- seed 없음 → ok=false, non-zero exit

## 9. Examples

sample_input/narrate_request.json 참고.

## 10. Non-goals

- HITL Pass/Fail 대행
- agent-browser 실행 (별도 `browser_execute`)
- Graph 조성 (별도 `interaction_graph`)

## 11. Observability

mode, scenarioCount 구조화 로그.

## 12. Ownership

qa_auto_platform

## 13. Compatibility

wf_scenario_dsl v1.1+ · capability QA.CODE.SCENARIO_NARRATE

## 14. Changelog

- 1.0.0 — D-014 에이전틱 시나리오 서술 Skill 추가
