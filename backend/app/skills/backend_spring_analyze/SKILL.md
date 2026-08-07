<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
frontmatter + 본문 §1~§14 필수.
-->
---
name: backend_spring_analyze
agent: platform_runner
version: 1.0.0
description: pinned Spring Backend workspace를 Python Tool로 정적 분석한다 (D-010).
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.BACKEND_SPRING_ANALYZE
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - backend_analysis_result
capability_aliases:
  - qa.code.backend_spring_analyze
  - backend.spring.analyze
selectors: {}
selection_rationale: >
  Spring Backend 정적 분석 전용 Skill. JVM JavaParser worker를 사용하지 않는다.
inputs:
  - name: backend_analyze_request
    type: json
    required: true
outputs:
  - name: backend_analysis_result
    type: json
tools:
  - name: analyze
    script: script/analyze.py
    input: sample_input/analyze_request.json
    output: output/backend_analysis_result.json
    order: 1
    description: backend-analyzer Python CLI(javalang)를 호출해 backend.json을 생성한다 (결정론, LLM 미사용).
---
# Backend Spring Analyze Skill

## 1. Skill Purpose

Phase 01에서 pin된 Backend workspace를 입력으로 Spring Endpoint·DTO·Validation·Service·Exception·MockMvc Evidence를
추출하고 `backend_analysis_result`와 `artifacts/analysis/*/backend.json`을 산출한다.
런타임은 Python 3.12 Tool이며 JVM JavaParser worker를 쓰지 않는다 (D-010).

## 2. When to use

- Workflow가 `QA.CODE.BACKEND_SPRING_ANALYZE`를 요구할 때
- Console/API가 Backend 정적 분석을 요청할 때

사용하지 않을 때:

- Frontend 분석이 필요할 때 (`frontend_analyze`)
- Pass/Fail·배포 확정이 필요할 때 (HITL)
- LLM만으로 Endpoint·DTO를 확정하려 할 때

## 3. Inputs

- `backend_analyze_request` JSON:
  - `workspacePath` (required)
  - `commitSha` (optional)
  - `analysisId` / `artifactPath` / `projectId` (optional)

## 4. Outputs

- `backend_analysis_result`: `{ ok, analysisId, artifactPath, commitSha, counts, result }`
- `result`는 schemaVersion=`backend-analysis/v1`
- Pass/Fail 판정 필드 없음

## 5. Tools

- `analyze.py`: CLI `--input`/`--output`, `backend/workers/backend-analyzer` (`python -m app.cli analyze`) 호출

## 6. Process

1. 입력 JSON 로드 · workspace 존재 확인
2. artifact 경로 결정
3. worker CLI 실행 (javalang 파서 · record 정규화)
4. 산출 JSON 로드 · counts 조립
5. LLM 호출 없음 · 미해결은 `unresolved`

## 7. Guardrails

- 근거 없는 Endpoint·DTO 추정 금지 → `unresolved` / `missing_data`
- Pass/Fail 최종 확정 금지
- 자동 배포 금지
- Hub에 없는 tool 호출 금지
- Graph Hub / `graph_manifest` 사용 금지
- JVM JavaParser Symbol Solver worker 금지

## 8. Error Handling

workspace 부재·worker 실패 시 stderr + non-zero. API는 status=error로 표면화.

## 9. Examples

`sample_input/analyze_request.json` → `output/backend_analysis_result.json`

## 10. Non-goals

- SQL 실행 계획 · DB 변경
- Kotlin · 전체 AOP/Profile 해석
- analyzer 내부 git clone (Phase 01 책임)
- Frontend AST 분석

## 11. Observability

`skill=backend_spring_analyze`, `tool=analyze`, `analysisId`, `endpoint_count` 로그

## 12. Ownership

qa_auto_platform. `capability_id` 변경 시 Capability Registry 동시 갱신.

## 13. Compatibility

Workflow `wf_backend_spring_analyze`의 `step_01`과 매칭.

## 14. Changelog

- 1.0.0: D-012 Skill Hub 재편 (Phase 03) · Python javalang worker 호출 (D-010)
