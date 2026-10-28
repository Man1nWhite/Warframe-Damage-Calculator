"""Application data revision stored in SQLite's user_version field."""
from __future__ import annotations

import sqlite3

# Revision 1 rebuilt DE elemental indices and parsed faction-mod effects.
# Revision 2 reparses official mod effects using the safer direct-damage rules.
# Revision 3 guards name collisions and repairs an unedited Grimoire export row.
# This is a data revision as well as a schema version: a structurally valid
# older database can still contain incorrect values.
CURRENT_DATABASE_REVISION = 3


class UnsupportedDatabaseRevision(RuntimeError):
    """A newer app has written a database this version cannot safely update."""


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
