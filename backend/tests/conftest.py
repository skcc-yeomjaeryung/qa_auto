"""Pytest defaults — disable auth header guard for unit/API tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir():
    """Keep the test catalog out of the running console's SQLite store.

    The platform store persists to `${DATA_DIR}/platform_store.sqlite3`. Without
    this isolation a test run overwrites projects/graphs a developer is looking at
    in the local console (last writer wins).
    """
    from app.utils.config import get_settings

    with tempfile.TemporaryDirectory(prefix="qa-auto-test-data-") as tmp:
        import os

        previous = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(Path(tmp))
        get_settings.cache_clear()
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("DATA_DIR", None)
            else:
                os.environ["DATA_DIR"] = previous
            get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _disable_auth_guard(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QA_AUTO_AUTH_GUARD", "0")
    # Phase 10: do not block unit/API tests waiting for Spring ingest.
    monkeypatch.setenv("QA_AUTO_BACKEND_LOG_WAIT_SEC", "0")
    monkeypatch.setenv("QA_AUTO_BACKEND_LOG_POLL_SEC", "0.01")
