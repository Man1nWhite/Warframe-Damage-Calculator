"""Ocucor Riven-layout and reload sensitivities."""
from __future__ import annotations

import contextlib
import csv
import io
import math
import unittest
from pathlib import Path

from modules.ocucor_comparison import compare as arcane_compare
from modules.ocucor_comparison import make_target
from modules.ocucor_sim import (
    ARCANE_ENERVATE,
    ARCANE_FLARE,
    DummyTarget,
    build_ocucor,
    simulate,
    simulate_room,
)
from modules.ocucor_viral_comparison import (
    RIVEN_LOW_VIRAL_TWO_POS,
    RIVEN_LOWER_VIRAL,
    RIVEN_NO_RELOAD,
    RIVEN_THREE_POS,
    RIVEN_TWO_POS,
    compare,
    target_factory,
)


class RivenLayoutTests(unittest.TestCase):
    def test_three_positive_midpoints_match_pistol_table(self):
        path = Path(__file__).resolve().parents[1] / "source/riven_stats_average_1_2.csv"
        with path.open(newline="") as stream:
            rows = {r["stat_name"]: r for r in csv.DictReader(stream)
                    if r["riven_type"] == "LotusPistolRandomModRare"}
        self.assertAlmostEqual(float(rows["Multishot"]["buff_3_pos_1_neg"]), 134.7)
        self.assertAlmostEqual(float(rows["Reload Speed"]["buff_3_pos_1_neg"]), 56.2)
        self.assertAlmostEqual(float(rows["Zoom"]["curse_with_3_pos"]), -72.1)
        # Spliced Viral's Wiki base is 90%; three-positive layout weight is 0.9375.
        self.assertAlmostEqual(0.9 * 1.2 * 0.9375 * 100, 101.25)
        # A real two-positive roll may independently have the minimum grade
        # for Viral while Multishot is midpoint-grade.
        self.assertAlmostEqual(round(0.9 * 1.2 * 1.2375 * 0.9 * 100, 1),
                               RIVEN_LOW_VIRAL_TWO_POS.viral * 100)

    def test_custom_riven_updates_damage_status_and_reload(self):
        old = build_ocucor(ARCANE_ENERVATE, "Multishot")
        new = build_ocucor(ARCANE_ENERVATE, "Multishot",
                           riven_multishot_bonus=1.347,
                           riven_viral_bonus=1.013,
                           riven_reload_speed_bonus=0.562)
        self.assertAlmostEqual(old.multishot, 5.678)
        self.assertAlmostEqual(new.multishot, 5.247)
        self.assertAlmostEqual(old.reload_time, 1.0)
        self.assertAlmostEqual(new.reload_time, 1.6 / (1 + 0.6 + 0.562))
        self.assertAlmostEqual(new.type_damage["VIRAL"],
                               11 * new.base_damage_bracket * 1.013)
        self.assertAlmostEqual(new.proc_weights["HEAT"], 1.65 / (1 + 1.65 + 1.013))
        self.assertAlmostEqual(new.proc_weights["VIRAL"], 1.013 / (1 + 1.65 + 1.013))
        self.assertAlmostEqual(new.merged_status, 0.432 * 5.247)
        self.assertLess(new.modded_base_merged, old.modded_base_merged)
        for kwargs in ({"riven_multishot_bonus": -1}, {"riven_viral_bonus": math.inf},
                       {"riven_reload_speed_bonus": -0.01}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_ocucor(ARCANE_ENERVATE, "Multishot", **kwargs)
        with self.assertRaises(ValueError):
            build_ocucor(ARCANE_ENERVATE, "Critical Damage",
                         riven_multishot_bonus=1.347)

    def test_counterfactuals_isolate_the_intended_attributes(self):
        old = RIVEN_TWO_POS.build(ARCANE_ENERVATE)
        viral_only = RIVEN_LOWER_VIRAL.build(ARCANE_ENERVATE)
        no_reload = RIVEN_NO_RELOAD.build(ARCANE_ENERVATE)
        proposed = RIVEN_THREE_POS.build(ARCANE_ENERVATE)
        self.assertEqual(old.multishot, viral_only.multishot)
        self.assertEqual(old.reload_time, viral_only.reload_time)
        self.assertGreater(viral_only.proc_weights["HEAT"], old.proc_weights["HEAT"])
        self.assertEqual(no_reload.multishot, proposed.multishot)
        self.assertEqual(no_reload.proc_weights, proposed.proc_weights)
        self.assertGreater(no_reload.reload_time, proposed.reload_time)
        self.assertFalse(RIVEN_LOWER_VIRAL.attainable_midpoint)
        self.assertFalse(RIVEN_NO_RELOAD.attainable_midpoint)

    def test_preprimed_viral_counts_for_gunco_and_cap(self):
        target = target_factory(True, preprimed_viral_stacks=10)
        self.assertEqual(target.viral_stacks(0), 10)
        self.assertEqual(target.unique_status_count(0), 1)
        result = simulate(RIVEN_TWO_POS.build(ARCANE_ENERVATE), target,
                          seed=1, max_time=0.01)
        self.assertEqual(result.viral_cap_time, 0.0)
        self.assertEqual(target.viral_stacks(6), 0)
        with self.assertRaises(ValueError):
            target_factory(True, preprimed_viral_stacks=11)

    def test_same_seed_baseline_agrees_with_arcane_comparison(self):
        with contextlib.redirect_stdout(io.StringIO()):
            previous = arcane_compare("old", eximus=True, trials=3, seed=17,
                                      tendrils=4)
            current = compare("new", eximus=True, arcane=ARCANE_ENERVATE,
                              initial_flare=0, tendrils=4, trials=3, seed=17)
        self.assertEqual(previous["enervate"]["mean_s"],
                         current["variants"]["two_positive"]["mean_s"])
        self.assertEqual(current["variants"]["three_positive_reload"]["timed_out"], 0)
        self.assertEqual(current["paired"][
            "three_positive_reload_minus_two_positive"]["complete_pairs"], 3)

    def test_reload_bonus_reduces_pause_but_does_not_save_tendrils(self):
        old = build_ocucor(ARCANE_ENERVATE, "Multishot")
        quick = build_ocucor(ARCANE_ENERVATE, "Multishot",
                             riven_reload_speed_bonus=0.562)
        slow_result = simulate(old, DummyTarget(10**12, 2700, 0), seed=42,
                               starting_tendrils=4, max_time=7.1)
        fast_result = simulate(quick, DummyTarget(10**12, 2700, 0), seed=42,
                               starting_tendrils=4, max_time=7.1)
        self.assertEqual(slow_result.reloads, 1)
        self.assertEqual(fast_result.reloads, 1)
        self.assertEqual(slow_result.ticks, 120)
        self.assertGreater(fast_result.ticks, slow_result.ticks)
        self.assertEqual(slow_result.final_tendrils, 0)
        self.assertEqual(fast_result.final_tendrils, 0)

    def test_single_room_parity_for_custom_riven(self):
        for arcane, flare in ((ARCANE_ENERVATE, 0), (ARCANE_FLARE, 40)):
            build = build_ocucor(arcane, "Multishot", riven_multishot_bonus=1.347,
                                 riven_viral_bonus=1.013,
                                 riven_reload_speed_bonus=0.562)
            for seed in (0, 1, 2):
                single = simulate(build, make_target(True), seed=seed,
                                  starting_tendrils=4, starting_flare_stacks=flare)
                room = simulate_room(arcane, "Multishot", 1,
                                     factory=lambda: make_target(True), seed=seed,
                                     starting_tendrils=4, starting_flare_stacks=flare,
                                     build_override=build)
                self.assertEqual(single.ttk, room.clear_time)
                self.assertEqual(single.flare_stacks_peak, room.flare_peak)
        with self.assertRaises(ValueError):
            simulate_room(ARCANE_FLARE, "Damage", 1, build_override=build)


if __name__ == "__main__":
    unittest.main()
