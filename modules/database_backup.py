"""Create a consistent, uniquely named SQLite backup before data changes."""
from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class DatabaseBackupError(RuntimeError):
    """A complete, integrity-checked SQLite backup could not be produced."""


def create_database_backup(connection: sqlite3.Connection, db_path: str | Path,
                           *, label: str) -> Path:
    """Snapshot the connection, including committed WAL data, to a new file.

    The caller must still verify that the source has not changed between the
    snapshot and its write transaction. This provides no cross-process lock.
    """
    db_path = Path(db_path)
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = backup_dir / f"{db_path.stem}-{label}-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    # Reserve a fresh filename and never overwrite an earlier backup.
    with path.open("xb"):
        pass
    try:
        deadline = time.monotonic() + 5.0

        def check_progress(status: int, remaining: int, total: int) -> None:
            if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) and time.monotonic() >= deadline:
                raise DatabaseBackupError("The database stayed locked during backup; close other instances and retry.")

        with closing(sqlite3.connect(path)) as destination:
            connection.backup(destination, pages=256, progress=check_progress, sleep=0.05)
            if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise DatabaseBackupError("The database backup failed its integrity check.")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path
