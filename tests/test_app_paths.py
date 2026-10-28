"""Seeding local sources must not silently combine different export snapshots."""
from __future__ import annotations

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
        real_copy = shutil.copy2
        def interrupted(src, dest, *args, **kwargs):
            if Path(src).name == UPGRADES:
                raise OSError("simulated interruption")
            return real_copy(src, dest, *args, **kwargs)
        with patch("modules.app_paths.shutil.copy2", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                seed_source_files(self.project)
        self.assertFalse((self.source / WEAPONS).exists())
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertFalse(list(self.source.glob(".wdc-refresh-*")))
        seed_source_files(self.project)
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"bundled weapons")
        self.assertEqual((self.source / UPGRADES).read_bytes(), b"bundled upgrades")

    def test_failed_second_publication_rolls_back_the_first_seeded_file(self):
        real_replace = os.replace
        def fail_second(src, dest):
            if Path(dest) == self.source / UPGRADES:
                raise OSError("second replacement failed")
            return real_replace(src, dest)
        with patch("modules.updater.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second replacement failed"):
                seed_source_files(self.project)
        self.assertFalse((self.source / WEAPONS).exists())
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertFalse(list(self.source.glob(".wdc-refresh-*")))

    def test_process_exit_mid_seed_leaves_a_marker_and_later_seeding_is_blocked(self):
        program = """
import os
from pathlib import Path
from modules.app_paths import seed_source_files
real_replace = os.replace
def exit_after_first(src, dest):
    real_replace(src, dest)
    if Path(dest).name == 'ExportWeapons_en_Cleaned.zip':
        os._exit(91)
os.replace = exit_after_first
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
        with self.assertRaises(UnfinishedExportPublication):
            require_complete_exports(self.source / WEAPONS, self.source / UPGRADES)
        seed_source_files(self.project)
        self.assertFalse((self.source / UPGRADES).exists())
        self.assertTrue(stages[0].exists())


if __name__ == "__main__":
    unittest.main()
