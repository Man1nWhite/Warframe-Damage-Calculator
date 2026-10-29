from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

from .constants import DAMAGE_TYPES, SEARCH_LIMIT
from .database_revision import database_has_contents
from .mod_effect_policy import usable_direct_effect
from .models import Mod, ModEffect, Weapon


class DatabaseSession:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    def connect(self) -> sqlite3.Connection:
        # SQLite may delete an orphaned WAL on the first query against an
        # empty/missing main file. Check before opening or creating it.
        database_has_contents(self.db_path)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


class WeaponRepository(DatabaseSession):
    def search_weapons(self, query: str, limit: int | None = SEARCH_LIMIT) -> list[str]:
        """Weapon names matching ``query``, alphabetically.

        ``limit`` defaults to ``SEARCH_LIMIT`` so a bare query stays bounded,
        but callers that browse the catalogue (the GUI sidebar) pass ``None``:
        silent truncation of the list hid most of the bundled weapons, because
        the cap applies after the alphabetical sort and the database holds far
        more rows than the cap.
        """
        query = query.strip()
        sql = "SELECT weapon FROM weapons"
        params: list[object] = []
        if query:
            sql += " WHERE weapon LIKE ?"
            params.append(f"%{query}%")
        sql += " ORDER BY weapon COLLATE NOCASE"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with closing(self.connect()) as connection:
            try:
                rows = connection.execute(sql, params).fetchall()
            except sqlite3.OperationalError as exc:
                # A brand-new, uninitialised database has no tables yet. Keep
                # first-run browsing empty, but never mistake a lock or damaged
                # partially initialised schema for a successful empty search.
                if str(exc) == "no such table: weapons" and not connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1"
                ).fetchone():
                    return []
                raise
            return [str(row["weapon"]) for row in rows]

    def get_weapon(self, weapon_name: str) -> Weapon | None:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM weapons WHERE weapon = ?", (weapon_name,)).fetchone()
        if row is None:
            return None

        damage = {damage_type: float(row[damage_type.lower()]) for damage_type in DAMAGE_TYPES}
        return Weapon(
            weapon=str(row["weapon"]),
            unique_name=str(row["unique_name"] or ""),
            product_category=str(row["product_category"] or ""),
            slot_group=str(row["slot_group"] or ""),
            dmg=float(row["dmg"]),
            critchan=float(row["critchan"]),
            critmult=float(row["critmult"]),
            statchan=float(row["statchan"]),
            firerate=float(row["firerate"]),
            multi=float(row["multi"]),
            damage=damage,
        )


class ModRepository(DatabaseSession):
    def search_mods(self, query: str, slot_group: str, limit: int = 250) -> list[Mod]:
        query = query.strip()
        params: list[object] = [slot_group]
        sql = (
            "SELECT * FROM mods WHERE supported = 1 AND (slot_group = ? OR slot_group = 'ANY')"
        )
        if query:
            sql += " AND name LIKE ?"
            params.append(f"%{query}%")
        sql += " ORDER BY name COLLATE NOCASE LIMIT ?"
        params.append(limit)
        with closing(self.connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
            return self._visible_mods(connection, rows)

    def list_mods_for_slot(self, slot_group: str, limit: int = 2000) -> list[Mod]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM mods WHERE supported = 1 AND (slot_group = ? OR slot_group = 'ANY') ORDER BY name COLLATE NOCASE LIMIT ?",
                (slot_group, limit),
            ).fetchall()
            return self._visible_mods(connection, rows)

    def _visible_mods(self, connection: sqlite3.Connection, rows: Iterable[sqlite3.Row]) -> list[Mod]:
        """Hide official rows whose only parsed effects are out of scope.

        Legacy exports may have marked e.g. Blast Range as supported damage.
        Recheck their max-rank effects in batches; user-defined rows stay
        available even if their custom labels do not resemble export text.
        """
        mods = [self._row_to_mod(row) for row in rows]
        official = [mod for mod in mods if mod.unique_name.startswith('/Lotus/')]
        keys = list(dict.fromkeys((mod.unique_name, mod.fusion_limit) for mod in official))
        effects = self._fetch_ranked_effects_many(connection, keys)
        return [mod for mod in mods if not mod.unique_name.startswith('/Lotus/')
                or effects[(mod.unique_name, mod.fusion_limit)]]

    def get_mod(self, unique_name: str) -> Mod | None:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM mods WHERE unique_name = ?", (unique_name,)).fetchone()
        return self._row_to_mod(row) if row else None

    def fetch_ranked_effects(self, unique_name: str, rank: int) -> list[ModEffect]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                "SELECT effect_code, effect_value, effect_text, position FROM mod_effects WHERE unique_name = ? AND rank = ? ORDER BY position",
                (unique_name, rank),
            ).fetchall()
        effects = [self._row_to_effect(row) for row in rows]
        return [effect for effect in effects if usable_direct_effect(unique_name, effect)]

    def fetch_ranked_effects_many(self, selections: Iterable[tuple[str, int]]) -> dict[tuple[str, int], list[ModEffect]]:
        """Fetch all equipped slot effects using one connection.

        Duplicate selections share a result, and chunks stay below SQLite's
        traditional 999-variable limit for callers requesting large batches.
        """
        keys = list(dict.fromkeys(selections))
        if not keys:
            return {}
        # A missing row is a valid empty effect set; an SQL failure is not.
        # Callers must not calculate an apparently valid unmodded result when
        # the database is locked, incomplete, or unreadable.
        with closing(self.connect()) as connection:
            return self._fetch_ranked_effects_many(connection, keys)

    def _fetch_ranked_effects_many(self, connection: sqlite3.Connection,
                                   keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[ModEffect]]:
        result: dict[tuple[str, int], list[ModEffect]] = {key: [] for key in keys}
        for start in range(0, len(keys), 400):
            chunk = keys[start:start + 400]
            # OR terms use the (unique_name, rank) index; SQLite's
            # row-value IN (VALUES ...) can scan the whole table.
            predicates = " OR ".join("(unique_name = ? AND rank = ?)" for _ in chunk)
            params = [value for key in chunk for value in key]
            rows = connection.execute(
                "SELECT unique_name, rank, effect_code, effect_value, effect_text, position "
                "FROM mod_effects WHERE " + predicates + " ORDER BY unique_name, rank, position",
                params,
            )
            for row in rows:
                unique_name = str(row["unique_name"])
                effect = self._row_to_effect(row)
                if usable_direct_effect(unique_name, effect):
                    result[(unique_name, int(row["rank"]))].append(effect)
        return result

    @staticmethod
    def _row_to_effect(row: sqlite3.Row) -> ModEffect:
        return ModEffect(code=str(row["effect_code"]), value=float(row["effect_value"]),
                         text=str(row["effect_text"]), position=int(row["position"]))

    def _row_to_mod(self, row: sqlite3.Row) -> Mod:
        return Mod(
            unique_name=str(row["unique_name"]),
            name=str(row["name"]),
            mod_type=str(row["mod_type"] or ""),
            compat_name=str(row["compat_name"] or ""),
            polarity=str(row["polarity"] or ""),
            rarity=str(row["rarity"] or ""),
            fusion_limit=int(row["fusion_limit"] or 0),
            base_drain=int(row["base_drain"] or 0),
            description=str(row["description"] or ""),
            effect_summary=str(row["effect_summary"] or ""),
            supported=bool(row["supported"]),
        )
