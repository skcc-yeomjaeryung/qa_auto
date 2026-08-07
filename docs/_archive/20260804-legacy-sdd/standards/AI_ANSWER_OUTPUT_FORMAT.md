# AI Answer 출력 포맷

상세 계약 · Cursor 규칙: [`.cursor/rules/01-ai-answer-format.mdc`](../../.cursor/rules/01-ai-answer-format.mdc)

---

## 필수 시각 구조

모든 Assistant 메시지(가이드·보고·RAG·Reduce 요약 포함)는 다음을 따른다.

1. **핵심 내용** → 옅은 회색 블록용 fence  
   ```` ```핵심 내용 ````
2. **요약** → 메시지 최하단 `**요약: …**`
3. plain text만으로 핵심을 길게 나열하지 않는다.

---

## Guardrail

- Evidence/Artifact 없는 추정·가설 금지
- 테스트 Pass/Fail·배포 확정은 심사자(개발PL/QA) 책임
- 내부 경로명·기술 스택 자랑을 사용자 문구에 노출하지 않는다

---

## 권장 톤

- BEST: `동기화된 저장소 분석 기준으로 설명합니다.` / `실행 결과 artifact 기준으로 설명합니다.`
- WORST: `case_grounded_qa 경로로…` 같은 내부 모듈명 노출
