---
skill_id: backend_spring_analyze_v1
name: backend_spring_analyze
version: 1.0.0
description: >
  Phase 01 workspace(Git URL clone 또는 절대경로)의 Spring Boot 소스를
  Python Tool로 정적 분석한다. JVM JavaParser worker를 사용하지 않는다 (D-010).
skill_type: analysis
language: ko
status: active
---

# Backend Spring Analyze Skill

## Capability

- Endpoint / DTO / Bean Validation / Service / Exception / MockMvc Evidence 추출
- Structured Output: `backend-analysis/v1` (Pydantic)

## Tools (script)

| order | script | 역할 |
|---|---|---|
| 1 | `script/spring_parse.py` | javalang 기반 Spring 일괄 추출·조립 |

## Inputs

- `workspacePath` (required) — Phase 01 sync 결과
- `commitSha` (optional)

## Outputs

- `BackendAnalysisResult` JSON

## Guardrail

- Endpoint·DTO·Validation 확정은 script만
- LLM 요약은 선택이며 사실 덮어쓰기 금지
- 미해석은 `unresolved`
