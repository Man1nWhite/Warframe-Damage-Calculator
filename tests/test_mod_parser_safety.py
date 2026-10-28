"""The desktop calculator must not invent direct damage from unrelated effects.

Sources: https://wiki.warframe.com/w/Firestorm (blast radius),
https://wiki.warframe.com/w/Comet_Rounds (Conclave physical conversion),
and https://wiki.warframe.com/w/Proton_Snap (conditional on Wall Latch).
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from modules.database import ModRepository
from modules.importer import _slot_group_from_mod, create_schema, mods_from_cleaned_json
from modules.mod_parser import parse_effects

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "weapons.db"


class DirectDamageParserSafetyTests(unittest.TestCase):
    def test_untyped_tome_mod_is_not_guessed_to_be_a_rifle_mod(self):
        # Wiki: Tome mods belong to Grimoire and Noctua, not generic primaries.
        # Without the export's explicit type, leave the slot unknown.
        self.assertEqual(_slot_group_from_mod({"compatName": "Tome"}), "OTHER")
        self.assertEqual(_slot_group_from_mod({"type": "SECONDARY", "compatName": "Tome"}), "SECONDARY")

    def test_real_non_damage_and_conditional_text_is_not_a_direct_damage_stat(self):
        lines = (
            "+24% Blast Range",                      # Firestorm
            "-50% Blast Radius",                     # Static Alacrity
            "20% of Damage converted into <DT_IMPACT_COLOR>Impact",  # Comet Rounds
            "(+20% Enemy Max Health) <DT_EXPLOSION_COLOR>Blast Damage",  # Entropy Detonation
            "Hold Wall Latch for 2s to gain +100% <DT_POISON_COLOR>Toxin Damage",  # Proton Snap
            "+100% Toxin Damage while Wall Latching",
            "+80% Melee Damage per Status Type affecting the target",  # Condition Overload
            "+100% Damage for 10s and +100% Heat",  # condition applies across tokens
            "+100% Damage and +100% Heat while Aiming",
            "+10% Void Sling radius for each Mod from a unique School",
        )
        for line in lines:
            with self.subTest(line=line):
                self.assertEqual(parse_effects(line), [])

    def test_standard_elemental_physical_base_and_faction_effects_still_parse(self):
        cases = (
            ("+90% <DT_FIRE_COLOR>Heat", "HEAT", 0.9),
            ("+60% Radiation Damage", "RAD", 0.6),
            ("+120% Puncture", "PUNC", 1.2),
            ("+165% Damage", "TRUE", 1.65),
            ("+165% Melee Damage", "TRUE", 1.65),  # Primed Pressure Point
            ("+90% Melee Damage", "TRUE", 0.9),   # Amar's Contempt
            ("x1.55 Damage to The Murmur", "BANE_MURMUR", 1.55),
            ("X1.33 Damage to Sentients", "BANE_SENTIENT", 1.33),
        )
        for text, code, value in cases:
            with self.subTest(text=text):
                effects = parse_effects(text)
                self.assertEqual(len(effects), 1)
                self.assertEqual(effects[0].code, code)
                self.assertAlmostEqual(effects[0].value, value)
        effects = parse_effects("+60% <DT_TOXIN_COLOR>Toxin +60% Status Chance")
        self.assertEqual([(effect.code, effect.value) for effect in effects], [("TOXIN", 0.6)])

    def test_new_import_marks_non_damage_and_conclave_mods_unsupported(self):
        mods, effects = mods_from_cleaned_json(ROOT / "source" / "ExportKeys_en_Cleaned.zip")
        by_id = {mod["unique_name"]: mod for mod in mods}
        unavailable = (
            "/Lotus/Upgrades/Mods/Rifle/WeaponIncreaseRadialExplosionMod",  # Firestorm
            "/Lotus/Upgrades/Mods/PvPMods/Rifle/DamageBiasImpactRifleMod",  # Comet Rounds
            "/Lotus/Upgrades/Mods/Sets/Spider/SpiderModC",  # Proton Snap
            "/Lotus/Upgrades/Mods/PvPMods/Rifle/TiberonLowRoFAiming",  # Measured Burst
            "/Lotus/Upgrades/Mods/Melee/WeaponMeleeDamageOnHeavyKillMod",  # unverified duplicate
        )
        for unique in unavailable:
            with self.subTest(unique=unique):
                self.assertEqual(by_id[unique]["supported"], 0)
        # The raw stat still parses, but the item is PvP-only and not offered.
        self.assertTrue(any(row["unique_name"] == unavailable[-2] for row in effects))
        self.assertEqual(by_id["/Lotus/Upgrades/Mods/Rifle/WeaponFireDamageMod"]["supported"], 1)
        pressure = "/Lotus/Upgrades/Mods/Melee/Expert/WeaponMeleeDamageModExpert"
        self.assertEqual(by_id[pressure]["supported"], 1)
        self.assertTrue(any(row["unique_name"] == pressure and row["rank"] == 10
                            and row["effect_code"] == "TRUE" and row["effect_value"] == 1.65
                            for row in effects))


class ExistingDatabaseSafetyTests(unittest.TestCase):
    def test_old_official_rows_do_not_turn_range_conversion_or_conditions_into_damage(self):
        repo = ModRepository(DB)
        # These stale entries exist in revision-1 databases; no rebuild should
        # be required to stop applying them as ordinary damage.
        ids = (
            "/Lotus/Upgrades/Mods/Rifle/WeaponIncreaseRadialExplosionMod",
            "/Lotus/Upgrades/Mods/PvPMods/Rifle/DamageBiasImpactRifleMod",
            "/Lotus/Upgrades/Mods/Sets/Spider/SpiderModC",
        )
        for unique in ids:
            with self.subTest(unique=unique):
                self.assertEqual(repo.fetch_ranked_effects(unique, 3), [])
        batch = repo.fetch_ranked_effects_many([(unique, 3) for unique in ids])
        self.assertTrue(all(not batch[(unique, 3)] for unique in ids))
        visible = {mod.unique_name for slot in ("PRIMARY", "MELEE")
                   for mod in repo.list_mods_for_slot(slot)}
        self.assertTrue(visible.isdisjoint(ids))

    def test_legacy_filter_keeps_user_defined_effects_even_with_custom_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "custom.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                create_schema(connection)
                connection.execute("INSERT INTO mods(unique_name, name, slot_group, supported) "
                                   "VALUES('/custom/fire', 'My custom damage', 'PRIMARY', 1)")
                connection.execute("INSERT INTO mod_effects VALUES('/custom/fire',0,1,'HEAT',.7,'custom effect')")
            repo = ModRepository(path)
            self.assertEqual(repo.fetch_ranked_effects('/custom/fire', 0)[0].value, 0.7)
            self.assertIn('/custom/fire', {mod.unique_name for mod in repo.list_mods_for_slot('PRIMARY')})


if __name__ == "__main__":
    unittest.main()
