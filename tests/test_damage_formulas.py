"""Regression tests for the damage calculation pipeline.

The reference values come from the bundled workbook
``source/Warframe-Damage-Calculator_v2.xlsx`` (sheet "Damage-Calculator"),
whose cached formula outputs were generated from a Tenet Arca Plasmor build.
The randomized parity test re-implements the workbook formulas independently
and checks the engine against them across many generated builds.
"""

from __future__ import annotations

import math
import random
import unittest

from modules.calculator import DamageCalculator
from modules.constants import DAMAGE_TYPES, FACTION_MULTIPLIERS, PHYSICAL_DAMAGE_TYPES
from modules.models import CalculationInputs, EquippedMod, Mod, ModEffect, Weapon
from modules.mod_engine import ModAggregator, _bane_bonus
from modules.rounding import excel_round


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


class SpreadsheetParityTests(unittest.TestCase):
    """Exact cached outputs of the workbook's Tenet Arca Plasmor example."""

    def setUp(self) -> None:
        self.weapon = make_weapon({"RAD": 760.0}, dmg=760.0)
        self.calculator = DamageCalculator()
        self.inputs = CalculationInputs(
            weapon_name=self.weapon.weapon,
            faction="Grineer",
            armor_value=2700.0,
            lich_element="MAG",
            valence_base=422.3,
            mods={"MAG": 3.3, "TRUE": 1.65, "BANE": 0.0},
        )
        self.results = self.calculator.calculate(self.weapon, self.inputs)

    def test_valence_and_quanta(self) -> None:
        self.assertAlmostEqual(self.results.valence_multiplier, 0.5556578947368421, places=15)
        self.assertAlmostEqual(self.results.weapon_total_damage, 1182.3)
        self.assertAlmostEqual(self.results.quanta, 73.89375)

    def test_lich_routing(self) -> None:
        self.assertEqual(self.results.lich_damage["MAG"], 422.3)
        self.assertEqual(sum(self.results.lich_damage.values()), 422.3)

    def test_hud_buckets_match_workbook(self) -> None:
        self.assertAlmostEqual(self.results.hud_damage_by_type["MAG"], 11458.3158703125)
        self.assertAlmostEqual(self.results.hud_damage_by_type["RAD"], 2013.9926296875)
        self.assertAlmostEqual(self.results.hud_total, 13472.3085)

    def test_final_total_matches_workbook(self) -> None:
        self.assertEqual(self.results.final_total, 1351.0)
        self.assertEqual(self.results.final_total_with_bane, 1351.0)

    def test_armor_term_at_2700(self) -> None:
        # Workbook D20: (1 - 0.9 * SQRT(2700/2700)) = 0.1, applied with the
        # Grineer Corrosive weakness of 1.5.
        self.assertAlmostEqual(self.results.armor_modifiers["CORR"], 0.1 * 1.5)

    def test_zero_armor_keeps_full_damage(self) -> None:
        inputs = CalculationInputs(
            weapon_name=self.weapon.weapon,
            faction="Grineer",
            armor_value=0.0,
            lich_element="",
            valence_base=0.0,
            mods={},
        )
        results = self.calculator.calculate(self.weapon, inputs)
        self.assertAlmostEqual(results.armor_modifiers["RAD"], 1.0)
        self.assertAlmostEqual(results.final_total, 760.0)


class BaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregator = ModAggregator()
        self.calculator = DamageCalculator()
        self.weapon = make_weapon({"SLASH": 100.0})

    def _total_with(self, mods: dict[str, float], faction: str = "Grineer"):
        results = self.calculator.calculate(
            self.weapon,
            CalculationInputs(
                weapon_name=self.weapon.weapon,
                faction=faction,
                armor_value=0.0,
                mods=dict(mods),
            ),
        )
        return results.hud_total_with_bane, results.final_total_with_bane

    def test_bane_value_normalized_to_bonus(self) -> None:
        self.assertAlmostEqual(_bane_bonus(1.3), 0.3)
        self.assertAlmostEqual(_bane_bonus(1.55), 0.55)
        # Percent-style fractional values pass through unchanged.
        self.assertAlmostEqual(_bane_bonus(0.3), 0.3)

    def test_single_bane_multiplies_by_full_factor(self) -> None:
        mods = self.aggregator.aggregate(equipped(("BANE_GRINEER", 1.3)), "Grineer")
        self.assertAlmostEqual(mods["BANE"], 0.3)
        hud_total, final_total = self._total_with(mods)
        self.assertAlmostEqual(hud_total, 130.0)
        self.assertEqual(final_total, 130.0)

    def test_stacked_banes_add_bonuses(self) -> None:
        # Narmer targets take both Grineer and Corpus bane mods. Two maxed
        # +30% banes must total x1.6, never x2.6.
        mods = self.aggregator.aggregate(
            equipped(("BANE_GRINEER", 1.3), ("BANE_CORPUS", 1.3)), "Narmer"
        )
        self.assertAlmostEqual(mods["BANE"], 0.6)
        hud_total, final_total = self._total_with(mods, faction="Narmer")
        # HUD is pre-faction: 100 x 1.6. Final also takes Narmer's 1.5x Slash
        # weakness: 100 x 1.5 x 1.6 = 240.
        self.assertAlmostEqual(hud_total, 160.0)
        self.assertEqual(final_total, 240.0)

    def test_no_bane_leaves_totals_unchanged(self) -> None:
        hud_total, final_total = self._total_with({"BANE": 0.0})
        self.assertAlmostEqual(hud_total, 100.0)
        self.assertEqual(final_total, 100.0)


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


# Independent transcription of the workbook formulas for randomized parity checks.
def _reference_lich(elements, lich_element, mods, base_dmg, valence_multiplier):
    out = {damage_type: 0.0 for damage_type in DAMAGE_TYPES}
    element = (lich_element or "").strip().upper()
    if not element or valence_multiplier <= 0:
        return out
    bonus = base_dmg * valence_multiplier

    def present(code):
        return mods.get(code, 0.0) > 0

    if element == "IMPACT":
        out["IMPACT"] = bonus
    if element == "PUNC":
        out["PUNC"] = bonus
    if element == "SLASH":
        out["SLASH"] = bonus
    if element == "BLAST" or (
        element in {"HEAT", "COLD"}
        and (elements.get("BLAST", 0.0) > 0 or (present("HEAT") and present("COLD")) or present("BLAST"))
    ):
        out["BLAST"] = bonus
    if element == "RAD" or (
        element in {"HEAT", "ELEC"}
        and (elements.get("RAD", 0.0) > 0 or (present("HEAT") and present("ELEC")) or present("RAD"))
    ):
        out["RAD"] = bonus
    if element == "GAS" or (
        element in {"HEAT", "TOXIN"}
        and (elements.get("GAS", 0.0) > 0 or (present("HEAT") and present("TOXIN")) or present("GAS"))
    ):
        out["GAS"] = bonus
    if element == "MAG" or (
        element in {"COLD", "ELEC"}
        and (elements.get("MAG", 0.0) > 0 or (present("COLD") and present("ELEC")) or present("MAG"))
    ):
        out["MAG"] = bonus
    if element == "VIRAL" or (
        element in {"COLD", "TOXIN"}
        and (elements.get("VIRAL", 0.0) > 0 or (present("COLD") and present("TOXIN")) or present("VIRAL"))
    ):
        out["VIRAL"] = bonus
    if element == "CORR" or (
        element in {"ELEC", "TOXIN"}
        and (elements.get("CORR", 0.0) > 0 or (present("ELEC") and present("TOXIN")) or present("CORR"))
    ):
        out["CORR"] = bonus
    if element == "HEAT" and not any(
        (
            elements.get("BLAST", 0.0) > 0,
            elements.get("RAD", 0.0) > 0,
            elements.get("GAS", 0.0) > 0,
            present("HEAT") and present("COLD"),
            present("HEAT") and present("TOXIN"),
            present("HEAT") and present("ELEC"),
            out["BLAST"] > 0,
            out["RAD"] > 0,
            out["GAS"] > 0,
        )
    ):
        out["HEAT"] = bonus
    if element == "COLD" and not any(
        (
            elements.get("BLAST", 0.0) > 0,
            elements.get("MAG", 0.0) > 0,
            elements.get("VIRAL", 0.0) > 0,
            present("HEAT") and present("COLD"),
            present("COLD") and present("ELEC"),
            present("COLD") and present("TOXIN"),
            present("BLAST"),
            present("MAG"),
            present("VIRAL"),
        )
    ):
        out["COLD"] = bonus
    if element == "ELEC" and not any(
        (
            elements.get("RAD", 0.0) > 0,
            elements.get("MAG", 0.0) > 0,
            elements.get("CORR", 0.0) > 0,
            present("HEAT") and present("ELEC"),
            present("COLD") and present("ELEC"),
            present("ELEC") and present("TOXIN"),
            present("RAD"),
            present("MAG"),
            present("CORR"),
        )
    ):
        out["ELEC"] = bonus
    if element == "TOXIN" and not any(
        (
            elements.get("GAS", 0.0) > 0,
            elements.get("VIRAL", 0.0) > 0,
            elements.get("CORR", 0.0) > 0,
            present("HEAT") and present("TOXIN"),
            present("COLD") and present("TOXIN"),
            present("ELEC") and present("TOXIN"),
            present("GAS"),
            present("VIRAL"),
            present("CORR"),
        )
    ):
        out["TOXIN"] = bonus
    return out


def _reference_calculate(elements, dmg, multi, lich_element, valence_base, faction, armor, mods, bane_bonus):
    valence_multiplier = valence_base / dmg if dmg else 0.0
    total = dmg + dmg * valence_multiplier
    quanta = total / 16 if total else 0.0
    lich = _reference_lich(elements, lich_element, mods, dmg, valence_multiplier)
    armor_term = (1 - 0.9 * math.sqrt(max(armor, 0.0) / 2700.0)) if armor > 0 else 1.0
    faction_modifiers = FACTION_MULTIPLIERS[faction]
    hud, final = {}, {}
    for damage_type in DAMAGE_TYPES:
        base = elements.get(damage_type, 0.0) + lich[damage_type]
        if damage_type in PHYSICAL_DAMAGE_TYPES:
            raw = base * (1 + mods.get(damage_type, 0.0))
        else:
            raw = base + total * mods.get(damage_type, 0.0)
        digits = 3 if damage_type == "MAG" else 4
        mod_screen = excel_round(raw / quanta, digits) * quanta
        hud[damage_type] = mod_screen + mod_screen * mods.get("TRUE", 0.0)
        quantized = excel_round(raw / quanta, 0) * quanta
        scaled = excel_round(quantized, 3) * armor_term * faction_modifiers[damage_type]
        final[damage_type] = scaled + scaled * mods.get("TRUE", 0.0)
    hud_total = sum(hud.values()) * multi
    final_total = excel_round(sum(final.values()), 0)
    return (
        lich,
        hud,
        final,
        hud_total * (1 + bane_bonus) if bane_bonus > 0 else hud_total,
        excel_round(final_total * (1 + bane_bonus), 0) if bane_bonus > 0 else final_total,
    )


class RandomizedParityTests(unittest.TestCase):
    def test_engine_matches_workbook_formulas_across_random_builds(self) -> None:
        rng = random.Random(42)
        calculator = DamageCalculator()
        for _ in range(500):
            components = rng.sample(DAMAGE_TYPES, rng.randint(1, 6))
            elements = {component: rng.uniform(5.0, 400.0) for component in components}
            dmg = sum(elements.values())
            multi = rng.choice([1.0, 1.0, 2.0, 12.0])
            # The workbook hardcodes lich VOID to zero (Q12), so exclude it here.
            lich_element = rng.choice(
                [""] + [damage_type for damage_type in DAMAGE_TYPES if damage_type != "VOID"]
            )
            valence_base = rng.uniform(0.0, 0.6) * dmg if lich_element else 0.0
            faction = rng.choice(list(FACTION_MULTIPLIERS))
            armor = rng.choice([0, 0, 100, 250, 500, 1500, 2700])
            mods = {damage_type: rng.choice([0, 0, 0.15, 0.6, 0.9, 1.2, 1.65, 3.3]) for damage_type in DAMAGE_TYPES}
            mods["TRUE"] = rng.choice([0, 0, 0.5, 1.65])
            bane_bonus = rng.choice([0, 0, 0.05, 0.3, 0.55])
            mods["BANE"] = bane_bonus

            weapon = make_weapon(elements, dmg=dmg, multi=multi)
            results = calculator.calculate(
                weapon,
                CalculationInputs(
                    weapon_name=weapon.weapon,
                    faction=faction,
                    armor_value=armor,
                    lich_element=lich_element,
                    valence_base=valence_base,
                    mods=dict(mods),
                ),
            )
            ref_lich, ref_hud, ref_final, ref_hud_bane, ref_final_bane = _reference_calculate(
                elements, dmg, multi, lich_element, valence_base, faction, armor, mods, bane_bonus
            )
            self.assertEqual(results.lich_damage, ref_lich)
            for damage_type in DAMAGE_TYPES:
                self.assertAlmostEqual(
                    results.hud_damage_by_type[damage_type], ref_hud[damage_type], places=9
                )
                self.assertAlmostEqual(
                    results.final_damage_by_type[damage_type], ref_final[damage_type], places=9
                )
            self.assertAlmostEqual(results.hud_total_with_bane, ref_hud_bane, places=9)
            self.assertAlmostEqual(results.final_total_with_bane, ref_final_bane, places=9)


if __name__ == "__main__":
    unittest.main()
