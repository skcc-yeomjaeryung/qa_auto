from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


NULL_MARKERS = {"", "null", "none", "nil", "n/a", "-"}


def normalize_value(
    value: Any,
    rules: list[str] | None = None,
    *,
    enum_labels: dict[str, str] | None = None,
) -> Any:
    """Apply deterministic Phase 11 normalization rules in declared order."""
    rules = [str(rule).lower() for rule in (rules or [])]
    current = value
    for rule in rules:
        if rule in {"null_empty", "null-empty", "empty_as_null"}:
            current = _null_empty(current)
        elif current is None:
            continue
        elif rule == "trim":
            current = str(current).strip()
        elif rule in {"case", "lowercase", "lower"}:
            current = str(current).casefold()
        elif rule in {"uppercase", "upper"}:
            current = str(current).upper()
        elif rule in {"number", "number_format", "number-format"}:
            current = _number(current, currency=False)
        elif rule in {"currency", "comma", "currency_comma", "currency-comma"}:
            current = _number(current, currency=True)
        elif rule in {"date", "datetime", "timezone", "date_timezone", "date-timezone"}:
            current = _datetime_utc(current)
        elif rule in {"enum", "enum_label", "enum-label"}:
            current = (enum_labels or {}).get(str(current), current)
    return current


def values_equal(
    expected: Any,
    actual: Any,
    rules: list[str] | None = None,
    *,
    enum_labels: dict[str, str] | None = None,
) -> tuple[bool, Any, Any]:
    left = normalize_value(expected, rules, enum_labels=enum_labels)
    right = normalize_value(actual, rules, enum_labels=enum_labels)
    return left == right, left, right


def _null_empty(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().casefold() in NULL_MARKERS:
        return None
    return value


def _number(value: Any, *, currency: bool) -> Any:
    if isinstance(value, bool):
        return value
    raw = str(value).strip()
    raw = raw.replace(",", "")
    if currency:
        raw = re.sub(r"[^\d+\-.]", "", raw)
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError):
        return value
    normalized = number.normalize()
    if normalized == normalized.to_integral():
        return int(normalized)
    return format(normalized, "f")


def _datetime_utc(value: Any) -> Any:
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
