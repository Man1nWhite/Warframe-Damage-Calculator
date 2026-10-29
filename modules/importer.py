from __future__ import annotations

import json
import math
import sqlite3
import stat
import zipfile
from collections.abc import Callable, Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, TypeVar, cast

import openpyxl

from .constants import DAMAGE_TYPES, JSON_DAMAGE_INDEX_MAP, WEAPON_SLOT_MAP
from .database_backup import create_database_backup
from .database_revision import CURRENT_DATABASE_REVISION, require_supported_revision
from .export_safety import locked_exports
from .mod_effect_policy import is_supported_export_mod
from .mod_parser import parse_effects
from .weapon_export_policy import order_export_weapons


def create_schema(connection: sqlite3.Connection) -> None:
    # executescript implicitly commits; execute the static DDL statements
    # separately so the caller can roll the entire rebuild back.
    schema = """
        CREATE TABLE IF NOT EXISTS weapons (
            weapon TEXT PRIMARY KEY,
            unique_name TEXT,
            product_category TEXT,
            slot_group TEXT,
            dmg REAL NOT NULL,
            impact REAL NOT NULL DEFAULT 0,
            punc REAL NOT NULL DEFAULT 0,
            slash REAL NOT NULL DEFAULT 0,
            heat REAL NOT NULL DEFAULT 0,
            cold REAL NOT NULL DEFAULT 0,
            elec REAL NOT NULL DEFAULT 0,
            toxin REAL NOT NULL DEFAULT 0,
            blast REAL NOT NULL DEFAULT 0,
            rad REAL NOT NULL DEFAULT 0,
            gas REAL NOT NULL DEFAULT 0,
            mag REAL NOT NULL DEFAULT 0,
            viral REAL NOT NULL DEFAULT 0,
            corr REAL NOT NULL DEFAULT 0,
            void REAL NOT NULL DEFAULT 0,
            critchan REAL NOT NULL DEFAULT 0,
            critmult REAL NOT NULL DEFAULT 0,
            statchan REAL NOT NULL DEFAULT 0,
            firerate REAL NOT NULL DEFAULT 0,
            multi REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_weapons_name ON weapons(weapon COLLATE NOCASE);

        CREATE TABLE IF NOT EXISTS mods (
            unique_name TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mod_type TEXT,
            compat_name TEXT,
            slot_group TEXT,
            polarity TEXT,
            rarity TEXT,
            fusion_limit INTEGER NOT NULL DEFAULT 0,
            base_drain INTEGER NOT NULL DEFAULT 0,
            description TEXT,
            effect_summary TEXT,
            supported INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_mods_name ON mods(name COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_mods_slot_group ON mods(slot_group);

        CREATE TABLE IF NOT EXISTS mod_effects (
            unique_name TEXT NOT NULL,
            rank INTEGER NOT NULL,
            position INTEGER NOT NULL,
            effect_code TEXT NOT NULL,
            effect_value REAL NOT NULL,
            effect_text TEXT NOT NULL,
            PRIMARY KEY (unique_name, rank, position)
        );
        CREATE INDEX IF NOT EXISTS idx_mod_effects_unique_rank ON mod_effects(unique_name, rank);
        """
    for statement in schema.split(";"):
        if statement.strip():
            connection.execute(statement)


def upsert_weapon_rows(connection: sqlite3.Connection, rows: list[dict[str, float | str]]) -> None:
    sql = """
        INSERT INTO weapons (
            weapon, unique_name, product_category, slot_group, dmg, impact, punc, slash, heat, cold, elec, toxin, blast,
            rad, gas, mag, viral, corr, void, critchan, critmult, statchan, firerate, multi
        ) VALUES (
            :weapon, :unique_name, :product_category, :slot_group, :dmg, :impact, :punc, :slash, :heat, :cold, :elec, :toxin, :blast,
            :rad, :gas, :mag, :viral, :corr, :void, :critchan, :critmult, :statchan, :firerate, :multi
        )
        ON CONFLICT(weapon) DO UPDATE SET
            unique_name = excluded.unique_name,
            product_category = excluded.product_category,
            slot_group = excluded.slot_group,
            dmg = excluded.dmg,
            impact = excluded.impact,
            punc = excluded.punc,
            slash = excluded.slash,
            heat = excluded.heat,
            cold = excluded.cold,
            elec = excluded.elec,
            toxin = excluded.toxin,
            blast = excluded.blast,
            rad = excluded.rad,
            gas = excluded.gas,
            mag = excluded.mag,
            viral = excluded.viral,
            corr = excluded.corr,
            void = excluded.void,
            critchan = excluded.critchan,
            critmult = excluded.critmult,
            statchan = excluded.statchan,
            firerate = excluded.firerate,
            multi = excluded.multi
    """
    connection.executemany(sql, rows)


def replace_mod_rows(connection: sqlite3.Connection, mod_rows: list[dict[str, object]],
                     effect_rows: list[dict[str, object]], *,
                     preserve_unmatched: bool = False) -> None:
    if preserve_unmatched:
        # Refresh exported mods without deleting user-added entries absent
        # from the saved export. Effects of refreshed mods are rebuilt.
        keys = [(row["unique_name"],) for row in mod_rows]
        connection.executemany("DELETE FROM mod_effects WHERE unique_name = ?", keys)
        connection.executemany("DELETE FROM mods WHERE unique_name = ?", keys)
    else:
        connection.execute("DELETE FROM mod_effects")
        connection.execute("DELETE FROM mods")
    connection.executemany(
        """
        INSERT INTO mods (
            unique_name, name, mod_type, compat_name, slot_group, polarity, rarity, fusion_limit,
            base_drain, description, effect_summary, supported
        ) VALUES (
            :unique_name, :name, :mod_type, :compat_name, :slot_group, :polarity, :rarity, :fusion_limit,
            :base_drain, :description, :effect_summary, :supported
        )
        """,
        mod_rows,
    )
    connection.executemany(
        """
        INSERT INTO mod_effects (
            unique_name, rank, position, effect_code, effect_value, effect_text
        ) VALUES (
            :unique_name, :rank, :position, :effect_code, :effect_value, :effect_text
        )
        """,
        effect_rows,
    )


def _empty_damage_row() -> dict[str, float | str]:
    """A weapon row with every damage type zeroed.

    Rows mix numbers and text (``weapon``, ``unique_name``), so the value type
    is the honest ``float | str`` even though this helper only seeds floats.
    """
    return {damage_type.lower(): 0.0 for damage_type in DAMAGE_TYPES}


_CachedT = TypeVar("_CachedT")


def _cached_source_parse(path: str | Path,
                         reader: Callable[[Path], object],
                         cache: Callable[..., _CachedT]) -> _CachedT:
    """Parse a source file once per (resolved path, mtime_ns, size).

    ``reader`` produces the fresh parse and ``cache`` is the memoized wrapper
    around it, which flattens the result into hashable tuples. Callers re-parse
    the same bundled exports every time they rebuild or migrate a database;
    this keeps that to one parse per unchanged file. A missing file is handed
    straight to ``reader`` so the reader raises its own error rather than this
    helper inventing one.
    """
    resolved = Path(path).resolve()
    try:
        stat_result = resolved.stat()
    except OSError:
        # Nothing to memoize; let the reader raise its own (more specific)
        # error for the missing file. The cast only satisfies the unflattened
        # return type, which no caller ever sees on this path.
        return cast(_CachedT, reader(resolved))
    return cache(str(resolved), stat_result.st_mtime_ns, stat_result.st_size)


@lru_cache(maxsize=4)
def _spreadsheet_rows_cached(
    path: str, mtime_ns: int, size: int,
) -> tuple[tuple[tuple[str, float | str], ...], ...]:
    """Parse the workbook once per (path, mtime, size); values are hashable."""
    rows = _read_spreadsheet(Path(path))
    _reject_non_finite(rows)
    return tuple(tuple(row.items()) for row in rows)


def rows_from_spreadsheet(xlsx_path: str | Path) -> list[dict[str, float | str]]:
    """Rows of the ``Weapon-Data`` sheet.

    Reading the workbook with openpyxl is the most expensive single step of a
    rebuild (about 0.18 s for the bundled file, against ~0.1 s for the ZIP
    exports), and callers routinely parse the same unchanged file several
    times in one process. The parse is therefore memoized on the file's
    identity: changing the workbook (its mtime or size) invalidates the entry,
    and each call returns fresh dicts so a caller cannot corrupt the cached
    rows.
    """
    cached = _cached_source_parse(
        xlsx_path, _read_spreadsheet, _spreadsheet_rows_cached)
    return [dict(items) for items in cached]


def _read_spreadsheet(xlsx_path: Path) -> list[dict[str, float | str]]:
    with closing(openpyxl.load_workbook(xlsx_path, data_only=True)) as workbook:
        sheet = workbook["Weapon-Data"]
        output: list[dict[str, float | str]] = []

        for row in sheet.iter_rows(min_row=3, values_only=True):
            if not row or not row[0]:
                continue
            payload = _empty_damage_row()
            payload.update(
                {
                    "weapon": str(row[0]),
                    "unique_name": "",
                    "product_category": "",
                    "slot_group": _slot_group_from_category(""),
                    "dmg": float(row[1] or 0),
                    "critchan": float(row[16] or 0),
                    "critmult": float(row[17] or 0),
                    "statchan": float(row[18] or 0),
                    "firerate": float(row[19] or 0),
                    "multi": float(row[20] or 0),
                }
            )
            for idx, damage_type in enumerate(DAMAGE_TYPES, start=2):
                payload[damage_type.lower()] = float(row[idx] or 0)
            output.append(payload)

        return output


@lru_cache(maxsize=4)
def _weapons_cached(
    path: str, mtime_ns: int, size: int,
) -> tuple[tuple[tuple[str, float | str], ...], ...]:
    """Memoized parse of the weapon export; see ``rows_from_cleaned_json``."""
    rows = _read_weapons(Path(path))
    _reject_non_finite(rows)
    return tuple(tuple(row.items()) for row in rows)


def rows_from_cleaned_json(zip_path: str | Path) -> list[dict[str, float | str]]:
    """Rows of the weapon export.

    Memoized on (path, mtime, size) like the other source parsers, for the same
    reason: rebuilds and migrations read the bundled exports repeatedly. Each
    call still returns independent dicts.
    """
    cached = _cached_source_parse(zip_path, _read_weapons, _weapons_cached)
    return [dict(items) for items in cached]


def _read_weapons(zip_path: Path) -> list[dict[str, float | str]]:
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        json_name = next((name for name in names if name.lower().endswith(".json")), None)
        if json_name is None:
            raise ValueError(f"Weapon export ZIP contains no JSON: {zip_path}")
        payload = json.loads(archive.read(json_name))

    if not isinstance(payload, dict) or not isinstance(payload.get("ExportWeapons"), list):
        raise ValueError(f"Weapon export is missing its ExportWeapons list: {zip_path}")
    weapons = payload["ExportWeapons"]
    output: list[dict[str, float | str]] = []
    for item in weapons:
        name = item.get("name")
        if not name:
            continue

        category = str(item.get("productCategory") or "")
        damage_per_shot = item.get("damagePerShot") or []
        row = _empty_damage_row()
        row.update(
            {
                "weapon": str(name),
                "unique_name": str(item.get("uniqueName") or ""),
                "product_category": category,
                "slot_group": _slot_group_from_category(category),
                "dmg": float(item.get("totalDamage") or 0),
                "critchan": float(item.get("criticalChance") or 0),
                "critmult": float(item.get("criticalMultiplier") or 0),
                "statchan": float(item.get("procChance") or 0),
                "firerate": float(item.get("fireRate") or 0),
                "multi": float(item.get("multishot") or 0),
            }
        )

        for damage_type, index in JSON_DAMAGE_INDEX_MAP.items():
            if index < len(damage_per_shot):
                row[damage_type.lower()] = float(damage_per_shot[index] or 0)

        output.append(row)

    return order_export_weapons(output)


class _CachedMods(NamedTuple):
    """Hashable form of a parsed upgrade export; see ``_mods_cached``."""

    mods: tuple[tuple[tuple[str, object], ...], ...]
    effects: tuple[tuple[tuple[str, object], ...], ...]
    stats: tuple[tuple[tuple[str, int], tuple[str, ...]], ...]


@lru_cache(maxsize=4)
def _mods_cached(path: str, mtime_ns: int, size: int) -> _CachedMods:
    """Memoized parse of the upgrade export; see ``mods_from_cleaned_json``."""
    mods, effects, stats = _read_mods(Path(path))
    _reject_non_finite(mods)
    _reject_non_finite(effects)
    return _CachedMods(
        tuple(tuple(row.items()) for row in mods),
        tuple(tuple(row.items()) for row in effects),
        tuple(stats.items()),
    )


def mods_from_cleaned_json(
    zip_path: str | Path,
    *,
    source_stats: dict[tuple[str, int], tuple[str, ...]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Parsed mod rows and effect rows from the upgrade export.

    Parsing the export re-runs the effect parser over every rank line of every
    mod (about 0.12 s for the bundled file). The result depends only on the
    file, so it is memoized on (path, mtime, size) exactly like
    ``rows_from_spreadsheet``; callers still receive fresh dicts and their own
    ``source_stats`` copy.
    """
    cached = _cached_source_parse(zip_path, _read_mods, _mods_cached)
    mods: list[dict[str, object]] = [dict(items) for items in cached.mods]
    effects: list[dict[str, object]] = [dict(items) for items in cached.effects]
    stats = dict(cached.stats)
    if source_stats is not None:
        source_stats.update(stats)
    return mods, effects


def _read_mods(
    zip_path: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]],
          dict[tuple[str, int], tuple[str, ...]]]:
    source_stats: dict[tuple[str, int], tuple[str, ...]] = {}
    with zipfile.ZipFile(zip_path) as archive:
        payload = json.loads(archive.read("ExportUpgrades_en_Cleaned.json"))

    if not isinstance(payload, dict) or not isinstance(payload.get("ExportUpgrades"), list):
        raise ValueError(f"Upgrade export is missing its ExportUpgrades list: {zip_path}")
    upgrades = payload["ExportUpgrades"]
    mod_rows: list[dict[str, object]] = []
    effect_rows: list[dict[str, object]] = []

    for item in upgrades:
        unique_name = str(item.get("uniqueName") or "")
        name = str(item.get("name") or "")
        if not unique_name or not name:
            continue

        slot_group = _slot_group_from_mod(item)
        rank_entries = item.get("levelStats") or []
        supported = False
        summary_bits: list[str] = []

        for rank, entry in enumerate(rank_entries):
            stat_lines = entry.get("stats") or []
            if source_stats is not None:
                source_stats[(unique_name, rank)] = tuple(str(line) for line in stat_lines)
            next_position = 1
            for stat_line in stat_lines:
                effects = parse_effects(str(stat_line))
                if effects:
                    supported = True
                    summary_bits.extend(effect.text for effect in effects if effect.text not in summary_bits)
                for effect in effects:
                    effect_rows.append(
                        {
                            "unique_name": unique_name,
                            "rank": rank,
                            "position": next_position,
                            "effect_code": effect.code,
                            "effect_value": effect.value,
                            "effect_text": effect.text,
                        }
                    )
                    next_position += 1

        description = " ".join(item.get("description") or [])
        mod_rows.append(
            {
                "unique_name": unique_name,
                "name": name,
                "mod_type": str(item.get("type") or ""),
                "compat_name": str(item.get("compatName") or ""),
                "slot_group": slot_group,
                "polarity": str(item.get("polarity") or ""),
                "rarity": str(item.get("rarity") or ""),
                "fusion_limit": int(item.get("fusionLimit") or 0),
                "base_drain": int(item.get("baseDrain") or 0),
                "description": description,
                "effect_summary": ", ".join(summary_bits),
                "supported": 1 if (supported and is_supported_export_mod(unique_name)
                                   and slot_group in {"PRIMARY", "SECONDARY", "MELEE", "ANY"}) else 0,
            }
        )

    return mod_rows, effect_rows, source_stats


def _slot_group_from_category(category: str) -> str:
    return WEAPON_SLOT_MAP.get(category, "PRIMARY")


def _slot_group_from_mod(item: dict) -> str:
    mod_type = str(item.get("type") or "").upper()
    compat = str(item.get("compatName") or "").upper()

    if mod_type == "PRIMARY":
        return "PRIMARY"
    if mod_type == "SECONDARY":
        return "SECONDARY"
    if mod_type == "MELEE":
        return "MELEE"

    # Tome compatibility alone is not a generic primary slot (Grimoire is a
    # secondary; Noctua is exalted). Without an explicit type, leave it OTHER.
    if compat in {"RIFLE", "SHOTGUN", "BOW", "SNIPER", "ASSAULT RIFLE", "PRIMARY"}:
        return "PRIMARY"
    if compat in {"PISTOL", "SECONDARY"}:
        return "SECONDARY"
    if compat in {"MELEE", "CLAWS", "DAGGERS", "POLEARMS", "SWORDS", "THROWN MELEE", "ARCHMELEE"}:
        return "MELEE"
    if compat in {"ANY", ""}:
        return "ANY"

    return "OTHER"


@dataclass(frozen=True)
class ImportPayload:
    spreadsheet_weapons: list[dict[str, float | str]]
    export_weapons: list[dict[str, float | str]]
    mods: list[dict[str, object]]
    effects: list[dict[str, object]]
    # Original rank lines are retained for legacy coverage checks even when
    # the current parser deliberately does not model a former false positive.
    source_mod_stats: dict[tuple[str, int], tuple[str, ...]] = field(default_factory=dict)


def _reject_non_finite(rows: Iterable[Mapping[str, object]]) -> None:
    """Refuse NaN/inf values before they reach the database.

    Called from the source parsers, so an unchanged file is scanned once per
    process instead of once per rebuild or migration reading it.
    """
    for row in rows:
        if any(isinstance(value, (int, float)) and not math.isfinite(value)
               for value in row.values()):
            raise ValueError("Export data contains a non-finite number.")


def load_import_payload(
    cleaned_weapons_zip_path: str | Path,
    cleaned_upgrades_zip_path: str | Path,
    spreadsheet_xlsx_path: str | Path | None = None,
) -> ImportPayload:
    """Parse and validate all source files before changing a database."""
    spreadsheet = (rows_from_spreadsheet(spreadsheet_xlsx_path)
                   if spreadsheet_xlsx_path and Path(spreadsheet_xlsx_path).exists()
                   else [])
    # Keep the shared lock from the marker check until both ZIPs have been
    # completely parsed; otherwise publication could replace one half between
    # the two reads and feed a mixed pair to the database rebuild.
    with locked_exports(cleaned_weapons_zip_path, cleaned_upgrades_zip_path):
        weapons = rows_from_cleaned_json(cleaned_weapons_zip_path)
        source_mod_stats: dict[tuple[str, int], tuple[str, ...]] = {}
        mods, effects = mods_from_cleaned_json(
            cleaned_upgrades_zip_path, source_stats=source_mod_stats)
    if not weapons or not mods or not effects:
        raise ValueError("Export data is incomplete: weapons, mods and parsed mod effects are required.")
    return ImportPayload(spreadsheet, weapons, mods, effects, source_mod_stats)


def apply_import_payload(connection: sqlite3.Connection, payload: ImportPayload,
                         *, preserve_unmatched_mods: bool = False) -> None:
    """Write parsed data within the caller's transaction."""
    upsert_weapon_rows(connection, payload.spreadsheet_weapons)
    upsert_weapon_rows(connection, payload.export_weapons)
    replace_mod_rows(connection, payload.mods, payload.effects,
                     preserve_unmatched=preserve_unmatched_mods)
    connection.execute(f"PRAGMA user_version = {CURRENT_DATABASE_REVISION}")


def apply_mod_import_payload(connection: sqlite3.Connection, payload: ImportPayload) -> None:
    """Reparse exported mods without rewriting weapon or unmatched custom rows.

    The caller owns the transaction and must validate source coverage first.
    """
    replace_mod_rows(connection, payload.mods, payload.effects, preserve_unmatched=True)
    connection.execute(f"PRAGMA user_version = {CURRENT_DATABASE_REVISION}")


class DatabaseRebuildError(RuntimeError):
    """A full rebuild failed; ``backup_path`` identifies any retained copy."""

    def __init__(self, message: str, backup_path: Path | None = None) -> None:
        super().__init__(message)
        self.backup_path = backup_path


def build_database(
    db_path: str | Path,
    cleaned_weapons_zip_path: str | Path,
    cleaned_upgrades_zip_path: str | Path,
    spreadsheet_xlsx_path: str | Path | None = None,
) -> Path | None:
    """Fully rebuild the catalog and return the existing database's backup.

    Parse sources first, snapshot an existing database via SQLite's backup
    API, and only then start a write transaction. Existing custom mod/effect
    rows are replaced, but the backup retains them. A new database has no
    previous state to back up. Concurrent readers/writers are not globally
    locked; changes detected between the snapshot and write abort the rebuild.
    """
    payload = load_import_payload(cleaned_weapons_zip_path, cleaned_upgrades_zip_path,
                                  spreadsheet_xlsx_path)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if str(db_path) == ":memory:":
        with closing(sqlite3.connect(":memory:")) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            create_schema(connection)
            apply_import_payload(connection, payload)
        return None

    # Reserve a new filename exclusively, or treat any pre-existing file as a
    # database to back up. mode=rw avoids recreating it if it disappears later.
    try:
        with db_path.open("xb"):
            pass
    except FileExistsError:
        pass
    original_stat = db_path.stat()
    if not stat.S_ISREG(original_stat.st_mode):
        raise DatabaseRebuildError(f"The database path is not a regular file: {db_path}")

    backup_path: Path | None = None
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=rw", uri=True)) as connection:
        # Observe the version before testing whether a placeholder is empty:
        # a concurrent commit during that test must trigger the later guard.
        before = connection.execute("PRAGMA data_version").fetchone()[0]
        revision = require_supported_revision(connection)
        # GUI startup can leave a zero-byte SQLite placeholder. It has no
        # prior data to save, unless committed WAL pages already exist.
        page_count = connection.execute("PRAGMA page_count").fetchone()[0]
        size = db_path.stat().st_size
        is_existing = bool(size or page_count)
        if is_existing:
            try:
                backup_path = create_database_backup(connection, db_path,
                                                     label=f"pre-rebuild-v{revision}")
            except Exception as exc:
                raise DatabaseRebuildError(
                    f"Could not back up the existing database; rebuild was not started: {exc}"
                ) from exc
        try:
            # SQLite's transaction context commits/rolls back, but does not
            # close. The outer context deterministically releases it.
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                after = connection.execute("PRAGMA data_version").fetchone()[0]
                current_stat = db_path.stat()
                replaced = ((original_stat.st_dev, original_stat.st_ino)
                            != (current_stat.st_dev, current_stat.st_ino))
                if before != after or replaced or require_supported_revision(connection) != revision:
                    raise DatabaseRebuildError(
                        "The database changed during backup; close other instances and retry.", backup_path)
                create_schema(connection)
                apply_import_payload(connection, payload)
        except Exception as exc:
            if backup_path is None:
                raise
            raise DatabaseRebuildError(
                f"Database rebuild failed; no rebuild changes were committed: {exc}\nBackup: {backup_path}",
                backup_path,
            ) from exc
    return backup_path
