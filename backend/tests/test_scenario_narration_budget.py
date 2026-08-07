from __future__ import annotations

import os

from app.core.llm import llm_client
from app.skills.scenario_narrate.script import narrate_and_bind


def _scenarios(count: int) -> list[dict]:
    return [
        {
            "scenarioId": f"SCN-{index:03d}",
            "serviceId": "sample",
            "name": f"샘플 {index}",
            "steps": [{"id": "S1", "action": "navigate", "target": {"route": "/"}}],
        }
        for index in range(count)
    ]


def test_narration_llm_calls_stop_inside_total_budget(monkeypatch) -> None:
    clock = [0.0]

    class SlowUnavailableClient:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def chat_json(self, *, system: str, user: str, timeout_s: float):
            del system, user
            self.timeouts.append(timeout_s)
            clock[0] += timeout_s
            return None

    client = SlowUnavailableClient()
    monkeypatch.setattr(llm_client, "get_llm_client", lambda: client)
    monkeypatch.setattr(narrate_and_bind.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(narrate_and_bind, "NARRATION_LLM_BUDGET_SECONDS", 20.0)
    monkeypatch.setattr(narrate_and_bind, "NARRATION_BATCH_TIMEOUT_SECONDS", 8.0)
    monkeypatch.setattr(narrate_and_bind, "NARRATION_MIN_REMAINING_SECONDS", 3.0)

    result = narrate_and_bind._try_llm(_scenarios(30), None)

    assert result is None
    assert client.timeouts == [8.0, 8.0, 2.0]
    assert clock[0] < 20.0


def test_narration_keeps_partial_model_output_and_fills_rest_deterministically(monkeypatch) -> None:
    clock = [0.0]
    calls = [0]

    class PartiallyAvailableClient:
        def chat_json(self, *, system: str, user: str, timeout_s: float):
            del system, user
            calls[0] += 1
            clock[0] += timeout_s
            if calls[0] == 1:
                return {
                    "scenarios": [
                        {
                            "scenarioId": "SCN-000",
                            "name": "모델이 다듬은 첫 시나리오",
                        }
                    ]
                }
            return None

    monkeypatch.setattr(llm_client, "get_llm_client", lambda: PartiallyAvailableClient())
    monkeypatch.setattr(narrate_and_bind.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(narrate_and_bind, "NARRATION_LLM_BUDGET_SECONDS", 11.0)
    monkeypatch.setattr(narrate_and_bind, "NARRATION_BATCH_TIMEOUT_SECONDS", 8.0)
    monkeypatch.setattr(narrate_and_bind, "NARRATION_MIN_REMAINING_SECONDS", 3.0)

    result = narrate_and_bind._try_llm(_scenarios(8), None)

    assert result is not None
    enriched, mode = result
    assert mode == "llm_partial"
    assert enriched[0]["name"] == "모델이 다듬은 첫 시나리오"
    assert enriched[0]["narrationMode"] == "llm"
    assert enriched[1]["narrationMode"] == "deterministic"
    assert len(enriched) == 8


def test_gpt5_narration_sets_fast_reasoning_and_complete_json_budget(monkeypatch) -> None:
    class UnavailableClient:
        def chat_json(self, *, system: str, user: str, timeout_s: float):
            del system, user, timeout_s
            return None

    monkeypatch.setenv("LLM_MODEL", "gpt-5")
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("LLM_MAX_TOKENS", "2048")
    monkeypatch.setattr(llm_client, "get_llm_client", lambda: UnavailableClient())

    narrate_and_bind._try_llm(_scenarios(1), None)

    assert os.environ["LLM_REASONING_EFFORT"] == "minimal"
    assert os.environ["LLM_MAX_TOKENS"] == "8192"


def test_gpt5_narration_waits_for_one_small_batch_without_exceeding_total_budget(monkeypatch) -> None:
    clock = [0.0]
    timeouts: list[float] = []

    class SlowClient:
        def chat_json(self, *, system: str, user: str, timeout_s: float):
            del system, user
            timeouts.append(timeout_s)
            clock[0] += timeout_s
            return None

    monkeypatch.setenv("LLM_MODEL", "gpt-5")
    monkeypatch.setattr(llm_client, "get_llm_client", lambda: SlowClient())
    monkeypatch.setattr(narrate_and_bind.time, "monotonic", lambda: clock[0])

    narrate_and_bind._try_llm(_scenarios(10), None)

    assert timeouts == [125.0, 13.0]
    assert clock[0] < narrate_and_bind.NARRATION_LLM_BUDGET_SECONDS
