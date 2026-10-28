"""Internal consistency tests for the *hypothetical* slam-count model.

These fixtures do not establish current in-game Jat/Afflictions behavior.
"""
from dataclasses import replace
import unittest
from unittest.mock import patch

from modules.enemy_scaling import steel_path_eximus_heavy_gunner
from modules.jat_kittag_slam_analysis import BUILD_BY_KEY
from modules.jat_kittag_slam_counts import (
    Assumptions, Fight, Target, simulate_trial, summarize,
)
from modules.status_damage import magnetic_break_electric_tick


A = BUILD_BY_KEY["focus_fever_gas_cold_damage"]
B = BUILD_BY_KEY["focus_gas_cc_cd"]


class FakeRng:
    def __init__(self, values, choices=()):
        self.values = iter(values)
        self.procs = list(choices)

    def random(self):
        return next(self.values)

    def choices(self, population, weights, k):
        assert k == len(self.procs)
        assert all(p in population for p in self.procs)
        return self.procs


class ParametersAndCountsTests(unittest.TestCase):
    def test_interval_validation_for_sustained_five_combo(self):
        Assumptions(interval=.2)
        with self.assertRaises(ValueError):
            Assumptions(interval=.19)
        with self.assertRaises(ValueError):
            Assumptions(interval=float("nan"))

    def test_rejects_shields(self):
        enemy = replace(steel_path_eximus_heavy_gunner(), shields=1)
        with self.assertRaises(ValueError):
            Target.from_scaled(enemy)

    def test_direct_only_counts_broken_gate_and_no_overflow(self):
        target = Target("test", health=100, overguard=100, armor_dr=.9)
        a = Assumptions(statuses=False)
        for build in (A, B):
            for seed in range(10):
                result = simulate_trial(build, target, a, seed=seed)
                self.assertEqual(result.slams, 2)
                self.assertEqual(result.death_time, .65)
                self.assertEqual(result.overguard_break_slam, 1)

    def test_direct_crit_tiers_are_sampled_not_average_hit(self):
        f = Fight(B, Target("test", 1e9, 0, .9), Assumptions(statuses=False))
        f.slam(FakeRng([0.0]), 0)  # orange, not the mean crit
        raw_noncrit = B.direct_average(5) / B.average_crit_multiplier
        expected = raw_noncrit * (1 + 2 * (B.crit_multiplier - 1)) * .1
        self.assertAlmostEqual(1e9 - f.health, expected, places=6)

    def test_tick_death_before_next_slam_counts_only_completed_slams(self):
        def toxin_then_no_damage(fight, rng, now):
            fight.slams += 1
            if fight.slams == 1:
                fight._add_dot("TOXIN", 1, 2, now)  # 2.65 raw / tick
        with patch.object(Fight, "slam", toxin_then_no_damage):
            target = Target("test", .2, 0, .9)
            result = simulate_trial(A, target, Assumptions(max_slams=2))
        self.assertEqual(result.slams, 2)  # attacks at 0 and .65, death at 1
        self.assertEqual(result.death_time, 1)
        self.assertTrue(result.killed)

    def test_summaries_are_reproducible_and_histogram_counts_all_kills(self):
        target = Target("test", 100, 100, .9)
        a = Assumptions(statuses=False)
        first = summarize(B, target, a, trials=20, base_seed=7)
        second = summarize(B, target, a, trials=20, base_seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first["mean_slams"], 2)
        self.assertEqual(first["median_slams"], 2)
        self.assertEqual(first["slam_count_histogram"], {2: 20})
        self.assertEqual(sum(first["slam_count_histogram"].values()), first["kills"])
        self.assertEqual(first["mean_slams_se"], 0)
        self.assertEqual(first["timeouts"], 0)

    def test_cutoff_reports_timeouts_and_conditional_summary(self):
        summary = summarize(A, Target("test", 1e20, 0, .9),
                            Assumptions(statuses=False, max_slams=1), trials=3)
        self.assertEqual(summary["attempted"], 3)
        self.assertEqual(summary["kills"], 0)
        self.assertEqual(summary["timeouts"], 3)
        self.assertIsNone(summary["mean_slams"])
        self.assertTrue(summary["conditional_on_kill"])


class LayerAndStatusTests(unittest.TestCase):
    def test_per_event_gate_discards_only_breaking_event(self):
        f = Fight(A, Target("test", 100, 50, .5), Assumptions())
        f._route(80, 0)
        self.assertEqual(f.overguard, 0)
        self.assertEqual(f.health, 100)
        f._route(10, 0)
        self.assertEqual(f.health, 95)

    def test_magnetic_break_proc_uses_six_ticks_and_combined_electric_bonus(self):
        f = Fight(A, Target("test", 100000, 1000, .9), Assumptions())
        f._add_magnetic(2, 0)
        f._route(500, 0)  # 2.25x vulnerability breaks 1000 Overguard
        self.assertEqual(f.overguard, 0)
        self.assertEqual(f.health, 100000)  # no overflow
        one_tick = magnetic_break_electric_tick(
            1000, 2, status_damage_bonus=.8, electricity_bonus=.6)
        f.advance(0)
        self.assertAlmostEqual(f.health, 100000 - one_tick * .1)
        f.advance(6)
        self.assertAlmostEqual(f.health, 100000 - one_tick * .1 * 6)

    def test_gas_ticks_immediately_but_toxin_is_delayed_and_both_end(self):
        f = Fight(A, Target("test", 100000, 0, 0), Assumptions())
        f._add_dot("GAS", 1, 20, 0)
        f._add_dot("TOXIN", 1, 20, 0)
        gas = .5 * 20 * (1 + A.gas_bonus)
        toxin = .5 * 20 * 2.65
        f.advance(0)
        self.assertAlmostEqual(f.health, 100000 - gas)
        f.advance(5)
        self.assertAlmostEqual(f.health, 100000 - 6 * gas - 5 * toxin)
        f.advance(6)
        self.assertAlmostEqual(f.health, 100000 - 6 * gas - 6 * toxin)
        self.assertEqual(f.dots, [])

    def test_shared_and_per_proc_aoe_clocks_are_distinct_hypotheses(self):
        for shared in (True, False):
            f = Fight(A, Target("test", 10000, 0, 0),
                      Assumptions(shared_aoe_ticks=shared))
            f._add_dot("ELECTRICITY", 1, 20, 0)
            f.advance(0)
            self.assertEqual(f.health, 10000 - 16)
            f._add_dot("ELECTRICITY", 1, 20, .25)
            f.advance(.25)
            # Shared: no second immediate pulse; separate clocks: there is one.
            self.assertEqual(f.health, 10000 - (16 if shared else 32))
            f.advance(1)
            # Shared: both stacks pulse together. Per-proc: only the first does.
            self.assertEqual(f.health, 10000 - 48)

    def test_gas_cap_replaces_oldest_and_truncates_added_groups(self):
        f = Fight(A, Target("test", 1e8, 0, 0), Assumptions())
        f._add_dot("GAS", 8, 10, 0)
        f._add_dot("GAS", 6, 20, .5)
        self.assertEqual([(d.count, d.proc_mbd) for d in f.dots], [(4, 10), (6, 20)])
        f._add_dot("GAS", 12, 30, 1)
        self.assertEqual([(d.count, d.proc_mbd) for d in f.dots], [(10, 30)])

    def test_blast_fuse_and_ten_stack_single_target_detonation(self):
        f = Fight(A, Target("test", 100, 0, 0), Assumptions())
        f._add_blast(9, .3, 0)
        self.assertEqual(f.health, 100)
        f._add_blast(1, .3, 0)
        self.assertAlmostEqual(f.health, 97)  # 10 x .3; no 5m AoE on host
        self.assertEqual(f.blast, [])
        f._add_blast(1, 2, .1)
        f.advance(1.599)
        self.assertAlmostEqual(f.health, 97)
        f.advance(1.6)
        self.assertAlmostEqual(f.health, 95)


class AfflictionsHypothesisTests(unittest.TestCase):
    def test_cross_type_means_and_reseeded_status_damage(self):
        f = Fight(A, Target("test", 1e9, 0, 0), Assumptions())
        f._add_dot("GAS", 1, 100, 0)
        f._add_dot("TOXIN", 2, 200, 0)
        f._afflict(0)
        gas = [d for d in f.dots if d.kind == "GAS"][-1]
        toxin = [d for d in f.dots if d.kind == "TOXIN"][-1]
        # Average each type (100 + 200), then status damage 1.8 a second time.
        self.assertEqual(gas.count, 6)
        self.assertEqual(toxin.count, 6)
        self.assertEqual(gas.proc_mbd, 540)
        self.assertEqual(toxin.proc_mbd, 540)
        self.assertEqual(gas.tick, 270)  # no literal Gas bonus in this hypothesis
        self.assertAlmostEqual(toxin.tick, 270 * 2.65)

    def test_gas_clone_bonus_is_a_separate_explicit_hypothesis(self):
        f = Fight(A, Target("test", 1e9, 0, 0),
                  Assumptions(clone_gas_bonus=True))
        f._add_dot("GAS", 1, 100, 0)
        f._afflict(0)
        self.assertAlmostEqual(f.dots[-1].tick, 90 * (1 + A.gas_bonus))

    def test_same_slam_statuses_can_seed_afflictions(self):
        f = Fight(A, Target("test", 1e9, 0, .9), Assumptions())
        f.slam(FakeRng([.9, .0], ["GAS", "TOXIN", "MAGNETIC"]), 0)
        self.assertEqual(f.triggers, 1)
        self.assertEqual(sum(d.count for d in f.dots if d.kind == "GAS"), 7)
        self.assertEqual(sum(d.count for d in f.dots if d.kind == "TOXIN"), 7)

    def test_default_defers_break_slam_trigger_optional_alternative_allows_it(self):
        for allowed in (False, True):
            f = Fight(A, Target("test", 1e9, 100, .9),
                      Assumptions(afflict_on_break=allowed))
            f.slam(FakeRng([.9, .0], ["GAS", "TOXIN", "MAGNETIC"]), 0)
            self.assertEqual(f.triggers, int(allowed))

    def test_two_sequential_passes_reseed_instead_of_one_twelve_stack_pass(self):
        f = Fight(A, Target("test", 1e9, 0, .9), Assumptions(affliction_passes=2))
        f.slam(FakeRng([.9, .0], ["GAS", "TOXIN", "MAGNETIC"]), 0)
        self.assertEqual(f.triggers, 2)
        toxins = [d for d in f.dots if d.kind == "TOXIN"]
        self.assertEqual([d.count for d in toxins], [1, 6, 6])
        self.assertGreater(toxins[-1].proc_mbd, toxins[-2].proc_mbd)

    def test_no_damaging_seed_does_not_assume_blast_only_replication(self):
        f = Fight(A, Target("test", 1e9, 0, 0), Assumptions())
        f._add_blast(1, 10, 0)
        f._afflict(0)
        self.assertEqual(f.triggers, 0)
        self.assertEqual(sum(g.count for g in f.blast), 1)


if __name__ == "__main__":
    unittest.main()
