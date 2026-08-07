"""Build expandable directory trees (default 3-depth) for Analysis console."""

from __future__ import annotations

from pathlib import Path

from app.services.console_models import ResourceNode
from app.services.ignore_rules import should_ignore_dir, should_ignore_file


def build_resource_tree(
    root: Path,
    *,
    role: str,
    analysis_id: str,
    max_depth: int = 3,
    excluded: set[str] | None = None,
    expand_path: str | None = None,
) -> list[ResourceNode]:
    root = root.resolve()
    if not root.exists():
        return []
    excluded = excluded or set()
    expand_parts = _normalize_rel(expand_path).split("/") if expand_path else []

    def walk(current: Path, depth: int, rel: str) -> list[ResourceNode]:
        if depth > max_depth and not _should_force_expand(rel, expand_parts):
            return []
        nodes: list[ResourceNode] = []
        try:
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return []
        for entry in entries:
            name = entry.name
            if entry.is_dir() and should_ignore_dir(name):
                continue
            if entry.is_file():
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                if should_ignore_file(entry, size):
                    continue
            child_rel = f"{rel}/{name}" if rel else name
            node_id = f"{analysis_id}:{child_rel}"
            if entry.is_dir():
                force = _should_force_expand(child_rel, expand_parts)
                next_depth = depth + 1
                children: list[ResourceNode] = []
                has_more = False
                if next_depth <= max_depth or force:
                    children = walk(entry, next_depth, child_rel)
                    # peek if deeper content exists beyond default depth
                    if next_depth >= max_depth and not force:
                        has_more = _has_children(entry)
                else:
                    has_more = _has_children(entry)
                nodes.append(
                    ResourceNode(
                        id=node_id,
                        name=name,
                        path=child_rel,
                        kind="dir",
                        role=role,
                        depth=depth,
                        excluded=child_rel in excluded,
                        selected=child_rel not in excluded,
                        children=children,
                        hasMore=has_more and not children,
                    )
                )
            else:
                nodes.append(
                    ResourceNode(
                        id=node_id,
                        name=name,
                        path=child_rel,
                        kind="file",
                        role=role,
                        depth=depth,
                        excluded=child_rel in excluded,
                        selected=child_rel not in excluded,
                    )
                )
        return nodes

    return walk(root, 1, "")


def expand_resource_node(
    root: Path,
    rel_path: str,
    *,
    role: str,
    analysis_id: str,
    max_depth: int = 2,
    excluded: set[str] | None = None,
) -> list[ResourceNode]:
    """Expand one directory deeper on demand."""
    root = root.resolve()
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root)) or not target.is_dir():
        return []
    base_depth = rel_path.count("/") + 2 if rel_path else 1
    excluded = excluded or set()

    def walk(current: Path, depth: int, rel: str) -> list[ResourceNode]:
        if depth > base_depth + max_depth - 1:
            return []
        nodes: list[ResourceNode] = []
        try:
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return []
        for entry in entries:
            if entry.is_dir() and should_ignore_dir(entry.name):
                continue
            if entry.is_file():
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                if should_ignore_file(entry, size):
                    continue
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            node_id = f"{analysis_id}:{child_rel}"
            if entry.is_dir():
                children = walk(entry, depth + 1, child_rel) if depth < base_depth + max_depth - 1 else []
                nodes.append(
                    ResourceNode(
                        id=node_id,
                        name=entry.name,
                        path=child_rel,
                        kind="dir",
                        role=role,
                        depth=depth,
                        excluded=child_rel in excluded,
                        selected=child_rel not in excluded,
                        children=children,
                        hasMore=_has_children(entry) and not children,
                    )
                )
            else:
                nodes.append(
                    ResourceNode(
                        id=node_id,
                        name=entry.name,
                        path=child_rel,
                        kind="file",
                        role=role,
                        depth=depth,
                        excluded=child_rel in excluded,
                        selected=child_rel not in excluded,
                    )
                )
        return nodes

    return walk(target, base_depth, rel_path)


def _has_children(path: Path) -> bool:
    try:
        for entry in path.iterdir():
            if entry.is_dir() and should_ignore_dir(entry.name):
                continue
            if entry.is_file():
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0
                if should_ignore_file(entry, size):
                    continue
            return True
    except OSError:
        return False
    return False


def _normalize_rel(path: str | None) -> str:
    if not path:
        return ""
    return path.strip().strip("/")


def _should_force_expand(rel: str, expand_parts: list[str]) -> bool:
    if not expand_parts or not rel:
        return False
    rel_parts = rel.split("/")
    return expand_parts[: len(rel_parts)] == rel_parts
