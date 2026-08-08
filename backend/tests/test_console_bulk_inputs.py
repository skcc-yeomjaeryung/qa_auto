from __future__ import annotations

from unittest.mock import MagicMock

from app.services.console_models import BulkRunRequest
from app.services.console_service import ConsoleService
from app.services.run_models import RunSummary


def _service() -> ConsoleService:
    service = ConsoleService.__new__(ConsoleService)
    service.store = MagicMock()
    service.input_recommend = MagicMock()
    service.runs = MagicMock()
    service.runs.start_run.return_value = RunSummary(
        runId="RUN-bulk-input",
        scenarioId="SCN-deposit",
        status="WAITING_FOR_REVIEW",
        progressPercent=100,
        outcomeKind="success",
        observationSummary="expected result observed",
    )
    return service


def test_bulk_run_prepares_scenario_specific_defaults_when_shared_inputs_are_empty() -> None:
    service = _service()
    service.store.get_recommendation_by_scenario.return_value = None

    result = service.bulk_run(
        BulkRunRequest(scenarioIds=["SCN-deposit"], environmentId="ENV-demo")
    )

    service.input_recommend.recommend.assert_called_once_with("SCN-deposit")
    run_payload = service.runs.start_run.call_args.args[1]
    assert run_payload.inputs == {}
    assert result.status == "complete"


def test_bulk_run_preserves_explicit_shared_override_without_recommendation() -> None:
    service = _service()

    service.bulk_run(
        BulkRunRequest(
            scenarioIds=["SCN-deposit"],
            environmentId="ENV-demo",
            inputs={"amount": "1000"},
        )
    )

    service.store.get_recommendation_by_scenario.assert_not_called()
    service.input_recommend.recommend.assert_not_called()
    run_payload = service.runs.start_run.call_args.args[1]
    assert run_payload.inputs == {"amount": "1000"}
