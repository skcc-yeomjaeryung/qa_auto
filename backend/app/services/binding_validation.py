from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from app.core.paths import ARTIFACTS_EVIDENCE
from app.schemas.binding_validation import (
    BindingAssertion,
    BindingValidateRequest,
    BindingValidationResult,
)
from app.services.binding_normalization import values_equal
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore


SENSITIVE_FIELD_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "ssn",
    "resident",
)
BUSINESS_REVIEW_FIELDS = {"risklevel", "status"}


class BindingValidationService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def validate(
        self,
        run_id: str,
        payload: BindingValidateRequest | None = None,
    ) -> BindingValidationResult:
        payload = payload or BindingValidateRequest()
        run = self.store.get_run(run_id)
        if not run:
            raise LookupError(f"run not found: {run_id}")
        scenario = self.store.get_scenario(run.scenarioId)
        contract = self.store.get_contract_by_scenario(run.scenarioId)
        outputs = self._outputs(contract.result if contract else {}, scenario.result if scenario else {})
        events = list(self.store.list_backend_events(run_id))
        request_event = next((e for e in reversed(events) if e.request), None)
        response_event = next(
            (e for e in reversed(events) if e.event == "response_returned" and e.response is not None),
            None,
        )

        backend_request = dict(request_event.request or {}) if request_event else {}
        backend_response = dict(response_event.response or {}) if response_event else {}
        frontend_request = (
            dict(payload.frontendRequest)
            or dict((run.result or {}).get("frontendRequest") or {})
        )
        ui_values = (
            dict(payload.uiValues)
            or dict((run.result or {}).get("bindingValues") or {})
            or self._ui_values_from_steps(run.steps)
        )

        assertions: list[BindingAssertion] = []
        missing: list[str] = []
        screenshot = self._result_screenshot(run)
        for idx, output in enumerate(outputs, start=1):
            field = str(output.get("field") or "")
            if not field:
                continue
            path = str(output.get("responsePath") or f"$.{field}")
            locator = dict(output.get("uiLocator") or {})
            target = self._locator_text(locator)
            rules = list(output.get("normalize") or ["trim"])
            enum_labels = dict(payload.enumLabels.get(field) or {})
            a_input = self._field(run.inputs, field)
            fe_request = self._field(frontend_request, field)
            be_request = self._field(backend_request, field)
            be_response = self._json_path(backend_response, path)
            ui_value = self._field(ui_values, field)
            field_missing: list[str] = []

            if field.casefold() == "customerid":
                for source_name, value in (
                    ("a_input", a_input),
                    ("frontend_request", fe_request),
                    ("backend_request", be_request),
                    ("backend_response", be_response),
                    ("ui_value", ui_value),
                ):
                    if value is None:
                        field_missing.append(source_name)
                candidates = [
                    value
                    for value in (a_input, fe_request, be_request, be_response, ui_value)
                    if value is not None
                ]
                expected = candidates[0] if candidates else None
                actual = ui_value
                compared = candidates
                normalized = [
                    values_equal(expected, value, rules, enum_labels=enum_labels)[2]
                    for value in compared
                ] if expected is not None else []
                matched = bool(normalized) and len(set(map(str, normalized))) == 1
                norm_expected = normalized[0] if normalized else None
                norm_actual = normalized[-1] if normalized else None
            else:
                expected = be_response
                actual = ui_value
                if be_response is None:
                    field_missing.append("backend_response")
                if ui_value is None:
                    field_missing.append("ui_value")
                matched, norm_expected, norm_actual = values_equal(
                    expected,
                    actual,
                    rules,
                    enum_labels=enum_labels,
                )

            business_review = bool(output.get("reviewRequired")) or field.casefold() in BUSINESS_REVIEW_FIELDS
            if field_missing:
                result = "MISSING_DATA"
                missing.extend(f"{field}:{item}" for item in field_missing)
            elif not matched:
                result = "MISMATCH"
            elif business_review:
                result = "REVIEW_REQUIRED"
            else:
                result = "MATCH"

            masked = self._sensitive(field)
            assertions.append(
                BindingAssertion(
                    assertionId=f"BA-{idx:03d}-{uuid4().hex[:6]}",
                    field=field,
                    source=path,
                    target=target,
                    aInput=self._display(a_input, masked),
                    frontendRequest=self._display(fe_request, masked),
                    backendRequest=self._display(be_request, masked),
                    backendResponse=self._display(be_response, masked),
                    uiValue=self._display(ui_value, masked),
                    expected=self._display(expected, masked),
                    actual=self._display(actual, masked),
                    normalizedExpected=self._display(norm_expected, masked),
                    normalizedActual=self._display(norm_actual, masked),
                    normalizers=rules,
                    result=result,
                    businessReviewRequired=business_review,
                    hard=False,
                    masked=masked,
                    evidence={
                        "screenshotPath": screenshot,
                        "region": payload.screenshotRegions.get(field),
                        "snapshotPath": self._snapshot_for_field(run.steps, target),
                    },
                    missingData=field_missing,
                )
            )

        assertions.extend(
            self._technical_assertions(
                run=run,
                scenario_result=scenario.result if scenario else {},
                response_event=response_event,
                payload=payload,
            )
        )
        missing = list(dict.fromkeys(missing))
        result = self._result(run, contract.contractId if contract else None, assertions, missing)
        artifact_dir = ARTIFACTS_EVIDENCE / "runs" / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / "binding-validation.json"
        result = result.model_copy(update={"artifactPath": str(artifact)})
        artifact.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        self.store.save_binding_result(result)
        return result

    def get(self, run_id: str) -> BindingValidationResult | None:
        return self.store.get_binding_result(run_id)

    def _result(
        self,
        run: Any,
        contract_id: str | None,
        assertions: list[BindingAssertion],
        missing: list[str],
    ) -> BindingValidationResult:
        hard_mismatch = any(a.hard and a.result == "MISMATCH" for a in assertions)
        mismatch = any(a.result == "MISMATCH" for a in assertions)
        partial = bool(missing) or any(a.result == "MISSING_DATA" for a in assertions)
        if hard_mismatch:
            status = "BLOCKED"
        elif partial:
            status = "PARTIAL"
        elif mismatch:
            status = "TECHNICAL_MISMATCH"
        else:
            status = "TECHNICALLY_MATCHED"
        return BindingValidationResult(
            runId=run.runId,
            scenarioId=run.scenarioId,
            contractId=contract_id,
            technicalStatus=status,
            businessReviewRequired=any(a.businessReviewRequired for a in assertions),
            assertions=assertions,
            missingData=missing,
            createdAt=utc_now().isoformat(),
        )

    def _technical_assertions(
        self,
        *,
        run: Any,
        scenario_result: dict[str, Any],
        response_event: Any,
        payload: BindingValidateRequest,
    ) -> list[BindingAssertion]:
        rows: list[BindingAssertion] = []
        expects_backend = any(
            str(step.get("action") or "") in {"wait_for_response", "verify_response"}
            for step in (scenario_result.get("steps") or [])
            if isinstance(step, dict)
        )
        if expects_backend:
            status = response_event.status if response_event else None
            rows.append(
                self._technical_row(
                    "httpStatus",
                    expected="2xx/3xx",
                    actual=status,
                    matched=isinstance(status, int) and 200 <= status < 400,
                    missing=status is None,
                )
            )
        route_pattern = str(
            (scenario_result.get("destination") or {}).get("routePattern") or ""
        ).strip()
        if route_pattern.casefold() not in {"", "missing_data", "n/a", "none", "없음"}:
            current_route = payload.currentRoute or str((run.result or {}).get("currentUrl") or "")
            rows.append(
                self._technical_row(
                    "route",
                    expected=route_pattern,
                    actual=current_route or None,
                    matched=self._route_matches(route_pattern, current_route),
                    missing=not current_route,
                )
            )
        if payload.responseSchemaValid is not None:
            rows.append(
                self._technical_row(
                    "responseSchema",
                    expected=True,
                    actual=payload.responseSchemaValid,
                    matched=payload.responseSchemaValid is True,
                    missing=False,
                )
            )
        return rows

    @staticmethod
    def _technical_row(
        field: str,
        *,
        expected: Any,
        actual: Any,
        matched: bool,
        missing: bool,
    ) -> BindingAssertion:
        return BindingAssertion(
            assertionId=f"TA-{field}-{uuid4().hex[:6]}",
            field=field,
            source="technical",
            target=field,
            expected=expected,
            actual=actual,
            normalizedExpected=expected,
            normalizedActual=actual,
            result="MISSING_DATA" if missing else ("MATCH" if matched else "MISMATCH"),
            hard=True,
            missingData=[field] if missing else [],
        )

    @staticmethod
    def _outputs(contract: dict[str, Any], scenario: dict[str, Any]) -> list[dict[str, Any]]:
        if bool((scenario.get("caseVariant") or {}).get("validationOnly")):
            return []
        outputs = list(contract.get("outputs") or [])
        if outputs:
            return outputs
        # Scenario ``bindings`` contains graph hints such as ``beforeAfter``
        # and ``connectedApi``.  They are not response-to-DOM output
        # contracts.  Only a Component Contract output may drive cross-layer
        # binding comparison; otherwise browser/network technical assertions
        # remain the source of truth.
        return []

    @staticmethod
    def _json_path(body: dict[str, Any], path: str) -> Any:
        if not path.startswith("$."):
            return None
        current: Any = body
        for part in path[2:].split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _field(body: dict[str, Any], field: str) -> Any:
        if field in body:
            return body[field]
        folded = field.casefold()
        for key, value in body.items():
            if str(key).casefold() == folded:
                return value
        return None

    @staticmethod
    def _ui_values_from_steps(steps: list[Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        pattern = re.compile(r"binding\s+([^=;\s]+)=([^;]+)")
        for step in steps or []:
            match = pattern.search(str(step.observationSummary or ""))
            if match:
                values[match.group(1)] = match.group(2).strip()
        return values

    @staticmethod
    def _locator_text(locator: dict[str, Any]) -> str:
        strategy = str(locator.get("strategy") or "testId")
        value = str(locator.get("value") or "")
        return f"{strategy}:{value}"

    @staticmethod
    def _snapshot_for_field(steps: list[Any], target: str) -> str | None:
        value = target.split(":", 1)[-1]
        for step in reversed(steps or []):
            if step.snapshotPath and (
                value in str(step.refOrLocator or "")
                or step.action == "verify_binding"
            ):
                return step.snapshotPath
        return None

    @staticmethod
    def _result_screenshot(run: Any) -> str | None:
        for step in reversed(run.steps or []):
            if step.screenshotPath:
                return step.screenshotPath
        return None

    @staticmethod
    def _route_matches(pattern: str, actual: str) -> bool:
        if not pattern or not actual:
            return False
        escaped = "/".join(
            r"[^/]+" if part.startswith(":") else re.escape(part)
            for part in pattern.split("/")
        )
        return bool(re.search(escaped, actual))

    @staticmethod
    def _sensitive(field: str) -> bool:
        compact = field.casefold().replace("-", "").replace("_", "")
        return any(part.replace("-", "").replace("_", "") in compact for part in SENSITIVE_FIELD_PARTS)

    @staticmethod
    def _display(value: Any, masked: bool) -> Any:
        if masked and value is not None:
            return "***"
        return value
