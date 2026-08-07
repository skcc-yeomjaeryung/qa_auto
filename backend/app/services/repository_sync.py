from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
from threading import Lock
from pathlib import Path

from app.services.ignore_rules import should_ignore_dir, should_ignore_file
from app.utils.config import get_settings
from app.services.repository_models import (
    JourneyStatus,
    Repository,
    RepositoryRegister,
    RepositorySet,
    SourceType,
    SyncStatus,
    utc_now,
)
from app.services.repository_store import InMemoryPlatformStore
from app.services.stack_detect import detect_stack

logger = logging.getLogger(__name__)

_SYNC_LOCKS_GUARD = Lock()
_SYNC_LOCKS: dict[str, Lock] = {}


class RepositorySyncBusyError(RuntimeError):
    """같은 저장소 세트에 중복 동기화가 들어온 경우."""


def _sync_lock(set_id: str) -> Lock:
    with _SYNC_LOCKS_GUARD:
        return _SYNC_LOCKS.setdefault(set_id, Lock())

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^\s'\"]+"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
]


class RepositorySyncService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store
        settings = get_settings()
        self.workspace_root = Path(settings.workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        project_id: str,
        payload: RepositoryRegister,
        *,
        repository_set_id: str | None = None,
        repository_set_name: str | None = None,
    ) -> RepositorySet:
        project = self.store.get_project(project_id)
        if not project:
            raise LookupError(f"project not found: {project_id}")

        set_id = repository_set_id or project.repositorySetId
        if not set_id:
            created = self.store.create_repository_set(
                project_id, repository_set_name or "기본 저장소"
            )
            set_id = created.id

        self._validate_register(payload)
        # Never log token
        if payload.token:
            logger.info(
                "repository register project=%s role=%s credential=present(masked)",
                project_id,
                payload.role.value,
            )

        repo_id = f"REPO-{payload.role.value[:2].upper()}-{os.urandom(4).hex()}"
        path_value = None
        if payload.path:
            path_value = str(Path(payload.path).expanduser().resolve())
        subdir = (payload.subdir or "").strip().strip("/") or None
        repository = Repository(
            id=repo_id,
            role=payload.role,
            sourceType=payload.sourceType,
            url=payload.url if payload.sourceType == SourceType.github else None,
            path=path_value,
            subdir=subdir,
            branch=payload.branch,
            commitSha=payload.commitSha,
            trackBranch=not bool(payload.commitSha),
            hasCredential=bool(payload.token),
            syncStatus=SyncStatus.pending,
        )

        repo_set = self.store.add_repository(
            set_id, repository, token=payload.token
        )
        self.store.update_project_journey(project_id, JourneyStatus.pending.value)
        self.store.append_log(
            repo_set.id,
            f"registered {payload.role.value} source={payload.sourceType.value}",
        )
        return repo_set

    def sync(self, set_id: str, force: bool = False) -> RepositorySet:
        repo_set = self.store.get_set(set_id)
        if not repo_set:
            raise LookupError(f"repository set not found: {set_id}")
        if not repo_set.repositories:
            raise ValueError("no repositories registered")

        resource_lock = _sync_lock(set_id)
        if not resource_lock.acquire(blocking=False):
            raise RepositorySyncBusyError(f"repository set is already syncing: {set_id}")

        try:
            return self._sync_locked(repo_set, force=force)
        finally:
            resource_lock.release()

    def _sync_locked(self, repo_set: RepositorySet, *, force: bool) -> RepositorySet:
        set_id = repo_set.id

        repo_set = repo_set.model_copy(
            update={
                "status": SyncStatus.progressing,
                "journeyStatus": JourneyStatus.progressing,
                "retryCount": repo_set.retryCount + (1 if force else 0),
            }
        )
        self.store.save_set(repo_set)
        self.store.update_project_journey(repo_set.projectId, JourneyStatus.progressing.value)
        self.store.append_log(set_id, "sync started")

        inventory: list[dict] = []
        synced: list[Repository] = []
        errors: list[str] = []

        for repo in repo_set.repositories:
            try:
                updated, files = self._sync_one(repo_set, repo, force=force)
                synced.append(updated)
                inventory.extend(files)
            except Exception as exc:  # noqa: BLE001 — surface sync error state
                logger.exception("sync failed for %s", repo.id)
                message = self._safe_error(str(exc))
                errors.append(f"{repo.role.value}: {message}")
                synced.append(
                    repo.model_copy(
                        update={
                            "syncStatus": SyncStatus.error,
                            "lastError": message,
                        }
                    )
                )

        status = (
            SyncStatus.error
            if errors
            else SyncStatus.cached
            if synced and all(repo.syncStatus == SyncStatus.cached for repo in synced)
            else SyncStatus.complete
        )
        journey = JourneyStatus.error if errors else JourneyStatus.complete
        updated_set = repo_set.model_copy(
            update={
                "repositories": synced,
                "status": status,
                "journeyStatus": journey,
                "lastSyncedAt": utc_now(),
            }
        )
        self.store.save_set(updated_set)
        self.store.set_files(set_id, inventory)
        self.store.update_project_journey(repo_set.projectId, journey.value)
        self.store.append_log(
            set_id,
            f"sync finished status={status.value} files={len(inventory)}",
        )
        return updated_set

    def _sync_one(
        self, repo_set: RepositorySet, repo: Repository, force: bool
    ) -> tuple[Repository, list[dict]]:
        if repo.sourceType == SourceType.local:
            root, commit = self._prepare_local(repo)
            cached = False
        else:
            root, commit, cached = self._prepare_github(repo_set, repo, force=force)

        cached = cached or (not force and bool(repo.commitSha) and repo.commitSha == commit)

        work = self._resolve_workdir(root, repo.subdir)
        if cached and not force:
            stack = detect_stack(work)
            files = self._inventory(work, repo.role.value)
            return (
                repo.model_copy(
                    update={
                        "commitSha": commit,
                        "workspacePath": str(work),
                        "stack": stack,
                        "fileCount": len(files),
                        "syncStatus": SyncStatus.cached,
                        "lastError": None,
                    }
                ),
                files,
            )

        stack = detect_stack(work)
        files = self._inventory(work, repo.role.value)
        # Cache key includes subdir so FE/BE monorepo workspaces do not collide.
        cache_key = f"{commit}:{repo.subdir or '.'}"
        self.store.put_cached_workspace(cache_key, str(work))
        return (
            repo.model_copy(
                update={
                    "commitSha": commit,
                    "workspacePath": str(work),
                    "stack": stack,
                    "fileCount": len(files),
                    "syncStatus": SyncStatus.complete,
                    "lastError": None,
                }
            ),
            files,
        )

    def _prepare_local(self, repo: Repository) -> tuple[Path, str]:
        if not repo.path:
            raise ValueError("local path required")
        root = Path(repo.path).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"local path not found: {root}")

        commit = repo.commitSha
        if not commit:
            # Only trust git SHA when this directory itself is a git work tree root.
            # Nested paths inside a monorepo must not inherit the parent commit.
            if self._is_git_worktree_root(root):
                commit = self._git_rev_parse(root)
            commit = commit or self._hash_tree(root)
        # Snapshot into workspace for stable artifact path
        dest = self.workspace_root / f"{repo.id}-{commit[:12]}"
        if dest.exists():
            return dest, commit
        shutil.copytree(
            root,
            dest,
            ignore=shutil.ignore_patterns(
                "node_modules",
                ".next",
                "dist",
                "build",
                "target",
                ".git",
                ".venv",
                "__pycache__",
            ),
            dirs_exist_ok=False,
        )
        return dest, commit

    def _prepare_github(
        self, repo_set: RepositorySet, repo: Repository, force: bool
    ) -> tuple[Path, str, bool]:
        if not repo.url:
            raise ValueError("github url required")
        url = repo.url.strip()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("file://")):
            raise ValueError("unsupported url scheme")

        # Clone root cache only (workdir/subdir applied in _sync_one).
        dest = self.workspace_root / repo.id
        if repo.commitSha and not repo.trackBranch and not force and dest.is_dir():
            try:
                head = self._git_rev_parse(dest)
            except Exception:  # noqa: BLE001
                head = None
            if head == repo.commitSha:
                self.store.append_log(repo_set.id, f"clone cache hit commit={repo.commitSha[:12]}")
                return dest, repo.commitSha, True

        if dest.exists() and force:
            shutil.rmtree(dest)

        token = self.store.get_token(repo.id)
        clone_url = self._authed_url(url, token) if token else url

        had_checkout = dest.exists()
        if not had_checkout:
            self._run_git(
                [
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    repo.branch,
                    clone_url,
                    str(dest),
                ],
                mask=token,
            )
        else:
            self._run_git(["-C", str(dest), "fetch", "--depth", "1", "origin", repo.branch], mask=token)

        if repo.trackBranch:
            # 등록 때 커밋을 고정하지 않은 저장소는 매 동기화마다 원격 branch HEAD를 관측한다.
            if had_checkout:
                self._run_git(["-C", str(dest), "checkout", "--detach", "FETCH_HEAD"], mask=token)
            commit = self._git_rev_parse(dest)
            if not commit:
                raise RuntimeError("unable to resolve branch head")
        elif repo.commitSha:
            # deepen if needed then checkout
            try:
                self._run_git(["-C", str(dest), "checkout", repo.commitSha], mask=token)
            except RuntimeError:
                self._run_git(
                    ["-C", str(dest), "fetch", "--depth", "50", "origin", repo.branch],
                    mask=token,
                )
                self._run_git(["-C", str(dest), "checkout", repo.commitSha], mask=token)
            commit = repo.commitSha
        else:
            commit = self._git_rev_parse(dest)
            if not commit:
                raise RuntimeError("unable to resolve commit sha")

        return dest, commit, False

    @staticmethod
    def _resolve_workdir(root: Path, subdir: str | None) -> Path:
        if not subdir:
            return root
        work = (root / subdir).resolve()
        try:
            work.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"subdir escapes repository root: {subdir}") from exc
        if not work.is_dir():
            raise ValueError(f"subdir not found: {subdir}")
        return work

    def _inventory(self, root: Path, role: str) -> list[dict]:
        items: list[dict] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not should_ignore_dir(d)]
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if should_ignore_file(path, size):
                    continue
                rel = str(path.relative_to(root)).replace("\\", "/")
                digest = self._sha256_file(path)
                items.append(
                    {
                        "path": rel,
                        "language": self._guess_language(path),
                        "sizeBytes": size,
                        "sha256": digest,
                        "roleHint": role,
                    }
                )
        return items

    @staticmethod
    def _guess_language(path: Path) -> str | None:
        mapping = {
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".py": "Python",
            ".java": "Java",
            ".kt": "Kotlin",
            ".go": "Go",
            ".json": "JSON",
            ".yml": "YAML",
            ".yaml": "YAML",
            ".md": "Markdown",
            ".css": "CSS",
            ".html": "HTML",
        }
        return mapping.get(path.suffix.lower())

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _hash_tree(root: Path) -> str:
        h = hashlib.sha256()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not should_ignore_dir(d)]
            for name in sorted(filenames):
                path = Path(dirpath) / name
                rel = str(path.relative_to(root))
                h.update(rel.encode())
                try:
                    h.update(path.read_bytes()[:4096])
                except OSError:
                    continue
        return h.hexdigest()

    @staticmethod
    def _is_git_worktree_root(root: Path) -> bool:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            )
            top = Path(result.stdout.strip()).resolve()
            return top == root.resolve()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def _git_rev_parse(root: Path) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip() or None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _run_git(self, args: list[str], mask: str | None = None) -> None:
        # Never pass token into logs
        display = ["git", *[self._redact(a, mask) for a in args]]
        logger.info("git %s", " ".join(display[1:]))
        attempts = 2 if any(part in {"clone", "fetch"} for part in args) else 1
        last_error: subprocess.CalledProcessError | None = None
        for attempt in range(1, attempts + 1):
            try:
                subprocess.run(
                    ["git", *args],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return
            except subprocess.CalledProcessError as exc:
                last_error = exc
                if attempt < attempts:
                    logger.warning("transient git command retry %s/%s", attempt, attempts - 1)
        assert last_error is not None
        stderr = self._redact(last_error.stderr or last_error.stdout or "git failed", mask)
        raise RuntimeError(stderr.strip() or "git command failed") from last_error

    @staticmethod
    def _authed_url(url: str, token: str) -> str:
        if url.startswith("https://"):
            return url.replace("https://", f"https://x-access-token:{token}@", 1)
        if url.startswith("http://"):
            return url.replace("http://", f"http://x-access-token:{token}@", 1)
        return url

    @staticmethod
    def _redact(text: str, secret: str | None) -> str:
        redacted = text
        if secret:
            redacted = redacted.replace(secret, "***")
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub("***", redacted)
        return redacted

    @staticmethod
    def _safe_error(message: str) -> str:
        return RepositorySyncService._redact(message, None)[:500]

    @staticmethod
    def _validate_register(payload: RepositoryRegister) -> None:
        if payload.sourceType == SourceType.local:
            if not payload.path:
                raise ValueError("path required for local source")
        elif payload.sourceType == SourceType.github:
            if not payload.url:
                raise ValueError("url required for github source")
        else:  # pragma: no cover
            raise ValueError("unsupported source type")
