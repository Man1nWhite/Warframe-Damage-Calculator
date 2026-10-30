"""Data refresh must never silently replace usable exports with broken ones."""
from __future__ import annotations

import json
import lzma
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from modules.updater import (
    DATA_URL,
    KEY_URL,
    DataRefreshError,
    DataRefreshRecoveryError,
    WarframeDataUpdater,
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

    def test_download_does_not_compare_decoded_body_to_content_length(self) -> None:
        class EncodedResponse:
            headers = {"Content-Length": "4", "Content-Encoding": "gzip"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def iter_content(chunk_size: int):
                yield b"decoded body"

        target = self.paths["temp"] / "download.json"
        with patch("modules.updater.requests.get", return_value=EncodedResponse()):
            self.assertEqual(self.updater._download("https://example.invalid/file", target), 12)
        self.assertEqual(target.read_bytes(), b"decoded body")

    def test_download_rejects_an_oversized_decoded_body_and_removes_partial_file(self) -> None:
        class OversizedResponse:
            headers = {"Content-Length": "1"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def iter_content(chunk_size: int):
                yield b"more bytes than allowed"

        target = self.paths["temp"] / "too-large.bin"
        with patch("modules.updater.MAX_DOWNLOAD_BYTES", 8), \
             patch("modules.updater.requests.get", return_value=OversizedResponse()) as get:
            with self.assertRaisesRegex(DataRefreshError, "safety limit"):
                self.updater._download("https://example.invalid/file", target)
        self.assertEqual(get.call_count, 3)  # transient failures retain retry behavior
        self.assertFalse(target.exists())

    def test_manifest_decompression_stops_at_the_output_limit(self) -> None:
        bomb = lzma.compress(b"x" * 4_000_000, format=lzma.FORMAT_XZ)
        with self.assertRaisesRegex(lzma.LZMAError, "safety limit"):
            self.updater._decompress_lzma_streams(bomb, max_output_bytes=1024)

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
        retained = list(self.paths["source"].glob(".wdc-export-backup-*"))
        self.assertEqual(len(retained), 1)
        self.assertEqual((retained[0] / WEAPONS).read_bytes(), self.old_bytes[0])
        self.assertEqual((retained[0] / UPGRADES).read_bytes(), self.old_bytes[1])
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*/PUBLISHING.json")), [])

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

    def test_failed_refresh_does_not_overwrite_a_concurrent_user_edit_during_rollback(self) -> None:
        real_link = os.link
        user_bytes = b"user changed this file during publication"

        def edit_then_fail(source, destination):
            if Path(source).name == UPGRADES and Path(destination) == self.upgrades:
                self.upgrades.write_bytes(user_bytes)
                raise OSError("publication stopped")
            return real_link(source, destination)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=edit_then_fail), \
             patch("modules.importer.build_database") as build:
            with self.assertRaises(DataRefreshRecoveryError):
                self.updater.update_and_build_database(self.root / "failed.db", self.weapons, self.upgrades)
        build.assert_not_called()
        self.assertEqual(self.upgrades.read_bytes(), user_bytes)
        stages = list(self.paths["source"].glob(".wdc-refresh-*"))
        self.assertEqual(len(stages), 1)
        self.assertTrue((stages[0] / "PUBLISHING.json").is_file())
        self.assertEqual((stages[0] / ("previous-" + UPGRADES)).read_bytes(), self.old_bytes[1])

    def test_refresh_refuses_same_size_same_mtime_edit_while_downloading(self) -> None:
        user_bytes = b"U" * len(self.old_bytes[0])
        original_stat = self.weapons.stat()
        real_download = self.download_fixture

        def edit_during_download(url: str, target: Path, min_expected_size: int = 0) -> int:
            result = real_download(url, target, min_expected_size)
            if target.name == "ExportUpgrades_en.json":
                self.weapons.write_bytes(user_bytes)
                os.utime(self.weapons, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            return result

        with patch.object(self.updater, "_download", side_effect=edit_during_download), \
             patch("modules.importer.build_database") as build:
            with self.assertRaisesRegex(DataRefreshRecoveryError, "changed while fresh data was downloading"):
                self.updater.update_and_build_database(self.root / "race.db", self.weapons, self.upgrades)
        build.assert_not_called()
        self.assertEqual(self.weapons.stat().st_size, original_stat.st_size)
        self.assertEqual(self.weapons.stat().st_mtime_ns, original_stat.st_mtime_ns)
        self.assertEqual(self.weapons.read_bytes(), user_bytes)
        self.assertEqual(self.upgrades.read_bytes(), self.old_bytes[1])
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])
        self.assertFalse((self.root / "race.db").exists())

    def check_edit_after_final_fingerprint_is_preserved(self, *, atomic: bool) -> None:
        real_fingerprint = WarframeDataUpdater._export_fingerprint
        user_bytes = b"edit after the last pre-publication fingerprint"
        seen = 0

        def edit_after_check(path):
            nonlocal seen
            result = real_fingerprint(path)
            if path == self.weapons:
                seen += 1
                if seen == 3:
                    if atomic:
                        replacement = self.paths["source"] / "user-replacement.tmp"
                        replacement.write_bytes(user_bytes)
                        os.replace(replacement, self.weapons)
                    else:
                        self.weapons.write_bytes(user_bytes)
            return result

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch.object(WarframeDataUpdater, "_export_fingerprint", side_effect=edit_after_check):
            with self.assertRaises(DataRefreshRecoveryError):
                self.updater.refresh()
        self.assertEqual(seen, 3)
        stages = list(self.paths["source"].glob(".wdc-refresh-*/PUBLISHING.json"))
        self.assertEqual(len(stages), 1)
        retained = [path.read_bytes() for path in self.paths["source"].rglob(WEAPONS)
                    if path.is_file()]
        self.assertIn(user_bytes, retained)

    def test_in_place_edit_after_final_fingerprint_is_preserved(self) -> None:
        self.check_edit_after_final_fingerprint_is_preserved(atomic=False)

    def test_atomic_edit_after_final_fingerprint_is_preserved(self) -> None:
        self.check_edit_after_final_fingerprint_is_preserved(atomic=True)

    def test_export_removed_after_pair_check_is_not_silently_recreated(self) -> None:
        real_fingerprint = WarframeDataUpdater._export_fingerprint
        seen = 0

        def remove_after_check(path):
            nonlocal seen
            result = real_fingerprint(path)
            if path == self.weapons:
                seen += 1
                if seen == 2:
                    self.weapons.unlink()
            return result

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch.object(WarframeDataUpdater, "_export_fingerprint", side_effect=remove_after_check):
            with self.assertRaises(DataRefreshRecoveryError):
                self.updater.refresh()
        self.assertFalse(self.weapons.exists())
        self.assertEqual(self.upgrades.read_bytes(), self.old_bytes[1])
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])

    def test_edit_after_displacement_is_retained_and_blocks_publication(self) -> None:
        user_bytes = b"late edit to the displaced original"
        real_link = os.link
        edited = []

        def edit_before_link(source, destination):
            if Path(destination) == self.weapons:
                displaced = list(self.paths["source"].glob(f".wdc-export-backup-*/{WEAPONS}"))
                self.assertEqual(len(displaced), 1)
                displaced[0].write_bytes(user_bytes)
                edited.append(displaced[0])
            return real_link(source, destination)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=edit_before_link):
            with self.assertRaises(DataRefreshRecoveryError):
                self.updater.refresh()
        self.assertEqual(len(edited), 1)
        self.assertEqual(edited[0].read_bytes(), user_bytes)
        self.assertEqual(len(list(self.paths["source"].glob(".wdc-refresh-*/PUBLISHING.json"))), 1)
        with zipfile.ZipFile(self.weapons) as archive:
            self.assertEqual(json.loads(archive.read(WEAPONS_MEMBER))["ExportWeapons"][0]["name"], "New Weapon")

    def test_open_writer_does_not_lose_late_edits(self) -> None:
        user_bytes = b"a late write through the original open file"
        real_link = os.link
        wrote_at_link = []

        with self.weapons.open("r+b") as original:
            def write_original():
                original.seek(0)
                original.write(user_bytes)
                original.truncate()
                original.flush()

            def write_before_link(source, destination):
                if Path(destination) == self.weapons:
                    write_original()
                    wrote_at_link.append(True)
                return real_link(source, destination)

            with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
                 patch("modules.updater.os.link", side_effect=write_before_link):
                try:
                    self.updater.refresh()
                except (DataRefreshRecoveryError, PermissionError) as exc:
                    if wrote_at_link:
                        self.assertIn("changed during publication", str(exc))
                    else:
                        # Some platforms deny reading or renaming an open file.
                        # The failure must leave it available to its writer.
                        cause = exc.__cause__ if isinstance(exc, DataRefreshRecoveryError) else exc
                        self.assertIsInstance(cause, PermissionError)
                        write_original()
                else:
                    self.fail("A write during publication must leave a recovery marker")

        retained = [path.read_bytes() for path in self.paths["source"].rglob(WEAPONS)
                    if path.is_file()]
        self.assertIn(user_bytes, retained)

    def test_edit_to_a_published_file_blocks_the_mixed_pair(self) -> None:
        user_bytes = b"new edit made after the first publication"
        real_link = os.link

        def edit_after_second_link(source, destination):
            result = real_link(source, destination)
            if Path(destination) == self.upgrades:
                self.weapons.write_bytes(user_bytes)
            return result

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=edit_after_second_link), \
             patch("modules.importer.build_database") as build:
            with self.assertRaises(DataRefreshRecoveryError):
                self.updater.update_and_build_database(self.root / "mixed.db", self.weapons, self.upgrades)
        build.assert_not_called()
        self.assertEqual(self.weapons.read_bytes(), user_bytes)
        self.assertEqual(len(list(self.paths["source"].glob(".wdc-refresh-*/PUBLISHING.json"))), 1)
        backups = list(self.paths["source"].glob(f".wdc-export-backup-*/{WEAPONS}"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.old_bytes[0])

    def test_file_created_after_displacement_is_not_overwritten(self) -> None:
        user_bytes = b"new export created while the old file was displaced"
        real_link = os.link

        def create_before_link(source, destination):
            if Path(destination) == self.weapons:
                self.weapons.write_bytes(user_bytes)
            return real_link(source, destination)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=create_before_link):
            with self.assertRaises(DataRefreshRecoveryError):
                self.updater.refresh()
        self.assertEqual(self.weapons.read_bytes(), user_bytes)
        self.assertEqual(len(list(self.paths["source"].glob(".wdc-refresh-*/PUBLISHING.json"))), 1)
        backups = list(self.paths["source"].glob(f".wdc-export-backup-*/{WEAPONS}"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.old_bytes[0])

    def test_refresh_refuses_a_new_export_created_while_downloading(self) -> None:
        self.upgrades.unlink()
        user_bytes = b"new file created by another process"
        real_download = self.download_fixture

        def create_during_download(url: str, target: Path, min_expected_size: int = 0) -> int:
            result = real_download(url, target, min_expected_size)
            if target.name == "ExportUpgrades_en.json":
                self.upgrades.write_bytes(user_bytes)
            return result

        with patch.object(self.updater, "_download", side_effect=create_during_download):
            with self.assertRaisesRegex(DataRefreshRecoveryError, "changed while fresh data was downloading"):
                self.updater.refresh()
        self.assertEqual(self.upgrades.read_bytes(), user_bytes)
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])

    def test_refresh_does_not_clobber_a_file_created_during_publication(self) -> None:
        self.upgrades.unlink()
        user_bytes = b"user created the previously absent export"
        real_link = os.link

        def create_after_first(source, destination):
            result = real_link(source, destination)
            if Path(destination) == self.weapons:
                self.upgrades.write_bytes(user_bytes)
            return result

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=create_after_first):
            with self.assertRaises(DataRefreshRecoveryError):
                self.updater.refresh()
        self.assertEqual(self.upgrades.read_bytes(), user_bytes)
        stages = list(self.paths["source"].glob(".wdc-refresh-*"))
        self.assertEqual(len(stages), 1)
        marker = json.loads((stages[0] / "PUBLISHING.json").read_text(encoding="utf-8"))
        self.assertIsNone(next(row for row in marker["archives"]
                               if row["destination"] == UPGRADES)["previous_copy"])

    def test_refresh_publishes_a_missing_destination_without_clobbering(self) -> None:
        self.upgrades.unlink()
        with patch.object(self.updater, "_download", side_effect=self.download_fixture):
            self.updater.refresh()
        with zipfile.ZipFile(self.weapons) as archive:
            self.assertEqual(json.loads(archive.read(WEAPONS_MEMBER))["ExportWeapons"][0]["name"], "New Weapon")
        with zipfile.ZipFile(self.upgrades) as archive:
            self.assertEqual(json.loads(archive.read(UPGRADES_MEMBER))["ExportUpgrades"][0]["name"], "New Mod")
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])

    def test_existing_pair_without_hardlink_support_is_left_untouched(self) -> None:
        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=OSError("hard links unavailable")):
            with self.assertRaisesRegex(DataRefreshError, "hard links unavailable"):
                self.updater.refresh()
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])
        self.assertEqual(list(self.paths["source"].glob(".wdc-export-backup-*")), [])

    def test_missing_destination_without_hardlink_support_never_starts_publication(self) -> None:
        self.upgrades.unlink()
        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=OSError("hard links unavailable")):
            with self.assertRaisesRegex(DataRefreshError, "hard links unavailable"):
                self.updater.refresh()
        self.assertFalse(self.upgrades.exists())
        self.assertEqual(self.weapons.read_bytes(), self.old_bytes[0])
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])
        self.assertEqual(list(self.paths["source"].glob(".wdc-export-backup-*")), [])

    def test_refresh_refuses_to_replace_a_saved_export_symlink(self) -> None:
        linked = self.paths["source"] / "user-weapons.zip"
        self.weapons.rename(linked)
        try:
            self.weapons.symlink_to(linked.name)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        with patch.object(self.updater, "_download", side_effect=self.download_fixture):
            with self.assertRaisesRegex(DataRefreshError, "(?i)symlink|symbolic"):
                self.updater.refresh()
        self.assertTrue(self.weapons.is_symlink())
        self.assertEqual(linked.read_bytes(), self.old_bytes[0])
        self.assertEqual(self.upgrades.read_bytes(), self.old_bytes[1])
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])

    def test_refresh_refuses_to_replace_a_dangling_export_symlink(self) -> None:
        self.weapons.unlink()
        try:
            self.weapons.symlink_to("missing-user-weapons.zip")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        with patch.object(self.updater, "_download", side_effect=self.download_fixture):
            with self.assertRaisesRegex(DataRefreshError, "(?i)symlink|symbolic"):
                self.updater.refresh()
        self.assertTrue(self.weapons.is_symlink())
        self.assertFalse((self.paths["source"] / "missing-user-weapons.zip").exists())
        self.assertEqual(self.upgrades.read_bytes(), self.old_bytes[1])
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])

    def test_second_publication_failure_retains_copies_and_refuses_fallback(self) -> None:
        real_link = os.link
        def fail_second(source, destination):
            if Path(source).name == UPGRADES and Path(destination) == self.upgrades:
                raise OSError("second link failed")
            return real_link(source, destination)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=fail_second), \
             patch("modules.importer.build_database") as build:
            with self.assertRaisesRegex(DataRefreshRecoveryError, "second link failed"):
                self.updater.update_and_build_database(
                    self.root / "fallback.db", self.weapons, self.upgrades)
        build.assert_not_called()
        stages = list(self.paths["source"].glob(".wdc-refresh-*"))
        self.assertEqual(len(stages), 1)
        self.assertTrue((stages[0] / "PUBLISHING.json").is_file())
        self.assertEqual((stages[0] / ("previous-" + WEAPONS)).read_bytes(), self.old_bytes[0])
        self.assertEqual((stages[0] / ("previous-" + UPGRADES)).read_bytes(), self.old_bytes[1])
        marker = json.loads((stages[0] / "PUBLISHING.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["mode"], "refresh-no-clobber")
        entry = next(item for item in marker["archives"] if item["destination"] == UPGRADES)
        self.assertEqual(entry["staged_copy"], UPGRADES)
        self.assertEqual(entry["displaced_copy"], UPGRADES)
        displaced = self.paths["source"] / marker["recovery_directory"] / UPGRADES
        self.assertEqual(displaced.read_bytes(), self.old_bytes[1])
        self.assertFalse(self.upgrades.exists())
        self.assertFalse((self.root / "fallback.db").exists())

    def test_marker_sync_failure_never_moves_a_destination(self) -> None:
        from modules.export_safety import UnfinishedExportPublication, require_complete_exports

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.fsync", side_effect=OSError("sync failed")):
            with self.assertRaisesRegex(OSError, "sync failed"):
                self.updater.refresh()
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)
        self.assertEqual(list(self.paths["source"].glob(".wdc-export-backup-*")), [])
        self.assertEqual(len(list(self.paths["source"].glob(".wdc-refresh-*/PUBLISHING.json"))), 1)
        with self.assertRaises(UnfinishedExportPublication):
            require_complete_exports(self.weapons, self.upgrades)

    def test_interrupt_after_displacing_original_keeps_it_and_blocks_import(self) -> None:
        from modules.export_safety import UnfinishedExportPublication, require_complete_exports

        real_rename = os.rename
        def interrupt_after_move(source, destination):
            real_rename(source, destination)
            if Path(source) == self.weapons:
                raise KeyboardInterrupt()

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.rename", side_effect=interrupt_after_move):
            with self.assertRaises(KeyboardInterrupt):
                self.updater.refresh()
        marker_path = next(self.paths["source"].glob(".wdc-refresh-*/PUBLISHING.json"))
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        displaced = self.paths["source"] / marker["recovery_directory"] / WEAPONS
        self.assertEqual(displaced.read_bytes(), self.old_bytes[0])
        self.assertFalse(self.weapons.exists())
        self.assertEqual(self.upgrades.read_bytes(), self.old_bytes[1])
        with self.assertRaises(UnfinishedExportPublication):
            require_complete_exports(self.weapons, self.upgrades)

    def test_interrupt_after_publication_retains_copies_and_blocks_import(self) -> None:
        real_link = os.link
        def interrupt_after_first(source, destination):
            result = real_link(source, destination)
            if Path(destination) == self.weapons:
                raise KeyboardInterrupt()
            return result

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=interrupt_after_first):
            with self.assertRaises(KeyboardInterrupt):
                self.updater.refresh()
        stages = list(self.paths["source"].glob(".wdc-refresh-*"))
        self.assertEqual(len(stages), 1)
        self.assertTrue((stages[0] / "PUBLISHING.json").is_file())
        self.assertEqual((stages[0] / ("previous-" + WEAPONS)).read_bytes(), self.old_bytes[0])
        self.assertEqual((stages[0] / ("previous-" + UPGRADES)).read_bytes(), self.old_bytes[1])
        self.assertEqual(self.upgrades.read_bytes(), self.old_bytes[1])
        from modules.export_safety import UnfinishedExportPublication, require_complete_exports
        with self.assertRaises(UnfinishedExportPublication):
            require_complete_exports(self.weapons, self.upgrades)

    def test_failed_publication_retains_backups_and_never_builds_a_mixed_pair(self) -> None:
        real_link = os.link
        def fail_publish(source, destination):
            if Path(source).name == UPGRADES and Path(destination) == self.upgrades:
                raise OSError("simulated failure")
            return real_link(source, destination)

        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.os.link", side_effect=fail_publish) as links, \
             patch("modules.importer.build_database") as build:
            with self.assertRaises(DataRefreshRecoveryError) as raised:
                self.updater.update_and_build_database(self.root / "fallback.db", self.weapons, self.upgrades)
        build.assert_not_called()
        self.assertTrue(all(not Path(call.args[0]).name.startswith("restore-")
                            for call in links.call_args_list))
        stages = list(self.paths["source"].glob(".wdc-refresh-*"))
        self.assertEqual(len(stages), 1)
        self.assertIn(str(stages[0]), str(raised.exception))
        self.assertEqual((stages[0] / ("previous-" + WEAPONS)).read_bytes(), self.old_bytes[0])
        self.assertEqual((stages[0] / ("previous-" + UPGRADES)).read_bytes(), self.old_bytes[1])
        marker = json.loads((stages[0] / "PUBLISHING.json").read_text(encoding="utf-8"))
        displaced = self.paths["source"] / marker["recovery_directory"] / UPGRADES
        self.assertEqual(displaced.read_bytes(), self.old_bytes[1])
        self.assertFalse(self.upgrades.exists())
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
original = os.link
def link_then_exit(src, dst):
    original(src, dst)
    if Path(dst).name == sys.argv[3]:
        os._exit(91)
with patch("modules.updater.os.link", side_effect=link_then_exit):
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

    def test_pretty_printed_export_is_bounded_while_zip_is_written(self) -> None:
        path = self.paths["temp"] / "encoded.zip"
        payload = {"items": [{"name": "value"} for _ in range(8)]}
        encoded = json.dumps(payload, indent=4).encode("utf-8")
        with patch("modules.updater.MAX_EXPORT_JSON_BYTES", len(encoded)):
            self.updater._write_zip(path, "data.json", payload)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read("data.json"), encoded)
        with patch("modules.updater.MAX_EXPORT_JSON_BYTES", len(encoded) - 1):
            with self.assertRaisesRegex(ValueError, "safety limit"):
                self.updater._write_zip(path, "data.json", payload)

    def test_expanded_json_limit_falls_back_without_publishing_the_staged_pair(self) -> None:
        # Both compact downloads fit 300 bytes, but formatting the first ZIP
        # member expands it beyond that cap. The old pair remains usable.
        self.assertLess(len(json.dumps(weapon_export("New Weapon")).encode()), 300)
        self.assertGreater(len(json.dumps(weapon_export("New Weapon"), indent=4).encode()), 300)
        db = self.root / "fallback-after-limit.db"
        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.MAX_EXPORT_JSON_BYTES", 300):
            result = self.updater.update_and_build_database(db, self.weapons, self.upgrades)
        self.assertEqual(result["source_mode"], "saved local exports")
        self.assertIn("safety limit", result["refresh_error"])
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])
        with closing(sqlite3.connect(db)) as connection:
            self.assertEqual(connection.execute("SELECT weapon FROM weapons").fetchone()[0], "Old Weapon")

    def test_oversized_downloaded_json_does_not_replace_saved_exports(self) -> None:
        with patch.object(self.updater, "_download", side_effect=self.download_fixture), \
             patch("modules.updater.MAX_EXPORT_JSON_BYTES", 32):
            with self.assertRaisesRegex(ValueError, "safety limit"):
                self.updater.refresh()
        self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), self.old_bytes)
        self.assertEqual(list(self.paths["source"].glob(".wdc-refresh-*")), [])

    def test_json_cleaning_rejects_duplicate_keys_at_any_depth(self) -> None:
        path = self.paths["temp"] / "duplicate.json"
        path.write_text('{"ExportWeapons": [{"name": "first", "name": "second"}]}',
                        encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate key 'name'"):
            self.updater._clean_json(path)

    def test_json_cleaning_rejects_invalid_utf8(self) -> None:
        path = self.paths["temp"] / "ExportWeapons_en.json"
        path.write_bytes(b'{"ExportWeapons": [], "x": "\xff"}')
        with self.assertRaises(UnicodeDecodeError):
            self.updater._clean_json(path)


if __name__ == "__main__":
    unittest.main()
