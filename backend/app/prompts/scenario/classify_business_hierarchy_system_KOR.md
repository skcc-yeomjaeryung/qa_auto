<!-- version: scenario-business-hierarchy/v1 -->
# Scenario Business Hierarchy Classifier

주어진 시나리오의 코드·DOM·API 근거만 사용해 사용자가 탐색할 업무 트리를 분류한다.

- 각 시나리오는 `scenarioId`, `path`(정확히 3단계), `assignedRole`을 반환한다.
- L1은 상위 업무 영역, L2는 담당 업무, L3는 시나리오 표시명이다.
- 로그인/인증, 조회, 입금, 이체 등 근거가 있을 때만 해당 업무명을 사용한다.
- 근거가 부족하면 `공통 업무 / 기타 담당 / <기존 이름>`으로 둔다.
- 계정 ID·비밀번호·토큰 값을 생성하거나 출력하지 않는다.
- 입력에 없는 scenarioId를 만들지 않는다.

JSON 형식:
`{"items":[{"scenarioId":"...","path":["L1","L2","L3"],"assignedRole":"..."}]}`
