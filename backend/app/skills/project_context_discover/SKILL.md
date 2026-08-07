<!--
교보재 포맷: docs/05.템플릿/few-shot/template_skill.md
-->
---
name: project_context_discover
agent: platform_runner
version: 1.0.0
description: 프로젝트에 등록된 CSV/PPT 보조자료를 탐색하고 Scenario DSL 생성 컨텍스트를 선별한다.
skill_type: analysis
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.CODE.PROJECT_CONTEXT_DISCOVER
    parent_capability_id: QA.CODE.ANALYZE
    required_outputs:
      - project_context_result
capability_aliases:
  - qa.code.project_context_discover
  - project.context.discover
selectors: {}
selection_rationale: >
  프로젝트 문서 존재 여부를 먼저 판단하고 관련 청크만 Scenario DSL에 넘긴다.
inputs:
  - name: project_context_request
    type: json
    required: true
outputs:
  - name: project_context_result
    type: json
tools:
  - name: discover_project_context
    script: script/discover_context.py
    input: sample_input/discover_request.json
    output: output/project_context_result.json
    order: 1
    description: 프로젝트 manifest 탐색 → 관련 CSV/PPT 청크 선별.
---
# Project Context Discover Skill

## 1. Skill Purpose

Scenario DSL 생성 전에 프로젝트의 현업 CSV·설계 PPT 보조자료 존재 여부를 확인하고 관련 컨텍스트만 제공한다.

## 2. When to use

- `wf_scenario_dsl` 시작 단계
- 프로젝트 연결 후 업로드한 품질 보강 자료가 있을 수 있는 경우

## 3. Inputs

- `projectId`
- `projectContextManifestPath`
- `scenarioContextQuery` 또는 Interaction Graph

## 4. Outputs

- `project_context_result`: found/not_found, documents, chunks, promptContext, guardrails

## 5. Tools

- `discover_context.py`: manifest와 처리 완료 청크를 읽고 질의 관련도를 계산한다.

## 6. Process

1. 프로젝트 manifest 확인
2. ready/partial 문서만 선택
3. Graph·service 질의와 관련된 청크 선별
4. Evidence ref와 안전 규칙을 포함해 다음 Skill로 전달

## 7. Guardrails

- 문서는 보조 Evidence다. 코드 Graph·DOM·API와 join되기 전 selector/endpoint/기대값 확정 금지
- Secret·개인정보 출력 금지
- 문서가 없으면 오류가 아닌 `not_found`로 기존 생성 경로 유지

## 8. Error Handling

- manifest 없음/깨짐 → `not_found` + missingData
- 개별 chunks 누락 → 해당 문서 제외 후 계속

## 9. Examples

sample_input/discover_request.json 참고.

## 10. Non-goals

- 문서만으로 Pass/Fail 확정
- 실행 가능한 selector 발명
- 브라우저 실행

## 11. Observability

projectId, status, documentCount, chunkCount를 구조화 출력한다.

## 12. Ownership

qa_auto_platform

## 13. Compatibility

wf_scenario_dsl v1.2+ · capability QA.CODE.PROJECT_CONTEXT_DISCOVER

## 14. Changelog

- 1.0.0 — 프로젝트 품질 보강 자료 탐색 분기 추가

