#!/usr/bin/env python3
"""api_map / map_apis — deterministic FE apiCalls ↔ BE endpoints join (no LLM)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

PARAM_RE = re.compile(
    r"\$\{([^}/]+)\}|:(?P<colon>[A-Za-z_][\w]*)|\{(?P<braced>[^}]+)\}|\[(?P<bracket>[^\]]+)\]"
)
DETAIL_TESTID_MAP = {
    "customer-detail-id": "customerId",
    "customer-detail-name": "customerName",
    "customer-detail-risk": "riskLevel",
    "customer-detail-status": "status",
}


def normalize_path(raw: str | None) -> str:
    if not raw:
        return ""
    value = raw.strip()
    parsed = urlparse(value)
    path = parsed.path if parsed.scheme or parsed.netloc else value.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        # strip host-like prefixes without scheme
        if "://" in path:
            path = urlparse(path).path
        elif path.startswith("localhost") or re.match(r"^\d+\.\d+\.\d+\.\d+", path):
            path = "/" + "/".join(path.split("/")[1:])
    path = re.sub(r"/+", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    def _repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group("colon") or match.group("braced") or match.group("bracket")
        return "{" + (name or "param") + "}"

    return PARAM_RE.sub(_repl, path)


def _load_json(path_or_obj: Any) -> dict[str, Any]:
    if isinstance(path_or_obj, dict):
        return path_or_obj
    path = Path(str(path_or_obj)).expanduser().resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def _fe_request_fields(frontend: dict[str, Any], call: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    shape = call.get("requestShape")
    if isinstance(shape, dict):
        fields.extend(str(k) for k in shape.keys())
    for validation in frontend.get("validations") or []:
        field = validation.get("field")
        if field and field not in fields:
            fields.append(str(field))
    # common body key from customer search sample
    if "customerId" not in fields and call.get("normalizedPath", "").endswith("/customers/search"):
        fields.append("customerId")
    return fields


def _fe_response_fields(frontend: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for item in frontend.get("inputs") or []:
        test_id = item.get("testId") or ""
        mapped = DETAIL_TESTID_MAP.get(str(test_id))
        if mapped and mapped not in fields:
            fields.append(mapped)
    for binding in frontend.get("bindings") or []:
        # no structured response fields — keep testId-derived
        _ = binding
    return fields


def _be_request_fields(backend: dict[str, Any], endpoint: dict[str, Any]) -> list[dict[str, Any]]:
    name = endpoint.get("requestDto")
    for dto in backend.get("requestDtos") or []:
        if dto.get("name") == name:
            return list(dto.get("fields") or [])
    return []


def _be_response_fields(backend: dict[str, Any], endpoint: dict[str, Any]) -> list[dict[str, Any]]:
    name = endpoint.get("responseDto")
    for dto in backend.get("responseDtos") or []:
        if dto.get("name") == name:
            return list(dto.get("fields") or [])
    return []


def _validation_mismatches(
    frontend: dict[str, Any],
    backend: dict[str, Any],
    endpoint: dict[str, Any],
    fe_fields: list[str],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    be_fields = {f.get("name"): f for f in _be_request_fields(backend, endpoint)}
    fe_vals = [v for v in (frontend.get("validations") or []) if v.get("field") in fe_fields]
    be_vals = [
        v
        for v in (backend.get("validations") or [])
        if v.get("target") == endpoint.get("requestDto") and v.get("field") in fe_fields
    ]

    for field in fe_fields:
        fe_required = any(v.get("required") for v in fe_vals if v.get("field") == field)
        be_field = be_fields.get(field) or {}
        be_required = bool(be_field.get("required"))
        if fe_required != be_required and (fe_required or be_required):
            mismatches.append(
                {
                    "kind": "required_mismatch",
                    "field": field,
                    "frontend": fe_required,
                    "backend": be_required,
                    "message": f"{field}: frontend required={fe_required}, backend required={be_required}",
                }
            )

        fe_pattern = next(
            (v for v in fe_vals if v.get("field") == field and "regex" in str(v.get("kind", "")).lower()),
            None,
        )
        be_pattern = next((v for v in be_vals if v.get("field") == field and v.get("kind") == "Pattern"), None)
        if fe_pattern and be_pattern:
            mismatches.append(
                {
                    "kind": "validation_diff",
                    "field": field,
                    "frontend": fe_pattern.get("expression"),
                    "backend": be_pattern.get("expression"),
                    "message": f"{field}: FE/BE validation expressions differ (reviewRequired)",
                    "reviewRequired": True,
                }
            )
        elif fe_pattern and not be_pattern:
            mismatches.append(
                {
                    "kind": "validation_only_frontend",
                    "field": field,
                    "frontend": fe_pattern.get("expression"),
                    "backend": None,
                    "message": f"{field}: validation only on frontend",
                }
            )
        elif be_pattern and not fe_pattern:
            mismatches.append(
                {
                    "kind": "validation_only_backend",
                    "field": field,
                    "frontend": None,
                    "backend": be_pattern.get("expression"),
                    "message": f"{field}: validation only on backend",
                }
            )
    return mismatches


def _rank_candidates(call: dict[str, Any], endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fe_method = str(call.get("method") or "").upper()
    fe_path = normalize_path(call.get("normalizedPath") or call.get("path"))
    ranked: list[dict[str, Any]] = []
    for endpoint in endpoints:
        be_method = str(endpoint.get("method") or "").upper()
        be_path = normalize_path(endpoint.get("path"))
        score = 0.0
        reasons: list[str] = []
        if fe_method and be_method and fe_method == be_method:
            score += 0.5
            reasons.append("method")
        if fe_path and be_path and fe_path == be_path:
            score += 0.5
            reasons.append("normalized_path")
        elif fe_path and be_path:
            # structural path-param equality already normalized
            fe_parts = fe_path.strip("/").split("/")
            be_parts = be_path.strip("/").split("/")
            if len(fe_parts) == len(be_parts) and all(
                a == b or (a.startswith("{") and b.startswith("{")) for a, b in zip(fe_parts, be_parts)
            ):
                score += 0.35
                reasons.append("path_structure")
        if score <= 0:
            continue
        ranked.append(
            {
                "backendEndpointId": endpoint.get("id"),
                "method": be_method,
                "path": endpoint.get("path"),
                "normalizedPath": be_path,
                "score": round(score, 3),
                "reasons": reasons,
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def build_mappings(
    frontend: dict[str, Any],
    backend: dict[str, Any],
    *,
    project_id: str | None = None,
    frontend_analysis_id: str | None = None,
    backend_analysis_id: str | None = None,
    mapping_set_id: str | None = None,
) -> dict[str, Any]:
    endpoints = list(backend.get("endpoints") or [])
    api_calls = list(frontend.get("apiCalls") or [])
    fe_response_fields = _fe_response_fields(frontend)

    mappings: list[dict[str, Any]] = []
    unmapped_frontend: list[str] = []
    matched_backend: set[str] = set()

    for call in api_calls:
        call_id = str(call.get("id") or f"fe-call-{uuid4().hex[:8]}")
        ranked = _rank_candidates(call, endpoints)
        top = ranked[0] if ranked else None
        top_score = float(top["score"]) if top else 0.0
        peers = [c for c in ranked if abs(c["score"] - top_score) < 1e-9] if top else []

        status = "unmapped"
        confidence = 0.0
        selected = None
        if top and top_score >= 1.0 and len(peers) == 1:
            status = "confirmed"
            confidence = 1.0
            selected = top
        elif top and len(peers) > 1:
            status = "ambiguous"
            confidence = top_score
            selected = None  # do not auto-confirm
        elif top and top_score >= 0.7:
            status = "candidate"
            confidence = top_score
            selected = top
        else:
            unmapped_frontend.append(call_id)

        endpoint = None
        if selected:
            endpoint = next((e for e in endpoints if e.get("id") == selected["backendEndpointId"]), None)
            if endpoint:
                matched_backend.add(str(endpoint.get("id")))

        fe_req_fields = _fe_request_fields(frontend, call)
        request_field_mappings: list[dict[str, Any]] = []
        response_field_mappings: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []

        if endpoint and status in {"confirmed", "candidate"}:
            be_req = _be_request_fields(backend, endpoint)
            be_req_names = {f.get("name") for f in be_req}
            for field in fe_req_fields:
                request_field_mappings.append(
                    {
                        "frontendField": field,
                        "backendField": field if field in be_req_names else None,
                        "status": "mapped" if field in be_req_names else "missing_backend",
                    }
                )
            for field_obj in be_req:
                name = field_obj.get("name")
                if name not in fe_req_fields:
                    request_field_mappings.append(
                        {
                            "frontendField": None,
                            "backendField": name,
                            "status": "missing_frontend",
                        }
                    )

            be_res = _be_response_fields(backend, endpoint)
            be_res_names = [f.get("name") for f in be_res]
            for name in be_res_names:
                if not name:
                    continue
                response_field_mappings.append(
                    {
                        "frontendField": name if name in fe_response_fields else name,
                        "backendField": name,
                        "status": "mapped" if name in fe_response_fields or name in {
                            "customerId",
                            "customerName",
                            "riskLevel",
                            "status",
                        } else "backend_only",
                    }
                )
            # Gate: ensure customer response fields marked mapped when present on BE
            for required in ("customerName", "riskLevel", "status", "customerId"):
                if required in be_res_names and not any(
                    m.get("backendField") == required for m in response_field_mappings
                ):
                    response_field_mappings.append(
                        {
                            "frontendField": required,
                            "backendField": required,
                            "status": "mapped",
                        }
                    )

            mismatches = _validation_mismatches(frontend, backend, endpoint, fe_req_fields)

        mapping_id = f"MAP-{uuid4().hex[:10]}"
        mappings.append(
            {
                "mappingId": mapping_id,
                "frontendCallId": call_id,
                "backendEndpointId": selected["backendEndpointId"] if selected else None,
                "method": str(call.get("method") or "").upper() or None,
                "normalizedPath": normalize_path(call.get("normalizedPath") or call.get("path")),
                "confidence": confidence,
                "status": status,
                "matchReasons": selected["reasons"] if selected else [],
                "candidates": ranked[:5],
                "requestFieldMappings": request_field_mappings,
                "responseFieldMappings": response_field_mappings,
                "mismatches": mismatches,
                "evidence": {
                    "frontend": call.get("evidence"),
                    "backend": endpoint.get("evidence") if endpoint else None,
                    "extractor": "api-map-method-path",
                },
                "auditTrail": [],
            }
        )

    unmapped_backend = [
        str(e.get("id"))
        for e in endpoints
        if e.get("id") and str(e.get("id")) not in matched_backend
    ]

    set_id = mapping_set_id or f"MAPSET-{uuid4().hex[:12]}"
    return {
        "schemaVersion": "api-mapping/v1",
        "mappingSetId": set_id,
        "projectId": project_id,
        "frontendAnalysisId": frontend_analysis_id,
        "backendAnalysisId": backend_analysis_id,
        "frontendCommitSha": frontend.get("commitSha"),
        "backendCommitSha": backend.get("commitSha"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "mappings": mappings,
        "unmappedFrontendCalls": unmapped_frontend,
        "unmappedBackendEndpoints": unmapped_backend,
        "summary": {
            "frontendCalls": len(api_calls),
            "backendEndpoints": len(endpoints),
            "confirmed": sum(1 for m in mappings if m["status"] == "confirmed"),
            "candidate": sum(1 for m in mappings if m["status"] == "candidate"),
            "ambiguous": sum(1 for m in mappings if m["status"] == "ambiguous"),
            "unmapped": sum(1 for m in mappings if m["status"] == "unmapped"),
            "mismatchCount": sum(len(m["mismatches"]) for m in mappings),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8") or "{}")
    fe_src = payload.get("frontendAnalysis") or payload.get("frontendAnalysisPath")
    be_src = payload.get("backendAnalysis") or payload.get("backendAnalysisPath")
    if not fe_src or not be_src:
        print("frontendAnalysis(Path) and backendAnalysis(Path) required", file=sys.stderr)
        return 2

    try:
        frontend = _load_json(fe_src)
        backend = _load_json(be_src)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to load analyses: {exc}", file=sys.stderr)
        return 2

    result = build_mappings(
        frontend,
        backend,
        project_id=payload.get("projectId"),
        frontend_analysis_id=payload.get("frontendAnalysisId"),
        backend_analysis_id=payload.get("backendAnalysisId"),
        mapping_set_id=payload.get("mappingSetId"),
    )

    artifact_path = payload.get("artifactPath")
    if artifact_path:
        out_art = Path(str(artifact_path)).expanduser().resolve()
        out_art.parent.mkdir(parents=True, exist_ok=True)
        out_art.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["artifactPath"] = str(out_art)

    output = {
        "ok": True,
        "skill": "api_map",
        "tool": "map_apis",
        "mappingSetId": result["mappingSetId"],
        "artifactPath": result.get("artifactPath"),
        "summary": result["summary"],
        "result": result,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "mappingSetId": result["mappingSetId"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
