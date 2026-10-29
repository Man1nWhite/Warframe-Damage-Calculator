"""Never initialize a database over potentially recoverable SQLite sidecars."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from modules.database import WeaponRepository
from modules.database_migration import DatabaseMigrationError, migrate_database
from modules.importer import DatabaseRebuildError, build_database
from modules.updater import WarframeDataUpdater


class DatabaseSidecarSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.weapons = self.root / "weapons.zip"
        self.upgrades = self.root / "upgrades.zip"
        with zipfile.ZipFile(self.weapons, "w") as archive:
            archive.writestr("ExportWeapons_en_Cleaned.json", json.dumps({"ExportWeapons": [{
                "name": "Test Weapon", "uniqueName": "/Lotus/Weapons/Test", "productCategory": "LongGuns",
                "totalDamage": 100, "damagePerShot": [100],
            }]}))
        with zipfile.ZipFile(self.upgrades, "w") as archive:
            archive.writestr("ExportUpgrades_en_Cleaned.json", json.dumps({"ExportUpgrades": [{
                "name": "Test Mod", "uniqueName": "/Lotus/Mods/Test", "type": "PRIMARY",
                "fusionLimit": 0, "levelStats": [{"stats": ["+10% Damage"]}],
            }]}))

    def case(self, name: str, *, empty: bool, suffix: str) -> tuple[Path, Path, bytes]:
        directory = self.root / name
        directory.mkdir()
        database = directory / "weapons.db"
        if empty:
            database.touch()
        sidecar = Path(str(database) + suffix)
        content = b"potentially recoverable SQLite data: " + suffix.encode()
        sidecar.write_bytes(content)
        return database, sidecar, content

    def assert_case_untouched(self, database: Path, sidecar: Path, content: bytes, *, empty: bool) -> None:
        self.assertEqual(database.exists(), empty)
        if empty:
            self.assertEqual(database.stat().st_size, 0)
        self.assertEqual(sidecar.read_bytes(), content)

    def test_repository_never_opens_missing_or_empty_main_with_sidecar(self) -> None:
        for empty in (False, True):
            for suffix in ("-wal", "-shm", "-journal"):
                with self.subTest(empty=empty, suffix=suffix):
                    database, sidecar, content = self.case(f"repo-{empty}-{suffix}", empty=empty, suffix=suffix)
                    with self.assertRaisesRegex(sqlite3.OperationalError, "(?i)sidecar"):
                        WeaponRepository(database).search_weapons("")
                    self.assert_case_untouched(database, sidecar, content, empty=empty)

    def test_migration_refuses_to_treat_sidecars_as_a_new_database(self) -> None:
        for empty in (False, True):
            for suffix in ("-wal", "-shm", "-journal"):
                with self.subTest(empty=empty, suffix=suffix):
                    database, sidecar, content = self.case(f"migration-{empty}-{suffix}", empty=empty, suffix=suffix)
                    with self.assertRaisesRegex(DatabaseMigrationError, "(?i)sidecar"):
                        migrate_database(database, self.weapons, self.upgrades)
                    self.assert_case_untouched(database, sidecar, content, empty=empty)

    def test_rebuild_refuses_to_create_over_orphan_sidecars(self) -> None:
        for empty in (False, True):
            for suffix in ("-wal", "-shm", "-journal"):
                with self.subTest(empty=empty, suffix=suffix):
                    database, sidecar, content = self.case(f"rebuild-{empty}-{suffix}", empty=empty, suffix=suffix)
                    with self.assertRaisesRegex(DatabaseRebuildError, "(?i)sidecar"):
                        build_database(database, self.weapons, self.upgrades)
                    self.assert_case_untouched(database, sidecar, content, empty=empty)
                    self.assertFalse((database.parent / "backups").exists())

    def test_updater_checks_sidecars_before_download_or_export_publication(self) -> None:
        with patch("modules.updater.ensure_app_dirs", return_value={}):
            updater = WarframeDataUpdater()
        for empty in (False, True):
            with self.subTest(empty=empty):
                database, sidecar, content = self.case(f"update-{empty}", empty=empty, suffix="-wal")
                original = (self.weapons.read_bytes(), self.upgrades.read_bytes())
                with patch.object(updater, "refresh") as refresh:
                    with self.assertRaisesRegex(sqlite3.OperationalError, "(?i)sidecar"):
                        updater.update_and_build_database(database, self.weapons, self.upgrades)
                refresh.assert_not_called()
                self.assertEqual((self.weapons.read_bytes(), self.upgrades.read_bytes()), original)
                self.assert_case_untouched(database, sidecar, content, empty=empty)

    def test_real_crash_left_wal_survives_until_the_matching_main_is_restored(self) -> None:
        database = self.root / "crash.db"
        script = r'''
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("CREATE TABLE notes (value TEXT)")
connection.execute("INSERT INTO notes VALUES ('recover me')")
connection.commit()
os._exit(73)
'''
        child = subprocess.run([sys.executable, "-c", script, str(database)], timeout=15, check=False)
        self.assertEqual(child.returncode, 73)
        wal = Path(str(database) + "-wal")
        self.assertGreater(wal.stat().st_size, 0)
        before = wal.read_bytes()
        missing_main = self.root / "crash-main.saved"
        database.rename(missing_main)
        with self.assertRaisesRegex(sqlite3.OperationalError, "(?i)sidecar"):
            WeaponRepository(database).search_weapons("")
        self.assertFalse(database.exists())
        self.assertEqual(wal.read_bytes(), before)
        missing_main.rename(database)
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM notes").fetchone()[0], "recover me")

    def test_sidecars_beside_a_symlink_target_are_also_preserved(self) -> None:
        database, sidecar, content = self.case("target", empty=True, suffix="-wal")
        link_dir = self.root / "links"
        link_dir.mkdir()
        alias = link_dir / "weapons.db"
        try:
            alias.symlink_to(database)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        with self.assertRaisesRegex(sqlite3.OperationalError, "(?i)sidecar"):
            WeaponRepository(alias).search_weapons("")
        self.assertTrue(alias.is_symlink())
        self.assert_case_untouched(database, sidecar, content, empty=True)

    def test_empty_or_dangling_sidecars_are_still_preserved(self) -> None:
        database = self.root / "ambiguous.db"
        sidecar = Path(str(database) + "-wal")
        sidecar.touch()
        with self.assertRaisesRegex(sqlite3.OperationalError, "(?i)sidecar"):
            WeaponRepository(database).search_weapons("")
        self.assertFalse(database.exists())
        self.assertEqual(sidecar.stat().st_size, 0)
        sidecar.unlink()
        try:
            sidecar.symlink_to("missing-wal-file")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        with self.assertRaisesRegex(sqlite3.OperationalError, "(?i)sidecar"):
            WeaponRepository(database).search_weapons("")
        self.assertTrue(sidecar.is_symlink())
        self.assertFalse(database.exists())

    def test_dangling_database_symlink_is_not_followed_or_recreated(self) -> None:
        database = self.root / "db-link"
        try:
            database.symlink_to("missing-target.db")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        with self.assertRaisesRegex(sqlite3.OperationalError, "(?i)dangling"):
            WeaponRepository(database).search_weapons("")
        self.assertTrue(database.is_symlink())
        self.assertFalse((self.root / "missing-target.db").exists())

    def test_new_database_and_memory_database_still_work_without_sidecars(self) -> None:
        fresh = self.root / "fresh" / "weapons.db"
        self.assertIsNone(build_database(fresh, self.weapons, self.upgrades))
        self.assertEqual(WeaponRepository(fresh).search_weapons(""), ["Test Weapon"])
        self.assertEqual(WeaponRepository(":memory:").search_weapons(""), [])
        self.assertIsNone(build_database(":memory:", self.weapons, self.upgrades))


if __name__ == "__main__":
    unittest.main()
