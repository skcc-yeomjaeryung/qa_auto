from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.skills.backend_spring_analyze.script.spring_parse import analyze_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI_TEST Backend Analyzer (Python / Spring)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    analyze = sub.add_parser("analyze", help="Analyze a Spring workspace")
    analyze.add_argument("workspace", type=Path)
    analyze.add_argument("--out", type=Path, default=None)
    analyze.add_argument("--commit", default=None)

    health = sub.add_parser("health", help="Health check")

    args = parser.parse_args(argv)
    if args.cmd == "health":
        print(json.dumps({"status": "ok", "service": "backend-analyzer", "runtime": "python", "parser": "javalang"}))
        return 0

    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        print(json.dumps({"ok": False, "error": f"workspace not found: {workspace}"}), file=sys.stderr)
        return 2

    progress_path = (
        Path(os.environ["ANALYSIS_PROGRESS_PATH"]).expanduser().resolve()
        if os.environ.get("ANALYSIS_PROGRESS_PATH")
        else None
    )
    configured_total = max(0, int(os.environ.get("ANALYSIS_PROGRESS_TOTAL") or 0))

    def write_progress(completed: int, worker_total: int) -> None:
        if progress_path is None:
            return
        total = configured_total or worker_total
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
            json.dumps({"completed": min(total, completed), "failed": 0, "total": total}),
            encoding="utf-8",
        )

    result = analyze_workspace(workspace, commit_sha=args.commit, progress_callback=write_progress)
    write_progress(configured_total, configured_total)
    payload = result.model_dump()
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(json.dumps({"ok": True, "out": str(args.out), "endpoints": len(result.endpoints)}))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
