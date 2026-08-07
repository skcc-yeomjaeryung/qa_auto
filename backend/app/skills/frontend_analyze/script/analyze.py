#!/usr/bin/env python3
"""frontend_analyze / analyze — ts-morph worker + Flask/Jinja UI merge (no LLM)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from extract_flask_screens import extract_flask_screens


def _backend_root() -> Path:
    # .../backend/app/skills/frontend_analyze/script/analyze.py
    return Path(__file__).resolve().parents[4]


def _write_progress(path: Path | None, completed: int, total: int) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"completed": max(0, min(total, completed)), "failed": 0, "total": total}),
        encoding="utf-8",
    )


def _read_completed(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("completed") or 0)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return 0


def _merge_flask_into(result: dict, flask: dict) -> dict:
    """Merge Jinja/Flask screens·apiCalls when ts-morph has little/no UI evidence."""
    fe_screens = list(result.get("screens") or [])
    fe_calls = list(result.get("apiCalls") or [])
    fl_screens = list(flask.get("screens") or [])
    fl_calls = list(flask.get("apiCalls") or [])

    by_route = {
        str(s.get("route")): s for s in fe_screens if isinstance(s, dict) and s.get("route")
    }
    for s in fl_screens:
        route = str(s.get("route") or "")
        if not route:
            continue
        prev = by_route.get(route)
        if not prev:
            by_route[route] = s
            continue
        # Enrich ts-morph screen with Jinja selectors when missing
        prev_inputs = prev.get("inputs") or prev.get("uiElements") or []
        new_inputs = s.get("inputs") or s.get("uiElements") or []
        if len(new_inputs) > len(prev_inputs):
            prev = {**prev, **{k: s[k] for k in ("inputs", "uiElements", "targetFile", "template") if k in s}}
            prev["evidence"] = s.get("evidence") or prev.get("evidence")
            by_route[route] = prev

    # Dedupe api calls by method+path
    call_keys: set[str] = set()
    merged_calls: list[dict] = []
    for c in fe_calls + fl_calls:
        if not isinstance(c, dict):
            continue
        key = f"{str(c.get('method') or '').upper()}|{c.get('normalizedPath') or c.get('path')}"
        if key in call_keys:
            continue
        call_keys.add(key)
        merged_calls.append(c)

    result = dict(result)
    result["screens"] = list(by_route.values())
    result["apiCalls"] = merged_calls
    result["extractor"] = "ts-morph+flask-jinja" if fe_screens else (flask.get("extractor") or "flask-jinja")
    if flask.get("inputs"):
        result["inputs"] = list(result.get("inputs") or []) + list(flask.get("inputs") or [])
    # 세션 선행조건 재료 (D-015) — 인증 뒤 동작 트리거 form · 인증 전용 요소
    if flask.get("actionForms"):
        result["actionForms"] = list(result.get("actionForms") or []) + list(flask["actionForms"])
    if flask.get("sessionMarkers"):
        result["sessionMarkers"] = list(result.get("sessionMarkers") or []) + list(
            flask["sessionMarkers"]
        )
    return result


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

    workspace = payload.get("workspacePath")
    if not workspace:
        print("workspacePath required", file=sys.stderr)
        return 2
    workspace_path = Path(str(workspace)).expanduser().resolve()
    if not workspace_path.is_dir():
        print(f"workspace not found: {workspace_path}", file=sys.stderr)
        return 2

    backend_root = _backend_root()
    repo_root = backend_root.parent
    worker = Path(os.environ.get("FRONTEND_ANALYZER_DIR") or (backend_root / "workers" / "frontend-analyzer"))
    worker = worker.resolve()

    analysis_id = str(payload.get("analysisId") or f"AN-FE-{uuid4().hex[:12]}")
    progress_path = (
        Path(str(payload["progressPath"])).expanduser().resolve()
        if payload.get("progressPath")
        else None
    )
    file_total = max(0, int(payload.get("fileTotal") or 0))
    artifact_path = payload.get("artifactPath")
    if artifact_path:
        out_file = Path(str(artifact_path)).expanduser().resolve()
    else:
        out_file = (repo_root / "artifacts" / "analysis" / analysis_id / "frontend.json").resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    commit = payload.get("commitSha")
    result: dict = {
        "schemaVersion": "frontend-analysis/v1",
        "commitSha": commit,
        "workspacePath": str(workspace_path),
        "screens": [],
        "components": [],
        "apiCalls": [],
        "unresolved": [],
    }

    # 1) ts-morph when worker + package.json-like project exists
    has_worker = (worker / "src" / "cli.ts").is_file()
    has_js = any(
        (workspace_path / name).exists()
        for name in ("package.json", "tsconfig.json", "next.config.js", "next.config.mjs", "vite.config.ts")
    )
    if has_worker and has_js:
        cmd = [
            "npx",
            "tsx",
            "src/cli.ts",
            "analyze",
            str(workspace_path),
            "--out",
            str(out_file),
        ]
        if commit:
            cmd.extend(["--commit", str(commit)])
        completed = subprocess.run(
            cmd,
            cwd=str(worker),
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "NODE_NO_WARNINGS": "1",
                "ANALYSIS_PROGRESS_PATH": str(progress_path or ""),
                "ANALYSIS_PROGRESS_TOTAL": str(file_total),
                "ANALYSIS_PROGRESS_OFFSET": "0",
            },
            timeout=160,
        )
        if completed.returncode == 0 and out_file.is_file():
            result = json.loads(out_file.read_text(encoding="utf-8"))
        else:
            err = (completed.stderr or completed.stdout or "analyzer failed").strip()
            result.setdefault("unresolved", []).append(
                {
                    "kind": "ts_morph_skipped",
                    "symbol": str(workspace_path),
                    "reason": err[:500] or "ts-morph failed — flask/jinja fallback",
                }
            )
    else:
        result.setdefault("unresolved", []).append(
            {
                "kind": "ts_morph_skipped",
                "symbol": str(workspace_path),
                "reason": "no JS/TS package markers — flask/jinja path",
            }
        )

    # 2) Always merge Flask/Jinja HTML controls (Bank of Anthos etc.)
    frontend_offset = _read_completed(progress_path)
    flask = extract_flask_screens(
        workspace_path,
        progress_callback=(
            lambda completed, _total: _write_progress(
                progress_path, frontend_offset + completed, file_total
            )
        ),
    )
    if flask.get("screens") or flask.get("apiCalls"):
        result = _merge_flask_into(result, flask)

    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_progress(progress_path, file_total, file_total)

    output = {
        "ok": True,
        "skill": "frontend_analyze",
        "tool": "analyze",
        "analysisId": analysis_id,
        "artifactPath": str(out_file),
        "commitSha": result.get("commitSha") or commit,
        "workspacePath": str(workspace_path),
        "projectId": payload.get("projectId"),
        "counts": {
            "screens": len(result.get("screens", [])),
            "components": len(result.get("components", [])),
            "apiCalls": len(result.get("apiCalls", [])),
            "unresolved": len(result.get("unresolved", [])),
            "uiInputs": sum(len(s.get("inputs") or []) for s in result.get("screens") or []),
        },
        "result": result,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "analysisId": analysis_id,
                "screens": output["counts"]["screens"],
                "uiInputs": output["counts"]["uiInputs"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
