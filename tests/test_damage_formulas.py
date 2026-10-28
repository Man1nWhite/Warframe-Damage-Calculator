"""Regression tests for the damage calculation pipeline.

Expected values are transcribed from the official WARFRAME Wiki, not the
historical workbook, which used an outdated 1/16 quantum and rounded damage
before applying faction bonuses.
"""

from __future__ import annotations

import itertools
import math
import unittest

from modules.calculator import DamageCalculator
from modules.constants import DAMAGE_TYPES, FACTION_MULTIPLIERS
from modules.models import CalculationInputs, EquippedMod, Mod, ModEffect, Weapon
from modules.mod_engine import ModAggregator, _bane_bonus
from modules.mod_parser import parse_effects


def make_weapon(damage: dict[str, float], dmg: float | None = None, multi: float = 1.0) -> Weapon:
    return Weapon(
        weapon="Test Weapon",
        unique_name="/test/weapon",
        product_category="LongGuns",
        slot_group="PRIMARY",
        dmg=float(dmg if dmg is not None else sum(damage.values())),
        critchan=0.1,
        critmult=2.0,
        statchan=0.1,
        firerate=1.0,
        multi=multi,
        damage=dict(damage),
    )


def equipped(*pairs: tuple[str, float]) -> list[EquippedMod]:
    mod = Mod(
        unique_name="/test/mod",
        name="Test Mod",
        mod_type="",
        compat_name="",
        polarity="",
        rarity="",
        fusion_limit=0,
        base_drain=0,
        description="",
        effect_summary="",
        supported=True,
    )
    return [
        EquippedMod(mod=mod, rank=0, effects=[ModEffect(code=code, value=value, text="")])
        for code, value in pairs
    ]


class ElementalCombinationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregator = ModAggregator()

    def aggregate(self, sequence):
        return {k: v for k, v in self.aggregator.aggregate(equipped(*sequence), "Grineer").items() if v}

    def assertStatMapEqual(self, actual: dict[str, float], expected: dict[str, float]) -> None:
        self.assertEqual(set(actual), set(expected))
        for code, value in expected.items():
            self.assertAlmostEqual(actual[code], value)

    def test_simple_pair(self) -> None:
        self.assertStatMapEqual(
            self.aggregate([("HEAT", 0.9), ("COLD", 0.6)]),
            {"BLAST": 1.5},
        )

    def test_repeated_element_stacks_before_combining(self) -> None:
        # Two Heat mods and one Cold mod produce a single Blast bucket with
        # all three values, matching the game's first-occurrence grouping.
        self.assertStatMapEqual(
            self.aggregate([("HEAT", 0.9), ("HEAT", 0.9), ("COLD", 0.6)]),
            {"BLAST": 2.4},
        )

    def test_later_copy_feeds_existing_combo(self) -> None:
        # Hellfire + Cryo Rounds + Thermite Rounds: the second Heat joins the
        # Blast combo instead of standing alone.
        self.assertStatMapEqual(
            self.aggregate([("HEAT", 0.9), ("COLD", 0.6), ("HEAT", 0.9)]),
            {"BLAST": 2.4},
        )

    def test_repeated_second_pair_element(self) -> None:
        self.assertStatMapEqual(
            self.aggregate([("ELEC", 0.9), ("TOXIN", 0.9), ("TOXIN", 0.9)]),
            {"CORR": 2.7},
        )

    def test_four_elements_pair_in_order(self) -> None:
        self.assertStatMapEqual(
            self.aggregate(
                [("HEAT", 0.9), ("COLD", 0.6), ("ELEC", 0.9), ("TOXIN", 0.9)]
            ),
            {"BLAST": 1.5, "CORR": 1.8},
        )

    def test_same_element_only_stays_standalone(self) -> None:
        self.assertStatMapEqual(self.aggregate([("HEAT", 0.9), ("HEAT", 0.9)]), {"HEAT": 1.8})

    def test_non_elemental_mod_does_not_disturb_pending(self) -> None:
        result = {
            k: v
            for k, v in self.aggregator.aggregate(
                equipped(("HEAT", 0.9), ("TRUE", 1.65), ("COLD", 0.6)), "Grineer"
            ).items()
            if v
        }
        self.assertStatMapEqual(result, {"BLAST": 1.5, "TRUE": 1.65})

    def test_non_riven_multi_element_mod_keeps_listed_order(self) -> None:
        mixed = equipped(("ELEC", 0.4))[0]
        mixed.effects.append(ModEffect(code="TOXIN", value=0.3, text="+30% Toxin"))
        bonuses = self.aggregator.aggregate(equipped(("HEAT", 0.5)) + [mixed], "Grineer")
        self.assertStatMapEqual({k: v for k, v in bonuses.items() if v},
                                {"RAD": 0.9, "TOXIN": 0.3})

    def test_aggregator_and_calculator_agree_for_all_four_effect_sequences(self) -> None:
        elements = ("HEAT", "COLD", "ELEC", "TOXIN")
        for sequence in itertools.product(elements, repeat=4):
            prior = equipped((sequence[0], 0.1))
            riven = equipped((sequence[1], 0.2))[0]
            riven.mod.name = "Test Riven"
            riven.effects.append(ModEffect(code=sequence[2], value=0.3, text=""))
            slots = prior + [riven] + equipped((sequence[3], 0.4))
            bonuses = self.aggregator.aggregate(slots, "Grineer")
            weapon = make_weapon({"SLASH": 100})
            result = DamageCalculator().calculate(weapon, CalculationInputs(
                weapon_name=weapon.weapon, faction="Grineer", armor_value=0,
                mods=bonuses, equipped_mods=slots))
            for kind in (*elements, "BLAST", "RAD", "GAS", "MAG", "VIRAL", "CORR"):
                self.assertAlmostEqual(result.aggregated_mods[kind], bonuses[kind],
                                       msg=f"{sequence}: {kind}")

    def test_riven_order_matches_calculator_with_mixed_effects_and_later_slots(self) -> None:
        # Wiki: the last listed Riven primary has priority; secondary element
        # and non-elemental effects remain independent. Later copies of Heat
        # feed the original combination rather than starting a new one.
        prior = equipped(("HEAT", 0.5))
        riven = equipped(("ELEC", 0.4))[0]
        riven.mod.name = "Riven Mod"
        riven.effects.extend([
            ModEffect(code="TRUE", value=0.2, text="+20% Damage", position=1),
            ModEffect(code="TOXIN", value=0.3, text="+30% Toxin", position=2),
            ModEffect(code="GAS", value=0.1, text="+10% Gas", position=3),
            ModEffect(code="BANE_GRINEER", value=0.25, text="+25% Damage to Grineer", position=4),
        ])
        slots = prior + [riven] + equipped(("COLD", 0.6), ("HEAT", 0.2))
        original_effects = list(riven.effects)
        bonuses = self.aggregator.aggregate(slots, "Grineer")
        self.assertStatMapEqual(
            {k: v for k, v in bonuses.items() if v},
            {"GAS": 1.1, "MAG": 1.0, "TRUE": 0.2, "BANE": 0.25},
        )
        self.assertEqual(riven.effects, original_effects)  # do not reorder saved effects
        weapon = make_weapon({"SLASH": 100})
        result = DamageCalculator().calculate(weapon, CalculationInputs(
            weapon_name=weapon.weapon, faction="Grineer", armor_value=0,
            mods=bonuses, equipped_mods=slots))
        for code in ("GAS", "MAG", "TRUE", "BANE"):
            self.assertAlmostEqual(result.aggregated_mods[code], bonuses[code], msg=code)
        self.assertEqual(result.aggregated_mods["RAD"], 0)
        self.assertEqual(result.aggregated_mods["VIRAL"], 0)


class DamageFixture:
    def calculate(self, damage, *, faction="Grineer", armor=0, mods=None,
                  slots=None, lich="", valence=0, multi=1):
        weapon = make_weapon(damage, multi=multi)
        if mods is None:
            mods = ModAggregator().aggregate(slots or [], faction)
        return DamageCalculator().calculate(weapon, CalculationInputs(
            weapon_name=weapon.weapon, faction=faction, armor_value=armor,
            mods=mods, equipped_mods=slots, lich_element=lich, valence_base=valence))


class WikiDamageExamplesTests(DamageFixture, unittest.TestCase):
    """Independent examples from /w/Damage/Calculation and /w/Armor."""

    def test_wiki_100_base_example_and_unrounded_health_damage(self):
        r = self.calculate({"IMPACT": 30, "PUNC": 30, "SLASH": 40},
                           faction="Infested")
        self.assertEqual(r.quanta, 3.125)
        self.assertEqual(r.final_damage_by_type["IMPACT"], 31.25)
        self.assertEqual(r.final_damage_by_type["PUNC"], 31.25)
        self.assertEqual(r.final_damage_by_type["SLASH"], 60.9375)
        self.assertEqual(r.final_total, 123.4375)  # popup would show 123
        self.assertEqual(r.hud_total, 100.0)     # Arsenal is not quantized

    def test_wiki_nagantaka_type_distribution(self):
        slots = equipped(("PUNC", 1.2), ("COLD", 0.9), ("TOXIN", 0.6),
                         ("HEAT", 0.9), ("GAS", 2.0))
        r = self.calculate({"IMPACT": 1.73, "PUNC": 15.57, "SLASH": 155.7},
                           faction="Infested", slots=slots)
        self.assertEqual(r.quanta, 173 / 32)
        self.assertEqual(r.final_damage_by_type["IMPACT"], 0)
        self.assertAlmostEqual(r.final_damage_by_type["PUNC"], 32.4375)
        self.assertAlmostEqual(r.final_damage_by_type["SLASH"], 156.78125 * 1.5)
        self.assertAlmostEqual(r.final_damage_by_type["VIRAL"], 259.5)
        self.assertAlmostEqual(r.final_damage_by_type["HEAT"], 156.78125 * 1.5)
        self.assertAlmostEqual(r.final_damage_by_type["GAS"], 346)
        self.assertAlmostEqual(r.final_total, 1108.28125)

    def test_base_damage_changes_quantum_and_damage_not_ratios(self):
        r = self.calculate({"IMPACT": 30, "PUNC": 30, "SLASH": 40},
                           faction="Infested", mods={"TRUE": 1.65})
        self.assertAlmostEqual(r.quanta, 265 / 32)
        self.assertAlmostEqual(r.final_total, 123.4375 * 2.65)

    def test_bane_applies_before_any_display_rounding_including_penalties(self):
        r = self.calculate({"IMPACT": 30, "PUNC": 30, "SLASH": 40},
                           faction="Infested", mods={"BANE": 0.3})
        self.assertAlmostEqual(r.final_total_with_bane, 123.4375 * 1.3)
        r = self.calculate({"SLASH": 100}, mods={"BANE": -0.2})
        self.assertAlmostEqual(r.final_total_with_bane, 80)

    def test_no_three_decimal_intermediate_rounding(self):
        r = self.calculate({"IMPACT": 0.3, "PUNC": 0.3, "SLASH": 0.4})
        self.assertEqual(r.final_damage_by_type["SLASH"], 0.40625)

    def test_armor_standard_exception_and_minimum(self):
        standard = self.calculate({"HEAT": 100}, armor=500)
        self.assertAlmostEqual(standard.final_total, 100 * (1 - 0.9 * math.sqrt(500 / 2700)))
        exception = self.calculate({"HEAT": 100}, armor=3000)
        self.assertAlmostEqual(exception.final_total, 100 * (300 / 3300))
        tiny = self.calculate({"IMPACT": 0.1, "PUNC": 0.1, "SLASH": 0.1}, armor=2700)
        self.assertEqual(tiny.final_total, 3.0)
        # No minimum for types quantized to zero.
        tiny = self.calculate({"IMPACT": 0.001, "PUNC": 99.999}, armor=2700)
        self.assertEqual(tiny.final_damage_by_type["IMPACT"], 0)

    def test_innate_multishot_and_melee_arsenal_total(self):
        # Wiki Hek: 7 pellets x 75 = 525; one projectile is still 75.
        r = self.calculate({"IMPACT": 11.25, "PUNC": 48.75, "SLASH": 15}, multi=7)
        self.assertEqual(r.hud_total, 525)
        self.assertAlmostEqual(sum(r.hud_damage_by_type.values()), 75)
        melee = self.calculate({"SLASH": 100}, multi=0)
        self.assertEqual(melee.hud_total, 100)

    def test_valence_without_element_does_not_create_damage(self):
        r = self.calculate({"SLASH": 100}, valence=60)
        self.assertEqual(r.weapon_total_damage, 100)
        self.assertEqual(sum(r.lich_damage.values()), 0)

    def test_zero_damage_multiplier_results_in_zero(self):
        r = self.calculate({"SLASH": 100}, mods={"TRUE": -1.0})
        self.assertEqual(r.quanta, 0)
        self.assertEqual(r.hud_total, 0)
        self.assertEqual(r.final_total, 0)


class WikiElementHierarchyTests(DamageFixture, unittest.TestCase):
    """Examples from /w/Damage#Modding, including the Tenet Detron case."""

    def test_innate_heat_combines_with_last_unpaired_cold_mod(self):
        r = self.calculate({"HEAT": 100}, slots=equipped(("COLD", 0.9)))
        self.assertAlmostEqual(r.hud_damage_by_type["BLAST"], 190)
        self.assertEqual(r.hud_damage_by_type["HEAT"], 0)
        self.assertEqual(r.hud_damage_by_type["COLD"], 0)

    def test_wiki_innate_electricity_after_mods(self):
        slots = equipped(("COLD", 0.9), ("TOXIN", 0.9), ("HEAT", 0.9))
        r = self.calculate({"ELEC": 100}, slots=slots)
        self.assertAlmostEqual(r.hud_damage_by_type["VIRAL"], 180)
        self.assertAlmostEqual(r.hud_damage_by_type["RAD"], 190)
        self.assertEqual(r.hud_damage_by_type["ELEC"], 0)

    def test_innate_secondary_does_not_absorb_primary_progenitor(self):
        # Wiki example: Tenet Detron Radiation with Electricity progenitor.
        r = self.calculate({"RAD": 100}, slots=[], lich="ELEC", valence=60)
        self.assertEqual(r.hud_damage_by_type["RAD"], 100)
        self.assertEqual(r.hud_damage_by_type["ELEC"], 60)
        self.assertEqual(sum(r.lich_damage.values()), 60)

    def test_innate_secondary_does_not_absorb_component_mod(self):
        r = self.calculate({"RAD": 100}, slots=equipped(("HEAT", 0.9)))
        self.assertEqual(r.hud_damage_by_type["RAD"], 100)
        self.assertEqual(r.hud_damage_by_type["HEAT"], 90)

    def test_progenitor_joins_exactly_one_preexisting_primary_pair(self):
        slots = equipped(("HEAT", 0.9), ("COLD", 0.9),
                         ("ELEC", 0.6), ("TOXIN", 0.6))
        r = self.calculate({"IMPACT": 100}, slots=slots, lich="HEAT", valence=60)
        self.assertEqual(r.lich_damage["BLAST"], 60)
        self.assertEqual(sum(r.lich_damage.values()), 60)
        self.assertAlmostEqual(r.hud_damage_by_type["BLAST"], 60 + 160 * 1.8)
        self.assertAlmostEqual(r.hud_damage_by_type["CORR"], 160 * 1.2)

    def test_riven_last_listed_primary_has_priority(self):
        prior = equipped(("HEAT", 0.5))
        riven = equipped(("ELEC", 0.4))[0]
        riven.mod.name = "Riven Mod"
        riven.effects.append(ModEffect(code="TOXIN", value=0.3, text="", position=2))
        r = self.calculate({"IMPACT": 100}, slots=prior + [riven])
        self.assertAlmostEqual(r.hud_damage_by_type["GAS"], 80)
        self.assertAlmostEqual(r.hud_damage_by_type["ELEC"], 40)
        self.assertEqual(r.hud_damage_by_type["RAD"], 0)


class FactionWikiTests(unittest.TestCase):
    def test_faction_matrix(self):
        # Non-neutral entries from /w/Damage/Overview_Table; all others are 1x.
        expected = {
            "Grineer": {"IMPACT": 1.5, "CORR": 1.5},
            "Kuva": {"IMPACT": 1.5, "CORR": 1.5, "HEAT": 0.5},
            "Corpus": {"PUNC": 1.5, "MAG": 1.5},
            "Amalgam": {"ELEC": 1.5, "MAG": 1.5, "BLAST": 0.5},
            "Infested": {"SLASH": 1.5, "HEAT": 1.5},
            "Deimos": {"BLAST": 1.5, "GAS": 1.5, "VIRAL": 0.5},
            "Orokin": {"PUNC": 1.5, "VIRAL": 1.5, "RAD": 0.5},
            "Sentient": {"COLD": 1.5, "RAD": 1.5, "CORR": 0.5},
            "Narmer": {"SLASH": 1.5, "TOXIN": 1.5, "MAG": 0.5},
            "Murmur": {"ELEC": 1.5, "RAD": 1.5, "VIRAL": 0.5},
            "Zariman": {"VOID": 1.5},
            "Scaldra": {"IMPACT": 1.5, "CORR": 1.5, "GAS": 0.5},
            "Techrot": {"GAS": 1.5, "MAG": 1.5, "COLD": 0.5},
            "Anarchs": {"IMPACT": 1.5, "ELEC": 1.5, "RAD": 0.5},
        }
        self.assertEqual(set(FACTION_MULTIPLIERS), set(expected))
        for faction, non_neutral in expected.items():
            for kind in DAMAGE_TYPES:
                self.assertEqual(FACTION_MULTIPLIERS[faction][kind],
                                 non_neutral.get(kind, 1.0), (faction, kind))

    def test_narmer_does_not_take_grineer_or_corpus_bane(self):
        slots = equipped(("BANE_GRINEER", 1.3), ("BANE_CORPUS", 1.3))
        self.assertEqual(ModAggregator().aggregate(slots, "Narmer")["BANE"], 0)

    def test_murmur_orokin_and_sentient_banes_are_parsed(self):
        for text, code in [("X1.55 damage to the murmur", "BANE_MURMUR"),
                           ("X1.3 damage to orokin", "BANE_CORRUPTED"),
                           ("+30% damage to sentients", "BANE_SENTIENT")]:
            with self.subTest(text=text):
                self.assertEqual(parse_effects(text)[0].code, code)
        self.assertAlmostEqual(_bane_bonus(1.55, "X1.55 damage to the murmur"), 0.55)
        self.assertAlmostEqual(_bane_bonus(1.55, "+155% damage to the murmur"), 1.55)
        self.assertAlmostEqual(_bane_bonus(1.0, "X1.0 damage to grineer"), 0)

    def test_zariman_legacy_spelling_is_accepted(self):
        w = make_weapon({"VOID": 100})
        def calculate(faction):
            return DamageCalculator().calculate(w, CalculationInputs(w.weapon, faction, 0))
        self.assertEqual(calculate("Zairman").final_total, calculate("Zariman").final_total)


if __name__ == "__main__":
    unittest.main()
