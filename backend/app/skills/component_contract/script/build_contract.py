#!/usr/bin/env python3
"""component_contract / build_contract — FE+BE → Input/Output Contract (deterministic)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


LOCATOR_RANK = {
    "testId": 1,
    "role": 2,
    "label": 3,
    "id": 4,
    "name": 5,
    "css": 6,
    "xpath": 7,
}

DEFAULT_B_BINDINGS = [
    {"field": "customerId", "responsePath": "$.customerId", "testId": "customer-detail-id", "normalize": ["trim"]},
    {"field": "customerName", "responsePath": "$.customerName", "testId": "customer-detail-name", "normalize": ["trim"]},
    {
        "field": "riskLevel",
        "responsePath": "$.riskLevel",
        "testId": "customer-detail-risk",
        "normalize": ["trim", "uppercase"],
    },
    {"field": "status", "responsePath": "$.status", "testId": "customer-detail-status", "normalize": ["trim"]},
]


def _load_json(src: Any) -> dict[str, Any]:
    if isinstance(src, dict):
        return src
    if not src:
        return {}
    path = Path(str(src)).expanduser().resolve()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_adapter(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {}
    text = p.read_text(encoding="utf-8")
    if p.suffix in {".yml", ".yaml"}:
        if yaml is None:
            return {}
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _extract_pattern(expression: str | None) -> str | None:
    if not expression:
        return None
    m = re.search(r"/(\^[^/]+\$)/", expression)
    if m:
        return m.group(1)
    m = re.search(r"'regexp'\s*:\s*'([^']+)'", expression)
    if m:
        return m.group(1).replace("\\\\", "\\")
    m = re.search(r'"regexp"\s*:\s*"([^"]+)"', expression)
    if m:
        return m.group(1).replace("\\\\", "\\")
    return None


def _choose_locator(inp: dict[str, Any], *, force_css: str | None = None) -> dict[str, Any]:
    if force_css:
        return {
            "strategy": "css",
            "value": force_css,
            "stable": False,
            "priority": LOCATOR_RANK["css"],
        }
    test_id = inp.get("testId")
    if test_id:
        return {
            "strategy": "testId",
            "value": str(test_id),
            "stable": True,
            "priority": LOCATOR_RANK["testId"],
        }
    role = inp.get("role")
    label = inp.get("label") or inp.get("name")
    if role and label:
        return {
            "strategy": "role",
            "value": str(role),
            "name": str(label),
            "stable": True,
            "priority": LOCATOR_RANK["role"],
        }
    if label:
        return {
            "strategy": "label",
            "value": str(label),
            "stable": True,
            "priority": LOCATOR_RANK["label"],
        }
    html_id = (inp.get("constraints") or {}).get("id") or inp.get("id")
    if html_id and not str(html_id).startswith("input-"):
        return {
            "strategy": "id",
            "value": str(html_id),
            "stable": True,
            "priority": LOCATOR_RANK["id"],
        }
    name = inp.get("name")
    if name:
        return {
            "strategy": "name",
            "value": str(name),
            "stable": True,
            "priority": LOCATOR_RANK["name"],
        }
    # last resort — unstable
    return {
        "strategy": "css",
        "value": f"[data-fallback='{inp.get('id') or 'unknown'}']",
        "stable": False,
        "priority": LOCATOR_RANK["css"],
    }


def _semantic_type(field: str, adapter: dict[str, Any]) -> str | None:
    hints = adapter.get("semanticHints") or {}
    if field in hints:
        return str(hints[field])
    if "customer" in field.lower() and "id" in field.lower():
        return "customer_identifier"
    return None


def _logical_name(inp: dict[str, Any]) -> str:
    return str(inp.get("name") or inp.get("testId") or inp.get("label") or inp.get("id") or "field")


def _fe_constraints_for(field: str, frontend: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"required": False, "pattern": None, "sources": []}
    for val in frontend.get("validations") or []:
        if str(val.get("field") or "") not in {field, field.replace("-", ""), "customerId"} and field not in {
            "customerId",
            "customer-id",
            "customer-id-input",
        }:
            # match customerId variants
            if str(val.get("field") or "").lower() not in {field.lower(), "customerid"}:
                if "customer" not in field.lower():
                    continue
                if str(val.get("field") or "").lower() != "customerid":
                    continue
        out["required"] = bool(val.get("required") or out["required"])
        pattern = _extract_pattern(str(val.get("expression") or ""))
        if pattern:
            out["pattern"] = pattern
        out["sources"].append(
            {
                "kind": "frontend_validation",
                "id": val.get("id"),
                "extractor": (val.get("evidence") or {}).get("extractor"),
            }
        )
    return out


def _be_constraints_for(field: str, backend: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"required": False, "pattern": None, "sources": []}
    canonical = "customerId" if "customer" in field.lower() and "id" in field.lower() else field
    for dto in backend.get("requestDtos") or []:
        for f in dto.get("fields") or []:
            if str(f.get("name") or f.get("jsonName")) != canonical:
                continue
            out["required"] = bool(f.get("required") or out["required"])
            constraints = f.get("constraints") or {}
            if constraints.get("NotBlank"):
                out["required"] = True
            pattern_obj = constraints.get("Pattern") or {}
            if isinstance(pattern_obj, dict) and pattern_obj.get("regexp"):
                out["pattern"] = str(pattern_obj["regexp"]).replace("\\\\", "\\")
            out["sources"].append({"kind": "backend_dto", "dto": dto.get("name"), "field": canonical})
    for val in backend.get("validations") or []:
        if str(val.get("field") or "") != canonical:
            continue
        if val.get("kind") == "NotBlank":
            out["required"] = True
        if val.get("kind") == "Pattern":
            pattern = _extract_pattern(str(val.get("expression") or ""))
            if pattern:
                out["pattern"] = pattern
        out["sources"].append({"kind": "backend_validation", "id": val.get("id")})
    return out


def _events_for_input(inp: dict[str, Any], frontend: dict[str, Any], adapter: dict[str, Any]) -> list[str]:
    events: list[str] = []
    kind = str(inp.get("kind") or "input")
    # adapter custom component
    for comp in adapter.get("components") or []:
        if str(comp.get("name")) in {kind, str(inp.get("componentType") or "")}:
            events.extend([str(e) for e in (comp.get("events") or [])])
    # FE event evidence near line
    line = (inp.get("evidence") or {}).get("line")
    for ev in frontend.get("events") or []:
        ev_line = (ev.get("evidence") or {}).get("line")
        name = str(ev.get("event") or "")
        if line and ev_line and abs(int(ev_line) - int(line)) <= 5:
            if name in {"onChange", "onInput"}:
                events.append("fill")
            elif name == "onBlur":
                events.append("blur")
            elif name == "onSubmit":
                events.append("submit")
            elif name == "onClick":
                events.append("click")
    if kind == "button":
        events.extend(["click"])
    elif kind in {"input", "form"} or inp.get("testId"):
        events.extend(["fill", "blur"])
    # unique preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for e in events:
        if e not in seen:
            seen.add(e)
            ordered.append(e)
    return ordered or ["fill"]


def _build_inputs(
    frontend: dict[str, Any],
    backend: dict[str, Any],
    adapter: dict[str, Any],
    *,
    design_hints: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    inputs_out: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    design_hints = design_hints or {}

    for inp in frontend.get("inputs") or []:
        kind = str(inp.get("kind") or "input")
        if kind == "form":
            continue
        logical = _logical_name(inp)
        field = str(inp.get("scenarioField") or inp.get("name") or logical)
        if not inp.get("scenarioField"):
            field = field.replace("-", "")
        if field in {"customerid", "customerId"} or logical in {"customer-id", "customer-id-input"}:
            field = "customerId"
        locator = _choose_locator(inp)
        if not locator.get("stable"):
            warnings.append(
                {
                    "kind": "unstable_locator",
                    "field": field,
                    "message": f"Locator strategy={locator['strategy']} is unstable; not auto-confirmed",
                    "confirmed": False,
                }
            )

        fe_c = _fe_constraints_for(field, frontend)
        be_c = _be_constraints_for(field, backend)
        pattern = fe_c.get("pattern") or be_c.get("pattern")
        required = bool(fe_c.get("required") or be_c.get("required") or inp.get("required"))

        if fe_c.get("pattern") and be_c.get("pattern") and fe_c["pattern"] != be_c["pattern"]:
            mismatches.append(
                {
                    "field": field,
                    "frontendPattern": fe_c["pattern"],
                    "backendPattern": be_c["pattern"],
                    "message": "Frontend/Backend pattern differs",
                }
            )
        if bool(fe_c.get("required")) != bool(be_c.get("required")) and (fe_c["sources"] or be_c["sources"]):
            mismatches.append(
                {
                    "field": field,
                    "frontendRequired": fe_c.get("required"),
                    "backendRequired": be_c.get("required"),
                    "message": "Frontend/Backend required flag differs",
                }
            )

        semantic = _semantic_type(field, adapter) or _semantic_type(logical, adapter)
        hint = (design_hints.get("fields") or {}).get(field) or (design_hints.get("fields") or {}).get(logical)
        sources = [
            {"kind": "frontend_input", "id": inp.get("id"), "file": (inp.get("evidence") or {}).get("file")},
            *fe_c.get("sources", []),
            *be_c.get("sources", []),
        ]
        if hint:
            sources.append({"kind": "design_spec_hint", "hint": hint, "reviewRequired": True})
            warnings.append(
                {
                    "kind": "design_spec_hint",
                    "field": field,
                    "message": "Design Spec used as hint only; Locator/required from code Evidence",
                    "confirmed": False,
                }
            )

        contract = {
            "field": field,
            "logicalName": logical,
            "semanticType": semantic,
            "componentType": kind if kind != "input" else "native-input",
            "required": required,
            "type": "string",
            "format": None,
            "pattern": pattern,
            "min": None,
            "max": None,
            "enum": None,
            "defaultValue": None,
            "locator": locator,
            "events": _events_for_input(inp, frontend, adapter),
            "recommendationReady": False,
            "sources": sources,
            "reviewRequired": not locator.get("stable") or bool(hint),
        }

        if kind == "button":
            actions.append(
                {
                    "id": str(inp.get("id") or f"action-{logical}"),
                    "kind": "button",
                    "logicalName": logical,
                    "events": contract["events"] or ["click"],
                    "locator": locator,
                    "sources": sources,
                }
            )
        else:
            inputs_out.append(contract)

    # Ensure customerId A input exists for golden path Gate
    if not any(i["field"] == "customerId" for i in inputs_out):
        warnings.append(
            {
                "kind": "missing_data",
                "field": "customerId",
                "message": "No customerId input Evidence in FE analysis",
                "confirmed": False,
            }
        )

    return inputs_out, actions, warnings, mismatches


def _build_outputs(
    frontend: dict[str, Any],
    backend: dict[str, Any],
    graph: dict[str, Any],
    adapter: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    adapter_bindings = list(adapter.get("bindings") or []) or list(DEFAULT_B_BINDINGS)
    graph_bindings = {
        str((n.get("attributes") or {}).get("field") or n.get("name")): n
        for n in (graph.get("nodes") or [])
        if n.get("type") == "binding"
    }

    response_fields: list[str] = []
    for dto in backend.get("responseDtos") or []:
        for f in dto.get("fields") or []:
            response_fields.append(str(f.get("jsonName") or f.get("name")))

    for bind in adapter_bindings:
        field = str(bind.get("field"))
        test_id = str(bind.get("testId") or "")
        response_path = str(bind.get("responsePath") or f"$.{field}")
        normalize = list(bind.get("normalize") or ["trim"])

        fe_hit = next(
            (i for i in (frontend.get("inputs") or []) if i.get("testId") == test_id),
            None,
        )
        g_hit = graph_bindings.get(field)
        in_response = field in response_fields or not response_fields

        sources: list[dict[str, Any]] = [{"kind": "adapter_binding", "field": field}]
        if g_hit:
            sources.append({"kind": "interaction_graph_binding", "nodeId": g_hit.get("id")})
        if fe_hit:
            sources.append({"kind": "frontend_input", "id": fe_hit.get("id")})
        if in_response and response_fields:
            sources.append({"kind": "backend_response_dto", "field": field})

        if not g_hit and not fe_hit and not in_response:
            missing.append(
                {
                    "kind": "missing_data",
                    "symbol": field,
                    "reason": "No FE/BE/graph Evidence for B binding; adapter hint only",
                }
            )
            warnings.append(
                {
                    "kind": "missing_data",
                    "field": field,
                    "message": f"B binding {field} lacks DOM/code Evidence",
                    "confirmed": False,
                }
            )

        locator = {
            "strategy": "testId",
            "value": test_id,
            "stable": True,
            "priority": LOCATOR_RANK["testId"],
        }
        outputs.append(
            {
                "field": field,
                "responsePath": response_path,
                "uiLocator": locator,
                "normalize": normalize,
                "assertion": f"ui shows {field} from {response_path}",
                "sources": sources,
                "reviewRequired": not bool(g_hit or fe_hit),
            }
        )

    return outputs, warnings, missing


def _screenshot_hooks(adapter: dict[str, Any]) -> dict[str, Any]:
    masks = []
    for m in adapter.get("screenshotMask") or []:
        masks.append(
            {
                "id": str(m.get("id") or m.get("testId")),
                "locator": {"strategy": "testId", "value": str(m.get("testId")), "stable": True},
                "reason": str(m.get("reason") or "pii_candidate"),
            }
        )
    if not masks:
        masks = [
            {
                "id": "mask-customer-id-input",
                "locator": {"strategy": "testId", "value": "customer-id-input", "stable": True},
                "reason": "identifier_pii_candidate",
            }
        ]
    return {
        "points": [
            {
                "id": "shot-after-fill",
                "when": "after_input_fill",
                "screen": "A",
                "filledAtRuntime": False,
            },
            {
                "id": "shot-result-screen",
                "when": "after_navigation_b",
                "screen": "B",
                "filledAtRuntime": False,
            },
        ],
        "maskRegions": masks,
    }


def _normal_field(value: Any) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", str(value or "").lower())


def _scenario_scoped_frontend(
    frontend: dict[str, Any], scenario: dict[str, Any]
) -> dict[str, Any]:
    """Keep only inputs/screens declared by one Scenario DSL.

    FE analysis is project-wide.  A Component Contract is scenario-wide; copying the
    full FE input inventory here made login profiles contain deposit/payment/signup
    values.  DSL declarations are the scope boundary and FE data only enriches a
    matching declaration with code Evidence.
    """
    scoped = {
        "commitSha": frontend.get("commitSha"),
        "events": list(frontend.get("events") or []),
        "validations": list(frontend.get("validations") or []),
        "inputs": [],
        "screens": [],
    }
    source = scenario.get("source") or {}
    destination = scenario.get("destination") or {}
    wanted_routes = {
        str(source.get("route") or "").rstrip("/"),
        str(destination.get("routePattern") or "").rstrip("/"),
    } - {"", "missing_data"}
    scoped["screens"] = [
        item
        for item in (frontend.get("screens") or [])
        if str(item.get("route") or "").rstrip("/") in wanted_routes
    ]

    analysed = list(frontend.get("inputs") or [])
    ui_elements = list((scenario.get("caseAnalysis") or {}).get("uiElements") or [])
    for index, declared in enumerate(scenario.get("inputs") or []):
        field = str(declared.get("name") or declared.get("field") or "").strip()
        if not field:
            continue
        locator = declared.get("locator") or {}
        selector = str(locator.get("value") or "")
        ui_hit = next(
            (
                item
                for item in ui_elements
                if _normal_field(item.get("field") or item.get("name")) == _normal_field(field)
                or (selector and str(item.get("selector") or "") == selector)
            ),
            {},
        )
        fe_hit = next(
            (
                item
                for item in analysed
                if _normal_field(item.get("name") or item.get("label") or item.get("testId"))
                == _normal_field(field)
                or (selector and selector.lstrip("#") in {
                    str(item.get("id") or ""),
                    str((item.get("constraints") or {}).get("id") or ""),
                    str(item.get("testId") or ""),
                })
            ),
            {},
        )
        constraints = dict(fe_hit.get("constraints") or {})
        constraints.update(dict(declared.get("constraints") or {}))
        if selector.startswith("#") and re.fullmatch(r"#[A-Za-z_][\w:-]*", selector):
            constraints.setdefault("id", selector[1:])
        scoped["inputs"].append(
            {
                **fe_hit,
                "id": fe_hit.get("id") or f"scenario-input-{index + 1}",
                "name": field,
                "scenarioField": field,
                "label": fe_hit.get("label") or ui_hit.get("name") or field,
                "kind": ui_hit.get("kind") or (
                    "select" if str(ui_hit.get("type") or "").lower() == "select" else "input"
                ),
                "required": bool(declared.get("required")),
                "constraints": constraints,
            }
        )
    return scoped


def _scenario_outputs(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Build only outputs that have a directly verifiable runtime contract.

    ``bindings.beforeAfter`` is a list of UI observation selectors, not a
    backend-response mapping.  Treating those selectors as synthetic output
    fields made successful browser journeys look PARTIAL because no imaginary
    ``$.screenStateChanged`` value could exist in the backend response.  The
    selectors remain available in the scenario/evidence policy and are
    verified by the browser steps themselves.
    """
    # Navigation is verified by BindingValidationService's hard technical route
    # assertion against the actually observed browser URL.  It is not a JSON
    # response field and must not be added to the cross-layer output contract.
    return []


def build_contract(
    frontend: dict[str, Any],
    backend: dict[str, Any] | None = None,
    *,
    graph: dict[str, Any] | None = None,
    adapter: dict[str, Any] | None = None,
    scenario_id: str | None = None,
    service_id: str = "customer-search",
    project_id: str | None = None,
    design_hints: dict[str, Any] | None = None,
    force_unstable_css_for: str | None = None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    backend = backend or {}
    graph = graph or {}
    adapter = adapter or {}
    scenario = scenario or {}

    if scenario:
        frontend = _scenario_scoped_frontend(frontend, scenario)

    screens = frontend.get("screens") or []
    screen_a = next((s for s in screens if "search" in str(s.get("route") or "").lower()), None)
    screen_b = next((s for s in screens if ":customer" in str(s.get("route") or "").lower()), None)

    inputs, actions, warn_a, mismatches = _build_inputs(
        frontend, backend, adapter, design_hints=design_hints
    )
    # optional test hook: force unstable locator on a field
    if force_unstable_css_for:
        for item in inputs:
            if item["field"] == force_unstable_css_for:
                item["locator"] = _choose_locator({}, force_css="div > form > input:nth-child(2)")
                item["reviewRequired"] = True
                warn_a.append(
                    {
                        "kind": "unstable_locator",
                        "field": item["field"],
                        "message": "Forced CSS locator for test; not auto-confirmed",
                        "confirmed": False,
                    }
                )

    if scenario:
        outputs, warn_b, missing = _scenario_outputs(scenario), [], []
    else:
        outputs, warn_b, missing = _build_outputs(frontend, backend, graph, adapter)
    warnings = warn_a + warn_b

    contract_id = f"CC-{uuid4().hex[:12]}"
    return {
        "schemaVersion": "component-contract/v1",
        "contractId": contract_id,
        "scenarioId": scenario_id,
        "serviceId": service_id,
        "projectId": project_id,
        "sourceRefs": {
            "frontendCommit": frontend.get("commitSha"),
            "backendCommit": backend.get("commitSha"),
            "graphId": graph.get("graphId"),
            "adapterId": adapter.get("adapterId"),
        },
        "screenA": {
            "name": (scenario.get("source") or {}).get("screen") or (screen_a or {}).get("name") or "missing_data",
            "route": (scenario.get("source") or {}).get("route") or (screen_a or {}).get("route") or "missing_data",
        },
        "screenB": {
            "name": (scenario.get("destination") or {}).get("screen") or (screen_b or {}).get("name") or "missing_data",
            "routePattern": (scenario.get("destination") or {}).get("routePattern") or (screen_b or {}).get("route") or "missing_data",
        },
        "inputs": inputs,
        "outputs": outputs,
        "actions": actions,
        "validationMismatches": mismatches,
        "warnings": warnings,
        "screenshotHooks": _screenshot_hooks(adapter),
        "adapterRef": adapter.get("adapterId"),
        "missing_data": missing,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = _load_json(args.input)
    frontend = payload.get("frontendAnalysis") or _load_json(payload.get("frontendAnalysisPath"))
    backend = payload.get("backendAnalysis") or _load_json(payload.get("backendAnalysisPath"))
    graph = payload.get("interactionGraph") or _load_json(payload.get("interactionGraphPath"))
    adapter = payload.get("adapter") or _load_adapter(payload.get("adapterPath"))

    if not frontend:
        print("frontendAnalysis required", file=sys.stderr)
        return 2

    result = build_contract(
        frontend,
        backend,
        graph=graph,
        adapter=adapter,
        scenario_id=payload.get("scenarioId"),
        service_id=str(payload.get("serviceId") or "customer-search"),
        project_id=payload.get("projectId"),
        design_hints=payload.get("designHints"),
        force_unstable_css_for=payload.get("forceUnstableCssFor"),
        scenario=payload.get("scenarioDefinition"),
    )

    artifact = payload.get("artifactPath")
    if artifact:
        out_file = Path(str(artifact)).expanduser().resolve()
    else:
        out_file = Path(args.output).expanduser().resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    wrapper = {
        "ok": True,
        "skill": "component_contract",
        "tool": "build_contract",
        "artifactPath": str(out_file),
        "contractId": result["contractId"],
        "counts": {
            "inputs": len(result["inputs"]),
            "outputs": len(result["outputs"]),
            "actions": len(result.get("actions") or []),
            "warnings": len(result["warnings"]),
            "mismatches": len(result.get("validationMismatches") or []),
        },
        "result": result,
    }
    Path(args.output).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(wrapper, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "contractId": result["contractId"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
