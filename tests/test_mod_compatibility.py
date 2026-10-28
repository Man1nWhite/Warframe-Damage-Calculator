"""Bounded mod-family filtering, grounded in offline snapshot and Wiki pages."""
from __future__ import annotations

from contextlib import closing

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from modules.database import ModRepository, WeaponRepository
from modules.mod_compatibility import ModCompatibility
from modules.models import Mod
from tools.build_weapon_mod_classes import CODA_BUBONICO, SOURCE_SHA256, build_snapshot

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "weapons.db"
SNAPSHOT = ROOT / "source" / "weapon_mod_classes.json"


class ModCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = ModCompatibility.from_file(SNAPSHOT)
        cls.weapons = WeaponRepository(DB)
        cls.mods = ModRepository(DB)

    def weapon(self, name):
        weapon = self.weapons.get_weapon(name)
        self.assertIsNotNone(weapon, name)
        return weapon

    def mod(self, unique):
        mod = self.mods.get_mod(unique)
        self.assertIsNotNone(mod, unique)
        return mod

    def test_snapshot_covers_the_bundled_primary_export_and_corrects_coda_bubonico(self):
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["source_sha256"], SOURCE_SHA256)
        self.assertEqual(snapshot["classes"][CODA_BUBONICO], "Shotgun")
        with closing(sqlite3.connect(DB)) as connection, connection:
            bundled = {row[0] for row in connection.execute(
                "SELECT unique_name FROM weapons WHERE product_category='LongGuns'")}
        self.assertTrue(bundled)
        self.assertFalse(bundled - set(self.policy.primary_classes))
        self.assertTrue((ROOT / "source" / snapshot["license"]).is_file())

    def test_snapshot_builder_overrides_coda_and_rejects_unknown_or_duplicate_rows(self):
        coda = {"uniqueName": CODA_BUBONICO, "type": "Rifle"}
        rifle = {"uniqueName": "/Lotus/Weapons/TestRifle", "type": "Rifle"}
        pistol = {"uniqueName": "/Lotus/Weapons/TestPistol", "type": "Pistol"}
        built = build_snapshot([rifle, coda, pistol])
        self.assertEqual(built["classes"][CODA_BUBONICO], "Shotgun")
        self.assertNotIn(pistol["uniqueName"], built["classes"])
        self.assertEqual(list(built["classes"]), sorted(built["classes"]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_snapshot([coda, coda])
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            build_snapshot([coda, {"uniqueName": "/Lotus/Weapons/X", "type": "Unmapped"}])
        with self.assertRaisesRegex(ValueError, "missing Coda"):
            build_snapshot([rifle])

    def test_rifle_and_shotgun_mods_do_not_cross_families(self):
        serration = self.mod("/Lotus/Upgrades/Mods/Rifle/WeaponDamageAmountMod")
        point_blank = self.mod("/Lotus/Upgrades/Mods/Shotgun/WeaponDamageAmountMod")
        for name in ("Braton", "Dread", "Vectis"):
            with self.subTest(weapon=name):
                self.assertTrue(self.policy.allows(self.weapon(name), serration))
                self.assertFalse(self.policy.allows(self.weapon(name), point_blank))
        for name in ("Hek", "Bubonico", "Coda Bubonico"):
            with self.subTest(weapon=name):
                self.assertTrue(self.policy.allows(self.weapon(name), point_blank))
                self.assertFalse(self.policy.allows(self.weapon(name), serration))

    def test_weapon_specific_augments_and_documented_variants(self):
        cases = (
            ("/Lotus/Weapons/Tenno/LongGuns/Gunbrella/ShrineMaidenGunbrellaAugment",
             ("Higasa",), ("Braton",)),
            ("/Lotus/Upgrades/Mods/Pistol/Event/AkbroncoViralDamageMod",
             ("Akbronco Prime",), ("Akbronco", "Ocucor")),
            ("/Lotus/Upgrades/Mods/Syndicate/MireMod", ("Mire", "Coda Mire"), ("Jat Kittag",)),
            ("/Lotus/Upgrades/Mods/Syndicate/SkanaMod", ("Skana", "Skana Prime", "Prisma Skana"),
             ("Dual Skana",)),
            ("/Lotus/Upgrades/Mods/Syndicate/DualCleaversMod", ("Dual Cleavers", "Prisma Dual Cleavers"),
             ("Jat Kittag",)),
        )
        for unique, allowed, rejected in cases:
            mod = self.mod(unique)
            for name in allowed:
                with self.subTest(mod=mod.name, weapon=name):
                    self.assertTrue(self.policy.allows(self.weapon(name), mod))
            for name in rejected:
                with self.subTest(mod=mod.name, weapon=name):
                    self.assertFalse(self.policy.allows(self.weapon(name), mod))

    def test_bounded_melee_subclasses_and_excluded_nonplayer_mods(self):
        amar = self.mod("/Lotus/Upgrades/Mods/Sets/Amar/AmarMeleeMod")
        boreal = self.mod("/Lotus/Upgrades/Mods/Sets/Boreal/BorealMeleeMod")
        nira = self.mod("/Lotus/Upgrades/Mods/Sets/Nira/NiraMeleeMod")
        for mod, legal, illegal in ((amar, "Fang Prime", "Jat Kittag"),
                                    (boreal, "Orthos Prime", "Jat Kittag"),
                                    (nira, "Atterax", "Jat Kittag")):
            with self.subTest(mod=mod.name):
                self.assertTrue(self.policy.allows(self.weapon(legal), mod))
                self.assertFalse(self.policy.allows(self.weapon(illegal), mod))
        for unique in ("/Lotus/Upgrades/Mods/Sentinel/Kubrow/BeastWeapon/BeastBruteConditioningMod",
                       "/Lotus/Upgrades/Mods/Archwing/Melee/ArchwingMeleeDamageMod"):
            self.assertFalse(self.policy.allows(self.weapon("Jat Kittag"), self.mod(unique)))

    def test_unsupported_trigger_rules_and_weapon_categories_are_not_assumed(self):
        cannonade = self.mod("/Lotus/Upgrades/Mods/Rifle/RifleSemiAutoFantasyMod")
        for name in ("Braton", "Latron"):
            self.assertFalse(self.policy.allows(self.weapon(name), cannonade))
        serration = self.mod("/Lotus/Upgrades/Mods/Rifle/WeaponDamageAmountMod")
        archgun = self.weapon("Imperator")
        self.assertFalse(self.policy.allows(archgun, serration))
        self.assertIn("not modeled", self.policy.notice(archgun))

    def test_unknown_official_family_fails_closed_and_custom_data_is_preserved(self):
        rifle = self.weapon("Braton")
        unknown = replace(rifle, unique_name="/Lotus/Weapons/NewUnknownPrimary")
        custom_weapon = replace(rifle, unique_name="/custom/my-weapon", weapon="My weapon")
        serration = self.mod("/Lotus/Upgrades/Mods/Rifle/WeaponDamageAmountMod")
        self.assertFalse(self.policy.allows(unknown, serration))
        self.assertIn("official rifle/shotgun mods are hidden", self.policy.notice(unknown))
        self.assertTrue(self.policy.allows(custom_weapon, serration))
        self.assertIn("not filtered", self.policy.notice(custom_weapon))
        custom_mod = Mod("/custom/mod", "My mod", "MELEE", "Anything", "", "", 0, 0, "", "", True)
        self.assertTrue(self.policy.allows(unknown, custom_mod))
        self.assertTrue(self.policy.allows(self.weapon("Imperator"), custom_mod))

    def test_missing_or_corrupt_snapshot_is_unknown_not_a_guessed_rifle(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "classes.json"
            for content in (None, "not json", '{"schema": 1, "classes": {"bad": "Rifle"}}'):
                if content is not None:
                    path.write_text(content, encoding="utf-8")
                policy = ModCompatibility.from_file(path)
                self.assertEqual(policy.primary_classes, {})
                self.assertFalse(policy.allows(self.weapon("Braton"),
                    self.mod("/Lotus/Upgrades/Mods/Rifle/WeaponDamageAmountMod")))
                self.assertIn("Unknown primary", policy.notice(self.weapon("Braton")))


if __name__ == "__main__":
    unittest.main()
