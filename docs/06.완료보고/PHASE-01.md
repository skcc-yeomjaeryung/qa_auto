# Phase 01 — 저장소연결 완료 보고 (SDD 재구현)

> **재구현 (2026-08-04):** 구 `apps/control-plane` 구현은 backend 전량 폐기(D-012)로 무효.  
> 본 보고는 **00b Gate 이후** `backend/app/services` + FastAPI 로 재구현한 Gate 결과다.

## 1. 기본 정보

- Phase: 01.저장소연결
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 기준 Branch: main
- 기준 Commit: 37555ef (작업 시점 HEAD; 산출물은 working tree)
- 관련 이전 Phase: 00b.BackendSDD기반 (`PHASE-00b.md`, Gate PASS)
- 회차 요약: `docs/report/20260804/01_3.md`
- 핸드오프: `docs/continue/NEXT.md`

## 2. 구현 요약

- Project + RepositorySet 모델을 `backend/app/services` 에 두고 FE/BE 저장소를 한 프로젝트에 등록한다.
- Local Path snapshot · GitHub(HTTPS/`file://` bare) shallow clone · Branch/Commit 고정.
- Sync 시 파일 인벤토리(language/size/sha256/roleHint), 스택 감지, 플랫폼 ignore 규칙을 적용한다.
- Token은 메모리 `_tokens`에만 보관하고 API 응답·로그에 평문 노출하지 않는다.
- 동일 Commit workspace는 캐시 재사용한다. 중첩 모노레포 경로는 parent SHA 오용을 막고 tree hash로 핀한다.
- Web Console `/projects` 가 동일 API 계약으로 연동된다 (Type 2 여정 스텝퍼 유지).
- Hub 우회 없이 CRUD·sync만 services에 둔다. 분석/시나리오 Skill은 본 Phase에서 추가하지 않았다.
- (선택) Design Spec / Excel 업로드 API는 미구현 — 후속 보완.

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/services/repository_*.py` | 모델·스토어·sync·inventory |
| `backend/app/services/stack_detect.py` | FE/BE 스택 감지 |
| `backend/app/services/ignore_rules.py` | 플랫폼 ignore |
| `backend/app/utils/config.py` | `WORKSPACE_ROOT` 설정 |
| `backend/app/api/projects.py` · `repository_sets.py` · `deps.py` | Project·Repository·sync API |
| `backend/app/main.py` | 라우터 등록 |
| `backend/tests/test_repository_phase01.py` | Gate 단위·통합 테스트 |
| `frontend/components/ProjectsWorkbench.tsx` | 기존 UI 유지(API 계약 재연동) |
| `docs/06.완료보고/PHASE-01.md` | 본 재구현 Gate 보고 |
| `docs/report/20260804/01_3.md` | 회차 요약 |
| `docs/index.md` / `AGENTS.md` / `docs/continue/NEXT.md` | Phase 포인터·핸드오프 |
| `.data/workspaces/` | 로컬 sync workspace (런타임, gitignore) |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| 책임 위치 | `services/` 동기 CRUD | Skill Hub로 sync | NEXT·D-012: 분석/시나리오만 Hub. 01 Gate Skill 남발 금지 |
| 영속 저장 | in-memory PlatformStore | Postgres 즉시 | Docker/DB 부재(Phase 00 제약) 유지 |
| nested sample path | worktree root일 때만 `git HEAD`, 아니면 tree hash | 부모 모노레포 SHA | FE/BE가 동일 parent SHA로 핀되는 버그 방지 |
| Credential | 메모리 전용 + `hasCredential` | DB 평문 | Secret 미저장 Guardrail |
| GitHub 테스트 | `file://` bare clone fixture | 실 GitHub 호출 | 오프라인·재현 가능 |
| settings | `app/utils/config.py` | `app/core/config.py` | NH_AML 정렬 — 공통 config를 core에 두지 않음 |

## 5. API·Schema 변경

- 추가/변경 API:
  - `POST /api/projects`
  - `GET /api/projects`, `GET /api/projects/{id}`
  - `POST /api/projects/{id}/repositories`
  - `GET /api/projects/{id}/repository-set`
  - `POST /api/repository-sets/{id}/sync`
  - `GET /api/repository-sets/{id}/status`
  - `GET /api/repository-sets/{id}/files`
- DB Migration: 없음 (in-memory)
- JSON Schema: `packages/contracts/schemas/project.schema.json` 최소 유지 — 런타임 계약은 Pydantic
- 호환성: 00b `/health` · `/api/runs/execute` 유지, Project API additive
- (선택 API 미구현) design-specs / test-data-sheets

## 6. 실행한 명령

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
# 12 passed (00b + 01)

export WORKSPACE_ROOT=/Users/a11123/Desktop/qa_auto/.data/workspaces
# Live smoke: sample-targets FE/BE local register → sync
# FE commitSha prefix 0355906d9d4a / BE 3cc807101e2a (distinct tree hash)
# inventory 39 files, node_modules/target 제외, sha256·roleHint 존재
```

## 7. 테스트 결과

| 테스트 영역 | 명령 | 결과 | 비고 |
|---|---|---|---|
| Unit/Integration | `pytest tests/` | 12 passed | local pin, bare clone, ignore, token mask, invalid path, nested tree-hash |
| Live Local sync | sample-targets | 관측됨 | FE/BE 서로 다른 pin · files=39 · forbidden=0 |
| Cache re-sync | pytest re-sync | 관측됨 | Commit SHA 불변 |
| Console UI | `/projects` | 코드 존재 | Type 2 stepper · API 계약 동일 |
| Design Spec API | — | 미구현 | 선택 범위 |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| FE·BE를 한 Project에 연결 | PASS | pytest + live `PRJ-*` / `RS-*` |
| 분석 대상 Commit SHA 저장·불변 | PASS | sync 재실행 동일 SHA; nested path tree-hash 분리 |
| 인벤토리 language/size/hash/역할 | PASS | `sha256`, `language`, `sizeBytes`, `roleHint` |
| 생성물·대용량 제외 | PASS | ignore 테스트 + live `forbidden_leaks=[]` |
| Credential 비노출 | PASS | `test_token_not_echoed_in_response` |
| 동일 Commit 캐시 재사용 | PASS | `_commit_cache` + re-sync SHA 유지 |
| Progress Type 2 표시 | PASS | `ProjectsWorkbench` JourneyStepper (저장소 스텝) |
| (선택) Design Spec/Excel | DEFERRED | 선택 범위 — 미구현 |

**Gate 판정: PASS** (선택 보조 Evidence 업로드는 후속 보완)

## 9. 보안·개인정보 검토

- Secret 노출 여부: Token 평문 API 미반환 · git URL에 주입 시 로그 redact
- PII 마스킹: 샘플 경로만 사용, 고객 PII 없음
- 로그 검토: `credential=present(masked)` 형태
- 권한 검토: Pilot/Sandbox 로컬 경로
- 미해결 위험: in-memory token은 프로세스 재시작 시 소멸 (의도적)

## 10. 알려진 제약

- Postgres/Redis/Docker 미기동 → 영속 DB Migration 없음
- Design Spec · Test Data Sheet 업로드 API 미구현 (선택)
- contracts JSON Schema 파일은 Project 최소 필드만 — 상세는 Pydantic
- 모노레포 하위 sample-targets는 독립 git root가 아니면 content tree hash로 pin
- Control Plane 재시작 시 in-memory Project/RepositorySet 소멸

## 11. 다음 Phase 전달사항

- 입력 계약: sync 완료된 RepositorySet (`commitSha`, `workspacePath`, files inventory, stack)
- 사용할 API: `GET /api/repository-sets/{id}/status`, `.../files`, project journey `repository=complete`
- 주의할 제약: workspace는 `WORKSPACE_ROOT` 아래; analyzer는 pinned workspace만 읽을 것
- 미해결 항목: 보조 Evidence 업로드, DB 영속화
- 다음 Phase: **02.Frontend분석** — Skill Hub로 재편 (`frontend_analyze` + workers 재도입)

## 12. 문서 변경

- `AGENTS.md`: Phase 포인터 01 → 02 (Gate PASS 후 갱신)
- `docs/index.md`: 동일
- `docs/continue/NEXT.md`: 02 핸드오프 갱신
- Architecture/ADR: D-007 범위 내 재구현, 신규 ADR 없음
