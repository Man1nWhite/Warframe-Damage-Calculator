"""Tests for the Alternox Prime Riven choice simulation."""
from __future__ import annotations

import dataclasses
import math
import random
import unittest

import modules.alternox_prime_sim as sim
from modules.alternox_prime_sim import (
    APTITUDE_STACK_CAP,
    BLAST_FUSE,
    CHAMBER_STACK_CAP,
    COMBINED_ELEMENT_STATS,
    MAGAZINE,
    R_BLAST,
    R_DAMAGE,
    R_ELEC,
    R_FIRE_RATE,
    R_HEAT,
    R_STATUS,
    R_TOXIN,
    RIVEN_PAIR_OPTIONS,
    AlternoxTarget,
    build_alternox,
    combine_elements,
    expected_dps,
    gunco_bonus,
    load_rifle_riven_averages,
    rank_riven_pairs,
    run_trials,
    simulate,
)
from modules.crit import quantize_crit_multiplier

# Average-grade Rifle Riven values, 3 positives + 1 curse (1.20 disposition).
AVG_DAMAGE = 1.856
AVG_ELEMENT = 1.013
AVG_FIRE_RATE = 0.675


class CsvLoaderTests(unittest.TestCase):
    def test_rifle_averages_match_vendored_table(self) -> None:
        avg = load_rifle_riven_averages()
        self.assertAlmostEqual(avg[R_DAMAGE], AVG_DAMAGE, places=3)
        self.assertAlmostEqual(avg[R_TOXIN], AVG_ELEMENT, places=3)
        self.assertAlmostEqual(avg[R_FIRE_RATE], AVG_FIRE_RATE, places=3)
        # Combined elements are intentionally absent from the base-attribute
        # CSV; the builder resolves them separately.
        self.assertNotIn(R_BLAST, avg)

    def test_loader_respects_plain_and_faction_units(self) -> None:
        avg = load_rifle_riven_averages()
        self.assertEqual(avg["Punch Through"], 3.0)  # meters, not 0.03
        self.assertEqual(avg["Damage to Grineer"], 0.51)  # +51%, not +0.51%

    def test_curse_column_skips_unrollable_traits(self) -> None:
        avg = load_rifle_riven_averages("curse_with_3_pos")
        self.assertNotIn("Heat", avg)
        self.assertNotIn("Punch Through", avg)
        self.assertAlmostEqual(avg["Damage"], -1.485)
        self.assertEqual(avg["Damage to Grineer"], -0.4)

    def test_two_positive_column_is_stronger(self) -> None:
        three = load_rifle_riven_averages("buff_3_pos_1_neg")
        two = load_rifle_riven_averages("buff_2_pos_1_neg")
        self.assertGreater(two[R_DAMAGE], three[R_DAMAGE])
        self.assertAlmostEqual(two[R_DAMAGE], 2.450, places=3)

    def test_combined_element_stats_constant_covers_spliced_traits(self) -> None:
        # Riven Splicer recipes (Update 44.1) all land in this set.
        self.assertEqual(
            COMBINED_ELEMENT_STATS,
            frozenset(("Blast", "Viral", "Magnetic", "Corrosive",
                       "Gas", "Radiation")))


class ElementCombineTests(unittest.TestCase):
    def test_toxin_combines_with_the_full_cold_into_viral(self) -> None:
        mix = combine_elements({R_BLAST: AVG_ELEMENT, R_TOXIN: AVG_ELEMENT})
        self.assertAlmostEqual(mix.factors["VIRAL"], 1.65 + AVG_ELEMENT)
        self.assertEqual(set(mix.status_types), {"ELEC", "BLAST", "VIRAL"})

    def test_heat_merges_into_blast_and_drops_the_cold(self) -> None:
        mix = combine_elements({R_BLAST: AVG_ELEMENT, R_HEAT: AVG_ELEMENT})
        self.assertNotIn("COLD", mix.factors)
        self.assertAlmostEqual(
            mix.factors["BLAST"], AVG_ELEMENT + 1.65 + AVG_ELEMENT)
        self.assertEqual(set(mix.status_types), {"ELEC", "BLAST"})

    def test_electricity_combines_into_magnetic(self) -> None:
        mix = combine_elements({R_BLAST: AVG_ELEMENT, R_ELEC: AVG_ELEMENT})
        self.assertAlmostEqual(mix.factors["MAG"], 1.0 + 1.65 + AVG_ELEMENT)
        self.assertNotIn("ELEC", mix.factors)
        self.assertEqual(set(mix.status_types), {"BLAST", "MAG"})

    def test_unpaired_cold_combines_with_innate_electricity(self) -> None:
        mix = combine_elements({R_BLAST: AVG_ELEMENT})
        self.assertAlmostEqual(mix.factors["MAG"], 2.65)
        self.assertNotIn("COLD", mix.factors)
        self.assertNotIn("ELEC", mix.factors)
        self.assertEqual(set(mix.status_types), {"BLAST", "MAG"})

    def test_two_base_elements_are_rejected_one_cold_source(self) -> None:
        with self.assertRaises(ValueError):
            combine_elements({R_TOXIN: 1.0, R_ELEC: 1.0})
        with self.assertRaises(ValueError):
            combine_elements({R_TOXIN: 1.0, R_HEAT: 1.0})

    def test_proc_weights_sum_to_one(self) -> None:
        mix = combine_elements({R_BLAST: AVG_ELEMENT, R_TOXIN: AVG_ELEMENT})
        self.assertAlmostEqual(sum(mix.weights().values()), 1.0)

    def test_zero_factor_types_are_excluded(self) -> None:
        # A layout without the Blast trait must not count a zero Blast
        # factor as a live GunCO status type.
        mix = combine_elements({R_TOXIN: AVG_ELEMENT})
        self.assertNotIn("BLAST", mix.status_types)
        self.assertEqual(set(mix.status_types), {"ELEC", "VIRAL"})
        self.assertAlmostEqual(mix.factors["BLAST"], 0.0)


class GuncoBonusTests(unittest.TestCase):
    def test_per_type_stack_math(self) -> None:
        # Two kill stacks at +40% per type = +80% per unique status type.
        self.assertAlmostEqual(gunco_bonus(3, 2), 2.4)
        self.assertAlmostEqual(gunco_bonus(4, 2), 3.2)
        # One stack is only +40% per type.
        self.assertAlmostEqual(gunco_bonus(3, 1), 1.2)

    def test_zero_stacks_or_types_give_no_bonus(self) -> None:
        self.assertEqual(gunco_bonus(3, 0), 0.0)
        self.assertEqual(gunco_bonus(0, 2), 0.0)

    def test_per_type_cap_cannot_be_exceeded(self) -> None:
        # The cap is already reached at the two-stack maximum; a hypothetical
        # third stack must not push a type past +80%.
        self.assertAlmostEqual(gunco_bonus(3, APTITUDE_STACK_CAP), 2.4)


class BuildTests(unittest.TestCase):
    def test_default_fire_rate_toxin_build_stats(self) -> None:
        b = build_alternox((R_BLAST, R_FIRE_RATE, R_TOXIN))
        self.assertAlmostEqual(b.crit_chance, 0.20 * 3.0)
        self.assertAlmostEqual(
            b.crit_multiplier, quantize_crit_multiplier(2.2) * 2.2)
        self.assertAlmostEqual(b.fire_rate, 5.33 * (1 - 0.20 + 0.675), places=4)
        self.assertAlmostEqual(b.multishot, 1.0 + 0.8 + 1.5)
        self.assertAlmostEqual(b.status_per_pellet, 0.40 * 1.8)
        self.assertAlmostEqual(b.base_bracket, 1.0 + 1.65)
        self.assertAlmostEqual(b.modded_base, 75.0 * 2.65)
        self.assertEqual(b.status_types, 3)

    def test_damage_positive_enters_the_serration_bracket(self) -> None:
        b = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        self.assertAlmostEqual(b.base_bracket, 1.0 + 1.65 + AVG_DAMAGE)
        self.assertAlmostEqual(b.modded_base, 75.0 * b.base_bracket)

    def test_gunco_resolves_to_multiply_from_the_catalog(self) -> None:
        b = build_alternox()
        self.assertEqual(b.co_behavior_mode, "multiply")
        self.assertEqual(b.co_scale, 1.0)
        self.assertAlmostEqual(b.gunco_multiplier(), 3.4)

    def test_blast_uses_average_element_value_by_default(self) -> None:
        b = build_alternox((R_BLAST, R_DAMAGE))
        self.assertAlmostEqual(b.riven[R_BLAST], AVG_ELEMENT)

    def test_blast_value_override(self) -> None:
        b = build_alternox((R_BLAST, R_DAMAGE), blast_value=0.60)
        self.assertEqual(b.riven[R_BLAST], 0.60)
        with self.assertRaises(ValueError):
            build_alternox((R_DAMAGE, R_TOXIN), blast_value=0.60)

    def test_unknown_stat_raises(self) -> None:
        with self.assertRaises(KeyError):
            build_alternox((R_BLAST, "Nonsense"))

    def test_stack_validation(self) -> None:
        with self.assertRaises(ValueError):
            build_alternox(galv_kill_stacks=3)
        with self.assertRaises(ValueError):
            build_alternox(chamber_stacks=CHAMBER_STACK_CAP + 1)


class AnalyticDpsTests(unittest.TestCase):
    def test_fire_rate_bonus_scales_burst_linearly(self) -> None:
        plain = expected_dps(build_alternox((R_BLAST, R_DAMAGE)))
        faster = expected_dps(build_alternox((R_BLAST, R_DAMAGE, R_FIRE_RATE)))
        self.assertAlmostEqual(faster.total_dps / plain.total_dps,
                               (1 - 0.2 + 0.675) / (1 - 0.2))

    def test_sustained_is_reload_discounted(self) -> None:
        r = expected_dps(build_alternox())
        self.assertLess(r.sustained_dps, r.total_dps)
        mag_life = MAGAZINE / build_alternox().fire_rate
        expected_uptime = mag_life / (mag_life + 1.8)
        self.assertAlmostEqual(
            r.sustained_dps / r.total_dps, expected_uptime, places=9)

    def test_ranking_order_and_length(self) -> None:
        reports = rank_riven_pairs()
        self.assertEqual(len(reports), len(RIVEN_PAIR_OPTIONS))
        bursts = [r.total_dps for r in reports]
        self.assertEqual(bursts, sorted(bursts, reverse=True))

    def test_cold_open_has_no_galvanized_bonus(self) -> None:
        reports = rank_riven_pairs(galv_kill_stacks=0)
        self.assertTrue(all(report.gunco_multiplier == 1.0 for report in reports))

    def test_additive_gunco_mode_is_weaker_than_multiply(self) -> None:
        build = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        multiplied = expected_dps(build)
        build.co_behavior_mode = "add"
        added = expected_dps(build)
        self.assertLess(added.total_dps, multiplied.total_dps)

    def test_viral_saturation_multiplier(self) -> None:
        build = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        saturated = expected_dps(build, viral_stacks=10)
        one_stack = expected_dps(build, viral_stacks=1)
        self.assertAlmostEqual(
            saturated.total_dps / one_stack.total_dps, 4.25 / 2.0, places=6)
        # Builds without Viral ignore the parameter.
        plain = expected_dps(
            build_alternox((R_BLAST, R_DAMAGE, R_FIRE_RATE)),
            viral_stacks=10)
        self.assertEqual(plain.viral_multiplier, 1.0)


class StochasticSimulationTests(unittest.TestCase):
    def test_seed_determinism(self) -> None:
        build = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        r1 = simulate(build, sim.alternox_dummy_factory(), seed=42)
        r2 = simulate(build, sim.alternox_dummy_factory(), seed=42)
        self.assertEqual(r1.ttk, r2.ttk)
        self.assertEqual(r1.shots, r2.shots)
        self.assertEqual(r1.pellets, r2.pellets)

    def test_dummy_is_plain_sp150_heavy_gunner(self) -> None:
        target = sim.alternox_dummy_factory()
        self.assertAlmostEqual(target.max_health, 286_139.57, places=1)
        self.assertEqual(target.max_armor, 2700.0)
        self.assertEqual(target.overguard, 0.0)
        self.assertIsInstance(target, AlternoxTarget)

    def test_viral_and_nonviral_trials_produce_finite_results(self) -> None:
        viral = run_trials((R_BLAST, R_DAMAGE, R_TOXIN), trials=60)
        plain = run_trials((R_BLAST, R_DAMAGE, R_FIRE_RATE), trials=60)
        self.assertTrue(math.isfinite(viral["ttk_median"]))
        self.assertTrue(math.isfinite(plain["ttk_median"]))
        self.assertGreater(viral["viral_median"], 0)

    def test_viral_and_electric_procs_are_recorded(self) -> None:
        build = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        result = simulate(build, sim.alternox_dummy_factory(), seed=7)
        self.assertGreater(result.viral_procs, 5)
        self.assertGreater(result.electric_procs, 0)
        self.assertEqual(result.final_viral_stacks, 10)

    def test_blast_fuse_detonation_fires_in_long_fights(self) -> None:
        build = build_alternox((R_BLAST, R_HEAT, R_DAMAGE))
        result = simulate(build, sim.alternox_dummy_factory(), seed=7)
        self.assertGreater(result.blast_detonations, 1)
        self.assertTrue(math.isfinite(result.ttk))

    def test_ten_blast_stacks_detonate_immediately(self) -> None:
        original_fuse = sim.BLAST_FUSE
        sim.BLAST_FUSE = 9_999.0  # fuses can never mature
        try:
            build = build_alternox((R_BLAST, R_STATUS, R_DAMAGE))
            result = simulate(build, sim.alternox_dummy_factory(), seed=11)
            self.assertGreaterEqual(result.blast_detonations, 1)
        finally:
            sim.BLAST_FUSE = original_fuse
        self.assertEqual(BLAST_FUSE, original_fuse)

    def test_reload_happens_past_one_magazine(self) -> None:
        # Magazine life is ~9.8 s; the weak Heat build needs far longer.
        build = build_alternox((R_BLAST, R_HEAT, R_DAMAGE))
        result = simulate(build, sim.alternox_dummy_factory(), seed=7)
        self.assertGreaterEqual(result.reloads, 1)

    def test_magnetic_proc_state_prunes_over_time(self) -> None:
        # Unpaired Cold combines with innate Electricity into Magnetic.
        build = build_alternox((R_BLAST, R_DAMAGE, R_FIRE_RATE))
        target = sim.alternox_dummy_factory()
        simulate(build, target, seed=3, max_time=8.0)
        self.assertIsInstance(target.mag_expiries, list)
        self.assertTrue(all(expiry > 2.0 for expiry in target.mag_expiries))

    def test_cold_open_trial_is_slower_than_stacked(self) -> None:
        stacked = run_trials((R_BLAST, R_DAMAGE, R_TOXIN), trials=40,
                             galv_kill_stacks=APTITUDE_STACK_CAP)
        cold_open = run_trials((R_BLAST, R_DAMAGE, R_TOXIN), trials=40,
                               galv_kill_stacks=0)
        self.assertGreater(cold_open["ttk_median"], stacked["ttk_median"])

    def test_status_above_100_percent_grants_extra_procs(self) -> None:
        # Status Chance Riven: 0.40 x (1 + 0.8 + 1.013) = 1.1252 procs/pellet,
        # so total procs must exceed the number of pellets fired (impossible
        # under the old single-roll-per-pellet model).
        build = build_alternox((R_BLAST, R_STATUS, R_TOXIN))
        self.assertGreater(build.status_per_pellet, 1.0)
        target = sim.alternox_dummy_factory()
        result = simulate(build, target, seed=11, max_time=4.0)
        total_procs = (result.viral_procs + result.electric_procs
                       + result.blast_procs + len(target.cold_expiries))
        self.assertGreater(total_procs, result.pellets)

    def test_fatal_blast_stops_remaining_status_procs(self) -> None:
        from modules.kuva_nukor_sim import BlastProc

        build = dataclasses.replace(build_alternox(), multishot=1.0, crit_chance=0.0,
                                    status_per_pellet=3.0,
                                    mix=sim.ElementMix({"BLAST": 1.0}, ("BLAST",)))
        target = AlternoxTarget(1000, 0, boss=True)
        target.blast_stacks.extend(BlastProc(0, 1.5, 10000, 1) for _ in range(3))
        result = simulate(build, target, seed=1, max_time=0.001)
        self.assertLessEqual(target.health, 0)
        self.assertEqual(result.blast_detonations, 1)
        self.assertEqual(result.blast_procs, 1)
        self.assertEqual(target.blast_stacks, [])

    def test_magnetic_stacks_are_capped_at_ten(self) -> None:
        build = build_alternox((R_BLAST, R_ELEC, R_DAMAGE))
        target = sim.alternox_dummy_factory()
        simulate(build, target, seed=5, max_time=8.0)
        self.assertLessEqual(len(target.mag_expiries), 10)

    def test_direct_damage_quantizes_pre_crit(self) -> None:
        # Pinned convention: quantization happens on the pre-crit type
        # value and the crit multiplier is applied afterwards.
        from modules.status_damage import wiki_quantized_damage
        build = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        co_bonus = gunco_bonus(build.status_types, build.galv_kill_stacks)
        quantized_pre_crit = sum(
            wiki_quantized_damage(
                sim.apply_co(75.0, co_bonus, build.base_bracket * factor,
                             1.0, mode=build.co_behavior_mode,
                             scale=build.co_scale),
                build.modded_base)
            for factor in build.mix.factors.values())
        raw_pre_crit = (
            75.0 * build.base_bracket * build.mix.total_factor
            * (1.0 + co_bonus))
        # Quantization can only round each type to the nearest 1/32 step.
        self.assertGreater(quantized_pre_crit, 0.0)
        self.assertLess(abs(raw_pre_crit - quantized_pre_crit),
                        build.modded_base / 32.0 * len(build.mix.factors))
        # The crit multiplier lands after quantization, so it must be an
        # exact scalar of the quantized pre-crit total.
        self.assertAlmostEqual(
            quantized_pre_crit * build.crit_multiplier
            / quantized_pre_crit,
            build.crit_multiplier)


if __name__ == "__main__":
    unittest.main()


class ColdCriticalDamageTests(unittest.TestCase):
    """Freeze stacks must reach the crit factor (wiki Damage/Cold_Damage)."""

    def test_cold_stacks_raise_every_critical_hit(self) -> None:
        build = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        target = sim.alternox_dummy_factory()
        plain = [sim._crit_factor(random.Random(seed), build, target, 0.0)
                 for seed in range(200)]

        target.add_cold(0.0, 6.0)
        self.assertEqual(target.cold_stacks(0.0), 1)
        primed = [sim._crit_factor(random.Random(seed), build, target, 0.0)
                  for seed in range(200)]

        # Cold adds a flat +0.10x additive to Critical Damage, so it only
        # moves the crit multiplier: a non-crit hit stays at 1.0.
        self.assertIn(1.0, plain)
        for before, after in zip(plain, primed, strict=True):
            expected = 1.0 if before == 1.0 else before + 0.10
            self.assertAlmostEqual(after, expected, places=12)

    def test_crit_tiers_continue_above_one_hundred_percent(self) -> None:
        base = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN))
        build = dataclasses.replace(base, crit_chance=2.5)
        target = sim.alternox_dummy_factory()
        values = {sim._crit_factor(random.Random(seed), build, target, 0.0)
                  for seed in range(400)}
        # 250% crit chance: tier 2 is guaranteed, tier 3 rolls the remainder.
        self.assertEqual(values, {1.0 + 2.0 * (build.crit_multiplier - 1.0),
                                  1.0 + 3.0 * (build.crit_multiplier - 1.0)})
