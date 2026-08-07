from __future__ import annotations

import json
from typing import Any

# Keys (case-insensitive) that must never be persisted in clear text.
SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "set-cookie",
    "apikey",
    "api_key",
    "accesskey",
    "refresh",
    "ssn",
    "resident",
)

DEFAULT_MAX_BYTES = 8_192
MASK = "***"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "").replace("_", "")
    for frag in SENSITIVE_KEY_FRAGMENTS:
        compact = frag.replace("-", "").replace("_", "")
        if compact in lowered:
            return True
    return False


def mask_payload(
    value: Any,
    *,
    path: str = "",
    masked: list[str] | None = None,
) -> Any:
    """Recursively mask sensitive fields. Mutates `masked` with dotted paths."""
    if masked is None:
        masked = []
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            child = f"{path}.{k}" if path else str(k)
            if _is_sensitive_key(str(k)):
                out[str(k)] = MASK
                masked.append(child)
            else:
                out[str(k)] = mask_payload(v, path=child, masked=masked)
        return out
    if isinstance(value, list):
        return [
            mask_payload(item, path=f"{path}[{idx}]", masked=masked)
            for idx, item in enumerate(value)
        ]
    return value


def truncate_payload(
    value: Any,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[Any, bool, dict[str, Any] | None]:
    """Truncate JSON-serializable payload; return (value, truncated, meta)."""
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raw = str(value)
    encoded = raw.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False, None
    clipped = encoded[:max_bytes].decode("utf-8", errors="ignore")
    meta = {
        "originalBytes": len(encoded),
        "keptBytes": len(clipped.encode("utf-8")),
        "maxBytes": max_bytes,
    }
    return {"_truncated": True, "preview": clipped}, True, meta


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Drop or mask sensitive transport headers before evidence persist."""
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if _is_sensitive_key(k):
            out[k] = MASK
        else:
            out[k] = v
    return out


def prepare_body(
    body: Any,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[Any | None, list[str], bool, dict[str, Any] | None]:
    if body is None:
        return None, [], False, None
    masked_fields: list[str] = []
    masked = mask_payload(body, masked=masked_fields)
    truncated_value, truncated, meta = truncate_payload(masked, max_bytes=max_bytes)
    return truncated_value, masked_fields, truncated, meta
