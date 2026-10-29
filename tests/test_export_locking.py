"""Export reads and pair publication must serialize across processes."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from modules.export_safety import export_lock

ROOT = Path(__file__).resolve().parents[1]
WEAPONS = "ExportWeapons_en_Cleaned.zip"
UPGRADES = "ExportKeys_en_Cleaned.zip"


class ExportLockingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        shutil.copy2(ROOT / "source" / WEAPONS, self.source / WEAPONS)
        shutil.copy2(ROOT / "source" / UPGRADES, self.source / UPGRADES)

    @staticmethod
    def wait_for_file(path: Path, process: subprocess.Popen[bytes], timeout: float = 10) -> None:
        deadline = time.monotonic() + timeout
        while not path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        if not path.exists():
            output, _ = process.communicate(timeout=1)
            raise AssertionError(f"{path.name} was not created; child output: {output!r}")

    def test_importer_holds_the_pair_lock_while_another_process_owns_it(self) -> None:
        ready = self.root / "lock-held"
        release = self.root / "release-lock"
        completed = self.root / "reader-completed"
        lock_owner = r"""
import sys, time
from pathlib import Path
from modules.export_safety import export_lock
source, ready, release = map(Path, sys.argv[1:4])
with export_lock(source / 'ExportWeapons_en_Cleaned.zip', source / 'ExportKeys_en_Cleaned.zip'):
    ready.write_text('locked')
    deadline = time.monotonic() + 15
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
"""
        importer = r"""
import sys
from pathlib import Path
from modules.importer import load_import_payload
source, completed = map(Path, sys.argv[1:3])
load_import_payload(source / 'ExportWeapons_en_Cleaned.zip', source / 'ExportKeys_en_Cleaned.zip')
completed.write_text('read')
"""
        owner = subprocess.Popen(
            [sys.executable, "-c", lock_owner, str(self.source), str(ready), str(release)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        reader: subprocess.Popen[bytes] | None = None
        try:
            self.wait_for_file(ready, owner)
            reader = subprocess.Popen(
                [sys.executable, "-c", importer, str(self.source), str(completed)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            time.sleep(0.25)
            self.assertIsNone(reader.poll(), "the import should wait for the active publisher lock")
            self.assertFalse(completed.exists(), "the two ZIPs must not be read before the lock is released")
        finally:
            release.touch()
            owner.communicate(timeout=10)
            if reader is not None:
                output, _ = reader.communicate(timeout=20)
                self.assertEqual(reader.returncode, 0, output.decode(errors="replace"))
        self.assertTrue(completed.exists())

    def test_concurrent_publishers_cannot_leave_a_mixed_pair(self) -> None:
        stage_a = self.source / ".wdc-refresh-a"
        stage_b = self.source / ".wdc-refresh-b"
        stage_a.mkdir()
        stage_b.mkdir()
        (stage_a / WEAPONS).write_bytes(b"publisher-a-weapons")
        (stage_a / UPGRADES).write_bytes(b"publisher-a-upgrades")
        (stage_b / WEAPONS).write_bytes(b"publisher-b-weapons")
        (stage_b / UPGRADES).write_bytes(b"publisher-b-upgrades")
        first_replaced = self.root / "first-replaced"
        release_a = self.root / "release-publisher-a"
        second_started = self.root / "second-started"
        second_finished = self.root / "second-finished"
        publisher_a = r"""
import os, sys, time
from pathlib import Path
from unittest.mock import patch
from modules.updater import WarframeDataUpdater
source, stage, first, release = map(Path, sys.argv[1:5])
original_replace = os.replace
def pause_after_first(src, dest):
    original_replace(src, dest)
    if Path(dest).name == 'ExportWeapons_en_Cleaned.zip':
        first.write_text('replaced')
        deadline = time.monotonic() + 15
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
archives = ((stage / 'ExportWeapons_en_Cleaned.zip', source / 'ExportWeapons_en_Cleaned.zip'),
            (stage / 'ExportKeys_en_Cleaned.zip', source / 'ExportKeys_en_Cleaned.zip'))
with patch('modules.updater.os.replace', side_effect=pause_after_first):
    WarframeDataUpdater._publish_exports(archives, stage)
"""
        publisher_b = r"""
import sys
from pathlib import Path
from modules.updater import WarframeDataUpdater
source, stage, started, finished = map(Path, sys.argv[1:5])
started.write_text('started')
archives = ((stage / 'ExportWeapons_en_Cleaned.zip', source / 'ExportWeapons_en_Cleaned.zip'),
            (stage / 'ExportKeys_en_Cleaned.zip', source / 'ExportKeys_en_Cleaned.zip'))
WarframeDataUpdater._publish_exports(archives, stage)
finished.write_text('finished')
"""
        first = subprocess.Popen(
            [sys.executable, "-c", publisher_a, str(self.source), str(stage_a),
             str(first_replaced), str(release_a)],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        second: subprocess.Popen[bytes] | None = None
        try:
            self.wait_for_file(first_replaced, first)
            second = subprocess.Popen(
                [sys.executable, "-c", publisher_b, str(self.source), str(stage_b),
                 str(second_started), str(second_finished)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.wait_for_file(second_started, second)
            time.sleep(0.25)
            self.assertIsNone(second.poll(), "the second publisher must wait for the pair lock")
            self.assertFalse(second_finished.exists())
        finally:
            release_a.touch()
            first.communicate(timeout=15)
            if second is not None:
                output, _ = second.communicate(timeout=15)
                self.assertEqual(second.returncode, 0, output.decode(errors="replace"))
        self.assertEqual(first.returncode, 0)
        self.assertEqual((self.source / WEAPONS).read_bytes(), b"publisher-b-weapons")
        self.assertEqual((self.source / UPGRADES).read_bytes(), b"publisher-b-upgrades")

    def test_export_lock_uses_a_persistent_lock_file(self) -> None:
        # OS-level locks are released automatically, but keeping this inode
        # avoids lock-file replacement races between cooperating processes.
        with export_lock(self.source / WEAPONS, self.source / UPGRADES):
            self.assertTrue((self.source / ".wdc-exports.lock").exists())


if __name__ == "__main__":
    unittest.main()
