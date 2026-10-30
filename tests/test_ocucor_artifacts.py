"""Guard the committed Ocucor comparison artifacts against silent staleness.

``docs/ocucor_enervate_flare_results.jsonl`` and
``docs/ocucor_viral_dilution_results.jsonl`` are model output with pinned
seeds, and both had already drifted from the tree: the copies committed before
the Cold-aware critical-damage work no longer reproduced from current code, yet
nothing failed, because nothing compared them with the model that writes them.

These tests compare them. Structural checks cover every record -- scenario
name, order, settings echo and trial counts, so a changed scenario list or
command line is caught for free. One scenario per artifact is then re-run at
its recorded trial count and must reproduce its record exactly, which is what
catches a formula change that was not mirrored into the artifact.

Only the cheapest scenario of each artifact is re-run (about 7 s for the
Enervate artifact's 4,500 trials and 2.5 s for the Viral artifact's 800
simulations); the expensive room scenarios cost minutes. That is a deliberate
sampling tradeoff, not a proof that the remaining records are current: a
change that alters only the room model still needs the artifacts regenerated
by hand, as the reports instruct.
"""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from modules import ocucor_comparison, ocucor_viral_comparison
from modules.ocucor_viral_comparison import RIVEN_NO_RELOAD, RIVEN_THREE_POS, RIVEN_TWO_POS

DOCS = Path(__file__).resolve().parents[1] / "docs"

# The commands printed in the two reports, which is what produced the
# committed artifacts. Keep in step with the docs, not with the module
# defaults: the artifacts were recorded at these counts.
ENERVATE_ARTIFACT = DOCS / "ocucor_enervate_flare_results.jsonl"
ENERVATE_COUNTS = {"seed": 20261028, "single_trials": 1500,
                   "room_trials": 250, "sensitivity_trials": 600}
ENERVATE_CHEAP = "single_ordinary_0_tendrils"

VIRAL_ARTIFACT = DOCS / "ocucor_viral_dilution_results.jsonl"
VIRAL_COUNTS = {"seed": 20261028, "single_trials": 800,
                "room_trials": 120, "sensitivity_trials": 400}
VIRAL_CHEAP = "shared_heat_eximus_4_enervate"

SETUPS = ("enervate", "flare_cold", "flare_full")


def load_records(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def capture_compare(func, name, kwargs) -> dict:
    """Run one scenario and return its record, swallowing the report line."""
    with contextlib.redirect_stdout(io.StringIO()):
        return json.loads(json.dumps(func(name, **kwargs)))


class ScenarioShapeMixin:
    """Checks shared by both artifacts; subclasses supply the mapping."""

    def scenario_map(self) -> dict[str, dict]:
        raise NotImplementedError

    def records(self) -> list[dict]:
        raise NotImplementedError

    #: Summary fields holding a percentage, checked to lie in [0, 100].
    PERCENT_FIELDS: tuple[str, ...] = ("reload_pct",)

    def percent_fields(self, summary: dict) -> tuple[str, ...]:
        """Percentage fields this summary must carry; room runs drop some."""
        return self.PERCENT_FIELDS

    def test_artifact_matches_the_scenarios_that_write_it(self):
        expected = list(self.scenario_map())
        self.assertEqual([r["scenario"] for r in self.records()], expected)

    def test_every_record_echoes_its_requested_settings(self):
        mapping = self.scenario_map()
        for record in self.records():
            kwargs = mapping[record["scenario"]]
            with self.subTest(scenario=record["scenario"]):
                self.assertEqual(record["seed_start"], kwargs["seed"])
                self.assertEqual(record["settings"]["starting_tendrils"],
                                 kwargs["tendrils"])

    def test_every_summary_is_internally_consistent(self):
        for record in self.records():
            for label, summary in self.summaries(record).items():
                with self.subTest(scenario=record["scenario"], setup=label):
                    self.assertEqual(summary["timed_out"], 0)
                    self.assertGreater(summary["attempted"], 0)
                    self.assertGreater(summary["mean_s"], 0.0)
                    self.assertGreaterEqual(summary["p90_s"], summary["median_s"])
                    for field in self.percent_fields(summary):
                        self.assertGreaterEqual(summary[field], 0.0)
                        self.assertLessEqual(summary[field], 100.0)


class EnervateArtifactTests(ScenarioShapeMixin, unittest.TestCase):
    PERCENT_FIELDS = ("reload_pct", "flare_cap_pct")

    def scenario_map(self) -> dict[str, dict]:
        return dict(ocucor_comparison.scenarios(**ENERVATE_COUNTS))

    def records(self) -> list[dict]:
        return load_records(ENERVATE_ARTIFACT)

    def summaries(self, record: dict) -> dict[str, dict]:
        return {label: record[label] for label in SETUPS}

    def test_every_setup_ran_the_documented_trial_count(self):
        mapping = self.scenario_map()
        for record in self.records():
            trials = mapping[record["scenario"]]["trials"]
            with self.subTest(scenario=record["scenario"]):
                for label in SETUPS:
                    self.assertEqual(record[label]["attempted"], trials)

    def test_room_scenarios_are_the_only_ten_target_runs(self):
        mapping = self.scenario_map()
        for record in self.records():
            kwargs = mapping[record["scenario"]]
            with self.subTest(scenario=record["scenario"]):
                self.assertEqual(record["settings"]["room_targets"],
                                 10 if kwargs.get("room") else None)

    def test_cheap_scenario_reproduces_its_record_exactly(self):
        kwargs = self.scenario_map()[ENERVATE_CHEAP]
        recorded = next(record for record in self.records()
                        if record["scenario"] == ENERVATE_CHEAP)
        # Exact equality: the model is deterministic and the artifact is
        # supposed to be this model's output. A mismatch means the artifact is
        # stale -- regenerate it with the command in the report.
        self.assertEqual(capture_compare(ocucor_comparison.compare,
                                         ENERVATE_CHEAP, kwargs),
                         recorded)


class ViralArtifactTests(ScenarioShapeMixin, unittest.TestCase):
    PERCENT_FIELDS = ("reload_pct", "viral_cap_pct")

    def percent_fields(self, summary: dict) -> tuple[str, ...]:
        # Room summaries report tendril occupancy instead of Viral capping.
        return self.PERCENT_FIELDS if "viral_cap_pct" in summary else ("reload_pct",)

    def scenario_map(self) -> dict[str, dict]:
        return dict(ocucor_viral_comparison.scenarios(**VIRAL_COUNTS))

    def records(self) -> list[dict]:
        return load_records(VIRAL_ARTIFACT)

    def summaries(self, record: dict) -> dict[str, dict]:
        return record["variants"]

    def test_every_variant_ran_the_documented_trial_count(self):
        mapping = self.scenario_map()
        for record in self.records():
            trials = mapping[record["scenario"]]["trials"]
            with self.subTest(scenario=record["scenario"]):
                for summary in record["variants"].values():
                    self.assertEqual(summary["attempted"], trials)

    def test_riven_variants_match_the_requested_layouts(self):
        mapping = self.scenario_map()
        for record in self.records():
            specs = mapping[record["scenario"]].get(
                "specs", ocucor_viral_comparison.ALL_SPECS)
            with self.subTest(scenario=record["scenario"]):
                self.assertEqual(list(record["variants"]),
                                 [spec.label for spec in specs])

    def test_paired_differences_only_join_recorded_variants(self):
        for record in self.records():
            for label in record["paired"]:
                with self.subTest(scenario=record["scenario"], pair=label):
                    old, new = label.split("_minus_")
                    self.assertIn(old, record["variants"])
                    self.assertIn(new, record["variants"])

    def test_reload_controls_keep_the_full_and_no_reload_layouts(self):
        controls = [record for record in self.records()
                    if record["scenario"].endswith("_reload_control")]
        self.assertEqual(len(controls), 2)
        for record in controls:
            with self.subTest(scenario=record["scenario"]):
                self.assertEqual(
                    list(record["variants"]),
                    [RIVEN_TWO_POS.label, RIVEN_THREE_POS.label,
                     RIVEN_NO_RELOAD.label])
                self.assertEqual(record["settings"]["starting_tendrils"], 0)

    def test_cheap_scenario_reproduces_its_record_exactly(self):
        kwargs = self.scenario_map()[VIRAL_CHEAP]
        recorded = next(record for record in self.records()
                        if record["scenario"] == VIRAL_CHEAP)
        self.assertEqual(capture_compare(ocucor_viral_comparison.compare,
                                         VIRAL_CHEAP, kwargs),
                         recorded)


if __name__ == "__main__":
    unittest.main()
