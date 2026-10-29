"""Cached imports must reflect the bytes on disk, not just file metadata."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import openpyxl

from modules import importer


def weapon_zip(path: Path, damage: int) -> None:
    entry = {"name": "Example", "uniqueName": "/Lotus/Test/Weapon",
             "totalDamage": damage, "damagePerShot": [damage]}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("weapons.json", json.dumps({"ExportWeapons": [entry]}))


def mods_zip(path: Path, percent: int) -> None:
    entry = {"name": "Example", "uniqueName": "/Lotus/Test/Mod", "type": "Primary",
             "levelStats": [{"stats": [f"+{percent}% Damage"]}]}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("ExportUpgrades_en_Cleaned.json", json.dumps({"ExportUpgrades": [entry]}))


def spreadsheet(path: Path, name: str) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Weapon-Data"
    sheet.append(["Weapon", "Total Damage"] + [""] * 19)
    sheet.append(["header row"])
    sheet.append([name, 100])
    workbook.save(path)
    workbook.close()


def same_size_bytes(first: Path, second: Path) -> tuple[bytes, bytes]:
    # ZIP/XLSX readers permit padding after the end-of-central-directory. The
    # padding also covers small compression differences in workbook metadata.
    left, right = first.read_bytes(), second.read_bytes()
    size = max(len(left), len(right))
    return left.ljust(size, b"\0"), right.ljust(size, b"\0")


def replace_preserving_metadata(path: Path, content: bytes, *, atomic: bool) -> None:
    previous = path.stat()
    if atomic:
        replacement = path.with_suffix(".new")
        replacement.write_bytes(content)
        os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        os.replace(replacement, path)
    else:
        path.write_bytes(content)
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    current = path.stat()
    assert (current.st_size, current.st_mtime_ns) == (previous.st_size, previous.st_mtime_ns)


class ImportCacheSafetyTests(unittest.TestCase):
    def test_weapon_replacement_with_same_size_and_mtime_is_not_stale(self):
        for atomic in (False, True):
            with self.subTest(atomic=atomic), tempfile.TemporaryDirectory() as tmp:
                path, other = Path(tmp) / "weapons.zip", Path(tmp) / "other.zip"
                weapon_zip(path, 100)
                weapon_zip(other, 200)
                old, new = same_size_bytes(path, other)
                path.write_bytes(old)
                with patch("modules.importer._read_weapons", wraps=importer._read_weapons) as reader:
                    self.assertEqual(importer.rows_from_cleaned_json(path)[0]["dmg"], 100)
                    self.assertEqual(importer.rows_from_cleaned_json(path)[0]["dmg"], 100)
                    self.assertEqual(reader.call_count, 1)  # unchanged bytes still hit the cache
                    replace_preserving_metadata(path, new, atomic=atomic)
                    self.assertEqual(importer.rows_from_cleaned_json(path)[0]["dmg"], 200)
                    self.assertEqual(reader.call_count, 2)

    def test_cache_key_and_parse_use_the_same_snapshot_if_path_changes_mid_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, other = Path(tmp) / "weapons.zip", Path(tmp) / "other.zip"
            weapon_zip(path, 100)
            weapon_zip(other, 200)
            old, new = same_size_bytes(path, other)
            path.write_bytes(old)
            real_reader = importer._read_weapons

            def replace_before_parse(source, contents=None):
                replace_preserving_metadata(path, new, atomic=True)
                return real_reader(source, contents)

            with patch("modules.importer._read_weapons", side_effect=replace_before_parse):
                self.assertEqual(importer.rows_from_cleaned_json(path)[0]["dmg"], 100)
            self.assertEqual(importer.rows_from_cleaned_json(path)[0]["dmg"], 200)

    def test_mod_rewrite_with_same_size_and_mtime_refreshes_effects_and_source_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, other = Path(tmp) / "mods.zip", Path(tmp) / "other.zip"
            mods_zip(path, 10)
            mods_zip(other, 20)
            old, new = same_size_bytes(path, other)
            path.write_bytes(old)
            _, effects = importer.mods_from_cleaned_json(path)
            self.assertAlmostEqual(effects[0]["effect_value"], 0.1)
            replace_preserving_metadata(path, new, atomic=False)
            stats = {}
            _, effects = importer.mods_from_cleaned_json(path, source_stats=stats)
            self.assertAlmostEqual(effects[0]["effect_value"], 0.2)
            self.assertEqual(stats[("/Lotus/Test/Mod", 0)], ("+20% Damage",))

    def test_duplicate_upgrade_zip_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate-mods.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("ExportUpgrades_en_Cleaned.json", '{"ExportUpgrades": []}')
                archive.writestr("ExportUpgrades_en_Cleaned.json", '{"ExportUpgrades": []}')
            with self.assertRaisesRegex(ValueError, "exactly one ExportUpgrades_en_Cleaned.json"):
                importer.mods_from_cleaned_json(path)

    def test_spreadsheet_rewrite_with_same_size_and_mtime_is_not_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, other = Path(tmp) / "weapons.xlsx", Path(tmp) / "other.xlsx"
            spreadsheet(path, "First")
            spreadsheet(other, "Other")
            old, new = same_size_bytes(path, other)
            path.write_bytes(old)
            self.assertEqual(importer.rows_from_spreadsheet(path)[0]["weapon"], "First")
            replace_preserving_metadata(path, new, atomic=False)
            self.assertEqual(importer.rows_from_spreadsheet(path)[0]["weapon"], "Other")


if __name__ == "__main__":
    unittest.main()
