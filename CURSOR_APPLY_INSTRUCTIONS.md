# Cursor 적용 지침

이 저장소의 SSOT는 **`docs/`** 다. Cursor Agent는 아래 순서로 읽는다.

```text
1. docs/index.md
2. AGENTS.md
3. docs/00.읽는법/*
4. docs/01.제품과완료기준/*
5. docs/04.Phase실행바이블/README.md
6. docs/index.md 의 현재 Phase 문서 1개만
```

현재 Phase: **14.배치테스트**
Backend 구조: [`docs/02.아키텍처/05.BackendSDD구조.md`](docs/02.아키텍처/05.BackendSDD구조.md) (D-012·D-016)
한 세션 = 한 Phase · Gate 실패 시 다음 금지.

메뉴 기능을 변경할 때는 [`docs/08.메뉴와워크플로우/index.md`](docs/08.메뉴와워크플로우/index.md)의
Route·API·Workflow 매핑도 함께 갱신한다.

alwaysApply 규칙 (자동 적용):

- `.cursor/rules/00-absolute-sdd-architecture.mdc`
- `.cursor/rules/01-ai-answer-format.mdc`
- `.cursor/rules/02-test-automation-domain.mdc`
- `.cursor/rules/03-post-report.mdc`
