"""Tests for the Akarius Prime Viral-vs-Corrosive Riven simulation."""
from __future__ import annotations

import math
import unittest

from modules.akarius_sim import (
    BURST_COUNT,
    BURST_DELAY,
    GALV_SHOT_CO,
    HORNET_STRIKE,
    RIVEN_CORROSIVE,
    RIVEN_VIRAL,
    AkariusTarget,
    build_akarius,
    corrosive_armor_factor,
    run_trials,
    simulate,
)
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
        self.assertAlmostEqual(b.burst_cycle, BURST_COUNT / b.fire_rate,
                               places=4)
        # 34% status x (1 + 80% Galvanized Shot), per damage instance.
        self.assertAlmostEqual(b.status_per_instance, 0.34 * 1.8)
        # No crit-chance mods: AFCC is driven purely by Secondary Enervate.
        self.assertAlmostEqual(b.afcc_pct, 102.45 + 0.5 * 18.0)
        # 2.0 x (1 + 120% PTC + 133.7% Riven).
        self.assertAlmostEqual(b.crit_multiplier, 2.0 * 3.537)
        # Status duration comes from Pistol Elementalist only.
        self.assertAlmostEqual(b.status_duration_mult, 1.9)
        self.assertAlmostEqual(b.heat_ramp_interval, 0.5 * 1.9)
        self.assertAlmostEqual(b.blast_fuse, 1.5 * 1.9)
        self.assertAlmostEqual(b.corrosive_duration, 8.0 * 1.9)

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
        # Two rockets 0.12 s apart, then recovery to the full cycle length.
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

    def test_both_rivens_kill_and_viral_is_faster_on_average(self) -> None:
        viral = run_trials(RIVEN_VIRAL, trials=200)
        corrosive = run_trials(RIVEN_CORROSIVE, trials=200)
        self.assertTrue(math.isfinite(viral["ttk_median"]))
        self.assertTrue(math.isfinite(corrosive["ttk_median"]))
        self.assertLess(viral["ttk_mean"], corrosive["ttk_mean"])

    def test_corrosive_never_kills_inside_first_magazine(self) -> None:
        # Mag 8 is empty before its armor ramp can finish the Eximus alone;
        # Viral's health amp occasionally does (bimodal Viral distribution).
        b = build_akarius(RIVEN_CORROSIVE)
        reloads = [simulate(b, factory(), seed=30000 + i).reloads
                   for i in range(120)]
        self.assertGreaterEqual(min(reloads), 1)

    def test_corrosive_build_actually_procs_corrosive(self) -> None:
        r = simulate(build_akarius(RIVEN_CORROSIVE), factory(), seed=11)
        self.assertGreater(r.corrosive_procs, 5)
        self.assertLess(r.final_armor, 2700.0)

    def test_viral_build_never_procs_corrosive(self) -> None:
        r = simulate(build_akarius(RIVEN_VIRAL), factory(), seed=11)
        self.assertEqual(r.corrosive_procs, 0)


if __name__ == "__main__":
    unittest.main()
