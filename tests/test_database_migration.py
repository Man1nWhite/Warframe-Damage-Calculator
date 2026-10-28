"""Offline, transactional migration of legacy AppData databases."""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from modules import database_migration as migration
from modules.database_revision import CURRENT_DATABASE_REVISION, UnsupportedDatabaseRevision
from modules.importer import build_database, rows_from_cleaned_json, upsert_weapon_rows
from modules.updater import WarframeDataUpdater
from modules.weapon_export_policy import GRIMOIRE_DOPPELGANGER_ID, GRIMOIRE_PLAYER_ID

ROOT = Path(__file__).resolve().parents[1]
WEAPONS = ROOT / "source" / "ExportWeapons_en_Cleaned.zip"
UPGRADES = ROOT / "source" / "ExportKeys_en_Cleaned.zip"
SPREADSHEET = ROOT / "source" / "Warframe-Damage-Calculator_v2.xlsx"
MURMUR = "/Lotus/Upgrades/Mods/Shotgun/WeaponShotgunFactionDamageMurmurs"


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "data" / "weapons.db"
        self.db.parent.mkdir()
        (self.root / "builds").mkdir()
        (self.root / "builds" / "my-build.json").write_text('{"weapon":"Custom Weapon"}')
        (self.root / "settings.json").write_text('{"custom":"value"}')
        shutil.copy2(ROOT / "data" / "weapons.db", self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("PRAGMA user_version = 0")
            # The old index mapping put innate Electricity into Heat.
            connection.execute("UPDATE weapons SET heat=75, cold=0, elec=0 "
                               "WHERE weapon='Alternox Prime'")
            connection.execute("DELETE FROM mod_effects WHERE unique_name=?", (MURMUR,))
            connection.execute("INSERT INTO weapons(weapon, dmg) VALUES ('Custom Weapon', 17)")
            connection.execute("INSERT INTO mods(unique_name, name, supported) VALUES ('custom-mod', 'Custom Mod', 1)")
            connection.execute("INSERT INTO mod_effects VALUES ('custom-mod', 0, 1, 'HEAT', 0.5, '+50% Heat')")
            connection.execute("CREATE TABLE personal_notes (note TEXT)")
            connection.execute("INSERT INTO personal_notes VALUES ('keep me')")

    def migrate(self):
        return migration.migrate_database(self.db, WEAPONS, UPGRADES, SPREADSHEET)

    def test_fixture_closes_database_handles_before_directory_cleanup(self):
        # A SQLite transaction context commits but does not close. Keep the
        # handles alive to prove the fixture closes them without relying on GC.
        class TrackingConnection(sqlite3.Connection):
            closed = False
            def close(self):
                self.closed = True
                super().close()

        real_connect = sqlite3.connect
        connections = []
        def tracked_connect(*args, **kwargs):
            connection = real_connect(*args, factory=TrackingConnection, **kwargs)
            connections.append(connection)
            return connection

        fixture = DatabaseMigrationTests(
            methodName="test_fixture_closes_database_handles_before_directory_cleanup")
        with patch("sqlite3.connect", side_effect=tracked_connect):
            fixture.setUp()
            try:
                fixture.inspect(fixture.db)
                fixture.set_legacy_grimoire()
                fixture.grimoire_row(fixture.db)
                self.assertGreaterEqual(len(connections), 4)
                self.assertTrue(all(connection.closed for connection in connections))
            finally:
                self.assertTrue(fixture.doCleanups())

    @staticmethod
    def inspect(path: Path):
        with closing(sqlite3.connect(path)) as connection, connection:
            return (
                connection.execute("PRAGMA user_version").fetchone()[0],
                connection.execute("SELECT heat,cold,elec FROM weapons "
                                   "WHERE weapon='Alternox Prime'").fetchone(),
                connection.execute("SELECT COUNT(*) FROM mod_effects WHERE unique_name=? "
                                   "AND effect_code='BANE_MURMUR'", (MURMUR,)).fetchone()[0],
                connection.execute("SELECT note FROM personal_notes").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM mods WHERE unique_name='custom-mod'").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM mod_effects WHERE unique_name='custom-mod'").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM weapons WHERE weapon='Custom Weapon'").fetchone()[0],
            )

    def test_migrates_and_keeps_a_consistent_backup(self):
        old = self.inspect(self.db)
        result = self.migrate()
        self.assertEqual(result.status, "migrated")
        self.assertEqual(result.from_revision, 0)
        self.assertTrue(result.backup_path.is_file())
        self.assertEqual(result.backup_path.parent, self.db.parent / "backups")
        self.assertEqual(self.inspect(result.backup_path), old)
        revision, elements, effects, note, mods, mod_effects, weapons = self.inspect(self.db)
        self.assertEqual(revision, CURRENT_DATABASE_REVISION)
        self.assertEqual(elements, (0, 0, 75))
        self.assertGreater(effects, 0)
        self.assertEqual((note, mods, mod_effects, weapons), ("keep me", 1, 1, 1))
        self.assertEqual(json.loads((self.root / "builds" / "my-build.json").read_text()),
                         {"weapon": "Custom Weapon"})
        self.assertEqual(json.loads((self.root / "settings.json").read_text()),
                         {"custom": "value"})
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
        # A current database doesn't need source files and never makes another backup.
        self.assertEqual(migration.migrate_database(self.db, "missing", "missing").status, "current")
        self.assertEqual(len(list(result.backup_path.parent.glob("*.sqlite3"))), 1)

    def test_bad_or_missing_exports_leave_legacy_database_unchanged(self):
        old = self.inspect(self.db)
        corrupt = self.root / "bad.zip"
        corrupt.write_bytes(b"not a zip")
        no_json = self.root / "no-json.zip"
        with zipfile.ZipFile(no_json, "w") as archive:
            archive.writestr("README.txt", "not a weapon export")
        for weapons, upgrades in ((corrupt, UPGRADES), (no_json, UPGRADES),
                                  (WEAPONS, self.root / "missing.zip")):
            with self.subTest(weapons=weapons, upgrades=upgrades):
                with self.assertRaises(migration.DatabaseMigrationError):
                    migration.migrate_database(self.db, weapons, upgrades)
                self.assertEqual(self.inspect(self.db), old)
                self.assertFalse((self.db.parent / "backups").exists())

    def test_write_failure_rolls_back_and_retains_backup(self):
        old = self.inspect(self.db)
        def fail_mid_import(connection, payload, *, preserve_unmatched_mods):
            connection.execute("UPDATE weapons SET heat=999 WHERE weapon='Alternox Prime'")
            connection.execute("PRAGMA user_version = 1")
            raise RuntimeError("simulated write failure")
        with patch.object(migration, "apply_import_payload", side_effect=fail_mid_import):
            with self.assertRaises(migration.DatabaseMigrationError) as caught:
                self.migrate()
        self.assertEqual(self.inspect(self.db), old)
        self.assertIsNotNone(caught.exception.backup_path)
        self.assertEqual(self.inspect(caught.exception.backup_path), old)
        result = self.migrate()
        self.assertNotEqual(result.backup_path, caught.exception.backup_path)
        self.assertTrue(caught.exception.backup_path.exists())
        self.assertEqual(len(list(result.backup_path.parent.glob("*.sqlite3"))), 2)

    def test_partial_export_cannot_mark_unmatched_official_rows_current(self):
        old = self.inspect(self.db)
        partial = self.root / "partial.zip"
        with zipfile.ZipFile(WEAPONS) as original:
            name = next(n for n in original.namelist() if n.endswith(".json"))
            payload = json.loads(original.read(name))
        payload["ExportWeapons"] = payload["ExportWeapons"][:1]
        with zipfile.ZipFile(partial, "w") as archive:
            archive.writestr(name, json.dumps(payload))
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "do not cover"):
            migration.migrate_database(self.db, partial, UPGRADES)
        self.assertEqual(self.inspect(self.db), old)
        self.assertFalse((self.db.parent / "backups").exists())

    def test_missing_effect_rank_cannot_erase_previously_parsed_effects(self):
        old = self.inspect(self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            unique, rank = connection.execute(
                "SELECT unique_name, rank FROM mod_effects "
                "WHERE unique_name LIKE '/Lotus/%' LIMIT 1").fetchone()
        with zipfile.ZipFile(UPGRADES) as original:
            name = "ExportUpgrades_en_Cleaned.json"
            payload = json.loads(original.read(name))
        item = next(m for m in payload["ExportUpgrades"] if m.get("uniqueName") == unique)
        item["levelStats"][rank]["stats"] = []
        incomplete = self.root / "incomplete-mod-rank.zip"
        with zipfile.ZipFile(incomplete, "w") as archive:
            archive.writestr(name, json.dumps(payload))
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "mod-effect ranks"):
            migration.migrate_database(self.db, WEAPONS, incomplete, SPREADSHEET)
        self.assertEqual(self.inspect(self.db), old)

    def add_legacy_false_positives(self):
        # The bundled revision-2 snapshot is clean; construct actual
        # revision-0/1-style stale rows explicitly instead of depending on it.
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("INSERT INTO mod_effects VALUES (?,3,1,'BLAST',.24,'+24% blast range')",
                               ("/Lotus/Upgrades/Mods/Rifle/WeaponIncreaseRadialExplosionMod",))
            connection.execute("INSERT INTO mod_effects VALUES (?,3,1,'TOXIN',1.0,'+100% toxin damage')",
                               ("/Lotus/Upgrades/Mods/Sets/Spider/SpiderModC",))

    def test_unsupported_legacy_fragments_are_removed_only_with_matching_source(self):
        firestorm = "/Lotus/Upgrades/Mods/Rifle/WeaponIncreaseRadialExplosionMod"
        proton = "/Lotus/Upgrades/Mods/Sets/Spider/SpiderModC"
        self.add_legacy_false_positives()
        result = self.migrate()
        with closing(sqlite3.connect(result.backup_path)) as old, old, \
             closing(sqlite3.connect(self.db)) as current, current:
            for unique in (firestorm, proton):
                with self.subTest(unique=unique):
                    self.assertGreater(old.execute("SELECT count(*) FROM mod_effects WHERE unique_name=?",
                                                   (unique,)).fetchone()[0], 0)
                    self.assertEqual(current.execute("SELECT count(*) FROM mod_effects WHERE unique_name=?",
                                                     (unique,)).fetchone()[0], 0)
                    self.assertEqual(current.execute("SELECT supported FROM mods WHERE unique_name=?",
                                                     (unique,)).fetchone()[0], 0)
            self.assertEqual(current.execute("SELECT count(*) FROM mod_effects WHERE unique_name='custom-mod'").fetchone()[0], 1)

    def test_unrelated_unparsed_replacement_does_not_pass_rank_coverage(self):
        self.add_legacy_false_positives()
        old = self.inspect(self.db)
        firestorm = "/Lotus/Upgrades/Mods/Rifle/WeaponIncreaseRadialExplosionMod"
        with zipfile.ZipFile(UPGRADES) as original:
            name = "ExportUpgrades_en_Cleaned.json"
            payload = json.loads(original.read(name))
        item = next(m for m in payload["ExportUpgrades"] if m.get("uniqueName") == firestorm)
        item["levelStats"][3]["stats"] = ["+24% Void Sling Range"]
        incomplete = self.root / "different-unparsed-rank.zip"
        with zipfile.ZipFile(incomplete, "w") as archive:
            archive.writestr(name, json.dumps(payload))
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "mod-effect ranks"):
            migration.migrate_database(self.db, WEAPONS, incomplete, SPREADSHEET)
        self.assertEqual(self.inspect(self.db), old)
        self.assertFalse((self.db.parent / "backups").exists())

    def test_missing_fragment_is_rejected_even_if_another_effect_at_rank_survives(self):
        amar = "/Lotus/Upgrades/Mods/Sets/Amar/AmarMeleeMod"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("INSERT INTO mod_effects VALUES (?, 5, 99, 'TRUE', 0.5, '+50% Damage')", (amar,))
        before = self.inspect(self.db)
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "mod-effect ranks"):
            self.migrate()
        self.assertEqual(self.inspect(self.db), before)
        self.assertFalse((self.db.parent / "backups").exists())

    def test_revision_one_refreshes_only_official_mods_with_a_backup(self):
        pressure = "/Lotus/Upgrades/Mods/Melee/Expert/WeaponMeleeDamageModExpert"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("PRAGMA user_version=1")
            connection.execute("DELETE FROM mod_effects WHERE unique_name=?", (pressure,))
            connection.execute("UPDATE mods SET supported=0 WHERE unique_name=?", (pressure,))
            # Even an edited official weapon must not be overwritten by a mod-only migration.
            connection.execute("UPDATE weapons SET heat=123 WHERE weapon='Alternox Prime'")
        old = self.inspect(self.db)
        result = self.migrate()
        self.assertEqual((result.status, result.from_revision), ("migrated", 1))
        self.assertEqual(self.inspect(result.backup_path), old)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], CURRENT_DATABASE_REVISION)
            self.assertEqual(connection.execute("SELECT heat FROM weapons WHERE weapon='Alternox Prime'").fetchone()[0], 123)
            self.assertEqual(connection.execute("SELECT supported FROM mods WHERE unique_name=?", (pressure,)).fetchone()[0], 1)
            self.assertAlmostEqual(connection.execute(
                "SELECT effect_value FROM mod_effects WHERE unique_name=? AND rank=10 AND effect_code='TRUE'",
                (pressure,)).fetchone()[0], 1.65)
            self.assertEqual(connection.execute("SELECT count(*) FROM mod_effects WHERE unique_name='custom-mod'").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT note FROM personal_notes").fetchone()[0], "keep me")

    def test_revision_one_mod_refresh_rolls_back_and_retains_backup(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("PRAGMA user_version=1")
        old = self.inspect(self.db)
        def fail_mid_mod_import(connection, payload):
            connection.execute("DELETE FROM mod_effects WHERE unique_name='custom-mod'")
            raise RuntimeError("simulated mod refresh failure")
        with patch.object(migration, "apply_mod_import_payload", side_effect=fail_mid_mod_import):
            with self.assertRaises(migration.DatabaseMigrationError) as caught:
                self.migrate()
        self.assertEqual(self.inspect(self.db), old)
        self.assertEqual(self.inspect(caught.exception.backup_path), old)

    def test_revision_one_preserves_weapons_not_in_the_saved_weapon_export(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("PRAGMA user_version=1")
            connection.execute("UPDATE weapons SET heat=456 WHERE weapon='Alternox Prime'")
        partial = self.root / "partial-weapons.zip"
        with zipfile.ZipFile(WEAPONS) as original:
            name = next(n for n in original.namelist() if n.endswith(".json"))
            payload = json.loads(original.read(name))
        payload["ExportWeapons"] = payload["ExportWeapons"][:1]
        with zipfile.ZipFile(partial, "w") as archive:
            archive.writestr(name, json.dumps(payload))
        result = migration.migrate_database(self.db, partial, UPGRADES, SPREADSHEET)
        self.assertEqual(result.from_revision, 1)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("SELECT heat FROM weapons WHERE weapon='Alternox Prime'").fetchone()[0], 456)
            self.assertEqual(connection.execute("SELECT count(*) FROM weapons WHERE weapon='Custom Weapon'").fetchone()[0], 1)

    def test_process_exit_during_revision_one_mod_refresh_rolls_back(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("PRAGMA user_version=1")
        old = self.inspect(self.db)
        program = '''
import os, sys
from modules import database_migration as migration

def interrupted(connection, payload):
    connection.execute("DELETE FROM mod_effects WHERE unique_name='custom-mod'")
    os._exit(93)

migration.apply_mod_import_payload = interrupted
migration.migrate_database(*sys.argv[1:])
'''
        result = subprocess.run([sys.executable, "-c", program, str(self.db), str(WEAPONS),
                                 str(UPGRADES), str(SPREADSHEET)], cwd=ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 93, result.stderr)
        self.assertEqual(self.inspect(self.db), old)
        backups = list((self.db.parent / "backups").glob("*-pre-v1-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.inspect(backups[0]), old)

    def test_non_finite_numbers_are_rejected_before_writes(self):
        old = self.inspect(self.db)
        corrupt = self.root / "nonfinite.zip"
        with zipfile.ZipFile(WEAPONS) as original:
            name = next(n for n in original.namelist() if n.endswith(".json"))
            payload = json.loads(original.read(name))
        payload["ExportWeapons"][0]["totalDamage"] = float("inf")
        with zipfile.ZipFile(corrupt, "w") as archive:
            archive.writestr(name, json.dumps(payload))
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "non-finite"):
            migration.migrate_database(self.db, corrupt, UPGRADES)
        self.assertEqual(self.inspect(self.db), old)

    def test_manual_rebuild_write_failure_rolls_back_schema_and_data(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("DROP INDEX idx_mods_slot_group")
        old = self.inspect(self.db)
        def fail_mid_import(connection, payload, *, preserve_unmatched_mods=False):
            connection.execute("UPDATE weapons SET heat=999 WHERE weapon='Alternox Prime'")
            connection.execute("PRAGMA user_version=1")
            raise RuntimeError("write failed")
        with patch("modules.importer.apply_import_payload", side_effect=fail_mid_import):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                build_database(self.db, WEAPONS, UPGRADES, SPREADSHEET)
        self.assertEqual(self.inspect(self.db), old)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master "
                                                 "WHERE name='idx_mods_slot_group'").fetchone())

    def test_concurrent_change_is_not_overwritten(self):
        original_backup = migration._backup_database
        def backup_then_change(connection, path, revision):
            backup = original_backup(connection, path, revision)
            with closing(sqlite3.connect(path)) as other, other:
                other.execute("UPDATE personal_notes SET note='changed elsewhere'")
            return backup
        with patch.object(migration, "_backup_database", side_effect=backup_then_change):
            with self.assertRaises(migration.DatabaseMigrationError) as caught:
                self.migrate()
        self.assertIn("changed during backup", str(caught.exception))
        self.assertEqual(self.inspect(self.db)[0], 0)
        self.assertEqual(self.inspect(self.db)[3], "changed elsewhere")
        self.assertEqual(self.inspect(caught.exception.backup_path)[3], "keep me")

    def test_locked_backup_fails_without_leaving_a_partial_file(self):
        old = self.inspect(self.db)
        original_coverage = migration._validate_legacy_coverage
        writer = sqlite3.connect(self.db)
        def lock_after_validation(connection, payload):
            original_coverage(connection, payload)
            writer.execute("BEGIN EXCLUSIVE")
            writer.execute("UPDATE personal_notes SET note='uncommitted'")
        try:
            with patch.object(migration, "_validate_legacy_coverage", side_effect=lock_after_validation), \
                 patch("modules.database_backup.time.monotonic", side_effect=[0.0] + [10.0] * 100):
                with self.assertRaisesRegex(migration.DatabaseMigrationError, "stayed locked"):
                    self.migrate()
        finally:
            writer.rollback()
            writer.close()
        self.assertEqual(self.inspect(self.db), old)
        self.assertEqual(list((self.db.parent / "backups").glob("*.sqlite3")), [])

    def test_future_database_is_not_downgraded_or_refreshed(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(f"PRAGMA user_version = {CURRENT_DATABASE_REVISION + 1}")
        old = self.inspect(self.db)
        with self.assertRaises(UnsupportedDatabaseRevision):
            self.migrate()
        with self.assertRaises(UnsupportedDatabaseRevision):
            build_database(self.db, WEAPONS, UPGRADES, SPREADSHEET)
        with patch("modules.updater.ensure_app_dirs", return_value={}), \
             patch.object(WarframeDataUpdater, "refresh") as refresh:
            updater = WarframeDataUpdater()
            with self.assertRaises(UnsupportedDatabaseRevision):
                updater.update_and_build_database(self.db, WEAPONS, UPGRADES, SPREADSHEET)
            refresh.assert_not_called()
        self.assertEqual(self.inspect(self.db), old)
        self.assertFalse((self.db.parent / "backups").exists())

    def test_backup_includes_committed_wal_content(self):
        with closing(sqlite3.connect(self.db)) as writer, writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("UPDATE personal_notes SET note='in the WAL'")
            writer.commit()
            result = self.migrate()
            self.assertEqual(self.inspect(result.backup_path)[3], "in the WAL")
            self.assertEqual(self.inspect(self.db)[3], "in the WAL")

    def test_absent_path_is_not_created(self):
        missing = self.root / "not-a-database.db"
        self.assertEqual(migration.migrate_database(missing, WEAPONS, UPGRADES).status, "missing")
        self.assertFalse(missing.exists())
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "not a regular file"):
            migration.migrate_database(self.root, WEAPONS, UPGRADES)

    def test_manual_command_migrates_legacy_data_without_deleting_custom_mods(self):
        import build_database as command
        from modules.app_paths import ensure_app_dirs

        with patch.dict(os.environ, {"APPDATA": str(self.root / "app data")}):
            paths = ensure_app_dirs()
            shutil.copy2(self.db, paths["db"])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                command.main()
        self.assertIn("Previous database backup:", output.getvalue())
        result = self.inspect(paths["db"])
        self.assertEqual(result[0], CURRENT_DATABASE_REVISION)
        self.assertEqual(result[4:7], (1, 1, 1))
        self.assertEqual(len(list((paths["data"] / "backups").glob("*.sqlite3"))), 1)

    def test_path_with_spaces_and_hash_is_opened_correctly(self):
        special_dir = self.root / "data # with spaces"
        special_dir.mkdir()
        special_db = special_dir / "weapons.db"
        shutil.copy2(self.db, special_db)
        result = migration.migrate_database(special_db, WEAPONS, UPGRADES, SPREADSHEET)
        self.assertEqual(result.status, "migrated")
        self.assertEqual(self.inspect(special_db)[0], CURRENT_DATABASE_REVISION)
        self.assertTrue(result.backup_path.is_file())

    def test_incompatible_current_schema_is_not_used(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(f"PRAGMA user_version={CURRENT_DATABASE_REVISION}")
            connection.execute("ALTER TABLE weapons RENAME COLUMN heat TO missing_heat")
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "missing required columns"):
            self.migrate()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],
                             CURRENT_DATABASE_REVISION)
        self.assertFalse((self.db.parent / "backups").exists())

    def set_legacy_grimoire(self, revision=2):
        legacy = next(row for row in rows_from_cleaned_json(WEAPONS)
                      if row["unique_name"] == GRIMOIRE_DOPPELGANGER_ID)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            upsert_weapon_rows(connection, [legacy])
            connection.execute(f"PRAGMA user_version={revision}")

    @staticmethod
    def grimoire_row(path):
        with closing(sqlite3.connect(path)) as connection, connection:
            return connection.execute("SELECT * FROM weapons WHERE weapon='Grimoire'").fetchone()

    def test_revision_two_repairs_only_unedited_legacy_grimoire_with_backup(self):
        self.set_legacy_grimoire()
        legacy = self.grimoire_row(self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            before_weapons = connection.execute(
                "SELECT * FROM weapons WHERE weapon!='Grimoire' ORDER BY weapon").fetchall()
            before_mods = connection.execute("SELECT * FROM mods ORDER BY unique_name").fetchall()
            before_effects = connection.execute(
                "SELECT * FROM mod_effects ORDER BY unique_name,rank,position").fetchall()
        result = self.migrate()
        self.assertEqual((result.status, result.from_revision), ("migrated", 2))
        self.assertEqual(self.grimoire_row(result.backup_path), legacy)
        row = self.grimoire_row(self.db)
        self.assertEqual(row[1], GRIMOIRE_PLAYER_ID)
        self.assertEqual(row[4], 150)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], CURRENT_DATABASE_REVISION)
            self.assertEqual(connection.execute(
                "SELECT * FROM weapons WHERE weapon!='Grimoire' ORDER BY weapon").fetchall(), before_weapons)
            self.assertEqual(connection.execute("SELECT * FROM mods ORDER BY unique_name").fetchall(), before_mods)
            self.assertEqual(connection.execute(
                "SELECT * FROM mod_effects ORDER BY unique_name,rank,position").fetchall(), before_effects)
            self.assertEqual(connection.execute("SELECT note FROM personal_notes").fetchone()[0], "keep me")

    def test_revision_zero_doppelganger_is_covered_and_reimported(self):
        self.set_legacy_grimoire(revision=0)
        old = self.grimoire_row(self.db)
        result = self.migrate()
        self.assertEqual(result.from_revision, 0)
        self.assertEqual(self.grimoire_row(result.backup_path), old)
        self.assertEqual(self.grimoire_row(self.db)[1], GRIMOIRE_PLAYER_ID)

    def test_revision_one_also_repairs_legacy_grimoire_during_mod_migration(self):
        self.set_legacy_grimoire(revision=1)
        old = self.grimoire_row(self.db)
        result = self.migrate()
        self.assertEqual(result.from_revision, 1)
        self.assertEqual(self.grimoire_row(result.backup_path), old)
        self.assertEqual(self.grimoire_row(self.db)[1], GRIMOIRE_PLAYER_ID)

    def test_revision_two_preserves_custom_grimoire(self):
        self.set_legacy_grimoire()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE weapons SET unique_name='custom/grimoire', dmg=42 "
                               "WHERE weapon='Grimoire'")
        custom = self.grimoire_row(self.db)
        result = self.migrate()
        self.assertEqual(result.from_revision, 2)
        self.assertEqual(self.grimoire_row(self.db), custom)
        self.assertEqual(self.grimoire_row(result.backup_path), custom)

    def test_revision_two_does_not_overwrite_edited_legacy_grimoire(self):
        self.set_legacy_grimoire()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE weapons SET dmg=26 WHERE weapon='Grimoire'")
        old = self.grimoire_row(self.db)
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "Grimoire.*modified"):
            self.migrate()
        self.assertEqual(self.grimoire_row(self.db), old)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertFalse((self.db.parent / "backups").exists())

    def test_revision_two_needs_matching_legacy_export_for_grimoire_repair(self):
        self.set_legacy_grimoire()
        old = self.grimoire_row(self.db)
        partial = self.root / "missing-doppelganger.zip"
        with zipfile.ZipFile(WEAPONS) as archive:
            name = next(n for n in archive.namelist() if n.endswith(".json"))
            payload = json.loads(archive.read(name))
        payload["ExportWeapons"] = [row for row in payload["ExportWeapons"]
                                    if row.get("uniqueName") != GRIMOIRE_DOPPELGANGER_ID]
        with zipfile.ZipFile(partial, "w") as archive:
            archive.writestr(name, json.dumps(payload))
        with self.assertRaisesRegex(migration.DatabaseMigrationError, "Grimoire.*saved export"):
            migration.migrate_database(self.db, partial, UPGRADES, SPREADSHEET)
        self.assertEqual(self.grimoire_row(self.db), old)
        self.assertFalse((self.db.parent / "backups").exists())

    def test_revision_two_grimoire_repair_failure_rolls_back_with_backup(self):
        self.set_legacy_grimoire()
        old = self.grimoire_row(self.db)
        original = migration.upsert_weapon_rows
        def fail_after_write(connection, rows):
            original(connection, rows)
            raise RuntimeError("simulated Grimoire repair failure")
        with patch.object(migration, "upsert_weapon_rows", side_effect=fail_after_write):
            with self.assertRaises(migration.DatabaseMigrationError) as caught:
                self.migrate()
        self.assertEqual(self.grimoire_row(self.db), old)
        self.assertEqual(self.grimoire_row(caught.exception.backup_path), old)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_process_exit_during_revision_two_repair_rolls_back(self):
        self.set_legacy_grimoire()
        old = self.grimoire_row(self.db)
        program = '''
import os, sys
from modules import database_migration as migration

original = migration.upsert_weapon_rows

def interrupted(connection, rows):
    original(connection, rows)
    os._exit(94)

migration.upsert_weapon_rows = interrupted
migration.migrate_database(*sys.argv[1:])
'''
        result = subprocess.run([sys.executable, "-c", program, str(self.db), str(WEAPONS),
                                 str(UPGRADES), str(SPREADSHEET)], cwd=ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 94, result.stderr)
        self.assertEqual(self.grimoire_row(self.db), old)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
        backups = list((self.db.parent / "backups").glob("*-pre-v2-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.grimoire_row(backups[0]), old)

    def test_new_import_and_bundled_database_are_versioned(self):
        fresh = self.root / "fresh.db"
        build_database(fresh, WEAPONS, UPGRADES, SPREADSHEET)
        for path in (fresh, ROOT / "data" / "weapons.db"):
            with self.subTest(path=path), closing(sqlite3.connect(path)) as connection, connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],
                                 CURRENT_DATABASE_REVISION)
                self.assertEqual(connection.execute("SELECT heat,cold,elec FROM weapons "
                                                    "WHERE weapon='Alternox Prime'").fetchone(),
                                 (0, 0, 75))


if __name__ == "__main__":
    unittest.main()
