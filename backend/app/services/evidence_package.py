from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.schemas.evidence import (
    EvidenceArtifact,
    EvidenceIntegrityReport,
    EvidenceManifest,
)
from app.services.evidence_storage import (
    EvidenceStorageAdapter,
    LocalFilesystemEvidenceStorage,
)
from app.services.repository_store import InMemoryPlatformStore
from app.services.telemetry.masking import mask_payload
from app.utils.config import get_settings


SCREENSHOT_NAMES = (
    "screenshots/01-source.png",
    "screenshots/02-input-completed.png",
    "screenshots/03-destination.png",
)
SNAPSHOT_NAMES = (
    "snapshots/01-source.txt",
    "snapshots/02-input-completed.txt",
    "snapshots/03-destination.txt",
)


class EvidencePackageService:
    def __init__(
        self,
        store: InMemoryPlatformStore,
        storage: EvidenceStorageAdapter | None = None,
    ) -> None:
        self.store = store
        self.storage = storage or LocalFilesystemEvidenceStorage()

    def finalize(self, run_id: str, *, retention_days: int | None = None) -> EvidenceManifest:
        run = self.store.get_run(run_id)
        if not run:
            raise LookupError(f"run not found: {run_id}")
        scenario = self.store.get_scenario(run.scenarioId)
        binding = self.store.get_binding_result(run_id)
        project = self.store.get_project(run.projectId) if run.projectId else None
        owner = project.ownerUserId if project else str((run.result or {}).get("ownerUserId") or "TEST")
        evidence_id = f"EVID-{run_id}"
        created = datetime.now(timezone.utc)
        retention = retention_days or get_settings().evidence_retention_days
        retention_until = created + timedelta(days=retention)
        missing: list[str] = []
        artifacts: list[EvidenceArtifact] = []

        try:
            self.storage.reset_package(evidence_id)
            events = list(self.store.list_backend_events(run_id))
            request_event = next((event for event in reversed(events) if event.request), None)
            response_event = next(
                (
                    event
                    for event in reversed(events)
                    if event.event == "response_returned" and event.response is not None
                ),
                None,
            )
            scenario_body = scenario.result if scenario else {"missing_data": "scenario"}
            expects_backend = any(
                str(step.get("action") or "") in {"wait_for_response", "verify_response"}
                for step in ((scenario_body.get("steps") or []) if isinstance(scenario_body, dict) else [])
                if isinstance(step, dict)
            )
            scenario_steps = (
                (scenario_body.get("steps") or [])
                if isinstance(scenario_body, dict)
                else []
            )
            has_scenario_input = bool(run.inputs) or any(
                str(step.get("action") or "")
                in {"fill", "type", "select", "check", "uncheck", "submit"}
                for step in scenario_steps
                if isinstance(step, dict)
            )
            self._write_json(
                evidence_id,
                "scenario.json",
                scenario_body,
                artifacts,
                "scenario",
            )
            self._write_json(
                evidence_id,
                "scenario-version.json",
                {
                    "scenarioId": run.scenarioId,
                    "version": scenario.version if scenario else "missing_data",
                },
                artifacts,
                "scenario",
            )
            commit_refs = dict(
                ((scenario_body.get("sourceRefs") or {}).get("commitRefs") or {})
                if isinstance(scenario_body, dict)
                else {}
            )
            if run.commitSha:
                commit_refs.setdefault("runRepository", run.commitSha)
            self._write_json(
                evidence_id,
                "commit-refs.json",
                commit_refs or {"missing_data": "commit_refs"},
                artifacts,
                "source",
            )
            if not commit_refs:
                missing.append("commit_refs")

            profile = self.store.get_profile(run.inputProfileId) if run.inputProfileId else None
            effective_inputs = dict(run.inputs or {})
            for binding_row in ((run.result or {}).get("inputBindings") or []):
                if not isinstance(binding_row, dict):
                    continue
                value = binding_row.get("value")
                field = str(binding_row.get("field") or "").strip()
                if (
                    binding_row.get("filled")
                    and binding_row.get("source") == "input_profile"
                    and field
                    and value not in (None, "", "***")
                ):
                    effective_inputs.setdefault(field, value)
            effective_profile_id = (
                profile.profileId
                if profile
                else f"RUN-INPUT-{run_id.removeprefix('RUN-')}"
                if effective_inputs
                else "missing_data"
            )
            profile_body = (
                profile.result
                if profile and profile.result
                else {
                    "schemaVersion": "input-profile/v1",
                    "profileId": effective_profile_id,
                    "scenarioId": run.scenarioId,
                    "serviceId": run.serviceId or "multi",
                    "projectId": run.projectId,
                    "name": "실행 시 확정 입력",
                    "version": run.inputProfileVersion or "1",
                    "status": "DRAFT",
                    "policy": {
                        "budget": 1,
                        "unresolvedPolicy": "reviewRequired",
                        "excludeDestructive": "submit_blocked_destructive"
                        in set(run.missingData or []),
                        "seed": 0,
                    },
                    "cases": [
                        {
                            "caseId": f"CASE-{run_id.removeprefix('RUN-')}",
                            "category": "runtime",
                            "inputs": mask_payload(effective_inputs),
                            "sources": [{"type": "resolved_run_inputs", "runId": run_id}],
                        }
                    ],
                    "categoryCounts": {"runtime": 1},
                    "createdAt": run.createdAt or created.isoformat(),
                }
                if effective_inputs
                else {"id": "missing_data", "version": "missing_data"}
            )
            self._write_json(
                evidence_id,
                "input-profile.json",
                profile_body,
                artifacts,
                "input",
                masked=True,
            )
            if not profile and not effective_inputs:
                missing.append("input_profile")
            self._write_json(
                evidence_id,
                "input.json",
                mask_payload(run.inputs),
                artifacts,
                "input",
                masked=True,
            )
            self._write_json(
                evidence_id,
                "request.json",
                mask_payload(request_event.request if request_event else {}),
                artifacts,
                "backend",
                masked=True,
            )
            self._write_json(
                evidence_id,
                "response.json",
                mask_payload(response_event.response if response_event else {}),
                artifacts,
                "backend",
                masked=True,
            )
            if expects_backend and not request_event:
                missing.append("backend_request")
            if expects_backend and not response_event:
                missing.append("backend_response")

            event_lines = "\n".join(event.model_dump_json() for event in events)
            if event_lines:
                event_lines += "\n"
            self._write_bytes(
                evidence_id,
                "backend-events.jsonl",
                event_lines.encode("utf-8"),
                artifacts,
                "backend",
                masked=True,
            )
            if expects_backend and not events:
                missing.append("backend_events")

            assertions = (
                binding.model_dump(mode="json")
                if binding
                else {"runId": run_id, "missing_data": ["binding_validation"]}
            )
            self._write_json(
                evidence_id,
                "assertions.json",
                assertions,
                artifacts,
                "binding",
                masked=True,
            )
            if not binding:
                missing.append("binding_validation")

            regions = self._mask_regions(binding)
            screenshot_sources = self._stage_file_sources(
                run,
                "screenshotPath",
                "screenshots",
                has_scenario_input=has_scenario_input,
            )
            for idx, relative in enumerate(SCREENSHOT_NAMES):
                source = screenshot_sources.get(idx)
                if source is None:
                    if idx != 1 or has_scenario_input:
                        missing.append(relative)
                    continue
                target, masked = self._mask_screenshot(
                    evidence_id,
                    relative,
                    source,
                    regions,
                )
                artifacts.append(
                    self._artifact(target, relative, "screenshot", masked, self._stage(idx))
                )

            snapshot_sources = self._stage_file_sources(
                run,
                "snapshotPath",
                "snapshots",
                has_scenario_input=has_scenario_input,
            )
            redactions = self._redaction_values(run, events)
            for idx, relative in enumerate(SNAPSHOT_NAMES):
                source = snapshot_sources.get(idx)
                if source is None:
                    if idx != 1 or has_scenario_input:
                        missing.append(relative)
                    continue
                text = source.read_text(encoding="utf-8", errors="replace")
                for value in redactions:
                    text = text.replace(value, "***")
                self._write_bytes(
                    evidence_id,
                    relative,
                    text.encode("utf-8"),
                    artifacts,
                    "snapshot",
                    masked=True,
                    stage=self._stage(idx),
                )

            network = list((run.result or {}).get("networkRequests") or [])
            network_body = {
                "requests": mask_payload(network),
                "sanitized": True,
                "source": "agent-browser",
            }
            self._write_json(
                evidence_id,
                "network/requests.json",
                network_body,
                artifacts,
                "network",
                masked=True,
            )
            if not network:
                missing.append("network_requests")

            if run.status in {"AUTO_FAILED", "CANCELLED"}:
                missing.append(f"run_status:{run.status}")
            # integrityStatus는 파일의 존재·해시·저장 성공 여부만 나타낸다.
            # 업무 관측의 부족은 missingData/technicalStatus로 별도 전달한다.
            expected_file_missing = any(
                item.startswith(("screenshots/", "snapshots/")) for item in missing
            )
            integrity = "partial" if expected_file_missing else "complete"
            manifest = EvidenceManifest(
                evidenceId=evidence_id,
                runId=run_id,
                projectId=run.projectId,
                ownerUserId=owner,
                scenario={
                    "id": run.scenarioId,
                    "version": scenario.version if scenario else "missing_data",
                },
                commitRefs={str(k): str(v) for k, v in commit_refs.items()},
                inputProfile={
                    "id": effective_profile_id,
                    "version": str(
                        (profile.result or {}).get("version", "1")
                        if profile
                        else run.inputProfileVersion or "1"
                        if effective_inputs
                        else "missing_data"
                    ),
                },
                technicalStatus=(
                    binding.technicalStatus
                    if binding
                    else ("PARTIAL" if missing else run.status)
                ),
                correlation={
                    "testRunId": run_id,
                    "scenarioId": run.scenarioId,
                    "testCaseId": run.testCaseId or "missing_data",
                    "inputProfileId": effective_profile_id,
                },
                artifacts=artifacts,
                integrityStatus=integrity,
                missingData=list(dict.fromkeys(missing)),
                retentionUntil=retention_until.isoformat(),
                createdAt=created.isoformat(),
            )
            self._write_manifest(manifest)
            self.store.save_evidence_manifest(manifest)
            return manifest
        except Exception:
            # Storage status is independent from test outcome.
            manifest = EvidenceManifest(
                evidenceId=evidence_id,
                runId=run_id,
                projectId=run.projectId,
                ownerUserId=owner,
                scenario={"id": run.scenarioId, "version": "missing_data"},
                inputProfile={"id": run.inputProfileId or "missing_data", "version": "missing_data"},
                technicalStatus="PARTIAL",
                integrityStatus="partial",
                storageStatus="write_failed",
                missingData=["evidence_storage_failed"],
                retentionUntil=retention_until.isoformat(),
                createdAt=created.isoformat(),
            )
            self.store.save_evidence_manifest(manifest)
            return manifest

    def get_manifest(self, evidence_id: str, *, verify: bool = True) -> EvidenceManifest | None:
        manifest = self.store.get_evidence_manifest(evidence_id)
        if not manifest:
            path = self.storage.package_dir(evidence_id) / "manifest.json"
            if not path.is_file():
                return None
            manifest = EvidenceManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if verify:
            report = self.verify(evidence_id, manifest)
            if report.integrityStatus == "corrupted":
                manifest = manifest.model_copy(update={"integrityStatus": "corrupted"})
        return manifest

    def verify(
        self,
        evidence_id: str,
        manifest: EvidenceManifest | None = None,
    ) -> EvidenceIntegrityReport:
        manifest = manifest or self.get_manifest(evidence_id, verify=False)
        if not manifest:
            raise LookupError(f"evidence not found: {evidence_id}")
        package = self.storage.package_dir(evidence_id)
        corrupted: list[str] = []
        missing: list[str] = []
        verified = 0
        for artifact in manifest.artifacts:
            target = (package / artifact.path).resolve()
            try:
                target.relative_to(package)
            except ValueError:
                corrupted.append(artifact.artifactId)
                continue
            if not target.is_file():
                missing.append(artifact.artifactId)
                continue
            if self._sha256(target) != artifact.sha256 or target.stat().st_size != artifact.size:
                corrupted.append(artifact.artifactId)
            else:
                verified += 1
        status = (
            "corrupted"
            if corrupted or missing
            else manifest.integrityStatus
        )
        return EvidenceIntegrityReport(
            evidenceId=evidence_id,
            integrityStatus=status,
            verified=verified,
            corruptedArtifacts=corrupted,
            missingArtifacts=missing,
        )

    def zip_bytes(self, evidence_id: str) -> bytes:
        manifest = self.get_manifest(evidence_id)
        if not manifest:
            raise LookupError(f"evidence not found: {evidence_id}")
        package = self.storage.package_dir(evidence_id)
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(package)))
        return output.getvalue()

    def artifact_path(self, evidence_id: str, artifact_id: str) -> Path:
        manifest = self.get_manifest(evidence_id)
        if not manifest:
            raise LookupError(f"evidence not found: {evidence_id}")
        artifact = next(
            (item for item in manifest.artifacts if item.artifactId == artifact_id),
            None,
        )
        if not artifact:
            raise LookupError(f"artifact not found: {artifact_id}")
        package = self.storage.package_dir(evidence_id)
        target = (package / artifact.path).resolve()
        try:
            target.relative_to(package)
        except ValueError as exc:
            raise ValueError("artifact outside package") from exc
        if not target.is_file():
            raise LookupError(f"artifact file missing: {artifact_id}")
        return target

    def cleanup_expired(self, *, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(timezone.utc)
        deleted: list[str] = []
        for manifest in list(self.store.list_evidence_manifests()):
            try:
                expires = datetime.fromisoformat(manifest.retentionUntil)
            except ValueError:
                continue
            if expires <= now:
                self.storage.delete_package(manifest.evidenceId)
                self.store.delete_evidence_manifest(manifest.evidenceId)
                deleted.append(manifest.evidenceId)
        return deleted

    def _write_manifest(self, manifest: EvidenceManifest) -> None:
        self.storage.write_bytes(
            manifest.evidenceId,
            "manifest.json",
            manifest.model_dump_json(indent=2).encode("utf-8"),
        )

    def _write_json(
        self,
        evidence_id: str,
        relative: str,
        value: Any,
        artifacts: list[EvidenceArtifact],
        artifact_type: str,
        *,
        masked: bool = False,
        stage: str | None = None,
    ) -> None:
        data = json.dumps(value, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self._write_bytes(
            evidence_id,
            relative,
            data,
            artifacts,
            artifact_type,
            masked=masked,
            stage=stage,
        )

    def _write_bytes(
        self,
        evidence_id: str,
        relative: str,
        data: bytes,
        artifacts: list[EvidenceArtifact],
        artifact_type: str,
        *,
        masked: bool = False,
        stage: str | None = None,
    ) -> None:
        target = self.storage.write_bytes(evidence_id, relative, data)
        artifacts.append(self._artifact(target, relative, artifact_type, masked, stage))

    def _mask_screenshot(
        self,
        evidence_id: str,
        relative: str,
        source: Path,
        regions: list[dict[str, int]],
    ) -> tuple[Path, bool]:
        target = self.storage.package_dir(evidence_id) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(source) as image:
                rendered = image.convert("RGB")
                draw = ImageDraw.Draw(rendered)
                for region in regions:
                    x = max(0, int(region.get("x", 0)))
                    y = max(0, int(region.get("y", 0)))
                    width = max(0, int(region.get("width", 0)))
                    height = max(0, int(region.get("height", 0)))
                    if width and height:
                        draw.rectangle((x, y, x + width, y + height), fill="black")
                rendered.save(target, format="PNG")
            return target, True
        except Exception:
            shutil.copy2(source, target)
            return target, False

    @staticmethod
    def _mask_regions(binding: Any) -> list[dict[str, int]]:
        regions: list[dict[str, int]] = []
        if not binding:
            return regions
        for assertion in binding.assertions:
            region = (assertion.evidence or {}).get("region")
            if isinstance(region, dict):
                try:
                    regions.append(
                        {
                            "x": int(region.get("x", 0)),
                            "y": int(region.get("y", 0)),
                            "width": int(region.get("width", 0)),
                            "height": int(region.get("height", 0)),
                        }
                    )
                except (TypeError, ValueError):
                    continue
        return regions

    @staticmethod
    def _file_sources(run: Any, step_attr: str, result_key: str) -> list[Path]:
        values: list[Path] = []
        seen: set[str] = set()
        for step in run.steps or []:
            raw = getattr(step, step_attr, None)
            if raw:
                path = Path(raw)
                if path.is_file() and str(path.resolve()) not in seen:
                    seen.add(str(path.resolve()))
                    values.append(path)
        for raw in (run.result or {}).get(result_key) or []:
            path = Path(str(raw))
            if path.is_file() and str(path.resolve()) not in seen:
                seen.add(str(path.resolve()))
                values.append(path)
        return values

    @classmethod
    def _stage_file_sources(
        cls,
        run: Any,
        step_attr: str,
        result_key: str,
        *,
        has_scenario_input: bool,
    ) -> dict[int, Path]:
        """Map real artifacts to source/input/destination without inventing a stage.

        A screen-composition scenario has no business input stage. In that case the
        first observation is the source and the final observation is the destination;
        the input-completed slot is explicitly not applicable. A scenario that does
        accept input keeps the strict three-stage evidence requirement.
        """
        values = cls._file_sources(run, step_attr, result_key)
        if has_scenario_input:
            return {index: value for index, value in enumerate(values[:3])}
        if not values:
            return {}
        return {0: values[0], 2: values[-1]}

    @staticmethod
    def _redaction_values(run: Any, events: list[Any]) -> list[str]:
        values = {
            str(value)
            for value in (run.inputs or {}).values()
            if value not in (None, "") and len(str(value)) >= 3
        }
        for event in events:
            for body in (event.request or {}, event.response or {}):
                for key, value in body.items():
                    lowered = str(key).casefold()
                    if any(part in lowered for part in ("password", "token", "secret", "customerid")):
                        if value not in (None, "", "***"):
                            values.add(str(value))
        return sorted(values, key=len, reverse=True)

    @staticmethod
    def _artifact(
        path: Path,
        relative: str,
        artifact_type: str,
        masked: bool,
        stage: str | None,
    ) -> EvidenceArtifact:
        created = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return EvidenceArtifact(
            artifactId=f"ART-{hashlib.sha1(relative.encode()).hexdigest()[:12]}",
            type=artifact_type,
            path=relative,
            mimeType=mime,
            size=path.stat().st_size,
            sha256=EvidencePackageService._sha256(path),
            createdAt=created,
            masked=masked,
            stage=stage,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _stage(index: int) -> str:
        return ("source", "input_completed", "destination")[min(index, 2)]
