# adapter-sdk

사내/커스텀 SI 컴포넌트·저장소·증적 확장점.

## Phase 07 — UI Adapter

- Types: `UiAdapterConfig`, `UiComponentMapping`, `UiBindingMapping`
- Example: `examples/ui-adapter.customer-search.yml` / `.json`
- Runtime consumer: `backend/app/skills/component_contract`

`BizInput` / `BizButton` 등 커스텀 컴포넌트를 native fill/click 이벤트·Locator 우선순위로 매핑한다.
Design Spec annotation은 hint만 — Locator/required는 코드 Evidence가 우선이다.
