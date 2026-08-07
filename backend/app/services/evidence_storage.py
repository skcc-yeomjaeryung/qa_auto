from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from app.core.paths import ARTIFACTS_EVIDENCE


class EvidenceStorageAdapter(Protocol):
    def package_dir(self, evidence_id: str) -> Path: ...

    def reset_package(self, evidence_id: str) -> Path: ...

    def write_bytes(self, evidence_id: str, relative_path: str, data: bytes) -> Path: ...

    def copy_file(self, evidence_id: str, relative_path: str, source: Path) -> Path: ...

    def delete_package(self, evidence_id: str) -> None: ...


class LocalFilesystemEvidenceStorage:
    """Pilot storage adapter with strict package-root path jail."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or (ARTIFACTS_EVIDENCE / "packages")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def package_dir(self, evidence_id: str) -> Path:
        if not evidence_id or "/" in evidence_id or ".." in evidence_id:
            raise ValueError("invalid evidence id")
        return (self.root / evidence_id).resolve()

    def reset_package(self, evidence_id: str) -> Path:
        path = self.package_dir(evidence_id)
        self._assert_under_root(path)
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_bytes(self, evidence_id: str, relative_path: str, data: bytes) -> Path:
        target = self._target(evidence_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def copy_file(self, evidence_id: str, relative_path: str, source: Path) -> Path:
        if not source.is_file():
            raise FileNotFoundError(source)
        target = self._target(evidence_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def delete_package(self, evidence_id: str) -> None:
        path = self.package_dir(evidence_id)
        self._assert_under_root(path)
        if path.exists():
            shutil.rmtree(path)

    def _target(self, evidence_id: str, relative_path: str) -> Path:
        rel = Path(relative_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("invalid artifact path")
        package = self.package_dir(evidence_id)
        target = (package / rel).resolve()
        try:
            target.relative_to(package)
        except ValueError as exc:
            raise ValueError("artifact outside package") from exc
        return target

    def _assert_under_root(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("package outside evidence root") from exc
