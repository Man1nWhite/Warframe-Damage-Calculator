"""Guard the committed Jat slam-count artifact against silent staleness.

``docs/jat_kittag_expected_slams_results.jsonl`` is model output with a pinned
seed, and it has already gone stale once: the copy regenerated on 2026-10-28
predated the critical-damage quantization, so 34 of its 44 records no longer
reproduced from the tree (see the regeneration record in
``docs/jat_kittag_expected_slams.md``). Nothing caught it, because nothing
compared the artifact with the model that produces it.

These tests do that. Structural checks cover every record; one scenario is
re-simulated and must reproduce its record exactly, which is what catches a
formula change that was not mirrored into the artifact. The re-simulated
scenario is the 1,000-trial ``normal_status_no_afflictions`` row (~0.3 s for
both builds); any 10,000-trial row costs ~2.5 s, which is too much for a suite
this size.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from modules.jat_kittag_slam_analysis import BUILD_BY_KEY
from modules.jat_kittag_slam_count_sweep import SCENARIOS
from modules.jat_kittag_slam_counts import BUILDS, TARGETS, Target, summarize

ARTIFACT = (Path(__file__).resolve().parents[1] / "docs"
            / "jat_kittag_expected_slams_results.jsonl")
CHEAP_SCENARIO = "normal_status_no_afflictions"


def load_records() -> list[dict]:
    with ARTIFACT.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class ArtifactTests(unittest.TestCase):
    def test_artifact_holds_one_record_per_scenario_target_and_build(self):
        records = load_records()
        expected = sum(len(targets) for _, _, targets, _ in SCENARIOS) * len(BUILDS)
        self.assertEqual(len(records), expected)
        keys = {(record["scenario"], record["target_key"], record["build"])
                for record in records}
        self.assertEqual(len(keys), len(records))

    def test_every_record_is_internally_consistent(self):
        for record in load_records():
            label = (record["scenario"], record["target_key"], record["build"])
            with self.subTest(record=label):
                self.assertEqual(record["timeouts"], 0)
                self.assertEqual(record["attempted"], record["kills"])
                histogram = record["slam_count_histogram"]
                self.assertEqual(sum(histogram.values()), record["kills"])
                for slam_count in histogram:
                    self.assertGreaterEqual(int(slam_count), 1)
                self.assertGreaterEqual(record["mean_slams"],
                                        record["p10_slams"])
                self.assertLessEqual(record["mean_slams"], record["p90_slams"])
                self.assertGreaterEqual(record["p90_slams"],
                                        record["median_slams"])
                self.assertGreaterEqual(record["median_slams"],
                                        record["p10_slams"])
                self.assertGreater(record["mean_slams_se"], 0.0)

    def test_cheap_scenario_reproduces_its_record_exactly(self):
        name, assumptions, target_keys, trials = next(
            scenario for scenario in SCENARIOS if scenario[0] == CHEAP_SCENARIO)
        target = Target.from_scaled(TARGETS[target_keys[0]]())
        recorded = {record["build"]: record for record in load_records()
                    if record["scenario"] == name}
        self.assertEqual(set(recorded), set(BUILDS))
        for build_key in BUILDS:
            record = recorded[build_key]
            with self.subTest(build=build_key):
                computed = summarize(BUILD_BY_KEY[build_key], target, assumptions,
                                     trials=trials, base_seed=record["seed"])
                computed["scenario"] = name
                computed["target_key"] = target_keys[0]
                # Round-trip through JSON so the histogram's integer keys are
                # compared as the strings the artifact stores.
                computed = json.loads(json.dumps(computed))
                # Exact equality: the model is deterministic and the artifact
                # is supposed to be this model's output. A mismatch means the
                # artifact is stale, not that the comparison is too strict.
                self.assertEqual(computed, record)


if __name__ == "__main__":
    unittest.main()
