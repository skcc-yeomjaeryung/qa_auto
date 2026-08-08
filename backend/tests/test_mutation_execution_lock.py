from __future__ import annotations

from contextlib import nullcontext

from app.services.run_models import RunSummary
from app.services.run_service import (
    _contains_destructive_action,
    _mutation_execution_context,
)


def _run(*, environment_id: str = "ENV-demo", account_id: str | None = None) -> RunSummary:
    return RunSummary(
        runId="RUN-lock",
        scenarioId="SCN-lock",
        status="RUNNING",
        environmentId=environment_id,
        executionAccountId=account_id,
    )


def test_destructive_detection_uses_scenario_step_metadata() -> None:
    assert _contains_destructive_action({"steps": [{"action": "click", "destructive": True}]})
    assert not _contains_destructive_action({"steps": [{"action": "assert_visible"}]})


def test_same_environment_and_account_share_mutation_lock() -> None:
    scenario = {"steps": [{"action": "click", "destructive": True}]}
    first = _mutation_execution_context(_run(), scenario, True)
    second = _mutation_execution_context(_run(), scenario, True)

    assert first is second


def test_read_only_or_disallowed_execution_does_not_take_mutation_lock() -> None:
    read_only = _mutation_execution_context(
        _run(), {"steps": [{"action": "assert_visible"}]}, True
    )
    blocked = _mutation_execution_context(
        _run(), {"steps": [{"action": "click", "destructive": True}]}, False
    )

    assert isinstance(read_only, nullcontext)
    assert isinstance(blocked, nullcontext)
