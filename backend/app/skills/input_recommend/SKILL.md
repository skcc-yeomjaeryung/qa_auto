<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
-->
---
name: input_recommend
agent: platform_runner
version: 1.0.0
description: Component Contract·Fixture·테스트·Catalog로 추천 INPUT과 Input Profile을 결정론 생성한다.
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.INPUT_RECOMMEND
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - input_recommend_result
capability_aliases:
  - qa.code.input_recommend
  - input.recommend
selectors: {}
selection_rationale: >
  Input 추천 전용 Skill. Fixture/Test/Schema/Catalog 우선.
  Sheet·Design Spec은 보조. 식별자 무작위 금지. Pass/Fail 확정 금지.
inputs:
  - name: input_recommend_request
    type: json
    required: true
outputs:
  - name: input_recommend_result
    type: json
tools:
  - name: recommend
    script: script/recommend.py
    input: sample_input/recommend_request.json
    output: output/input_recommend_result.json
    order: 1
    description: Contract+Catalog → recommendations / optional Input Profile
---
# Input Recommend Skill

## 1. Skill Purpose

Component Contract와 Fixture·existing test·Schema·Best Practice Catalog를 결합해
정상/경계/오류/업무상태 추천값과 배치용 Input Profile 초안을 만든다.

## 2. When to use

- Workflow가 `QA.CODE.INPUT_RECOMMEND`을 요구할 때
- Phase 07 Contract 이후 건별/배치 실행 준비 시

## 3. Inputs

- `componentContract` / path (required)
- `frontendAnalysis` / `backendAnalysis` (optional)
- `testDataSheet` (optional, reviewRequired if unapproved)
- `seed` / `budget` / `buildProfile`

## 4. Outputs

- `input_recommend_result`: recommendations + defaults + generator.seed
- optional `profile` draft (status=DRAFT)

## 5. Tools

- `recommend.py`: CLI `--input`/`--output`

## 6. Process

1. Fixture → existing test → schema → sheet → catalog 순 후보 수집
2. category 분류 (happy/business/not_found/invalid/missing/boundary)
3. 건별 defaults = happy_path
4. 배치 cases = category pairwise 축소 + budget

## 7. Guardrails

- 식별자 무작위 생성 금지
- destructive 데이터 금지
- Sheet/Design Spec만으로 기대값 확정 금지
- PII/Secret은 mask
- Pass/Fail 금지

## 8. Error Handling

componentContract 없으면 stderr + non-zero.

## 9. Examples

`sample_input/recommend_request.json`

## 10. Non-goals

- 운영 DB 조회
- 무제한 fuzzing
- HITL 최종 승인 자동화
- Browser 실행 (Phase 09)

## 11. Observability

`skill=input_recommend`, recommendationId, counts, generator.seed

## 12. Ownership

qa_auto_platform

## 13. Compatibility

`wf_input_recommend` step_01

## 14. Changelog

- 1.0.0: Phase 08 · recommend + Input Profile draft
