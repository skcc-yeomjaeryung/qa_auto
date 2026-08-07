#!/usr/bin/env python3
"""input_recommend / recommend — deterministic Input recommendations + profile cases."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

GENERATOR_VERSION = "input-recommend/1.0.0"

SOURCE_RANK = {
    "fixture": 1,
    "existing_test": 2,
    "schema_validation": 3,
    "test_data_sheet": 4,
    "best_practice_catalog": 5,
    "llm_hint": 6,
    "design_spec_hint": 6,
    "derived_synthetic": 7,
    "user": 8,
}

PII_FIELD_HINTS = ("password", "secret", "token", "ssn", "resident", "phone", "email")
CREDENTIAL_FIELD_HINTS = (
    "password",
    "passwd",
    "pwd",
    "username",
    "loginid",
    "login_id",
    "비밀번호",
    "로그인아이디",
)
CUSTOMER_FIELD_HINTS = ("customerid", "customerno", "customernumber", "custid", "custno")


def _load_json(src: Any) -> dict[str, Any] | list[Any]:
    if isinstance(src, (dict, list)):
        return src
    if not src:
        return {}
    path = Path(str(src)).expanduser().resolve()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _mask_value(field: str, value: Any) -> tuple[Any, str | None, bool]:
    text = "" if value is None else str(value)
    lowered = field.lower()
    # 빈 값(negative path)은 가리지 않는다 — 가리면 "***"가 실제 입력값처럼 채워진다.
    if text and any(h in lowered for h in PII_FIELD_HINTS):
        return "***", "***", True
    # never invent real PII; synthetic CUS-* stays as-is
    return value, text if text else "(empty)", False


def _extract_pattern(contract_input: dict[str, Any], frontend: dict, backend: dict) -> str | None:
    if contract_input.get("pattern"):
        return str(contract_input["pattern"])
    for val in frontend.get("validations") or []:
        expr = str(val.get("expression") or "")
        m = re.search(r"/(\^[^/]+\$)/", expr)
        if m:
            return m.group(1)
    for dto in backend.get("requestDtos") or []:
        for f in dto.get("fields") or []:
            pat = (f.get("constraints") or {}).get("Pattern") or {}
            if isinstance(pat, dict) and pat.get("regexp"):
                return str(pat["regexp"]).replace("\\\\", "\\")
    return None


def _accepts_customer_id(field: str, pattern: str | None) -> bool:
    """고객 식별자 fixture(CUS-####)를 이 필드에 붙일 근거가 있는가.

    Without this gate every declared field (Deposit Amount, Username, uuid …) received
    the customer fixture and surfaced as a confirmed value, which is estimation. Either
    the analysed pattern must accept a CUS id, or the field name must name a customer.
    """
    if pattern:
        try:
            return bool(re.match(pattern, "CUS-1001"))
        except re.error:
            return False
    lowered = re.sub(r"[^a-z]", "", field.lower())
    return any(hint in lowered for hint in CUSTOMER_FIELD_HINTS)


def _dedupe_inputs(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 필드가 Contract에 두 번 선언돼도 후보·기본값을 중복 생성하지 않는다."""
    merged: dict[str, dict[str, Any]] = {}
    for inp in inputs:
        field = str(inp.get("field") or inp.get("name") or "customerId")
        existing = merged.get(field)
        if existing is None:
            merged[field] = {**inp, "field": field}
            continue
        existing["required"] = bool(existing.get("required")) or bool(inp.get("required"))
        existing["reviewRequired"] = bool(existing.get("reviewRequired")) or bool(
            inp.get("reviewRequired")
        )
        for key, value in inp.items():
            existing.setdefault(key, value)
    return list(merged.values())


# 필드 이름 → 합성 테스트값 규칙. 자동화 도구는 "데이터가 없어서 못 한다"가 아니라
# 분석된 필드명·타입으로 실행 가능한 값을 만들어 붙이고, 그 값이 합성값임을 라벨링한다.
# 값 결정은 script/rule (재현 가능) — LLM은 설명·후보 보조만 담당한다.
SYNTHETIC_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("email", "mail", "이메일"), "qa.auto+test@example.com", "이메일 형식 필드"),
    (("firstname", "이름"), "Qa", "이름 필드"),
    (("lastname", "성"), "Tester", "성 필드"),
    (("fullname", "name", "성명"), "QA Tester", "성명 필드"),
    (("routingnum", "routingnumber", "은행코드"), "883745000", "9자리 라우팅 번호 필드"),
    (("accountnum", "accountnumber", "계좌"), "1234567890", "계좌번호 형식 필드"),
    (("cardnum", "cardnumber", "카드번호"), "4242424242424242", "카드번호 형식 필드"),
    (("amount", "금액", "price", "balance"), "1000", "금액 필드"),
    (("quantity", "count", "수량"), "1", "수량 필드"),
    (("zip", "postal", "우편"), "06236", "우편번호 필드"),
    (("address", "주소"), "1 Test Street, Seoul", "주소 필드"),
    (("phone", "mobile", "tel", "전화"), "010-0000-0000", "전화번호 필드"),
    (("birth", "dob", "생년"), "1990-01-01", "생년월일 필드"),
    (("date", "일자", "일시"), "2026-01-01", "날짜 필드"),
    (("ssn", "resident", "주민"), "123456789", "식별번호 필드 (합성)"),
    (("label", "memo", "note", "설명", "라벨"), "QA 자동 테스트", "라벨·메모 필드"),
    (("uuid", "guid"), None, "UUID 필드"),
    (("code", "코드"), "QA001", "코드 필드"),
    (("search", "query", "keyword", "검색"), "test", "검색어 필드"),
)

BOOLEAN_HINTS = ("agree", "consent", "checked", "동의", "isactive", "enabled")
NUMERIC_TYPES = {"number", "integer", "int", "long", "double", "decimal", "float"}

# 패턴이 있는 필드는 아무 값이나 넣지 않고, 후보를 패턴에 대조해 통과하는 값만 쓴다.
PATTERN_PROBES = (
    "CUS-1001",
    "QA-0001",
    "QA001",
    "1234567890",
    "0000000001",
    "1",
    "100",
    "qa.auto+test@example.com",
    "qatester01",
    "2026-01-01",
    "010-0000-0000",
    "true",
)


def is_sensitive_field(field: str) -> bool:
    """비밀번호·식별번호처럼 화면·증적에서 값을 가려야 하는 필드인가."""
    lowered = str(field).lower()
    return any(hint in lowered for hint in PII_FIELD_HINTS)


def is_connection_credential_field(field: str) -> bool:
    """로그인 계정 값은 추천/LLM이 만들지 않고 실행환경 참조만 사용한다."""
    normalized = re.sub(r"[^a-z0-9가-힣_]", "", str(field).lower())
    return any(hint in normalized for hint in CREDENTIAL_FIELD_HINTS)


def _matches(pattern: str, value: str) -> bool:
    try:
        return bool(re.match(pattern, value))
    except re.error:
        return True  # 패턴을 해석할 수 없으면 제약으로 쓰지 않는다


def _synthetic_uuid(field: str, scenario_id: str | None) -> str:
    """같은 시나리오·필드면 항상 같은 UUID — 실행 재현성을 유지한다."""
    seed = f"{scenario_id or 'SCN'}:{field}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def synthesize_value(
    contract_input: dict[str, Any],
    *,
    scenario_id: str | None = None,
    pattern: str | None = None,
) -> tuple[str, str] | None:
    """분석된 필드 정의에서 실행 가능한 합성 테스트값을 만든다.

    반환값은 (value, rationale). 만들 근거(필드명·타입·enum)가 전혀 없으면 None.
    """
    field = str(contract_input.get("field") or contract_input.get("name") or "")
    if not field:
        return None
    normalized = re.sub(r"[^a-z0-9가-힣]", "", field.lower())
    field_type = str(contract_input.get("type") or "").lower()
    enum = contract_input.get("enum")

    if isinstance(enum, list) and enum:
        return str(enum[0]), f"분석된 선택 목록의 첫 값 ({field})"

    for hints, value, reason in SYNTHETIC_RULES:
        if not any(hint in normalized for hint in hints):
            continue
        resolved = value if value is not None else _synthetic_uuid(field, scenario_id)
        if pattern and not _matches(pattern, resolved):
            break  # 이름 규칙 값이 패턴과 어긋나면 아래 패턴 후보로 넘어간다
        return resolved, f"{reason} 이름에서 유추한 합성 테스트값"

    if pattern:
        for probe in PATTERN_PROBES:
            if _matches(pattern, probe):
                return probe, f"분석된 형식 제약({pattern})을 통과하는 합성 테스트값"
        return None  # 형식을 만족하는 값을 만들 수 없으면 사람에게 넘긴다

    if any(hint in normalized for hint in BOOLEAN_HINTS) or field_type in {"boolean", "bool"}:
        return "true", f"체크·동의 성격 필드({field})로 판단한 합성값"
    if field_type in NUMERIC_TYPES:
        return "1", f"숫자 타입({field_type}) 필드로 판단한 합성값"
    if field_type in {"string", "text", ""}:
        return f"QA-{normalized[:12] or 'value'}", "필드명을 그대로 쓴 합성 문자열값"
    return None


def _values_from_existing_tests(backend: dict[str, Any], field: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    pattern = re.compile(rf'"{re.escape(field)}"\s*:\s*"([^"]*)"')
    for test in backend.get("existingTests") or []:
        file_ref = str(test.get("file") or test.get("id") or "existing_test")
        for step in test.get("steps") or []:
            raw = str(step.get("value") or "")
            # unescape common java-string escaping in analysis artifacts
            raw = raw.replace('\\"', '"').replace("\\\\", "\\")
            for m in pattern.finditer(raw):
                found.append((m.group(1), file_ref))
            # also match CUS-xxxx loose
            if field == "customerId":
                for m in re.finditer(r"CUS-\d{4}", raw):
                    found.append((m.group(0), file_ref))
                if '""' in raw or '"customerId":""' in raw.replace(" ", ""):
                    found.append(("", file_ref))
    return found


def _load_fixture_customers(catalog_root: Path) -> list[dict[str, Any]]:
    path = catalog_root / "fixtures" / "customers.json"
    data = _load_json(path)
    return data if isinstance(data, list) else []


def _load_bp_catalog(catalog_root: Path, service_id: str) -> list[dict[str, Any]]:
    path = catalog_root / "catalog" / f"{service_id}.json"
    data = _load_json(path)
    if isinstance(data, dict):
        return list(data.get("entries") or [])
    return []


def _sheet_rows(sheet: dict[str, Any] | None, service_id: str) -> list[dict[str, Any]]:
    if not sheet:
        return []
    rows = []
    for row in sheet.get("rows") or []:
        key = str(row.get("serviceOrTxnId") or "")
        if key and key not in {service_id, "customer-search", "*"}:
            continue
        rows.append(row)
    return rows


def _category_for_value(
    value: str,
    pattern: str | None,
    fixture_ids: set[str],
    restricted_ids: set[str],
) -> str:
    if value == "":
        return "missing_required"
    if pattern:
        try:
            if not re.match(pattern, value):
                return "invalid_format"
        except re.error:
            pass
    if value in restricted_ids:
        return "business_state"
    if value.startswith("CUS-") and value not in fixture_ids and value.endswith("9999"):
        return "not_found"
    if value in {"CUS-0000", "CUS-9998"}:
        return "boundary"
    if value in fixture_ids:
        # CUS-2002 may be both fixture and business_state
        if value in restricted_ids:
            return "business_state"
        return "happy_path"
    if value.startswith("CUS-") and value not in fixture_ids:
        return "not_found"
    return "happy_path"


def recommend_inputs(
    *,
    contract: dict[str, Any],
    frontend: dict[str, Any] | None = None,
    backend: dict[str, Any] | None = None,
    catalog_root: Path | None = None,
    sheet: dict[str, Any] | None = None,
    service_id: str = "customer-search",
    scenario_id: str | None = None,
    project_id: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    frontend = frontend or {}
    backend = backend or {}
    catalog_root = catalog_root or (
        Path(__file__).resolve().parents[5] / "packages" / "test-data-catalog"
    )
    # parents: script -> input_recommend -> skills -> app -> backend -> repo
    # Path(__file__) = .../backend/app/skills/input_recommend/script/recommend.py
    # parents[0]=script [1]=input_recommend [2]=skills [3]=app [4]=backend [5]=repo
    if not catalog_root.is_dir():
        catalog_root = Path(__file__).resolve().parents[5] / "packages" / "test-data-catalog"

    fixtures = _load_fixture_customers(catalog_root)
    bp_entries = _load_bp_catalog(catalog_root, service_id)
    fixture_ids = {str(f.get("customerId")) for f in fixtures}
    restricted_ids = {
        str(f.get("customerId"))
        for f in fixtures
        if str(f.get("riskLevel") or "").upper() in {"HIGH", "RESTRICTED"}
        or str(f.get("status") or "").upper() in {"RESTRICTED", "REVIEW_REQUIRED"}
    }
    # seed also marks CUS-2002 from catalog
    restricted_ids.add("CUS-2002")

    recommendations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    defaults: dict[str, Any] = {}

    inputs = _dedupe_inputs(list(contract.get("inputs") or []))
    if not inputs and service_id == "customer-search":
        inputs = [{"field": "customerId", "required": True, "pattern": r"^CUS-\d{4}$"}]

    for inp in inputs:
        field = str(inp.get("field") or "customerId")
        if is_connection_credential_field(field):
            conflicts.append(
                {
                    "kind": "environment_credential_required",
                    "field": field,
                    "message": "로그인 계정은 environment.loginId/loginSecret만 사용하며 추천값을 생성하지 않습니다.",
                }
            )
            continue
        pattern = _extract_pattern(inp, frontend, backend)
        customer_id_field = _accepts_customer_id(field, pattern)
        candidates: dict[str, dict[str, Any]] = {}

        def add_candidate(
            value: str,
            category: str | None,
            source: str,
            ref: str,
            rationale: str,
            *,
            review_required: bool = False,
            frequency: int | None = None,
            expected_path: str | None = None,
            keep_value: bool = False,
        ) -> None:
            masked_val, display, masked = _mask_value(field, value)
            if keep_value:
                # 합성값은 실행에 실제로 채워야 하므로 값을 남기고 표시만 가린다.
                masked_val = value
            cat = category or _category_for_value(str(value), pattern, fixture_ids, restricted_ids)
            key = f"{field}|{value}|{cat}"
            evidence = {
                "source": source,
                "rank": SOURCE_RANK.get(source, 99),
                "ref": ref,
                "frequency": frequency,
                "detail": rationale,
            }
            if key not in candidates:
                candidates[key] = {
                    "field": field,
                    "value": masked_val if masked else value,
                    "displayValue": display,
                    "category": cat,
                    "expectedPath": expected_path,
                    "rationale": rationale,
                    "sources": [evidence],
                    "selectedByDefault": False,
                    "reviewRequired": review_required,
                    "uncertain": review_required or source in {"test_data_sheet", "llm_hint", "design_spec_hint"},
                    "masked": masked,
                    "_rank": evidence["rank"],
                }
            else:
                candidates[key]["sources"].append(evidence)
                candidates[key]["_rank"] = min(candidates[key]["_rank"], evidence["rank"])
                if frequency:
                    # bump frequency on matching source
                    pass

        # 1) Fixture — 고객 식별자 필드에만 붙인다 (그 밖은 근거 없음 → 후보 없음)
        for fx in fixtures if customer_id_field else []:
            vid = str(fx.get("customerId") or "")
            if not vid:
                continue
            add_candidate(
                vid,
                None,
                "fixture",
                "packages/test-data-catalog/fixtures/customers.json",
                f"Fixture synthetic customer {vid}",
                expected_path="detail_success" if vid == "CUS-1001" else "detail_restricted",
            )

        # 2) Existing tests
        test_vals = _values_from_existing_tests(backend, field)
        freq = Counter(v for v, _ in test_vals)
        for value, ref in test_vals:
            add_candidate(
                value,
                None,
                "existing_test",
                ref,
                f"Hard-coded value in existing test ({freq[value]}×)",
                frequency=freq[value],
            )

        # 3) Schema/validation derived (invalid / missing / boundary) — not random ids
        if inp.get("required"):
            add_candidate(
                "",
                "missing_required",
                "schema_validation",
                "contract.required",
                "Required field empty for negative path",
                expected_path="validation_error",
            )
        if pattern and customer_id_field:
            add_candidate(
                "CUS-AB12",
                "invalid_format",
                "schema_validation",
                f"pattern:{pattern}",
                "Invalid format against Zod/Bean pattern",
                expected_path="validation_error",
            )
            add_candidate(
                "CUS-0000",
                "boundary",
                "schema_validation",
                f"pattern:{pattern}",
                "Boundary zero-padded id matching pattern",
                expected_path="detail_or_not_found",
                review_required=True,
            )

        # 4) Test data sheet (reviewRequired if not approved)
        for row in _sheet_rows(sheet, service_id):
            req = row.get("request") or {}
            if field not in req:
                continue
            approved = str(row.get("approvalStatus") or "") == "approved"
            add_candidate(
                str(req[field]),
                None,
                "test_data_sheet",
                str(row.get("rowId")),
                "Test Data Sheet row (auxiliary)",
                review_required=not approved,
            )
            if not approved:
                conflicts.append(
                    {
                        "kind": "sheet_unapproved",
                        "field": field,
                        "rowId": row.get("rowId"),
                        "message": "Sheet row not approved — reviewRequired",
                    }
                )

        # 5) Best practice catalog
        for entry in bp_entries:
            if str(entry.get("field")) != field:
                continue
            add_candidate(
                str(entry.get("value")),
                str(entry.get("category")),
                "best_practice_catalog",
                str(entry.get("entryId")),
                str(entry.get("rationale") or "Best Practice Catalog"),
                expected_path=entry.get("expectedPath"),
            )

        # 6) 합성값 — 여기까지 실행 가능한 값이 하나도 없으면 필드 정의로 값을 만든다.
        #    「데이터가 없어 못 채웠다」로 끝내면 테스터가 손으로 다 넣어야 하고 플로우도 비어 있다.
        has_runnable = any(str(c.get("value") or "") for c in candidates.values())
        if not has_runnable:
            synthesized = synthesize_value(inp, scenario_id=scenario_id, pattern=pattern)
            if synthesized:
                value, reason = synthesized
                add_candidate(
                    value,
                    "happy_path",
                    "derived_synthetic",
                    f"contract.inputs[{field}]",
                    reason,
                    expected_path="happy_path",
                    keep_value=True,
                )
                key = f"{field}|{value}|happy_path"
                if key in candidates:
                    candidates[key]["synthesized"] = True
                    candidates[key]["uncertain"] = True

        # Sort by source rank then category preference
        cat_order = {
            "happy_path": 0,
            "business_state": 1,
            "not_found": 2,
            "invalid_format": 3,
            "missing_required": 4,
            "boundary": 5,
            "pairwise": 6,
        }
        ordered = sorted(
            candidates.values(),
            key=lambda c: (c["_rank"], cat_order.get(c["category"], 9), str(c["value"])),
        )
        for item in ordered:
            item.pop("_rank", None)
            recommendations.append(item)

        # Default for interactive = best happy_path (or first)
        happy = next((r for r in ordered if r["category"] == "happy_path"), None)
        pick = happy or (ordered[0] if ordered else None)
        if pick:
            pick["selectedByDefault"] = True
            defaults[field] = pick["value"]

    # Determinism stamp
    # 시나리오를 포함해야 한다. 같은 계약을 쓰는 두 시나리오가 같은 id를 만들면
    # 뒤에 저장된 추천이 앞의 것을 덮어써 한쪽 시나리오는 추천을 잃는다.
    material = json.dumps(
        {
            "defaults": defaults,
            "n": len(recommendations),
            "seed": seed,
            "scenarioId": scenario_id,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(f"{seed}:{material}".encode()).hexdigest()[:12]

    return {
        "schemaVersion": "input-recommendation/v1",
        "recommendationId": f"REC-{digest}",
        "scenarioId": scenario_id,
        "serviceId": service_id,
        "projectId": project_id,
        "contractId": contract.get("contractId"),
        "defaults": defaults,
        "requiresInput": bool(inputs),
        "recommendations": recommendations,
        "conflicts": conflicts,
        "generator": {
            "version": GENERATOR_VERSION,
            "seed": seed,
            "policy": {
                "excludeDestructive": True,
                "allowRandomIdentifiers": False,
                "pairwise": True,
            },
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def generate_profile_cases(
    recommendation: dict[str, Any],
    *,
    budget: int = 8,
    categories: list[str] | None = None,
    unresolved_policy: str = "reviewRequired",
    seed: int = 42,
    pairwise: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not recommendation.get("recommendations") and not recommendation.get("requiresInput", False):
        return (
            [
                {
                    "caseId": f"CASE-no-input-{seed}-1",
                    "category": "happy_path",
                    "inputs": {},
                    "expectedPath": "screen_observation",
                    "reviewRequired": False,
                    "sources": [
                        {
                            "source": "scenario_contract",
                            "rank": 1,
                            "ref": "contract.inputs=[]",
                            "detail": "이 시나리오는 사용자 입력 없이 화면·동작을 관측합니다.",
                        }
                    ],
                }
            ],
            {"happy_path": 1},
        )

    allowed = set(
        categories
        or [
            "happy_path",
            "business_state",
            "not_found",
            "invalid_format",
            "missing_required",
            "boundary",
        ]
    )
    # one case per category (pairwise-style reduction for single-field)
    by_cat: dict[str, dict[str, Any]] = {}
    for rec in recommendation.get("recommendations") or []:
        cat = str(rec.get("category"))
        if cat not in allowed:
            continue
        if rec.get("uncertain") and unresolved_policy == "skip":
            continue
        # prefer higher-frequency / fixture
        ranks = [s.get("rank", 99) for s in rec.get("sources") or []]
        best = min(ranks) if ranks else 99
        prev = by_cat.get(cat)
        if not prev or best < prev["_rank"]:
            by_cat[cat] = {**rec, "_rank": best}

    ordered_cats = [
        "happy_path",
        "business_state",
        "not_found",
        "invalid_format",
        "missing_required",
        "boundary",
    ]
    cases: list[dict[str, Any]] = []
    for cat in ordered_cats:
        if cat not in by_cat:
            continue
        if len(cases) >= budget:
            break
        rec = by_cat[cat]
        case = {
            "caseId": f"CASE-{cat}-{seed}-{len(cases)+1}",
            "category": cat,
            "inputs": {} if rec.get("omitFromProfile") else {rec["field"]: rec["value"]},
            "expectedPath": rec.get("expectedPath"),
            "reviewRequired": bool(rec.get("reviewRequired") or rec.get("uncertain")),
            "sources": rec.get("sources") or [],
        }
        if unresolved_policy == "usePolicyDefault" and case["reviewRequired"]:
            case["reviewRequired"] = False
            case["inputs"] = dict(recommendation.get("defaults") or case["inputs"])
        cases.append(case)

    # optional pairwise stamp (single field → same as category set)
    if pairwise and len(cases) > budget:
        cases = cases[:budget]

    counts: dict[str, int] = {}
    for c in cases:
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    return cases, counts


def build_input_profile(
    recommendation: dict[str, Any],
    *,
    scenario_id: str,
    name: str = "customer-search batch",
    budget: int = 8,
    categories: list[str] | None = None,
    unresolved_policy: str = "reviewRequired",
    seed: int = 42,
    status: str = "DRAFT",
) -> dict[str, Any]:
    cases, counts = generate_profile_cases(
        recommendation,
        budget=budget,
        categories=categories,
        unresolved_policy=unresolved_policy,
        seed=seed,
    )
    return {
        "schemaVersion": "input-profile/v1",
        "profileId": f"IP-{uuid4().hex[:12]}",
        "scenarioId": scenario_id,
        "serviceId": recommendation.get("serviceId") or "customer-search",
        "projectId": recommendation.get("projectId"),
        "name": name,
        "version": "1",
        "status": status,
        "policy": {
            "budget": budget,
            "unresolvedPolicy": unresolved_policy,
            "excludeDestructive": True,
            "seed": seed,
            "categories": categories
            or [
                "happy_path",
                "business_state",
                "not_found",
                "invalid_format",
                "missing_required",
                "boundary",
            ],
            "pairwise": True,
        },
        "cases": cases,
        "categoryCounts": counts,
        "approvedAt": None,
        "approvedBy": None,
        "recommendationId": recommendation.get("recommendationId"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = _load_json(args.input)
    if not isinstance(payload, dict):
        print("input must be object", file=sys.stderr)
        return 2

    contract = payload.get("componentContract") or _load_json(payload.get("componentContractPath"))
    if not isinstance(contract, dict) or not contract:
        print("componentContract required", file=sys.stderr)
        return 2

    frontend = payload.get("frontendAnalysis") or _load_json(payload.get("frontendAnalysisPath"))
    backend = payload.get("backendAnalysis") or _load_json(payload.get("backendAnalysisPath"))
    sheet = payload.get("testDataSheet") or _load_json(payload.get("testDataSheetPath"))
    catalog = payload.get("catalogRoot")
    seed = int(payload.get("seed") or 42)

    result = recommend_inputs(
        contract=contract,
        frontend=frontend if isinstance(frontend, dict) else {},
        backend=backend if isinstance(backend, dict) else {},
        catalog_root=Path(catalog) if catalog else None,
        sheet=sheet if isinstance(sheet, dict) else None,
        service_id=str(payload.get("serviceId") or contract.get("serviceId") or "customer-search"),
        scenario_id=payload.get("scenarioId"),
        project_id=payload.get("projectId"),
        seed=seed,
    )

    profile = None
    if payload.get("buildProfile"):
        profile = build_input_profile(
            result,
            scenario_id=str(payload.get("scenarioId") or "SCN-unknown"),
            name=str(payload.get("profileName") or "auto profile"),
            budget=int(payload.get("budget") or 8),
            unresolved_policy=str(payload.get("unresolvedPolicy") or "reviewRequired"),
            seed=seed,
        )

    artifact = payload.get("artifactPath")
    if artifact:
        out_file = Path(str(artifact)).expanduser().resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    wrapper = {
        "ok": True,
        "skill": "input_recommend",
        "tool": "recommend",
        "recommendationId": result["recommendationId"],
        "counts": {
            "recommendations": len(result["recommendations"]),
            "conflicts": len(result.get("conflicts") or []),
        },
        "result": result,
        "profile": profile,
        "artifactPath": str(artifact) if artifact else None,
    }
    Path(args.output).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(wrapper, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "recommendationId": result["recommendationId"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
