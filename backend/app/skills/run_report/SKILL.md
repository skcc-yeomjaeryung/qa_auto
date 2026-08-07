<!-- 실행 이력 전용 REPORT AGENT Skill. AML 리포트 도메인 로직을 포함하지 않는다. -->
---
name: run_report
agent: platform_runner
version: 1.1.0
description: 실행 이력·기술 검증·Evidence Package를 run-report/v1 계약의 인쇄 가능한 시각 검토 리포트로 렌더링한다.
skill_type: report_generation
language: ko
status: active
priority: 100
owner: qa_auto_platform
provided_capabilities:
  - capability_id: QA.RUN.REPORT_GENERATE
    parent_capability_id: QA.CODE.EXECUTE
    required_outputs:
      - run_report_result
capability_aliases:
  - qa.run.report_generate
  - run.report.generate
selectors: {}
selection_rationale: >
  실행 원본에 존재하는 값만 고정 스키마로 정리하는 전용 Skill이다.
  새로운 Pass/Fail·품질 판단·근거를 생성하지 않는다.
inputs:
  - name: reportSource
    type: json
    required: true
  - name: artifactPath
    type: string
    required: true
  - name: htmlPath
    type: string
    required: true
outputs:
  - name: run_report_result
    type: json
tools:
  - name: generate_run_report
    script: script/generate_report.py
    input: sample_input/run_report_source.json
    output: output/run_report_result.json
    order: 1
    description: 실행 원본을 검증하고 JSON/HTML 검토 리포트를 결정적으로 생성한다.
---
# Run Report Skill

## 1. Skill Purpose

실행 이력 상세, 시나리오, 바인딩 검증, Evidence Package를 하나의 `run-report/v1` 계약으로 묶는다.

## 2. When to use

- HITL 승인자가 실행 증적과 리포트를 함께 검토할 때
- 실행 이력을 누락 없는 JSON/HTML 파일로 내려받아야 할 때

## 3. Inputs

- `reportSource`: Backend가 Run·Scenario·Binding·Evidence에서 정규화한 원본
- `artifactPath`, `htmlPath`: 서비스가 허용한 리포트 저장 위치

## 4. Outputs

- `run_report_result`: `run-report/v1` Structured Output
- JSON/HTML artifact 경로

## 5. Tools

- `generate_report.py`: 원본 필수 키를 검사하고 고정 섹션을 렌더링한다.

## 6. Process

1. 실행·시나리오·검증·증적 source 존재 여부 확인
2. 누락값은 추정하지 않고 `missing_data`로 표시
3. 모든 필수 섹션을 JSON에 생성
4. 동일 JSON을 기반으로 시각 우선 HTML 생성
5. 실행 진행·정상/확인 필요·기술 검증·증적 수치를 Progress Bar UI Kit 패턴으로 표현
6. A 화면 → Backend → B 화면 여정, 대표 화면 3장, 단계별 전체 화면 캡처를 시각 증적으로 배치
7. JSON·스냅샷·Network·로그 원문은 본문에 펼치지 않고 파일 인벤토리와 ZIP/JSON 다운로드로 연결
8. Workflow reviewer가 구조와 artifact 참조를 확인

## 7. Guardrails

- 최종 Pass/Fail·승인 결정을 생성하지 않는다.
- 실행 이력에 없는 원인·점수·근거를 만들지 않는다.
- Secret·입력 원문을 리포트에 기록하지 않는다.
- 기술 상태와 사람의 최종 판정을 명확히 분리한다.
- HTML/PDF 본문은 스크롤에 의존하지 않으며 `pre` 기반 원시 JSON·로그 덤프를 금지한다.
- 패키지 대표 화면 수와 실행 원본의 전체 화면 캡처 수를 혼동하지 않는다.
- 시각 상태는 Figma Progress Bar UI Kit
  (`HLWN6f7fxSVMIxoZtW6SIc`, Components `799:98620`, Type 1 `266:199`/`266:196`)
  의 상태 원·수치·8px 진행 막대 구조를 프로젝트 CSS로 변환해 사용한다.
- 색·아이콘·진행률은 원본 상태와 수치만 표현하며 새로운 점수나 판정을 만들지 않는다.

## 8. Error Handling

필수 source 또는 출력 경로가 없으면 non-zero로 종료하고 Workflow를 중단한다.

## 9. Examples

`sample_input/run_report_source.json` 형식의 서비스 정규화 입력을 사용한다.

## 10. Non-goals

- AML 거래 분석 또는 의심거래 판단
- 테스트 최종 합격/불합격 결정
- 실행 재수행 또는 증적 변조

## 11. Observability

`workflow=wf_run_report`, `skill=run_report`, `runId`, `reportId`, artifact 경로를 Agent trace에 남긴다.

## 12. Ownership

qa_auto_platform

## 13. Compatibility

`wf_run_report` step_01, `run-report/v1`

## 14. Changelog

- 1.1.0: 인쇄/PDF용 시각 우선 리포트, Progress Kit 상태 표현, 전체 실행 캡처와 증적 인벤토리 분리
- 1.0.0: 실행 이력 기반 REPORT AGENT 최초 도입
