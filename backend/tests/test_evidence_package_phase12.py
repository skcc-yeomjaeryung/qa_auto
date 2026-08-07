from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import ARTIFACTS_EVIDENCE, REPO_ROOT
from app.main import app
from app.schemas.binding_validation import BindingAssertion, BindingValidationResult
from app.schemas.telemetry import BackendTelemetryEvent
from app.services.evidence_package import EvidencePackageService
from app.services.evidence_storage import LocalFilesystemEvidenceStorage
from app.services.input_recommend_models import InputProfileSummary
from app.services.repository_models import ProjectCreate
from app.services.run_models import RunStepSummary, RunSummary
from app.services.scenario_models import ScenarioSummary

client = TestClient(app)
SCHEMA = REPO_ROOT / "packages" / "contracts" / "schemas" / "evidence_manifest.schema.json"


@pytest.fixture(autouse=True)
def fresh_store():
    bootstrap_runtime()
    store = get_platform_store()
    for attr in (
        "_projects",
        "_sets",
        "_files",
        "_commit_cache",
        "_tokens",
        "_analyses",
        "_mapping_sets",
        "_graphs",
        "_scenarios",
        "_contracts",
        "_recommendations",
        "_profiles",
        "_runs",
        "_backend_events",
        "_backend_seq",
        "_binding_results",
        "_evidence_manifests",
    ):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    yield


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_complete(tmp_path: Path, run_id: str = "RUN-p12") -> None:
    store = get_platform_store()
    project = store.create_project(ProjectCreate(name="Evidence", ownerUserId="TEST"))
    scenario = ScenarioSummary(
        scenarioId=f"SCN-{run_id}",
        projectId=project.id,
        version="2",
        status="EXECUTABLE",
        result={
            "scenarioId": f"SCN-{run_id}",
            "sourceRefs": {"commitRefs": {"frontend": "abc123", "backend": "def456"}},
        },
    )
    store.save_scenario(scenario)
    profile = InputProfileSummary(
        profileId=f"IP-{run_id}",
        scenarioId=scenario.scenarioId,
        projectId=project.id,
        version="3",
        status="APPROVED",
        result={"version": "3", "cases": [{"inputs": {"customerId": "C10001"}}]},
    )
    store.save_profile(profile)

    steps: list[RunStepSummary] = []
    screenshots: list[str] = []
    snapshots: list[str] = []
    for idx, stage in enumerate(("source", "input", "destination"), start=1):
        image_path = tmp_path / f"{run_id}-{idx}.png"
        Image.new("RGB", (40, 30), color=(255, 255, 255)).save(image_path)
        snapshot_path = tmp_path / f"{run_id}-{idx}.snapshot.txt"
        snapshot_path.write_text(
            f"screen={stage} customerId=C10001 password=secret",
            encoding="utf-8",
        )
        screenshots.append(str(image_path))
        snapshots.append(str(snapshot_path))
        steps.append(
            RunStepSummary(
                stepId=f"S{idx}",
                action="verify_binding",
                status="ok",
                screenshotPath=str(image_path),
                snapshotPath=str(snapshot_path),
            )
        )
    run = RunSummary(
        runId=run_id,
        scenarioId=scenario.scenarioId,
        projectId=project.id,
        status="WAITING_FOR_REVIEW",
        commitSha="run789",
        inputProfileId=profile.profileId,
        testCaseId=f"TC-{run_id}",
        inputs={"customerId": "C10001", "password": "secret"},
        evidenceDir=str(tmp_path),
        steps=steps,
        result={
            "screenshots": screenshots,
            "snapshots": snapshots,
            "networkRequests": [
                {
                    "method": "POST",
                    "url": "http://target/api/customer",
                    "headers": {"Authorization": "Bearer top-secret"},
                    "request": {"customerId": "C10001", "password": "secret"},
                    "status": 200,
                }
            ],
            "ownerUserId": "TEST",
        },
        createdAt=_now(),
        updatedAt=_now(),
    )
    store.save_run(run)
    store.append_backend_event(
        BackendTelemetryEvent(
            timestamp=_now(),
            event="response_returned",
            testRunId=run_id,
            scenarioId=scenario.scenarioId,
            request={"customerId": "C10001", "password": "***"},
            response={
                "customerId": "C10001",
                "customerName": "합성고객",
                "riskLevel": "HIGH",
                "status": "ACTIVE",
            },
            status=200,
            source="spring",
            maskedFields=["password"],
        )
    )
    store.save_binding_result(
        BindingValidationResult(
            runId=run_id,
            scenarioId=scenario.scenarioId,
            technicalStatus="TECHNICALLY_MATCHED",
            businessReviewRequired=True,
            assertions=[
                BindingAssertion(
                    assertionId="BA-1",
                    field="customerId",
                    source="$.customerId",
                    target="testId:customer-detail-id",
                    expected="C10001",
                    actual="C10001",
                    result="MATCH",
                    evidence={
                        "screenshotPath": screenshots[-1],
                        "region": {"x": 2, "y": 2, "width": 10, "height": 8},
                    },
                )
            ],
            createdAt=_now(),
        )
    )


def _service(tmp_path: Path) -> EvidencePackageService:
    return EvidencePackageService(
        get_platform_store(),
        LocalFilesystemEvidenceStorage(tmp_path / "packages"),
    )


def test_complete_package_manifest_schema_and_required_files(tmp_path):
    _seed_complete(tmp_path)
    manifest = _service(tmp_path).finalize("RUN-p12", retention_days=7)
    assert manifest.integrityStatus == "complete"
    assert manifest.storageStatus == "ready"
    paths = {artifact.path for artifact in manifest.artifacts}
    required = {
        "scenario.json",
        "scenario-version.json",
        "commit-refs.json",
        "input-profile.json",
        "input.json",
        "request.json",
        "response.json",
        "backend-events.jsonl",
        "assertions.json",
        "network/requests.json",
        *{
            f"screenshots/0{i}-{name}.png"
            for i, name in ((1, "source"), (2, "input-completed"), (3, "destination"))
        },
        *{
            f"snapshots/0{i}-{name}.txt"
            for i, name in ((1, "source"), (2, "input-completed"), (3, "destination"))
        },
    }
    assert required.issubset(paths)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        manifest.model_dump(mode="json")
    )


def test_failed_run_produces_partial_package(tmp_path):
    _seed_complete(tmp_path, "RUN-failed")
    store = get_platform_store()
    run = store.get_run("RUN-failed")
    assert run
    store.save_run(
        run.model_copy(
            update={
                "status": "AUTO_FAILED",
                "steps": run.steps[:1],
                "result": {"screenshots": [], "snapshots": [], "ownerUserId": "TEST"},
            }
        )
    )
    manifest = _service(tmp_path).finalize("RUN-failed")
    assert manifest.integrityStatus == "partial"
    assert "run_status:AUTO_FAILED" in manifest.missingData
    assert any(item.startswith("screenshots/") for item in manifest.missingData)


def test_run_resolved_inputs_are_packaged_without_saved_profile(tmp_path):
    _seed_complete(tmp_path, "RUN-inline-input")
    store = get_platform_store()
    run = store.get_run("RUN-inline-input")
    assert run
    store.save_run(
        run.model_copy(
            update={
                "inputProfileId": None,
                "inputProfileVersion": None,
                "inputs": {"amount": "0.01"},
            }
        )
    )

    service = _service(tmp_path)
    manifest = service.finalize("RUN-inline-input")

    assert manifest.integrityStatus == "complete"
    assert "input_profile" not in manifest.missingData
    assert manifest.inputProfile["id"] == "RUN-INPUT-inline-input"
    profile_path = service.storage.package_dir(manifest.evidenceId) / "input-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["cases"][0]["inputs"] == {"amount": "0.01"}
    assert profile["cases"][0]["sources"][0]["type"] == "resolved_run_inputs"


def test_screen_composition_package_treats_input_stage_as_not_applicable(tmp_path):
    _seed_complete(tmp_path, "RUN-composition")
    store = get_platform_store()
    run = store.get_run("RUN-composition")
    scenario = store.get_scenario("SCN-RUN-composition")
    assert run and scenario
    store.save_scenario(
        scenario.model_copy(
            update={
                "result": {
                    "scenarioId": scenario.scenarioId,
                    "sourceRefs": {
                        "commitRefs": {"frontend": "abc123", "backend": "def456"}
                    },
                    "steps": [
                        {"stepId": "S1", "action": "navigate"},
                        {"stepId": "S2", "action": "assert_visible"},
                    ],
                }
            }
        )
    )
    store.save_run(
        run.model_copy(
            update={
                "inputs": {},
                "steps": run.steps[:2],
                "result": {
                    **run.result,
                    "screenshots": (run.result.get("screenshots") or [])[:2],
                    "snapshots": (run.result.get("snapshots") or [])[:2],
                },
            }
        )
    )

    manifest = _service(tmp_path).finalize("RUN-composition")

    paths = {artifact.path for artifact in manifest.artifacts}
    assert manifest.integrityStatus == "complete"
    assert "screenshots/01-source.png" in paths
    assert "screenshots/03-destination.png" in paths
    assert "snapshots/01-source.txt" in paths
    assert "snapshots/03-destination.txt" in paths
    assert "screenshots/02-input-completed.png" not in paths
    assert "snapshots/02-input-completed.txt" not in paths


def test_hash_verification_and_corruption_detection(tmp_path):
    _seed_complete(tmp_path)
    service = _service(tmp_path)
    manifest = service.finalize("RUN-p12")
    report = service.verify(manifest.evidenceId)
    assert report.integrityStatus == "complete"
    assert report.verified == len(manifest.artifacts)
    first = manifest.artifacts[0]
    target = service.storage.package_dir(manifest.evidenceId) / first.path
    target.write_bytes(target.read_bytes() + b"tampered")
    corrupted = service.verify(manifest.evidenceId)
    assert corrupted.integrityStatus == "corrupted"
    assert first.artifactId in corrupted.corruptedArtifacts


def test_screenshot_and_network_masking(tmp_path):
    _seed_complete(tmp_path)
    service = _service(tmp_path)
    manifest = service.finalize("RUN-p12")
    shot = next(item for item in manifest.artifacts if item.path == "screenshots/03-destination.png")
    assert shot.masked is True
    with Image.open(service.storage.package_dir(manifest.evidenceId) / shot.path) as image:
        assert image.convert("RGB").getpixel((4, 4)) == (0, 0, 0)
    network = service.storage.package_dir(manifest.evidenceId) / "network/requests.json"
    body = json.loads(network.read_text(encoding="utf-8"))
    headers = body["requests"][0]["headers"]
    assert headers["Authorization"] == "***"
    assert body["requests"][0]["request"]["password"] == "***"
    snapshot = service.storage.package_dir(manifest.evidenceId) / "snapshots/03-destination.txt"
    text = snapshot.read_text(encoding="utf-8")
    assert "C10001" not in text and "secret" not in text


def test_local_filesystem_path_jail(tmp_path):
    storage = LocalFilesystemEvidenceStorage(tmp_path / "packages")
    storage.reset_package("EVID-ok")
    with pytest.raises(ValueError):
        storage.write_bytes("EVID-ok", "../escape.txt", b"x")
    with pytest.raises(ValueError):
        storage.package_dir("../bad")


def test_zip_export_contains_manifest_and_artifacts(tmp_path):
    _seed_complete(tmp_path)
    service = _service(tmp_path)
    manifest = service.finalize("RUN-p12")
    payload = service.zip_bytes(manifest.evidenceId)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "scenario.json" in names
        assert "screenshots/03-destination.png" in names


def test_retention_deletes_expired_package(tmp_path):
    _seed_complete(tmp_path)
    service = _service(tmp_path)
    manifest = service.finalize("RUN-p12")
    expired = manifest.model_copy(
        update={
            "retentionUntil": (
                datetime.now(timezone.utc) - timedelta(days=1)
            ).isoformat()
        }
    )
    get_platform_store().save_evidence_manifest(expired)
    deleted = service.cleanup_expired()
    assert manifest.evidenceId in deleted
    assert not service.storage.package_dir(manifest.evidenceId).exists()


def test_storage_failure_does_not_replace_run_status(tmp_path):
    _seed_complete(tmp_path)

    class FailingStorage(LocalFilesystemEvidenceStorage):
        def reset_package(self, evidence_id: str) -> Path:
            raise OSError("disk full")

    service = EvidencePackageService(
        get_platform_store(),
        FailingStorage(tmp_path / "failed"),
    )
    manifest = service.finalize("RUN-p12")
    assert manifest.storageStatus == "write_failed"
    assert get_platform_store().get_run("RUN-p12").status == "WAITING_FOR_REVIEW"


def test_authorized_api_finalize_download_and_unauthorized_denial(tmp_path):
    run_id = "RUN-api-p12"
    _seed_complete(tmp_path, run_id)
    headers = {"X-User-Id": "TEST"}
    preview_response = client.get(f"/api/runs/{run_id}/evidence", headers=headers)
    assert preview_response.status_code == 200
    preview = preview_response.json()["packagePreview"]
    assert [stage["id"] for stage in preview["stages"]] == ["source", "backend", "destination"]
    assert preview["rawEvidence"]["screenshots"] >= 3
    assert preview["integrity"]["status"] == "not_finalized"
    raw_download = client.get(f"/api/runs/{run_id}/evidence/download", headers=headers)
    assert raw_download.status_code == 200
    with zipfile.ZipFile(BytesIO(raw_download.content)) as archive:
        assert any(name.endswith(".png") for name in archive.namelist())
    assert client.get(f"/api/runs/{run_id}/evidence/download").status_code == 403
    finalized = client.post(
        f"/api/runs/{run_id}/evidence/finalize",
        headers=headers,
        json={"retentionDays": 3},
    )
    assert finalized.status_code == 200
    evidence_id = finalized.json()["evidenceId"]
    manifest_response = client.get(
        f"/api/evidence/{evidence_id}/manifest",
        headers=headers,
    )
    assert manifest_response.status_code == 200
    artifact_id = manifest_response.json()["artifacts"][0]["artifactId"]
    artifact_response = client.get(
        f"/api/evidence/{evidence_id}/artifacts/{artifact_id}",
        headers=headers,
    )
    assert artifact_response.status_code == 200
    denied = client.get(f"/api/evidence/{evidence_id}/download")
    assert denied.status_code == 403
    wrong = client.get(
        f"/api/evidence/{evidence_id}/download",
        headers={"X-User-Id": "OTHER"},
    )
    assert wrong.status_code == 403
    downloaded = client.get(
        f"/api/evidence/{evidence_id}/download",
        headers=headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(downloaded.content)) as archive:
        assert "manifest.json" in archive.namelist()
    # clean API package under repository artifacts
    package = ARTIFACTS_EVIDENCE / "packages" / evidence_id
    if package.exists():
        import shutil

        shutil.rmtree(package)
