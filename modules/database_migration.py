"""Safely upgrade existing local data using the user's saved exports.

Revision zero databases predate corrected elemental indices and faction mods;
revision one also needs safer direct-damage mod parsing. Revision two can hold
an incorrectly selected Grimoire export entry. A migration takes an
SQLite-consistent backup and applies guarded updates transactionally, offline.
"""
from __future__ import annotations

import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from .database_backup import DatabaseBackupError, create_database_backup
from .database_revision import (
    CURRENT_DATABASE_REVISION,
    UnsupportedDatabaseRevision,
    require_supported_revision,
)
from .importer import (
    ImportPayload,
    apply_import_payload,
    apply_mod_import_payload,
    load_import_payload,
    upsert_weapon_rows,
)
from .mod_parser import source_effect_fragments
from .weapon_export_policy import GRIMOIRE_DOPPELGANGER_ID, GRIMOIRE_NAME, GRIMOIRE_PLAYER_ID

_REQUIRED_COLUMNS = {
    "weapons": {"weapon", "unique_name", "product_category", "slot_group", "dmg", "impact", "punc", "slash",
                "heat", "cold", "elec", "toxin", "blast", "rad", "gas", "mag", "viral", "corr", "void",
                "critchan", "critmult", "statchan", "firerate", "multi"},
    "mods": {"unique_name", "name", "mod_type", "compat_name", "slot_group", "polarity", "rarity",
             "fusion_limit", "base_drain", "description", "effect_summary", "supported"},
    "mod_effects": {"unique_name", "rank", "position", "effect_code", "effect_value", "effect_text"},
}


@dataclass(frozen=True)
class MigrationResult:
    status: str  # "missing", "current", or "migrated"
    from_revision: int | None = None
    backup_path: Path | None = None


class DatabaseMigrationError(RuntimeError):
    def __init__(self, message: str, backup_path: Path | None = None) -> None:
        super().__init__(message)
        self.backup_path = backup_path


def _backup_database(connection: sqlite3.Connection, db_path: Path,
                     revision: int) -> Path:
    try:
        return create_database_backup(connection, db_path, label=f"pre-v{revision}")
    except DatabaseBackupError as exc:
        raise DatabaseMigrationError(str(exc)) from exc


def _validate_legacy_coverage(connection: sqlite3.Connection, payload: ImportPayload,
                              *, include_weapons: bool = True) -> None:
    # An old or partial export must not mark official-looking rows as fixed
    # while leaving their legacy elemental indices/effect parsing untouched.
    # Truly custom rows are retained; /Lotus/ identifiers are reserved by DE.
    # A spreadsheet-only row lacks export category/identifier metadata, so it
    # is not a safe replacement for a previously imported DE weapon.
    weapon_ids: dict[str, set[str]] = {}
    for row in payload.export_weapons:
        weapon_ids.setdefault(str(row["weapon"]), set()).add(str(row["unique_name"]))
    mod_ids = {str(row["unique_name"]) for row in payload.mods}
    missing_weapons = ([str(name) for name, unique in connection.execute(
        "SELECT weapon, unique_name FROM weapons")
        if str(unique or "").startswith("/Lotus/")
        and str(unique) not in weapon_ids.get(str(name), set())] if include_weapons else [])
    missing_mods = [str(name) for unique, name in connection.execute(
        "SELECT unique_name, name FROM mods")
        if str(unique or "").startswith("/Lotus/") and str(unique) not in mod_ids]
    parsed_texts = {(str(row["unique_name"]), int(row["rank"]), str(row["effect_text"]))
                    for row in payload.effects}
    # An effect can legitimately disappear when the new parser rejects an
    # old false positive (e.g. "Blast Range"). Check every removed fragment,
    # even when another effect survives at the same rank. An empty or
    # unrelated replacement source must not silently erase an older effect.
    missing_ranks: set[tuple[str, int]] = set()
    source_fragments: dict[tuple[str, int], set[str]] = {}
    for unique, rank, effect_text in connection.execute(
            "SELECT unique_name, rank, effect_text FROM mod_effects"):
        key = (str(unique), int(rank))
        if (not key[0].startswith("/Lotus/") or key[0] not in mod_ids
                or (*key, str(effect_text)) in parsed_texts):
            continue
        if key not in source_fragments:
            source_fragments[key] = {
                fragment for line in payload.source_mod_stats.get(key, ())
                for fragment in source_effect_fragments(line)
            }
        if str(effect_text) not in source_fragments[key]:
            missing_ranks.add(key)
    if missing_weapons or missing_mods or missing_ranks:
        examples = ", ".join((missing_weapons + missing_mods +
                              [f"{unique} rank {rank}" for unique, rank in sorted(missing_ranks)])[:5])
        raise DatabaseMigrationError(
            "Saved exports do not cover all existing official-looking rows "
            f"({len(missing_weapons)} weapons, {len(missing_mods)} mods, "
            f"{len(missing_ranks)} mod-effect ranks; e.g. {examples}). "
            "Replace the saved exports with a complete matching set and retry."
        )


def _prepare_grimoire_correction(connection: sqlite3.Connection,
                                 payload: ImportPayload) -> dict[str, float | str] | None:
    """Prepare a targeted repair only when the entire legacy row is unedited.

    A user may have modified an official-looking row; never silently replace
    it. Both the bad source entry and the player entry must be present, and
    every modeled column of the bad entry must match the saved database row.
    """
    columns = sorted(_REQUIRED_COLUMNS["weapons"])
    found = connection.execute(
        f"SELECT {','.join(columns)} FROM weapons WHERE weapon=?", (GRIMOIRE_NAME,)
    ).fetchone()
    if found is None:
        return None
    old = dict(zip(columns, found, strict=True))
    if old["unique_name"] != GRIMOIRE_DOPPELGANGER_ID:
        return None  # a custom, already-correct, or otherwise unrelated row
    candidates = [row for row in payload.export_weapons if row["weapon"] == GRIMOIRE_NAME]
    legacy = [row for row in candidates if row["unique_name"] == GRIMOIRE_DOPPELGANGER_ID]
    player = [row for row in candidates if row["unique_name"] == GRIMOIRE_PLAYER_ID]
    if len(legacy) != 1 or len(player) != 1:
        raise DatabaseMigrationError(
            "Grimoire repair requires both matching player and Doppelganger entries in the saved export."
        )
    if any(old[column] != legacy[0][column] for column in columns):
        raise DatabaseMigrationError(
            "Grimoire appears modified, or its saved export no longer matches the existing row; "
            "automatic repair was not applied. Preserve your changes and restore a matching export."
        )
    return player[0]


def migrate_database(
    db_path: str | Path,
    cleaned_weapons_zip_path: str | Path,
    cleaned_upgrades_zip_path: str | Path,
    spreadsheet_xlsx_path: str | Path | None = None,
) -> MigrationResult:
    """Upgrade a legacy database, preserving unrelated rows and a backup.

    Missing/empty paths are left to the initial-data bootstrap. A future
    revision is never downgraded. Source parsing and validation happen before
    the backup or any database writes; failed writes roll back atomically.
    """
    path = Path(db_path)
    try:
        original_stat = path.stat()
    except FileNotFoundError:
        return MigrationResult("missing")
    except OSError as exc:
        raise DatabaseMigrationError(f"Cannot inspect the database path: {exc}") from exc
    if not stat.S_ISREG(original_stat.st_mode):
        raise DatabaseMigrationError(f"The database path is not a regular file: {path}")
    if original_stat.st_size == 0:
        return MigrationResult("missing")

    backup_path: Path | None = None
    connection: sqlite3.Connection | None = None
    try:
        # mode=rw avoids creating a database if the path disappears mid-startup.
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=rw",
                                     uri=True, timeout=5.0)
        revision = require_supported_revision(connection)
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise DatabaseMigrationError("The existing database failed its integrity check.")
        present = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not _REQUIRED_COLUMNS.keys() <= present:
            raise DatabaseMigrationError("The existing database is missing required tables.")
        for table, columns in _REQUIRED_COLUMNS.items():
            actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if not columns <= actual:
                raise DatabaseMigrationError(f"The existing database is missing required columns in {table}.")
        if revision == CURRENT_DATABASE_REVISION:
            return MigrationResult("current", revision)
        if revision not in (0, 1, 2):
            raise DatabaseMigrationError(f"No migration is available for revision {revision}.")

        # Parsing may fail, but has no effect on the current database. Require
        # both saved files and no interrupted-publication marker for all paths.
        payload = load_import_payload(cleaned_weapons_zip_path, cleaned_upgrades_zip_path,
                                      spreadsheet_xlsx_path)
        before = connection.execute("PRAGMA data_version").fetchone()[0]
        correction = None
        if revision == 0:
            _validate_legacy_coverage(connection, payload)
        elif revision == 1:
            _validate_legacy_coverage(connection, payload, include_weapons=False)
            correction = _prepare_grimoire_correction(connection, payload)
        else:
            correction = _prepare_grimoire_correction(connection, payload)
        backup_path = _backup_database(connection, path, revision)
        connection.execute("BEGIN IMMEDIATE")
        # Detect another app writing after the snapshot. Never silently throw
        # away its changes or report an out-of-date backup as complete.
        after = connection.execute("PRAGMA data_version").fetchone()[0]
        current_stat = path.stat()
        replaced = (original_stat.st_dev, original_stat.st_ino) != (current_stat.st_dev, current_stat.st_ino)
        if before != after or replaced or require_supported_revision(connection) != revision:
            raise DatabaseMigrationError("The database changed during backup; retry after closing other instances.")
        if revision == 0:
            apply_import_payload(connection, payload, preserve_unmatched_mods=True)
        elif revision == 1:
            apply_mod_import_payload(connection, payload)
            if correction is not None:
                upsert_weapon_rows(connection, [correction])
        else:
            if correction is not None:
                upsert_weapon_rows(connection, [correction])
            connection.execute(f"PRAGMA user_version = {CURRENT_DATABASE_REVISION}")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise DatabaseMigrationError("The migrated database failed its integrity check.")
        connection.commit()
        return MigrationResult("migrated", revision, backup_path)
    except UnsupportedDatabaseRevision:
        if connection is not None:
            connection.rollback()
        raise
    except Exception as exc:
        if connection is not None:
            connection.rollback()
        if isinstance(exc, DatabaseMigrationError) and exc.backup_path is not None:
            raise
        message = f"Database migration failed; no migration changes were committed: {exc}"
        if backup_path is not None:
            message += f"\nBackup: {backup_path}"
        raise DatabaseMigrationError(message, backup_path) from exc
    finally:
        if connection is not None:
            connection.close()
