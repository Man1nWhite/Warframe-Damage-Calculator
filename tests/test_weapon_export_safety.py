"""Regression tests for name collisions in the official weapon export."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path

from modules.importer import create_schema, rows_from_cleaned_json, upsert_weapon_rows

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "source" / "ExportWeapons_en_Cleaned.zip"
PLAYER = "/Lotus/Weapons/Tenno/Grimoire/TnGrimoire"
DOPPELGANGER = "/Lotus/Weapons/Tenno/Grimoire/TnDoppelgangerGrimoire"


class WeaponExportCollisionTests(unittest.TestCase):
    @staticmethod
    def read_grimoire_rows():
        with zipfile.ZipFile(EXPORT) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".json"))
            items = json.loads(archive.read(name))["ExportWeapons"]
        return [item for item in items if item.get("uniqueName") in (PLAYER, DOPPELGANGER)]

    @staticmethod
    def write_export(path, entries):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("weapons.json", json.dumps({"ExportWeapons": entries}))

    def test_weapon_export_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "duplicate.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("weapons.json", '{"ExportWeapons": [], "ExportWeapons": []}')
            with self.assertRaisesRegex(ValueError, "duplicate key 'ExportWeapons'"):
                rows_from_cleaned_json(path)

    def test_ambiguous_weapon_archive_with_multiple_json_members_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ambiguous.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("README.json", json.dumps({"ExportWeapons": [{"name": "Wrong"}]}))
                archive.writestr("ExportWeapons_en_Cleaned.json", json.dumps({"ExportWeapons": [
                    {"name": "Right", "uniqueName": "/Lotus/Weapons/Right",
                     "productCategory": "LongGuns", "totalDamage": 10},
                ]}))
            with self.assertRaisesRegex(ValueError, "exactly one JSON"):
                rows_from_cleaned_json(path)

    def test_player_grimoire_wins_independent_of_export_order(self):
        entries = self.read_grimoire_rows()
        self.assertEqual(len(entries), 2)
        for order in (entries, list(reversed(entries))):
            with self.subTest(first=order[0]["uniqueName"]), tempfile.TemporaryDirectory() as root:
                path = Path(root) / "weapons.zip"
                self.write_export(path, order)
                rows = rows_from_cleaned_json(path)
                # Keep both in the payload so a legacy database using the
                # doppelganger ID still passes source-coverage checks.
                self.assertEqual({r["unique_name"] for r in rows}, {PLAYER, DOPPELGANGER})
                with closing(sqlite3.connect(":memory:")) as connection, connection:
                    create_schema(connection)
                    upsert_weapon_rows(connection, rows)
                    actual = connection.execute(
                        "SELECT unique_name,dmg,elec,impact,punc,critchan,critmult,statchan "
                        "FROM weapons WHERE weapon='Grimoire'"
                    ).fetchone()
                self.assertEqual(actual, (PLAYER, 150, 150, 0, 0, .2, 2, .25999999))

    def test_missing_player_entry_does_not_silently_import_doppelganger(self):
        entries = [item for item in self.read_grimoire_rows() if item["uniqueName"] == DOPPELGANGER]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "partial.zip"
            self.write_export(path, entries)
            with self.assertRaisesRegex(ValueError, "Grimoire.*player"):
                rows_from_cleaned_json(path)

    def test_conflicting_duplicate_player_entries_are_rejected(self):
        entries = [item for item in self.read_grimoire_rows() if item["uniqueName"] == PLAYER]
        conflicting = dict(entries[0], totalDamage=999)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "conflicting.zip"
            self.write_export(path, entries + [conflicting])
            with self.assertRaisesRegex(ValueError, "Grimoire.*conflict"):
                rows_from_cleaned_json(path)

    def test_sirocco_void_is_imported_but_finisher_is_not_misidentified(self):
        rows = {row["weapon"]: row for row in rows_from_cleaned_json(EXPORT)}
        self.assertEqual(rows["Sirocco"]["void"], 2000)
        # Shadow Clones use a different, unmodeled export damage index. It
        # must not be silently reclassified as Void (or True damage).
        for name in ("Shadow Clones", "Shadow Clones Prime"):
            self.assertGreater(rows[name]["dmg"], 0)
            self.assertEqual(rows[name]["void"], 0)

    def test_unknown_same_name_conflict_is_not_guessed(self):
        entries = [dict(name="Ambiguous", uniqueName=f"/Lotus/Test/{i}",
                        productCategory="Pistols", totalDamage=damage)
                   for i, damage in enumerate((10, 20))]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "unknown.zip"
            self.write_export(path, entries)
            with self.assertRaisesRegex(ValueError, "Ambiguous.*conflict"):
                rows_from_cleaned_json(path)


if __name__ == "__main__":
    unittest.main()
