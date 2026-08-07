# Phase 02 — TypeScript·React·Next.js Frontend 의미 분석

## 이 프롬프트의 역할

당신은 대형 SI 프로젝트용 AI Code-to-E2E 관통 테스트 플랫폼의 수석 개발자다.  
프로젝트 루트에서 먼저 다음 문서를 읽고 현재 코드 상태를 점검하라.

- `AGENTS.md`
- `README.md`
- `index.md`
- `00_common_context.md`
- `00_pilot_definition_of_done.md`
- 관련 JSON Schema와 이전 Phase 완료 보고서

계획 문서만 작성하지 말고, **실제 구현·테스트·문서화·완료 보고까지 한 번의 작업으로 수행**하라.  
모호한 부분은 기존 코드와 공통 문서를 근거로 합리적인 기본값을 채택하고, 구현을 중단하는 질문으로 돌리지 말라.

## Phase 목표


Frontend 저장소에서 화면, 컴포넌트, 입력 속성, 이벤트, Validation, API 호출, Route 전환, 기존 브라우저 테스트(Playwright 등)를 근거와 함께 추출한다.  
참고: 플랫폼 Runtime 실행 엔진은 Phase 09의 **agent-browser MCP**이며, 이 Phase의 Playwright Parser는 대상 저장소 Evidence 추출용이다.


## 선행조건


- Phase 01 완료
- Commit이 고정된 Frontend Workspace
- TypeScript 설정과 의존성 메타데이터 접근 가능


## 구현 범위


- TypeScript Compiler API/ts-morph 기반 Project 분석
- React/JSX Adapter
- Next.js App Router/Pages Router Adapter
- React Hook Form, Zod/Yup 기본 Adapter
- fetch, Axios, React Query 기본 Adapter
- Playwright Test Parser
- Frontend Analysis Result 저장


## 상세 구현 요구사항


1. `tsconfig.json` path alias, project reference, barrel export, re-export를 최대한 해결한다.
2. Next.js Route를 다음에서 추출한다.
   - `app/**/page.tsx`
   - `pages/**`
   - `Link href`
   - `router.push/replace`
   - `redirect`
   - 동적 segment
3. React 컴포넌트에서 다음을 추출한다.
   - Props
   - input/select/checkbox/radio/button/form/table/modal
   - `data-testid`, label, role, name
   - `required`, min/max, minLength/maxLength, pattern
   - `onClick`, `onSubmit`, `onChange`, `onBlur`, keyboard event
   - Handler call chain
4. Form Schema와 컴포넌트 필드를 연결한다.
5. API 호출에서 method, normalized path, request body/query/path param, response type 후보를 추출한다.
6. Handler에서 API 호출 후 Route 이동, State 갱신, 오류 분기를 추출한다.
7. Playwright Test에서 `goto/fill/click/expect/toHaveURL` 등을 Scenario Evidence로 추출한다.
8. 모든 결과에 file/line/extractor/confidence를 포함한다.
9. 동적 dispatch나 해결 불가능 Symbol은 숨기지 말고 `unresolved`로 기록한다.
10. 전체 원본 코드를 LLM에 전달하지 않고 구조화된 결과를 저장한다.
11. 증분 분석을 위해 file hash와 dependency invalidation을 지원한다.


## API·계약·데이터


Frontend Analysis Result 최소 구조:

```json
{
  "screens": [],
  "components": [],
  "inputs": [],
  "events": [],
  "validations": [],
  "apiCalls": [],
  "routeTransitions": [],
  "bindings": [],
  "existingTests": [],
  "unresolved": []
}
```

필수 API:
- `POST /api/analyses/frontend`
- `GET /api/analyses/{id}/frontend/screens`
- `GET /api/analyses/{id}/frontend/components/{componentId}`
- `GET /api/analyses/{id}/frontend/unresolved`


## UI 요구사항


- Frontend 분석 실행
- 화면 목록과 Route
- 화면별 컴포넌트 트리
- 이벤트→Handler→API→Route 후보
- Evidence 파일/라인 링크
- Unresolved와 Confidence 표시


## 필수 테스트


Golden Fixture를 최소 다음 형태로 만든다.

- Next.js App Router 고객조회
- Pages Router 예제
- React Hook Form + Zod
- Axios/fetch/React Query
- 직접 `router.push`
- Wrapper Button
- path alias
- dynamic dispatch 미해결 예제
- 기존 Playwright Test

Snapshot/Golden 결과가 의도치 않게 변하면 테스트가 실패해야 한다.


## 완료 기준


- [ ] A 고객조회 화면 Route와 주요 컴포넌트를 찾는다.
- [ ] `customerId` 필수·형식 제약을 찾는다.
- [ ] 조회 이벤트와 실제 Handler를 연결한다.
- [ ] `POST /api/customers/search`를 찾는다.
- [ ] 정상 경로 B 화면 Route와 오류/제한 분기 후보를 찾는다.
- [ ] 기존 Playwright Test를 Evidence로 연결한다.
- [ ] 모든 결과가 Commit SHA와 파일 라인을 가진다.
- [ ] 해석 실패가 조용히 누락되지 않는다.


## 제외 범위


- 모든 상태관리 라이브러리 완전 지원
- Runtime DOM 탐색
- Visual regression
- Vue/Angular


## 산출물


- Frontend Analyzer Worker
- Framework Adapter 구조
- Analysis API
- 결과 UI
- Golden Fixture와 테스트
- Analyzer 확장 가이드


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-02.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
