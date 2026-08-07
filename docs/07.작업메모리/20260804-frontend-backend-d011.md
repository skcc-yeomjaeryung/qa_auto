# 작업 memory — D-011 frontend/backend 이관 · Phase 04 진입 전

- 날짜: 2026-08-04
- 포인터: **00b.BackendSDD기반** (후속: D-012 — 본 memory는 D-011 이관 이력)
- 상태: D-011 이관 후 **backend 전량 폐기**(2026-08-04). 후속 memory: `20260804-backend-sdd-d012.md`

## 현재 루트 (강제)

```text
qa_auto/
  frontend/                 # Console :3000
  backend/                  # API :8000 + workers
    workers/{frontend-analyzer,backend-analyzer,agent-browser-runner}/
  sample-targets/           # 분석 대상 (플랫폼과 별개)
  packages/ docs/ artifacts/ infra/ scripts/
```

폐기: `apps/` · 루트 `workers/`

## 완료 Phase

| Phase | 보고 |
|---|---|
| 00 기반구축 | `docs/06.완료보고/PHASE-00.md` (PARTIAL — Docker 미기동) |
| 01 저장소연결 | `docs/06.완료보고/PHASE-01.md` |
| 02 Frontend분석 | `docs/06.완료보고/PHASE-02.md` |
| 03 Backend분석 | `docs/06.완료보고/PHASE-03.md` (D-010 Python Skill/Tool) |

## ADR

- D-010 Backend 분석 = Python Agent/Tool (JVM JavaParser 폐기)
- D-011 루트 = `frontend/` + `backend/`

## 기동

```bash
make up-dev   # 또는 backend uvicorn · frontend next · samples
# ports: 8000 / 3000 / 5173 / 8080
```

## 다음

Phase 04: FE `apiCalls` ↔ BE `endpoints` 매핑 API·UI · Gate 보고
