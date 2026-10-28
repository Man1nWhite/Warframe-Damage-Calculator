import unittest

from modules.calculator import DamageCalculator
from modules.mod_engine import ModAggregator
from modules.models import CalculationInputs, EquippedMod, Mod, ModEffect, Weapon
from modules.crit import quantize_crit_multiplier
from modules.jat_kittag_slam_analysis import (
    BUILD_BY_KEY,
    BUILDS,
    COMMON_MODS,
    COMMON_WITHOUT_PRESSURE,
    R3_HEAVY_ATTACK_DAMAGE,
    R3_MELEE_DAMAGE,
    R3_SLAM_DAMAGE,
    combo_sequence,
    combo_tier,
    direct_sequence_average,
    first_recovery_time,
    magnetic_break_electric_total,
    probability_at_least_one,
    probability_both,
    probability_three,
    sustainable_interval,
)


class BuildTests(unittest.TestCase):
    def test_every_build_has_eight_unique_mods_and_at_most_one_riven(self):
        self.assertEqual(len(BUILD_BY_KEY), len(BUILDS))
        for build in BUILDS:
            with self.subTest(build=build.key):
                self.assertEqual(len(build.weapon_mods), 8)
                self.assertEqual(len(set(build.weapon_mods)), 8)
                self.assertLessEqual(sum(slot.startswith("Riven:")
                                         for slot in build.weapon_mods), 1)
                self.assertIn(build.fixed_mods, (COMMON_MODS, COMMON_WITHOUT_PRESSURE))
                self.assertEqual(build.pressure_point_bonus,
                                 1.65 if "Primed Pressure Point" in build.weapon_mods else 0.0)
                self.assertGreaterEqual(build.efficiency, 0.5)
                self.assertLessEqual(build.efficiency, 0.9)
                self.assertAlmostEqual(sum(build.proc_share(kind)
                                           for kind in build.types), 1.0)

    def test_requested_fever_focus_riven_has_no_hidden_pressure_point(self):
        b = BUILD_BY_KEY["focus_fever_gas_cold_damage"]
        self.assertEqual(b.weapon_mods, (
            "Seismic Wave", "Galvanized Elementalist", "Galvanized Reflex",
            "Vulcan Blitz", "Galvanized Steel", "Focus Energy",
            "Riven: Gas / Cold / Melee Damage", "Primed Fever Strike",
        ))
        self.assertEqual(b.pressure_point_bonus, 0.0)
        self.assertAlmostEqual(b.melee_damage_bonus, R3_MELEE_DAMAGE)
        self.assertEqual(set(b.types), {"BLAST", "GAS", "MAGNETIC", "TOXIN"})
        self.assertAlmostEqual(b.types["MAGNETIC"], 1.6125)
        self.assertAlmostEqual(b.types["TOXIN"], 1.65)
        self.assertAlmostEqual(b.gas_bonus, 1.0125)
        self.assertAlmostEqual(b.efficiency, 0.9)
        self.assertAlmostEqual(b.crit_chance, 0.48)
        self.assertAlmostEqual(b.probability_of("GAS"), 0.37211017, places=7)
        self.assertAlmostEqual(b.probability_of("MAGNETIC"), 0.54740228, places=7)
        self.assertAlmostEqual(b.probability_of("TOXIN"), 0.55729449, places=7)
        self.assertAlmostEqual(b.probability_of_both("GAS", "MAGNETIC"), 0.14676982, places=7)
        self.assertAlmostEqual(b.probability_of_both("GAS", "TOXIN"), 0.14992698, places=7)
        self.assertAlmostEqual(b.probability_of_three("GAS", "MAGNETIC", "TOXIN"),
                               0.022023815, places=7)

    def test_focus_gas_crit_crit_damage_build_has_electricity_not_toxin(self):
        b = BUILD_BY_KEY["focus_gas_cc_cd"]
        self.assertEqual(len(b.weapon_mods), 8)
        self.assertIn("Primed Pressure Point", b.weapon_mods)
        self.assertNotIn("Primed Fever Strike", b.weapon_mods)
        self.assertEqual(set(b.types), {"BLAST", "GAS", "ELECTRICITY"})
        self.assertAlmostEqual(b.crit_chance, 1.0875)
        # Includes the Wiki's quantized base critical multiplier.
        self.assertAlmostEqual(b.crit_multiplier, quantize_crit_multiplier(2.0) * 3.2125)
        self.assertAlmostEqual(b.average_crit_multiplier, 6.901393772893773)
        self.assertAlmostEqual(b.efficiency, 0.9)
        self.assertAlmostEqual(b.probability_of("GAS"), 0.6539904302)
        self.assertAlmostEqual(b.probability_of("ELECTRICITY"), 0.4338414795)
        self.assertAlmostEqual(b.probability_of_both("GAS", "ELECTRICITY"), 0.21626194)
        a = BUILD_BY_KEY["focus_fever_gas_cold_damage"]
        self.assertAlmostEqual(b.direct_average(5) / a.direct_average(5),
                               1.195917770801871)

    def test_fever_focus_riven_damage_vs_crit_uses_no_pressure_for_either(self):
        damage = BUILD_BY_KEY["focus_fever_gas_cold_damage"]
        crit = BUILD_BY_KEY["focus_fever_gas_cold_cc"]
        self.assertEqual(crit.pressure_point_bonus, 0.0)
        self.assertEqual(damage.types, crit.types)
        self.assertAlmostEqual(crit.crit_chance, 1.0875)
        self.assertAlmostEqual(damage.direct_average(5) / crit.direct_average(5),
                               1.598445908727162)
        old_gas = BUILD_BY_KEY["gas_eff_cc"]
        self.assertAlmostEqual(damage.direct_average(5) / old_gas.direct_average(5),
                               0.8712703066437362)

    def test_focus_energy_combines_toxin_and_electricity(self):
        b = BUILD_BY_KEY["focus_energy"]
        self.assertEqual(b.types, {"BLAST": 1.0, "CORROSIVE": 2.25})
        self.assertAlmostEqual(b.efficiency, 0.90)
        self.assertAlmostEqual(b.probability_of("CORROSIVE"), 0.9184347, places=6)
        self.assertEqual(b.probability_of("TOXIN"), 0.0)

    def test_focus_radon_retains_separate_toxin_and_radiation(self):
        b = BUILD_BY_KEY["focus_radon"]
        self.assertEqual(b.types, {"BLAST": 1.0, "TOXIN": 1.65, "RADIATION": 0.60})
        self.assertAlmostEqual(b.efficiency, 0.90)
        self.assertAlmostEqual(b.probability_of("TOXIN"), 0.7822427, places=6)

    def test_volcanic_and_molten_both_form_gas_not_toxin(self):
        volatile = BUILD_BY_KEY["volcanic_edge"]
        molten = BUILD_BY_KEY["molten_impact"]
        self.assertEqual(volatile.types, {"BLAST": 1.0, "GAS": 2.25})
        self.assertEqual(molten.types, {"BLAST": 1.0, "GAS": 2.55})
        self.assertEqual(volatile.gas_bonus, 0.0)  # no literal +Gas mod
        self.assertEqual(molten.gas_bonus, 0.0)
        self.assertAlmostEqual(volatile.status_rolls, 2.8)
        self.assertAlmostEqual(volatile.probability_of("GAS"), 0.95776, places=5)
        self.assertAlmostEqual(molten.probability_of("GAS"), 0.93205, places=5)
        self.assertEqual(volatile.efficiency, 0.5)
        self.assertEqual(molten.efficiency, 0.5)

    def test_spliced_gas_plus_toxin_and_efficiency_riven_fits(self):
        b = BUILD_BY_KEY["gas_eff_cc"]
        self.assertEqual(b.types, {"BLAST": 1.0, "TOXIN": 1.65, "GAS": 1.0125})
        self.assertEqual(b.flex_slots[0], "Primed Fever Strike")
        self.assertAlmostEqual(b.gas_bonus, 1.0125)
        self.assertAlmostEqual(b.efficiency, 0.90)  # cap, not 132.6%
        self.assertAlmostEqual(b.probability_of("GAS"), 0.50542, places=5)
        self.assertAlmostEqual(b.probability_of("TOXIN"), 0.72527, places=5)
        self.assertAlmostEqual(b.probability_of_both("GAS", "TOXIN"), 0.29440, places=5)

    def test_fever_plus_spliced_gas_cold_crit_is_viral_not_magnetic(self):
        b = BUILD_BY_KEY["gas_cold_cc"]
        self.assertEqual(set(b.types), {"BLAST", "GAS", "VIRAL"})
        self.assertAlmostEqual(b.types["GAS"], 1.0125)
        self.assertAlmostEqual(b.types["VIRAL"], 2.6625)
        self.assertEqual(b.efficiency, 0.50)
        self.assertAlmostEqual(b.crit_chance, 1.0875)
        self.assertAlmostEqual(b.gas_bonus, 1.0125)
        self.assertAlmostEqual(b.probability_of("GAS"), 0.41283417, places=7)
        self.assertAlmostEqual(b.probability_of("VIRAL"), 0.83579384, places=7)
        self.assertAlmostEqual(b.probability_of_both("GAS", "VIRAL"), 0.28718929, places=7)
        self.assertEqual(b.probability_of("MAGNETIC"), 0.0)
        prior = BUILD_BY_KEY["gas_eff_cc"]
        self.assertAlmostEqual(b.direct_average(5) / prior.direct_average(5), 1.2735042735)
        self.assertAlmostEqual(direct_sequence_average(b, 0.65)
                               / direct_sequence_average(prior, 0.65), 0.8596153846)

    def test_spliced_gas_cold_electric_keeps_toxin_but_not_crit_or_efficiency(self):
        b = BUILD_BY_KEY["gas_cold_electric"]
        self.assertEqual(b.flex_slots[0], "Riven: Gas / Cold / Electricity")
        self.assertEqual(set(b.types), {"BLAST", "GAS", "MAGNETIC", "TOXIN"})
        self.assertAlmostEqual(b.types["MAGNETIC"], 2.025)
        self.assertEqual(b.efficiency, 0.50)
        self.assertAlmostEqual(b.crit_chance, 0.48)
        self.assertAlmostEqual(b.probability_of("MAGNETIC"), 0.61484943, places=7)

    def test_spliced_magnetic_heat_eff_keeps_fever_and_reaches_efficiency_cap(self):
        b = BUILD_BY_KEY["mag_heat_eff"]
        self.assertEqual(set(b.types), {"BLAST", "GAS", "MAGNETIC"})
        self.assertAlmostEqual(b.types["GAS"], 2.6625)
        self.assertAlmostEqual(b.types["MAGNETIC"], 1.0125)
        self.assertAlmostEqual(b.efficiency, 0.90)
        self.assertAlmostEqual(b.crit_chance, 0.48)
        self.assertEqual(b.gas_bonus, 0.0)  # Gas is made from Heat + Toxin.
        self.assertAlmostEqual(b.probability_of("GAS"), 0.83579384, places=7)
        self.assertAlmostEqual(b.probability_of("MAGNETIC"), 0.41283417, places=7)

    def test_spliced_magnetic_heat_crit_loses_efficiency_not_fever(self):
        b = BUILD_BY_KEY["mag_heat_cc"]
        efficient = BUILD_BY_KEY["mag_heat_eff"]
        self.assertEqual(b.types, efficient.types)
        self.assertEqual(b.gas_bonus, 0.0)
        self.assertEqual(b.efficiency, 0.50)
        self.assertAlmostEqual(b.crit_chance, 1.0875)
        self.assertEqual(b.flex_slots[0], "Primed Fever Strike")

    def test_focus_and_spliced_gas_cold_crit_fits_but_drops_fever(self):
        b = BUILD_BY_KEY["focus_gas_cold_cc"]
        self.assertEqual(b.flex_slots[0], "Focus Energy")
        self.assertEqual(set(b.types), {"BLAST", "GAS", "MAGNETIC"})
        self.assertAlmostEqual(b.types["MAGNETIC"], 1.6125)
        self.assertAlmostEqual(b.efficiency, 0.90)
        self.assertAlmostEqual(b.crit_chance, 1.0875)
        self.assertAlmostEqual(b.probability_of("MAGNETIC"), 0.71920422, places=7)
        self.assertAlmostEqual(b.probability_of("GAS"), 0.50962082, places=7)
        self.assertAlmostEqual(b.probability_of_both("GAS", "MAGNETIC"), 0.29390356, places=7)

    def test_unspliced_dual_element_riven_before_focus_forms_gas_and_electricity(self):
        b = BUILD_BY_KEY["focus_gas_electric_cc"]
        self.assertEqual(b.flex_slots,
                         ("Riven: Heat / Toxin / Crit Chance", "Focus Energy"))
        self.assertEqual(set(b.types), {"BLAST", "GAS", "ELECTRICITY"})
        self.assertAlmostEqual(b.types["GAS"], 2.025)
        self.assertAlmostEqual(b.types["ELECTRICITY"], 0.60)
        self.assertAlmostEqual(b.efficiency, 0.9)
        self.assertEqual(b.gas_bonus, 0.0)
        self.assertAlmostEqual(b.probability_of("GAS"), 0.82695, places=5)
        self.assertAlmostEqual(b.probability_of("ELECTRICITY"), 0.32669, places=5)
        self.assertAlmostEqual(b.probability_of_both("GAS", "ELECTRICITY"), 0.21872, places=5)

    def test_spliced_gas_stays_separate_when_riven_toxin_forms_corrosive(self):
        b = BUILD_BY_KEY["gas_corrosive_cc"]
        self.assertEqual(b.flex_slots[0], "Focus Energy")
        self.assertEqual(set(b.types), {"BLAST", "CORROSIVE", "GAS"})
        self.assertAlmostEqual(b.types["CORROSIVE"], 1.6125)
        self.assertAlmostEqual(b.types["GAS"], 1.0125)
        self.assertNotIn("TOXIN", b.types)
        self.assertAlmostEqual(b.efficiency, 0.90)
        self.assertAlmostEqual(b.probability_of("GAS"), 0.50962, places=5)
        self.assertAlmostEqual(b.probability_of("CORROSIVE"), 0.71920, places=5)
        self.assertAlmostEqual(b.probability_of_both("GAS", "CORROSIVE"), 0.29390, places=5)

    def test_volcanic_toxin_riven_increases_normal_proc_count_not_direct_hit(self):
        edge = BUILD_BY_KEY["toxin_eff_cc_edge"]
        fever = BUILD_BY_KEY["heat_eff_cc"]
        self.assertEqual(edge.flex_slots[0], "Volcanic Edge")
        self.assertEqual(set(edge.types), {"BLAST", "GAS"})
        self.assertAlmostEqual(edge.efficiency, 0.9)
        self.assertAlmostEqual(edge.status_rolls, 2.8)
        self.assertAlmostEqual(edge.status_rolls * edge.proc_share("GAS"), 1.72823, places=5)
        self.assertAlmostEqual(fever.status_rolls * fever.proc_share("GAS"), 1.59932, places=5)
        self.assertAlmostEqual(edge.probability_of_both("GAS", "BLAST"), 0.66152, places=5)
        self.assertAlmostEqual(fever.probability_of_both("GAS", "BLAST"), 0.43667, places=5)
        self.assertLess(edge.direct_average(5), fever.direct_average(5))
        self.assertEqual(edge.gas_bonus, 0.0)
        self.assertEqual(fever.gas_bonus, 0.0)

    def test_unspliced_gas_and_spliced_gas_have_distinct_dot_bonus(self):
        regular = BUILD_BY_KEY["heat_eff_cc"]
        spliced = BUILD_BY_KEY["gas_eff_cc"]
        self.assertAlmostEqual(regular.types["GAS"], 2.6625)
        self.assertEqual(regular.gas_bonus, 0.0)
        self.assertAlmostEqual(spliced.gas_bonus, 1.0125)
        self.assertNotIn("TOXIN", regular.types)
        self.assertIn("TOXIN", spliced.types)
        self.assertGreater(regular.probability_of("GAS"), spliced.probability_of("GAS"))

    def test_crit_and_status_assumptions(self):
        base = BUILD_BY_KEY["focus_energy"]
        crit = BUILD_BY_KEY["gas_eff_cc"]
        self.assertAlmostEqual(base.crit_chance, 0.48)
        # Wiki Critical Hit: the base multiplier is quantized before mods.
        self.assertAlmostEqual(base.crit_multiplier, quantize_crit_multiplier(2.0) * 2.2)
        self.assertAlmostEqual(base.average_crit_multiplier, 2.6325157509157506)
        self.assertAlmostEqual(base.status_rolls, 2.2)
        self.assertAlmostEqual(crit.crit_chance, 1.0875)
        self.assertAlmostEqual(crit.average_crit_multiplier, 4.698668498168498)
        self.assertAlmostEqual(crit.average_crit_multiplier / base.average_crit_multiplier,
                               1.7848586457779076, places=6)

    def test_riven_crit_damage_vs_melee_damage_direct_only(self):
        crit_damage = BUILD_BY_KEY["normal_eff_cc_cd"]
        melee_damage = BUILD_BY_KEY["normal_eff_cc_damage"]
        self.assertAlmostEqual(crit_damage.crit_multiplier,
                               quantize_crit_multiplier(2.0) * 3.2125)
        self.assertAlmostEqual(crit_damage.average_crit_multiplier, 6.901393772893773)
        self.assertGreater(melee_damage.direct_average(5), crit_damage.direct_average(5))
        self.assertEqual(melee_damage.types, crit_damage.types)

    def test_spliced_slam_and_heavy_bonuses_use_different_damage_brackets(self):
        base = BUILD_BY_KEY["status_eff_cc"]
        slam = BUILD_BY_KEY["slam_eff_cc"]
        heavy = BUILD_BY_KEY["heavy_eff_cc"]
        self.assertAlmostEqual(R3_SLAM_DAMAGE, 1.346625)
        self.assertAlmostEqual(R3_HEAVY_ATTACK_DAMAGE, 1.346625)
        self.assertAlmostEqual(slam.direct_average(5) / base.direct_average(5),
                               (3.0 + R3_SLAM_DAMAGE) / 3.0)
        self.assertAlmostEqual(heavy.direct_average(5) / base.direct_average(5),
                               (2.65 + R3_HEAVY_ATTACK_DAMAGE) / 2.65)
        self.assertGreater(heavy.direct_average(5), slam.direct_average(5))

    def test_direct_only_comparison_and_grineer_type_weakness(self):
        focus = BUILD_BY_KEY["focus_energy"]
        gas_toxin = BUILD_BY_KEY["gas_eff_cc"]
        gas_corrosive = BUILD_BY_KEY["gas_corrosive_cc"]
        self.assertAlmostEqual(gas_toxin.direct_average(5) / focus.direct_average(5),
                               2.00797, places=4)
        self.assertAlmostEqual(gas_corrosive.direct_average(5) / focus.direct_average(5),
                               1.99080, places=4)
        grineer = {"CORROSIVE": 1.5}
        self.assertAlmostEqual(gas_toxin.direct_average(5, faction_types=grineer)
                               / focus.direct_average(5, faction_types=grineer),
                               1.49163, places=4)
        self.assertAlmostEqual(gas_corrosive.direct_average(5, faction_types=grineer)
                               / focus.direct_average(5, faction_types=grineer),
                               1.81036, places=4)
        # Faction-type weakness changes direct damage, not proc weighting.
        self.assertAlmostEqual(gas_corrosive.probability_of("CORROSIVE"), 0.71920, places=5)

    def test_direct_sequence_uses_tier_each_slam(self):
        b = BUILD_BY_KEY["volcanic_edge"]
        five = b.direct_average(5)
        # 0.65 s => 5, 4, 3, 3, 3, 3, 3, 3 (mean tier 3.375).
        self.assertAlmostEqual(direct_sequence_average(b, 0.65) / five, 3.375 / 5)
        initial_combo = BUILD_BY_KEY["normal_eff_cc_initial"]
        self.assertAlmostEqual(direct_sequence_average(initial_combo, 0.65)
                               / initial_combo.direct_average(5), 6 / 5)
        with self.assertRaises(ValueError):
            direct_sequence_average(b, 0.65, 0)


class ElementOrderIntegrationTests(unittest.TestCase):
    """Check the recommendation against the project's ordered-element resolver."""

    @staticmethod
    def equipped(name, pairs):
        mod = Mod(unique_name="/test/" + name, name=name, mod_type="", compat_name="",
                  polarity="", rarity="", fusion_limit=0, base_drain=0,
                  description="", effect_summary="", supported=True)
        effects = [ModEffect(code=kind, value=value, text="", position=i)
                   for i, (kind, value) in enumerate(pairs)]
        return EquippedMod(mod=mod, rank=0, effects=effects)

    def calculate(self, slots):
        weapon = Weapon(weapon="Jat Heavy Slam Fixture", unique_name="/test/jat",
                        product_category="Melee", slot_group="MELEE", dmg=600.0,
                        critchan=0.15, critmult=2.0, statchan=1.0, firerate=1.0,
                        multi=1.0, damage={"BLAST": 600.0})
        inputs = CalculationInputs(weapon_name=weapon.weapon, faction="Grineer",
                                   armor_value=0.0,
                                   mods=ModAggregator().aggregate(slots, "Grineer"),
                                   equipped_mods=slots)
        return DamageCalculator().calculate(weapon, inputs).hud_damage_by_type

    def test_dual_element_riven_must_precede_focus_energy_for_gas_electric(self):
        riven = self.equipped("Jat Kittag Riven", [("HEAT", 1.0125), ("TOXIN", 1.0125)])
        focus = self.equipped("Focus Energy", [("ELEC", 0.60)])
        gas_first = self.calculate([riven, focus])
        self.assertAlmostEqual(gas_first["BLAST"], 600)
        self.assertAlmostEqual(gas_first["GAS"], 1215)
        self.assertAlmostEqual(gas_first["ELEC"], 360)
        self.assertEqual(gas_first["CORR"], 0)
        focus_first = self.calculate([focus, riven])
        self.assertAlmostEqual(focus_first["CORR"], 967.5)
        self.assertAlmostEqual(focus_first["HEAT"], 607.5)
        self.assertEqual(focus_first["GAS"], 0)

    def test_fever_cold_and_spliced_gas_combine_into_viral(self):
        riven = self.equipped("Jat Kittag Riven", [("GAS", 1.0125), ("COLD", 1.0125)])
        fever = self.equipped("Primed Fever Strike", [("TOXIN", 1.65)])
        for slots in ([riven, fever], [fever, riven]):
            with self.subTest(slots=[s.mod.name for s in slots]):
                types = self.calculate(slots)
                self.assertAlmostEqual(types["BLAST"], 600)
                self.assertAlmostEqual(types["GAS"], 607.5)
                self.assertAlmostEqual(types["VIRAL"], 1597.5)
                self.assertEqual(types["MAG"], 0)
                self.assertEqual(types["TOXIN"], 0)

    def test_gas_cold_electric_riven_precedes_fever_for_toxin_and_magnetic(self):
        riven = self.equipped("Jat Kittag Riven", [("GAS", 1.0125),
                                                   ("COLD", 1.0125),
                                                   ("ELEC", 1.0125)])
        fever = self.equipped("Primed Fever Strike", [("TOXIN", 1.65)])
        types = self.calculate([riven, fever])
        self.assertAlmostEqual(types["GAS"], 607.5)
        self.assertAlmostEqual(types["MAG"], 1215)
        self.assertAlmostEqual(types["TOXIN"], 990)
        self.assertEqual(types["VIRAL"], 0)
        reversed_types = self.calculate([fever, riven])
        self.assertEqual(reversed_types["MAG"], 0)
        self.assertAlmostEqual(reversed_types["CORR"], 1597.5)
        self.assertAlmostEqual(reversed_types["COLD"], 607.5)

    def test_focus_and_gas_cold_riven_form_magnetic_without_fever(self):
        riven = self.equipped("Jat Kittag Riven", [("GAS", 1.0125), ("COLD", 1.0125)])
        focus = self.equipped("Focus Energy", [("ELEC", 0.60)])
        for slots in ([riven, focus], [focus, riven]):
            with self.subTest(slots=[s.mod.name for s in slots]):
                types = self.calculate(slots)
                self.assertAlmostEqual(types["BLAST"], 600)
                self.assertAlmostEqual(types["GAS"], 607.5)
                self.assertAlmostEqual(types["MAG"], 967.5)
                self.assertEqual(types["TOXIN"], 0)
                self.assertEqual(types["VIRAL"], 0)

    def test_focus_gas_riven_leaves_electricity_separate(self):
        riven = self.equipped("Jat Kittag Riven", [("GAS", 1.0125)])
        focus = self.equipped("Focus Energy", [("ELEC", 0.60)])
        for slots in ([riven, focus], [focus, riven]):
            types = self.calculate(slots)
            self.assertAlmostEqual(types["BLAST"], 600)
            self.assertAlmostEqual(types["GAS"], 607.5)
            self.assertAlmostEqual(types["ELEC"], 360)
            self.assertEqual(types["TOXIN"], 0)
            self.assertEqual(types["MAG"], 0)

    def test_requested_focus_riven_fever_order_and_melee_damage(self):
        riven = self.equipped("Jat Kittag Riven", [("GAS", 1.0125),
                                                   ("COLD", 1.0125),
                                                   ("TRUE", R3_MELEE_DAMAGE)])
        focus = self.equipped("Focus Energy", [("ELEC", 0.60)])
        fever = self.equipped("Primed Fever Strike", [("TOXIN", 1.65)])
        types = self.calculate([focus, riven, fever])
        base = 600 * (1 + R3_MELEE_DAMAGE)
        self.assertAlmostEqual(types["BLAST"], base)
        self.assertAlmostEqual(types["GAS"], base * 1.0125)
        self.assertAlmostEqual(types["MAG"], base * 1.6125)
        self.assertAlmostEqual(types["TOXIN"], base * 1.65)
        self.assertEqual(types["VIRAL"], 0)
        self.assertEqual(types["CORR"], 0)

    def test_focus_and_cold_need_to_pair_before_fever_for_magnetic_and_toxin(self):
        # These are three elemental slots, possible only by replacing a mod
        # outside the original six; this test does not prescribe that change.
        riven = self.equipped("Jat Kittag Riven", [("GAS", 1.0125), ("COLD", 1.0125)])
        focus = self.equipped("Focus Energy", [("ELEC", 0.60)])
        fever = self.equipped("Primed Fever Strike", [("TOXIN", 1.65)])
        for slots in ([riven, focus, fever], [focus, riven, fever]):
            with self.subTest(slots=[s.mod.name for s in slots]):
                types = self.calculate(slots)
                self.assertAlmostEqual(types["GAS"], 607.5)
                self.assertAlmostEqual(types["MAG"], 967.5)
                self.assertAlmostEqual(types["TOXIN"], 990)
                self.assertEqual(types["VIRAL"], 0)
        viral_first = self.calculate([fever, riven, focus])
        self.assertAlmostEqual(viral_first["VIRAL"], 1597.5)
        self.assertAlmostEqual(viral_first["ELEC"], 360)
        self.assertEqual(viral_first["MAG"], 0)
        corrosive_first = self.calculate([fever, focus, riven])
        self.assertAlmostEqual(corrosive_first["CORR"], 1350)
        self.assertAlmostEqual(corrosive_first["COLD"], 607.5)
        self.assertEqual(corrosive_first["MAG"], 0)

    def test_spliced_magnetic_remains_separate_from_heat_toxin_gas(self):
        riven = self.equipped("Jat Kittag Riven", [("MAG", 1.0125), ("HEAT", 1.0125)])
        fever = self.equipped("Primed Fever Strike", [("TOXIN", 1.65)])
        for slots in ([riven, fever], [fever, riven]):
            with self.subTest(slots=[s.mod.name for s in slots]):
                types = self.calculate(slots)
                self.assertAlmostEqual(types["BLAST"], 600)
                self.assertAlmostEqual(types["GAS"], 1597.5)
                self.assertAlmostEqual(types["MAG"], 607.5)
                self.assertEqual(types["TOXIN"], 0)
                self.assertEqual(types["HEAT"], 0)

    def test_spliced_gas_does_not_consume_rerolled_toxin(self):
        riven = self.equipped("Jat Kittag Riven", [("GAS", 1.0125), ("TOXIN", 1.0125)])
        focus = self.equipped("Focus Energy", [("ELEC", 0.60)])
        for slots in ([riven, focus], [focus, riven]):
            with self.subTest(slots=[s.mod.name for s in slots]):
                types = self.calculate(slots)
                self.assertAlmostEqual(types["BLAST"], 600)
                self.assertAlmostEqual(types["GAS"], 607.5)
                self.assertAlmostEqual(types["CORR"], 967.5)
                self.assertEqual(types["TOXIN"], 0)
                self.assertEqual(types["ELEC"], 0)


class StatusProbabilityTests(unittest.TestCase):
    def test_fractional_roll_count_inclusion_exclusion(self):
        # Two rolls guaranteed; third occurs 20% of the time.
        self.assertAlmostEqual(probability_at_least_one(2.2, 0.4),
                               1 - 0.6**2 * (1 - 0.2 * 0.4))
        self.assertAlmostEqual(probability_both(2.2, 0.4, 0.3), 0.2856)
        self.assertEqual(probability_both(2.2, 0.0, 0.3), 0.0)
        self.assertEqual(probability_at_least_one(0.0, 1.0), 0.0)
        self.assertEqual(probability_at_least_one(1.0, 1.0), 1.0)
        self.assertEqual(probability_both(2.0, 0.5, 0.5), 0.5)

    def test_three_types_require_the_optional_third_roll(self):
        self.assertAlmostEqual(probability_three(2.0, 0.2, 0.3, 0.1), 0.0)
        self.assertAlmostEqual(probability_three(2.2, 0.2, 0.3, 0.1),
                               0.2 * 6 * 0.2 * 0.3 * 0.1)
        self.assertAlmostEqual(probability_three(3.0, 1/3, 1/3, 1/3), 2/9)

    def test_rejects_invalid_shares_and_duplicate_types(self):
        with self.assertRaises(ValueError):
            probability_three(2.2, 0.4, 0.4, 0.4)
        with self.assertRaises(ValueError):
            BUILD_BY_KEY["focus_fever_gas_cold_damage"].probability_of_three("GAS", "GAS", "TOXIN")
        with self.assertRaises(ValueError):
            probability_both(2.2, 0.8, 0.3)
        with self.assertRaises(ValueError):
            probability_at_least_one(-1.0, 0.3)
        with self.assertRaises(ValueError):
            BUILD_BY_KEY["gas_eff_cc"].probability_of_both("GAS", "GAS")


class MagneticBreakTests(unittest.TestCase):
    def test_defense_scaling_and_mods_are_applied_as_wiki_describes(self):
        self.assertAlmostEqual(magnetic_break_electric_total(100, 1), 3.0)
        self.assertAlmostEqual(magnetic_break_electric_total(100, 10), 30.0)
        self.assertAlmostEqual(magnetic_break_electric_total(100, 15), 30.0)
        self.assertEqual(magnetic_break_electric_total(100, 0), 0.0)
        # Fully ranked Galvanized Elementalist: +80% status damage, twice;
        # Focus Energy: +60% Electricity even when combined into Magnetic.
        self.assertAlmostEqual(magnetic_break_electric_total(
            100, 1, status_damage_bonus=0.8, electricity_bonus=0.6), 15.552)
        self.assertAlmostEqual(magnetic_break_electric_total(
            100, 10, status_damage_bonus=0.8, electricity_bonus=0.6), 155.52)
        # Faction bonus double dips; duration is a separate input.
        self.assertAlmostEqual(magnetic_break_electric_total(
            100, 1, faction_bonus=0.3, duration_multiplier=2.0),
            3.0 * 1.3**2 * 2.0)

    def test_invalid_inputs_are_rejected(self):
        for args in ((-1, 1), (100, -1), (100, 1.5)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                magnetic_break_electric_total(*args)
        for kwargs in ({"status_damage_bonus": -1.1}, {"electricity_bonus": -1.1},
                       {"faction_bonus": -1.1}, {"duration_multiplier": -0.1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                magnetic_break_electric_total(100, 1, **kwargs)


class InitialComboTests(unittest.TestCase):
    def test_tier_thresholds(self):
        self.assertEqual([combo_tier(x) for x in (0, 19.99, 20, 79.99, 80, 100, 220, 400)],
                         [1, 1, 2, 4, 5, 6, 12, 12])
        with self.assertRaises(ValueError):
            combo_tier(-1)

    def test_first_recovery_is_not_sustain(self):
        for efficiency, expected_first, expected_sustain in (
            (0.5, 0.9825, 1.0), (0.9, 0.1685, 0.2),
        ):
            with self.subTest(efficiency=efficiency):
                self.assertAlmostEqual(first_recovery_time(81.4, efficiency, 80), expected_first)
                self.assertAlmostEqual(sustainable_interval(80, efficiency), expected_sustain)
        self.assertAlmostEqual(first_recovery_time(81.4, 0.9, 81.4), 0.2035)
        self.assertAlmostEqual(first_recovery_time(109.0, 0.9, 100), 0.0475)
        self.assertAlmostEqual(first_recovery_time(105.4, 0.9, 100), 0.1285)
        self.assertAlmostEqual(sustainable_interval(100, 0.9), 0.25)
        with self.assertRaises(ValueError):
            first_recovery_time(81.4, 0.9, 100)

    def test_combo_sequences(self):
        def tiers(floor, efficiency, interval):
            return [tier for _, tier in combo_sequence(floor, efficiency, interval, 8)]
        self.assertEqual(tiers(81.4, 0.5, 0.65), [5, 4, 3, 3, 3, 3, 3, 3])
        self.assertEqual(tiers(81.4, 0.9, 0.65), [5] * 8)
        self.assertEqual(tiers(81.4, 0.5, 0.75), [5, 4, 4, 4, 4, 4, 4, 4])
        self.assertEqual(tiers(81.4, 0.5, 1.00), [5] * 8)
        self.assertEqual(tiers(109.0, 0.9, 0.50), [6] * 8)
        self.assertEqual(tiers(105.4, 0.9, 0.65), [6] * 8)  # Ready Steel aura

    def test_initial_floor_does_not_delete_earned_combo_above_floor(self):
        sequence = combo_sequence(81.4, 0.9, 0.65, 2, starting_points=220.0)
        self.assertEqual(sequence[0], (220.0, 12))
        self.assertAlmostEqual(sequence[1][0], 198.0)
        self.assertEqual(sequence[1][1], 10)


if __name__ == "__main__":
    unittest.main()
