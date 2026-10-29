"""Safely upgrade existing local data using the user's saved exports.

Revision zero databases predate corrected elemental indices and faction mods;
revision one also needs safer direct-damage mod parsing. Revision two can hold
an incorrectly selected Grimoire export entry. Revisions zero through three
may have lost the Void component of exported weapons such as Sirocco. A
migration takes an SQLite-consistent backup and applies guarded updates
transactionally, offline.
"""
from __future__ import annotations

import sqlite3
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from .database_backup import DatabaseBackupError, create_database_backup
from .database_revision import (
    CURRENT_DATABASE_REVISION,
    UnsupportedDatabaseRevision,
    database_has_contents,
    require_supported_revision,
)
from .database_schema_safety import quote_identifier, validate_catalog_schema
from .importer import (
    ImportPayload,
    apply_import_payload,
    apply_mod_import_payload,
    load_import_payload,
    upsert_weapon_rows,
)
from .mod_parser import IGNORE_TERMS, PHRASE_MAP, TOKEN_PATTERN, source_effect_fragments
from .weapon_export_policy import GRIMOIRE_DOPPELGANGER_ID, GRIMOIRE_NAME, GRIMOIRE_PLAYER_ID

# This known affected official ID lets us fail closed even when a partial or
# mismatched saved export omits Sirocco's Void component entirely. Other Void
# rows present in an export are repaired generically by matching both IDs and
# all other modeled fields.
_KNOWN_VOID_WEAPON_IDS = {
    "/Lotus/Weapons/Operator/Pistols/DrifterPistol/DrifterPistolPlayerWeapon",
}

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


def _effect_rank(row: dict[str, object]) -> int:
    """The rank of a parsed effect row, validated rather than coerced.

    Payload rows are heterogeneous dictionaries, so the column type is only
    known by convention; a wrong value should fail loudly here instead of
    silently importing a mis-ranked effect.
    """
    rank = row["rank"]
    if isinstance(rank, bool) or not isinstance(rank, int):
        raise TypeError(f"effect rank must be an int, not {type(rank).__name__}")
    return rank


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
    parsed_texts = {(str(row["unique_name"]), _effect_rank(row), str(row["effect_text"]))
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


def _weapon_matches_source(old: dict[str, object], source: dict[str, float | str],
                           *, legacy_elements: bool) -> bool:
    ordinary_columns = _REQUIRED_COLUMNS["weapons"] - {"void", "heat", "cold", "elec"}
    if any(old[column] != source[column] for column in ordinary_columns):
        return False
    elements = (old["heat"], old["cold"], old["elec"])
    current = (source["heat"], source["cold"], source["elec"])
    original = (source["elec"], source["heat"], source["cold"])
    return elements == current or (legacy_elements and elements == original)


def _prepare_void_corrections(connection: sqlite3.Connection, payload: ImportPayload,
                              *, legacy_elements: bool = False) -> list[tuple[float, str, str]]:
    """Find missing Void values without replacing edited or unrelated rows.

    Only an official row with a zero Void value and an identical source row
    (apart from the known missing component) is safe to repair. For revision
    zero, accept either the original rotated element indices or already-fixed
    elements; the older full import will do the actual repair. A nonzero Void
    value may be a user edit, so leave it untouched. Known affected IDs with
    no matching Void source must not silently be marked current.
    """
    by_identity = {(str(row["weapon"]), str(row["unique_name"])): row
                   for row in payload.export_weapons if float(row["void"]) > 0}
    columns = sorted(_REQUIRED_COLUMNS["weapons"])
    corrections: list[tuple[float, str, str]] = []
    for found in connection.execute(f"SELECT {','.join(columns)} FROM weapons"):
        old = dict(zip(columns, found, strict=True))
        name, unique = str(old["weapon"]), str(old["unique_name"] or "")
        if not unique.startswith("/Lotus/") or old["void"] != 0:
            continue
        source = by_identity.get((name, unique))
        if source is None:
            if unique in _KNOWN_VOID_WEAPON_IDS:
                raise DatabaseMigrationError(
                    f"{name} Void repair needs a matching saved export with its Void damage. "
                    "Restore a matching export or retain your edited row and repair it manually."
                )
            continue
        if not _weapon_matches_source(old, source, legacy_elements=legacy_elements):
            raise DatabaseMigrationError(
                f"{name} appears modified, or its saved export no longer matches the existing row; "
                "automatic Void repair was not applied. Preserve your changes and restore a matching export."
            )
        corrections.append((float(source["void"]), name, unique))
    return corrections


def _apply_void_corrections(connection: sqlite3.Connection,
                            corrections: list[tuple[float, str, str]]) -> None:
    # Do not replace the rest of the row (or any extra user columns).
    connection.executemany(
        "UPDATE weapons SET void=? WHERE weapon=? AND unique_name=?", corrections)


def _legacy_fragment_effect(fragment: str) -> tuple[str, float] | None:
    """Reconstruct an effect accepted by the original revision-0 parser.

    Older parsers used prefix/suffix matches and accepted conditional lines;
    those false positives are legitimate *legacy* rows to remove, not evidence
    of a user edit. The modern parser's output is also accepted below.
    """
    match = TOKEN_PATTERN.match(fragment)
    if match is None:
        return None
    raw = match.group(1).lower()
    label = fragment[match.end():].strip().lower()
    if any(term in label for term in IGNORE_TERMS):
        return None
    factions = {
        "damage to grineer": "BANE_GRINEER",
        "damage to corpus": "BANE_CORPUS",
        "damage to infested": "BANE_INFESTED",
        "damage to corrupted": "BANE_CORRUPTED",
    }
    code = next((value for phrase, value in factions.items() if phrase in label), None)
    if code is None:
        normalized = label.removesuffix(" damage").strip()
        code = next((value for phrase, value in PHRASE_MAP.items()
                     if normalized == phrase or normalized.endswith(f" {phrase}")
                     or normalized.startswith(f"{phrase} ")), None)
        if normalized == "damage":
            code = "TRUE"
    if code is None:
        return None
    value = float(raw[1:]) if raw.startswith("x") else float(raw.rstrip("%")) / 100.0
    return code, value


def _prepare_legacy_import_payload(connection: sqlite3.Connection, payload: ImportPayload,
                                   *, include_weapons: bool) -> ImportPayload:
    """Protect custom collisions and reject identifiable edits before reimport.

    Revisions 0/1 must reparse official mod effects, and revision 0 must also
    correct the rotated weapon indices. A broad upsert used to silently
    replace a custom weapon sharing an exported name, or a modified official
    row. Only update source-matching official weapon rows; preserve custom
    collisions and fail closed on identifiable official edits. Existing legacy
    parser outputs and the new parser's outputs are both valid mod effects.
    """
    protected_weapons: set[str] = set()
    if include_weapons:
        columns = sorted(_REQUIRED_COLUMNS["weapons"])
        source_by_id = {(str(row["weapon"]), str(row["unique_name"])): row
                        for row in payload.export_weapons}
        spreadsheet = {str(row["weapon"]): row for row in payload.spreadsheet_weapons}
        incoming_names = set(spreadsheet) | {name for name, _ in source_by_id}
        for found in connection.execute(f"SELECT {','.join(columns)} FROM weapons"):
            old = dict(zip(columns, found, strict=True))
            name, unique = str(old["weapon"]), str(old["unique_name"] or "")
            if unique.startswith("/Lotus/"):
                source = source_by_id.get((name, unique))
                # Missing official IDs are reported by the coverage check.
                if source is not None and (
                        not _weapon_matches_source(old, source, legacy_elements=True)
                        or old["void"] not in (0, source["void"])):
                    raise DatabaseMigrationError(
                        f"{name} appears modified, or its saved export no longer matches; "
                        "automatic legacy import was not applied. Preserve your changes "
                        "and restore a matching export."
                    )
            elif name in incoming_names:
                original = spreadsheet.get(name)
                unedited_workbook_row = (not unique and original is not None
                                         and all(old[column] == original[column] for column in columns))
                if not unedited_workbook_row:
                    protected_weapons.add(name)

    mods_by_id = {str(row["unique_name"]): row for row in payload.mods}
    mod_columns = ("name", "mod_type", "compat_name", "polarity", "rarity",
                   "fusion_limit", "base_drain", "description")
    protected_mods: set[str] = set()
    for found in connection.execute(f"SELECT unique_name,{','.join(mod_columns)} FROM mods"):
        unique = str(found[0])
        if not unique.startswith("/Lotus/"):
            protected_mods.add(unique)
            continue
        mod_source = mods_by_id.get(unique)
        if mod_source is not None and any(value != mod_source[column]
                                          for column, value in zip(mod_columns, found[1:], strict=True)):
            raise DatabaseMigrationError(
                f"Official mod {unique} appears modified, or its saved export no longer matches; "
                "automatic legacy import was not applied. Preserve your changes and restore a matching export."
            )

    # Compare each retained effect against either the original parser or the
    # current parser, including its position. Missing/changed source fragments
    # are left to the existing coverage check, which gives a specific error.
    accepted: set[tuple[str, int, int, str, float, str]] = set()
    for row in payload.effects:
        value = row["effect_value"]
        if not isinstance(value, (int, float)):
            raise TypeError("effect value must be numeric")
        accepted.add((str(row["unique_name"]), _effect_rank(row), int(str(row["position"])),
                      str(row["effect_code"]), float(value), str(row["effect_text"])))
    source_fragments: dict[tuple[str, int], set[str]] = {}
    for (unique, rank), lines in payload.source_mod_stats.items():
        position = 1
        fragments: set[str] = set()
        for line in lines:
            for fragment in source_effect_fragments(line):
                fragments.add(fragment)
                parsed = _legacy_fragment_effect(fragment)
                if parsed is not None:
                    code, value = parsed
                    accepted.add((unique, rank, position, code, value, fragment))
                    position += 1
        source_fragments[(unique, rank)] = fragments
    for unique, rank, position, code, value, text in connection.execute(
            "SELECT unique_name,rank,position,effect_code,effect_value,effect_text FROM mod_effects"):
        unique = str(unique)
        key = (unique, int(rank))
        if (not unique.startswith("/Lotus/") or unique not in mods_by_id
                or str(text) not in source_fragments.get(key, set())):
            continue
        if (unique, int(rank), int(position), str(code), float(value), str(text)) not in accepted:
            raise DatabaseMigrationError(
                f"Official mod {unique} rank {rank} appears modified; automatic legacy "
                "import was not applied. Preserve your changes and restore a matching export."
            )

    return replace(
        payload,
        spreadsheet_weapons=[row for row in payload.spreadsheet_weapons
                             if str(row["weapon"]) not in protected_weapons],
        export_weapons=[row for row in payload.export_weapons
                        if str(row["weapon"]) not in protected_weapons],
        mods=[row for row in payload.mods if str(row["unique_name"]) not in protected_mods],
        effects=[row for row in payload.effects if str(row["unique_name"]) not in protected_mods],
    )


def _validate_user_schema_preservation(connection: sqlite3.Connection, revision: int,
                                       payload: ImportPayload, *, writes_weapons: bool,
                                       weapon_names: set[str]) -> None:
    """Refuse side effects or effect annotations we cannot safely retain.

    Legacy reimports rebuild effect rows, whose positions and even presence
    may change after parser fixes. Extra values on those rows cannot be mapped
    reliably to the new effects. Mod rows, by contrast, are updated in place
    so their extra columns survive. User triggers on any written catalog table
    could make arbitrary changes elsewhere, so require manual review first.
    """
    written_tables: set[str] = set()
    if revision in (0, 1):
        written_tables.update(("mods", "mod_effects"))
    if writes_weapons:
        written_tables.add("weapons")

    affected = {"weapons": weapon_names} if writes_weapons else {}
    if revision in (0, 1):
        mod_ids = {str(row["unique_name"]) for row in payload.mods}
        affected.update({"mods": mod_ids, "mod_effects": mod_ids})
    validate_catalog_schema(connection, written_tables=written_tables, affected=affected)

    if revision not in (0, 1):
        return
    extras = [str(row[1]) for row in connection.execute("PRAGMA table_info(mod_effects)")
              if row[1] not in _REQUIRED_COLUMNS["mod_effects"]]
    if not extras:
        return
    # Identifiers originate in an existing SQLite schema, not a query parameter.
    quoted = [quote_identifier(name) for name in extras]
    refreshed = {str(row["unique_name"]) for row in payload.mods}
    for row in connection.execute(f"SELECT unique_name,{','.join(quoted)} FROM mod_effects"):
        if str(row[0]) in refreshed:
            for column, value in zip(extras, row[1:], strict=True):
                if value is not None:
                    raise DatabaseMigrationError(
                        f"Custom mod_effects column {column!r} contains data on a row that "
                        "must be reparsed; automatic migration was not applied. Preserve "
                        "and review those annotations before retrying."
                    )


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
        if not database_has_contents(path):
            return MigrationResult("missing")
        original_stat = path.stat()
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseMigrationError(f"Cannot inspect the database path: {exc}") from exc
    if not stat.S_ISREG(original_stat.st_mode):
        raise DatabaseMigrationError(f"The database path is not a regular file: {path}")

    backup_path: Path | None = None
    connection: sqlite3.Connection | None = None
    try:
        # Recheck before opening in case the file became empty while starting.
        if not database_has_contents(path):
            raise DatabaseMigrationError("The database became missing or empty before opening; retry.")
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
        if revision not in (0, 1, 2, 3):
            raise DatabaseMigrationError(f"No migration is available for revision {revision}.")

        # Parsing may fail, but has no effect on the current database. Require
        # both saved files and no interrupted-publication marker for all paths.
        payload = load_import_payload(cleaned_weapons_zip_path, cleaned_upgrades_zip_path,
                                      spreadsheet_xlsx_path)
        before = connection.execute("PRAGMA data_version").fetchone()[0]
        void_corrections = _prepare_void_corrections(connection, payload,
                                                      legacy_elements=revision == 0)
        legacy_payload = (_prepare_legacy_import_payload(connection, payload,
                                                        include_weapons=revision == 0)
                          if revision in (0, 1) else payload)
        correction = (_prepare_grimoire_correction(connection, payload)
                      if revision in (1, 2) else None)
        if revision == 0:
            weapon_names = {str(row["weapon"]) for row in
                            (*legacy_payload.spreadsheet_weapons, *legacy_payload.export_weapons)}
        else:
            weapon_names = {name for _, name, _ in void_corrections}
            if correction is not None:
                weapon_names.add(str(correction["weapon"]))
        _validate_user_schema_preservation(
            connection, revision, legacy_payload,
            writes_weapons=revision == 0 or correction is not None or bool(void_corrections),
            weapon_names=weapon_names)
        if revision == 0:
            _validate_legacy_coverage(connection, payload)
        elif revision == 1:
            _validate_legacy_coverage(connection, payload, include_weapons=False)
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
            # The full legacy import already uses the corrected Void index.
            apply_import_payload(connection, legacy_payload, preserve_unmatched_mods=True)
        else:
            if revision == 1:
                apply_mod_import_payload(connection, legacy_payload)
            if correction is not None:
                upsert_weapon_rows(connection, [correction])
            _apply_void_corrections(connection, void_corrections)
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
