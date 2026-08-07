from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_REPORTS, RUN_REPORT_SCHEMA
from app.schemas.run_report import RunReport
from app.services.binding_validation import BindingValidationService
from app.services.evidence_package import EvidencePackageService
from app.services.repository_store import InMemoryPlatformStore
from app.skills.run_report.script.generate_report import write_artifacts


SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class RunReportService:
    """Build and persist HITL reports from canonical execution sources only."""

    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def _paths(self, run_id: str) -> tuple[Path, Path]:
        if not SAFE_RUN_ID.fullmatch(run_id):
            raise ValueError("invalid run id")
        root = ARTIFACTS_REPORTS / "runs" / run_id
        return root / "report.json", root / "report.html"

    def get(self, run_id: str) -> RunReport | None:
        artifact_path, _ = self._paths(run_id)
        if not artifact_path.is_file():
            return None
        try:
            return RunReport.model_validate_json(artifact_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def generate(self, run_id: str, *, force: bool = False) -> RunReport:
        existing = self.get(run_id)
        if existing is not None and not force:
            return existing

        run = self.store.get_run(run_id)
        if not run:
            raise LookupError(f"run not found: {run_id}")
        scenario = self.store.get_scenario(run.scenarioId)
        if not scenario:
            raise LookupError(f"scenario not found: {run.scenarioId}")
        project = self.store.get_project(run.projectId) if run.projectId else None

        binding = self.store.get_binding_result(run_id)
        if binding is None:
            binding = BindingValidationService(self.store).validate(run_id)
        manifest = self.store.get_evidence_manifest_by_run(run_id)
        if manifest is None:
            manifest = EvidencePackageService(self.store).finalize(run_id)

        artifact_path, html_path = self._paths(run_id)
        report_id = f"RPT-{run_id.removeprefix('RUN-')}"
        source = {
            "reportId": report_id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "durationMs": self._duration_ms(run.createdAt, run.updatedAt),
            "run": run.model_dump(mode="json"),
            "project": (
                project.model_dump(mode="json")
                if project
                else {"id": run.projectId or "missing_data", "name": "missing_data"}
            ),
            "scenario": scenario.model_dump(mode="json"),
            "binding": binding.model_dump(mode="json"),
            "evidence": manifest.model_dump(mode="json"),
        }
        response = PlatformRunnerAdapter().execute(
            "wf_run_report",
            {
                "projectId": run.projectId,
                "runId": run_id,
                "scenarioId": run.scenarioId,
                "reportSource": source,
                "artifactPath": str(artifact_path.resolve()),
                "htmlPath": str(html_path.resolve()),
            },
        )
        if response.status != "complete" or not response.stepResults:
            raise RuntimeError("REPORT AGENT workflow did not complete")
        output = response.stepResults[0].get("output") or {}
        raw_report = output.get("result")
        if not isinstance(raw_report, dict):
            raise RuntimeError("REPORT AGENT produced no structured result")
        raw_report["generatedBy"] = {
            **dict(raw_report.get("generatedBy") or {}),
            "traceId": response.plan.planId,
        }
        report = RunReport.model_validate(raw_report)
        report_body = report.model_dump(mode="json", by_alias=True)
        schema = json.loads(RUN_REPORT_SCHEMA.read_text(encoding="utf-8"))
        jsonschema.validate(report_body, schema)
        write_artifacts(report_body, artifact_path, html_path)
        return report

    def download_path(self, run_id: str, output_format: str) -> Path:
        artifact_path, html_path = self._paths(run_id)
        target = html_path if output_format == "html" else artifact_path
        if not target.is_file():
            raise LookupError(f"report not found: {run_id}")
        return target

    @staticmethod
    def _duration_ms(started_at: str | None, ended_at: str | None) -> int | None:
        if not started_at or not ended_at:
            return None
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            ended = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0, int((ended - started).total_seconds() * 1000))
