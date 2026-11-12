"""Tests for the Corinth Prime Riven choice simulation.

The numbers pinned here are model output under the repository's audited core
(armor curve, 1/32 quantization, critical tiers, status stack rules). They are
regression pins, not in-game measurements.
"""
from __future__ import annotations

import io
import math
import unittest
from contextlib import redirect_stdout

import modules.corinth_prime_sim as sim
from modules.constants import FACTION_MULTIPLIERS
from modules.corinth_prime_sim import (
    ARMOR_CURVE_AUDITED,
    ARMOR_CURVE_LINEAR,
    BASE_CRIT_CHANCE,
    BASE_CRIT_MULTIPLIER,
    BASE_FIRE_RATE,
    BASE_STATUS_CHANCE,
    CORROSIVE_CAP,
    CORROSIVE_DURATION,
    DEFAULT_CURSE,
    GALVANIZED_HELL_MULTISHOT,
    MAGAZINE,
    PELLET_DAMAGE,
    PELLETS,
    PRIMARY_OVERCHARGE_MULTISHOT,
    PUNCTURE_CAP,
    PUNCTURE_CRIT_PER_STACK,
    RELOAD_TIME,
    SUPPORTED_PROC_TYPES,
    WEAPON_NAME,
    CorinthTarget,
    DoTProc,
    RivenRoll,
    build_corinth,
    candidate_rolls,
    corinth_dummy_factory,
    corrosive_armor_factor,
    equivalent_armor,
    fixed_effects,
    load_shotgun_riven_averages,
    rank_rolls,
    riven_effects,
    run_trials,
    simulate,
    steady_state_dps,
    supports_simulation,
    viral_health_multiplier,
)
from modules.crit import quantize_crit_multiplier

BEST_THREE = ("Damage", "Critical Damage", "Damage to Grineer")
BEST_SPLICED = ("Corrosive", "Damage", "Damage to Grineer")


class RivenTableTests(unittest.TestCase):
    def test_shotgun_table_values(self) -> None:
        averages = load_shotgun_riven_averages("buff_3_pos_1_neg")
        self.assertAlmostEqual(averages["Damage"], 1.853, places=6)
        self.assertAlmostEqual(averages["Critical Chance"], 1.013, places=6)
        self.assertAlmostEqual(averages["Critical Damage"], 1.013, places=6)
        self.assertAlmostEqual(averages["Multishot"], 1.347, places=6)
        self.assertAlmostEqual(averages["Status Duration"], 1.125, places=6)
        # Faction values are bonus multipliers (+51%), not percentages.
        self.assertAlmostEqual(averages["Damage to Grineer"], 0.51, places=6)
        # Values are fractions, and plain units keep their own scale.
        self.assertAlmostEqual(averages["Punch Through"], 3.0, places=6)

    def test_two_positive_layout_is_larger(self) -> None:
        two = load_shotgun_riven_averages("buff_2_pos_1_neg")
        self.assertAlmostEqual(two["Damage"], 2.446, places=6)
        self.assertAlmostEqual(two["Critical Chance"], 1.337, places=6)
        self.assertAlmostEqual(two["Damage to Grineer"], 0.67, places=6)

    def test_curse_columns(self) -> None:
        curses = load_shotgun_riven_averages("curse_with_3_pos")
        self.assertAlmostEqual(curses["Ammo Maximum"], -0.81, places=6)
        self.assertAlmostEqual(curses["Critical Chance"], -0.81, places=6)
        # Recoil is stored as the penalty it applies to the weapon.
        self.assertAlmostEqual(curses["Weapon Recoil"], 0.81, places=6)
        two = load_shotgun_riven_averages("curse_with_2_pos")
        self.assertAlmostEqual(two["Multishot"], -0.711, places=6)

    def test_shotgun_table_has_no_zoom_trait(self) -> None:
        # The rifle and pistol tables carry Zoom; the shotgun table does not.
        self.assertNotIn("Zoom", load_shotgun_riven_averages("buff_3_pos_1_neg"))
        self.assertNotIn("Zoom", load_shotgun_riven_averages("curse_with_3_pos"))

    def test_cached_table_is_returned_as_a_fresh_copy(self) -> None:
        first = load_shotgun_riven_averages("buff_3_pos_1_neg")
        first["Damage"] = -99.0
        second = load_shotgun_riven_averages("buff_3_pos_1_neg")
        self.assertAlmostEqual(second["Damage"], 1.853, places=6)


class RivenRollTests(unittest.TestCase):
    def test_layout_is_inferred_from_positives_and_curse(self) -> None:
        self.assertEqual(RivenRoll(("Damage", "Multishot")).value_column, "buff_2_pos")
        self.assertEqual(RivenRoll(("Damage", "Multishot"), "Ammo Maximum").value_column,
                         "buff_2_pos_1_neg")
        self.assertEqual(RivenRoll(("Damage", "Multishot", "Critical Damage")).value_column,
                         "buff_3_pos")
        self.assertEqual(
            RivenRoll(("Damage", "Multishot", "Critical Damage"), DEFAULT_CURSE).value_column,
            "buff_3_pos_1_neg")

    def test_spliced_flag(self) -> None:
        self.assertFalse(RivenRoll(BEST_THREE, DEFAULT_CURSE).spliced)
        self.assertTrue(RivenRoll(BEST_SPLICED, DEFAULT_CURSE).spliced)

    def test_invalid_rolls_are_rejected(self) -> None:
        cases = [
            (("Damage",), None),                                    # too few
            (("Damage", "Multishot", "Critical Damage", "Toxin"), None),  # too many
            (("Damage", "Not A Stat"), None),                       # unknown
            (("Damage", "Damage", "Toxin"), None),                  # duplicate
            (("Corrosive", "Viral", "Damage"), None),               # two splices
            (("Damage", "Multishot", "Toxin"), "Damage"),           # curse repeats
            (("Damage", "Multishot", "Toxin"), "Zoom"),             # no such curse
        ]
        for positives, curse in cases:
            with self.subTest(positives=positives, curse=curse):
                with self.assertRaises(ValueError):
                    RivenRoll(positives, curse)

    def test_riven_effects_use_element_value_for_spliced_traits(self) -> None:
        # A spliced trait inherits the element value of the same layout, so it
        # is worth exactly what a single element positive is worth.
        spliced = riven_effects(RivenRoll(("Viral", "Damage"), DEFAULT_CURSE))
        plain = riven_effects(RivenRoll(("Toxin", "Damage"), DEFAULT_CURSE))
        self.assertAlmostEqual(spliced["VIRAL"], plain["TOXIN"], places=9)

    def test_curse_is_applied_with_its_recorded_sign(self) -> None:
        effects = riven_effects(RivenRoll(("Damage", "Multishot"), "Ammo Maximum"))
        self.assertLess(effects["AMMO_MAXIMUM"], 0.0)
        recoil = riven_effects(RivenRoll(("Damage", "Multishot"), "Weapon Recoil"))
        self.assertGreater(recoil["RECOIL"], 0.0)


class BuildTests(unittest.TestCase):
    def test_baseline_stats(self) -> None:
        build = build_corinth(None)
        self.assertAlmostEqual(build.multishot,
                               PELLETS * (1 + GALVANIZED_HELL_MULTISHOT
                                          + PRIMARY_OVERCHARGE_MULTISHOT),
                               places=9)
        self.assertAlmostEqual(build.multishot, 34.8, places=9)
        self.assertAlmostEqual(build.crit_chance, BASE_CRIT_CHANCE * 1.90, places=9)
        self.assertAlmostEqual(build.crit_multiplier,
                               quantize_crit_multiplier(BASE_CRIT_MULTIPLIER) * 2.10,
                               places=9)
        self.assertAlmostEqual(build.status_chance, BASE_STATUS_CHANCE * 1.60, places=9)
        self.assertAlmostEqual(build.modded_base, PELLET_DAMAGE * 3.40, places=9)
        self.assertAlmostEqual(build.fire_rate, BASE_FIRE_RATE, places=9)
        self.assertEqual(build.magazine, MAGAZINE)
        self.assertAlmostEqual(build.reload_time, RELOAD_TIME, places=9)
        self.assertAlmostEqual(build.faction_bonus, 0.0, places=9)

    def test_baseline_per_pellet_damage(self) -> None:
        build = build_corinth(None)
        self.assertAlmostEqual(build.hud_by_type["IMPACT"], 85.68, places=6)
        self.assertAlmostEqual(build.hud_by_type["PUNC"], 128.52, places=6)
        self.assertAlmostEqual(build.hud_by_type["SLASH"], 91.80, places=6)
        self.assertAlmostEqual(build.hud_by_type["VIRAL"], 688.50, places=6)
        self.assertAlmostEqual(build.hud_by_type["ELEC"], 504.90, places=6)
        self.assertAlmostEqual(sum(build.hud_by_type.values()), 1499.4, places=6)

    def test_multishot_is_capped_by_the_two_bonuses_not_multiplied(self) -> None:
        # Galvanized Hell and Primary Overcharge are additive, and multishot
        # scales the six pellets rather than adding projectiles one by one.
        build = build_corinth(RivenRoll(("Multishot", "Damage"), DEFAULT_CURSE))
        expected = PELLETS * (1 + GALVANIZED_HELL_MULTISHOT
                              + PRIMARY_OVERCHARGE_MULTISHOT + 1.778)
        self.assertAlmostEqual(build.multishot, expected, places=9)

    def test_element_hierarchy_follows_slot_order(self) -> None:
        toxin = build_corinth(RivenRoll(("Toxin", "Damage"), DEFAULT_CURSE))
        corrosive = build_corinth(RivenRoll(("Corrosive", "Damage"), DEFAULT_CURSE))
        electricity = build_corinth(RivenRoll(("Electricity", "Damage"), DEFAULT_CURSE))
        heat = build_corinth(RivenRoll(("Heat", "Damage"), DEFAULT_CURSE))
        baseline = build_corinth(None)

        def factor(build, kind) -> float:
            return build.hud_by_type[kind] / build.modded_base

        # A Toxin (or Cold, or spliced Viral) positive pairs with the fixed
        # Cold: the Viral factor grows and the Electricity factor is untouched.
        self.assertGreater(factor(toxin, "VIRAL"), factor(baseline, "VIRAL"))
        self.assertAlmostEqual(factor(toxin, "ELEC"), factor(baseline, "ELEC"),
                               places=6)
        # A spliced Corrosive trait is pre-combined and joins nothing.
        self.assertIn("CORR", corrosive.hud_by_type)
        self.assertAlmostEqual(factor(corrosive, "VIRAL"), factor(baseline, "VIRAL"),
                               places=6)
        self.assertAlmostEqual(factor(corrosive, "ELEC"), factor(baseline, "ELEC"),
                               places=6)
        self.assertGreater(factor(corrosive, "CORR"), 0.0)
        # Electricity stacks into the Charged Shell group.
        self.assertGreater(factor(electricity, "ELEC"), factor(baseline, "ELEC"))
        # Heat pairs with the fixed Electricity into Radiation, so the
        # Electricity DoT disappears from that layout.
        self.assertIn("RAD", heat.hud_by_type)
        self.assertNotIn("ELEC", heat.hud_by_type)

    def test_cannonade_locks_fire_rate(self) -> None:
        baseline = build_corinth(None)
        cursed = build_corinth(RivenRoll(("Damage", "Critical Damage"),
                                         "Fire Rate / Attack Speed"))
        boosted = build_corinth(RivenRoll(("Damage", "Fire Rate / Attack Speed"),
                                          "Ammo Maximum"))
        self.assertAlmostEqual(cursed.fire_rate, baseline.fire_rate, places=9)
        self.assertAlmostEqual(boosted.fire_rate, baseline.fire_rate, places=9)

    def test_curse_arithmetic(self) -> None:
        cursed = build_corinth(RivenRoll(("Critical Damage", "Damage to Grineer"),
                                         "Damage"))
        curses = load_shotgun_riven_averages("curse_with_2_pos")
        expected = PELLET_DAMAGE * (1.0 + fixed_effects()["TRUE"] + curses["Damage"])
        self.assertAlmostEqual(cursed.modded_base, expected, places=9)
        self.assertLess(cursed.modded_base,
                        build_corinth(RivenRoll(("Critical Damage", "Damage to Grineer"),
                                                "Ammo Maximum")).modded_base)

        faster_reload = build_corinth(RivenRoll(("Damage", "Critical Damage"),
                                                "Reload Speed"))
        self.assertAlmostEqual(faster_reload.reload_time,
                               RELOAD_TIME / (1.0 + curses["Reload Speed"]), places=9)
        smaller_magazine = build_corinth(RivenRoll(("Damage", "Critical Damage"),
                                                   "Magazine Capacity"))
        self.assertEqual(smaller_magazine.magazine,
                         math.floor(MAGAZINE * (1.0 + curses["Magazine Capacity"])))

    def test_multishot_curse_removes_pellets(self) -> None:
        cursed = build_corinth(RivenRoll(("Damage", "Critical Damage"), "Multishot"))
        self.assertAlmostEqual(cursed.multishot,
                               PELLETS * (1 + GALVANIZED_HELL_MULTISHOT
                                          + PRIMARY_OVERCHARGE_MULTISHOT - 0.711),
                               places=9)

    def test_supported_proc_types(self) -> None:
        self.assertIn("CORR", SUPPORTED_PROC_TYPES)
        self.assertNotIn("BLAST", SUPPORTED_PROC_TYPES)
        self.assertTrue(supports_simulation(build_corinth(None)))
        self.assertFalse(supports_simulation(
            build_corinth(RivenRoll(("Blast", "Damage"), DEFAULT_CURSE))))

    def test_simulate_rejects_unmodelled_proc_types(self) -> None:
        build = build_corinth(RivenRoll(("Gas", "Damage"), DEFAULT_CURSE))
        with self.assertRaises(ValueError) as caught:
            simulate(build, corinth_dummy_factory())
        self.assertIn("GAS", str(caught.exception))


class StackRuleTests(unittest.TestCase):
    def test_corrosive_armor_factor(self) -> None:
        self.assertAlmostEqual(corrosive_armor_factor(0), 1.0, places=12)
        self.assertAlmostEqual(corrosive_armor_factor(1), 1.0 - 0.26, places=12)
        self.assertAlmostEqual(corrosive_armor_factor(10), 0.2, places=12)
        # Beyond the cap the factor is clamped, not extrapolated.
        self.assertAlmostEqual(corrosive_armor_factor(15), 0.2, places=12)

    def test_viral_health_multiplier(self) -> None:
        self.assertAlmostEqual(viral_health_multiplier(0), 1.0, places=12)
        self.assertAlmostEqual(viral_health_multiplier(1), 2.0, places=12)
        self.assertAlmostEqual(viral_health_multiplier(10), 4.25, places=12)
        self.assertAlmostEqual(viral_health_multiplier(14), 4.25, places=12)

    def test_target_armor_follows_corrosive_stacks(self) -> None:
        target = CorinthTarget(286139.57, 2700.0, 0.0)
        self.assertAlmostEqual(target.current_armor(0.0, 0.5), 2700.0, places=9)
        target.add_corrosive(0.0, CORROSIVE_DURATION)
        self.assertEqual(target.corrosive_stacks(0.5), 1)
        self.assertAlmostEqual(target.current_armor(0.5, 0.5), 2700.0 * 0.74, places=9)
        # The stack expires after its own duration.
        self.assertEqual(target.corrosive_stacks(CORROSIVE_DURATION + 0.1), 0)
        self.assertAlmostEqual(target.current_armor(CORROSIVE_DURATION + 0.1, 0.5),
                               2700.0, places=9)

    def test_corrosive_stacks_are_capped(self) -> None:
        target = CorinthTarget(100.0, 2700.0, 0.0)
        for index in range(CORROSIVE_CAP + 5):
            target.add_corrosive(index * 0.1, CORROSIVE_DURATION)
        self.assertEqual(target.corrosive_stacks(1.0), CORROSIVE_CAP)

    def test_linear_armor_switch_matches_the_alternative_reading(self) -> None:
        # Both armor curves agree at the 2,700 cap and at zero.
        self.assertAlmostEqual(equivalent_armor(2700.0), 2700.0, places=9)
        self.assertEqual(equivalent_armor(0.0), 0.0)
        # Below the cap the mapping keeps the surviving damage fraction equal
        # to 300 / (armor + 300).
        from modules.enemy_scaling import enemy_armor_damage_multiplier
        for armor in (200.0, 1350.0, 1998.0):
            mapped = equivalent_armor(armor)
            self.assertAlmostEqual(enemy_armor_damage_multiplier(mapped),
                                   300.0 / (armor + 300.0), places=9)

    def test_linear_curve_target_uses_the_mapped_armor(self) -> None:
        audited = CorinthTarget(1000.0, 2700.0, 0.0)
        linear = CorinthTarget(1000.0, 2700.0, 0.0, armor_curve=ARMOR_CURVE_LINEAR)
        for target in (audited, linear):
            target.add_corrosive(0.0, CORROSIVE_DURATION)
        self.assertAlmostEqual(audited.current_armor(0.1, 0.5), 1998.0, places=9)
        self.assertGreater(linear.current_armor(0.1, 0.5), 1998.0)
        with self.assertRaises(ValueError):
            CorinthTarget(1000.0, 2700.0, 0.0, armor_curve="nonsense")

    def test_dot_proc_clock(self) -> None:
        electric = DoTProc(2.0, 100.0, 1.0, first_tick=0.0)
        self.assertAlmostEqual(electric.next_tick, 2.0)
        self.assertAlmostEqual(electric.last_tick(6.0), 7.0)
        bleed = DoTProc(2.0, 100.0, 1.0, first_tick=1.0)
        self.assertAlmostEqual(bleed.next_tick, 3.0)
        self.assertAlmostEqual(bleed.last_tick(6.0), 8.0)

    def test_puncture_bonus_constants(self) -> None:
        self.assertAlmostEqual(PUNCTURE_CRIT_PER_STACK, 0.05)
        self.assertEqual(PUNCTURE_CAP, 5)


class AnalyticDpsTests(unittest.TestCase):
    def test_baseline_dps_is_pinned(self) -> None:
        report = steady_state_dps(build_corinth(None))
        self.assertAlmostEqual(report.total_dps, 135928.0849, places=3)
        self.assertAlmostEqual(report.direct_dps, 122103.3513, places=3)
        self.assertAlmostEqual(report.slash_dps, 4485.4292, places=3)
        self.assertAlmostEqual(report.electric_dps, 9339.3044, places=3)
        self.assertAlmostEqual(report.viral_multiplier, 4.25, places=12)
        self.assertAlmostEqual(report.armour, 2700.0, places=9)

    def test_best_three_positive_roll_is_pinned(self) -> None:
        report = steady_state_dps(build_corinth(RivenRoll(BEST_THREE, DEFAULT_CURSE)))
        self.assertAlmostEqual(report.total_dps, 476155.8799, places=3)
        self.assertAlmostEqual(report.sustained_dps, 392705.8787, places=3)

    def test_viral_saturation_scales_direct_damage_only(self) -> None:
        build = build_corinth(None)
        saturated = steady_state_dps(build, viral_stacks=10)
        fresh = steady_state_dps(build, viral_stacks=0)
        self.assertAlmostEqual(fresh.total_dps * 4.25, saturated.total_dps, places=6)

    def test_corrosive_saturation_lowers_armor(self) -> None:
        build = build_corinth(None)
        stripped = steady_state_dps(build, corrosive_stacks=CORROSIVE_CAP)
        self.assertAlmostEqual(stripped.armour, 540.0, places=9)
        self.assertGreater(stripped.total_dps, steady_state_dps(build).total_dps * 5)

    def test_analytic_ranking_orders_the_expected_rolls(self) -> None:
        ranked = rank_rolls(candidate_rolls(3))
        labels = [report.label for report in ranked[:4]]
        self.assertEqual(labels[0], "+Damage / Critical Damage / Damage to Grineer, "
                                   "-Ammo Maximum")
        self.assertEqual(labels[1], "+Damage / Critical Chance / Damage to Grineer, "
                                   "-Ammo Maximum")
        # A spliced Corrosive trait costs one positive line: its steady-state
        # DPS is lower even though it strips armor once the fight starts.
        corrosive = steady_state_dps(build_corinth(RivenRoll(BEST_SPLICED,
                                                            DEFAULT_CURSE)))
        self.assertLess(corrosive.total_dps, ranked[0].total_dps)

    def test_sustained_dps_applies_magazine_uptime(self) -> None:
        build = build_corinth(None)
        report = steady_state_dps(build)
        firing = MAGAZINE / BASE_FIRE_RATE
        self.assertAlmostEqual(report.sustained_dps,
                               report.total_dps * firing / (firing + RELOAD_TIME),
                               places=6)

    def test_every_candidate_roll_builds(self) -> None:
        for positives in (2, 3):
            rolls = candidate_rolls(positives)
            for roll in rolls[:40]:
                with self.subTest(roll=roll.label()):
                    build = build_corinth(roll)
                    self.assertGreater(sum(build.hud_by_type.values()), 0.0)


class CandidateSweepTests(unittest.TestCase):
    def test_candidate_counts(self) -> None:
        stats = len(sim.DAMAGE_STATS)
        self.assertEqual(len(candidate_rolls(3)), math.comb(stats, 3)
                         + len(sim.COMBINED_ELEMENT_STATS) * math.comb(stats, 2))
        self.assertEqual(len(candidate_rolls(2)), math.comb(stats, 2)
                         + len(sim.COMBINED_ELEMENT_STATS) * stats)

    def test_candidates_exclude_free_traits_and_use_the_default_curse(self) -> None:
        for roll in candidate_rolls(3):
            self.assertEqual(roll.curse, DEFAULT_CURSE)
            for stat in roll.positives:
                self.assertIn(stat, sim.DAMAGE_STATS + tuple(sim.COMBINED_ELEMENT_STATS))

    def test_spliced_candidates_exist_for_every_combined_element(self) -> None:
        spliced = {roll.positives[0] for roll in candidate_rolls(3) if roll.spliced}
        self.assertEqual(spliced, set(sim.COMBINED_ELEMENT_STATS))


class SimulationTests(unittest.TestCase):
    def test_trial_kills_the_dummy(self) -> None:
        build = build_corinth(RivenRoll(BEST_THREE, DEFAULT_CURSE))
        result = simulate(build, corinth_dummy_factory(), seed=1)
        self.assertTrue(math.isfinite(result.ttk))
        self.assertGreater(result.pellets, 0)
        self.assertGreater(result.viral_procs, 0)
        self.assertLessEqual(result.final_viral_stacks, 10)

    def test_kill_times_sit_on_the_trigger_clock(self) -> None:
        build = build_corinth(RivenRoll(BEST_THREE, DEFAULT_CURSE))
        step = 1.0 / BASE_FIRE_RATE
        for seed in range(5):
            result = simulate(build, corinth_dummy_factory(), seed=seed)
            pulls = result.ttk / step
            self.assertAlmostEqual(pulls, round(pulls), places=6)

    def test_same_seed_is_reproducible(self) -> None:
        build = build_corinth(RivenRoll(BEST_SPLICED, DEFAULT_CURSE))
        first = simulate(build, corinth_dummy_factory(), seed=42)
        second = simulate(build, corinth_dummy_factory(), seed=42)
        self.assertEqual(first, second)
        # A different seed changes the pellet/status draws even when the kill
        # still lands on the same trigger pull.
        other = simulate(build, corinth_dummy_factory(), seed=43)
        self.assertNotEqual((first.ttk, first.pellets, first.viral_procs),
                            (other.ttk, other.pellets, other.viral_procs))

    def test_corrosive_build_strips_armor_in_a_trial(self) -> None:
        build = build_corinth(RivenRoll(BEST_SPLICED, DEFAULT_CURSE))
        result = simulate(build, corinth_dummy_factory(), seed=7)
        self.assertGreater(result.corrosive_procs, 0)
        self.assertLess(result.final_armor, 2700.0)
        self.assertAlmostEqual(
            result.final_armor,
            2700.0 * corrosive_armor_factor(result.final_corrosive_stacks),
            places=6)

    def test_armor_curve_sensitivity_slows_the_corrosive_roll(self) -> None:
        roll = RivenRoll(BEST_SPLICED, DEFAULT_CURSE)
        curated = run_trials(roll, trials=60, base_seed=99,
                             armor_curve=ARMOR_CURVE_AUDITED)
        linear = run_trials(roll, trials=60, base_seed=99,
                            armor_curve=ARMOR_CURVE_LINEAR)
        self.assertLessEqual(curated["ttk_mean"], linear["ttk_mean"])

    def test_stronger_build_kills_faster(self) -> None:
        weak = run_trials(None, trials=40, base_seed=5)
        strong = run_trials(RivenRoll(BEST_THREE, DEFAULT_CURSE), trials=40,
                            base_seed=5)
        self.assertLess(strong["ttk_mean"], weak["ttk_mean"])

    def test_run_trials_validates_and_counts(self) -> None:
        with self.assertRaises(ValueError):
            run_trials(None, trials=0)
        result = run_trials(RivenRoll(BEST_THREE, DEFAULT_CURSE), trials=5)
        self.assertEqual(result["trials_attempted"], 5)
        self.assertEqual(result["trials"] + result["timed_out"], 5)
        self.assertTrue(math.isfinite(result["ttk_median"]))
        self.assertEqual(result["corrosive_median"], 0.0)

    def test_rank_by_ttk_skips_unmodelled_procs(self) -> None:
        rolls = [RivenRoll(("Blast", "Damage"), DEFAULT_CURSE),
                 RivenRoll(BEST_THREE, DEFAULT_CURSE)]
        results = sim.rank_by_ttk(rolls, trials=4)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["roll"], RivenRoll(BEST_THREE, DEFAULT_CURSE))


class TargetTests(unittest.TestCase):
    def test_plain_factory_has_no_overguard(self) -> None:
        target = corinth_dummy_factory()
        self.assertEqual(target.overguard_max, 0.0)
        self.assertAlmostEqual(target.max_health, 286139.57, places=2)
        self.assertAlmostEqual(target.max_armor, 2700.0)

    def test_eximus_factory_adds_overguard_and_eximus_health(self) -> None:
        target = corinth_dummy_factory(target=sim.TARGET_EXIMUS)
        self.assertAlmostEqual(target.overguard_max, 269918.97, places=2)
        self.assertAlmostEqual(target.max_health, 1716837.41, places=2)
        self.assertAlmostEqual(target.max_armor, 2700.0)

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            corinth_dummy_factory(target="sortie")

    def test_overguard_absorbs_before_health(self) -> None:
        target = corinth_dummy_factory(target=sim.TARGET_EXIMUS)
        health = target.health
        target.absorb({"VIRAL": 1000.0}, 0.0, sim.HEAT_RAMP_INTERVAL,
                      faction_type_modifiers=FACTION_MULTIPLIERS["Grineer"])
        self.assertAlmostEqual(target.health, health, places=6)
        self.assertAlmostEqual(target.overguard, 269918.97 - 1000.0, places=2)

    def test_overguard_is_neutral_to_grineer_type_modifiers(self) -> None:
        # Grineer Corrosive is x1.5 on the health layer; Overguard is neutral.
        target = corinth_dummy_factory(target=sim.TARGET_EXIMUS)
        target.absorb({"CORR": 500.0}, 0.0, sim.HEAT_RAMP_INTERVAL,
                      faction_type_modifiers=FACTION_MULTIPLIERS["Grineer"])
        self.assertAlmostEqual(target.overguard, 269918.97 - 500.0, places=2)

    def test_eximus_dummy_dies_and_reports_the_break(self) -> None:
        build = build_corinth(RivenRoll(BEST_SPLICED, DEFAULT_CURSE))
        target = corinth_dummy_factory(target=sim.TARGET_EXIMUS)
        result = simulate(build, target, seed=3)
        self.assertTrue(math.isfinite(result.ttk))
        self.assertTrue(math.isfinite(result.overguard_break))
        self.assertLessEqual(result.overguard_break, result.ttk)
        self.assertEqual(target.overguard, 0.0)
        self.assertLessEqual(target.health, 0.0)

    def test_only_the_unrivend_build_needs_a_second_pull_to_break(self) -> None:
        step = 1.0 / BASE_FIRE_RATE
        weak = simulate(build_corinth(None),
                        corinth_dummy_factory(target=sim.TARGET_EXIMUS), seed=1)
        self.assertAlmostEqual(weak.overguard_break, step, places=6)
        strong = simulate(build_corinth(RivenRoll(BEST_SPLICED, DEFAULT_CURSE)),
                          corinth_dummy_factory(target=sim.TARGET_EXIMUS), seed=1)
        self.assertAlmostEqual(strong.overguard_break, 0.0, places=6)

    def test_run_trials_reports_overguard_telemetry(self) -> None:
        eximus = run_trials(None, trials=2, target=sim.TARGET_EXIMUS)
        self.assertGreater(eximus["overguard_max"], 0.0)
        self.assertGreater(eximus["overguard_break_median"], 0.0)
        self.assertEqual(eximus["target"], sim.TARGET_EXIMUS)
        plain = run_trials(None, trials=2)
        self.assertEqual(plain["overguard_max"], 0.0)
        self.assertEqual(plain["overguard_break_median"], 0.0)
        self.assertEqual(plain["target"], sim.TARGET_PLAIN)

    def test_eximus_target_is_slower_than_the_plain_one(self) -> None:
        roll = RivenRoll(BEST_SPLICED, DEFAULT_CURSE)
        plain = run_trials(roll, trials=40, base_seed=11)
        eximus = run_trials(roll, trials=40, base_seed=11,
                            target=sim.TARGET_EXIMUS)
        self.assertLess(plain["ttk_mean"], eximus["ttk_mean"])

    def test_dot_seeds_exclude_the_crit_factor(self) -> None:
        # Regression: the proc seed must not already contain the pellet's crit
        # multiplier, because every tick applies ``seed * crit_factor`` once.
        build = build_corinth(RivenRoll(BEST_SPLICED, DEFAULT_CURSE))
        expected = build.modded_base * (1.0 + build.faction_bonus)
        procs = []
        for seed in range(6):
            target = corinth_dummy_factory()
            simulate(build, target, seed=seed)
            procs.extend(target.electric_procs)
            procs.extend(target.bleed_procs)
        self.assertTrue(procs)
        for proc in procs:
            self.assertAlmostEqual(proc.seed, expected, places=6)


class CliTests(unittest.TestCase):
    def test_cli_prints_tables(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            sim.main(["--trials", "3", "--top", "2"])
        text = buffer.getvalue()
        self.assertIn(WEAPON_NAME, text)
        self.assertIn("Analytic steady-state DPS", text)
        self.assertIn("Monte Carlo TTK", text)
        self.assertIn("Damage to Grineer", text)

    def test_cli_target_flag_selects_the_dummy(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            sim.main(["--trials", "2", "--top", "1", "--target", "plain"])
        self.assertIn("SP150 Heavy Gunner", buffer.getvalue())
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            sim.main(["--trials", "2", "--top", "1", "--target", "eximus"])
        text = buffer.getvalue()
        self.assertIn("Eximus Heavy Gunner", text)
        self.assertIn("Overguard", text)

    def test_weapon_stat_constants_match_the_export(self) -> None:
        self.assertEqual(WEAPON_NAME, "Corinth Prime")
        self.assertAlmostEqual(PELLETS, 6.0)
        self.assertAlmostEqual(PELLET_DAMAGE, 90.0)
        self.assertAlmostEqual(BASE_CRIT_CHANCE, 0.30)
        self.assertAlmostEqual(BASE_CRIT_MULTIPLIER, 2.80)
        self.assertAlmostEqual(BASE_STATUS_CHANCE, 0.09)
        self.assertAlmostEqual(BASE_FIRE_RATE, 1.4166667)
        self.assertEqual(MAGAZINE, 20)
        self.assertAlmostEqual(RELOAD_TIME, 3.0)


if __name__ == "__main__":
    unittest.main()
