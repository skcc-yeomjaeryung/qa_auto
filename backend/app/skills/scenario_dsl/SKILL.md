<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
-->
---
name: scenario_dsl
agent: platform_runner
version: 1.1.0
description: Interaction Graph를 실행 가능한 Scenario DSL seed로 결정론 변환한다 (후속 narrate Skill이 한글 보강).
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.SCENARIO_DSL
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - scenario_dsl_result
capability_aliases:
  - qa.code.scenario_dsl
  - scenario.dsl
selectors: {}
selection_rationale: >
  Scenario DSL 전용 Skill. Graph Evidence 기반 결정론 변환. Pass/Fail 확정 금지.
inputs:
  - name: scenario_dsl_request
    type: json
    required: true
outputs:
  - name: scenario_dsl_result
    type: json
tools:
  - name: generate_dsl
    script: script/generate_dsl.py
    input: sample_input/generate_request.json
    output: output/scenario_dsl_result.json
    order: 1
    description: Interaction Graph JSON → Scenario DSL (결정론).
---
# Scenario DSL Skill

## 1. Skill Purpose

Interaction Graph를 `scenario_dsl.schema.json`에 맞는 Scenario DSL 초안으로 변환한다.
`serviceId`를 포함해 Flow UI 딥링크 키로 쓴다.

## 2. When to use

- Workflow가 `QA.CODE.SCENARIO_DSL`을 요구할 때
- Graph artifact가 준비된 뒤 시나리오 목록에 올릴 때

## 3. Inputs

- `interactionGraphPath` 또는 `interactionGraph`
- `serviceId` (default `customer-search`)
- `projectId` / `artifactPath` (optional)

## 4. Outputs

- `scenario_dsl_result`: `{ ok, serviceId, scenarios[] }`
- Pass/Fail 필드 없음. expected는 `reviewRequired`/`unresolved` 가능.
- 시나리오마다 **세션 선행조건**을 함께 낸다.
  - `authRequired` (bool) · `sessionPolicy`
    (`no_auth` | `login_then_reuse` | `reuse_existing_session` | `fresh_login_required`)
  - 인증 뒤 화면이면 로그인 선행 step + 로그인 성공 확인 step (`blocking`)
  - 계정 값은 넣지 않고 `valueRef` (`environment.loginId` / `environment.loginSecret`)로만 참조
  - `verdictCriteria[]` — 기대 결과를 화면 관측 가능한 문장으로
  - 계약: [`prompts/scenario/session_precondition_system.md`](../../prompts/scenario/session_precondition_system.md)

## 5. Tools

- `generate_dsl.py`: CLI `--input`/`--output`

## 6. Process

1. Graph 로드
2. primaryPath·Node 타입으로 steps 조립
3. **세션 선행조건 판정** — 인증 뒤 화면(로그아웃·잔액·송금·거래내역·내 정보 등)이면
   로그인 선행 step을 시나리오에 포함하고 `sessionPolicy`를 지정한다.
   로그아웃 시나리오는 예외 없이 선행 로그인을 포함한다.
4. 부족 정보는 unresolved
5. LLM 사실 확정 없음

## 7. Guardrails

- Evidence 없는 expected 확정 금지
- Pass/Fail 금지
- Graph Hub 금지
- 로그인 없는 로그아웃·인증 화면 시나리오 생성 금지 (선행 로그인 또는 `missing_data`)
- URL 직접 접근으로 로그인·로그아웃을 대신하지 않는다 (실제 사용자 이벤트 step)
- 아이디·비밀번호 문자열 생성 금지 — `valueRef` 참조만

## 8. Error Handling

입력 부재 시 stderr + non-zero.

## 9. Examples

`sample_input/generate_request.json`

## 10. Non-goals

- 브라우저 실행 (Phase 09)
- HITL 승인

## 11. Observability

`skill=scenario_dsl`, `serviceId`, `scenarioCount`

## 12. Ownership

qa_auto_platform

## 13. Compatibility

`wf_scenario_dsl` step_01

## 14. Changelog

- 1.0.0: Phase 06 · Graph→DSL · serviceId
- 1.1.0: 세션 선행조건(로그인 필수·세션 승계) · `verdictCriteria` 계약 반영 (D-015)
