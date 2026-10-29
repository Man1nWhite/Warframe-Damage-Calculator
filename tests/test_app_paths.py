"""Seeding local sources must not silently combine different export snapshots."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.app_paths import ensure_app_dirs, seed_source_files
from modules.export_safety import UnfinishedExportPublication, require_complete_exports

WEAPONS = "ExportWeapons_en_Cleaned.zip"
UPGRADES = "ExportKeys_en_Cleaned.zip"


class SourceSeedingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        environment.start()
        self.addCleanup(environment.stop)
        self.source = ensure_app_dirs()["source"]
        self.project = self.root / "project"
        bundled = self.project / "source"
        bundled.mkdir(parents=True)
        (bundled / WEAPONS).write_bytes(b"bundled weapons")
        (bundled / UPGRADES).write_bytes(b"bundled upgrades")
        (bundled / "riven_tags.json").write_bytes(b"other reference")

    def test_absent_pair_is_seeded_together_but_existing_pair_is_preserved(self):
        seed_source_files(self.project)
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"bundled weapons")
        self.assertEqual((self.source / UPGRADES).read_bytes(), b"bundled upgrades")
        (self.source / WEAPONS).write_bytes(b"newer weapons")
        (self.source / UPGRADES).write_bytes(b"newer upgrades")
        seed_source_files(self.project)
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"newer weapons")
        self.assertEqual((self.source / UPGRADES).read_bytes(), b"newer upgrades")

    def test_export_created_during_first_seed_is_not_overwritten(self):
        target = self.source / WEAPONS
        real_copy = shutil.copyfile

        def create_user_export(src, dest, *args, **kwargs):
            if Path(src).name == WEAPONS:
                target.write_bytes(b"user export created during seeding")
            return real_copy(src, dest, *args, **kwargs)

        with patch("modules.app_paths.shutil.copyfile", side_effect=create_user_export):
            seed_source_files(self.project)
        self.assertEqual(target.read_bytes(), b"user export created during seeding")
        self.assertFalse((self.source / UPGRADES).exists())

    def test_export_created_between_existence_check_and_first_publication_is_preserved(self):
        target = self.source / WEAPONS
        real_link = os.link

        def create_user_export(src, dest, *args, **kwargs):
            if Path(dest) == target:
                target.write_bytes(b"racing user export")
            return real_link(src, dest, *args, **kwargs)

        with patch("modules.updater.os.link", side_effect=create_user_export):
            seed_source_files(self.project)
        self.assertEqual(target.read_bytes(), b"racing user export")
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertEqual(list(self.source.glob(".wdc-refresh-*")), [])

    def test_export_created_between_pair_publications_is_preserved_and_guarded(self):
        target = self.source / UPGRADES
        real_link = os.link

        def create_user_export(src, dest, *args, **kwargs):
            if Path(dest) == target:
                target.write_bytes(b"racing user export")
            return real_link(src, dest, *args, **kwargs)

        with patch("modules.updater.os.link", side_effect=create_user_export):
            with self.assertRaisesRegex(RuntimeError, "inspect|recover"):
                seed_source_files(self.project)
        self.assertEqual(target.read_bytes(), b"racing user export")
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"bundled weapons")
        markers = list(self.source.glob(".wdc-refresh-*/PUBLISHING.json"))
        self.assertEqual(len(markers), 1)
        with self.assertRaises(UnfinishedExportPublication):
            require_complete_exports(self.source / WEAPONS, self.source / UPGRADES)

    def test_only_one_existing_export_is_not_supplemented_from_another_snapshot(self):
        for existing, missing in ((WEAPONS, UPGRADES), (UPGRADES, WEAPONS)):
            with self.subTest(existing=existing):
                (self.source / existing).write_bytes(b"custom existing export")
                (self.source / missing).unlink(missing_ok=True)
                seed_source_files(self.project)
                self.assertEqual((self.source / existing).read_bytes(), b"custom existing export")
                self.assertFalse((self.source / missing).exists())
                self.assertEqual((self.source / "riven_tags.json").read_bytes(), b"other reference")
                (self.source / existing).unlink()

    def test_incomplete_bundled_pair_does_not_seed_just_one_export(self):
        (self.project / "source" / UPGRADES).unlink()
        seed_source_files(self.project)
        self.assertFalse((self.source / WEAPONS).exists())
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertTrue((self.source / "riven_tags.json").exists())

    def test_recovery_marker_prevents_seeding_even_when_both_exports_are_absent(self):
        stage = self.source / ".wdc-refresh-unfinished"
        stage.mkdir()
        (stage / "PUBLISHING.json").write_text("{}", encoding="utf-8")
        seed_source_files(self.project)
        self.assertFalse((self.source / WEAPONS).exists())
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertTrue((stage / "PUBLISHING.json").exists())

    def test_failed_staging_keeps_both_targets_absent_and_allows_a_safe_retry(self):
        real_copy = shutil.copyfile
        def interrupted(src, dest, *args, **kwargs):
            if Path(src).name == UPGRADES:
                raise OSError("simulated interruption")
            return real_copy(src, dest, *args, **kwargs)
        with patch("modules.app_paths.shutil.copyfile", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                seed_source_files(self.project)
        self.assertFalse((self.source / WEAPONS).exists())
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertFalse(list(self.source.glob(".wdc-refresh-*")))
        seed_source_files(self.project)
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"bundled weapons")
        self.assertEqual((self.source / UPGRADES).read_bytes(), b"bundled upgrades")

    def test_failed_second_seed_publication_retains_a_guarded_recovery_copy(self):
        real_link = os.link
        def fail_second(src, dest):
            if Path(dest) == self.source / UPGRADES:
                raise OSError("second publication failed")
            return real_link(src, dest)
        with patch("modules.updater.os.link", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second publication failed"):
                seed_source_files(self.project)
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"bundled weapons")
        self.assertFalse((self.source / UPGRADES).exists())
        stages = list(self.source.glob(".wdc-refresh-*"))
        self.assertEqual(len(stages), 1)
        self.assertTrue((stages[0] / "PUBLISHING.json").is_file())
        self.assertEqual((stages[0] / WEAPONS).read_bytes(), b"bundled weapons")
        self.assertEqual((stages[0] / UPGRADES).read_bytes(), b"bundled upgrades")
        with self.assertRaises(UnfinishedExportPublication):
            require_complete_exports(self.source / WEAPONS, self.source / UPGRADES)

    def test_interrupted_reference_copy_never_leaves_a_partial_target(self):
        target = self.source / "riven_tags.json"
        real_copy = shutil.copyfile

        def interrupt(src, dest, *args, **kwargs):
            if Path(src).name == "riven_tags.json":
                Path(dest).write_bytes(b"partial")
                raise OSError("interrupted reference copy")
            return real_copy(src, dest, *args, **kwargs)

        with patch("modules.app_paths.shutil.copyfile", side_effect=interrupt):
            with self.assertRaisesRegex(OSError, "interrupted reference copy"):
                seed_source_files(self.project)
        self.assertFalse(target.exists())
        seed_source_files(self.project)
        self.assertEqual(target.read_bytes(), b"other reference")

    def test_reference_created_during_seeding_is_not_overwritten(self):
        target = self.source / "riven_tags.json"
        real_copy = shutil.copyfile

        def create_custom(src, dest, *args, **kwargs):
            if Path(src).name == "riven_tags.json":
                target.write_bytes(b"user data created during seeding")
            return real_copy(src, dest, *args, **kwargs)

        with patch("modules.app_paths.shutil.copyfile", side_effect=create_custom):
            seed_source_files(self.project)
        self.assertEqual(target.read_bytes(), b"user data created during seeding")

    def test_unavailable_atomic_export_publication_does_not_create_targets(self):
        with patch("modules.updater.os.link", side_effect=OSError("hard links unavailable")):
            with self.assertRaisesRegex(RuntimeError, "safely seed.*hard links unavailable"):
                seed_source_files(self.project)
        self.assertFalse((self.source / WEAPONS).exists())
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertEqual(list(self.source.glob(".wdc-refresh-*")), [])
        seed_source_files(self.project)
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"bundled weapons")
        self.assertEqual((self.source / UPGRADES).read_bytes(), b"bundled upgrades")

    def test_unavailable_atomic_publication_does_not_leave_a_partial_reference(self):
        target = self.source / "riven_tags.json"
        (self.source / WEAPONS).write_bytes(b"existing weapons")
        (self.source / UPGRADES).write_bytes(b"existing upgrades")
        with patch("modules.app_paths.os.link", side_effect=OSError("hard links unavailable")):
            with self.assertRaisesRegex(OSError, "safely seed.*hard links unavailable"):
                seed_source_files(self.project)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.source.glob(".wdc-reference-*")), [])
        seed_source_files(self.project)
        self.assertEqual(target.read_bytes(), b"other reference")

    def test_dangling_reference_symlink_is_never_overwritten(self):
        target = self.source / "riven_tags.json"
        try:
            target.symlink_to("missing-user-reference.json")
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this platform")
        seed_source_files(self.project)
        self.assertTrue(target.is_symlink())
        self.assertFalse((self.source / "missing-user-reference.json").exists())

    def test_process_exit_during_reference_copy_allows_clean_retry(self):
        program = """
import os, shutil
from pathlib import Path
from modules.app_paths import seed_source_files
real_copy = shutil.copyfile
def interrupted(src, dest, *args, **kwargs):
    if Path(src).name == 'riven_tags.json':
        Path(dest).write_bytes(b'partial')
        os._exit(93)
    return real_copy(src, dest, *args, **kwargs)
shutil.copyfile = interrupted
seed_source_files(Path(os.environ['TEST_PROJECT']))
"""
        env = os.environ.copy()
        env["TEST_PROJECT"] = str(self.project)
        run = subprocess.run([sys.executable, "-c", program], env=env, check=False,
                             cwd=Path(__file__).resolve().parents[1], timeout=20)
        self.assertEqual(run.returncode, 93)
        target = self.source / "riven_tags.json"
        self.assertFalse(target.exists())
        seed_source_files(self.project)
        self.assertEqual(target.read_bytes(), b"other reference")

    def test_process_exit_mid_seed_leaves_a_marker_and_later_seeding_is_blocked(self):
        program = """
import os
from pathlib import Path
from modules.app_paths import seed_source_files
real_link = os.link
def exit_after_first(src, dest):
    result = real_link(src, dest)
    if Path(dest).name == 'ExportWeapons_en_Cleaned.zip':
        os._exit(91)
    return result
os.link = exit_after_first
seed_source_files(Path(os.environ['TEST_PROJECT']))
"""
        env = os.environ.copy()
        env["TEST_PROJECT"] = str(self.project)
        run = subprocess.run([sys.executable, "-c", program], env=env, check=False,
                             cwd=Path(__file__).resolve().parents[1], timeout=20)
        self.assertEqual(run.returncode, 91)
        self.assertTrue((self.source / WEAPONS).exists())
        self.assertFalse((self.source / UPGRADES).exists())
        stages = list(self.source.glob(".wdc-refresh-*/PUBLISHING.json"))
        self.assertEqual(len(stages), 1)
        marker = json.loads(stages[0].read_text(encoding="utf-8"))
        self.assertEqual(marker["mode"], "seed-no-clobber")
        self.assertEqual([item["staged_copy"] for item in marker["archives"]], [WEAPONS, UPGRADES])
        with self.assertRaises(UnfinishedExportPublication):
            require_complete_exports(self.source / WEAPONS, self.source / UPGRADES)
        seed_source_files(self.project)
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertTrue(stages[0].exists())


if __name__ == "__main__":
    unittest.main()
