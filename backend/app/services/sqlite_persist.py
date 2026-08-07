"""SQLite KV persistence for platform store catalog blobs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from app.utils.config import get_settings

_lock = Lock()


def _db_path() -> Path:
    root = Path(get_settings().data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / "platform_store.sqlite3"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def kv_get(key: str) -> Any | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            if not row:
                return None
            return json.loads(row[0])
        finally:
            conn.close()


def kv_set(key: str, value: Any) -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)",
                (key, json.dumps(value, default=str)),
            )
            conn.commit()
        finally:
            conn.close()
