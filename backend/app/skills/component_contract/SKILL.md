<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
-->
---
name: component_contract
agent: platform_runner
version: 1.0.0
description: FE/BE 분석과 Adapter로 A/B Input·Output Component Contract를 결정론 생성한다.
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.COMPONENT_CONTRACT
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - component_contract_result
capability_aliases:
  - qa.code.component_contract
  - component.contract
selectors: {}
selection_rationale: >
  Component Contract 전용 Skill. Locator·제약·바인딩은 Evidence 기반 결정론.
  Design Spec은 hint만. Pass/Fail 확정 금지.
inputs:
  - name: component_contract_request
    type: json
    required: true
outputs:
  - name: component_contract_result
    type: json
tools:
  - name: build_contract
    script: script/build_contract.py
    input: sample_input/build_request.json
    output: output/component_contract_result.json
    order: 1
    description: FE+BE(+graph/adapter) → Component Contract (결정론).
---
# Component Contract Skill

## 1. Skill Purpose

시나리오 A/B 화면의 필수 입력, Locator, 이벤트, B 바인딩, Screenshot/mask hook을
`component_contract.schema.json` 계약으로 확정한다.

## 2. When to use

- Workflow가 `QA.CODE.COMPONENT_CONTRACT`을 요구할 때
- Scenario DSL 생성 후 Input Profile 추천(Phase 08) 전에

## 3. Inputs

- `frontendAnalysis` 또는 `frontendAnalysisPath`
- `backendAnalysis` 또는 `backendAnalysisPath` (optional)
- `interactionGraph` / path (optional)
- `adapterPath` (UI Adapter JSON/YAML)
- `scenarioId` / `serviceId` / `projectId`
- `scenarioDefinition` — 프로젝트 전체 분석을 이 시나리오 입력·출력 범위로 격리
- `designHints` (optional, annotation hint only)

## 4. Outputs

- `component_contract_result`: inputs/outputs/actions/warnings/screenshotHooks
- Pass/Fail 없음. 불안정 Locator는 `warnings` + `reviewRequired`.

## 5. Tools

- `build_contract.py`: CLI `--input`/`--output`

## 6. Process

1. Scenario DSL 입력을 범위 경계로 삼고 FE inputs의 일치 근거만 결합
2. Locator 우선순위: testId → role+name → label → id/name → css(경고)
3. Zod/HTML + BE Bean Validation 병합·불일치 표시
4. Adapter/Graph로 B 4-field binding
5. Screenshot points + mask regions

## 7. Guardrails

- Design Spec만으로 Locator/required 확정 금지
- 불안정 CSS Locator 자동 확정 금지
- Evidence 없으면 `missing_data`
- Pass/Fail·배포 금지

## 8. Error Handling

FE analysis 없으면 stderr + non-zero.

## 9. Examples

`sample_input/build_request.json`

## 10. Non-goals

- 추천값 생성 (Phase 08)
- Browser 실행 (Phase 09)
- Visual AI
- HITL 승인

## 11. Observability

`skill=component_contract`, counts.inputs/outputs/warnings/mismatches

## 12. Ownership

qa_auto_platform

## 13. Compatibility

`wf_component_contract` step_01

## 14. Changelog

- 1.0.0: Phase 07 · Component Contract Builder · Adapter SDK
