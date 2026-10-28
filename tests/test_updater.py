"""Data refresh must never silently replace usable exports with broken ones."""
from __future__ import annotations

from contextlib import closing

import json
import lzma
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from modules.updater import (
    DATA_URL, KEY_URL, DataRefreshError, DataRefreshRecoveryError, WarframeDataUpdater,
)


WEAPONS = "ExportWeapons_en_Cleaned.zip"
UPGRADES = "ExportKeys_en_Cleaned.zip"
WEAPONS_MEMBER = "ExportWeapons_en_Cleaned.json"
UPGRADES_MEMBER = "ExportUpgrades_en_Cleaned.json"


def weapon_export(name: str) -> dict:
    return {"ExportWeapons": [{
        "name": name, "uniqueName": f"/Lotus/Weapons/{name}",
        "productCategory": "LongGuns", "totalDamage": 100,
        "damagePerShot": [100], "criticalChance": .2,
        "criticalMultiplier": 2, "procChance": .1,
    }]}


def mod_export(name: str) -> dict:
    return {"ExportUpgrades": [{
        "name": name, "uniqueName": f"/Lotus/Mods/{name}", "type": "PRIMARY",
        "fusionLimit": 0, "description": ["Description"],
        "levelStats": [{"stats": ["+10% Damage"]}],
    }]}


def write_export(path: Path, member: str, payload: dict) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, json.dumps(payload))


class UpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = {name: self.root / name for name in ("source", "temp")}
        for path in self.paths.values():
            path.mkdir()
        with patch("modules.updater.ensure_app_dirs", return_value=self.paths):
            self.updater = WarframeDataUpdater()
        self.weapons = self.paths["source"] / WEAPONS
        self.upgrades = self.paths["source"] / UPGRADES
        write_export(self.weapons, WEAPONS_MEMBER, weapon_export("Old Weapon"))
        write_export(self.upgrades, UPGRADES_MEMBER, mod_export("Old Mod"))
        self.old_bytes = (self.weapons.read_bytes(), self.upgrades.read_bytes())

    def download_fixture(self, url: str, target: Path, min_expected_size: int = 0) -> int:
        if url == KEY_URL:
            payload = lzma.compress(
                b"ExportWeapons_en.json!weapons\nExportUpgrades_en.json!upgrades\n",
                format=lzma.FORMAT_ALONE,
            )
        elif url == DATA_URL + "ExportWeapons_en.json!weapons":
            payload = json.dumps(weapon_export("New Weapon")).encode()
        elif url == DATA_URL + "ExportUpgrades_en.json!upgrades":
            payload = json.dumps(mod_export("New Mod")).encode()
        else:
            raise AssertionError(f"Unexpected request: {url}")
        target.write_bytes(payload)
        return len(payload)

    def test_truncated_stream_is_not_accepted_as_a_complete_manifest(self) -> None:
        source = b"ExportWeapons_en.json!hash\nExportUpgrades_en.json!hash\n"
        for fmt in (lzma.FORMAT_ALONE, lzma.FORMAT_XZ):
            encoded = lzma.compress(source, format=fmt)
            for cut in (1, 5, len(encoded) // 2):
                with self.subTest(format=fmt, cut=cut):
                    with self.assertRaises((lzma.LZMAError, DataRefreshError)):
                        self.updater._decompress_lzma_streams(encoded[:-cut])

    def test_complete_concatenated_streams_are_read(self) -> None:
        first = lzma.compress(b"one\n", format=lzma.FORMAT_ALONE)
        second = lzma.compress(b"two\n", format=lzma.FORMAT_ALONE)
        self.assertEqual(self.updater._decompress_lzma_streams(first + second), b"one\ntwo\n")

    def test_truncated_second_stream_is_not_silently_ignored(self) -> None:
        first = lzma.compress(b"one\n")
        second = lzma.compress(b"two\n")
        with self.assertRaises((lzma.LZMAError, DataRefreshError)):
            self.updater._decompress_lzma_streams(first + second[:-5])

    def test_expansion_rejects_an_incomplete_stream(self) -> None:
        source = self.paths["temp"] / "broken.lzma"
        source.write_bytes(lzma.compress(b"a manifest", format=lzma.FORMAT_ALONE)[:-1])
        with self.assertRaises(DataRefreshError):
            self.updater._expand_lzma(source, self.paths["temp"])
        self.assertFalse((self.paths["temp"] / "index_en.txt").exists())

    def test_known_size_header_recovery_requires_the_declared_size(self) -> None:
        raw = b"ExportWeapons_en.json!hash\nExportUpgrades_en.json!hash\n"
        compressed = lzma.compress(raw, format=lzma.FORMAT_ALONE)
        source = self.paths["temp"] / "known-size.lzma"
        output = self.paths["temp"] / "index_en.txt"
        real_decompress = self.updater._decompress_lzma_streams

        def older_liblzma(data: bytes) -> bytes:
            if data[5:13] != b"\xff" * 8:
                raise lzma.LZMAError("known size plus end marker rejected")
            return real_decompress(data)

        with patch.object(self.updater, "_decompress_lzma_streams", side_effect=older_liblzma):
            source.write_bytes(compressed[:5] + len(raw).to_bytes(8, "little") + compressed[13:])
            method = self.updater._expand_lzma(source, self.paths["temp"])
            self.assertIn("header recovery", method)
            self.assertEqual(output.read_bytes(), raw)
            output.unlink()
            source.write_bytes(compressed[:5] + (len(raw) + 1).to_bytes(8, "little") + compressed[13:])
            with self.assertRaisesRegex(DataRefreshError, "size does not match"):
                self.updater._expand_lzma(source, self.paths["temp"])
            self.assertFalse(output.exists())

    def test_refresh_does_not_delete_unrelated_temporary_files(self) -> None:
        sentinel = self.paths["temp"] / "other-session.txt"
        sentinel.write_text("keep me", encoding="utf-8")
        with patch.object(self.updater, "_download", side_effect=self.download_fixture):
            result = self.updater.refresh()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(result["weapons_zip"], self.weapons)
        self.assertEqual(result["upgrades_zip"], self.upgrades)
        with zipfile.ZipFile(self.weapons) as archive:
            self.assertEqual(json.loads(archive.read(WEAPONS_MEMBER))["ExportWeapons"][0]["name"], "New Weapon")

    def test_a_staging_write_failure_keeps_both_saved_exports_and_fallback(self) -> None:
        original_write = self.updater._write_zip
        def fail_second(path: Path, member: str, payload: dict) -> None:
            if member == UPGRADES_MEMBER:
                raise OSError("simulated disk full")
            original_write(path, member, payload)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch.object(self.updater, "_write_zip", side_effect=fail_second):
            result = self.updater.update_and_build_database(
                self.root / "fallback.db", self.weapons, self.upgrades,
                allow_bundled_fallback=True,
            )
        self.assertEqual(result["source_mode"], "saved local exports")
        self.assertIn("disk full", result["refresh_error"])
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)
        with closing(sqlite3.connect(self.root / "fallback.db")) as connection, connection:
            self.assertEqual(connection.execute("SELECT weapon FROM weapons").fetchone()[0], "Old Weapon")
            self.assertEqual(connection.execute("SELECT name FROM mods").fetchone()[0], "Old Mod")

    def test_second_publication_failure_restores_first_and_falls_back(self) -> None:
        real_replace = os.replace
        def fail_second(source, destination):
            if Path(source).name == UPGRADES and Path(destination) == self.upgrades:
                raise OSError("second replace failed")
            return real_replace(source, destination)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.replace", side_effect=fail_second):
            result = self.updater.update_and_build_database(
                self.root / "fallback.db", self.weapons, self.upgrades)
        self.assertEqual(result["source_mode"], "saved local exports")
        self.assertIn("second replace failed", result["refresh_error"])
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])
        with closing(sqlite3.connect(self.root / "fallback.db")) as connection, connection:
            self.assertEqual(connection.execute("SELECT weapon FROM weapons").fetchone()[0], "Old Weapon")

    def test_interrupt_after_replacement_restores_the_old_pair(self) -> None:
        real_replace = os.replace
        def interrupt_after_first(source, destination):
            result = real_replace(source, destination)
            if Path(source).name == WEAPONS:
                raise KeyboardInterrupt()
            return result

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.replace", side_effect=interrupt_after_first):
            with self.assertRaises(KeyboardInterrupt):
                self.updater.refresh()
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])

    def test_failed_rollback_retains_backups_and_never_builds_a_mixed_pair(self) -> None:
        real_replace = os.replace
        def fail_publish_and_restore(source, destination):
            if ((Path(source).name == UPGRADES and Path(destination) == self.upgrades)
                    or Path(source).name.startswith("restore-")):
                raise OSError("simulated failure")
            return real_replace(source, destination)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.replace", side_effect=fail_publish_and_restore), \
             patch("modules.importer.build_database") as build:
            with self.assertRaises(DataRefreshRecoveryError) as raised:
                self.updater.update_and_build_database(self.root / "fallback.db", self.weapons, self.upgrades)
        build.assert_not_called()
        stages = list(self.paths["source"].glob(".wdc-refresh-*"))
        self.assertEqual(len(stages), 1)
        self.assertIn(str(stages[0]), str(raised.exception))
        self.assertEqual((stages[0] / ("previous-" + WEAPONS)).read_bytes(), self.old_bytes[0])
        self.assertEqual((stages[0] / ("previous-" + UPGRADES)).read_bytes(), self.old_bytes[1])
        self.assertEqual(self.upgrades.read_bytes(), self.old_bytes[1])
        # An unsafe pair must also be blocked on a later offline rebuild.
        from modules.importer import build_database
        with self.assertRaisesRegex(RuntimeError, "unfinished.*refresh"):
            build_database(self.root / "later.db", self.weapons, self.upgrades)
        self.assertFalse((self.root / "later.db").exists())

    def test_process_exit_during_publication_leaves_a_guarded_recovery_copy(self) -> None:
        from modules.importer import build_database
        stage = self.paths["source"] / ".wdc-refresh-crash-test"
        stage.mkdir()
        write_export(stage / WEAPONS, WEAPONS_MEMBER, weapon_export("New Weapon"))
        write_export(stage / UPGRADES, UPGRADES_MEMBER, mod_export("New Mod"))
        script = '''
import os, sys
from pathlib import Path
from unittest.mock import patch
from modules.updater import WarframeDataUpdater
stage, source = map(Path, sys.argv[1:3])
archives = ((stage / sys.argv[3], source / sys.argv[3]),
            (stage / sys.argv[4], source / sys.argv[4]))
original = os.replace
def replace_then_exit(src, dst):
    original(src, dst)
    os._exit(91)
with patch("modules.updater.os.replace", side_effect=replace_then_exit):
    WarframeDataUpdater._publish_exports(archives, stage)
'''
        result = subprocess.run([sys.executable, "-c", script, str(stage), str(self.paths["source"]),
                                 WEAPONS, UPGRADES], check=False)
        self.assertEqual(result.returncode, 91)
        self.assertTrue((stage / "PUBLISHING.json").is_file())
        self.assertEqual((stage / ("previous-" + WEAPONS)).read_bytes(), self.old_bytes[0])
        self.assertEqual((stage / ("previous-" + UPGRADES)).read_bytes(), self.old_bytes[1])
        with self.assertRaisesRegex(RuntimeError, "unfinished.*refresh"):
            build_database(self.root / "blocked.db", self.weapons, self.upgrades)
        self.assertFalse((self.root / "blocked.db").exists())

    def test_unfinished_publication_marker_blocks_saved_exports(self) -> None:
        from modules.importer import build_database
        stage = self.paths["source"] / ".wdc-refresh-interrupted"
        stage.mkdir()
        (stage / "PUBLISHING.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "unfinished.*refresh"):
            build_database(self.root / "blocked.db", self.weapons, self.upgrades)
        with patch.object(self.updater, "_download") as download:
            with self.assertRaisesRegex(RuntimeError, "unfinished.*refresh"):
                self.updater.refresh()
        download.assert_not_called()
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)

    def test_malformed_download_does_not_replace_the_previous_pair(self) -> None:
        def malformed_download(url: str, target: Path, min_expected_size: int = 0) -> int:
            if url == DATA_URL + "ExportUpgrades_en.json!upgrades":
                payload = json.dumps({"ExportUpgrades": []}).encode()
                target.write_bytes(payload)
                return len(payload)
            return self.download_fixture(url, target, min_expected_size)

        with patch.object(self.updater, "_download", side_effect=malformed_download):
            with self.assertRaises((ValueError, DataRefreshError)):
                self.updater.refresh()
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)

    def test_sqlite_constraint_failure_in_fresh_data_keeps_previous_pair(self) -> None:
        def duplicate_download(url: str, target: Path, min_expected_size: int = 0) -> int:
            if url == DATA_URL + "ExportUpgrades_en.json!upgrades":
                item = mod_export("Duplicate")["ExportUpgrades"][0]
                payload = json.dumps({"ExportUpgrades": [item, item]}).encode()
                target.write_bytes(payload)
                return len(payload)
            return self.download_fixture(url, target, min_expected_size)

        with patch.object(self.updater, "_download", side_effect=duplicate_download):
            with self.assertRaises(sqlite3.IntegrityError):
                self.updater.refresh()
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)

    def test_json_cleaning_preserves_spaces_around_escaped_newlines(self) -> None:
        path = self.paths["temp"] / "ExportWeapons_en.json"
        payload = weapon_export("New Weapon")
        payload["ExportWeapons"][0]["description"] = "Line one  \n  Line two"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.updater._clean_json(path), payload)

    def test_json_cleaning_rejects_invalid_utf8(self) -> None:
        path = self.paths["temp"] / "ExportWeapons_en.json"
        path.write_bytes(b'{"ExportWeapons": [], "x": "\xff"}')
        with self.assertRaises(UnicodeDecodeError):
            self.updater._clean_json(path)


if __name__ == "__main__":
    unittest.main()
