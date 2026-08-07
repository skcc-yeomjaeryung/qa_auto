# Phase 12 — 증적수집 완료 보고

## 1. 기본 정보

- Phase: 12.증적수집
- 작업일: 2026-08-05
- 담당 Agent/개발자: Cursor Agent
- 기준 Branch: 현재 작업 브랜치
- 관련 이전 Phase: 09 브라우저실행 · 10 Backend추적 · 11 바인딩검증
- 회차 요약: `docs/report/20260805/12_1.md`

## 2. 구현 요약

Run의 Scenario·Commit·Input·Network·Backend Log·Binding Assertion·Screenshot·DOM snapshot을
독립 디렉터리의 재현 가능한 Evidence Package로 생성한다.

- Local filesystem storage adapter와 package path jail
- 필수 canonical artifact 생성 및 A→Backend→B stage 분류
- Artifact별 SHA-256 · size · MIME · createdAt manifest
- complete/partial/corrupted 무결성 상태와 storageStatus 분리
- Screenshot rectangle 마스킹(Pillow), Network/JSON/DOM 값 마스킹
- 실패·취소 Run도 가능한 artifact를 수집하고 missing_data 유지
- 환경설정 기반 retention과 만료 package 정리
- owner 기반 manifest/artifact/ZIP 접근 제어
- ZIP exporter와 corruption 검증 API
- Run 상세에 manifest-first Evidence Viewer 추가
- 원문보다 실행 요약·연결관계·마스킹·무결성을 먼저 표시

## 3. 변경 파일

| 파일/디렉터리 | 변경 목적 |
|---|---|
| `backend/app/schemas/evidence.py` | Manifest·Artifact·Integrity 계약 |
| `backend/app/services/evidence_storage.py` | Local filesystem adapter |
| `backend/app/services/evidence_package.py` | Collector·hash·mask·retention·ZIP |
| `backend/app/api/evidence.py` | finalize/manifest/integrity/download/artifact API |
| `backend/app/services/repository_store.py` | Manifest SQLite catalog 영속 |
| `backend/app/api/scenario_runs.py` | 기존 Run evidence 응답에 package 요약 추가 |
| `backend/app/utils/config.py` | retention 설정 |
| `packages/contracts/schemas/evidence_manifest.schema.json` | Runtime schema |
| `docs/03.계약과예시/schemas/evidence_manifest.schema.json` | SSOT 문서 동기화 |
| `frontend/components/EvidencePackageViewer.tsx` | A→Backend→B Viewer |
| `frontend/app/runs/[runId]/page.tsx` | Run 상세 연결 |
| `frontend/app/styles.css` | dense manifest/lineage UI |
| `backend/tests/test_evidence_package_phase12.py` | Gate 테스트 |
| `backend/pyproject.toml` · `backend/uv.lock` | Pillow screenshot masking |

## 4. 주요 설계 결정

| 결정 | 선택 | 대안 | 선택 이유 |
|---|---|---|---|
| Pilot 저장 | Local filesystem adapter | 외부 Object Storage | 외부 의존 없이 재현·교체 가능 |
| Package ID | `EVID-{runId}` | 무작위 ID | Run과 단일 추적 |
| 무결성 | SHA-256 + size | 파일 존재만 | corruption 탐지 |
| Screenshot mask | 좌표 rectangle pixel mask | 메타데이터만 | 원본 PII 노출 방지 |
| Network | sanitized request JSON | raw HAR 기본 | Secret/Token 미저장 |
| 실패 수집 | partial package | package 미생성 | 실패 원인 증적 보존 |

## 5. API·Schema 변경

- 기존 유지: `GET /api/runs/{id}/evidence`
- 추가:
  - `POST /api/runs/{id}/evidence/finalize`
  - `GET /api/evidence/{id}/manifest`
  - `GET /api/evidence/{id}/integrity`
  - `GET /api/evidence/{id}/download`
  - `GET /api/evidence/{id}/artifacts/{artifactId}`
- Schema: Evidence Manifest에 owner/storage/retention/stage/missingData additive 확장
- DB Migration: 없음 (SQLite KV catalog additive)

## 6. 실행한 명령

```bash
cd backend
uv add pillow
.venv/bin/pytest \
  tests/test_evidence_package_phase12.py \
  tests/test_binding_validation_phase11.py \
  tests/test_backend_trace_phase10.py \
  tests/test_browser_execute_phase09.py -q
# 35 passed, 1 skipped

.venv/bin/pytest tests/test_evidence_package_phase12.py -q
# 9 passed

cd frontend
npx tsc --noEmit
npm run build
# Next.js production build 완료
```

agent-browser로 local Run 상세에서 패키지 생성 전/후를 관측했다.

- Evidence Package 생성·재생성 CTA
- partial/missing_data 명시
- Artifact/마스킹/보존기한
- A 입력 → Request·Backend → B 화면·Assertion 연결관계
- ZIP 다운로드 CTA

## 7. 테스트 결과

| 테스트 영역 | 명령 | 관측 결과 | 비고 |
|---|---|---|---|
| Package | Phase 12 pytest | 9 passed | complete/partial/hash/mask/auth/retention/zip |
| Regression | Phase 9~12 pytest | 35 passed · 1 skipped | CLI 조건 skip |
| Frontend | tsc + build | 완료 | 타입·production build |
| Console | agent-browser DOM/screenshot | Viewer·partial package 관측 | RUN-cancel은 입력 증적 부재 |

## 8. Acceptance Criteria

| Criteria | 결과 | Evidence |
|---|---|---|
| 정상 Run 필수 Evidence | 충족 관측 | `test_complete_package_manifest_schema_and_required_files` |
| 실패 Run partial package | 충족 관측 | `test_failed_run_produces_partial_package` |
| Schema·SHA-256 검증 | 충족 관측 | hash/corruption tests |
| Screenshot·Network 마스킹 | 충족 관측 | pixel/network/snapshot masking test |
| UI A→Backend→B 순서 | 충족 관측 | agent-browser DOM + screenshot |
| 권한 사용자 ZIP | 충족 관측 | authorized/unauthorized API test |

> 기술 Gate 관측이며 고객의 최종 Pass/Fail 또는 배포 승인을 뜻하지 않는다.

## 9. 보안·개인정보 검토

- Authorization/Cookie/Token/Password 등 Network/JSON 재귀 마스킹
- Input/customerId 등 runtime value를 DOM snapshot에서 치환
- Screenshot은 binding evidence region을 검정 pixel로 마스킹
- 다운로드·artifact 조회는 `X-User-Id`와 owner가 일치해야 함
- ZIP에는 package jail 내부 파일만 포함

## 10. 알려진 제약

- 좌표가 없는 screenshot mask locator는 pixel 위치를 확정할 수 없어 runtime region이 필요하다.
- Raw HAR 대신 파일럿 기본은 sanitized request log다.
- 공인 전자서명·외부 Object Storage·법정 장기보존은 제외 범위다.
- 실제 RUN-cancel 관측은 원본 증적 부재로 partial이며 이를 숨기지 않았다.

## 11. 다음 Phase 전달사항

- 다음 Phase: **13.건별테스트**
- Evidence 입력: `EvidenceManifest` · integrity/missingData · assertion artifact
- 건별 실행 화면에서 package finalize와 HITL 전달 상태를 재사용
- corrupted/partial package를 기술 성공으로 오인하지 않도록 분리

## 12. 문서 변경

- `docs/index.md` · `AGENTS.md` · Cursor pointer → Phase 13
- `docs/continue/NEXT.md` → Phase 13
- `docs/report/20260805/12_1.md`
