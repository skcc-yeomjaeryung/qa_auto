<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
frontmatter + 본문 §1~§14 필수.
-->
---
name: api_map
agent: platform_runner
version: 1.0.0
description: Frontend apiCalls와 Backend endpoints를 결정론적으로 매핑하고 불일치를 표시한다.
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.API_MAP
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - api_mapping_result
capability_aliases:
  - qa.code.api_map
  - api.map
selectors: {}
selection_rationale: >
  FE↔BE API 매핑 전용 Skill. Method+normalized path 우선, 다중 후보는 자동 확정하지 않는다.
inputs:
  - name: api_map_request
    type: json
    required: true
outputs:
  - name: api_mapping_result
    type: json
tools:
  - name: map_apis
    script: script/map_apis.py
    input: sample_input/map_request.json
    output: output/api_mapping_result.json
    order: 1
    description: FE/BE 분석 JSON을 join해 mappings·mismatches를 산출한다 (결정론, LLM 미사용).
---
# API Map Skill

## 1. Skill Purpose

Phase 02 `frontend.json`과 Phase 03 `backend.json`을 입력으로
HTTP Method + normalized path 기준으로 FE apiCalls ↔ BE endpoints를 매핑하고
Request/Response 필드·validation 불일치를 `api_mapping_result`로 산출한다.

## 2. When to use

- Workflow가 `QA.CODE.API_MAP`을 요구할 때
- FE/BE 분석 artifact가 모두 준비된 뒤 계약 join이 필요할 때

사용하지 않을 때:

- FE 또는 BE 분석이 없을 때
- 실제 API 호출·Pass/Fail 확정이 필요할 때

## 3. Inputs

- `api_map_request` JSON:
  - `frontendAnalysisPath` 또는 `frontendAnalysis` (required)
  - `backendAnalysisPath` 또는 `backendAnalysis` (required)
  - `projectId` / `frontendAnalysisId` / `backendAnalysisId` / `artifactPath` (optional)

## 4. Outputs

- `api_mapping_result`: `{ ok, mappingSetId, summary, result }`
- `result.schemaVersion` = `api-mapping/v1`
- 다중 후보는 `status=ambiguous` (자동 확정 금지)
- Pass/Fail 판정 필드 없음

## 5. Tools

- `map_apis.py`: CLI `--input`/`--output`, Method/Path 정규화·필드 join·mismatch 규칙

## 6. Process

1. FE/BE 분석 JSON 로드
2. path 정규화 (`${id}` / `:id` → `{id}`, baseURL 제거)
3. Method + path 점수화 · 후보 순위
4. 단일 완전일치만 `confirmed`, 다중은 `ambiguous`
5. request/response 필드·validation mismatch 기록
6. LLM 호출 없음

## 7. Guardrails

- 근거 없는 Endpoint 확정 금지 → `unmapped` / `ambiguous` / `missing_data`
- Pass/Fail 최종 확정 금지
- 다중 후보 자동 확정 금지
- Hub에 없는 tool 호출 금지
- Graph Hub / `graph_manifest` 사용 금지

## 8. Error Handling

입력 artifact 부재·JSON 파싱 실패 시 stderr + non-zero.

## 9. Examples

`sample_input/map_request.json` → `output/api_mapping_result.json`

## 10. Non-goals

- 실제 API 호출 실행
- Interaction Graph 생성 (Phase 05)
- DB Schema 매핑

## 11. Observability

`skill=api_map`, `tool=map_apis`, `mappingSetId`, `confirmed`, `ambiguous` 로그

## 12. Ownership

qa_auto_platform. `capability_id` 변경 시 Capability Registry 동시 갱신.

## 13. Compatibility

Workflow `wf_api_map`의 `step_01`과 매칭.

## 14. Changelog

- 1.0.0: Phase 04 Skill Hub 재개 · 결정론 Method/Path join
