from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.core.catalog import AgentRegistry
from app.core.context import ContextStore
from app.core.models import (
    ModelProfileCreate,
    ModelRegistry,
    ModelRequirement,
    ModelSelector,
    resolve_project_model_binding,
)
from app.core.models.secret_store import MemoryModelSecretStore
from app.core.observability import AgentEventStore
from app.core.prompts import PromptCatalog
from app.core.skill_registry import SkillRegistry
from app.core.tool_runtime import ToolRuntime
from app.core.workflow_registry import WorkflowRegistry
from app.core.capability_registry import CapabilityRegistry
from app.core.cross_validator import cross_validate
from app.core.planning import Planner
from app.core.execution.orchestrator import _step_audit_details
from app.core.llm.llm_client import LlmClient
from app.utils.config import get_settings


def _isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "seed-model")
    monkeypatch.setenv("LLM_API_KEY", "seed-secret")
    get_settings.cache_clear()


def test_model_registry_separates_secret_and_health_checks(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    registry = ModelRegistry()
    item = registry.create(
        ModelProfileCreate(
            displayName="Internal Qwen",
            endpoint="http://llm.internal:11434",
            modelId="qwen3.6:32b",
            apiKey="never-expose",
            capabilities=["chat", "code"],
        )
    )
    assert item.hasApiKey is True
    assert "apiKey" not in item.model_dump()
    assert registry.secret(item.id) == "never-expose"

    def fake_get(_self, url, headers=None):
        assert url == "http://llm.internal:11434/v1/models"
        assert headers == {"Authorization": "Bearer never-expose"}
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": [{"id": "qwen3.6:32b"}]},
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    checked = registry.health_check(item.id)
    assert checked.healthStatus == "up"
    assert checked.discoveredModels == ["qwen3.6:32b"]
    persisted = (tmp_path / "data" / "platform_store.sqlite3").read_bytes()
    assert b"never-expose" not in persisted
    public_blob = json.dumps(checked.model_dump(mode="json"))
    assert "never-expose" not in public_blob


def test_model_registry_restores_secret_after_process_restart(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    secret_store = MemoryModelSecretStore()
    first = ModelRegistry(secret_store=secret_store)
    item = first.create(
        ModelProfileCreate(
            displayName="Persistent external model",
            endpoint="https://api.example.com",
            modelId="external-model",
            deploymentType="external",
            apiKey="keychain-only-secret",
            capabilities=["chat"],
        )
    )

    restarted = ModelRegistry(secret_store=secret_store)
    restored = restarted.require(item.id)

    assert restored.hasApiKey is True
    assert restarted.secret(item.id) == "keychain-only-secret"
    persisted = (tmp_path / "data" / "platform_store.sqlite3").read_bytes()
    assert b"keychain-only-secret" not in persisted


def test_model_selector_applies_hard_filters_and_policy(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    registry = ModelRegistry()
    for item in list(registry.list()):
        registry.delete(item.id)
    cheap = registry.create(
        ModelProfileCreate(
            displayName="sLLM",
            endpoint="http://small.internal:8000",
            modelId="small",
            capabilities=["chat", "code"],
            contextWindow=32768,
            qualityScore=55,
            costScore=100,
            speedScore=95,
            reliabilityScore=80,
        )
    )
    quality = registry.create(
        ModelProfileCreate(
            displayName="Large",
            endpoint="https://external.example.com",
            modelId="large",
            deploymentType="external",
            apiKey="test-only-memory-key",
            capabilities=["chat", "code"],
            contextWindow=131072,
            qualityScore=100,
            costScore=10,
            speedScore=40,
            reliabilityScore=95,
        )
    )
    requirement = ModelRequirement(
        capabilities=["chat", "code"],
        minimumContext=16000,
        structuredOutput=True,
        qualityProfile="scenario_generation",
    )
    selector = ModelSelector(registry)
    assert selector.select(requirement, "cost_saver").selectedModelProfileId == cheap.id
    assert selector.select(requirement, "highest_quality").selectedModelProfileId == quality.id
    internal = selector.select(requirement, "internal_only")
    assert internal.selectedModelProfileId == cheap.id
    external_eval = next(row for row in internal.candidates if row.modelProfileId == quality.id)
    assert external_eval.eligible is False
    assert any("internal_only" in reason for reason in external_eval.reasons)


def test_model_selector_honors_project_fixed_role_and_blocks_unloaded_external_secret(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    registry = ModelRegistry()
    for item in list(registry.list()):
        registry.delete(item.id)
    internal = registry.create(
        ModelProfileCreate(
            displayName="Internal",
            endpoint="http://internal.example:8000",
            modelId="internal",
            capabilities=["chat", "code"],
            contextWindow=32768,
        )
    )
    external_without_key = registry.create(
        ModelProfileCreate(
            displayName="External",
            endpoint="https://api.example.com",
            modelId="external",
            deploymentType="external",
            capabilities=["chat", "code", "vision"],
            contextWindow=400000,
        )
    )
    requirement = ModelRequirement(
        capabilities=["chat", "code"],
        minimumContext=8192,
        structuredOutput=True,
        qualityProfile="scenario_generation",
    )
    selector = ModelSelector(registry)
    fixed = selector.select(
        requirement,
        "auto",
        preferred_model_profile_id=internal.id,
        selection_role="advanced",
    )
    assert fixed.selectedModelProfileId == internal.id
    assert fixed.selectionMode == "manual"
    assert fixed.selectionRole == "advanced"
    blocked = selector.select(
        requirement,
        "auto",
        preferred_model_profile_id=external_without_key.id,
        selection_role="advanced",
    )
    assert blocked.route == "deterministic_fallback"
    candidate = next(item for item in blocked.candidates if item.modelProfileId == external_without_key.id)
    assert "external model credential is not loaded" in candidate.reasons


def test_project_model_binding_resolves_the_requirement_role(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    from app.services.sqlite_persist import kv_set

    kv_set(
        "platform_catalog_v1",
        {
            "projects": [
                {
                    "id": "PRJ-MODEL",
                    "modelSelectionMode": "manual",
                    "modelBindings": {"vision": "MODEL-VISION", "advanced": "MODEL-ADV"},
                }
            ]
        },
    )
    role, profile_id = resolve_project_model_binding(
        "PRJ-MODEL",
        ModelRequirement(capabilities=["chat", "vision"], qualityProfile="evidence_review"),
    )
    assert (role, profile_id) == ("vision", "MODEL-VISION")
    role, profile_id = resolve_project_model_binding(
        "PRJ-MODEL",
        ModelRequirement(capabilities=["chat", "code"], qualityProfile="scenario_generation"),
    )
    assert (role, profile_id) == ("advanced", "MODEL-ADV")


def test_tool_runtime_injects_the_selected_model_profile(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    registry = ModelRegistry()
    selected = registry.create(
        ModelProfileCreate(
            displayName="Selected Qwen",
            endpoint="http://qwen.internal:9000",
            modelId="qwen3.6:32b",
            apiKey="memory-only-key",
            capabilities=["chat", "code"],
        )
    )
    skills = SkillRegistry()
    skills.load()
    observed: dict[str, str] = {}

    def fake_run(args, *, capture_output, text, check, timeout, env):
        assert args[0] == sys.executable
        observed.update(
            {
                "base": env["LLM_BASE_URL"],
                "model": env["LLM_MODEL"],
                "key": env["LLM_API_KEY"],
                "enabled": env["LLM_ENABLED"],
            }
        )
        output_path = Path(args[args.index("--output") + 1])
        output_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("app.core.tool_runtime.runtime.subprocess.run", fake_run)
    result = ToolRuntime(skills, registry).run(
        "scenario_narrate",
        "narrate_and_bind",
        {
            "_runtime": {
                "modelDecision": {
                    "selectedModelProfileId": selected.id,
                }
            }
        },
    )
    assert result["ok"] is True
    assert result["_modelInvocations"] == [
        {
            "model": "qwen3.6:32b",
            "modelProfileId": selected.id,
            "displayName": "Selected Qwen",
            "status": "not_invoked",
            "reason": "도구가 완료됐지만 LLM 클라이언트 호출 경로는 실행되지 않았습니다.",
        }
    ]
    assert observed == {
        "base": "http://qwen.internal:9000/v1",
        "model": "qwen3.6:32b",
        "key": "memory-only-key",
        "enabled": "1",
    }


def test_tool_runtime_gives_gpt5_narration_enough_structured_output_budget(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    registry = ModelRegistry()
    selected = registry.create(
        ModelProfileCreate(
            displayName="GPT-5 narration",
            endpoint="https://api.openai.com",
            modelId="gpt-5",
            deploymentType="external",
            apiKey="memory-only-key",
            capabilities=["chat", "code"],
        )
    )
    skills = SkillRegistry()
    skills.load()
    observed: dict[str, str] = {}

    def fake_run(args, *, capture_output, text, check, timeout, env):
        del capture_output, text, check, timeout
        observed["maxTokens"] = env["LLM_MAX_TOKENS"]
        observed["reasoningEffort"] = env["LLM_REASONING_EFFORT"]
        output_path = Path(args[args.index("--output") + 1])
        output_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("app.core.tool_runtime.runtime.subprocess.run", fake_run)
    ToolRuntime(skills, registry).run(
        "scenario_narrate",
        "narrate_and_bind",
        {"_runtime": {"modelDecision": {"selectedModelProfileId": selected.id}}},
    )

    assert observed == {"maxTokens": "8192", "reasoningEffort": "minimal"}


def test_planner_agent_prompt_context_and_trace_are_integrated(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    workflows, skills, capabilities, agents = WorkflowRegistry(), SkillRegistry(), CapabilityRegistry(), AgentRegistry()
    workflows.load()
    skills.load()
    capabilities.load()
    agents.load()
    cross_validate(workflows, skills, capabilities, agents)
    registry = ModelRegistry()
    events = AgentEventStore()
    context = ContextStore(threshold_bytes=100)
    planner = Planner(
        workflows,
        skills,
        agents=agents,
        model_selector=ModelSelector(registry),
        context_store=context,
        events=events,
    )
    plan = planner.build(
        "wf_scenario_dsl",
        {"projectId": "PRJ-CORE", "aiPolicy": "balanced", "large": "x" * 1000},
    )
    assert plan.schemaVersion == "plan/v2"
    assert all(step.selectionReason for step in plan.steps)
    assert plan.steps[-1].modelDecision is not None
    assert plan.steps[-1].modelDecision.policy == "balanced"
    assert plan.steps[0].inputs.get("_contextRef", "").startswith("file:")
    assert context.resolve(plan.steps[0].inputs)["large"] == "x" * 1000
    event_types = [event.eventType for event in events.list_events(plan.planId)]
    assert event_types[0] == "workflow_started"
    assert "model_candidates_evaluated" in event_types
    assert "model_selected" in event_types
    assert event_types[-1] == "plan_created"
    detail = events.trace_detail(plan.planId)
    assert detail is not None
    assert "chain-of-thought" in detail["privacyNotice"]

    messages, metadata = PromptCatalog().render(
        "agent_roles/model_advisor_system.md",
        "정책: {policy}",
        policy="balanced",
    )
    assert len(messages) == 2
    assert metadata.version == "model-advisor/v1"
    system, vlm_metadata = PromptCatalog().render_system("project_context/vlm_ocr_system.md")
    assert '"screenName"' in system
    assert vlm_metadata.version == "project-context-vlm/v1"


def test_browser_step_audit_receipt_exposes_tool_provenance_without_inputs():
    details = _step_audit_details(
        {
            "ok": True,
            "runId": "RUN-audit",
            "artifactPath": "/evidence/RUN-audit/run-result.json",
            "result": {
                "scenarioId": "SCN-audit",
                "browserRunner": "agent-browser-cli",
                "steps": [
                    {"mcpTool": "agent_browser_open", "refOrLocator": "secret-selector"},
                    {"mcpTool": "agent_browser_fill", "value": "must-not-leak"},
                    {"mcpTool": "agent_browser_open"},
                ],
                "networkRequests": [{}, {}],
                "matchedNetworkRequests": [{}],
            },
        }
    )
    assert details == {
        "ok": True,
        "artifactPath": "/evidence/RUN-audit/run-result.json",
        "runId": "RUN-audit",
        "scenarioId": "SCN-audit",
        "browserRunner": "agent-browser-cli",
        "toolHistory": ["agent_browser_open", "agent_browser_fill"],
        "toolCallCount": 3,
        "networkRequestCount": 2,
        "matchedNetworkRequestCount": 1,
    }
    assert "must-not-leak" not in json.dumps(details)


def test_llm_client_writes_provider_usage_receipt_without_prompt_or_secret(monkeypatch, tmp_path):
    receipt_path = tmp_path / "model-usage.jsonl"
    monkeypatch.setenv("LLM_USAGE_RECEIPT_PATH", str(receipt_path))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "chatcmpl-receipt",
                    "model": "qwen-receipt",
                    "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                }
            ).encode("utf-8")

    monkeypatch.setattr("app.core.llm.llm_client.urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    client = LlmClient(
        base_url="http://model.internal/v1",
        model="qwen-receipt",
        embedding_model="embed",
        api_key="must-not-persist",
        temperature=0.0,
        max_tokens=64,
        enabled=True,
    )
    assert client.chat_json(system="secret system", user="secret input") == {"ok": True}
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["providerRequestId"] == "chatcmpl-receipt"
    assert receipt["promptTokens"] == 11
    assert receipt["completionTokens"] == 7
    assert receipt["totalTokens"] == 18
    stored = receipt_path.read_text(encoding="utf-8")
    assert "must-not-persist" not in stored
    assert "secret system" not in stored
    assert "secret input" not in stored


def test_gpt5_chat_uses_reasoning_family_generation_options(monkeypatch):
    observed: dict = {}
    monkeypatch.setenv("LLM_REASONING_EFFORT", "minimal")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"id": "chatcmpl-gpt5", "model": "gpt-5", "choices": [{"message": {"content": '{"ok": true}'}}]}
            ).encode("utf-8")

    def fake_open(request, **_kwargs):
        observed.update(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    monkeypatch.setattr("app.core.llm.llm_client.urllib.request.urlopen", fake_open)
    client = LlmClient(
        base_url="https://api.openai.com/v1",
        model="gpt-5",
        embedding_model="unused",
        api_key="memory-only",
        temperature=0.3,
        max_tokens=128,
        enabled=True,
    )
    assert client.chat_json(system="system", user="user") == {"ok": True}
    assert observed["max_completion_tokens"] == 128
    assert observed["reasoning_effort"] == "minimal"
    assert "max_tokens" not in observed
    assert "temperature" not in observed


def test_agent_monitor_distinguishes_selection_from_confirmed_model_usage(monkeypatch, tmp_path):
    _isolated_settings(monkeypatch, tmp_path)
    events = AgentEventStore()
    events.record(
        trace_id="PLAN-used",
        event_type="model_selected",
        summary="Qwen 후보 선택",
        details={"selectedDisplayName": "Qwen", "route": "model"},
    )
    events.record(
        trace_id="PLAN-used",
        event_type="model_invocation_completed",
        summary="Qwen 호출 완료",
        status="complete",
        details={"displayName": "Qwen", "status": "completed", "promptTokens": 5, "completionTokens": 3, "totalTokens": 8, "durationMs": 120},
    )
    events.record(trace_id="PLAN-used", event_type="workflow_completed", summary="완료", status="complete")
    events.record(
        trace_id="PLAN-selected-only",
        event_type="model_selected",
        summary="Qwen 후보 선택",
        details={"selectedDisplayName": "Qwen", "route": "model"},
    )
    events.record(trace_id="PLAN-selected-only", event_type="workflow_completed", summary="완료", status="complete")

    by_id = {item.traceId: item for item in events.traces()}
    assert by_id["PLAN-used"].modelExecutionStatus == "used"
    assert by_id["PLAN-used"].modelTotalTokens == 8
    assert by_id["PLAN-selected-only"].modelExecutionStatus == "unverified"
    assert events.summary()["selectedWithoutInvocation"] == 1
    metrics = events.prometheus_metrics()
    assert 'qa_auto_model_invocations_total{model="Qwen",outcome="completed"} 1' in metrics
    assert 'qa_auto_model_tokens_total{model="Qwen",type="total"} 8' in metrics
