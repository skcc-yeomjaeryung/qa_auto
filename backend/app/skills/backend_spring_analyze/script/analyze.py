#!/usr/bin/env python3
"""backend_spring_analyze / analyze — invoke Python Spring worker (no LLM)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def _backend_root() -> Path:
    # .../backend/app/skills/backend_spring_analyze/script/analyze.py
    return Path(__file__).resolve().parents[4]


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
    worker = Path(
        os.environ.get("BACKEND_ANALYZER_DIR")
        or (backend_root / "workers" / "backend-analyzer")
    ).resolve()
    if not (worker / "app" / "cli.py").is_file():
        print(f"backend-analyzer worker missing: {worker}", file=sys.stderr)
        return 2

    python = worker / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(os.environ.get("BACKEND_ANALYZER_PYTHON", "python3"))

    analysis_id = str(payload.get("analysisId") or f"AN-BE-{uuid4().hex[:12]}")
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
        out_file = (repo_root / "artifacts" / "analysis" / analysis_id / "backend.json").resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    commit = payload.get("commitSha")
    cmd = [
        str(python),
        "-m",
        "app.cli",
        "analyze",
        str(workspace_path),
        "--out",
        str(out_file),
    ]
    if commit:
        cmd.extend(["--commit", str(commit)])

    env = {
        **os.environ,
        "PYTHONPATH": str(worker),
        "ANALYSIS_PROGRESS_PATH": str(progress_path or ""),
        "ANALYSIS_PROGRESS_TOTAL": str(file_total),
    }
    completed = subprocess.run(
        cmd,
        cwd=str(worker),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=160,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "analyzer failed").strip()
        print(err[:2000], file=sys.stderr)
        return completed.returncode or 1

    result = json.loads(out_file.read_text(encoding="utf-8"))
    output = {
        "ok": True,
        "skill": "backend_spring_analyze",
        "tool": "analyze",
        "analysisId": analysis_id,
        "artifactPath": str(out_file),
        "commitSha": result.get("commitSha") or commit,
        "workspacePath": str(workspace_path),
        "projectId": payload.get("projectId"),
        "counts": {
            "endpoints": len(result.get("endpoints", [])),
            "services": len(result.get("services", [])),
            "validations": len(result.get("validations", [])),
            "unresolved": len(result.get("unresolved", [])),
        },
        "result": result,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "analysisId": analysis_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
