"""Create a consistent, uniquely named SQLite backup before data changes."""
from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

# How long a locked source database may block the backup before it is
# reported as an error. Exposed as a module constant so tests can shrink it:
# waiting out the real five seconds is correct in production but pointless in
# a unit test that is asserting the timeout path.
BACKUP_LOCK_DEADLINE_SECONDS = 5.0

# Busy timeout used on the source connection while the snapshot runs.
# ``sqlite3.backup`` honours the source connection's busy handler, so without
# this the wait is governed by whatever timeout the caller connected with
# (five seconds by default, but a caller is free to pass sixty) and the
# deadline below could be exceeded -- or never noticed -- because a single
# ``sqlite3_backup_step`` blocks inside SQLite instead of returning BUSY.
# A short timeout keeps each step observable so the deadline and its error
# message actually bound the wait.
BACKUP_BUSY_TIMEOUT_MS = 50


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
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = backup_dir / f"{db_path.stem}-{label}-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    # Reserve a fresh filename and never overwrite an earlier backup.
    with path.open("xb"):
        pass
    try:
        deadline = time.monotonic() + BACKUP_LOCK_DEADLINE_SECONDS

        def check_progress(status: int, remaining: int, total: int) -> None:
            if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) and time.monotonic() >= deadline:
                raise DatabaseBackupError("The database stayed locked during backup; close other instances and retry.")

        previous_busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        try:
            connection.execute(f"PRAGMA busy_timeout = {BACKUP_BUSY_TIMEOUT_MS}")
            with closing(sqlite3.connect(path)) as destination:
                connection.backup(destination, pages=256, progress=check_progress, sleep=0.05)
                if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise DatabaseBackupError("The database backup failed its integrity check.")
        finally:
            connection.execute(f"PRAGMA busy_timeout = {int(previous_busy_timeout)}")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path
