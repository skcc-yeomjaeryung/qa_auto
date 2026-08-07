# 07.작업메모리

컨텍스트가 흐려지거나 세션이 끊기면 여기에 memory를 남긴다.

## 작성 시점

- Phase 중간에 중단할 때
- Agent 컨텍스트가 길을 잃었을 때
- 사람/Agent 핸드오프 시

## 권장 파일명

```text
YYYY-MM-DD_PHASE-XX_memory.md
```

## 최소 내용

- 현재 Phase / 완료된 작업
- 미완료 TODO
- 막힌 지점 · 결정 대기
- 다음에 열 문서 경로

작성 후 반드시 [`../index.md`](../index.md) 읽기 순서를 다시 수행한다.
