#!/usr/bin/env python3
"""health_ping / ping — deterministic echo Tool (no LLM)."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    payload = {}
    if input_path.is_file():
        payload = json.loads(input_path.read_text(encoding="utf-8") or "{}")

    result = {
        "ok": True,
        "skill": "health_ping",
        "tool": "ping",
        "echo": payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
