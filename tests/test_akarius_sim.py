"""Tests for the Akarius Prime Viral-vs-Corrosive Riven simulation."""
from __future__ import annotations

import math
import unittest
from dataclasses import replace
from unittest.mock import patch

from modules.akarius_sim import (
    BURST_DELAY,
    GALV_SHOT_CO,
    HORNET_STRIKE,
    RELOAD_TIME,
    RIVEN_CORROSIVE,
    RIVEN_VIRAL,
    AkariusTarget,
    build_akarius,
    corrosive_armor_factor,
    run_trials,
    simulate,
)
from modules.crit import quantize_crit_multiplier
from modules.enemy_scaling import steel_path_eximus_heavy_gunner

DUMMY = steel_path_eximus_heavy_gunner(150)


def factory() -> AkariusTarget:
    return AkariusTarget(DUMMY.health, DUMMY.armor, DUMMY.overguard)


class BuildStatTests(unittest.TestCase):
    def test_shared_stats(self) -> None:
        b = build_akarius(RIVEN_VIRAL)
        # 1 + 230% Galvanized Diffusion + 60% Lethal Torrent.
        self.assertAlmostEqual(b.multishot, 3.9)
        # 3.667 base x 1.6 Lethal Torrent fire rate.
        self.assertAlmostEqual(b.fire_rate, 3.667 * 1.6, places=4)
        self.assertAlmostEqual(b.intra_burst_delay, BURST_DELAY / 1.6)
        self.assertAlmostEqual(b.burst_cycle, 1 / b.fire_rate + b.intra_burst_delay)
        # 34% status x (1 + 80% Galvanized Shot), per damage instance.
        self.assertAlmostEqual(b.status_per_instance, 0.34 * 1.8)
        # No crit-chance mods: AFCC is driven purely by Secondary Enervate.
        self.assertAlmostEqual(b.afcc_pct, 102.45 + 0.5 * 18.0)
        # 2.0 x (1 + 110% PTC + 133.7% Riven).
        self.assertAlmostEqual(
            b.crit_multiplier, quantize_crit_multiplier(2.0) * 3.437)
        # Elementalist gives status damage and reload speed, not duration.
        self.assertAlmostEqual(b.status_duration_mult, 1.0)
        self.assertAlmostEqual(b.heat_ramp_interval, 0.5)
        self.assertAlmostEqual(b.blast_fuse, 1.5)
        self.assertAlmostEqual(b.corrosive_duration, 8.0)

    def test_gunco_multiplicative_vs_hornet_strike(self) -> None:
        # Repo GunCO table: Akarius Prime Rocket Impact is a "multiply" rule;
        # the detonation radius receives no CO-type bonus at all.
        b = build_akarius(RIVEN_VIRAL)
        self.assertAlmostEqual(
            b.impact_bracket,
            (1.0 + HORNET_STRIKE) * (1.0 + GALV_SHOT_CO))
        self.assertEqual(b.impact_bracket, 3.2 * 2.2)
        self.assertAlmostEqual(b.blast_bracket, 1.0 + HORNET_STRIKE)
        # An additive rule would be 4.4; the multiply rule gives 7.04.
        self.assertGreater(b.impact_bracket, 1.0 + HORNET_STRIKE + GALV_SHOT_CO)

    def test_instance_damage_and_weights(self) -> None:
        b = build_akarius(RIVEN_VIRAL)
        self.assertAlmostEqual(b.impact_base_modded, 68.0 * 7.04)
        self.assertAlmostEqual(b.blast_base_modded, 509.0 * 3.2)
        self.assertEqual(set(b.impact_instance), {"IMPACT", "HEAT", "VIRAL"})
        self.assertEqual(set(b.blast_instance), {"BLAST", "HEAT", "VIRAL"})
        self.assertAlmostEqual(sum(b.proc_weights_impact.values()), 1.0)
        self.assertAlmostEqual(sum(b.proc_weights_blast.values()), 1.0)
        # Heat is the dominant proc weight in both instances.
        self.assertGreater(b.proc_weights_impact["HEAT"], 0.4)

    def test_corrosive_riven_replaces_viral_elements(self) -> None:
        b = build_akarius(RIVEN_CORROSIVE)
        self.assertIn("CORROSIVE", b.impact_instance)
        self.assertIn("CORROSIVE", b.blast_instance)
        self.assertNotIn("VIRAL", b.impact_instance)
        # Same magnitudes either way; only the element label changes.
        bv = build_akarius(RIVEN_VIRAL)
        self.assertAlmostEqual(
            b.impact_instance["CORROSIVE"],
            bv.impact_instance["VIRAL"])

    def test_burst_schedule(self) -> None:
        b = build_akarius(RIVEN_VIRAL)
        # Base 0.12 s burst delay is shortened by +60% fire rate.
        self.assertEqual(BURST_DELAY, 0.12)
        self.assertGreater(b.burst_cycle, BURST_DELAY)


class CorrosiveArmorTests(unittest.TestCase):
    def test_stack_schedule(self) -> None:
        self.assertEqual(corrosive_armor_factor(0), 1.0)
        self.assertAlmostEqual(corrosive_armor_factor(1), 0.74)  # 26%
        self.assertAlmostEqual(corrosive_armor_factor(2), 0.68)  # +6%
        self.assertAlmostEqual(corrosive_armor_factor(10), 0.20)  # 80% cap
        self.assertAlmostEqual(corrosive_armor_factor(99), 0.20)

    def test_multiplies_with_heat_strip(self) -> None:
        t = AkariusTarget(1000.0, 2700.0, 100.0)
        t.corrosive_expiries.append(99.0)  # one stack active at t=0
        # No Heat yet: 2700 x 0.74.
        self.assertAlmostEqual(t.current_armor(0.0, 0.95), 2700.0 * 0.74)


class SimulationTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self) -> None:
        b = build_akarius(RIVEN_VIRAL)
        r1 = simulate(b, factory(), seed=42)
        r2 = simulate(b, factory(), seed=42)
        self.assertEqual(r1.ttk, r2.ttk)
        self.assertEqual(r1.shots, r2.shots)

    def test_overguard_breaks_first_and_fast(self) -> None:
        # No Magnetic damage in this build, but raw direct damage breaks it.
        r = simulate(build_akarius(RIVEN_VIRAL), factory(), seed=7)
        self.assertLessEqual(r.overguard_break_time, 0.2)
        self.assertLessEqual(r.overguard_break_time, r.ttk)
        self.assertGreater(r.direct_to_overguard, 0.0)

    def test_viral_from_multishot_does_not_amplify_same_shot(self) -> None:
        # Two rockets per ammo shot, each with separate impact and detonation.
        # Force Viral on each instance and turn off crits and GunCO. The Wiki
        # says multishot hits do not benefit from same-shot Viral procs.
        b = replace(build_akarius(RIVEN_VIRAL), multishot=2.0,
                    afcc_pct=0.0, status_per_instance=1.0,
                    impact_instance={"IMPACT": 1.0}, impact_base_modded=1.0,
                    blast_instance={"BLAST": 100.0}, blast_base_modded=100.0,
                    proc_weights_impact={"VIRAL": 1.0},
                    proc_weights_blast={"VIRAL": 1.0})
        target = AkariusTarget(1e9, 0.0, 0.0)
        with patch("modules.akarius_sim.GALV_SHOT_CO", 0.0):
            result = simulate(b, target, seed=1, max_time=0.076)
        # Shot one: 2 * (1.5 Impact + 100 Blast), before Viral exists.
        # Shot two, 0.075 s later, benefits from the first shot's four stacks
        # (2 + 3 * 0.25 = 2.75), but not its own four new stacks.
        self.assertEqual(result.shots, 2)
        self.assertAlmostEqual(result.direct_to_health, 203.0 * (1 + 2.75))
        self.assertEqual(target.viral_stacks(0.075), 8)

    def test_splash_only_excludes_projectile_impact_and_its_status(self) -> None:
        b = replace(build_akarius(RIVEN_VIRAL), multishot=1.0,
                    afcc_pct=0.0, status_per_instance=1.0,
                    impact_instance={"IMPACT": 1.0}, impact_base_modded=1.0,
                    blast_instance={"BLAST": 100.0}, blast_base_modded=100.0,
                    proc_weights_impact={"VIRAL": 1.0},
                    proc_weights_blast={"HEAT": 1.0})
        target = AkariusTarget(1e9, 0.0, 0.0)
        result = simulate(b, target, seed=1, max_time=0.001, direct_hits=False)
        self.assertAlmostEqual(result.direct_to_health, 100.0)
        self.assertEqual(target.viral_stacks(0.0), 0)
        self.assertEqual(len(target.heat_procs), 1)
        self.assertEqual(result.shots, 1)

    def test_gunco_still_uses_status_from_earlier_multishot(self) -> None:
        # Unlike Viral's damage vulnerability, Galvanized Shot treats
        # multishot impacts as sequential for counting distinct statuses.
        b = replace(build_akarius(RIVEN_VIRAL), multishot=2.0,
                    afcc_pct=0.0, status_per_instance=1.0,
                    impact_instance={"VIRAL": 220.0}, impact_base_modded=220.0,
                    blast_instance={"BLAST": 1.0}, blast_base_modded=1.0,
                    proc_weights_impact={"HEAT": 1.0},
                    proc_weights_blast={"HEAT": 1.0})
        target = AkariusTarget(1e9, 0.0, 0.0)
        result = simulate(b, target, seed=1, max_time=0.001)
        # Impact one has no CO (100); impact two has one status (220).
        # Each explosion adds one neutral Blast damage and has no GunCO.
        self.assertEqual(result.shots, 1)
        self.assertAlmostEqual(result.direct_to_health, 322.0)

    def test_both_riven_scenarios_produce_finite_results(self) -> None:
        viral = run_trials(RIVEN_VIRAL, trials=200)
        corrosive = run_trials(RIVEN_CORROSIVE, trials=200)
        self.assertTrue(math.isfinite(viral["ttk_median"]))
        self.assertTrue(math.isfinite(corrosive["ttk_median"]))

    def test_trial_summary_uses_a_fresh_custom_target(self) -> None:
        made = []

        def custom_factory() -> AkariusTarget:
            target = AkariusTarget(10_000.0, 0.0, 0.0)
            made.append(target)
            return target

        result = run_trials(RIVEN_VIRAL, trials=3, base_seed=42,
                            target_factory=custom_factory)
        self.assertEqual(len(made), 3)
        self.assertEqual(len({id(target) for target in made}), 3)
        self.assertEqual(result["trials_attempted"], 3)
        self.assertEqual(result["timed_out"], 0)
        self.assertEqual(result["overguard_median"], 0.0)
        self.assertGreaterEqual(result["first_magazine_kills"], 0)

    def test_trial_summary_reports_censored_custom_targets(self) -> None:
        result = run_trials(RIVEN_CORROSIVE, trials=2, max_time=0.0,
                            target_factory=lambda: AkariusTarget(1e9, 0, 0))
        self.assertEqual(result["trials_attempted"], 2)
        self.assertEqual(result["timed_out"], 2)
        self.assertTrue(math.isinf(result["ttk_mean"]))
        self.assertEqual(result["first_magazine_kills"], 0)

    def test_reload_after_eight_shots_on_large_target(self) -> None:
        build = build_akarius(RIVEN_CORROSIVE)
        target = AkariusTarget(1e12, 0, 0)
        result = simulate(build, target, seed=1,
                          max_time=build.burst_cycle * 4 + RELOAD_TIME + 0.1)
        self.assertGreaterEqual(result.reloads, 1)

    def test_corrosive_build_actually_procs_corrosive(self) -> None:
        r = simulate(build_akarius(RIVEN_CORROSIVE), factory(), seed=11)
        self.assertGreater(r.corrosive_procs, 5)
        self.assertLess(r.final_armor, 2700.0)

    def test_viral_build_never_procs_corrosive(self) -> None:
        r = simulate(build_akarius(RIVEN_VIRAL), factory(), seed=11)
        self.assertEqual(r.corrosive_procs, 0)


if __name__ == "__main__":
    unittest.main()
