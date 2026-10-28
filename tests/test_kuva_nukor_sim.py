"""Tests for the Kuva Nukor tick-by-tick kill simulation.

Stat pins are hand-computed from the mod values on the wiki pages; simulation
tests exercise selected invariants against the SP150 Eximus Heavy Gunner.
They do not establish a valid Monte Carlo ranking.
"""
from __future__ import annotations

import math
import unittest

from modules.crit import quantize_crit_multiplier
from modules.enemy_scaling import steel_path_eximus_heavy_gunner
from modules.kuva_nukor_sim import (
    AMMO_PER_TICK,
    BASE_MAGNETIC,
    BASE_TOTAL,
    BLAST_RADIAL_COEF,
    BLAST_SINGLE_COEF,
    LAST_MODS,
    MAGAZINE,
    PISTOL_ELEMENTALIST_SD,
    RAMP_START,
    BlastProc,
    DummyTarget,
    _heat_strip_fraction,
    build_nukor,
    enervate_afcc,
    galv_shot_scale,
    roll_multishot,
    run_trials,
    simulate,
    simulate_room,
    steel_path_dummy_factory,
    viral_magnetic_multiplier,
)

DUMMY = steel_path_eximus_heavy_gunner(150)


class BuildStatTests(unittest.TestCase):
    def test_progenitor_and_base(self) -> None:
        self.assertAlmostEqual(BASE_MAGNETIC, 12.6)
        self.assertAlmostEqual(BASE_TOTAL, 33.6)

    def test_shared_baseline_stats(self) -> None:
        b = build_nukor("Primed Pistol Gambit")
        # Galv Diffusion +230% and Lethal Torrent +60% -> 3.9 merged beams.
        self.assertAlmostEqual(b.multishot, 3.9)
        # 10/s x 1.6 fire rate.
        self.assertAlmostEqual(b.fire_rate, 16.0)
        self.assertAlmostEqual(b.tick_interval, 1 / 16)
        # 50% x (1 + 80% Galv Shot) per beam, merged x3.9.
        self.assertAlmostEqual(b.status_per_beam, 0.9)
        self.assertAlmostEqual(b.merged_status, 3.51)
        # Wiki Primed Target Cracker: +110% at max rank.
        # 5.0 x (1 + 110% PTC + 101.3% riven).
        self.assertAlmostEqual(
            b.crit_multiplier, quantize_crit_multiplier(5.0) * 3.113)
        # Only the Riven affects duration; Elementalist buffs status damage.
        self.assertAlmostEqual(b.status_duration_mult, 2.125)
        self.assertAlmostEqual(b.proc_duration, 12.75)
        self.assertAlmostEqual(b.heat_ramp_interval, 0.5 * 2.125)
        # Damage bonus is Galvanized Shot's +120% only (no Hornet Strike).
        self.assertAlmostEqual(b.damage_bonus, 1.2)
        self.assertAlmostEqual(b.heat_bonus, 1.65)

    def test_comparison_candidates_use_max_rank_primed_target_cracker(self) -> None:
        # Max-rank PTC adds 110%, not 120%. None of these last-slot mods
        # changes the assumed 101.3% Riven critical-damage bonus.
        for name in ("Hornet Strike", "Scorch", "Frostbite"):
            with self.subTest(last_mod=name):
                self.assertAlmostEqual(build_nukor(name).crit_multiplier,
                                       quantize_crit_multiplier(5.0) * 3.113)

    def test_ppg_crit_chance_and_afcc(self) -> None:
        b = build_nukor("Primed Pistol Gambit")
        # 7% x (1 + 187%) = 20.09% modded crit chance.
        self.assertAlmostEqual(b.crit_chance_per_beam_pct, 20.09)
        self.assertAlmostEqual(b.afcc_pct, 102.45 + 0.5 * 20.09)

    def test_hollow_point_tradeoff(self) -> None:
        b = build_nukor("Hollow Point")
        self.assertAlmostEqual(b.damage_bonus, 1.05)       # 120% - 15%
        self.assertAlmostEqual(
            b.crit_multiplier, quantize_crit_multiplier(5.0) * 3.713)
        self.assertAlmostEqual(b.afcc_pct, 102.45 + 0.5 * 7.0)

    def test_scorch_keeps_heat_and_raises_status(self) -> None:
        b = build_nukor("Scorch")
        self.assertAlmostEqual(b.heat_bonus, 2.25)          # 165% + 60%
        self.assertAlmostEqual(b.merged_status, 0.5 * 2.4 * 3.9)
        self.assertEqual(set(b.type_damage), {"RAD", "MAG", "HEAT", "VIRAL"})

    def test_hornet_strike_additive_with_galvanized_shot(self) -> None:
        b = build_nukor("Hornet Strike")
        # +220% adds on top of Galvanized Shot's +120% -> +340% total.
        self.assertAlmostEqual(b.damage_bonus, 3.40)
        self.assertAlmostEqual(b.modded_base_single, 33.6 * 4.4)
        # Status/crit/fire rate are untouched.
        self.assertAlmostEqual(b.merged_status, 3.51)
        self.assertAlmostEqual(b.fire_rate, 16.0)
        self.assertAlmostEqual(b.afcc_pct, 102.45 + 0.5 * 7.0)
        self.assertAlmostEqual(b.heat_bonus, 1.65)

    def test_anemic_agility_tradeoff(self) -> None:
        b = build_nukor("Anemic Agility")
        self.assertAlmostEqual(b.fire_rate, 25.0)           # 10 x 2.5
        self.assertAlmostEqual(b.damage_bonus, 1.05)
        self.assertAlmostEqual(b.tick_interval, 0.04)

    def test_proc_weights_normalized(self) -> None:
        for name in LAST_MODS:
            b = build_nukor(name)
            self.assertAlmostEqual(sum(b.proc_weights.values()), 1.0)


class NukorConstantsTests(unittest.TestCase):
    def test_beam_specific_constants(self) -> None:
        # Nukor characteristics: 30% ramp start (not the generic 20%) and
        # 0.5 ammo per continuous-beam tick.
        self.assertEqual(RAMP_START, 0.3)
        self.assertEqual(AMMO_PER_TICK, 0.5)


class FrostbiteBuildTests(unittest.TestCase):
    def test_cold_combines_with_heat_into_blast(self) -> None:
        b = build_nukor("Frostbite")
        self.assertIn("BLAST", b.type_damage)
        self.assertNotIn("HEAT", b.type_damage)
        # 165% Heat + 60% Cold add into a 225% Blast element.
        self.assertAlmostEqual(b.blast_bonus, 2.25)
        self.assertAlmostEqual(
            b.type_damage["BLAST"], b.modded_base_single * 2.25)
        # Same status chance profile as Scorch.
        self.assertAlmostEqual(b.merged_status, 0.5 * 2.4 * 3.9)
        # Blast fuse = 1.5 s x status duration multiplier.
        self.assertAlmostEqual(b.blast_fuse, 1.5 * 2.125)
        self.assertAlmostEqual(sum(b.proc_weights.values()), 1.0)
        self.assertAlmostEqual(b.proc_weights["BLAST"], 0.5278, places=4)

    def test_heat_builds_keep_heat_element(self) -> None:
        for name in ("Scorch", "Hornet Strike", "No 8th mod"):
            b = build_nukor(name)
            self.assertIn("HEAT", b.type_damage)
            self.assertNotIn("BLAST", b.type_damage)
            self.assertEqual(b.blast_bonus, 0.0)


class BlastMechanicTests(unittest.TestCase):
    def test_stack_damage_helpers(self) -> None:
        target = DummyTarget(10_000.0, 2700.0, 5_000.0)
        target.blast_stacks = [
            BlastProc(0.0, 4.5375, 100.0, 17.0),
            BlastProc(0.1, 4.6375, 100.0, 15.0),
        ]
        single = target.blast_single_damage(PISTOL_ELEMENTALIST_SD)
        expected_single = BLAST_SINGLE_COEF * (
            100 * 1.9 * 17 + 100 * 1.9 * 15)
        self.assertAlmostEqual(single, expected_single)
        radial = target.blast_radial_damage(PISTOL_ELEMENTALIST_SD)
        expected_radial = BLAST_RADIAL_COEF * (
            100 * 1.9 * 17 + 100 * 1.9 * 15)
        self.assertAlmostEqual(radial, expected_radial)
        # Radial is exactly ten times the single-target damage.
        self.assertAlmostEqual(radial / single, 10.0)

    def test_frostbite_never_strips_armor(self) -> None:
        b = build_nukor("Frostbite")
        r = simulate(b, steel_path_dummy_factory(), seed=11)
        self.assertGreater(r.blast_procs, 50)
        self.assertEqual(r.heat_procs, 0)
        self.assertEqual(r.final_armor, 2700.0)  # no Heat = no strip
        self.assertTrue(math.isfinite(r.ttk))

    def test_frostbite_trials_produce_finite_damage(self) -> None:
        summary = run_trials("Frostbite", steel_path_dummy_factory, trials=20)
        self.assertTrue(math.isfinite(summary["ttk_median"]))



class RoomClearTests(unittest.TestCase):
    def test_room_sim_kills_everyone_and_scales_radials(self) -> None:
        b = build_nukor("Frostbite")
        r = simulate_room(b, 10, seed=7000)
        self.assertEqual(len(r.kill_times), 10)
        self.assertGreater(r.radial_events, 20)
        self.assertGreater(r.radial_damage_total, r.direct_damage_total)
        self.assertTrue(math.isfinite(r.clear_time))

    def test_heat_builds_have_no_radials(self) -> None:
        for name in ("Scorch", "Hornet Strike"):
            r = simulate_room(build_nukor(name), 10, seed=7000)
            self.assertEqual(r.radial_events, 0)
            self.assertEqual(r.radial_damage_total, 0.0)
            self.assertEqual(len(r.kill_times), 10)

    def test_room_is_reproducible_with_same_seed(self) -> None:
        build = build_nukor("Frostbite")
        first = simulate_room(build, 3, seed=9000)
        second = simulate_room(build, 3, seed=9000)
        self.assertEqual(first.clear_time, second.clear_time)
        self.assertEqual(first.kill_times, second.kill_times)



class EnervateAFCCTests(unittest.TestCase):
    def test_piecewise_branches(self) -> None:
        self.assertAlmostEqual(enervate_afcc(7), 105.95)
        self.assertAlmostEqual(enervate_afcc(100), 152.45)
        self.assertAlmostEqual(enervate_afcc(145), 77.5 + 0.7 * 145)
        self.assertAlmostEqual(enervate_afcc(155), 70 + 0.75 * 155)
        self.assertAlmostEqual(enervate_afcc(200), 225.0)
        self.assertAlmostEqual(enervate_afcc(250), 275.0)


class StackMultiplierTests(unittest.TestCase):
    def test_viral_magnetic_table(self) -> None:
        self.assertEqual(viral_magnetic_multiplier(0), 1.0)
        self.assertEqual(viral_magnetic_multiplier(1), 2.0)
        self.assertEqual(viral_magnetic_multiplier(2), 2.25)
        self.assertEqual(viral_magnetic_multiplier(10), 4.25)
        self.assertEqual(viral_magnetic_multiplier(99), 4.25)  # capped


class HeatStripTests(unittest.TestCase):
    def test_ramp_schedule_with_status_duration(self) -> None:
        interval = 1.5125  # 0.5s x (1 + 202.5% status duration)
        self.assertEqual(_heat_strip_fraction(0.0, interval), 0.0)
        self.assertEqual(_heat_strip_fraction(1.5, interval), 0.0)
        self.assertEqual(_heat_strip_fraction(1.5125, interval), 0.15)
        self.assertEqual(_heat_strip_fraction(3.025, interval), 0.30)
        self.assertEqual(_heat_strip_fraction(4.5375, interval), 0.40)
        self.assertEqual(_heat_strip_fraction(6.05, interval), 0.50)
        self.assertEqual(_heat_strip_fraction(99.0, interval), 0.50)

    def test_many_heat_procs_share_one_ramp_and_cap(self) -> None:
        target = DummyTarget(1000.0, 2700.0, 100.0)
        interval = 1.5125
        target.heat_procs.append(_make_proc(age=4.0))  # 30% shared strip
        self.assertAlmostEqual(target.current_armor(0.0, interval), 2700 * 0.70)
        for _ in range(20):
            target.heat_procs.append(_make_proc(age=2.0))
        self.assertAlmostEqual(target.current_armor(0.0, interval), 2700 * 0.70)
        self.assertAlmostEqual(target.current_armor(3.0, interval), 1350.0)

    def test_heat_expiry_restores_armor_in_steps(self) -> None:
        target = DummyTarget(1000, 2700, 0)
        from modules.kuva_nukor_sim import HeatProc
        target.heat_procs.append(HeatProc(0, 100, 1, 0))
        target.prune(6.0, 6.0)  # final tick still applies
        self.assertEqual(len(target.heat_procs), 1)
        target.prune(6.01, 6.0)
        self.assertAlmostEqual(target.current_armor(6.01, 0.5), 1350)
        self.assertAlmostEqual(target.current_armor(7.5, 0.5), 1620)
        self.assertAlmostEqual(target.current_armor(12.0, 0.5), 2700)

    def test_live_status_types_not_kill_stacks_determine_gunco(self) -> None:
        target = DummyTarget(1000, 0, 0)
        self.assertEqual(target.unique_status_count(0), 0)
        target.record_status("MICROWAVE", 0, math.inf)
        target.record_status("HEAT", 0.2, 6)
        target.record_status("HEAT", 1, 6)  # same type counts once
        self.assertEqual(target.unique_status_count(1), 2)
        self.assertEqual(target.unique_status_count(8), 1)
        self.assertAlmostEqual(galv_shot_scale(1.2, 0), 1 / 2.2)
        self.assertAlmostEqual(galv_shot_scale(1.2, 3), 4.6 / 2.2)

    def test_fractional_multishot_rolls_integer_counts(self) -> None:
        import random
        rng = random.Random(42)
        counts = [roll_multishot(rng, 3.9) for _ in range(10000)]
        self.assertEqual(set(counts), {3, 4})
        self.assertAlmostEqual(sum(counts) / len(counts), 3.9, delta=0.01)


def _make_proc(age: float):
    from modules.kuva_nukor_sim import HeatProc
    # start = -age so "now = 0" gives the requested age; refreshed far future.
    return HeatProc(start=-age, seed=100.0, crit_factor=1.0, refreshed=99.0)


class SimulationTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self) -> None:
        b = build_nukor("Scorch")
        r1 = simulate(b, steel_path_dummy_factory(), seed=42)
        r2 = simulate(b, steel_path_dummy_factory(), seed=42)
        self.assertEqual(r1.ttk, r2.ttk)
        self.assertEqual(r1.heat_procs, r2.heat_procs)

    def test_overguard_breaks_before_health_depletes(self) -> None:
        b = build_nukor("Primed Pistol Gambit")
        r = simulate(b, steel_path_dummy_factory(), seed=7)
        self.assertLessEqual(r.overguard_break_time, r.ttk)
        self.assertGreater(r.direct_to_overguard, 0.0)

    def test_damage_buckets_cover_the_kill(self) -> None:
        b = build_nukor("Scorch")
        r = simulate(b, steel_path_dummy_factory(), seed=7)
        # Overguard absorbed by direct damage; health by direct + DoT + break.
        # Current simulation reports the whole final hit as Overguard damage,
        # including overkill; see the audit for this routing limitation.
        self.assertGreaterEqual(r.direct_to_overguard + r.dot_to_overguard,
                                DUMMY.overguard)
        health_dealt = (r.direct_to_health + r.dot_to_health
                        + r.break_electric)
        self.assertGreaterEqual(health_dealt, DUMMY.health * 0.99)

    def test_no_reload_needed_in_two_second_fight(self) -> None:
        b = build_nukor("Anemic Agility")  # fastest ammo burn, 25/s
        r = simulate(b, steel_path_dummy_factory(), seed=7)
        self.assertEqual(r.reloads, 0)
        self.assertLessEqual(r.ticks, MAGAZINE)

    def test_all_candidates_produce_finite_results(self) -> None:
        summary = {
            name: run_trials(name, steel_path_dummy_factory, trials=200)
            for name in LAST_MODS
        }
        for name, result in summary.items():
            self.assertTrue(math.isfinite(result["ttk_median"]), name)
            self.assertEqual(result["trials"], 200)
        # Ranking is model-dependent; do not treat an old Monte Carlo
        # ordering or timing as an independent wiki fact.


    def test_factory_returns_independent_targets(self) -> None:
        t1 = steel_path_dummy_factory()
        t2 = steel_path_dummy_factory()
        self.assertIsNot(t1, t2)
        self.assertEqual(t1.health, t2.health)


if __name__ == "__main__":
    unittest.main()
