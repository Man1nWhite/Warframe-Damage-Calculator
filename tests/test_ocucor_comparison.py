"""Regression tests for the experimental Ocucor arcane comparison."""
from __future__ import annotations

import contextlib
import csv
import io
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import modules.ocucor_sim as ocucor
from modules.damage_routing import route_enemy_hit
from modules.kuva_nukor_sim import DummyTarget, enervate_afcc
from modules.crit import quantize_crit_multiplier
from modules.ocucor_comparison import compare, discard_overguard_overflow, make_target
from modules.ocucor_sim import (
    ARCANE_ENERVATE,
    ARCANE_FLARE,
    FLARE_MAX_STACKS,
    RIVEN_STATS,
    _add_heat,
    build_ocucor,
    effective_crit_chance_pct,
    effective_status_per_beam,
    simulate,
    simulate_room,
)


class RivenAndStatTests(unittest.TestCase):
    def test_two_positive_one_negative_values_match_pistol_csv(self):
        path = Path(__file__).resolve().parents[1] / "source/riven_stats_average_1_2.csv"
        with path.open(newline="") as stream:
            rows = {row["stat_name"]: row for row in csv.DictReader(stream)
                    if row["riven_type"] == "LotusPistolRandomModRare"}
        for stat, csv_stat in (("Critical Damage", "Critical Damage"),
                               ("Critical Chance", "Critical Chance"),
                               ("Damage", "Damage"),
                               ("Fire Rate", "Fire Rate / Attack Speed"),
                               ("Status Chance", "Status Chance"),
                               ("Multishot", "Multishot")):
            with self.subTest(stat=stat):
                self.assertAlmostEqual(RIVEN_STATS[stat] * 100,
                                       float(rows[csv_stat]["buff_2_pos_1_neg"]))
        self.assertAlmostEqual(float(rows["Zoom"]["curse_with_2_pos"]), -47.6)

    def test_requested_roll_and_surge_stats(self):
        en = build_ocucor(ARCANE_ENERVATE, "Multishot")
        fl = build_ocucor(ARCANE_FLARE, "Multishot")
        self.assertAlmostEqual(en.multishot, 5.678)
        self.assertAlmostEqual(en.fire_rate, 19.2)
        self.assertAlmostEqual(en.crit_multiplier, quantize_crit_multiplier(1.8) * 2.1)
        self.assertAlmostEqual(en.merged_status, 2.452896)
        self.assertAlmostEqual(effective_status_per_beam(en, 4), 1.008)
        self.assertAlmostEqual(effective_status_per_beam(en, 4) * en.multishot,
                               5.723424)
        self.assertAlmostEqual(effective_crit_chance_pct(fl, 4, 0), 54.4)
        self.assertAlmostEqual(effective_crit_chance_pct(fl, 4, 5), 79.4)
        self.assertAlmostEqual(effective_crit_chance_pct(en, 0, 0), 110.45)
        self.assertAlmostEqual(effective_crit_chance_pct(en, 4, 0), 129.65)
        self.assertAlmostEqual(effective_crit_chance_pct(en, 4, 5), 142.15)
        self.assertAlmostEqual(effective_crit_chance_pct(
            en, 4, 5, enervate_extra_pct=50.0), enervate_afcc(79.4) + 50.0)

    def test_puncture_stacks_expire_and_count_once_for_gunco(self):
        target = DummyTarget(1000, 0, 0)
        for when in range(7):
            target.add_puncture(when)
        self.assertEqual(target.puncture_stacks(6), 5)
        self.assertEqual(target.unique_status_count(6), 1)
        # Oldest two were replaced at the cap; expiry is exclusive.
        self.assertEqual(target.puncture_stacks(12), 4)
        self.assertEqual(target.puncture_stacks(16), 0)
        target.add_puncture(20, max_stacks=3)
        for _ in range(6):
            target.add_puncture(20, max_stacks=3)
        self.assertEqual(target.puncture_stacks(20), 3)
        with self.assertRaises(ValueError):
            target.add_puncture(20, max_stacks=0)

    def test_puncture_replaces_oldest_not_longest_expiry(self):
        target = DummyTarget(1000, 0, 0)
        target.add_puncture(0, duration=100, max_stacks=2)
        target.add_puncture(1, duration=10, max_stacks=2)
        target.add_puncture(2, duration=10, max_stacks=2)
        self.assertEqual(target.puncture_expiries, [11, 12])
        self.assertEqual(target.puncture_stacks(13), 0)
        self.assertEqual(target.unique_status_count(13), 0)


class OcucorMechanicTests(unittest.TestCase):
    def test_puncture_on_a_hit_only_changes_subsequent_hit_crit(self):
        class AlwaysPuncture:
            def random(self):
                return 0.2

            def choices(self, population, weights, k):
                return ["PUNC"] * k

        build = build_ocucor(ARCANE_FLARE, "Multishot")
        target = DummyTarget(10**12, 0, 0)
        with patch.object(ocucor.random, "Random", return_value=AlwaysPuncture()), \
                patch.object(ocucor, "effective_crit_chance_pct",
                             wraps=effective_crit_chance_pct) as crit:
            simulate(build, target, full_beam_ramp=True,
                     max_time=build.tick_interval * 1.5)
        stack_args = [call.args[2] for call in crit.call_args_list]
        self.assertEqual(stack_args[0], 0)
        self.assertGreater(stack_args[1], 0)

    def test_heat_inheritance_sensitivity_is_explicit(self):
        separate = DummyTarget(1000, 0, 0)
        inherited = DummyTarget(1000, 0, 0)
        for target, mode in ((separate, "per_hit"), (inherited, "first_hit")):
            _add_heat(target, 0.0, 10.0, 2.0, 6.0, mode)
            _add_heat(target, 0.1, 50.0, 3.0, 6.0, mode)
        self.assertEqual((separate.heat_procs[1].seed,
                          separate.heat_procs[1].crit_factor), (50.0, 3.0))
        self.assertEqual((inherited.heat_procs[1].seed,
                          inherited.heat_procs[1].crit_factor), (10.0, 2.0))

    def test_ramp_heat_seed_sensitivity_changes_first_seed_not_crit(self):
        build = build_ocucor(ARCANE_ENERVATE, "Multishot")
        default, ramped = DummyTarget(10**9, 0, 0), DummyTarget(10**9, 0, 0)
        simulate(build, default, seed=6, starting_tendrils=4, max_time=0.01)
        simulate(build, ramped, seed=6, starting_tendrils=4, max_time=0.01,
                 ramp_heat_seed=True)
        self.assertTrue(default.heat_procs)
        self.assertAlmostEqual(ramped.heat_procs[0].seed, default.heat_procs[0].seed)
        self.assertAlmostEqual(ramped.heat_procs[0].crit_factor,
                               default.heat_procs[0].crit_factor * 0.2)

    def test_reload_and_magazine_empty_remove_stored_tendrils(self):
        build = build_ocucor(ARCANE_ENERVATE, "Multishot")
        result = simulate(build, DummyTarget(10**12, 2700, 0), seed=3,
                          starting_tendrils=4, max_time=6.3)
        self.assertTrue(math.isinf(result.ttk))
        self.assertEqual(result.final_tendrils, 0)
        self.assertEqual(result.reloads, 1)

    def test_flare_can_start_full_or_ramp_from_zero(self):
        build = build_ocucor(ARCANE_FLARE, "Multishot")
        full = simulate(build, DummyTarget(10**12, 2700, 0), seed=3,
                        starting_tendrils=4, starting_flare_stacks=40,
                        max_time=0.1)
        self.assertEqual(full.flare_stacks_peak, 40)
        self.assertEqual(full.flare_cap_time, 0.0)
        cold = simulate(build, DummyTarget(10**12, 2700, 0), seed=3,
                        starting_tendrils=4, max_time=4.0)
        self.assertEqual(cold.flare_stacks_peak, FLARE_MAX_STACKS)
        self.assertGreater(cold.flare_cap_time, 0)
        with self.assertRaises(ValueError):
            simulate(build_ocucor(ARCANE_ENERVATE, "Multishot"),
                     DummyTarget(10**12, 0, 0), starting_flare_stacks=40)

    def test_fatal_heat_still_stacks_flare(self):
        class AlwaysHeat:
            def random(self):
                return 0.0

            def choices(self, population, weights, k):
                return ["HEAT"] * k

        with patch.object(ocucor.random, "Random", return_value=AlwaysHeat()):
            single = simulate(build_ocucor(ARCANE_FLARE, "Multishot"),
                              DummyTarget(1, 0, 0))
            room = simulate_room(ARCANE_FLARE, "Multishot", 1,
                                 factory=lambda: DummyTarget(1, 0, 0))
        self.assertEqual(single.ttk, 0.0)
        self.assertEqual(single.flare_stacks_peak, 1)
        self.assertEqual(room.flare_peak, 1)

    def test_direct_tendril_kills_do_not_create_tendrils(self):
        result = simulate_room(ARCANE_FLARE, "Multishot", 6, seed=1,
                               starting_tendrils=1,
                               factory=lambda: DummyTarget(1, 0, 0))
        self.assertEqual(result.primary_direct_kills, 3)
        self.assertEqual(result.tendril_direct_kills, 3)
        self.assertEqual(result.status_kills, 0)
        self.assertEqual(result.tendril_peak, 3)

    def test_lone_target_room_matches_single_target_for_paired_seeds(self):
        for arcane, flare in ((ARCANE_ENERVATE, 0), (ARCANE_FLARE, 0),
                              (ARCANE_FLARE, 40)):
            for tendrils in (0, 4):
                for seed in range(3):
                    with self.subTest(arcane=arcane, flare=flare,
                                      tendrils=tendrils, seed=seed):
                        build = build_ocucor(arcane, "Multishot")
                        single = simulate(build, make_target(True), seed=seed,
                                          starting_tendrils=tendrils,
                                          starting_flare_stacks=flare)
                        room = simulate_room(arcane, "Multishot", 1, seed=seed,
                                             factory=lambda: make_target(True),
                                             starting_tendrils=tendrils,
                                             starting_flare_stacks=flare)
                        self.assertEqual(single.ttk, room.clear_time)
                        self.assertEqual(single.flare_stacks_peak, room.flare_peak)
                        if arcane == ARCANE_ENERVATE:
                            extra = simulate_room(
                                arcane, "Multishot", 1, seed=seed,
                                factory=lambda: make_target(True),
                                starting_tendrils=tendrils,
                                enervate_extra_pct=100.0)
                            self.assertEqual(single.ttk, extra.clear_time)

    def test_user_asserted_overguard_gate_is_a_routing_sensitivity(self):
        kwargs = dict(overguard=50.0, armor=0.0, viral_stacks=0)
        wiki_default = route_enemy_hit({"HEAT": 100.0}, **kwargs)
        gated = discard_overguard_overflow({"HEAT": 100.0}, **kwargs)
        self.assertTrue(wiki_default.broke_overguard)
        self.assertEqual(wiki_default.health, 50.0)
        self.assertEqual(gated.health, 0.0)
        self.assertEqual(gated.overguard, 50.0)

    def test_comparison_reports_timeouts_and_paired_difference(self):
        with contextlib.redirect_stdout(io.StringIO()):
            report = compare("smoke", eximus=False, trials=2, seed=8,
                             tendrils=4, room=False)
        self.assertEqual(report["settings"]["starting_tendrils"], 4)
        self.assertEqual(report["enervate"]["attempted"], 2)
        self.assertEqual(report["enervate"]["timed_out"], 0)
        self.assertEqual(report["paired"]["flare_full"]["complete_pairs"], 2)
        self.assertEqual(report["flare_full"]["flare_cap_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
