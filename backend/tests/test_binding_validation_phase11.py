from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_platform_store
from app.core.bootstrap import bootstrap_runtime
from app.core.paths import REPO_ROOT
from app.main import app
from app.schemas.telemetry import BackendTelemetryEvent
from app.services.binding_normalization import normalize_value, values_equal
from app.services.component_contract_models import ComponentContractSummary
from app.services.run_models import RunStepSummary, RunSummary
from app.services.scenario_models import ScenarioSummary

client = TestClient(app)
SCHEMA = (
    REPO_ROOT
    / "packages"
    / "contracts"
    / "schemas"
    / "binding_validation.schema.json"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    ):
        if hasattr(store, attr):
            getattr(store, attr).clear()
    yield


def _seed(
    *,
    run_id: str = "RUN-p11",
    outputs: list[dict] | None = None,
    response: dict | None = None,
    request: dict | None = None,
    inputs: dict | None = None,
    binding_values: dict | None = None,
    status: int = 200,
) -> None:
    store = get_platform_store()
    scenario = ScenarioSummary(
        scenarioId="SCN-p11",
        serviceId="customer-search",
        status="EXECUTABLE",
        result={
            "scenarioId": "SCN-p11",
            "destination": {"routePattern": "/customers/:customerId"},
        },
    )
    store.save_scenario(scenario)
    default_outputs = [
        {
            "field": "customerId",
            "responsePath": "$.customerId",
            "uiLocator": {"strategy": "testId", "value": "customer-detail-id"},
            "normalize": ["trim"],
            "reviewRequired": False,
        },
        {
            "field": "customerName",
            "responsePath": "$.customerName",
            "uiLocator": {"strategy": "testId", "value": "customer-detail-name"},
            "normalize": ["trim"],
            "reviewRequired": False,
        },
        {
            "field": "riskLevel",
            "responsePath": "$.riskLevel",
            "uiLocator": {"strategy": "testId", "value": "customer-detail-risk"},
            "normalize": ["trim", "uppercase"],
            "reviewRequired": True,
        },
        {
            "field": "status",
            "responsePath": "$.status",
            "uiLocator": {"strategy": "testId", "value": "customer-detail-status"},
            "normalize": ["trim"],
            "reviewRequired": True,
        },
    ]
    store.save_contract(
        ComponentContractSummary(
            contractId="CC-p11",
            scenarioId="SCN-p11",
            result={"outputs": outputs or default_outputs},
        )
    )
    run = RunSummary(
        runId=run_id,
        scenarioId="SCN-p11",
        status="WAITING_FOR_REVIEW",
        inputs=inputs or {"customerId": "C10001"},
        result={
            "bindingValues": binding_values or {},
            "frontendRequest": request or {},
            "currentUrl": "http://local/customers/C10001",
        },
        steps=[
            RunStepSummary(
                stepId="S9",
                action="verify_binding",
                status="ok",
                snapshotPath=f"/tmp/{run_id}.snapshot.txt",
                screenshotPath=f"/tmp/{run_id}.png",
            )
        ],
        createdAt=_now(),
        updatedAt=_now(),
    )
    store.save_run(run)
    store.append_backend_event(
        BackendTelemetryEvent(
            timestamp=_now(),
            event="response_returned",
            testRunId=run_id,
            scenarioId="SCN-p11",
            request=request or {},
            response=response or {},
            status=status,
            durationMs=5,
            source="spring",
        )
    )


def test_exact_customer_lineage_and_output_equality():
    body = {
        "customerId": "C10001",
        "customerName": "홍길동",
        "riskLevel": "HIGH",
        "status": "ACTIVE",
    }
    _seed(response=body, request={"customerId": "C10001"}, binding_values=body)
    res = client.post(
        "/api/runs/RUN-p11/validate-bindings",
        json={
            "uiValues": body,
            "frontendRequest": {"customerId": "C10001"},
            "currentRoute": "/customers/C10001",
            "responseSchemaValid": True,
        },
    )
    assert res.status_code == 200
    result = res.json()
    customer = next(a for a in result["assertions"] if a["field"] == "customerId")
    assert customer["result"] == "MATCH"
    assert customer["aInput"] == customer["frontendRequest"]
    assert customer["frontendRequest"] == customer["backendRequest"]
    assert customer["backendRequest"] == customer["backendResponse"]
    assert customer["backendResponse"] == customer["uiValue"]
    risk = next(a for a in result["assertions"] if a["field"] == "riskLevel")
    assert risk["result"] == "REVIEW_REQUIRED"
    assert result["businessReviewRequired"] is True


def test_trim_and_case_normalization():
    ok, expected, actual = values_equal(" HIGH ", "high", ["trim", "case"])
    assert ok is True
    assert expected == actual == "high"


def test_number_and_currency_normalization():
    assert normalize_value("1,234", ["number"]) == 1234
    assert normalize_value("₩ 1,234.50", ["currency"]) == "1234.5"


def test_date_timezone_normalization():
    left = normalize_value("2026-08-05T09:00:00+09:00", ["timezone"])
    right = normalize_value("2026-08-05T00:00:00Z", ["timezone"])
    assert left == right == "2026-08-05T00:00:00Z"


def test_enum_label_normalization():
    ok, expected, actual = values_equal(
        "ACTIVE",
        "정상",
        ["enum_label"],
        enum_labels={"ACTIVE": "정상"},
    )
    assert ok is True
    assert expected == actual == "정상"


def test_null_empty_normalization():
    ok, expected, actual = values_equal(None, "  ", ["null_empty"])
    assert ok is True
    assert expected is None and actual is None


def test_async_delayed_binding_observation_reused_from_run_result():
    output = [
        {
            "field": "customerName",
            "responsePath": "$.customerName",
            "uiLocator": {"strategy": "testId", "value": "customer-detail-name"},
            "normalize": ["trim"],
            "reviewRequired": False,
        }
    ]
    _seed(
        run_id="RUN-async",
        outputs=output,
        response={"customerName": "지연 렌더"},
        binding_values={"customerName": "지연 렌더"},
    )
    res = client.post(
        "/api/runs/RUN-async/validate-bindings",
        json={"currentRoute": "/customers/C10001"},
    )
    assertion = res.json()["assertions"][0]
    assert assertion["result"] == "MATCH"
    assert assertion["uiValue"] == "지연 렌더"


def test_missing_ui_field_is_missing_data_not_inferred():
    output = [
        {
            "field": "customerName",
            "responsePath": "$.customerName",
            "uiLocator": {"strategy": "testId", "value": "customer-detail-name"},
            "normalize": ["trim"],
            "reviewRequired": False,
        }
    ]
    _seed(run_id="RUN-missing", outputs=output, response={"customerName": "홍길동"})
    res = client.post(
        "/api/runs/RUN-missing/validate-bindings",
        json={"currentRoute": "/customers/C10001"},
    )
    body = res.json()
    assertion = body["assertions"][0]
    assert assertion["result"] == "MISSING_DATA"
    assert "ui_value" in assertion["missingData"]
    assert body["technicalStatus"] == "PARTIAL"


def test_business_review_required_is_separate_from_technical_match():
    output = [
        {
            "field": "riskLevel",
            "responsePath": "$.riskLevel",
            "uiLocator": {"strategy": "testId", "value": "risk"},
            "normalize": ["uppercase"],
            "reviewRequired": True,
        }
    ]
    _seed(
        run_id="RUN-review",
        outputs=output,
        response={"riskLevel": "HIGH"},
        binding_values={"riskLevel": "HIGH"},
    )
    body = client.post(
        "/api/runs/RUN-review/validate-bindings",
        json={"currentRoute": "/customers/C10001"},
    ).json()
    assert body["technicalStatus"] == "TECHNICALLY_MATCHED"
    assert body["businessReviewRequired"] is True
    assert body["assertions"][0]["result"] == "REVIEW_REQUIRED"


def test_graph_hint_bindings_and_na_route_do_not_create_false_missing_data():
    store = get_platform_store()
    store.save_scenario(
        ScenarioSummary(
            scenarioId="SCN-p11",
            serviceId="multi",
            status="EXECUTABLE",
            result={
                "scenarioId": "SCN-p11",
                "destination": {"routePattern": "n/a"},
                "bindings": {"beforeAfter": ["#account-user-name"]},
                "steps": [],
            },
        )
    )
    store.save_contract(
        ComponentContractSummary(
            contractId="CC-p11",
            scenarioId="SCN-p11",
            result={"outputs": []},
        )
    )
    store.save_run(
        RunSummary(
            runId="RUN-ui-only",
            scenarioId="SCN-p11",
            status="WAITING_FOR_REVIEW",
            result={"currentUrl": "http://local/"},
            createdAt=_now(),
            updatedAt=_now(),
        )
    )
    body = client.post("/api/runs/RUN-ui-only/validate-bindings", json={}).json()
    assert body["technicalStatus"] == "TECHNICALLY_MATCHED"
    assert body["missingData"] == []
    assert body["assertions"] == []


def test_masked_sensitive_field_and_mismatch_evidence():
    output = [
        {
            "field": "password",
            "responsePath": "$.password",
            "uiLocator": {"strategy": "testId", "value": "password"},
            "normalize": ["trim"],
            "reviewRequired": False,
        }
    ]
    _seed(
        run_id="RUN-mask",
        outputs=output,
        response={"password": "server-secret"},
        binding_values={"password": "different"},
    )
    body = client.post(
        "/api/runs/RUN-mask/validate-bindings",
        json={
            "currentRoute": "/customers/C10001",
            "screenshotRegions": {"password": {"x": 1, "y": 2, "width": 10, "height": 10}},
        },
    ).json()
    assertion = body["assertions"][0]
    assert assertion["result"] == "MISMATCH"
    assert assertion["expected"] == assertion["actual"] == "***"
    assert assertion["masked"] is True
    assert assertion["evidence"]["screenshotPath"].endswith(".png")
    assert assertion["evidence"]["region"]["x"] == 1


def test_assertions_api_and_schema_persistence():
    output = [
        {
            "field": "customerName",
            "responsePath": "$.customerName",
            "uiLocator": {"strategy": "testId", "value": "name"},
            "normalize": ["trim"],
            "reviewRequired": False,
        }
    ]
    _seed(
        run_id="RUN-api",
        outputs=output,
        response={"customerName": "홍길동"},
        binding_values={"customerName": "홍길동"},
    )
    created = client.post(
        "/api/runs/RUN-api/validate-bindings",
        json={"currentRoute": "/customers/C10001"},
    )
    assert created.status_code == 200
    assertions = client.get("/api/runs/RUN-api/assertions")
    assert assertions.status_code == 200
    assert assertions.json()[0]["field"] == "customerName"
    loaded = client.get("/api/runs/RUN-api/binding-validation")
    assert loaded.status_code == 200
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(loaded.json())
    timeline = client.get("/api/runs/RUN-api/timeline")
    assert timeline.status_code == 200
    binding_entry = next(
        entry for entry in timeline.json()["entries"] if entry["kind"] == "binding"
    )
    assert binding_entry["status"] == "TECHNICALLY_MATCHED"
    assert binding_entry["payload"]["artifactPath"].endswith(
        "binding-validation.json"
    )
