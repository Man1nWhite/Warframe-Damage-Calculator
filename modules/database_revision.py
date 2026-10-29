"""Application data revision stored in SQLite's user_version field."""
from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

# Revision 1 rebuilt DE elemental indices and parsed faction-mod effects.
# Revision 2 reparses official mod effects using the safer direct-damage rules.
# Revision 3 guards name collisions and repairs an unedited Grimoire export row.
# Revision 4 imports export index 13 as Void and repairs matching legacy rows.
# This is a data revision as well as a schema version: a structurally valid
# older database can still contain incorrect values.
CURRENT_DATABASE_REVISION = 4


class UnsupportedDatabaseRevision(RuntimeError):
    """A newer app has written a database this version cannot safely update."""


class OrphanedDatabaseSidecar(sqlite3.OperationalError):
    """A missing or empty main database has a potentially recoverable sidecar."""


def database_has_contents(db_path: str | Path) -> bool:
    """Check a file without letting SQLite discard an orphaned journal or WAL.

    Opening a missing or zero-byte main database can cause SQLite to delete
    existing ``-wal``, ``-shm`` or ``-journal`` files. Treat even an empty
    sidecar as an active/ambiguous state: preserve it and require review.
    When the main database is nonempty, SQLite may safely inspect its sidecars
    in the usual way. ``:memory:`` remains an independent in-memory database.
    """
    if str(db_path) == ":memory:":
        return False
    path = Path(db_path)
    try:
        try:
            info = path.stat()
        except FileNotFoundError:
            info = None
            # A dangling database symlink is an existing user-owned entry, not
            # permission to create its target or treat it as a first run.
            try:
                link = path.lstat()
            except FileNotFoundError:
                link = None
            if link is not None and stat.S_ISLNK(link.st_mode):
                raise sqlite3.OperationalError(f"The database path is a dangling symbolic link: {path}") from None
        if info is not None:
            if not stat.S_ISREG(info.st_mode):
                raise sqlite3.OperationalError(f"The database path is not a regular file: {path}")
            if info.st_size:
                return True

        # A symlink can put the database entry and its real SQLite sidecars in
        # different directories; protect both spellings while the main is empty.
        for base in {path.absolute(), path.resolve()}:
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = base.with_name(base.name + suffix)
                try:
                    sidecar.lstat()  # Includes dangling symlinks and zero-byte files.
                except FileNotFoundError:
                    continue
                raise OrphanedDatabaseSidecar(
                    f"Database {path} is missing or empty, but SQLite sidecar {sidecar} exists. "
                    "No database was opened or rebuilt. Close other instances and preserve the "
                    "main file and all sidecars together for recovery before retrying."
                )
        return False
    except OSError as exc:
        raise sqlite3.OperationalError(f"Cannot inspect the database path {path}: {exc}") from exc
    except RuntimeError as exc:
        raise sqlite3.OperationalError(f"Cannot resolve the database path {path}: {exc}") from exc


def database_revision(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def require_supported_revision(connection: sqlite3.Connection) -> int:
    revision = database_revision(connection)
    if revision > CURRENT_DATABASE_REVISION:
        raise UnsupportedDatabaseRevision(
            f"Database revision {revision} is newer than this app supports "
            f"({CURRENT_DATABASE_REVISION}); it has not been modified."
        )
    return revision
