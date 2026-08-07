from types import SimpleNamespace
from unittest.mock import Mock

from app.services.console_service import ConsoleService


def test_flask_workspace_runs_ui_and_server_analysis(tmp_path) -> None:
    """Flask-only stack metadata must never make the Frontend/UI result disappear."""
    service = ConsoleService.__new__(ConsoleService)
    service.store = SimpleNamespace(append_log=Mock())
    service.fe = SimpleNamespace(run=Mock(return_value=SimpleNamespace(id="AN-FE-flask")))
    service.be = SimpleNamespace(run=Mock(return_value=SimpleNamespace(id="AN-BE-flask")))
    repo_set = SimpleNamespace(id="RS-flask")
    repo = SimpleNamespace(
        stack={"frameworks": ["Flask"], "languages": ["Python", "HTML"]},
        workspacePath=str(tmp_path),
        commitSha="abc123",
    )

    started, analysis_ids = service._analyze_workspace_repo("PRJ-flask", repo_set, repo)

    assert started is True
    assert analysis_ids == ["AN-FE-flask", "AN-BE-flask"]
    service.fe.run.assert_called_once()
    service.be.run.assert_called_once()
