# Phase 01 — GitHub·Local Repository 연결과 Commit 고정 수집

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


Frontend와 Backend 저장소를 GitHub URL 또는 Local Path로 등록하고, 분석 대상 Branch/Commit을 재현 가능하게 수집한다.


## 선행조건


- Phase 00 완료
- 저장소를 저장할 Workspace 디렉터리
- 공개 GitHub URL 또는 선택적 Personal Access Token


## 구현 범위


- Project와 RepositorySet 모델
- Frontend/Backend Repository 등록
- Git clone/fetch 또는 Local Path snapshot
- Branch/Tag/Commit 선택
- 파일 인벤토리와 언어/프레임워크 감지
- Ignore/Allow 정책
- Secret 마스킹


## 상세 구현 요구사항


1. 하나의 Project가 Frontend Repository와 Backend Repository를 각각 또는 함께 참조하도록 설계한다.
2. 입력 소스:
   - Public GitHub HTTPS URL
   - 인증이 필요한 GitHub URL
   - 이미 내려받은 Local Path
3. 분석 실행 전 Commit SHA를 확정하고 이후 결과에 항상 기록한다.
4. shallow clone을 기본으로 하되 사용자가 이전 Commit을 선택하면 필요한 History만 보강한다.
5. `.gitignore` 외에 플랫폼 전용 ignore 규칙을 지원한다.
6. `node_modules`, `.next`, `target`, `build`, generated files, binary, 대용량 파일을 기본 제외한다.
7. `package.json`, lockfile, `tsconfig.json`, Next config, `pom.xml`, Gradle 파일을 감지해 기술 스택을 기록한다.
8. Repository Token과 URL Credential을 로그에 남기지 않는다.
9. 동일 Repository+Commit은 재사용하고 중복 clone하지 않는다.
10. 수집 작업은 상태, 오류, 로그, 재시도 정보를 가진다.


## API·계약·데이터


필수 모델 예시:

```json
{
  "projectId": "PRJ-001",
  "repositorySetId": "RS-001",
  "repositories": [
    {
      "role": "frontend",
      "sourceType": "github",
      "url": "...",
      "branch": "main",
      "commitSha": "..."
    },
    {
      "role": "backend",
      "sourceType": "local",
      "path": "...",
      "commitSha": "..."
    }
  ]
}
```

필수 API:
- `POST /api/projects`
- `POST /api/projects/{id}/repositories`
- `POST /api/repository-sets/{id}/sync`
- `GET /api/repository-sets/{id}/files`
- `GET /api/repository-sets/{id}/status`


## UI 요구사항


- 프로젝트 생성
- Frontend/Backend 저장소 추가
- Branch/Commit 선택
- 기술 스택 감지 결과
- 수집 상태와 오류
- Credential은 입력 후 다시 평문 표시하지 않는다.


## 필수 테스트


- Public GitHub URL을 Fixture Git server 또는 로컬 bare repo로 대체한 clone 테스트
- Local Path snapshot 테스트
- Commit 고정 및 재실행 테스트
- ignore 규칙 테스트
- Token 마스킹 테스트
- 잘못된 URL, 권한 없음, Commit 없음 오류 테스트


## 완료 기준


- [ ] Frontend와 Backend 저장소를 한 Project에 연결할 수 있다.
- [ ] 분석 대상 Commit SHA가 저장되고 변경되지 않는다.
- [ ] 파일 인벤토리에 언어, 크기, hash, 역할이 기록된다.
- [ ] 생성물과 대용량 디렉터리가 제외된다.
- [ ] Credential이 API 응답, 로그, DB 평문에 노출되지 않는다.
- [ ] 동일 Commit 재수집은 캐시를 사용한다.


## 제외 범위


- GitHub PR Review Comment 작성
- 조직 전체 Repository 자동 검색
- GitLab/Bitbucket 정식 지원


## 산출물


- Repository 수집 서비스
- DB Migration
- API와 UI
- 저장소 감지 규칙
- 테스트 Fixture
- 운영·보안 문서


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-01.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
