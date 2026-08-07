from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from typing import Callable, TypeVar


_IGNORED_PARTS = {
    ".git",
    ".next",
    ".next-build",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "venv",
}

_ROLE_SUFFIXES = {
    "frontend": {".html", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"},
    # 현재 backend_spring_analyze worker가 실제로 파싱하는 단위와 일치시킨다.
    "backend": {".java"},
}


def list_analysis_files(workspace: Path, role: str) -> tuple[Path, ...]:
    """분석기가 읽을 수 있는 소스 파일을 결정적 순서로 반환한다."""

    suffixes = _ROLE_SUFFIXES.get(role, _ROLE_SUFFIXES["frontend"] | _ROLE_SUFFIXES["backend"])
    files: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        try:
            relative_parts = path.relative_to(workspace).parts
        except ValueError:
            continue
        if any(part in _IGNORED_PARTS for part in relative_parts):
            continue
        files.append(path)
    return tuple(sorted(files))


def count_analysis_files(workspace: Path, role: str) -> int:
    """임의 시간 추정 없이 실제 분석 대상 파일 수를 센다."""

    return len(list_analysis_files(workspace, role))


T = TypeVar("T")


def execute_with_file_progress(
    *,
    operation: Callable[[], T],
    progress_path: Path,
    file_total: int,
    on_progress: Callable[[int, int], None],
    poll_seconds: float = 0.08,
) -> T:
    """별도 analyzer process가 기록한 실제 파일 진행을 store callback으로 전달한다.

    analyzer가 처리한 파일 수만 반영하며 경과 시간을 진행률로 위장하지 않는다.
    부분 write는 다음 poll에서 다시 읽고, operation 종료 직전 snapshot도 한 번 더 적용한다.
    """

    progress_path.unlink(missing_ok=True)
    stop = Event()
    last = (-1, -1)

    def publish() -> None:
        nonlocal last
        try:
            payload = json.loads(progress_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        completed = max(0, min(file_total, int(payload.get("completed") or 0)))
        failed = max(0, min(file_total - completed, int(payload.get("failed") or 0)))
        current = (completed, failed)
        if current == last:
            return
        last = current
        on_progress(completed, failed)

    def watch() -> None:
        while not stop.wait(poll_seconds):
            publish()

    watcher = Thread(target=watch, name=f"analysis-progress-{progress_path.parent.name}", daemon=True)
    watcher.start()
    try:
        return operation()
    finally:
        stop.set()
        publish()
        watcher.join(timeout=1)
