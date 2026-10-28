"""Tests pinning the wiki's status DoT and proc-chance formulas.

Worked examples are taken verbatim from wiki.warframe.com:
- Damage/Calculation "Damage Over Time" (exact +1 accumulator examples)
- Damage/Slash_Damage and Damage/Toxin_Damage (simplified per-type examples)
- Status_Effect "Average Procs" table and Damage Distribution example
- Damage_over_Time tick timing table
"""
from __future__ import annotations

import unittest

from modules.status_damage import (
    GAS_MAX_STACKS,
    STATUS_PROCS,
    average_procs_per_second,
    average_procs_per_shot,
    beam_merged_status_chance,
    damaging_ticks,
    electricity_tick,
    gas_tick,
    heat_tick,
    modded_base_damage,
    proc_tick_damage,
    proc_type_chances,
    slash_tick,
    total_ticks,
    toxin_tick,
    wiki_quantized_damage,
)


class AccumulatorTickTests(unittest.TestCase):
    """Exact (sum(S_i)+1)*C*M examples from Damage/Calculation."""

    def test_heat_supra_vandal_example(self) -> None:
        # 40 base, Thermite Rounds +60% Heat: (40+1)*0.5*1.6 = 32.8, shown 33
        self.assertAlmostEqual(heat_tick(40.0, elemental_bonus=0.6), 32.8)

    def test_electricity_example(self) -> None:
        # 40 seed, +150% Electricity: (40+1)*0.5*2.5 = 51.25, shown 51
        self.assertAlmostEqual(
            electricity_tick(40.0, elemental_bonus=1.5), 51.25)

    def test_gas_bare_seed_example(self) -> None:
        # 40 seed, no bonuses: (40+1)*0.5 = 20.5, shown 21
        self.assertAlmostEqual(gas_tick(40.0), 20.5)

    def test_toxin_double_dip_faction_example(self) -> None:
        # 40 seed, +225% Toxin, Primed Bane of Orokin +55%:
        # (40*1.55+1)*0.5*3.25*1.55 = 158.68125, shown 159
        seed = modded_base_damage(40.0, faction_bonus=0.55)
        tick = toxin_tick(seed, elemental_bonus=2.25, faction_bonus=0.55)
        self.assertAlmostEqual(tick, 158.68125)

    def test_consolidated_seeds_count_accumulator_once(self) -> None:
        # two 40-damage seeds in one tick group: (40+40+1)*0.5, not 2*(41*0.5)
        tick = proc_tick_damage(40.0, 0.5, extra_seeds=40.0)
        self.assertAlmostEqual(tick, 40.5)

    def test_crit_applies_to_seed_before_single_accumulator(self) -> None:
        # Wiki's consolidated examples add critical seeds and noncritical
        # seeds before the one fixed +1, rather than critting that +1.
        self.assertAlmostEqual(
            electricity_tick(40.0, crit_multiplier=2.0), (80 + 1) * 0.5)
        self.assertAlmostEqual(
            proc_tick_damage(40.0, 0.5, crit_multiplier=2.0, extra_seeds=40),
            (80 + 40 + 1) * 0.5)
        self.assertAlmostEqual(
            toxin_tick(40.0, body_part_multiplier=2.0), (80 + 1) * 0.5)

    def test_simplified_formula_without_accumulator(self) -> None:
        # per-type wiki pages omit the +1 accumulator
        simple = proc_tick_damage(40.0, 0.5, accumulator=False)
        self.assertAlmostEqual(simple, 20.0)
        self.assertAlmostEqual(gas_tick(40.0), simple + 0.5)


class PerTypePageExamples(unittest.TestCase):
    """Simplified formulas from the Slash/Toxin damage-type pages."""

    def test_slash_bleed_wiki_example(self) -> None:
        # 100 base, Serration +165%, Bane of Grineer +30%, Rifle Elementalist +90%
        # Bleed/tick = 100*2.65*0.35*1.3^2*1.9 = 297.8202 (wiki value)
        seed = modded_base_damage(100.0, base_damage_bonus=1.65,
                                  faction_bonus=0.3)
        tick = slash_tick(seed, faction_bonus=0.3, status_damage_bonus=0.9,
                          accumulator=False)
        self.assertAlmostEqual(tick, 297.8202, places=3)

    def test_toxin_wiki_example(self) -> None:
        # Modded base = 100*2.65*1.3 = 344.5; DoT mult = 1.9*1.9*1.3 = 4.693
        # Tick = 0.5*344.5*4.693 = 808.3692
        seed = modded_base_damage(100.0, base_damage_bonus=1.65,
                                  faction_bonus=0.3)
        tick = toxin_tick(seed, elemental_bonus=0.9, faction_bonus=0.3,
                          status_damage_bonus=0.9, accumulator=False)
        self.assertAlmostEqual(tick, 808.3692, places=3)

    def test_slash_rejects_elemental_bonus(self) -> None:
        # Buzz Kill / physical mods and elemental mods never buff Bleed
        plain = slash_tick(100.0, accumulator=False)
        with_bonus = slash_tick(100.0, elemental_bonus=5.0, accumulator=False)
        self.assertEqual(plain, with_bonus)

    def test_gas_ignores_component_mods_documentation(self) -> None:
        # only literal Gas bonuses enter; callers must not pass Heat/Toxin mods
        base = gas_tick(100.0, accumulator=False)
        self.assertAlmostEqual(base, 50.0)
        buffed = gas_tick(100.0, elemental_bonus=0.9, accumulator=False)
        self.assertAlmostEqual(buffed, 50.0 * 1.9)


class TimingAndStackTests(unittest.TestCase):
    def test_single_target_procs_have_six_damaging_ticks(self) -> None:
        # 1 s delay, 6 s duration: ticks at t = 1..6
        self.assertEqual(total_ticks(6.0, delay=1.0), 6)
        self.assertEqual(damaging_ticks(6.0, delay=1.0), 6)

    def test_aoe_procs_last_tick_deals_nothing(self) -> None:
        # Gas/Electricity: no delay -> 7 nominal ticks, last one empty
        self.assertEqual(total_ticks(6.0, delay=0.0), 7)
        self.assertEqual(
            damaging_ticks(6.0, delay=0.0, last_tick_empty=True), 6)

    def test_fractional_duration_preserves_last_pre_expiry_aoe_pulse(self) -> None:
        # At 6.1 s, t=6 is still before expiration; at exactly 6 it is empty.
        self.assertEqual(damaging_ticks(6.1, delay=0, last_tick_empty=True), 7)
        self.assertEqual(damaging_ticks(6.0, delay=0, last_tick_empty=True), 6)
        self.assertEqual(damaging_ticks(0.5, delay=0, last_tick_empty=True), 1)
        self.assertEqual(damaging_ticks(0.5, delay=1), 0)
        self.assertEqual(damaging_ticks(-2, delay=1), 0)
        with self.assertRaises(ValueError):
            damaging_ticks(6, tick_rate=0)

    def test_status_proc_reference_table(self) -> None:
        self.assertEqual(STATUS_PROCS["slash"].coefficient, 0.35)
        self.assertTrue(STATUS_PROCS["slash"].armor_bypass)
        self.assertEqual(STATUS_PROCS["gas"].max_stacks, GAS_MAX_STACKS)
        self.assertTrue(STATUS_PROCS["gas"].aoe)
        self.assertTrue(STATUS_PROCS["electricity"].last_tick_empty)
        for name in ("slash", "heat", "toxin", "electricity", "gas"):
            self.assertEqual(STATUS_PROCS[name].duration, 6.0)


class ProcChanceTests(unittest.TestCase):
    def test_proc_type_weights_match_wiki_distribution(self) -> None:
        distribution = {"Impact": 20, "Puncture": 5, "Slash": 10,
                        "Heat": 25, "Corrosive": 50}
        weights = proc_type_chances(distribution)
        self.assertAlmostEqual(weights["Impact"], 20 / 110)
        self.assertAlmostEqual(weights["Puncture"], 5 / 110)
        self.assertAlmostEqual(weights["Slash"], 10 / 110)
        self.assertAlmostEqual(weights["Heat"], 25 / 110)
        self.assertAlmostEqual(weights["Corrosive"], 50 / 110)
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_empty_distribution_raises(self) -> None:
        with self.assertRaises(ValueError):
            proc_type_chances({})
        for invalid in ({"A": -1, "B": 2}, {"A": float("nan"), "B": 1},
                        {"A": float("inf"), "B": 1}, {"A": 1e308, "B": 1e308}):
            with self.subTest(distribution=invalid), self.assertRaises(ValueError):
                proc_type_chances(invalid)

    def test_average_procs_per_shot_wiki_table(self) -> None:
        # wiki Status_Effect table: 1.9 multishot x 80% status = 1.52
        self.assertAlmostEqual(average_procs_per_shot(0.8, 1.9), 1.52)
        self.assertAlmostEqual(average_procs_per_shot(1.0, 1.9), 1.9)
        self.assertAlmostEqual(average_procs_per_shot(1.0, 10.0), 10.0)
        self.assertAlmostEqual(average_procs_per_shot(1.5, 3.0), 4.5)

    def test_forced_procs_are_multiplied_by_multishot(self) -> None:
        self.assertAlmostEqual(
            average_procs_per_shot(0.0, 2.0, forced_procs=1.0), 2.0)

    def test_procs_per_second(self) -> None:
        self.assertAlmostEqual(
            average_procs_per_second(1.0, 1.0, fire_rate=12.0), 12.0)

    def test_beam_status_chance_sums_merged_instances(self) -> None:
        # continuous weapon: merged tick status chance = sum of beams
        self.assertAlmostEqual(beam_merged_status_chance(0.3, 2.0), 0.6)


class QuantizationTests(unittest.TestCase):
    def test_wiki_1_32nd_quantization(self) -> None:
        # 35 damage of a 100 base: floor(0.35*32 + 0.5) = 11 -> 34.375
        self.assertAlmostEqual(wiki_quantized_damage(35.0, 100.0), 34.375)

    def test_quantization_keeps_clean_multiples(self) -> None:
        self.assertAlmostEqual(wiki_quantized_damage(50.0, 100.0), 50.0)

    def test_quantization_preserves_sign(self) -> None:
        self.assertAlmostEqual(wiki_quantized_damage(-35.0, 100.0), -34.375)


if __name__ == "__main__":
    unittest.main()
