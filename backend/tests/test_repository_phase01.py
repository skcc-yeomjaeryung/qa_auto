from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_platform_store
from app.main import app


@pytest.fixture(autouse=True)
def fresh_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = get_platform_store()
    store._projects.clear()
    store._sets.clear()
    store._files.clear()
    store._commit_cache.clear()
    store._tokens.clear()
    if hasattr(store, "_analyses"):
        store._analyses.clear()
    if hasattr(store, "_mapping_sets"):
        store._mapping_sets.clear()
    if hasattr(store, "_graphs"):
        store._graphs.clear()
    if hasattr(store, "_scenarios"):
        store._scenarios.clear()
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    from app.utils import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


client = TestClient(app)


def test_project_exposes_created_and_updated_timestamps() -> None:
    created = client.post("/api/projects", json={"name": "Timestamp contract"})
    assert created.status_code == 201
    body = created.json()
    assert body["createdAt"]
    assert body["updatedAt"]

    updated = client.patch(
        f"/api/projects/{body['id']}",
        json={"name": "Timestamp contract updated"},
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["updatedAt"] >= body["updatedAt"]


def _init_git_repo(root: Path, filename: str = "README.md", content: str = "hello") -> str:
    root.mkdir(parents=True, exist_ok=True)
    (root / filename).write_text(content, encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps({"name": "fixture-fe", "dependencies": {"react": "18.0.0"}}),
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "pilot@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Pilot"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def test_console_connect_reuses_same_repository_source(tmp_path: Path) -> None:
    repository = tmp_path / "same-repository"
    _init_git_repo(repository)
    project = client.post("/api/projects", json={"name": "중복 연결 방지"}).json()
    payload = {
        "projectId": project["id"],
        "repositoryName": "첫 표시명",
        "sourceType": "local",
        "repository": {"path": str(repository), "branch": "main"},
        "autoAnalyze": False,
    }

    first = client.post("/api/console/connect", json=payload)
    assert first.status_code == 200
    second = client.post(
        "/api/console/connect",
        json={**payload, "repositoryName": "다른 표시명"},
    )
    assert second.status_code == 200
    assert second.json()["repositorySetId"] == first.json()["repositorySetId"]
    assert "이미 연결" in second.json()["message"]

    sets = client.get(f"/api/projects/{project['id']}/repository-sets").json()
    assert len(sets) == 1
    refreshed = client.get(f"/api/projects/{project['id']}").json()
    assert refreshed["repositorySetIds"] == [first.json()["repositorySetId"]]


def test_console_connect_edit_updates_repository_in_place(tmp_path: Path) -> None:
    original = tmp_path / "original-repository"
    replacement = tmp_path / "replacement-repository"
    _init_git_repo(original)
    _init_git_repo(replacement, content="replacement")
    project = client.post("/api/projects", json={"name": "연결 수정"}).json()
    first = client.post(
        "/api/console/connect",
        json={
            "projectId": project["id"],
            "repositoryName": "기존 연결",
            "sourceType": "local",
            "repository": {"path": str(original), "branch": "main"},
            "autoAnalyze": False,
        },
    ).json()

    edited = client.post(
        "/api/console/connect",
        json={
            "projectId": project["id"],
            "repositorySetId": first["repositorySetId"],
            "repositoryName": "수정한 연결",
            "sourceType": "local",
            "repository": {"path": str(replacement), "branch": "main"},
            "autoAnalyze": False,
        },
    )

    assert edited.status_code == 200
    assert edited.json()["repositorySetId"] == first["repositorySetId"]
    assert "수정" in edited.json()["message"]
    sets = client.get(f"/api/projects/{project['id']}/repository-sets").json()
    assert len(sets) == 1
    assert sets[0]["name"] == "수정한 연결"
    assert sets[0]["repositories"][0]["path"] == str(replacement)


def test_projects_default_to_latest_updated_first() -> None:
    older = client.post("/api/projects", json={"name": "이전 프로젝트"}).json()
    newer = client.post("/api/projects", json={"name": "최근 프로젝트"}).json()
    client.patch(f"/api/projects/{older['id']}", json={"name": "가장 최근 수정"})

    projects = client.get("/api/projects").json()
    assert projects[0]["id"] == older["id"]
    assert projects[1]["id"] == newer["id"]


def test_local_path_snapshot_and_commit_pin(tmp_path: Path) -> None:
    fe = tmp_path / "fe"
    be = tmp_path / "be"
    fe_sha = _init_git_repo(fe, "App.tsx", "export const App = () => null")
    be_sha = _init_git_repo(be, "Main.java", "class Main {}")
    (be / "pom.xml").write_text("<project></project>", encoding="utf-8")
    subprocess.run(["git", "add", "pom.xml"], cwd=be, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "pom"], cwd=be, check=True, capture_output=True)
    be_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=be, text=True).strip()

    project = client.post("/api/projects", json={"name": "Pilot local"}).json()
    project_id = project["id"]
    assert project["journey"]["project"] == "complete"
    assert project["journey"]["repository"] == "pending"

    fe_set = client.post(
        f"/api/projects/{project_id}/repositories",
        json={
            "role": "frontend",
            "sourceType": "local",
            "path": str(fe),
            "branch": "main",
        },
    )
    assert fe_set.status_code == 201

    be_set = client.post(
        f"/api/projects/{project_id}/repositories",
        json={
            "role": "backend",
            "sourceType": "local",
            "path": str(be),
            "branch": "main",
        },
    )
    assert be_set.status_code == 201
    set_id = be_set.json()["id"]

    sync = client.post(f"/api/repository-sets/{set_id}/sync", json={"force": False})
    assert sync.status_code == 200
    body = sync.json()
    assert body["status"] == "complete"
    assert body["journeyStatus"] == "complete"
    repos = {r["role"]: r for r in body["repositories"]}
    assert repos["frontend"]["commitSha"] == fe_sha
    assert repos["backend"]["commitSha"] == be_sha
    assert "React" in repos["frontend"]["stack"].get("frameworks", [])

    files = client.get(f"/api/repository-sets/{set_id}/files").json()
    assert files
    assert all("node_modules" not in f["path"] for f in files)
    assert all(f["sha256"] for f in files)

    again = client.post(f"/api/repository-sets/{set_id}/sync", json={"force": False}).json()
    repos2 = {r["role"]: r for r in again["repositories"]}
    assert repos2["frontend"]["commitSha"] == fe_sha
    assert repos2["backend"]["commitSha"] == be_sha

    project_after = client.get(f"/api/projects/{project_id}").json()
    assert project_after["journey"]["repository"] == "complete"


def test_github_via_local_bare_clone(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    sha = _init_git_repo(origin)
    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "clone", "--bare", str(origin), str(bare)],
        check=True,
        capture_output=True,
    )

    project = client.post("/api/projects", json={"name": "Bare clone"}).json()
    set_resp = client.post(
        f"/api/projects/{project['id']}/repositories",
        json={
            "role": "frontend",
            "sourceType": "github",
            "url": f"file://{bare}",
            "branch": "main",
        },
    )
    assert set_resp.status_code == 201
    set_id = set_resp.json()["id"]

    synced = client.post(f"/api/repository-sets/{set_id}/sync").json()
    assert synced["status"] == "complete"
    assert synced["repositories"][0]["commitSha"] == sha


def test_token_not_echoed_in_response(tmp_path: Path) -> None:
    fe = tmp_path / "fe"
    _init_git_repo(fe)
    project = client.post("/api/projects", json={"name": "Secret"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/repositories",
        json={
            "role": "frontend",
            "sourceType": "local",
            "path": str(fe),
            "token": "ghp_supersecrettokenvalue999",
        },
    )
    assert response.status_code == 201
    raw = response.text
    assert "ghp_supersecrettokenvalue999" not in raw
    assert response.json()["repositories"][0]["hasCredential"] is True


def test_ignore_excludes_node_modules(tmp_path: Path) -> None:
    fe = tmp_path / "fe"
    _init_git_repo(fe)
    nested = fe / "node_modules" / "lodash"
    nested.mkdir(parents=True)
    (nested / "index.js").write_text("module.exports={}", encoding="utf-8")
    project = client.post("/api/projects", json={"name": "Ignore"}).json()
    set_id = client.post(
        f"/api/projects/{project['id']}/repositories",
        json={"role": "frontend", "sourceType": "local", "path": str(fe)},
    ).json()["id"]
    client.post(f"/api/repository-sets/{set_id}/sync")
    files = client.get(f"/api/repository-sets/{set_id}/files").json()
    assert not any("node_modules" in f["path"] for f in files)


def test_invalid_local_path() -> None:
    project = client.post("/api/projects", json={"name": "Bad"}).json()
    reg = client.post(
        f"/api/projects/{project['id']}/repositories",
        json={
            "role": "frontend",
            "sourceType": "local",
            "path": "/definitely/missing/path-xyz",
        },
    )
    assert reg.status_code == 201
    set_id = reg.json()["id"]
    sync = client.post(f"/api/repository-sets/{set_id}/sync")
    assert sync.status_code == 200
    assert sync.json()["status"] == "error"


def test_nested_monorepo_path_uses_tree_hash(tmp_path: Path) -> None:
    """Nested path inside a git root must not inherit parent commit SHA."""
    mono = tmp_path / "mono"
    mono.mkdir()
    nested = mono / "apps" / "fe"
    nested.mkdir(parents=True)
    (nested / "package.json").write_text(
        json.dumps({"name": "nested-fe", "dependencies": {"react": "18.0.0"}}),
        encoding="utf-8",
    )
    (nested / "App.tsx").write_text("export {}", encoding="utf-8")
    (mono / "README.md").write_text("mono", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=mono, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "pilot@example.com"], cwd=mono, check=True)
    subprocess.run(["git", "config", "user.name", "Pilot"], cwd=mono, check=True)
    subprocess.run(["git", "add", "."], cwd=mono, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=mono, check=True, capture_output=True)
    parent_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=mono, text=True
    ).strip()

    project = client.post("/api/projects", json={"name": "Nested"}).json()
    set_id = client.post(
        f"/api/projects/{project['id']}/repositories",
        json={"role": "frontend", "sourceType": "local", "path": str(nested)},
    ).json()["id"]
    synced = client.post(f"/api/repository-sets/{set_id}/sync").json()
    assert synced["status"] == "complete"
    pin = synced["repositories"][0]["commitSha"]
    assert pin != parent_sha
    assert len(pin) == 64
