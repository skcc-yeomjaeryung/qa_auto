"""Platform ignore/allow rules for repository inventory (Phase 01)."""

from __future__ import annotations

from pathlib import Path

DEFAULT_IGNORE_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "target",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".turbo",
    ".cache",
    "vendor",
}

DEFAULT_IGNORE_FILE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".jar",
    ".war",
    ".class",
    ".o",
    ".so",
    ".dylib",
    ".exe",
    ".dll",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp4",
    ".mov",
}

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB


def should_ignore_dir(name: str) -> bool:
    return name in DEFAULT_IGNORE_DIR_NAMES or name.startswith(".")


def should_ignore_file(path: Path, size: int) -> bool:
    if size > MAX_FILE_BYTES:
        return True
    if path.name.startswith("."):
        return path.name not in {".gitignore", ".env.example"}
    return path.suffix.lower() in DEFAULT_IGNORE_FILE_SUFFIXES
