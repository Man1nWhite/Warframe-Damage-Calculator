"""Tests for the Riven stat engine.

The fingerprint cases reproduce the real in-game Riven assertions from
RivenParser.js's upstream test.js (calamity-inc/warframe-riven-info), which
validates the whole value chain: disposition, grade rolls, combined-stat
attenuation, rank steps and display rounding.
"""

from __future__ import annotations

import unittest

from modules import riven
from modules.riven import (
    BUFF_LAYOUTS,
    CURSE_LAYOUTS,
    DEFAULT_DISPOSITION,
    GRADE_MAX_FACTOR,
    GRADE_MIN_FACTOR,
    NUM_BUFFS_ATTEN,
    RIVEN_TYPE_NAMES,
    TAG_METADATA,
    average_buff,
    average_curse,
    build_average_tables,
    display_value,
    grade_factor,
    load_riven_tags,
    parse_riven,
)


class FingerprintParityTests(unittest.TestCase):
    """Exact in-game display values from upstream test.js."""

    def test_melee_three_positives_one_curse(self) -> None:
        stats = parse_riven(
            "PlayerMeleeWeaponRandomModRare",
            {
                "lvl": 8,
                "buffs": [
                    {"Tag": "WeaponMeleeDamageMod", "Value": 40881867},
                    {"Tag": "WeaponElectricityDamageMod", "Value": 176959},
                    {"Tag": "WeaponFireRateMod", "Value": 257573658},
                ],
                "curses": [{"Tag": "WeaponArmorPiercingDamageMod", "Value": 400514956}],
            },
            1.10,
        )
        self.assertEqual([s["display"] for s in stats], [154.2, 83.5, 53.7, -96.2])

    def test_pistol_three_positives_no_curse(self) -> None:
        stats = parse_riven(
            "LotusPistolRandomModRare",
            {
                "lvl": 8,
                "buffs": [
                    {"Tag": "WeaponReloadSpeedMod", "Value": 1031084030},
                    {"Tag": "WeaponProjectileSpeedMod", "Value": 979115818},
                    {"Tag": "WeaponFreezeDamageMod", "Value": 287446961},
                ],
                "curses": [],
            },
            1.00,
        )
        self.assertEqual([s["display"] for s in stats], [40.9, 73.1, 64.4])

    def test_rifle_three_positives_one_curse(self) -> None:
        stats = parse_riven(
            "LotusRifleRandomModRare",
            {
                "lvl": 8,
                "buffs": [
                    {"Tag": "WeaponElectricityDamageMod", "Value": 258268665},
                    {"Tag": "WeaponClipMaxMod", "Value": 57385833},
                    {"Tag": "WeaponStunChanceMod", "Value": 590970762},
                ],
                "curses": [{"Tag": "WeaponAmmoMaxMod", "Value": 462255655}],
            },
            1.30,
        )
        self.assertEqual([s["display"] for s in stats], [104.0, 55.5, 110.8, -48.0])

    def test_repeated_tag_with_min_and_max_rolls(self) -> None:
        stats = parse_riven(
            "LotusRifleRandomModRare",
            {
                "lvl": 8,
                "buffs": [
                    {"Tag": "WeaponFireRateMod", "Value": 4294967295},
                    {"Tag": "WeaponFireRateMod", "Value": 1073741823},
                ],
                "curses": [],
            },
            0.65,
        )
        self.assertEqual([s["display"] for s in stats], [34.8, 42.5])


class GradeTests(unittest.TestCase):
    def test_average_grade_is_unity(self) -> None:
        self.assertEqual(grade_factor(0.5), 1.0)

    def test_grade_band(self) -> None:
        self.assertEqual(grade_factor(0.0), GRADE_MIN_FACTOR)
        self.assertEqual(grade_factor(1.0), GRADE_MAX_FACTOR)
        self.assertEqual(GRADE_MIN_FACTOR, 0.9)
        self.assertEqual(GRADE_MAX_FACTOR, 1.1)


class DisplayValueTests(unittest.TestCase):
    def test_percent_uses_one_decimal(self) -> None:
        self.assertEqual(display_value("WeaponFireDamageMod", 1.0692), 106.9)
        self.assertEqual(display_value("WeaponArmorPiercingDamageMod", -0.5346), -53.5)

    def test_faction_bonus_uses_two_decimals(self) -> None:
        self.assertEqual(display_value("WeaponFactionDamageGrineer", 0.5346), 0.53)
        self.assertEqual(display_value("WeaponMeleeFactionDamageCorpus", 0.5), 0.5)

    def test_plain_stats_use_one_decimal(self) -> None:
        self.assertEqual(display_value("WeaponMeleeRangeIncMod", 2.9133), 2.9)
        self.assertEqual(display_value("ComboDurationMod", 8.04), 8.0)
        self.assertEqual(display_value("WeaponMeleeComboInitialBonusMod", 29.12), 29.1)


class AverageTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tables = build_average_tables(disposition=DEFAULT_DISPOSITION)
        cls.tags = load_riven_tags()

    def test_all_seven_riven_types_present(self) -> None:
        self.assertEqual(set(self.tables["riven_types"]), set(RIVEN_TYPE_NAMES))

    def test_metadata_covers_every_tag(self) -> None:
        all_tags = {entry["tag"] for entries in self.tags.values() for entry in entries}
        self.assertEqual(all_tags, set(TAG_METADATA))
        # Every generated row resolves to a real label rather than the raw tag.
        for payload in self.tables["riven_types"].values():
            for stat in payload["stats"]:
                self.assertNotEqual(stat["name"], stat["tag"])

    def test_every_stat_has_all_layouts(self) -> None:
        buff_keys = [key for key, _, _ in BUFF_LAYOUTS]
        curse_keys = [key for key, _, _ in CURSE_LAYOUTS]
        for payload in self.tables["riven_types"].values():
            for stat in payload["stats"]:
                self.assertEqual(set(stat["buffs"]), set(buff_keys))
                self.assertEqual(set(stat["curses"]), set(curse_keys))

    def test_rifle_heat_known_values_at_disposition_1_2(self) -> None:
        rifle = self.tables["riven_types"]["LotusRifleRandomModRare"]
        heat = next(stat for stat in rifle["stats"] if stat["tag"] == "WeaponFireDamageMod")
        self.assertEqual(heat["name"], "Heat")
        self.assertEqual(heat["unit"], "percent")
        self.assertEqual(heat["wdc_code"], "HEAT")
        self.assertEqual(heat["buffs"]["2_pos"]["display"], 106.9)
        self.assertEqual(heat["buffs"]["3_pos"]["display"], 81.0)
        self.assertEqual(heat["buffs"]["2_pos_1_neg"]["display"], 133.7)
        self.assertEqual(heat["buffs"]["3_pos_1_neg"]["display"], 101.3)  # 1012.5 rounds half up
        self.assertEqual(heat["curses"]["with_2_pos"]["display"], -53.5)
        self.assertEqual(heat["curses"]["with_3_pos"]["display"], -81.0)

    def test_values_scale_linearly_with_disposition(self) -> None:
        at_1_2 = average_buff("LotusRifleRandomModRare", "WeaponFireDamageMod", disposition=1.2)
        at_1_0 = average_buff("LotusRifleRandomModRare", "WeaponFireDamageMod", disposition=1.0)
        self.assertAlmostEqual(at_1_2 / at_1_0, 1.2, places=12)

    def test_combined_stat_attenuation_ratios(self) -> None:
        two_pos = average_buff("LotusRifleRandomModRare", "WeaponFireDamageMod", num_buffs=2)
        three_pos = average_buff("LotusRifleRandomModRare", "WeaponFireDamageMod", num_buffs=3)
        self.assertAlmostEqual(three_pos / two_pos, NUM_BUFFS_ATTEN[3] / NUM_BUFFS_ATTEN[2], places=12)
        with_curse = average_buff(
            "LotusRifleRandomModRare", "WeaponFireDamageMod", num_buffs=2, num_curses=1
        )
        self.assertAlmostEqual(with_curse / two_pos, 1.25, places=12)

    def test_curse_is_negative_and_layout_dependent(self) -> None:
        with_two = average_curse("LotusRifleRandomModRare", "WeaponFireDamageMod", num_buffs=2)
        with_three = average_curse("LotusRifleRandomModRare", "WeaponFireDamageMod", num_buffs=3)
        self.assertLess(with_two, 0)
        self.assertLess(with_three, 0)
        self.assertNotAlmostEqual(with_two, with_three)

    def test_unknown_tag_raises(self) -> None:
        with self.assertRaises(KeyError):
            average_buff("LotusRifleRandomModRare", "NotARealTag")

    def test_meta_records_requested_disposition(self) -> None:
        self.assertEqual(self.tables["meta"]["disposition"], DEFAULT_DISPOSITION)
        self.assertEqual(self.tables["meta"]["grade_factor"], 1.0)
        self.assertEqual(self.tables["meta"]["rank_steps"], 9)


if __name__ == "__main__":
    unittest.main()
