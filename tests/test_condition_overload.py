"""Tests for the GunCO (Condition Overload mechanic) tables and resolver.

Rule-level expectations are pinned to rows read directly from
wiki.warframe.com/w/Condition_Overload_(Mechanic) (2026-10-27) and its
cross-referenced TS rule table (source/conditionOverload.ts).
"""
from __future__ import annotations

import re
import unittest
from collections import Counter

from modules.condition_overload import (
    MODE_ADD,
    MODE_MULTIPLY,
    MODE_NONE,
    SOURCE_DEFAULT,
    SOURCE_SHEET,
    SOURCE_WIKI,
    apply_co,
    co_bonus_for_statuses,
    load_gunco_dataset,
    multiplicative_rules,
    resolve_co_behavior,
)


class GuncoDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_gunco_dataset()

    def test_dataset_structure(self) -> None:
        self.assertIn("stacking_modes", self.data)
        self.assertIn("co_sources", self.data)
        self.assertGreater(len(self.data["rules"]), 90)
        for rule in self.data["rules"]:
            self.assertIn(rule["mode"], {"multiply", "add", "none"})
            self.assertIn(rule["section"],
                          {"primary", "secondary", "melee", "exalted",
                           "archgun", "robotic", "amp"})
            self.assertIn(rule["source"], {"wiki", "gunco_sheet"})
            self.assertTrue(rule["weapons"])
            self.assertGreater(rule["scale"], 0.0)
            re.compile(rule["attack_pattern"])  # every pattern must compile

    def test_rule_keys_unique(self) -> None:
        keys = [
            (tuple(r["weapons"]), r["attack_pattern"], r["section"])
            for r in self.data["rules"]
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_expected_rule_counts(self) -> None:
        modes = Counter(r["mode"] for r in self.data["rules"])
        self.assertEqual(modes["multiply"], 77)
        self.assertEqual(modes["add"], 25)
        self.assertEqual(modes["none"], 16)

    def test_wiki_rows_missing_from_ts_are_recovered(self) -> None:
        """Rows on the wiki (2026-10) absent from the TS cross-reference."""
        cases = [
            ("Zenith", "Alt-fire Disk Bonk", MODE_MULTIPLY),
            ("Sporelacer", "Normal Attack", MODE_MULTIPLY),  # primary chamber
            ("Tombfinger", "Normal Attack", MODE_MULTIPLY),
            ("Ballistica Prime", "Incarnon Mode", MODE_MULTIPLY),
            ("Catabolyst", "Partial Reload Impact", MODE_MULTIPLY),
            ("Catabolyst", "Reload From Empty Impact", MODE_MULTIPLY),
            ("Mk1-Kunai", "Incarnon Mode", MODE_MULTIPLY),
            ("Castanas", "Normal Attack", MODE_NONE),
            ("Sancti Castanas", "Embedded Detonation", MODE_NONE),
            ("Kompressa Prime", "Radial Attack", MODE_NONE),
            ("Scyotid", "Alt-Fire Grab", MODE_NONE),
            ("Vadarya Prime", "Primary Fire Lightning Strikes", MODE_NONE),
        ]
        for weapon, attack, mode in cases:
            behavior = resolve_co_behavior(weapon, attack)
            self.assertEqual(behavior.mode, mode, f"{weapon} {attack}")
            self.assertEqual(behavior.source, SOURCE_WIKI)
            self.assertTrue(behavior.matched)

    def test_sporelacer_kitgun_section_collision(self) -> None:
        # same chamber name exists in both slots; section disambiguates
        primary = resolve_co_behavior("Sporelacer", "Normal Attack",
                                      section="primary")
        self.assertEqual(primary.mode, MODE_MULTIPLY)
        secondary = resolve_co_behavior("Sporelacer", "Normal Attack",
                                        section="secondary")
        self.assertEqual(secondary.mode, MODE_ADD)
        self.assertAlmostEqual(secondary.scale, 0.63)
        bomblet = resolve_co_behavior("Sporelacer", "Bomblet Impact",
                                      section="secondary")
        self.assertEqual(bomblet.mode, MODE_ADD)
        self.assertAlmostEqual(bomblet.scale, 6.33)
        # without a section hint the first (primary) match wins
        self.assertEqual(resolve_co_behavior("Sporelacer", "Normal Attack").mode,
                         MODE_MULTIPLY)

    def test_co_sources_known_values(self) -> None:
        by_name = {s["name"]: s for s in self.data["co_sources"]}
        self.assertEqual(by_name["Condition Overload"]["per_status"], 0.80)
        self.assertEqual(by_name["Galvanized Shot"]["cap"], 1.20)
        self.assertEqual(by_name["Galvanized Aptitude"]["cap"], 0.80)
        self.assertEqual(by_name["Secondary Shiver"]["per_status"], 0.45)
        self.assertIn("Catalyze", self.data["excluded_sources"][0])


class ResolverWikiPinnedTests(unittest.TestCase):
    """Explicit catalog rows, cross-checked against the wiki Attack Catalog."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_gunco_dataset()

    def test_arca_plasmor_projectile_multiplies(self) -> None:
        for weapon in ("Arca Plasmor", "Tenet Arca Plasmor"):
            behavior = resolve_co_behavior(weapon, "Normal Attack")
            self.assertEqual(behavior.mode, MODE_MULTIPLY)
            self.assertTrue(behavior.matched)
            self.assertEqual(behavior.source, SOURCE_WIKI)

    def test_acceltra_rocket_additive_with_scale(self) -> None:
        behavior = resolve_co_behavior("Acceltra", "Rocket Impact")
        self.assertEqual(behavior.mode, MODE_ADD)
        self.assertAlmostEqual(behavior.scale, 0.743)
        self.assertIn("26 damage", behavior.note)

    def test_ballistica_charged_uses_uncharged_base(self) -> None:
        behavior = resolve_co_behavior("Ballistica", "Charged Shot")
        self.assertEqual(behavior.mode, MODE_ADD)
        self.assertAlmostEqual(behavior.scale, 0.25)
        self.assertIn("uncharged base", behavior.note)

    def test_stug_gets_nothing(self) -> None:
        behavior = resolve_co_behavior("Stug", "Blob Impact")
        self.assertEqual(behavior.mode, MODE_NONE)

    def test_azima_turret_gets_nothing(self) -> None:
        behavior = resolve_co_behavior("Azima", "Turret Bullets")
        self.assertEqual(behavior.mode, MODE_NONE)
        self.assertIn("Bug", behavior.note)

    def test_cyanex_direct_hit_multiplies_but_aoe_does_not(self) -> None:
        direct = resolve_co_behavior("Cyanex", "Normal Attack")
        self.assertEqual(direct.mode, MODE_MULTIPLY)
        self.assertEqual(direct.source, SOURCE_WIKI)
        aoe = resolve_co_behavior("Cyanex", "Rocket Explosion AoE", is_aoe=True)
        self.assertEqual(aoe.mode, MODE_NONE)
        self.assertFalse(aoe.matched)

    def test_sheet_sourced_rows_are_flagged(self) -> None:
        bramma = resolve_co_behavior("Kuva Bramma", "Cluster Bomb Contact")
        self.assertEqual(bramma.mode, MODE_ADD)
        self.assertAlmostEqual(bramma.scale, 4.92)
        self.assertEqual(bramma.source, SOURCE_SHEET)
        sonicor = resolve_co_behavior("Sonicor", "Projectile Wave")
        self.assertEqual(sonicor.mode, MODE_NONE)
        self.assertEqual(sonicor.source, SOURCE_SHEET)

    def test_melee_wiki_rows(self) -> None:
        syam = resolve_co_behavior("Syam", "Heavy Attack Wave 1")
        self.assertEqual((syam.mode, syam.scale), (MODE_MULTIPLY, 1.0))
        agendus = resolve_co_behavior("Tenet Agendus", "Heavy Attack Wave 2")
        self.assertEqual(agendus.mode, MODE_MULTIPLY)
        self.assertAlmostEqual(agendus.scale, 0.2)
        contagion = resolve_co_behavior("Exodia Contagion", "Aerial Projectile")
        self.assertEqual(contagion.mode, MODE_MULTIPLY)
        self.assertIn("Zaw", contagion.note)

    def test_archgun_robotic_amp_rows(self) -> None:
        self.assertEqual(resolve_co_behavior("Grattler", "Normal Attack").mode,
                         MODE_MULTIPLY)
        self.assertEqual(resolve_co_behavior("Velocitus", "Charged Attack").mode,
                         MODE_MULTIPLY)
        cryotra = resolve_co_behavior("Cryotra", "Normal Attack")
        self.assertEqual(cryotra.mode, MODE_MULTIPLY)
        cryotra_rule = next(r for r in self.data["rules"]
                            if "Cryotra" in r["weapons"] and r["mode"] == MODE_MULTIPLY)
        self.assertEqual(cryotra_rule["section"], "robotic")
        self.assertEqual(resolve_co_behavior("Shwaak Prism", "Normal Attack").mode,
                         MODE_MULTIPLY)
        self.assertEqual(resolve_co_behavior("Phahd Scaffold", "Normal Attack").mode,
                         MODE_MULTIPLY)

    def test_exalted_umbra_heavy_waves_multiply(self) -> None:
        behavior = resolve_co_behavior("Exalted Umbra Blade", "Heavy Waves")
        self.assertEqual(behavior.mode, MODE_MULTIPLY)
        rule = next(r for r in self.data["rules"]
                    if "Exalted Umbra Blade" in r["weapons"])
        self.assertEqual(rule["section"], "exalted")

    def test_default_resolution(self) -> None:
        plain = resolve_co_behavior("Braton Prime", "Normal Attack")
        self.assertEqual((plain.mode, plain.scale, plain.matched),
                         (MODE_ADD, 1.0, False))
        self.assertEqual(plain.source, SOURCE_DEFAULT)
        projectile_aoe = resolve_co_behavior("Some Launcher", "Rocket Explosion",
                                             is_aoe=True)
        self.assertEqual(projectile_aoe.mode, MODE_NONE)
        hitscan_aoe = resolve_co_behavior("Some Beam", "Beam Radial",
                                          hitscan_aoe=True)
        self.assertEqual(hitscan_aoe.mode, MODE_ADD)
        self.assertIn("directly", hitscan_aoe.note)


class FormulaTests(unittest.TestCase):
    """Wiki Math section: base 100, +100% CO, Serration x2.65 worked example."""

    def test_additive_formula(self) -> None:
        # 100 x (2.65 + 1.00) = 365
        self.assertAlmostEqual(
            apply_co(100.0, co_bonus=1.0, damage_bonus_mult=2.65, mode=MODE_ADD),
            365.0)

    def test_multiplicative_formula(self) -> None:
        # 100 x 2.65 x (1 + 1.00) = 530
        self.assertAlmostEqual(
            apply_co(100.0, co_bonus=1.0, damage_bonus_mult=2.65,
                     mode=MODE_MULTIPLY),
            530.0)

    def test_none_formula_ignores_co(self) -> None:
        self.assertAlmostEqual(
            apply_co(100.0, co_bonus=1.0, damage_bonus_mult=2.65, mode=MODE_NONE),
            265.0)

    def test_additive_scale_ballistica_charged(self) -> None:
        # charged Ballistica: CO term is 25% of the +100% bonus
        self.assertAlmostEqual(
            apply_co(100.0, co_bonus=1.0, damage_bonus_mult=2.65,
                     mode=MODE_ADD, scale=0.25),
            290.0)

    def test_multiplicative_other_multipliers_apply(self) -> None:
        self.assertAlmostEqual(
            apply_co(100.0, co_bonus=0.8, damage_bonus_mult=2.65,
                     other_multipliers=2.0, mode=MODE_MULTIPLY),
            100.0 * 2.65 * 1.8 * 2.0)

    def test_co_bonus_for_statuses_and_caps(self) -> None:
        self.assertAlmostEqual(co_bonus_for_statuses(0.8, 3), 2.4)  # Condition Overload
        self.assertAlmostEqual(co_bonus_for_statuses(0.4, 3, cap=0.8), 1.2)
        self.assertAlmostEqual(co_bonus_for_statuses(0.8, 3, cap=0.8), 2.4)
        self.assertAlmostEqual(co_bonus_for_statuses(0.8, 3, cap=0.4), 1.2)
        self.assertAlmostEqual(co_bonus_for_statuses(0.4, 1, cap=1.2), 0.4)
        self.assertEqual(co_bonus_for_statuses(0.45, 0), 0.0)
        with self.assertRaises(ValueError):
            co_bonus_for_statuses(0.4, -1)

    def test_multiplicative_scale_applies_to_co_term(self) -> None:
        # E.g. Syam heavy wave 2 has a 0.2 multiplicative CO scale.
        self.assertAlmostEqual(apply_co(100, 1.0, 2.0, mode=MODE_MULTIPLY,
                                         scale=0.2), 240.0)

    def test_invalid_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            apply_co(100.0, 1.0, 2.0, mode="sideways")

    def test_multiplicative_rule_index(self) -> None:
        primaries = multiplicative_rules("primary")
        self.assertTrue(any(r["weapons"][0] == "Arca Plasmor" for r in primaries))
        total = len(multiplicative_rules())
        self.assertGreater(total, 60)


if __name__ == "__main__":
    unittest.main()
