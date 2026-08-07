# 증분 분석 · 프로젝트 카드 변경 인식 UX 상세계획

- 작성일: 2026-08-07
- 상태: **계획 전용 — 미구현**
- 현재 Phase: 14.배치테스트
- 사용자 요구: 저장소 동기화 직후와 메인 대시보드 프로젝트 카드에서 변경분, 영향 시나리오, 다음 행동을 인식시킨다.
- 적용 시점: 별도 증분 분석 Gate 승인 후. 현재 Phase 14 화면·API에는 이 문서만으로 기능이 생기지 않는다.

## 1. 목표

대형 SI의 잦은 코드 변경에서 전체 저장소를 매번 다시 분석하지 않고 아래 흐름을 제공한다.

```text
저장소 동기화
  → Source Snapshot 비교
  → 추가·수정·삭제·이름변경 ChangeSet
  → 의존성 영향 범위 계산
  → 영향 파일만 분석하고 기존 Analysis Snapshot과 병합
  → 영향 시나리오만 재생성
  → 프로젝트 카드·시나리오 목록에 변경 상태와 다음 행동 표시
```

사용자는 내부 분석기 용어를 몰라도 다음 질문에 답을 얻어야 한다.

1. 소스가 마지막 분석 뒤 바뀌었는가?
2. 무엇이 얼마나 바뀌었는가?
3. 기존 테스트 시나리오 중 무엇이 영향을 받았는가?
4. 새 시나리오를 검토해야 하는가, 기존 시나리오를 다시 실행해야 하는가?
5. 지금 누를 버튼은 무엇인가?

## 2. 비목표

- 코드 변경만으로 테스트 성공·실패 또는 고객 승인을 확정하지 않는다.
- 단순 파일 `mtime`만으로 실제 코드 변경을 확정하지 않는다.
- 증분 생성본으로 승인된 기존 시나리오를 즉시 덮어쓰지 않는다.
- 변경이 없는데 사용자를 매번 분석·실행 화면으로 보내지 않는다.
- 프로젝트 카드에 파일 경로·Symbol·Graph Node를 장황하게 노출하지 않는다.

## 3. 기준 데이터 계약

### 3.1 SourceSnapshot

| 필드 | 의미 |
|---|---|
| `snapshotId` | 동기화 시점의 불변 소스 Snapshot ID |
| `repositorySetId` | 연결 저장소 |
| `revision` | Git Commit SHA 또는 Local tree digest |
| `parentSnapshotId` | 비교 기준 Snapshot |
| `manifestHash` | 전체 파일 manifest 해시 |
| `files[]` | `path`, `sha256`, `sizeBytes`, `roleHint` |
| `createdAt` | 관측 시각 |

Git은 Commit을 진실원으로 사용한다. Local Path는 `mtime + size`를 빠른 후보 판별에만 사용하고 SHA-256으로 실제 변경을 확정한다. 내용이 같고 날짜만 바뀐 파일은 재분석 대상에서 제외한다.

### 3.2 ChangeSet

| 필드 | 의미 |
|---|---|
| `baseSnapshotId` | 마지막 분석에 사용된 Snapshot |
| `headSnapshotId` | 현재 동기화 Snapshot |
| `added[]` | 신규 파일 |
| `modified[]` | 내용 변경 파일 |
| `deleted[]` | 삭제 파일 |
| `renamed[]` | 이름·경로 변경 파일 |
| `changeCount` | 사용자용 합계 |
| `detectionStatus` | `NO_CHANGE`, `DETECTED`, `PARTIAL`, `ERROR` |

### 3.3 ImpactSummary

| 필드 | 의미 |
|---|---|
| `screens` | 영향 화면 수 |
| `apiEndpoints` | 영향 API 수 |
| `contracts` | DTO·Validation·Component Contract 영향 수 |
| `graphNodes` | 영향 Graph Node 수 |
| `scenarioNew` | 신규 시나리오 후보 수 |
| `scenarioChanged` | 변경 시나리오 수 |
| `scenarioUnaffected` | 영향 없음 수 |
| `scenarioObsoleteCandidates` | 폐기 검토 수 |
| `scenarioReviewRequired` | 불확실성으로 사람 검토가 필요한 수 |
| `reasonRefs[]` | 파일·Route·Endpoint 기반 영향 근거 참조 |

### 3.4 ProjectChangeStatus

프로젝트 카드의 단일 진실원이다.

```text
UP_TO_DATE
CHANGES_DETECTED
INCREMENTAL_ANALYSIS_RUNNING
SCENARIO_REVIEW_REQUIRED
IMPACT_RUN_RECOMMENDED
ANALYSIS_BLOCKED
```

`UP_TO_DATE`는 소스와 분석 Snapshot이 같다는 뜻이며 테스트 성공 또는 HITL 승인을 뜻하지 않는다.

## 4. 동기화 직후 UX

저장소 동기화 응답 직후 프로젝트 화면에 결과 배너를 표시한다.

### 변경 없음

```text
최신 소스와 마지막 분석 결과가 같습니다.
Commit e98fd21 · 추가 분석이 필요하지 않습니다.

[분석 결과 보기]
```

### 변경 감지

```text
마지막 분석 이후 코드 변경이 감지되었습니다.
a12bc34 → e98fd21

추가 3 · 수정 8 · 삭제 1
예상 영향: 화면 2 · API 3 · 시나리오 5

[변경 내역 보기] [변경분 분석 시작]
```

### 변경 감지 실패·부분

```text
일부 파일의 변경 여부를 확정하지 못했습니다.
기존 분석 결과는 유지됩니다.

[확인 필요 항목 보기] [안전하게 전체 분석]
```

분석 시작 뒤 Progress Type 2 또는 Type 1로 다음 단계를 표시한다.

```text
변경 파일 확인
→ 의존성 영향 계산
→ 변경분 분석
→ 기존 결과 병합
→ 시나리오 영향 계산
```

Progress Complete는 기술 처리 완료이며 HITL Pass가 아니다.

## 5. 메인 대시보드 프로젝트 카드

### 5.1 카드 기본 정보

프로젝트 카드에 아래 정보만 상시 노출한다.

```text
인터넷뱅킹 고도화
소스 e98fd21 · 마지막 분석 a12bc34

변경 파일 12개
영향 예상 시나리오 5개

상태: 변경분 분석 필요
[변경분 분석]
```

세부 파일 경로와 Symbol은 `변경 내역` drawer에서만 제공한다.

### 5.2 카드 상태별 표현

| 상태 | 카드 문구 | Primary Action | Secondary Action |
|---|---|---|---|
| `UP_TO_DATE` | 최신 분석 반영 | 시나리오 보기 | 마지막 분석 보기 |
| `CHANGES_DETECTED` | 변경 파일 N개 · 영향 예상 M건 | 변경분 분석 | 변경 내역 |
| `INCREMENTAL_ANALYSIS_RUNNING` | 변경분 분석 중 N% | 진행 보기 | 취소(정책 허용 시) |
| `SCENARIO_REVIEW_REQUIRED` | 신규 A · 변경 B · 폐기 후보 C | 시나리오 변경 검토 | 분석 요약 |
| `IMPACT_RUN_RECOMMENDED` | 검토 완료 · 영향 테스트 M건 권장 | 영향 시나리오 실행 | 실행 대상 보기 |
| `ANALYSIS_BLOCKED` | 변경분 일부 확인 필요 | 누락 근거 검토 | 안전하게 전체 분석 |

카드의 Primary Action은 항상 한 개만 둔다. 사용자가 다음 행동을 추론하게 하지 않는다.

### 5.3 카드 갱신 규칙

- 동기화가 끝나면 `headSnapshotId`를 갱신한다.
- 분석이 끝나기 전에는 `lastAnalyzedSnapshotId`를 바꾸지 않는다.
- 증분 분석·병합이 끝나면 `lastAnalyzedSnapshotId=headSnapshotId`로 승격한다.
- 시나리오 검토가 남았으면 소스 분석이 최신이어도 `SCENARIO_REVIEW_REQUIRED`를 표시한다.
- 분석 실패 시 기존 승인 시나리오와 기존 Snapshot을 유지하고 `ANALYSIS_BLOCKED`로 표시한다.

## 6. 분석 결과와 시나리오 재생성 UX

증분 분석 완료 화면은 건수만 보여주지 않고 분류와 다음 행동을 함께 제시한다.

```text
변경분 분석이 완료되었습니다.

신규 시나리오        2
변경 시나리오        3
영향 없음           41
폐기 후보            1
재검토 필요          1

권장 다음 작업
신규·변경 시나리오 5건을 검토하세요.

[시나리오 변경 비교] [나중에]
```

### 시나리오 상태

| 상태 | 처리 |
|---|---|
| `NEW_DRAFT` | 새 시나리오 초안. 사람 검토 전 실행 목록 자동 승격 금지 |
| `CHANGED_DRAFT` | 기존 승인 버전은 유지하고 새 버전을 Draft로 생성 |
| `UNAFFECTED` | 기존 버전과 승인·실행 이력 유지 |
| `OBSOLETE_CANDIDATE` | 근거 삭제. 자동 삭제하지 않고 비활성 검토 |
| `REVIEW_REQUIRED` | 의존성·Mapping 불확실. 사람 확인 필요 |

### 버전 원칙

```text
승인·실행에 사용된 v3  ─ 보존
증분 재생성된 v4 Draft ─ 비교·검토
사람 채택              ─ v4 활성
사람 반려              ─ v3 유지
```

변경 비교 화면에는 다음만 우선 표시한다.

- 변경을 만든 코드 근거
- 변경된 화면·API·입력 제약
- 추가·수정·제거된 시나리오 단계
- Input Profile 재승인 필요 여부
- 권장 회귀 실행 범위

## 7. 다음 행동 결정 규칙

| 관측 결과 | 사용자 안내 | 다음 행동 |
|---|---|---|
| 변경 없음 | 최신 분석 상태 | 없음 또는 시나리오 보기 |
| 코드 변경, 시나리오 영향 없음 | 기존 시나리오 유지 가능 | 변경 근거 확인 선택 |
| 신규 화면/API | 신규 시나리오 후보 존재 | 초안 검토 |
| 기존 화면/API 계약 변경 | 기존 시나리오가 구버전 | Diff 검토 후 재실행 |
| DTO/Validation 변경 | 입력 계약 변경 | Input Profile 재승인 |
| Endpoint/화면 삭제 | 시나리오 근거 소멸 | 폐기·대체 경로 검토 |
| 영향 관계 불확실 | `missing_data`/review required | Mapping·근거 확인 |
| destructive/auth 흐름 변경 | 안전 정책 재확인 필요 | 환경·계정·HITL 확인 |

영향 테스트 버튼은 전체 프로젝트 실행이 아니라 검토·채택된 변경 시나리오 ID만 Batch 입력으로 넘긴다.

## 8. 예정 API

상세 이름은 구현 Phase에서 OpenAPI·Schema와 함께 확정한다.

```text
POST /api/repository-sets/{setId}/sync
GET  /api/projects/{projectId}/change-summary
POST /api/projects/{projectId}/incremental-analyses
GET  /api/incremental-analyses/{analysisRunId}
GET  /api/incremental-analyses/{analysisRunId}/events
GET  /api/scenario-change-sets/{changeSetId}
POST /api/scenario-change-sets/{changeSetId}/accept
POST /api/scenario-change-sets/{changeSetId}/impact-runs
```

동기화 응답 또는 `change-summary`는 최소한 아래를 제공한다.

```json
{
  "projectId": "PRJ-...",
  "baseRevision": "a12bc34",
  "headRevision": "e98fd21",
  "status": "CHANGES_DETECTED",
  "files": { "added": 3, "modified": 8, "deleted": 1, "renamed": 0 },
  "impact": { "screens": 2, "apiEndpoints": 3, "scenarios": 5 },
  "recommendedAction": "RUN_INCREMENTAL_ANALYSIS"
}
```

## 9. 구현 순서

1. 잘못된 Commit 캐시 재사용과 Local Path 변경 감지를 먼저 교정한다.
2. `SourceSnapshot`·`ChangeSet`·파일 manifest를 영속화한다.
3. 파일→Symbol→화면/API→Graph→Scenario 역방향 영향 인덱스를 만든다.
4. 변경 파일 분석·삭제 tombstone·기존 Snapshot 병합을 구현한다.
5. 안정적인 Scenario logical key와 버전 이력을 구현한다.
6. `ProjectChangeStatus`·`recommendedAction` API를 제공한다.
7. 동기화 직후 배너와 대시보드 프로젝트 카드를 구현한다.
8. 시나리오 Diff 검토와 영향 Batch 실행을 연결한다.
9. Progress UI·오류·취소·재개·HITL 분리를 검증한다.

## 10. 검증 Gate

- 같은 Commit/내용은 분석을 재실행하지 않는다.
- Local Path 신규·수정·삭제 파일을 SHA-256 manifest로 감지한다.
- 변경 파일과 의존 영향 파일만 Analyzer에 전달한다.
- 삭제 파일의 옛 화면·Endpoint·시나리오 근거가 tombstone 처리된다.
- 영향 없는 시나리오의 ID·버전·승인·실행 이력이 보존된다.
- 변경 시나리오는 기존 승인본을 덮어쓰지 않고 Draft 버전으로 생성된다.
- 프로젝트 카드의 Commit·파일 수·영향 시나리오 수가 API와 일치한다.
- 카드 상태마다 Primary Action이 정확히 하나다.
- `Complete`를 테스트 성공이나 HITL 승인으로 표현하지 않는다.
- 1920×1080과 1440px 화면에서 카드가 잘리지 않는다.
- Frontend 구현 시 agent-browser로 동기화→카드→변경 검토→영향 실행 여정을 관측한다.

## 11. 이번 작업과의 경계

이번 회차에는 위 UX·API·증분 분석을 구현하지 않는다. 실제 변경은 브라우저 실행 Python 경로의 세션 종료를 `finally`로 보장하는 범위뿐이다. 이 계획은 이후 별도 증분 분석 Phase의 입력으로 사용한다.
