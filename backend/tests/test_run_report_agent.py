from __future__ import annotations

import json
import base64
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import RUN_REPORT_SCHEMA
from app.main import app
from app.schemas.binding_validation import BindingAssertion, BindingValidationResult
from app.schemas.evidence import EvidenceArtifact, EvidenceManifest
from app.services.repository_models import ProjectCreate
from app.services.run_models import RunStepSummary, RunSummary
from app.services.run_report_service import RunReportService
from app.services.scenario_models import ScenarioSummary
from app.skills.run_report.script import generate_report


client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    bootstrap_runtime()
    store = get_platform_store()
    for attr in (
        "_projects", "_sets", "_scenarios", "_runs", "_binding_results",
        "_evidence_manifests", "_backend_events", "_backend_seq",
    ):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    monkeypatch.setattr("app.services.run_report_service.ARTIFACTS_REPORTS", tmp_path / "reports")
    monkeypatch.setattr(generate_report, "EVIDENCE_PACKAGES_ROOT", tmp_path / "evidence" / "packages")
    monkeypatch.setattr(generate_report, "RUN_EVIDENCE_ROOT", tmp_path / "evidence" / "runs")
    monkeypatch.setattr(generate_report, "REPORT_MASCOT_PATH", tmp_path / "missing-mascot.png")
    yield


def _now(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def _seed(run_id: str = "RUN-report-agent", *, artifact_count: int = 1) -> None:
    store = get_platform_store()
    project = store.create_project(ProjectCreate(name="AI 해커톤 프로젝트", ownerUserId="TEST"))
    scenario = ScenarioSummary(
        scenarioId="SCN-report-agent",
        projectId=project.id,
        serviceId="signup",
        name="회원가입 후 홈 화면 이동 확인",
        version="4",
        status="EXECUTABLE",
        businessPath=["회원", "가입"],
        result={
            "source": {"route": "/signup"},
            "request": {"method": "POST", "path": "/api/signup"},
            "destination": {"routePattern": "/home"},
        },
    )
    store.save_scenario(scenario)
    run_evidence_root = generate_report.RUN_EVIDENCE_ROOT / run_id
    run_evidence_root.mkdir(parents=True, exist_ok=True)
    screenshot_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    first_screenshot = run_evidence_root / "01-source.png"
    second_screenshot = run_evidence_root / "02-destination.png"
    first_screenshot.write_bytes(screenshot_bytes)
    second_screenshot.write_bytes(screenshot_bytes)
    store.save_run(
        RunSummary(
            runId=run_id,
            scenarioId=scenario.scenarioId,
            projectId=project.id,
            status="WAITING_FOR_REVIEW",
            environmentName="Pilot Chrome",
            testCaseId="TC-report",
            backendTraceStatus="linked",
            repositoryUrl="https://example.invalid/repo.git",
            branch="main",
            commitSha="abc123",
            inputProfileId="IP-report",
            screenshotCount=2,
            snapshotCount=2,
            plannedStepCount=2,
            progressPercent=100,
            inputs={"password": "must-not-appear", "token": "must-not-appear"},
            steps=[
                RunStepSummary(stepId="S1", action="navigate", status="ok", observationSummary="입력 #login-username = hidden-account", screenshotPath=str(first_screenshot)),
                RunStepSummary(stepId="S2", action="assert_visible", status="ok", observationSummary="홈 화면 관측", screenshotPath=str(second_screenshot)),
            ],
            outcomeKind="success",
            outcomeSummary="기대 경로 /home을 관측했습니다.",
            result={
                "agentTraceId": "PLAN-browser-run",
                "verdict": {
                    "verdict": "expected_met",
                    "reason": "기대 경로 /home을 관측했습니다.",
                    "criteriaResults": [
                        {
                            "id": "C-route",
                            "check": "destination_route",
                            "expected": "/home",
                            "result": "met",
                            "observed": "/home",
                        }
                    ],
                },
            },
            createdAt=_now(-2),
            updatedAt=_now(),
        )
    )
    store.save_binding_result(
        BindingValidationResult(
            runId=run_id,
            scenarioId=scenario.scenarioId,
            technicalStatus="TECHNICALLY_MATCHED",
            businessReviewRequired=False,
            assertions=[
                BindingAssertion(
                    assertionId="BA-report",
                    field="route",
                    source="scenario.destination",
                    target="browser.currentUrl",
                    expected="/home",
                    actual="/home",
                    result="MATCH",
                )
            ],
            createdAt=_now(),
        )
    )
    if artifact_count == 1:
        artifacts = [
            EvidenceArtifact(
                artifactId="ART-report-response",
                type="backend",
                path="backend/response.json",
                mimeType="application/json",
                size=128,
                sha256="a" * 64,
                createdAt=_now(),
                masked=True,
                stage="backend",
            )
        ]
    else:
        artifacts = [
            EvidenceArtifact(
                artifactId=f"ART-report-{index:02d}",
                type="snapshot" if index % 2 else "network",
                path=f"details/evidence-{index:02d}.json",
                mimeType="application/json",
                size=48,
                sha256=(f"{index:x}" * 64)[:64],
                createdAt=_now(),
                masked=True,
                stage="destination" if index % 2 else "backend",
            )
            for index in range(1, artifact_count + 1)
        ]
    package_root = generate_report.EVIDENCE_PACKAGES_ROOT / f"EVID-{run_id}"
    for artifact in artifacts:
        target = package_root / artifact.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"artifactId": artifact.artifactId, "observed": True}, ensure_ascii=False),
            encoding="utf-8",
        )
    store.save_evidence_manifest(
        EvidenceManifest(
            evidenceId=f"EVID-{run_id}",
            runId=run_id,
            projectId=project.id,
            ownerUserId="TEST",
            scenario={"id": scenario.scenarioId, "version": scenario.version},
            inputProfile={"id": "IP-report", "version": "1"},
            technicalStatus="TECHNICALLY_MATCHED",
            artifacts=artifacts,
            integrityStatus="partial",
            storageStatus="ready",
            missingData=["backend_response"],
            retentionUntil=_now(86400),
            createdAt=_now(),
        )
    )


def test_report_agent_generates_schema_complete_report_and_html():
    _seed()
    service = RunReportService(get_platform_store())
    report = service.generate("RUN-report-agent")

    assert report.schemaVersion == "run-report/v1"
    assert report.generatedBy.agentName == "REPORT AGENT"
    assert report.generatedBy.workflowId == "wf_run_report"
    assert report.generatedBy.traceId.startswith("PLAN-")
    assert report.review.finalDecision == "PENDING_HUMAN_REVIEW"
    assert report.verification.matchedCount == 1
    assert report.scenario.request.path == "/api/signup"
    assert report.evidence.artifactCount == 1
    assert report.diagnosis.outcome == "success"
    assert report.missingDataDetails[0].label == "서버 응답 내용을 수집하지 못했습니다"

    body = report.model_dump(mode="json", by_alias=True)
    Draft202012Validator(json.loads(RUN_REPORT_SCHEMA.read_text(encoding="utf-8"))).validate(body)
    serialized = json.dumps(body, ensure_ascii=False)
    assert "must-not-appear" not in serialized
    assert "hidden-account" not in serialized
    assert "#login-username = ***" in serialized
    assert "final_pass" not in serialized.lower()

    html_path = service.download_path(report.runId, "html")
    html = html_path.read_text(encoding="utf-8")
    assert "REPORT AGENT" in html
    assert "최종 판정은 담당자 검토" in html
    assert "회원가입 후 홈 화면 이동 확인" in html
    assert "1. 실행 결과 한눈에 보기" in html
    assert "2. AI 관측 결과 및 최종 검토 가이드" in html
    assert "무엇이 정상 관측됐나요?" in html
    assert "어떤 근거로 성공을 확인했나요?" in html
    assert "무슨 문제가 있었나요?" not in html
    assert "3. 기술 검증" in html
    assert "4. 증적 패키지" in html
    assert "실행 결과 한눈에 보기" in html
    assert "전체 실행 진행률" in html
    assert "단계별 실행 화면 2/2장" in html
    assert "role='progressbar'" in html
    assert "증적 파일 전체 목록" in html
    assert "backend/response.json" in html
    assert "서버 응답 내용을 수집하지 못했습니다" in html
    assert "backend_response" not in html
    assert "<pre" not in html
    assert "overflow:auto" not in html


def test_report_html_renders_visual_evidence_and_complete_inventory_without_raw_dump():
    _seed("RUN-report-evidence-16", artifact_count=16)
    service = RunReportService(get_platform_store())
    report = service.generate("RUN-report-evidence-16")

    assert report.evidence.artifactCount == 16
    html = service.download_path(report.runId, "html").read_text(encoding="utf-8")
    assert "증적 파일 16건 인벤토리" in html
    assert html.count("data-inventory-item=") == 16
    assert html.count("data-artifact-id=") == 16
    assert html.count("<pre") == 0
    assert html.count("class='evidence-open'") == 2
    assert "href='data:image" not in html
    assert "id='evidence-viewer'" in html
    # 로봇 + 본문 증적 + 화면 확대 dialog 이미지 자리
    assert html.count("<img") == 3
    for index in range(1, 17):
        assert f"ART-report-{index:02d}" in html
        assert f"details/evidence-{index:02d}.json" in html


def test_report_uses_same_failed_verdict_and_actionable_diagnosis_as_run_history():
    run_id = "RUN-report-invalid-format"
    _seed(run_id)
    store = get_platform_store()
    current = store.get_run(run_id)
    assert current is not None
    store.save_run(
        current.model_copy(
            update={
                "status": "AUTO_FAILED",
                "outcomeKind": "business_error",
                "result": {
                    "verdict": {
                        "verdict": "expected_not_met",
                        "criteriaResults": [
                            {
                                "id": "C-invalid-format",
                                "check": "native_constraint_rejection",
                                "expected": "숫자 형식 외 문자 입력은 업무 요청 전에 거부된다",
                                "result": "not_met",
                                "observed": "브라우저 입력 제약의 거부 상태를 확인하지 못했습니다",
                            }
                        ],
                    }
                },
            }
        )
    )

    service = RunReportService(store)
    report = service.generate(run_id, force=True)

    assert report.execution.technicalStatus == "AUTO_FAILED"
    assert report.diagnosis.outcome == "failure"
    assert report.diagnosis.causeCategory == "client_validation_missing"
    assert "숫자만 입력해야 하는 필드" in report.diagnosis.problemSummary
    assert "type=number" in report.diagnosis.actions[0].action
    html = service.download_path(run_id, "html").read_text(encoding="utf-8")
    assert "기대 결과 불일치" in html
    assert "AI 관측 진단 및 조치 가이드" in html
    assert "숫자만 입력해야 하는 필드" in html


def test_report_renders_execution_policy_block_as_attention_not_product_failure():
    run_id = "RUN-report-policy-attention"
    _seed(run_id)
    store = get_platform_store()
    current = store.get_run(run_id)
    assert current is not None
    store.save_run(
        current.model_copy(
            update={
                "status": "AUTO_FAILED",
                "outcomeKind": "business_error",
                "missingData": ["submit_blocked_destructive"],
                "result": {
                    "missing_data": ["submit_blocked_destructive"],
                    "verdict": {
                        "verdict": "expected_not_met",
                        "criteriaResults": [
                            {
                                "id": "C-response",
                                "check": "request_accepted",
                                "expected": "업무 요청 응답이 관측된다",
                                "result": "undetermined",
                                "observed": "데이터를 만드는 동작이라 자동 실행을 차단했습니다",
                            }
                        ],
                    },
                    "steps": [
                        {
                            "stepId": "S8",
                            "action": "click",
                            "status": "skipped",
                            "observationSummary": "데이터를 생성할 수 있어 자동 클릭을 차단했습니다",
                            "missingData": ["submit_blocked_destructive"],
                        }
                    ],
                },
            }
        )
    )

    service = RunReportService(store)
    report = service.generate(run_id, force=True)

    assert report.execution.technicalStatus == "AUTO_FAILED"
    assert report.diagnosis.outcome == "undetermined"
    assert report.diagnosis.causeCategory == "destructive_policy_blocked"
    assert "송금" not in report.diagnosis.problemSummary
    assert "1회 테스트를 명시적으로 승인" in report.diagnosis.actions[0].action
    html = service.download_path(run_id, "html").read_text(encoding="utf-8")
    assert "담당자 확인 필요" in html
    assert "대상 서비스 오류가 아니라 실행 정책" in html


def test_report_api_get_and_download_contract():
    _seed("RUN-report-api")
    headers = {"X-User-Id": "TEST"}
    generated = client.post("/api/runs/RUN-report-api/report", json={}, headers=headers)
    assert generated.status_code == 200
    assert generated.json()["review"]["hitlRequired"] is True

    loaded = client.get("/api/runs/RUN-report-api/report", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["reportId"] == generated.json()["reportId"]

    html = client.get("/api/runs/RUN-report-api/report/download?format=html", headers=headers)
    assert html.status_code == 200
    assert "text/html" in html.headers["content-type"]
    assert "RUN-report-api-review-report.html" in html.headers["content-disposition"]

    raw = client.get("/api/runs/RUN-report-api/report/download?format=json", headers=headers)
    assert raw.status_code == 200
    assert raw.json()["schemaVersion"] == "run-report/v1"


def test_report_access_requires_run_owner():
    _seed("RUN-report-owner")
    response = client.post(
        "/api/runs/RUN-report-owner/report",
        json={},
        headers={"X-User-Id": "OTHER"},
    )
    assert response.status_code == 403
