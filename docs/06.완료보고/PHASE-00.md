# Phase 00 — 실행 가능한 플랫폼 골격 보고

> **Supersede (2026-08-04):** 당시 Control Plane/`workers` 구현은 **전량 폐기**.  
> Backend는 Phase **00b · D-012** 로 재구축. 본 보고는 frontend·sample 이력으로만 유효.

## 1. 기본 정보

- Phase: 00.기반구축
- 작업일: 2026-08-04
- 담당 Agent/개발자: Cursor Agent
- 관련 이전 Phase: 없음
- 회차 요약: `docs/report/20260804/00_1.md` ~ `00_3.md`

## 2. 구현 요약

- FastAPI Control Plane: `/health`, `/api/projects`, `/api/runs`, Fake LLM adapter, in-memory store
- Next.js Web Console: Dashboard/Projects/Analysis/Scenarios/Runs/Evidence/HITL + Control Plane 상태 + 여정 힌트
- Sample FE/BE: A 고객조회 → API → B 상세 (합성 고객 `CUS-1001`/`CUS-2002`)
- Workers health 골격 + contracts schema 동기화
- `make up-dev` / `test-phase00` / Compose 파일 / 오프라인 설치 문서
- agent-browser로 A→B·Console 시각 관측 및 스크린샷 증적

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `.cursor/rules/03-post-report.mdc` | 날짜·회차 보고 규칙 |
| `docs/report/` | 회차 요약 저장소 |
| `apps/` | Control Plane · Web Console |
| `workers/` | analyzer/runner 골격 |
| `packages/` | contracts · adapter-sdk · fixtures |
| `sample-targets/` | FE/BE 샘플 + CORS/`127.0.0.1` 수정 |
| `infra/`, `scripts/`, `Makefile` | 로컬 기동 |
| `artifacts/evidence/phase00-smoke/` | 시각 증적 |
| `docs/OFFLINE_INSTALL.md` | 폐쇄망 노트 |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| DB/Redis 부재 시 | in-memory Control Plane | Docker 강제 | 로컬에 Docker 없음 |
| Sample FE | Vite+React | Next.js | 샘플 대상과 Console 분리 |
| API Origin | `127.0.0.1` + localhost CORS | localhost only | agent-browser/로컬 Origin 불일치 해소 |

## 5. API·Schema 변경

- API: `GET /health`, `GET/POST /api/projects`, `GET /api/runs`
- Sample BE: `POST /api/customers/search`, `GET /health`
- JSON Schema: SSOT 동기화 + project/run schema
- DB Migration: 없음

## 6. 실행한 명령

```bash
make test-phase00   # (하위 모듈 단위로 실행됨)
# 서비스: uvicorn:8000, next:3000, vite:5173, spring:8080
# agent-browser: open → fill CUS-1001 → click → screenshot
curl -X POST http://127.0.0.1:8080/api/customers/search \
  -H 'Content-Type: application/json' -H 'Origin: http://127.0.0.1:5173' \
  -d '{"customerId":"CUS-1001"}'
```

## 7. 테스트 결과

| 테스트 영역 | 결과 | 비고 |
|---|---|---|
| Control Plane pytest | 완료 | health/project |
| Web Console build | 완료 | |
| Workers/contracts | 완료 | |
| Sample FE vitest | 완료 | |
| Sample BE MockMvc | 완료 | |
| agent-browser A→B | 관측 완료 | Pass/Fail 단정 아님 |
| Docker Compose | 미실행 | Docker 미설치 |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| 모노레포 골격 기동 | PARTIAL | CP/Console/FE/BE 기동. Postgres/Redis는 Compose만 제공·Docker 부재 |
| `/customers/search` → Backend → B | 관측됨 | `02-customer-detail.png`, API 200 JSON |
| agent-browser smoke | 관측됨 | `artifacts/evidence/phase00-smoke/` |
| Health UI/API | 관측됨 | Console Online · `/health` JSON |
| 오프라인 문서 | 있음 | `docs/OFFLINE_INSTALL.md` |
| 합성 데이터만 | 충족 | PII/Secret 없음 |
| 고객 HITL 승인 | 해당 없음 | 후속 Phase |

## 9. 보안·개인정보 검토

- 합성 customer만 사용. Secret/Token 미저장.
- `X-Test-Run-ID`는 수용·로그용.

## 10. 알려진 제약

- Docker 없음 → Postgres/Redis 실기동 Evidence `missing_data`
- `make up-dev`는 IDE 셸 종료 시 자식 프로세스가 죽을 수 있음 → Cursor 백그라운드 셸 또는 별도 터미널 권장
- Backend analyzer는 Node health stub (JavaParser는 Phase 03)

## 11. 다음 Phase 전달사항

- Phase 포인터는 Gate PARTIAL로 **00 유지**. 사람 확인 후 01 진행.
- 입력: 기동 가능한 샘플 FE/BE, Control Plane project API
- 주의: CORS에 localhost와 127.0.0.1 모두 필요

## 12. 문서 변경

- `AGENTS.md`: `03-post-report` · `docs/report` 링크 추가
- `docs/index.md`: report 목차 추가
- `docs/report/20260804/00_*.md` 작성
