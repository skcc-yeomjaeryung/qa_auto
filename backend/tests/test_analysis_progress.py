from __future__ import annotations

import json
import time
from pathlib import Path

from app.services.analysis_progress import (
    count_analysis_files,
    execute_with_file_progress,
)


def test_analysis_file_count_matches_active_workers(tmp_path: Path) -> None:
    (tmp_path / "page.tsx").write_text("export default () => null", encoding="utf-8")
    (tmp_path / "view.html").write_text("<main />", encoding="utf-8")
    (tmp_path / "Controller.java").write_text("class Controller {}", encoding="utf-8")
    (tmp_path / "helper.py").write_text("pass", encoding="utf-8")

    assert count_analysis_files(tmp_path, "frontend") == 2
    assert count_analysis_files(tmp_path, "backend") == 1


def test_file_progress_watcher_forwards_real_snapshots(tmp_path: Path) -> None:
    progress_path = tmp_path / "progress.json"
    observed: list[tuple[int, int]] = []

    def operation() -> str:
        progress_path.write_text(
            json.dumps({"completed": 1, "failed": 0, "total": 3}), encoding="utf-8"
        )
        time.sleep(0.12)
        progress_path.write_text(
            json.dumps({"completed": 2, "failed": 1, "total": 3}), encoding="utf-8"
        )
        return "complete"

    result = execute_with_file_progress(
        operation=operation,
        progress_path=progress_path,
        file_total=3,
        on_progress=lambda completed, failed: observed.append((completed, failed)),
        poll_seconds=0.02,
    )

    assert result == "complete"
    assert (1, 0) in observed
    assert observed[-1] == (2, 1)
