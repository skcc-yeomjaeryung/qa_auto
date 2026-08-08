#!/usr/bin/env python3
"""Execution history -> fixed Structured Output + HTML (deterministic)."""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
from pathlib import Path
from typing import Any


MISSING = "missing_data"
WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
EVIDENCE_PACKAGES_ROOT = (WORKSPACE_ROOT / "artifacts" / "evidence" / "packages").resolve()
RUN_EVIDENCE_ROOT = (WORKSPACE_ROOT / "artifacts" / "evidence" / "runs").resolve()
REPORT_MASCOT_PATH = (WORKSPACE_ROOT / "frontend" / "public" / "dashboard" / "qa-robot.png").resolve()

_MISSING_DETAILS: dict[str, tuple[str, str, str]] = {
    "criterion:C-collection-change": (
        "업무 처리 전후의 목록 변화를 확인하지 못했습니다",
        "결과 화면에서 새 거래나 변경된 항목이 표시됐는지 확인해 주세요.",
        "실행 결과",
    ),
    "criterion:C-state-delta": (
        "업무 처리 전후의 화면 값 변화를 확인하지 못했습니다",
        "잔액·상태·건수처럼 변경돼야 하는 값이 실제로 달라졌는지 확인해 주세요.",
        "실행 결과",
    ),
    "criterion:C-success-message": (
        "완료 안내 문구를 화면에서 확인하지 못했습니다",
        "업무 완료 또는 오류 안내가 화면에 표시됐는지 확인해 주세요.",
        "실행 결과",
    ),
    "submit_blocked_destructive": (
        "데이터를 변경하는 제출 단계가 안전 정책에 따라 실행되지 않았습니다",
        "실제 데이터 변경이 허용되는 테스트인지 확인한 뒤 담당자가 다시 실행해 주세요.",
        "실행 단계",
    ),
    "input_precondition_invalid": (
        "현재 테스트 계정 상태로는 입력값을 제출할 수 없습니다",
        "계정 잔액·허용 범위를 확인하고 테스트 데이터를 초기화하거나 충전한 뒤 다시 실행해 주세요.",
        "실행 선행조건",
    ),
    "backend_telemetry": (
        "서버 처리 추적 정보를 수집하지 못했습니다",
        "실행 ID가 서버 로그까지 전달됐는지 확인해 주세요.",
        "서버 검증",
    ),
    "input_profile": (
        "실행에 사용한 입력값 묶음 정보가 연결되지 않았습니다",
        "어떤 입력값으로 실행했는지 입력 프로필을 확인해 주세요.",
        "실행 입력",
    ),
    "backend_request": (
        "서버로 보낸 요청 내용을 수집하지 못했습니다",
        "Network 증적 또는 서버 요청 로그를 확인해 주세요.",
        "서버 검증",
    ),
    "backend_response": (
        "서버 응답 내용을 수집하지 못했습니다",
        "응답 상태와 본문이 기록됐는지 확인해 주세요.",
        "서버 검증",
    ),
    "backend_events": (
        "서버 내부 처리 이벤트를 수집하지 못했습니다",
        "실행 ID 기준 서버 이벤트 로그가 남았는지 확인해 주세요.",
        "서버 검증",
    ),
    "httpStatus": (
        "서버 응답 상태를 확인하지 못했습니다",
        "Network 기록에서 응답 상태 코드가 수집됐는지 확인해 주세요.",
        "기술 검증",
    ),
}

_ARTIFACT_LABELS = {
    "scenario": "테스트 시나리오 원문",
    "source": "소스·Commit 연결 정보",
    "input": "실행 입력값",
    "backend": "서버 요청·응답",
    "binding": "기대값·관측값 검증",
    "screenshot": "실행 화면",
    "snapshot": "화면 구조 스냅샷",
    "network": "Network 요청 기록",
}


def _missing_detail(code: Any) -> dict[str, str]:
    raw = _text(code)
    if raw.startswith("run_status:"):
        status = raw.split(":", 1)[1]
        return {
            "code": raw,
            "label": "자동 실행에서 확인이 필요한 결과가 발생했습니다",
            "guidance": f"실행 상태({status})와 단계별 관측 내용을 확인해 주세요.",
            "section": "실행 결과",
        }
    if raw.startswith("locator:"):
        return {
            "code": raw,
            "label": "화면에서 확인 대상 요소를 찾지 못했습니다",
            "guidance": "화면 구조가 변경됐는지 또는 대상 요소가 실제로 표시됐는지 확인해 주세요.",
            "section": "화면 검증",
        }
    label, guidance, section = _MISSING_DETAILS.get(
        raw,
        (
            "자동 검증에 필요한 자료를 충분히 수집하지 못했습니다",
            "실행 단계와 증적 패키지에서 관련 자료가 남았는지 확인해 주세요.",
            "추가 확인",
        ),
    )
    return {"code": raw, "label": label, "guidance": guidance, "section": section}


def _artifact_label(row: dict[str, Any]) -> str:
    kind = _text(row.get("type"))
    base = _ARTIFACT_LABELS.get(kind, "실행 증적 파일")
    stage = _text(row.get("stage")) if row.get("stage") else ""
    stage_label = {
        "source": "A 화면",
        "input_completed": "입력 완료 화면",
        "destination": "B 결과 화면",
    }.get(stage)
    return f"{stage_label} · {base}" if stage_label else base


def _text(value: Any) -> str:
    if value is None or value == "":
        return MISSING
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _refs(*values: Any) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if value not in (None, "")))


def _safe_observation(value: Any) -> str:
    """Keep the observation while removing credential values copied into run logs."""
    text = _text(value)
    sensitive = re.compile(
        r"(?i)((?:#?login-(?:username|password|id)|password|passwd|secret|token|authorization|cookie|api[_-]?key)\s*[=:]\s*)([^\s,;)]+)"
    )
    return sensitive.sub(r"\1***", text)


def build_report(source: dict[str, Any]) -> dict[str, Any]:
    required = ("reportId", "run", "project", "scenario", "binding", "evidence", "generatedAt")
    missing_keys = [key for key in required if key not in source]
    if missing_keys:
        raise ValueError(f"reportSource required keys missing: {', '.join(missing_keys)}")

    run = dict(source["run"] or {})
    project = dict(source["project"] or {})
    scenario = dict(source["scenario"] or {})
    scenario_body = dict(scenario.get("result") or {})
    binding = dict(source["binding"] or {})
    evidence = dict(source["evidence"] or {})
    assertions = [row for row in (binding.get("assertions") or []) if isinstance(row, dict)]
    artifacts = [row for row in (evidence.get("artifacts") or []) if isinstance(row, dict)]
    steps = [row for row in (run.get("steps") or []) if isinstance(row, dict)]
    run_result = dict(run.get("result") or {}) if isinstance(run.get("result"), dict) else {}
    raw_diagnosis = (
        dict(run_result.get("runDiagnosis") or {})
        if isinstance(run_result.get("runDiagnosis"), dict)
        else {}
    )
    diagnosis_actions = [
        {
            "owner": _text(item.get("owner")),
            "action": _text(item.get("action")),
            "reason": _text(item.get("reason")),
        }
        for item in (raw_diagnosis.get("actions") or [])
        if isinstance(item, dict) and item.get("action")
    ]
    cause_category = _text(raw_diagnosis.get("causeCategory") or "unknown")
    raw_diagnosis_outcome = _text(raw_diagnosis.get("outcome"))
    if raw_diagnosis_outcome not in {"success", "failure", "undetermined"}:
        run_outcome = _text(run.get("outcomeKind")).lower()
        raw_diagnosis_outcome = (
            "success"
            if run_outcome == "success"
            else "failure"
            if run_outcome in {"failure", "fe_error", "be_error", "business_error"}
            else "undetermined"
        )
    diagnosis_outcome = (
        "undetermined"
        if cause_category in {"destructive_policy_blocked", "input_precondition_invalid"}
        else raw_diagnosis_outcome
    )
    diagnosis = {
        "outcome": diagnosis_outcome,
        "headline": _text(raw_diagnosis.get("headline") or "판정 근거 확인 필요"),
        "problemSummary": _text(
            raw_diagnosis.get("problemSummary")
            or run.get("outcomeSummary")
            or run.get("observationSummary")
        ),
        "causeCategory": cause_category,
        "causeSummary": _text(raw_diagnosis.get("causeSummary") or "관측 근거를 추가로 확인해야 합니다"),
        "evidence": [_text(item) for item in (raw_diagnosis.get("evidence") or [])],
        "actions": diagnosis_actions,
        "retestCondition": _text(
            raw_diagnosis.get("retestCondition")
            or "누락된 관측 근거를 보강한 뒤 같은 입력과 실행환경으로 다시 실행하세요"
        ),
        "handoffMessage": _text(
            raw_diagnosis.get("handoffMessage")
            or "개발·QA 담당자가 실행 근거를 확인한 뒤 재검증해 주세요"
        ),
        "mode": _text(raw_diagnosis.get("mode") or "deterministic"),
        "humanDecisionRequired": True,
    }
    source_screen = dict(scenario_body.get("source") or {})
    destination_screen = dict(scenario_body.get("destination") or {})
    request = dict(scenario_body.get("request") or {})

    report_assertions = []
    for row in assertions:
        evidence_data = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        report_assertions.append(
            {
                "assertionId": _text(row.get("assertionId")),
                "field": _text(row.get("field")),
                "result": _text(row.get("result")),
                "expected": _text(row.get("expected")),
                "actual": _text(row.get("actual")),
                "businessReviewRequired": bool(row.get("businessReviewRequired")),
                "evidenceRefs": _refs(evidence_data.get("screenshotPath"), evidence_data.get("snapshotPath")),
                "missingData": [_text(item) for item in (row.get("missingData") or [])],
            }
        )

    observations = []
    for row in steps:
        observations.append(
            {
                "stepId": _text(row.get("stepId")),
                "action": _text(row.get("action")),
                "status": _text(row.get("status")),
                "observation": _safe_observation(row.get("observationSummary")),
                "evidenceRefs": _refs(row.get("screenshotPath"), row.get("snapshotPath"), *(row.get("networkRefs") or [])),
                "missingData": [_text(item) for item in (row.get("missingData") or [])],
            }
        )
    final_result_screenshot = run_result.get("resultScreenshot")
    if final_result_screenshot and observations:
        observations[-1]["evidenceRefs"] = _refs(
            *observations[-1].get("evidenceRefs", []), final_result_screenshot
        )

    report_artifacts = [
        {
            "artifactId": _text(row.get("artifactId")),
            "type": _text(row.get("type")),
            "label": _artifact_label(row),
            "path": _text(row.get("path")),
            "mimeType": _text(row.get("mimeType")),
            "size": max(0, int(row.get("size") or 0)),
            "sha256": _text(row.get("sha256")),
            "masked": bool(row.get("masked")),
            "stage": _text(row.get("stage")) if row.get("stage") else None,
        }
        for row in artifacts
    ]

    counts = {name: sum(row.get("result") == name for row in assertions) for name in ("MATCH", "MISMATCH", "MISSING_DATA", "REVIEW_REQUIRED")}
    missing_data = list(
        dict.fromkeys(
            [_text(item) for item in (run.get("missingData") or [])]
            + [_text(item) for item in (binding.get("missingData") or [])]
            + [_text(item) for item in (evidence.get("missingData") or [])]
            + [
                _text(item)
                for assertion in report_assertions
                for item in assertion.get("missingData", [])
            ]
        )
    )
    if run.get("backendTraceStatus") == "external_network_only":
        missing_data = [
            item
            for item in missing_data
            if item not in {"backend_telemetry", "backend_instrumentation"}
        ]
    consequence_codes = {
        "criterion:C-collection-change",
        "criterion:C-state-delta",
        "criterion:C-success-message",
    }
    precondition_code = next(
        (
            code
            for code in ("input_precondition_invalid", "submit_blocked_destructive")
            if code in missing_data
        ),
        None,
    )
    cascaded = (
        [item for item in missing_data if item in consequence_codes]
        if precondition_code
        else []
    )
    actionable_missing = [item for item in missing_data if item not in set(cascaded)]
    attention = []
    if counts["MISMATCH"]:
        attention.append(f"기술 불일치 {counts['MISMATCH']}건")
    if counts["MISSING_DATA"] or missing_data:
        if cascaded:
            attention.append(
                f"직접 확인할 항목 {len(actionable_missing)}건 · 제출 전 중단의 연쇄 영향 {len(cascaded)}건"
            )
        else:
            attention.append(f"자동으로 확인하지 못한 자료가 {len(missing_data)}건 있습니다")
    if counts["REVIEW_REQUIRED"] or binding.get("businessReviewRequired"):
        attention.append("담당자 판단이 필요한 검증 항목")
    if evidence.get("storageStatus") != "ready" or any(
        str(item).startswith(("screenshots/", "snapshots/"))
        for item in (evidence.get("missingData") or [])
    ):
        attention.append("증적 패키지에서 일부 자료가 수집되지 않았습니다")
    if diagnosis["outcome"] == "failure":
        attention.insert(0, diagnosis["problemSummary"])
    elif diagnosis["outcome"] == "undetermined":
        attention.insert(0, f"판정 근거 확인 필요: {diagnosis['problemSummary']}")
    if not attention:
        attention.append("자동 관측 자료 확인 후 최종 판정")

    report = {
        "schemaVersion": "run-report/v1",
        "reportId": _text(source["reportId"]),
        "runId": _text(run.get("runId")),
        "title": f"{_text(project.get('name'))} · {_text(scenario.get('name'))} 실행 검토 리포트",
        "project": {"id": _text(project.get("id")), "name": _text(project.get("name"))},
        "scenario": {
            "id": _text(scenario.get("scenarioId")),
            "name": _text(scenario.get("name")),
            "version": _text(scenario.get("version")),
            "serviceId": _text(scenario.get("serviceId")),
            "businessPath": [_text(item) for item in (scenario.get("businessPath") or [])],
            "sourceRoute": _text(source_screen.get("route") or source_screen.get("screen")),
            "destinationRoute": _text(destination_screen.get("routePattern") or destination_screen.get("screen")),
            "request": {"method": _text(request.get("method")), "path": _text(request.get("path"))},
        },
        "execution": {
            "technicalStatus": _text(run.get("status")),
            "startedAt": _text(run.get("createdAt")),
            "endedAt": _text(run.get("updatedAt")),
            "durationMs": source.get("durationMs"),
            "environmentName": _text(run.get("environmentName")),
            "browserRunner": _text(run.get("browserRunner")),
            "progressPercent": int(run.get("progressPercent") or 0),
            "plannedStepCount": int(run.get("plannedStepCount") or len(steps)),
            "completedStepCount": sum(str(row.get("status") or "").lower() not in {"queued", "running"} for row in steps),
            "outcomeKind": _text(run.get("outcomeKind")),
            "outcomeSummary": _text(run.get("outcomeSummary") or run.get("observationSummary")),
        },
        "trace": {
            "testCaseId": _text(run.get("testCaseId")),
            "agentTraceId": _text(run_result.get("agentTraceId")),
            "backendTraceStatus": _text(run.get("backendTraceStatus")),
            "repositoryUrl": _text(run.get("repositoryUrl")),
            "branch": _text(run.get("branch")),
            "commitSha": _text(run.get("commitSha")),
            "inputProfileId": _text(run.get("inputProfileId")),
        },
        "observations": observations,
        "verification": {
            "technicalStatus": _text(binding.get("technicalStatus")),
            "businessReviewRequired": bool(binding.get("businessReviewRequired")),
            "totalCount": len(assertions),
            "matchedCount": counts["MATCH"],
            "mismatchCount": counts["MISMATCH"],
            "missingCount": counts["MISSING_DATA"],
            "reviewRequiredCount": counts["REVIEW_REQUIRED"],
            "assertions": report_assertions,
        },
        "evidence": {
            "evidenceId": _text(evidence.get("evidenceId")),
            "integrityStatus": _text(evidence.get("integrityStatus")),
            "storageStatus": _text(evidence.get("storageStatus")),
            "screenshotCount": int(run.get("screenshotCount") or 0),
            "snapshotCount": int(run.get("snapshotCount") or 0),
            "artifactCount": len(artifacts),
            "maskedArtifactCount": sum(bool(row.get("masked")) for row in artifacts),
            "retentionUntil": _text(evidence.get("retentionUntil")),
            "downloadReady": bool(evidence.get("evidenceId") and evidence.get("storageStatus") == "ready"),
            "missingData": [_text(item) for item in (evidence.get("missingData") or [])],
            "artifacts": report_artifacts,
        },
        "diagnosis": diagnosis,
        "review": {
            "finalDecision": "PENDING_HUMAN_REVIEW",
            "hitlRequired": True,
            "checklist": [
                "시나리오의 A 화면 → Backend → B 화면 연결 근거 확인",
                "기대값과 실제 관측값의 기술 검증 항목 확인",
                "스크린샷·스냅샷·Network·로그의 누락 및 무결성 확인",
                "담당자가 최종 Pass/Fail 및 승인 여부 결정",
            ],
            "attentionItems": attention,
            "guardrail": "이 리포트는 자동 관측 자료를 정리한 검토 보조물이며 최종 Pass/Fail·승인은 사람이 결정합니다.",
        },
        "sourceLineage": [
            {"sourceType": "run_history", "sourceId": _text(run.get("runId")), "description": "실행 상태·단계·관측 원본"},
            {"sourceType": "scenario", "sourceId": _text(scenario.get("scenarioId")), "description": "시나리오 버전·A/API/B 계약"},
            {"sourceType": "binding_validation", "sourceId": _text(binding.get("runId")), "description": "기술 검증과 기대/실제 관측"},
            {"sourceType": "evidence_package", "sourceId": _text(evidence.get("evidenceId")), "description": "마스킹·해시된 실행 증적"},
        ],
        "generatedBy": {
            "agentName": "REPORT AGENT",
            "workflowId": "wf_run_report",
            "skillName": "run_report",
            "traceId": MISSING,
            "generatedAt": _text(source.get("generatedAt")),
        },
        "downloads": {
            "html": f"/api/runs/{_text(run.get('runId'))}/report/download?format=html",
            "json": f"/api/runs/{_text(run.get('runId'))}/report/download?format=json",
            "evidenceZip": f"/api/evidence/{_text(evidence.get('evidenceId'))}/download",
        },
        "missingData": missing_data,
        "missingDataDetails": [_missing_detail(item) for item in missing_data],
    }
    return report


def _artifact_file(evidence_id: str, artifact: dict[str, Any]) -> Path | None:
    package_root = (EVIDENCE_PACKAGES_ROOT / evidence_id).resolve()
    candidate = (package_root / str(artifact.get("path") or "")).resolve()
    if package_root != candidate and package_root not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _image_data_uri(evidence_id: str, artifact: dict[str, Any]) -> str | None:
    if not str(artifact.get("mimeType") or "").startswith("image/"):
        return None
    candidate = _artifact_file(evidence_id, artifact)
    if candidate is None or candidate.stat().st_size > 5 * 1024 * 1024:
        return None
    encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
    return f"data:{artifact['mimeType']};base64,{encoded}"


def _runtime_image_data_uri(run_id: str, ref: Any) -> str | None:
    """Embed only image evidence stored below this run's immutable evidence directory."""
    run_root = (RUN_EVIDENCE_ROOT / run_id).resolve()
    candidate = Path(str(ref or ""))
    if not candidate.is_absolute():
        candidate = run_root / candidate
    candidate = candidate.resolve()
    if run_root != candidate and run_root not in candidate.parents:
        return None
    suffix = candidate.suffix.lower()
    mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix)
    if not mime_type or not candidate.is_file() or candidate.stat().st_size > 8 * 1024 * 1024:
        return None
    encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _mascot_data_uri() -> str | None:
    if not REPORT_MASCOT_PATH.is_file() or REPORT_MASCOT_PATH.stat().st_size > 2 * 1024 * 1024:
        return None
    encoded = base64.b64encode(REPORT_MASCOT_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _percent(numerator: int, denominator: int) -> int:
    return min(100, max(0, round((numerator / denominator) * 100))) if denominator else 0


def render_report_html(report: dict[str, Any]) -> str:
    esc = lambda value: html.escape(_text(value))
    execution = report["execution"]
    verification = report["verification"]
    evidence = report["evidence"]
    scenario = report["scenario"]
    diagnosis = report["diagnosis"]
    action_labels = {
        "navigate": "화면 이동", "click": "클릭", "fill": "값 입력", "select": "항목 선택",
        "assert_visible": "화면 표시 확인", "assert_text": "안내 문구 확인",
        "wait_for_response": "응답 확인", "verify_navigation": "이동 결과 확인",
        "verify_numeric_delta": "화면 값 변화 확인", "verify_collection_change": "목록 변화 확인",
        "capture_value": "변경 전 값 기록", "capture_collection": "변경 전 목록 기록",
        "set_headers": "실행 추적 준비",
    }
    status_labels = {
        "ok": "관측 완료", "warning": "확인 필요", "skipped": "안전 정책으로 미실행",
        "queued": "대기", "running": "실행 중", "error": "오류",
    }
    result_labels = {
        "MATCH": "일치", "MISMATCH": "불일치", "MISSING_DATA": "자료 확인 필요",
        "REVIEW_REQUIRED": "담당자 확인",
    }
    field_labels = {"httpStatus": "서버 응답 상태", "route": "결과 화면 경로"}
    status_counts: dict[str, int] = {}
    for row in report["observations"]:
        key = str(row.get("status") or "unknown").lower()
        status_counts[key] = status_counts.get(key, 0) + 1
    observation_total = len(report["observations"])
    observation_ok = status_counts.get("ok", 0)
    observation_attention = sum(status_counts.get(key, 0) for key in ("warning", "skipped", "error"))
    attention_observations = [
        row for row in report["observations"]
        if str(row.get("status") or "").lower() in {"warning", "skipped", "error"}
    ]
    attention_steps = "".join(
        "".join(
            [
                "<article class='finding warning'>",
                f"<span>{esc(row['stepId'])} · {esc(action_labels.get(row['action'], row['action']))}</span>",
                f"<strong>{esc(status_labels.get(str(row['status']).lower(), row['status']))}</strong>",
                f"<p>{esc(row['observation'])}</p>",
                "</article>",
            ]
        )
        for row in attention_observations
    ) or "<article class='finding success'><span>자동 관측</span><strong>추가 확인 단계 없음</strong><p>모든 실행 단계가 정상적으로 관측됐습니다.</p></article>"
    assertions = "".join(
        f"<tr><td>{esc(field_labels.get(row['field'], row['field']))}</td><td><span class='tag'>{esc(result_labels.get(row['result'], row['result']))}</span></td><td>{esc(row['expected'])}</td><td>{esc('확인 자료 없음' if row['actual'] == MISSING else row['actual'])}</td></tr>"
        for row in verification["assertions"]
    ) or "<tr><td colspan='4'>기술 검증 항목이 없습니다.</td></tr>"
    attention = "".join(f"<li>{esc(item)}</li>" for item in report["review"]["attentionItems"])
    missing_details = list(report.get("missingDataDetails", []))
    consequence_codes = {
        "criterion:C-collection-change",
        "criterion:C-state-delta",
        "criterion:C-success-message",
    }
    precondition_code = next(
        (
            code
            for code in ("input_precondition_invalid", "submit_blocked_destructive")
            if any(item.get("code") == code for item in missing_details)
        ),
        None,
    )
    if precondition_code:
        consequence_count = sum(item.get("code") in consequence_codes for item in missing_details)
        missing_details = [item for item in missing_details if item.get("code") not in consequence_codes]
        if consequence_count:
            missing_details.insert(
                1,
                {
                    "code": "submit_precondition_consequences",
                    "section": "연쇄 영향",
                    "label": f"제출 전 중단으로 결과 확인 {consequence_count}건이 함께 중단됐습니다",
                    "guidance": "완료 문구·화면 값·목록 변화는 제출이 실제 실행된 뒤 한 번에 다시 확인됩니다.",
                },
            )
    missing = "".join(
        f"<article class='missing-card'><span>{esc(item['section'])}</span><strong>{esc(item['label'])}</strong><p>{esc(item['guidance'])}</p></article>"
        for item in missing_details[:6]
    ) or "<p>추가로 확인할 누락 자료가 없습니다.</p>"
    missing_more = (
        f"<p class='more-note'>그 외 {len(missing_details) - 6}건은 구조화 JSON과 증적 ZIP에서 확인할 수 있습니다.</p>"
        if len(missing_details) > 6 else ""
    )
    artifact_rows = "".join(
        f"<tr data-inventory-item='{index}' data-artifact-id='{esc(item['artifactId'])}'><td>{index}</td><td>{esc(item['label'])}</td><td>{esc(item['path'])}</td><td>{item['size']:,} B</td><td>{'적용' if item['masked'] else '해당 없음'}</td><td><code>{esc(item['sha256'][:16])}…</code></td></tr>"
        for index, item in enumerate(evidence.get("artifacts", []), start=1)
    ) or "<tr><td colspan='6'>증적 파일이 없습니다.</td></tr>"
    package_images = []
    for index, item in enumerate(evidence.get("artifacts", []), start=1):
        data_uri = _image_data_uri(evidence["evidenceId"], item)
        if not data_uri:
            continue
        package_images.append(
            "".join(
                [
                    f"<figure class='stage-evidence' data-evidence-item='{index}' data-artifact-id='{esc(item['artifactId'])}'>",
                    f"<button type='button' class='evidence-open' data-evidence-open aria-label='{esc(item['label'])} 크게 보기'><img src='{data_uri}' alt='{esc(item['label'])}'></button>",
                    f"<figcaption><strong>{esc(item['label'])}</strong><span>{esc(Path(item['path']).name)}</span></figcaption>",
                    "</figure>",
                ]
            )
        )
    package_image_html = "".join(package_images) or "<p>대표 화면 증적이 없습니다.</p>"

    runtime_images = []
    seen_runtime_refs: set[str] = set()
    for row in report["observations"]:
        for ref in row.get("evidenceRefs", []):
            ref_text = str(ref or "")
            if ref_text in seen_runtime_refs:
                continue
            data_uri = _runtime_image_data_uri(report["runId"], ref_text)
            if not data_uri:
                continue
            seen_runtime_refs.add(ref_text)
            runtime_images.append(
                "".join(
                    [
                        "<figure class='capture-evidence'>",
                        f"<button type='button' class='evidence-open' data-evidence-open aria-label='{esc(row['stepId'])} 실행 화면 크게 보기'><img src='{data_uri}' alt='{esc(row['stepId'])} 실행 화면'></button>",
                        f"<figcaption><strong>{esc(row['stepId'])} · {esc(action_labels.get(row['action'], row['action']))}</strong><span>{esc(status_labels.get(str(row['status']).lower(), row['status']))}</span></figcaption>",
                        "</figure>",
                    ]
                )
            )
    runtime_image_html = "".join(runtime_images) or "<p>단계별 실행 화면이 없습니다.</p>"
    visual_evidence_count = len(package_images) + len(runtime_images)

    execution_progress = int(execution.get("progressPercent") or 0)
    verification_observed = verification["totalCount"] - verification["missingCount"]
    verification_progress = _percent(verification_observed, verification["totalCount"])
    observation_progress = _percent(observation_ok, observation_total)
    screenshot_progress = _percent(len(runtime_images), int(evidence.get("screenshotCount") or 0))
    masked_progress = _percent(evidence["maskedArtifactCount"], evidence["artifactCount"])
    diagnosis_outcome = str(diagnosis.get("outcome") or "undetermined")
    diagnosis_tone = "failure" if diagnosis_outcome == "failure" else "success" if diagnosis_outcome == "success" else "warning"
    diagnosis_value = 100 if diagnosis_outcome == "success" else 0 if diagnosis_outcome == "failure" else 50
    diagnosis_label = {
        "success": "성공 기준 관측",
        "failure": "기대 결과 불일치",
        "undetermined": "담당자 확인 필요",
    }.get(diagnosis_outcome, diagnosis.get("headline") or diagnosis_outcome)
    diagnosis_copy = {
        "success": {
            "section": "AI 관측 결과 및 최종 검토 가이드",
            "problem": "무엇이 정상 관측됐나요?",
            "cause": "어떤 근거로 성공을 확인했나요?",
            "action": "담당자는 무엇을 확인하나요?",
            "retest": "최종 검토 조건",
            "fallback": "자동 관측 근거와 증적을 확인한 뒤 최종 결과를 판정하세요.",
        },
        "failure": {
            "section": "AI 관측 진단 및 조치 가이드",
            "problem": "무슨 문제가 있었나요?",
            "cause": "왜 이런 결과가 발생했나요?",
            "action": "조치 제안",
            "retest": "재검증 조건",
            "fallback": "실패 단계와 증적을 확인한 뒤 같은 조건으로 재검증해 주세요.",
        },
        "undetermined": {
            "section": "AI 관측 확인 및 근거 보강 가이드",
            "problem": "무엇을 확인해야 하나요?",
            "cause": "왜 판정이 보류됐나요?",
            "action": "근거 보강 안내",
            "retest": "재확인 조건",
            "fallback": "누락된 실행 단계와 증적을 보강한 뒤 다시 확인하세요.",
        },
    }.get(diagnosis_outcome, {})
    diagnosis_color = "#198038" if diagnosis_tone == "success" else "#c73e4a" if diagnosis_tone == "failure" else "#b26a00"
    diagnosis_actions = "".join(
        "".join(
            [
                "<li>",
                f"<strong>{esc(item['owner'])}</strong>",
                f"<span>{esc(item['action'])}</span>",
                f"<small>{esc(item['reason'])}</small>",
                "</li>",
            ]
        )
        for item in diagnosis.get("actions", [])
    ) or f"<li><strong>개발·QA 담당</strong><span>{esc(diagnosis_copy.get('fallback'))}</span></li>"
    diagnosis_evidence = "".join(f"<li>{esc(item)}</li>" for item in diagnosis.get("evidence", [])) or "<li>구조화된 실행 단계와 증적 패키지를 확인해 주세요.</li>"
    mascot_uri = _mascot_data_uri()
    mascot = f"<img class='mascot' src='{mascot_uri}' alt='QA 리포트 도우미 캐릭터'>" if mascot_uri else "<div class='mascot-fallback'>🤖</div>"
    technical_label = {
        "AUTO_FAILED": "자동 관측 확인 필요",
        "WAITING_FOR_REVIEW": "실행 관측 완료",
        "COMPLETED": "실행 관측 완료",
        "COMPLETE": "실행 관측 완료",
    }.get(str(execution["technicalStatus"]).upper(), execution["technicalStatus"])
    integrity_label = {
        "complete": "파일·해시 확인 완료",
        "partial": "필수 파일 확인 필요",
        "corrupted": "파일 무결성 오류",
    }.get(evidence["integrityStatus"], evidence["integrityStatus"])
    return f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>{esc(report['title'])}</title>
<style>
:root{{--violet:#625cff;--violet-dark:#4338a8;--blue:#0043ce;--green:#198038;--amber:#b26a00;--red:#c73e4a;--ink:#20243a;--muted:#6f7285;--line:#e4e6ef;--soft:#f5f6fb}}
*{{box-sizing:border-box}}body{{font-family:Arial,'Noto Sans KR',sans-serif;color:var(--ink);margin:0;background:var(--soft);-webkit-print-color-adjust:exact;print-color-adjust:exact}}main{{max-width:1120px;margin:24px auto;background:#fff;padding:34px;border-radius:18px}}.hero{{position:relative;min-height:154px;overflow:hidden;border:1px solid #ddd9ff;border-radius:18px;padding:26px 230px 26px 28px;background:linear-gradient(120deg,#f0eeff 0%,#eef7ff 58%,#fff1f4 100%)}}.hero:after{{content:'';position:absolute;width:240px;height:240px;border:1px solid rgba(98,92,255,.12);border-radius:50%;right:84px;top:-84px}}h1{{font-size:25px;line-height:1.35;margin:8px 0 6px}}h2{{font-size:19px;margin:34px 0 14px;color:var(--violet-dark);border-bottom:1px solid #e8e7f2;padding-bottom:9px}}h3{{font-size:15px;margin:24px 0 10px}}p{{line-height:1.55}}.kicker{{font-weight:800;color:var(--violet);font-size:12px;letter-spacing:.04em}}.hero-sub{{font-size:12px;color:var(--muted);margin:0}}.mascot{{position:absolute;right:18px;bottom:-50px;width:205px;height:205px;object-fit:contain;z-index:1}}.mascot-fallback{{position:absolute;right:48px;top:34px;font-size:70px}}.hero-status{{display:inline-flex;margin-top:14px;padding:6px 11px;border-radius:999px;background:#fff7e8;color:#8a5700;border:1px solid #f1cf96;font-size:12px;font-weight:800}}.guard{{background:#f1efff;border:1px solid #d9d4ff;padding:13px 15px;border-radius:10px;font-size:12px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.metric{{display:flex;align-items:center;gap:12px;padding:14px;border:1px solid var(--line);border-radius:12px;break-inside:avoid}}.donut{{--value:0;--color:var(--violet);position:relative;display:grid;place-items:center;width:58px;height:58px;border-radius:50%;background:conic-gradient(var(--color) calc(var(--value)*1%),#eceef4 0);flex:0 0 auto}}.donut:after{{content:'';position:absolute;inset:7px;border-radius:50%;background:#fff}}.donut strong{{position:relative;z-index:1;font-size:14px}}.metric-copy span{{display:block;color:var(--muted);font-size:10px}}.metric-copy strong{{display:block;margin-top:3px;font-size:14px}}.progress-card{{display:grid;grid-template-columns:40px 1fr;gap:10px;align-items:center;padding:14px 16px;border-radius:10px;border:1px solid var(--line)}}.progress-icon{{display:grid;place-items:center;width:40px;height:40px;border-radius:50%;background:var(--green);color:#fff;font-weight:900}}.progress-top{{display:flex;align-items:end;gap:8px;margin-bottom:6px}}.progress-top strong{{font-size:18px}}.progress-top span{{font-size:10px;color:var(--muted);letter-spacing:.04em}}.progress-track{{height:8px;border-radius:99px;background:#e0e0e0;overflow:hidden}}.progress-fill{{height:100%;border-radius:99px;background:var(--green)}}.journey{{display:grid;grid-template-columns:1fr 42px 1fr 42px 1fr;align-items:stretch;gap:8px}}.journey-card{{padding:15px;border:1px solid var(--line);border-radius:12px;background:#fafaff;break-inside:avoid}}.journey-card span{{display:block;font-size:10px;color:var(--violet);font-weight:800}}.journey-card strong{{display:block;margin:7px 0;font-size:14px}}.journey-card small{{color:var(--muted)}}.journey-arrow{{display:grid;place-items:center;color:var(--violet);font-size:24px;font-weight:900}}.status-bar{{display:flex;height:14px;border-radius:99px;overflow:hidden;background:#eceef4;margin:12px 0 8px}}.status-bar span{{min-width:0}}.status-ok{{background:var(--green)}}.status-warning{{background:#e6a23c}}.status-skipped{{background:#9aa0ad}}.status-error{{background:var(--red)}}.legend{{display:flex;gap:18px;font-size:11px;color:var(--muted)}}.legend b{{color:var(--ink)}}.finding-grid,.missing-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.finding,.missing-card{{border:1px solid #f1c783;background:#fffaf0;border-radius:10px;padding:12px;break-inside:avoid}}.finding.success{{border-color:#acd8b8;background:#f3fbf5}}.finding span,.missing-card span{{display:block;color:#9a6500;font-size:10px;font-weight:700}}.finding.success span{{color:var(--green)}}.finding strong,.missing-card strong{{display:block;margin:5px 0;font-size:13px}}.finding p,.missing-card p{{margin:0;color:#5f6073;font-size:12px;line-height:1.5}}.more-note{{font-size:11px;color:var(--muted)}}table{{width:100%;border-collapse:collapse;font-size:11px;page-break-inside:auto}}tr{{page-break-inside:avoid}}th,td{{border-bottom:1px solid #ececf2;text-align:left;padding:8px;vertical-align:top}}th{{background:#f7f7fb}}.tag{{display:inline-block;background:#eeeaff;color:#5146bc;padding:3px 7px;border-radius:999px;font-weight:700}}ul{{line-height:1.7}}.evidence-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.stat-card{{padding:13px;border:1px solid var(--line);border-radius:10px}}.stat-card span{{display:block;color:var(--muted);font-size:10px}}.stat-card strong{{display:block;margin-top:5px;font-size:18px}}.stage-gallery{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}figure{{margin:0}}.stage-evidence,.capture-evidence{{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff;break-inside:avoid}}.evidence-open{{display:block;width:100%;margin:0;padding:0;border:0;background:#f4f5f8;cursor:zoom-in}}.evidence-open:focus-visible{{outline:3px solid var(--violet);outline-offset:-3px}}.stage-evidence img{{display:block;width:100%;height:172px;object-fit:contain;background:#f4f5f8}}figcaption{{display:flex;justify-content:space-between;gap:8px;padding:9px 10px;font-size:10px}}figcaption strong{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}figcaption span{{color:var(--muted);white-space:nowrap}}.capture-gallery{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.capture-evidence img{{display:block;width:100%;height:138px;object-fit:cover;object-position:top;background:#f4f5f8}}.capture-note{{font-size:11px;color:var(--muted)}}.inventory-note{{padding:10px 12px;border-radius:9px;background:#f5f4ff;color:#555070;font-size:11px}}.evidence-viewer{{width:min(1180px,94vw);max-height:92vh;padding:0;border:0;border-radius:16px;box-shadow:0 24px 70px rgba(28,31,53,.38)}}.evidence-viewer::backdrop{{background:rgba(20,23,39,.78)}}.evidence-viewer header{{position:sticky;top:0;z-index:1;display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#fff;border-bottom:1px solid var(--line)}}.evidence-viewer header strong{{font-size:13px}}.evidence-viewer-close{{border:1px solid var(--line);border-radius:8px;background:#fff;padding:7px 11px;cursor:pointer}}.evidence-viewer img{{display:block;max-width:100%;height:auto;margin:0 auto;background:#fff}}code{{font-size:9px;color:#66697b}}main>footer{{margin-top:30px;color:#777b8e;font-size:10px}}@media print{{@page{{size:A4;margin:12mm}}body{{background:#fff}}main{{margin:0;max-width:none;border-radius:0;padding:0}}.hero{{min-height:135px}}.mascot{{width:170px;height:170px}}h2{{break-after:avoid}}.metrics,.evidence-stats{{grid-template-columns:repeat(4,1fr)}}.capture-gallery,.stage-gallery{{grid-template-columns:repeat(3,1fr)}}.capture-evidence img{{height:105px}}.stage-evidence img{{height:135px}}.hero,.metric,.progress-card,.journey-card,.finding,.missing-card,.stage-evidence,.capture-evidence{{break-inside:avoid}}.evidence-viewer{{display:none}}}}@media(max-width:760px){{main{{margin:0;padding:18px}}.hero{{padding:22px 20px}}.mascot{{display:none}}.metrics,.evidence-stats,.finding-grid,.missing-grid,.stage-gallery,.capture-gallery{{grid-template-columns:1fr}}.journey{{grid-template-columns:1fr}}.journey-arrow{{transform:rotate(90deg)}}}}
.hero-status.is-failure{{background:#fff0f0;color:#9d222d;border-color:#efb5ba}}.hero-status.is-success{{background:#edf9f1;color:#126b31;border-color:#a9dbb8}}.diagnosis-card{{border:1px solid #efd0d3;border-left:6px solid var(--red);border-radius:14px;background:#fff6f6;padding:18px;break-inside:avoid}}.diagnosis-card.is-warning{{border-color:#efd49f;border-left-color:var(--amber);background:#fffaf0}}.diagnosis-card.is-success{{border-color:#afd9ba;border-left-color:var(--green);background:#f3fbf5}}.diagnosis-card header{{display:flex;align-items:center;justify-content:space-between;gap:12px}}.diagnosis-card header span{{padding:4px 8px;border-radius:999px;background:#fff;font-size:10px;font-weight:800}}.diagnosis-card h3{{margin:0}}.diagnosis-summary{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}}.diagnosis-summary>div{{padding:12px;border:1px solid rgba(90,60,70,.12);border-radius:10px;background:#fff}}.diagnosis-summary strong{{display:block;font-size:11px}}.diagnosis-summary p{{margin:5px 0 0;font-size:12px;color:#5f6073}}.diagnosis-actions{{display:grid;gap:8px;padding:0;list-style:none}}.diagnosis-actions li{{display:grid;grid-template-columns:130px 1fr;gap:4px 12px;padding:10px 12px;border-radius:9px;background:#fff}}.diagnosis-actions strong{{font-size:11px}}.diagnosis-actions span{{font-size:12px;line-height:1.5}}.diagnosis-actions small{{grid-column:2;color:var(--muted)}}.diagnosis-retest{{padding:11px 13px;border-radius:9px;background:#f1efff;font-size:12px}}
</style></head><body><main>
<header class='hero'><span class='kicker'>REPORT AGENT · 시각화 실행 검토</span><h1>{esc(report['title'])}</h1><p class='hero-sub'>{esc(report['project']['name'])} · {esc(scenario['name'])} · {esc(report['runId'])}</p><span class='hero-status is-{diagnosis_tone}'>{esc(diagnosis_label)} · 최종 판정은 담당자 검토</span>{mascot}</header>
<p class='guard'>{esc(report['review']['guardrail'])}</p>
<h2>1. 실행 결과 한눈에 보기</h2>
<div class='metrics'><div class='metric'><div class='donut' style='--value:{execution_progress};--color:#625cff'><strong>{execution_progress}%</strong></div><div class='metric-copy'><span>실행 진행</span><strong>{execution['completedStepCount']}/{execution['plannedStepCount']}단계</strong></div></div><div class='metric'><div class='donut' style='--value:{diagnosis_value};--color:{diagnosis_color}'><strong>{diagnosis_value}%</strong></div><div class='metric-copy'><span>AI 관측 판정</span><strong>{esc(diagnosis_label)}</strong></div></div><div class='metric'><div class='donut' style='--value:{verification_progress};--color:#0043ce'><strong>{verification_observed}</strong></div><div class='metric-copy'><span>검증 자료 확보</span><strong>전체 {verification['totalCount']}항목</strong></div></div><div class='metric'><div class='donut' style='--value:{screenshot_progress};--color:#625cff'><strong>{len(runtime_images)}</strong></div><div class='metric-copy'><span>실행 화면 증적</span><strong>캡처 {evidence['screenshotCount']}장</strong></div></div></div>
<h3>전체 실행 진행률</h3><div class='progress-card'><div class='progress-icon'>✓</div><div><div class='progress-top'><strong>{execution_progress}%</strong><span>{esc(technical_label)}</span></div><div class='progress-track' role='progressbar' aria-label='전체 실행 진행률' aria-valuemin='0' aria-valuemax='100' aria-valuenow='{execution_progress}'><div class='progress-fill' style='width:{execution_progress}%'></div></div></div></div>
<h3>관통 시나리오</h3><div class='journey'><div class='journey-card'><span>A 화면 · 입력</span><strong>{esc(scenario['sourceRoute'])}</strong><small>사용자 입력과 시작 화면</small></div><div class='journey-arrow'>→</div><div class='journey-card'><span>Backend · 요청</span><strong>{esc(scenario['request']['method'])} {esc(scenario['request']['path'])}</strong><small>화면에서 서버로 전달되는 처리</small></div><div class='journey-arrow'>→</div><div class='journey-card'><span>B 화면 · 결과</span><strong>{esc(scenario['destinationRoute'])}</strong><small>이동·안내·값 변경 관측</small></div></div>
<h3>단계별 관측 분포</h3><div class='status-bar' aria-label='단계별 관측 분포'><span class='status-ok' style='width:{_percent(status_counts.get('ok', 0), observation_total)}%'></span><span class='status-warning' style='width:{_percent(status_counts.get('warning', 0), observation_total)}%'></span><span class='status-skipped' style='width:{_percent(status_counts.get('skipped', 0), observation_total)}%'></span><span class='status-error' style='width:{_percent(status_counts.get('error', 0), observation_total)}%'></span></div><div class='legend'><span>● 정상 관측 <b>{observation_ok}</b></span><span>● 확인 필요 <b>{observation_attention}</b></span><span>● 전체 <b>{observation_total}</b></span></div>
<h3>자동 관측 요약</h3><p>{esc(execution['outcomeSummary'])}</p><div class='finding-grid'>{attention_steps}</div>
<h2>2. {esc(diagnosis_copy.get('section'))}</h2><section class='diagnosis-card is-{diagnosis_tone}'><header><h3>{esc(diagnosis['headline'])}</h3><span>{esc(diagnosis_label)}</span></header><div class='diagnosis-summary'><div><strong>{esc(diagnosis_copy.get('problem'))}</strong><p>{esc(diagnosis['problemSummary'])}</p></div><div><strong>{esc(diagnosis_copy.get('cause'))}</strong><p>{esc(diagnosis['causeSummary'])}</p></div></div><h3>관측 근거</h3><ul>{diagnosis_evidence}</ul><h3>{esc(diagnosis_copy.get('action'))}</h3><ul class='diagnosis-actions'>{diagnosis_actions}</ul><p class='diagnosis-retest'><strong>{esc(diagnosis_copy.get('retest'))}</strong> · {esc(diagnosis['retestCondition'])}</p></section>
<h2>3. 기술 검증</h2><div class='evidence-stats'><div class='stat-card'><span>검증 상태</span><strong>{esc(verification['technicalStatus'])}</strong></div><div class='stat-card'><span>일치</span><strong>{verification['matchedCount']}건</strong></div><div class='stat-card'><span>불일치</span><strong>{verification['mismatchCount']}건</strong></div><div class='stat-card'><span>자료 확인 필요</span><strong>{verification['missingCount']}건</strong></div></div><table><thead><tr><th>검증 항목</th><th>결과</th><th>기대값</th><th>관측값</th></tr></thead><tbody>{assertions}</tbody></table>
<h3>먼저 확인할 내용</h3><ul>{attention}</ul><div class='missing-grid'>{missing}</div>{missing_more}
<h2>4. 증적 패키지</h2><div class='evidence-stats'><div class='stat-card'><span>패키지 파일</span><strong>{evidence['artifactCount']}건</strong></div><div class='stat-card'><span>시각 증적</span><strong>{visual_evidence_count}장</strong></div><div class='stat-card'><span>시각 증적 구성</span><strong>대표 {len(package_images)} + 단계 {len(runtime_images)}</strong></div><div class='stat-card'><span>파일 무결성</span><strong>{esc(integrity_label)}</strong></div></div>
<p class='inventory-note'>패키지 파일 {evidence['artifactCount']}건은 PNG뿐 아니라 JSON·화면 구조·Network를 모두 합한 수입니다. 화면으로 보는 증적은 대표 화면 {len(package_images)}장과 단계별 캡처 {len(runtime_images)}장, 총 {visual_evidence_count}장입니다.</p>
<h3>핵심 화면 증적 {len(package_images)}장 · A 화면 → 입력 완료 → B 결과</h3><div class='stage-gallery'>{package_image_html}</div>
<h3>단계별 실행 화면 {len(runtime_images)}/{evidence['screenshotCount']}장</h3><p class='capture-note'>모든 실행 캡처를 인쇄 가능한 썸네일로 포함했습니다. 화면을 클릭하면 원본 크기로 확인할 수 있습니다.</p><div class='capture-gallery'>{runtime_image_html}</div>
<h3>증적 파일 {evidence['artifactCount']}건 인벤토리</h3><p class='inventory-note'>JSON·화면 구조·Network·로그는 인쇄 본문에 원문을 펼치지 않습니다. 아래 파일명·크기·마스킹·해시로 누락 여부를 확인하고, 전체 내용은 증적 ZIP 또는 구조화 JSON에서 검토합니다.</p>
<h3>증적 파일 전체 목록</h3><table><thead><tr><th>번호</th><th>증적 내용</th><th>파일</th><th>크기</th><th>마스킹</th><th>무결성 해시</th></tr></thead><tbody>{artifact_rows}</tbody></table>
<footer>생성: {esc(report['generatedBy']['generatedAt'])} · Workflow {esc(report['generatedBy']['workflowId'])} · Trace {esc(report['generatedBy']['traceId'])}</footer>
</main><dialog id='evidence-viewer' class='evidence-viewer' aria-labelledby='evidence-viewer-title'><header><strong id='evidence-viewer-title'>증적 원본 보기</strong><button type='button' class='evidence-viewer-close' data-evidence-close>닫기</button></header><img id='evidence-viewer-image' alt='선택한 증적 원본'></dialog>
<script>(()=>{{const viewer=document.getElementById('evidence-viewer');const image=document.getElementById('evidence-viewer-image');const title=document.getElementById('evidence-viewer-title');if(!viewer||!image)return;document.querySelectorAll('[data-evidence-open]').forEach((button)=>{{button.addEventListener('click',()=>{{const selected=button.querySelector('img');if(!selected)return;image.src=selected.src;image.alt=selected.alt||'선택한 증적 원본';if(title)title.textContent=selected.alt||'증적 원본 보기';viewer.showModal();}});}});viewer.querySelector('[data-evidence-close]')?.addEventListener('click',()=>viewer.close());viewer.addEventListener('click',(event)=>{{if(event.target===viewer)viewer.close();}});}})();</script></body></html>"""


def write_artifacts(report: dict[str, Any], artifact_path: Path, html_path: Path) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_report_html(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    source = payload.get("reportSource")
    if not isinstance(source, dict):
        raise ValueError("reportSource must be an object")
    artifact_path = Path(str(payload.get("artifactPath") or ""))
    html_path = Path(str(payload.get("htmlPath") or ""))
    if not str(artifact_path) or not str(html_path):
        raise ValueError("artifactPath and htmlPath are required")
    report = build_report(source)
    write_artifacts(report, artifact_path, html_path)
    output = {
        "ok": True,
        "runId": report["runId"],
        "reportId": report["reportId"],
        "artifactPath": str(artifact_path),
        "htmlPath": str(html_path),
        "result": report,
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
