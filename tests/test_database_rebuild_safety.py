"""Full rebuilds must protect existing custom data before replacing the catalog."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from modules.database_backup import DatabaseBackupError, create_database_backup
from modules.database_revision import CURRENT_DATABASE_REVISION
from modules.importer import build_database


class DatabaseRebuildSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "data # with spaces" / "weapons.db"
        self.weapons = self.root / "weapons.zip"
        self.upgrades = self.root / "upgrades.zip"
        with zipfile.ZipFile(self.weapons, "w") as archive:
            archive.writestr("ExportWeapons_en_Cleaned.json", json.dumps({"ExportWeapons": [{
                "name": "Exported Weapon", "uniqueName": "/Lotus/Weapons/Test",
                "productCategory": "LongGuns", "totalDamage": 100,
                "damagePerShot": [100], "criticalChance": .2,
                "criticalMultiplier": 2, "procChance": .1,
            }]}))
        with zipfile.ZipFile(self.upgrades, "w") as archive:
            archive.writestr("ExportUpgrades_en_Cleaned.json", json.dumps({"ExportUpgrades": [{
                "name": "Exported Mod", "uniqueName": "/Lotus/Mods/Test", "type": "PRIMARY",
                "fusionLimit": 0, "description": ["Description"],
                "levelStats": [{"stats": ["+10% Damage"]}],
            }]}))
        build_database(self.db, self.weapons, self.upgrades)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("INSERT INTO mods(unique_name, name) VALUES('/custom/mod', 'Custom Mod')")
            connection.execute("INSERT INTO mod_effects VALUES('/custom/mod', 0, 1, 'TRUE', .75, '+75% Damage')")
            connection.execute("CREATE TABLE personal_notes (note TEXT)")
            connection.execute("INSERT INTO personal_notes VALUES ('before rebuild')")

    @staticmethod
    def inspect(path: Path) -> tuple:
        with closing(sqlite3.connect(path)) as connection:
            return (
                connection.execute("PRAGMA user_version").fetchone()[0],
                connection.execute("SELECT count(*) FROM mods WHERE unique_name='/custom/mod'").fetchone()[0],
                connection.execute("SELECT count(*) FROM mod_effects WHERE unique_name='/custom/mod'").fetchone()[0],
                connection.execute("SELECT note FROM personal_notes").fetchone()[0],
                connection.execute("PRAGMA integrity_check").fetchone()[0],
            )

    def test_existing_database_gets_consistent_unique_backup_before_rebuild(self):
        before = self.inspect(self.db)
        backup = build_database(self.db, self.weapons, self.upgrades)
        self.assertIsInstance(backup, Path)
        self.assertTrue(backup.is_file())
        self.assertEqual(self.inspect(backup), before)
        self.assertEqual(self.inspect(self.db), (CURRENT_DATABASE_REVISION, 0, 0, "before rebuild", "ok"))
        second = build_database(self.db, self.weapons, self.upgrades)
        self.assertNotEqual(second, backup)
        self.assertEqual(self.inspect(backup), before)
        self.assertTrue(second.is_file())

    def test_rebuild_backup_contains_committed_wal_content(self):
        with closing(sqlite3.connect(self.db)) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("UPDATE personal_notes SET note='committed in WAL'")
            writer.commit()
            backup = build_database(self.db, self.weapons, self.upgrades)
            self.assertEqual(self.inspect(backup)[3], "committed in WAL")
            self.assertEqual(self.inspect(self.db)[3], "committed in WAL")

    def test_conflicting_export_names_stop_before_rebuilding_existing_data(self):
        before = self.inspect(self.db)
        bad = self.root / "ambiguous.zip"
        entries = [dict(name="Ambiguous", uniqueName=f"/Lotus/Test/{i}",
                        productCategory="Pistols", totalDamage=damage,
                        damagePerShot=[damage]) for i, damage in enumerate((10, 20))]
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("weapons.json", json.dumps({"ExportWeapons": entries}))
        with self.assertRaisesRegex(ValueError, "Ambiguous.*conflict"):
            build_database(self.db, bad, self.upgrades)
        self.assertEqual(self.inspect(self.db), before)
        self.assertFalse((self.db.parent / "backups").exists())

    def test_locked_backup_deadline_is_not_extended_by_a_long_busy_timeout(self):
        # sqlite3_backup_step blocks inside SQLite's busy handler, so a caller
        # that connected with a long timeout would otherwise blow straight
        # through the deadline and report the lock up to a minute later.
        writer = sqlite3.connect(self.db)
        self.addCleanup(writer.close)
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("UPDATE personal_notes SET note='uncommitted'")
        with closing(sqlite3.connect(self.db)) as reader:
            self.addCleanup(writer.rollback)
            reader.execute("PRAGMA busy_timeout = 60000")
            started = time.monotonic()
            with patch("modules.database_backup.BACKUP_LOCK_DEADLINE_SECONDS", 0.05):
                with self.assertRaisesRegex(DatabaseBackupError, "stayed locked"):
                    create_database_backup(reader, self.db, label="locked")
            self.assertLess(time.monotonic() - started, 5.0)
            # The caller's own timeout survives the attempt.
            self.assertEqual(reader.execute("PRAGMA busy_timeout").fetchone()[0], 60000)

    def test_successful_backup_restores_the_callers_busy_timeout(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("PRAGMA busy_timeout = 7000")
            create_database_backup(connection, self.db, label="restore")
            self.assertEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 7000)

    def test_backup_failure_prevents_destructive_write(self):
        before = self.inspect(self.db)
        with patch("modules.importer.create_database_backup", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(RuntimeError, "disk full"):
                build_database(self.db, self.weapons, self.upgrades)
        self.assertEqual(self.inspect(self.db), before)

    def test_rebuild_failure_rolls_back_and_reports_retained_backup(self):
        before = self.inspect(self.db)
        def fail_after_write(connection, payload):
            connection.execute("DELETE FROM mods WHERE unique_name='/custom/mod'")
            raise RuntimeError("simulated rebuild failure")
        with patch("modules.importer.apply_import_payload", side_effect=fail_after_write):
            with self.assertRaisesRegex(RuntimeError, "simulated rebuild failure") as caught:
                build_database(self.db, self.weapons, self.upgrades)
        self.assertEqual(self.inspect(self.db), before)
        backup = caught.exception.backup_path
        self.assertIsInstance(backup, Path)
        self.assertEqual(self.inspect(backup), before)
        self.assertIn(str(backup), str(caught.exception))

    def test_process_exit_mid_rebuild_rolls_back_and_retains_backup(self):
        before = self.inspect(self.db)
        program = """
import os
import sys
from modules import importer

def interrupted(connection, payload):
    connection.execute("DELETE FROM mods WHERE unique_name='/custom/mod'")
    os._exit(92)

importer.apply_import_payload = interrupted
importer.build_database(*sys.argv[1:])
"""
        run = subprocess.run([sys.executable, "-c", program, str(self.db),
                              str(self.weapons), str(self.upgrades)],
                             cwd=Path(__file__).resolve().parents[1],
                             capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(run.returncode, 92, run.stderr)
        self.assertEqual(self.inspect(self.db), before)
        backups = list((self.db.parent / "backups").glob("*-pre-rebuild-v*.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.inspect(backups[0]), before)

    def test_concurrent_commit_after_backup_aborts_before_catalog_replacement(self):
        from modules.database_backup import create_database_backup
        def backup_then_change(connection, db_path, **kwargs):
            backup = create_database_backup(connection, db_path, **kwargs)
            with closing(sqlite3.connect(db_path)) as other, other:
                other.execute("UPDATE personal_notes SET note='changed elsewhere'")
            return backup
        with patch("modules.importer.create_database_backup", side_effect=backup_then_change):
            with self.assertRaisesRegex(RuntimeError, "changed during backup") as caught:
                build_database(self.db, self.weapons, self.upgrades)
        self.assertEqual(self.inspect(self.db), (CURRENT_DATABASE_REVISION, 1, 1, "changed elsewhere", "ok"))
        self.assertEqual(self.inspect(caught.exception.backup_path)[3], "before rebuild")

    def test_placeholder_populated_during_preflight_is_not_silently_replaced(self):
        # Commit just before the first data_version observation. If an earlier
        # empty-file probe is trusted, the custom rows are rebuilt without backup.
        from modules.importer import create_schema
        empty = self.root / "racing-bootstrap.db"
        empty.touch()
        real_connect = sqlite3.connect
        injected = False

        class RacingConnection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def __enter__(self):
                self.connection.__enter__()
                return self

            def __exit__(self, *args):
                return self.connection.__exit__(*args)

            def execute(self, sql, *args):
                nonlocal injected
                if sql == "PRAGMA data_version" and not injected:
                    injected = True
                    with closing(real_connect(empty)) as other, other:
                        create_schema(other)
                        other.execute("INSERT INTO mods(unique_name, name) VALUES('/custom/mod', 'Custom Mod')")
                        other.execute("INSERT INTO mod_effects VALUES('/custom/mod', 0, 1, 'TRUE', .75, '+75% Damage')")
                        other.execute("CREATE TABLE personal_notes(note TEXT)")
                        other.execute("INSERT INTO personal_notes VALUES('concurrent bootstrap')")
                return self.connection.execute(sql, *args)

        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            if kwargs.get("uri") and "mode=rw" in str(args[0]):
                return RacingConnection(connection)
            return connection

        with patch("modules.importer.sqlite3.connect", side_effect=connect):
            backup = build_database(empty, self.weapons, self.upgrades)
        self.assertTrue(injected)
        self.assertIsInstance(backup, Path)
        self.assertEqual(self.inspect(backup)[1:], (1, 1, "concurrent bootstrap", "ok"))

    def test_offline_updater_returns_the_backup_path(self):
        from modules.updater import WarframeDataUpdater
        with patch("modules.updater.ensure_app_dirs", return_value={}):
            updater = WarframeDataUpdater()
        output = updater.update_and_build_database(self.db, self.weapons, self.upgrades,
                                                   allow_bundled_fallback=False)
        backup = output["backup_path"]
        self.assertIsInstance(backup, Path)
        self.assertEqual(self.inspect(backup)[1:3], (1, 1))
        self.assertEqual(self.inspect(self.db)[1:3], (0, 0))
        self.assertEqual(output["source_mode"], "saved local exports")

    def test_manual_command_prints_pre_rebuild_backup_path(self):
        import build_database as command
        source = self.root / "command-source"
        source.mkdir()
        shutil.copy2(self.weapons, source / "ExportWeapons_en_Cleaned.zip")
        shutil.copy2(self.upgrades, source / "ExportKeys_en_Cleaned.zip")
        output = io.StringIO()
        with patch.object(command, "seed_source_files"), \
             patch.object(command, "ensure_app_dirs", return_value={"db": self.db, "source": source}), \
             contextlib.redirect_stdout(output):
            command.main()
        backups = list((self.db.parent / "backups").glob("*-pre-rebuild-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertIn(f"Previous database backup: {backups[0]}", output.getvalue())
        self.assertEqual(self.inspect(backups[0])[1:3], (1, 1))

    def test_new_database_does_not_create_a_backup(self):
        fresh = self.root / "new" / "new.db"
        result = build_database(fresh, self.weapons, self.upgrades)
        self.assertIsNone(result)
        self.assertTrue(fresh.is_file())
        self.assertFalse((fresh.parent / "backups").exists())

    def test_empty_bootstrap_placeholder_does_not_create_a_meaningless_backup(self):
        fresh = self.root / "empty" / "new.db"
        fresh.parent.mkdir()
        fresh.touch()
        result = build_database(fresh, self.weapons, self.upgrades)
        self.assertIsNone(result)
        self.assertTrue(fresh.is_file())
        self.assertFalse((fresh.parent / "backups").exists())


if __name__ == "__main__":
    unittest.main()
