# Phase 03 — Java·Spring Boot Backend 의미 분석

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


Backend 저장소에서 Endpoint, Request/Response DTO, Bean Validation, Service 진입점, 예외/상태 분기, JUnit·MockMvc·REST Assured 테스트를 근거와 함께 추출한다.


## 선행조건


- Phase 01 완료
- Commit이 고정된 Backend Workspace
- Maven/Gradle metadata 접근 가능


## 구현 범위


- JavaParser + Symbol Solver
- Spring MVC Adapter
- Bean Validation Adapter
- JUnit 5, MockMvc, REST Assured Test Adapter
- Maven/Gradle classpath 해석
- Backend Analysis Result 저장


## 상세 구현 요구사항


1. Classpath와 sourceSet을 분석해 Symbol Solver 정확도를 확보한다.
2. 다음 Annotation을 우선 지원한다.
   - `@RestController`, `@Controller`
   - `@RequestMapping`
   - `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`
   - `@RequestBody`, `@RequestParam`, `@PathVariable`
   - `@Valid`, `@Validated`
3. Request DTO 필드, 타입, required, pattern, size, min/max, enum을 추출한다.
4. Response DTO 필드와 JSON name을 추출한다.
5. Controller→Service 호출과 주요 조건 분기를 추출한다.
6. `@ControllerAdvice`, Exception Handler, HTTP Status 후보를 추출한다.
7. JUnit/MockMvc/REST Assured에서 입력값, endpoint, status, body assertion을 추출한다.
8. Lombok, record, getter/setter 생성 요소는 가능한 범위에서 해석한다.
9. Interface 구현체가 여러 개인 경우 후보와 조건을 기록한다.
10. Reflection, Profile, AOP로 인해 확정할 수 없는 정보는 `unresolved`로 기록한다.
11. 모든 결과에 Commit, 파일/라인, extractor, confidence를 포함한다.


## API·계약·데이터


Backend Analysis Result 최소 구조:

```json
{
  "endpoints": [],
  "requestDtos": [],
  "validations": [],
  "services": [],
  "responseDtos": [],
  "exceptions": [],
  "existingTests": [],
  "unresolved": []
}
```

필수 API:
- `POST /api/analyses/backend`
- `GET /api/analyses/{id}/backend/endpoints`
- `GET /api/analyses/{id}/backend/endpoints/{endpointId}`
- `GET /api/analyses/{id}/backend/unresolved`


## UI 요구사항


- Backend 분석 실행
- Endpoint 목록
- Controller→Request DTO→Service→Response DTO 흐름
- Validation 제약
- 기존 테스트 Evidence
- 예외/HTTP Status
- Unresolved와 Confidence


## 필수 테스트


Golden Fixture 최소 구성:

- Class-level + method-level RequestMapping 조합
- RequestBody Bean Validation
- PathVariable/RequestParam
- Response record/class
- ControllerAdvice
- Service interface + implementation
- Lombok DTO
- MockMvc 테스트
- REST Assured 테스트
- 미해결 Profile Bean


## 완료 기준


- [ ] `POST /api/customers/search` Endpoint를 찾는다.
- [ ] `CustomerSearchRequest.customerId` 제약을 찾는다.
- [ ] `CustomerResponse` 필드를 찾는다.
- [ ] Controller와 Service 호출을 연결한다.
- [ ] 정상/제한/미존재 또는 예외 분기 Evidence를 찾는다.
- [ ] JUnit/MockMvc/REST Assured 값을 추출한다.
- [ ] 모든 결과가 Commit과 파일 라인을 가진다.


## 제외 범위


- SQL 실행 계획
- DB 데이터 자동 변경
- 모든 Spring AOP 의미 해석
- Kotlin


## 산출물


- Backend Analyzer Worker
- Spring/Test Adapter
- Analysis API와 UI
- Golden Fixture
- Symbol 해석 및 제약 문서


## 작업 종료 보고

`templates/phase_completion_report.md` 형식으로  
`docs/20260804/phase-reports/PHASE-03.md`를 작성하라.

보고서에는 다음을 반드시 포함한다.

- 구현 요약
- 변경 파일
- 실행한 명령
- 테스트 결과
- Acceptance Criteria 충족표
- 알려진 제약
- 다음 Phase 전달사항
- `AGENTS.md` 변경 여부
