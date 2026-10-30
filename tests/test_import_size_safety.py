"""Untrusted saved exports must not expand or load without a size limit."""
from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import openpyxl

from modules import importer
from modules.json_safety import read_bounded


def write_zip(path: Path, member: str, payload: object) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, json.dumps(payload))


class ImportSizeSafetyTests(unittest.TestCase):
    def test_bounded_reader_accepts_the_limit_and_rejects_the_next_byte(self):
        content = b"x" * (1024 * 1024 + 1)
        self.assertEqual(read_bounded(io.BytesIO(content), len(content), "test"), content)
        with self.assertRaisesRegex(ValueError, "safety limit"):
            read_bounded(io.BytesIO(content), len(content) - 1, "test")
        self.assertEqual(read_bounded(io.BytesIO(b""), 0, "test"), b"")

    def test_compressed_json_members_are_bounded_before_they_are_inflated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for member, payload, reader in (
                ("weapons.json", {"ExportWeapons": [], "padding": "x" * 10_000},
                 importer.rows_from_cleaned_json),
                ("ExportUpgrades_en_Cleaned.json", {"ExportUpgrades": [], "padding": "x" * 10_000},
                 importer.mods_from_cleaned_json),
            ):
                with self.subTest(member=member):
                    path = root / (member + ".zip")
                    write_zip(path, member, payload)
                    self.assertLess(path.stat().st_size, 1024)  # expands well beyond the limit
                    with patch("modules.importer.MAX_EXPORT_JSON_BYTES", 1024):
                        with self.assertRaisesRegex(ValueError, "safety limit"):
                            reader(path)

    def test_source_snapshot_is_bounded_before_the_cached_parser_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.zip"
            path.write_bytes(b"x" * 200)
            with patch("modules.importer.MAX_SOURCE_ARCHIVE_BYTES", 100), \
                 patch("modules.importer._read_weapons") as reader:
                with self.assertRaisesRegex(ValueError, "safety limit"):
                    importer.rows_from_cleaned_json(path)
            reader.assert_not_called()

    def test_workbook_uncompressed_total_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weapons.xlsx"
            workbook = openpyxl.Workbook()
            workbook.active.title = "Weapon-Data"
            workbook.save(path)
            workbook.close()
            with patch("modules.importer.MAX_WORKBOOK_UNCOMPRESSED_BYTES", 1024):
                with self.assertRaisesRegex(ValueError, "safety limit"):
                    importer.rows_from_spreadsheet(path)

    def test_oversized_export_is_rejected_before_existing_database_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "user.db"
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.execute("CREATE TABLE custom_data (value TEXT)")
                connection.execute("INSERT INTO custom_data VALUES ('keep me')")
            before = db.read_bytes()
            weapons = root / "weapons.zip"
            mods = root / "mods.zip"
            write_zip(weapons, "weapons.json", {
                "ExportWeapons": [{"name": "Example", "totalDamage": 10, "damagePerShot": [10]}],
                "padding": "x" * 10_000,
            })
            write_zip(mods, "ExportUpgrades_en_Cleaned.json", {
                "ExportUpgrades": [{"name": "Example", "uniqueName": "/Lotus/Test",
                                    "type": "Primary", "compatName": "Rifle",
                                    "levelStats": [{"stats": ["+10% Damage"]}]}],
            })
            with patch("modules.importer.MAX_EXPORT_JSON_BYTES", 1024):
                with self.assertRaisesRegex(ValueError, "safety limit"):
                    importer.build_database(db, weapons, mods)
            self.assertEqual(db.read_bytes(), before)
            self.assertFalse((root / "backups").exists())


if __name__ == "__main__":
    unittest.main()
