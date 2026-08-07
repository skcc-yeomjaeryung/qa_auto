<!--
=============================================================================
Few-shot 참조 템플릿: SKILL.md (Skill Definition) — Test Automation
-----------------------------------------------------------------------------
실제 로드 대상이 아니라 구조/수준의 기준이다.
frontmatter는 SkillDefinition Pydantic Schema로 검증 가능해야 한다.
=============================================================================
-->
---
name: integration_plan_skill
agent: integration_plan
version: 1.0.0
description: 코드 의존관계를 분석해 A→B→C 통합 테스트 Plan 초안을 산출한다.
skill_type: analysis
language: ko
status: active
priority: 100
owner: test_automation_team
provided_capabilities:
  - capability_id: TEST.SCENARIO.INTEGRATION_PLAN
    parent_capability_id: TEST.SCENARIO.GENERATE
    required_outputs:
      - integration_plan
capability_aliases:
  - test.scenario.integration_plan
selectors: {}
selection_rationale: >
  통합 테스트 Plan 전용 Skill. 경쟁이 없으면 기본 적용.
inputs:
  - name: code_analysis
    type: json
    required: true
outputs:
  - name: integration_plan
    type: json
tools:
  - name: build_integration_plan
    script: script/build_integration_plan.py
    input: sample_input/code_analysis.json
    output: output/integration_plan.json
    order: 1
    description: 의존관계 기반 A→B→C Plan JSON 생성 (결정론 파서+규칙, LLM 초안 보조 가능)
---
# Integration Plan Skill

## 1. Skill Purpose

`code_analysis`를 입력으로 A→B→C 형태의 통합 테스트 Plan 초안(`integration_plan`)을 산출한다.
이 Skill은 프로젝트 North Star의 핵심 난제를 담당한다.

## 2. When to use

- 단위 시나리오만으로 부족하고 모듈 간 연속 호출이 필요할 때
- Workflow가 `TEST.SCENARIO.INTEGRATION_PLAN`을 요구할 때

사용하지 않을 때:

- 저장소 스냅샷/분석 artifact가 없을 때
- 단순 단일 Class 단위 테스트만 필요할 때 (UNIT_GENERATE 사용)

## 3. Inputs

- `code_analysis`: 파일·심볼·의존 엣지·missing_data 목록

## 4. Outputs

- `integration_plan`: steps[], depends_on, evidence_refs, missing_data
- FE 연계 step이 있으면 step에 `fe_verify` 힌트를 남긴다
  (url/screen_id · expected DOM 입력 · expected 후속 결과 · screenshot 의무)

## 5. Tools

- `build_integration_plan.py`: CLI `--input`/`--output`, 의존 그래프 파싱·Plan 조립

## 6. Process

1. 의존 엣지 로드 (없으면 missing_data)
2. 호출 가능 경로 후보 추출 (script/rule)
3. A→B→C Plan 초안 조립 (LLM은 설명·정렬 보조만)
4. FE 연계 step에는 Vercel MCP 검증 힌트 부착
   (`open → DOM 입력 → action → DOM 결과 → screenshot`)
5. evidence_refs 없는 단계는 단정하지 않음

## 7. Guardrails

- 근거 없는 의존 추정 금지 → `missing_data`
- Pass/Fail 최종 확정 금지
- 자동 배포 금지
- Hub에 없는 tool 호출 금지
- FE 검증 실행은 `TEST.RUN.EXECUTE` + Vercel MCP (본 Skill이 브라우저를 직접 돌리지 않음)

## 8. Error Handling

파서 실패 시 stderr + non-zero. 부분 성공 시 incomplete 플래그와 missing_data.

## 9. Examples

`sample_input/code_analysis.json` → `output/integration_plan.json`

## 10. Non-goals

- 대상 앱 실기동 E2E 전체 수행 (RUN.EXECUTE / 후속 Phase)
- FLOW UI 렌더링 (FLOW.COMPOSE / Frontend)

## 11. Observability

`skill=integration_plan`, `edge_count`, `step_count`, `missing_data_keys` 로그

## 12. Ownership

test_automation_team. capability_id 변경 시 Capability Registry 동시 갱신.

## 13. Compatibility

Workflow `test_scenario_generation_workflow`의 step_03과 매칭.

## 14. Changelog

- 1.0.0: few-shot 초기 템플릿
- 1.0.1: FE 연계 step에 Vercel MCP(DOM·스크린샷) 검증 힌트 계약 추가
