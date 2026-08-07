<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
frontmatter + 본문 §1~§14 필수.
-->
---
name: frontend_analyze
agent: platform_runner
version: 1.0.0
description: pinned Frontend workspace를 정적 분석해 screens·events·API·Route 산출물을 만든다.
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.FRONTEND_ANALYZE
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - frontend_analysis_result
capability_aliases:
  - qa.code.frontend_analyze
  - frontend.analyze
selectors: {}
selection_rationale: >
  Frontend 정적 분석 전용 Skill. 동일 capability 경쟁이 없으므로 selectors 비움.
inputs:
  - name: frontend_analyze_request
    type: json
    required: true
outputs:
  - name: frontend_analysis_result
    type: json
tools:
  - name: analyze
    script: script/analyze.py
    input: sample_input/analyze_request.json
    output: output/frontend_analysis_result.json
    order: 1
    description: ts-morph worker CLI를 호출해 frontend.json artifact를 생성한다 (결정론, LLM 미사용).
---
# Frontend Analyze Skill

## 1. Skill Purpose

Phase 01에서 pin된 Frontend workspace(`workspacePath` · `commitSha`)를 입력으로
화면·컴포넌트·이벤트·validation·API 호출·Route·Playwright Evidence를 추출하고
`frontend_analysis_result`와 `artifacts/analysis/*/frontend.json`을 산출한다.

## 2. When to use

- Workflow가 `QA.CODE.FRONTEND_ANALYZE`를 요구할 때
- Console/API가 Frontend 정적 분석을 요청할 때

사용하지 않을 때:

- Backend(Spring) 분석이 필요할 때 (전용 Skill)
- Pass/Fail·배포 확정이 필요할 때 (HITL)
- Design Spec만으로 Endpoint를 확정하려 할 때

## 3. Inputs

- `frontend_analyze_request` JSON:
  - `workspacePath` (required): pinned FE workspace
  - `commitSha` (optional)
  - `analysisId` (optional): artifact 디렉터리 id
  - `artifactPath` (optional): 출력 frontend.json 절대 경로
  - `projectId` (optional): 추적 메타

## 4. Outputs

- `frontend_analysis_result`: `{ ok, analysisId, artifactPath, commitSha, counts, result }`
- `result`는 schemaVersion=`frontend-analysis/v1` 구조
- Pass/Fail 판정 필드 없음

## 5. Tools

- `analyze.py`: CLI `--input`/`--output`, `backend/workers/frontend-analyzer` (ts-morph) 호출

## 6. Process

1. 입력 JSON 로드 · workspace 존재 확인
2. artifact 경로 결정 (`artifacts/analysis/{analysisId}/frontend.json`)
3. worker CLI `tsx src/cli.ts analyze …` 실행
4. 산출 JSON 로드 · counts 조립 · script output 기록
5. LLM 호출 없음 · 미해결은 `unresolved` 배열로 유지

## 7. Guardrails

- 근거 없는 Endpoint·Route 추정 금지 → `unresolved` / `missing_data`
- Pass/Fail 최종 확정 금지
- 자동 배포 금지
- Hub에 없는 tool 호출 금지
- Graph Hub / `graph_manifest` 사용 금지
- Design Spec만으로 API 확정 금지

## 8. Error Handling

workspace 부재·worker 실패 시 stderr + non-zero. API 계층은 status=error로 표면화.

## 9. Examples

`sample_input/analyze_request.json` → `output/frontend_analysis_result.json`

## 10. Non-goals

- Runtime DOM 탐색 · agent-browser 실행
- Backend Spring 분석
- API 매핑·Scenario DSL 확정

## 11. Observability

`skill=frontend_analyze`, `tool=analyze`, `analysisId`, `screen_count`, `api_count` 로그

## 12. Ownership

qa_auto_platform. `capability_id` 변경 시 Capability Registry 동시 갱신.

## 13. Compatibility

Workflow `wf_frontend_analyze`의 `step_01` (`required_capability: QA.CODE.FRONTEND_ANALYZE`)과 매칭.

## 14. Changelog

- 1.0.0: D-012 Skill Hub 재편 (Phase 02) · ts-morph worker 호출
