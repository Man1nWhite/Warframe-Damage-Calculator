"""Wiki-pinned checks for ``modules.crit``.

Every expected value is taken from the English WARFRAME Wiki (retrieved
2026-10-28):

* https://wiki.warframe.com/w/Critical_Hit#Critical_Chance (relative/absolute
  bonuses and the Braton + Point Strike / Arcane Avenger example)
* https://wiki.warframe.com/w/Critical_Hit#Quantization (the 12-bit base
  multiplier and the Braton Incarnon code-256 example)
* https://wiki.warframe.com/w/Damage/Cold_Damage (the Freeze table and the
  Kunai + Primed Target Cracker example)
* https://wiki.warframe.com/w/Damage/Calculation#Average_Shot/Hit (average,
  normal and critical shot, AoE and weak-point variants)

These tests document the formulas; they do not validate in-game binary32
rounding.
"""

from __future__ import annotations

import math
import unittest

from modules.calculator import DamageCalculator
from modules.crit import (
    COLD_CRIT_DAMAGE_BY_STACK,
    average_shot,
    cold_crit_damage_bonus,
    crit_multiplier_for_tier,
    crit_tiers,
    critical_shot,
    direct_aoe_shot,
    modded_crit_chance,
    modded_crit_multiplier,
    normal_shot,
    quantize_crit_multiplier,
    weak_point_shot,
)
from modules.mod_engine import ModAggregator
from modules.models import CalculationInputs, EquippedMod, Mod, ModEffect, Weapon

CODE_UNIT = 32.0 / 4095.0


class CriticalChanceTests(unittest.TestCase):
    def test_braton_point_strike_and_argon_scope(self) -> None:
        # 12% x (1 + 150% + 135%).
        self.assertAlmostEqual(modded_crit_chance(0.12, 1.50 + 1.35), 0.462)

    def test_braton_point_strike_and_arcane_avenger(self) -> None:
        # Relative bonuses scale the base; absolute bonuses are added after.
        self.assertAlmostEqual(modded_crit_chance(0.12, 1.50, 0.45), 0.75)

    def test_blood_rush_form(self) -> None:
        # Gram, True Steel + Blood Rush at a x7 combo multiplier.
        expected = 0.15 * (1 + 1.20 + 0.40 * (7 - 1))
        self.assertAlmostEqual(modded_crit_chance(0.15, 1.20 + 0.40 * (7 - 1)),
                               expected)


class CriticalMultiplierQuantizationTests(unittest.TestCase):
    def test_braton_incarnon_code_256_example(self) -> None:
        # Code(1.6 + 0.4) = floor(2.0 * 4095/32 + 0.5) = 256.
        self.assertEqual(math.floor(2.0 * 4095 / 32 + 0.5), 256)
        self.assertAlmostEqual(quantize_crit_multiplier(1.6 + 0.4), 256 * CODE_UNIT)
        self.assertAlmostEqual(quantize_crit_multiplier(2.0), 2.0004884004884005)

    def test_weapon_base_multipliers(self) -> None:
        self.assertAlmostEqual(quantize_crit_multiplier(1.6), 205 * CODE_UNIT)
        self.assertAlmostEqual(quantize_crit_multiplier(1.8), 230 * CODE_UNIT)
        self.assertAlmostEqual(quantize_crit_multiplier(2.2), 282 * CODE_UNIT)
        self.assertAlmostEqual(quantize_crit_multiplier(5.0), 640 * CODE_UNIT)

    def test_clamped_to_the_36_bit_code_range(self) -> None:
        # The wiki clamps x to [0, 32] before encoding.
        self.assertEqual(quantize_crit_multiplier(0.0), 0.0)
        self.assertEqual(quantize_crit_multiplier(-3.0), 0.0)
        self.assertAlmostEqual(quantize_crit_multiplier(40.0),
                               quantize_crit_multiplier(32.0))
        self.assertAlmostEqual(quantize_crit_multiplier(32.0), 32.0)

    def test_non_finite_rejected(self) -> None:
        with self.assertRaises(ValueError):
            quantize_crit_multiplier(math.inf)

    def test_quantization_is_skippable_for_documented_examples(self) -> None:
        # The wiki's worked examples round the base multiplier for clarity.
        self.assertAlmostEqual(modded_crit_multiplier(1.6, 1.20, quantize=False), 3.52)
        self.assertAlmostEqual(modded_crit_multiplier(1.6, 1.20), 205 * CODE_UNIT * 2.2)


class ColdCritDamageTests(unittest.TestCase):
    def test_freeze_table(self) -> None:
        expected = {1: 0.10, 2: 0.15, 3: 0.20, 4: 0.25, 5: 0.30,
                    6: 0.35, 7: 0.40, 8: 0.45, 9: 0.50, 10: 1.00}
        self.assertEqual(COLD_CRIT_DAMAGE_BY_STACK, expected)
        self.assertEqual(cold_crit_damage_bonus(0), 0.0)
        for stacks, bonus in expected.items():
            self.assertAlmostEqual(cold_crit_damage_bonus(stacks), bonus)

    def test_overguard_and_boss_cap_is_four_stacks(self) -> None:
        self.assertAlmostEqual(cold_crit_damage_bonus(9, overguard_or_boss=True), 0.25)
        self.assertAlmostEqual(cold_crit_damage_bonus(4, overguard_or_boss=True), 0.25)

    def test_kunai_primed_target_cracker_example(self) -> None:
        # 1.6 x (1 + 110%) + 0.50 = 3.86 critical damage multiplier.
        self.assertAlmostEqual(
            modded_crit_multiplier(1.6, 1.10,
                                   cold_crit_damage_bonus(9),
                                   quantize=False),
            3.86)

    def test_negative_stacks_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cold_crit_damage_bonus(-1)


class CriticalTierTests(unittest.TestCase):
    def test_paris_prime_tier_example(self) -> None:
        # 112.5% critical chance, 2x base and +0.50x Cold -> 2.5x Critical
        # Damage: tier 1 for 87.5% and tier 2 for 12.5%.
        crit_damage = 2.0 + cold_crit_damage_bonus(9)
        self.assertEqual(crit_tiers(1.125), (1, 2))
        self.assertAlmostEqual(normal_shot(100.0, 1.125, crit_damage), 250.0)
        self.assertAlmostEqual(critical_shot(100.0, 1.125, crit_damage), 400.0)
        self.assertAlmostEqual(crit_multiplier_for_tier(crit_damage, 0), 1.0)

    def test_over_100_percent_uses_lowest_and_next_tier(self) -> None:
        self.assertEqual(crit_tiers(2.50), (2, 3))

    def test_negative_chance_clamps_to_tier_zero(self) -> None:
        self.assertEqual(crit_tiers(-0.25), (0, 0))

    def test_average_shot_does_not_round_the_chance(self) -> None:
        # 250% crit chance, 2x multiplier -> 1 + 2.5 x (2 - 1) = 3.5x.
        self.assertAlmostEqual(average_shot(100.0, 2.50, 2.0), 350.0)
        self.assertAlmostEqual(average_shot(100.0, 0.0, 2.0), 100.0)

    def test_average_shot_matches_weighted_tiers(self) -> None:
        # 112.5%: 87.5% tier 1 + 12.5% tier 2 = 2.75x average.
        expected = 0.875 * 250.0 + 0.125 * 400.0
        self.assertAlmostEqual(average_shot(100.0, 1.125, 2.5), expected)


class ArsenalShotTests(unittest.TestCase):
    def test_direct_and_aoe_hits_are_separate_instances(self) -> None:
        self.assertAlmostEqual(direct_aoe_shot(100.0, 250.0), 350.0)

    def test_weak_point_multiplier_and_bonus(self) -> None:
        # Average Shot x (Weak Point Multiplier + Weak Point Damage Bonus).
        self.assertAlmostEqual(weak_point_shot(200.0, 2.0, 0.35), 470.0)


class SimulatorIntegrationTests(unittest.TestCase):
    """The bundled simulators use the quantized base multiplier."""

    def test_nukor_base_multiplier_is_quantized(self) -> None:
        from modules.kuva_nukor_sim import PRIMED_TARGET_CRACKER, RIVEN_CRIT_DAMAGE, build_nukor
        build = build_nukor("Primed Pistol Gambit")
        expected = (quantize_crit_multiplier(5.0)
                    * (1.0 + PRIMED_TARGET_CRACKER + RIVEN_CRIT_DAMAGE))
        self.assertAlmostEqual(build.crit_multiplier, expected)

    def test_ocucor_base_multiplier_is_quantized(self) -> None:
        from modules.ocucor_sim import build_ocucor
        build = build_ocucor(riven_stat="Critical Damage")
        self.assertAlmostEqual(build.crit_multiplier,
                               quantize_crit_multiplier(1.8) * (1.0 + 1.10 + 1.337))

    def test_alternox_base_multiplier_is_quantized(self) -> None:
        from modules.alternox_prime_sim import (
            R_BLAST,
            R_FIRE_RATE,
            R_TOXIN,
            VITAL_SENSE_CD,
            build_alternox,
        )
        build = build_alternox((R_BLAST, R_FIRE_RATE, R_TOXIN))
        self.assertAlmostEqual(
            build.crit_multiplier,
            quantize_crit_multiplier(2.2) * (1.0 + VITAL_SENSE_CD))


class CodeSpacingTests(unittest.TestCase):
    def test_adjacent_codes_differ_by_32_over_4095(self) -> None:
        low = quantize_crit_multiplier(4.0)
        high = quantize_crit_multiplier(4.0 + CODE_UNIT)
        self.assertAlmostEqual(high - low, CODE_UNIT)


class DamageCalculationQuantizationTests(unittest.TestCase):
    """The Nagantaka Prime example from Damage/Calculation#Quantization.

    Cryo Rounds, Malignant Force, Hellfire, Piercing Caliber and a 200% Gas
    Valence Formation, in that slot order, against a 173-damage weapon:
    Puncture 32.4375 + Slash 156.78125 + Viral 259.5 + Heat 156.78125 +
    Gas 346 = 951.5, with the 1.73 Impact quantized to 0.
    """

    @staticmethod
    def _equipped(*pairs: tuple[str, float]) -> list[EquippedMod]:
        mod = Mod(
            unique_name="/test/mod", name="Test Mod", mod_type="",
            compat_name="", polarity="", rarity="", fusion_limit=0,
            base_drain=0, description="", effect_summary="", supported=True,
        )
        return [
            EquippedMod(mod=mod, rank=0,
                        effects=[ModEffect(code=code, value=value, text="")])
            for code, value in pairs
        ]

    def setUp(self) -> None:
        self.weapon = Weapon(
            weapon="Nagantaka Prime", unique_name="/test/nagantaka",
            product_category="LongGuns", slot_group="PRIMARY", dmg=173.0,
            critchan=0.2, critmult=2.3, statchan=0.3, firerate=1.0,
            multi=1.0,
            damage={"IMPACT": 1.73, "PUNC": 15.57, "SLASH": 155.7},
        )
        self.slots = self._equipped(
            ("COLD", 0.90), ("TOXIN", 0.60), ("HEAT", 0.90),
            ("PUNC", 1.20), ("GAS", 2.00),
        )

    def calculate(self):
        mods = {k: v for k, v in ModAggregator()
                .aggregate(self.slots, "Grineer").items() if v}
        return DamageCalculator().calculate(
            self.weapon,
            CalculationInputs(self.weapon.weapon, "Grineer", 0, mods=mods,
                              equipped_mods=self.slots),
        )

    def test_every_quantized_type_value(self) -> None:
        final = self.calculate().final_damage_by_type
        expected = {
            "PUNC": 32.4375,
            "SLASH": 156.78125,
            "VIRAL": 259.5,
            "HEAT": 156.78125,
            "GAS": 346.0,
        }
        self.assertEqual(set(expected),
                         {k for k, v in final.items() if v})
        for damage_type, value in expected.items():
            self.assertAlmostEqual(final[damage_type], value, places=9,
                                   msg=damage_type)
        # 1.73 Impact quantizes to zero and never registers.
        self.assertEqual(final["IMPACT"], 0.0)

    def test_total_is_951_5(self) -> None:
        self.assertAlmostEqual(self.calculate().final_total, 951.5, places=9)

    def test_arsenal_display_is_not_quantized(self) -> None:
        hud = self.calculate().hud_damage_by_type
        self.assertAlmostEqual(hud["PUNC"], 15.57 * 2.2)
        self.assertAlmostEqual(hud["SLASH"], 155.7)
        self.assertAlmostEqual(hud["VIRAL"], 173 * 1.5)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
