<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
frontmatter + 본문 §1~§14 필수.
-->
---
name: health_ping
agent: platform_runner
version: 1.0.0
description: 플랫폼 SDD Gate용 health ping을 script로 수행한다.
skill_type: utility
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.PLATFORM.HEALTH_PING
    parent_capability_id: QA.PLATFORM.BASE
    required_outputs:
      - health_ping_result
capability_aliases:
  - qa.platform.health_ping
  - health.ping
selectors: {}
selection_rationale: >
  Gate 전용 Skill. 동일 capability 경쟁이 없으므로 selectors 비움(무조건 적용).
inputs:
  - name: ping_request
    type: json
    required: false
outputs:
  - name: health_ping_result
    type: json
tools:
  - name: ping
    script: script/ping.py
    input: sample_input/ping_request.json
    output: output/health_ping_result.json
    order: 1
    description: 결정론 echo ping (LLM 미사용). CLI --input/--output.
---
# Health Ping Skill

## 1. Skill Purpose

`ping_request`(선택)를 입력으로 health ping을 수행하고 `health_ping_result`를 산출한다.
SDD Hub·Plan·ToolRuntime 경로 Gate 검증이 목적이다.

## 2. When to use

- Workflow가 `QA.PLATFORM.HEALTH_PING`을 요구할 때
- 플랫폼 기동 직후 Hub/Plan/execute smoke가 필요할 때

사용하지 않을 때:

- 대상 FE/BE 분석·매핑·시나리오 생성이 필요할 때 (전용 Skill 사용)
- Pass/Fail·배포 확정이 필요할 때 (HITL)

## 3. Inputs

- `ping_request`: 선택 JSON. echo용 필드(`notes`, `echo` 등). 없어도 동작.

## 4. Outputs

- `health_ping_result`: `{ ok, skill, tool, echo, ts }`
- Pass/Fail 판정 필드 없음 (HITL 재료만)

## 5. Tools

- `ping.py`: CLI `--input`/`--output`, 결정론 echo

## 6. Process

1. 입력 JSON 로드 (없으면 `{}`)
2. script로 echo 결과 조립
3. `ok=true`와 타임스탬프 기록
4. LLM 호출 없음

## 7. Guardrails

- 근거 없는 품질 단정 금지
- Pass/Fail 최종 확정 금지
- 자동 배포 금지
- Hub에 없는 tool 호출 금지
- Graph Hub / `graph_manifest` 사용 금지

## 8. Error Handling

파서·IO 실패 시 stderr + non-zero exit. 부분 성공 개념 없음(단일 tool).

## 9. Examples

`sample_input/ping_request.json` → `output/health_ping_result.json`

## 10. Non-goals

- FE/BE 정적 분석
- API 매핑·시나리오 DSL 생성
- agent-browser 실행

## 11. Observability

`skill=health_ping`, `tool=ping`, `ok`, `ts` 로그

## 12. Ownership

qa_auto_platform. `capability_id` 변경 시 Capability Registry 동시 갱신.

## 13. Compatibility

Workflow `wf_health_smoke`의 `step_01` (`required_capability: QA.PLATFORM.HEALTH_PING`)과 매칭.

## 14. Changelog

- 1.0.0: 교보재 few-shot 포맷으로 재작성 (D-012 · Phase 00b)
