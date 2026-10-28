"""Guard rails for the model benchmark / equivalence tool."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.bench_models import main, snapshot


class SnapshotTests(unittest.TestCase):
    def test_snapshot_is_deterministic_for_fixed_seeds(self):
        first, payload = snapshot(2)
        second, _ = snapshot(2)
        self.assertEqual(first, second)
        self.assertEqual(sorted(payload), ["jat_kittag_sim", "kuva_nukor_sim",
                                           "ocucor_sim"])
        # The trace is free text and is deliberately not part of the digest.
        for trials in payload.values():
            for trial in trials:
                self.assertNotIn("trace", trial)

    def test_snapshot_records_actual_trial_values(self):
        _, payload = snapshot(1)
        jat = payload["jat_kittag_sim"][0]
        self.assertGreater(jat["slams"], 0)
        self.assertGreater(jat["ttk"], 0)


class CheckModeTests(unittest.TestCase):
    def _write(self, directory: Path, payload: dict) -> Path:
        path = directory / "reference.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_matching_reference_exits_zero(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            reference = self._write(directory, {"sha256": snapshot(1)[0],
                                                "trials": 1})
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["--check", str(reference), "--no-timing"]), 0)

    def test_changed_results_exit_one(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            reference = self._write(directory, {"sha256": "0" * 64, "trials": 1})
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(["--check", str(reference), "--no-timing"]), 1)

    def test_trial_count_mismatch_is_not_a_result_change(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            reference = self._write(directory, {"sha256": snapshot(1)[0],
                                                "trials": 1})
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(["--check", str(reference), "--trials", "2",
                          "--no-timing"]), 2)

    def test_incomplete_reference_exits_two(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            reference = self._write(directory, {"trials": 1})
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(["--check", str(reference), "--no-timing"]), 2)

    def test_missing_reference_exits_two(self):
        with tempfile.TemporaryDirectory() as raw, \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                main(["--check", str(Path(raw) / "absent.json"),
                      "--no-timing"]), 2)


if __name__ == "__main__":
    unittest.main()
