<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
frontmatter + 본문 §1~§14 필수.
-->
---
name: browser_execute
agent: platform_runner
version: 1.2.0
description: Scenario DSL을 agent-browser CLI로 실행해 DOM snapshot·스크린샷·관측 요약을 남긴다.
skill_type: execution
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.BROWSER_EXECUTE
    parent_capability_id: QA.CODE.EXECUTE
    required_outputs:
      - browser_run_result
capability_aliases:
  - qa.code.browser_execute
  - browser.execute
selectors: {}
selection_rationale: >
  통합 FE 기본 실행 경로. Playwright Test Runner를 기본으로 두지 않는다.
  사용자 consent 없으면 실행 차단. Pass/Fail 확정 금지.
model_requirements:
  capabilities: [chat, code, vision]
  minimum_context: 8192
  structured_output: true
  quality_profile: run_observation
  allow_deterministic_fallback: true
inputs:
  - name: browser_execute_request
    type: json
    required: true
outputs:
  - name: browser_run_result
    type: json
tools:
  - name: execute_run
    script: script/execute_run.py
    input: sample_input/execute_request.json
    output: output/browser_run_result.json
    order: 1
    description: DSL steps → agent-browser open/snapshot/fill/click/screenshot
---
# Browser Execute Skill

## 1. Skill Purpose

Scenario DSL과 Input을 **agent-browser**로 실행해 A→API→B 관측 재료
(DOM snapshot·스크린샷·step 로그)를 만든다. Pass/Fail은 HITL.

## 2. When to use

- Workflow가 `QA.CODE.BROWSER_EXECUTE`를 요구할 때
- 건별 FE 연계 시나리오 실행

사용하지 않을 때:

- 사용자 consent 없음
- Pass/Fail·배포 확정

## 3. Inputs

- `browser_execute_request`: scenario · inputs · consent · baseUrl · headers · evidenceDir · headed
- `progressPath` (선택): 지정 시 step 단위 진행 상황을 JSON으로 증분 기록한다 (건별 interactive 실행 관측용)

## 4. Outputs

- `browser_run_result`: steps · screenshots · snapshots · missing_data · status
- 실행 종료 상태는 `WAITING_FOR_REVIEW` (HITL Pass 아님)
- **세션 관측:** `sessionEstablished` (bool) · `sessionPolicy` (시나리오에서 승계)
- **기대 결과 대조:** `verdict` (`expected_met|expected_not_met|undetermined`) ·
  `verdictReason` · `criteriaResults[]` · `blockingIssues[]` · `coverageNote`
  — 계약: [`prompts/run/verify_expected_result_system.md`](../../prompts/run/verify_expected_result_system.md)

`verdict` 없이 `status`만으로 성공을 표기하지 않는다.

## 5. Tools

- `execute_run.py`: CLI `--input`/`--output`, agent-browser subprocess

## 6. Process

1. consent 확인 (없으면 CANCELLED)
2. Test Run Header 주입 (`set headers`)
3. **세션 선행조건 처리** — `sessionPolicy` 가 인증을 요구하면 연결 정보 계정으로
   로그인 단계를 먼저 수행하고, 로그인 성공 여부를 화면 관측으로 확인한다.
   확인 실패 시 본 단계를 실행하지 않고 `blockingIssues.session_missing` 으로 종료한다.
4. open → snapshot → fill → screenshot(입력 직후) → click → wait → snapshot/screenshot(결과)
   — 같은 브라우저 세션을 유지한다 (쿠키·세션 폐기 금지)
5. evidenceDir에 artifact 저장
6. **기대 결과 대조** — 기대 기준과 관측을 항목별로 맞춰 `verdict` · 사유를 기록한다.
   화면·Endpoint 도달만으로 성공을 기록하지 않는다.
7. Pass/Fail 단정 없이 observationSummary·verdictReason만 기록

## 7. Guardrails

- 임의 sleep 금지(가능하면 wait --load)
- DOM 직접 주입 금지 · 쿠키/스토리지 조작으로 세션 위조 금지
- 로그인 계정은 연결 정보(`environment.loginId` / `environment.loginSecret`)만 사용하고 저장하지 않는다
- **Endpoint 도달·예외 없음·스크린샷 존재를 성공 근거로 쓰지 않는다**
  (401·403·405·Allowlist methods 관측 시 실패 신호로 다룬다)
- 기대 기준이 없으면 `undetermined` + `missing_data`. 성공으로 올리지 않는다
- Secret/Token 미저장
- Complete/AUTO ≠ HITL Pass
- Graph Hub 금지

## 8. Error Handling

CLI 미설치·locator 실패 → missing_data / AUTO_FAILED · failure screenshot·snapshot 보존

## 9. Examples

`sample_input/execute_request.json` → `output/browser_run_result.json`

## 10. Non-goals

- Backend 로그 수집 완성
- Binding 비교 최종 확정
- HITL Pass/Fail UI
- Playwright Test Runner를 기본 엔진으로 사용

## 11. Observability

`skill=browser_execute`, runId, step status, screenshotCount, missing_data

## 12. Ownership

qa_auto_platform. `capability_id` 변경 시 Capability Registry 동시 갱신.

## 13. Compatibility

Workflow `wf_browser_execute` step_01 (`required_capability: QA.CODE.BROWSER_EXECUTE`)과 매칭.

## 14. Changelog

- 1.0.0: Phase 09 · agent-browser CLI adapter
- 1.1.0: Phase 13 · `progressPath` step 진행 증분 기록 (건별 Type 4 관측)
- 1.2.0: 세션 선행조건(로그인 승계) · 기대 결과 대조 판정(`verdict`·사유) 계약 반영 (D-015)
