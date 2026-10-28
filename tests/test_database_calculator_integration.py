"""Integration checks against the repository's bundled data snapshot.

The snapshot is not a live wiki feed. These examples verify that database
fields and mod text reach the calculator with the intended meanings.
"""
import unittest
from pathlib import Path

from modules.calculator import DamageCalculator
from modules.database import ModRepository, WeaponRepository
from modules.mod_engine import ModAggregator
from modules.models import CalculationInputs, EquippedMod

DB = Path(__file__).resolve().parents[1] / "data" / "weapons.db"


class BundledDataIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.weapons = WeaponRepository(DB)
        cls.mods = ModRepository(DB)

    def test_export_primary_elements_are_not_rotated(self):
        # Three independent wiki weapon examples exercise DE indices 3, 4, 5.
        for name, kind, damage in (("Ignis Wraith", "HEAT", 35),
                                   ("Tenet Glaxion", "COLD", 34),
                                   ("Alternox Prime", "ELEC", 75)):
            weapon = self.weapons.get_weapon(name)
            self.assertIsNotNone(weapon, name)
            self.assertEqual(weapon.damage_for(kind), damage, name)
            for other in {"HEAT", "COLD", "ELEC"} - {kind}:
                self.assertEqual(weapon.damage_for(other), 0, (name, other))

    def test_grimoire_uses_the_player_export_not_the_doppelganger(self):
        # The public export's 150 Electricity aggregates the Wiki's primary
        # 100 direct + 50 radial components; it is not one 150-damage hit.
        weapon = self.weapons.get_weapon("Grimoire")
        self.assertTrue(weapon.unique_name.endswith("/TnGrimoire"))
        self.assertEqual(weapon.dmg, 150)
        self.assertEqual(weapon.damage_for("ELEC"), 150)
        self.assertEqual(weapon.damage_for("IMPACT"), 0)
        self.assertEqual(weapon.damage_for("PUNC"), 0)
        self.assertAlmostEqual(weapon.critchan, .20)
        self.assertAlmostEqual(weapon.statchan, .26)

    def test_hek_innate_multishot_arsenal_total(self):
        # Wiki Hek: 75 per pellet, 7 pellets -> 525 total.
        weapon = self.weapons.get_weapon("Hek")
        self.assertIsNotNone(weapon)
        result = DamageCalculator().calculate(
            weapon, CalculationInputs(weapon_name=weapon.weapon,
                                      faction="Grineer", armor_value=0))
        self.assertAlmostEqual(result.hud_total, 525, places=3)
        self.assertAlmostEqual(sum(result.hud_damage_by_type.values()), 75, places=3)

    def test_bane_multiplier_in_database_is_a_bonus_not_155_percent(self):
        mod = next(m for m in self.mods.list_mods_for_slot("PRIMARY")
                   if m.name == "Primed Bane of Infested")
        slots = [EquippedMod(mod=mod, rank=mod.fusion_limit,
                            effects=self.mods.fetch_ranked_effects(
                                mod.unique_name, mod.fusion_limit))]
        bonuses = ModAggregator().aggregate(slots, "Infested")
        self.assertAlmostEqual(bonuses["BANE"], 0.55)
        self.assertEqual(ModAggregator().aggregate(slots, "Grineer")["BANE"], 0)

    def test_rebuilt_database_recognizes_primed_bane_of_the_murmur(self):
        mod = next(m for m in self.mods.list_mods_for_slot("PRIMARY")
                   if m.name == "Primed Bane of The Murmur")
        slots = [EquippedMod(mod=mod, rank=mod.fusion_limit,
                            effects=self.mods.fetch_ranked_effects(
                                mod.unique_name, mod.fusion_limit))]
        self.assertAlmostEqual(ModAggregator().aggregate(slots, "Murmur")["BANE"], 0.55)
        self.assertEqual(ModAggregator().aggregate(slots, "Grineer")["BANE"], 0)

    def test_equipped_slots_alone_carry_the_mod_bonuses(self) -> None:
        # Callers that hand over only ``equipped_mods`` must get the same
        # numbers as callers that also pre-aggregate into ``mods``; the slots
        # are authoritative, so nothing may be silently dropped.
        weapon = self.weapons.get_weapon("Hek")
        self.assertIsNotNone(weapon)
        wanted = ("Primed Bane of Grineer", "Cryo Rounds", "Hellfire")
        slots = []
        for name in wanted:
            mod = next(m for m in self.mods.list_mods_for_slot("PRIMARY")
                       if m.name == name)
            rank = mod.fusion_limit
            slots.append(EquippedMod(mod=mod, rank=rank,
                                     effects=self.mods.fetch_ranked_effects(
                                         mod.unique_name, rank)))
        bonuses = ModAggregator().aggregate(slots, "Grineer")
        calc = DamageCalculator()

        def run(**kwargs):
            return calc.calculate(weapon, CalculationInputs(
                weapon_name=weapon.weapon, faction="Grineer",
                armor_value=0, **kwargs))

        slots_only = run(equipped_mods=slots)
        both = run(mods=bonuses, equipped_mods=slots)
        unmodded = run()
        self.assertGreater(slots_only.hud_total, unmodded.hud_total)
        self.assertAlmostEqual(slots_only.hud_total, both.hud_total, places=6)
        self.assertAlmostEqual(slots_only.final_total, both.final_total, places=6)
        self.assertAlmostEqual(slots_only.final_total_with_bane,
                               both.final_total_with_bane, places=6)
        self.assertEqual(slots_only.hud_damage_by_type, both.hud_damage_by_type)
        # +90% Cold and +90% Heat turn Hellfire/Cryo Rounds into Blast.
        self.assertGreater(slots_only.hud_damage_by_type.get("BLAST", 0), 0)

    def test_database_mod_slot_combines_with_innate_element(self):
        weapon = self.weapons.get_weapon("Alternox Prime")
        self.assertIsNotNone(weapon)
        mod = next(m for m in self.mods.list_mods_for_slot("PRIMARY")
                   if m.name == "Cryo Rounds" and m.fusion_limit == 5)
        slots = [EquippedMod(mod=mod, rank=5,
                            effects=self.mods.fetch_ranked_effects(mod.unique_name, 5))]
        bonuses = ModAggregator().aggregate(slots, "Grineer")
        result = DamageCalculator().calculate(
            weapon, CalculationInputs(weapon_name=weapon.weapon, faction="Grineer",
                                      armor_value=0, mods=bonuses, equipped_mods=slots))
        # +90% Cold combines with the innate 75 Electricity into Magnetic.
        self.assertAlmostEqual(result.hud_damage_by_type["MAG"], 75 * 1.9)
        self.assertEqual(result.hud_damage_by_type["ELEC"], 0)
        self.assertEqual(result.hud_damage_by_type["COLD"], 0)
