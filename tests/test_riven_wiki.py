"""Parity with the WARFRAME Wiki Riven Mods page.

Reference: https://wiki.warframe.com/w/Riven_Mods ("Attribute Value Formula"
and the rank-8 "Base Values" range tables). The wiki states that each stat is
rolled between 90% and 110% of its base value, scaled by the 1.2x disposition
constant, then multiplied by weighted layout factors:

    | Type of stats   | Bonus  | Malus   |
    | 2 Bonus, 0 Curse| 0.99   | -       |
    | 2 Bonus, 1 Curse| 1.2375 | -0.495  |
    | 3 Bonus, 0 Curse| 0.75   | -       |
    | 3 Bonus, 1 Curse| 0.9375 | -0.75   |

The engine keeps DE's factors split into SPECIFIC_FIT_ATTENUATION (1.5) and the
numBuffsAtten / curse arrays, so the wiki weights equal 1.5 x engine layout
factor (the only differences are float32 representations such as 0.66000003).

Range endpoints below are taken verbatim from the wiki's rank-8 tables; the
engine reproduces them with grade rolls at the 0.9 and 1.1 band edges.
"""

from __future__ import annotations

import unittest

from modules.riven import (
    BUFF_LAYOUTS,
    CURSE_LAYOUTS,
    GRADE_MAX_FACTOR,
    GRADE_MIN_FACTOR,
    SPECIFIC_FIT_ATTENUATION,
    average_buff,
    average_curse,
    buff_layout_factor,
    curse_layout_factor,
)

RIFLE = "LotusRifleRandomModRare"
MELEE = "PlayerMeleeWeaponRandomModRare"

# Wiki "Attribute Value Formula" weighted table.
WIKI_BONUS_WEIGHTS = {(2, 0): 0.99, (2, 1): 1.2375, (3, 0): 0.75, (3, 1): 0.9375}
WIKI_MALUS_WEIGHTS = {(2, 1): -0.495, (3, 1): -0.75}

# Wiki rank-8 range table rows: tag -> (3+1, 2+1, 3+0, 2+0) endpoint pairs,
# expressed in percentage points; the final entry is the engine display scale.
WIKI_BUFF_RANGES = [
    (RIFLE, "WeaponFireDamageMod",
     ((91.13, 111.38), (120.29, 147.02), (72.90, 89.10), (96.23, 117.61)), 100.0, 0.02),
    (RIFLE, "WeaponDamageAmountMod",
     ((167.06, 204.19), (220.52, 269.53), (133.65, 163.35), (176.42, 215.62)), 100.0, 0.02),
    (RIFLE, "WeaponCritChanceMod",
     ((151.86, 185.61), (200.46, 245.01), (121.49, 148.49), (160.37, 196.01)), 100.0, 0.02),
    (RIFLE, "WeaponCritDamageMod",
     ((121.50, 148.50), (160.38, 196.02), (97.20, 118.80), (128.30, 156.81)), 100.0, 0.02),
    (RIFLE, "WeaponFireRateMod",
     ((60.78, 74.29), (80.23, 98.06), (48.62, 59.43), (64.18, 78.45)), 100.0, 0.02),
    (RIFLE, "WeaponProcTimeMod",
     ((101.24, 123.74), (133.64, 163.33), (80.99, 98.99), (106.91, 130.67)), 100.0, 0.02),
    (RIFLE, "WeaponStunChanceMod",
     ((91.13, 111.38), (120.29, 147.02), (72.90, 89.10), (96.23, 117.61)), 100.0, 0.02),
    (MELEE, "WeaponMeleeDamageMod",
     ((166.76, 203.82), (220.12, 269.04), (133.41, 163.05), (176.10, 215.23)), 100.0, 0.02),
    (MELEE, "WeaponFireRateMod",
     ((55.59, 67.94), (73.37, 89.68), (44.47, 54.35), (58.70, 71.74)), 100.0, 0.02),
    # Plain-unit rows (meters / seconds / counts): natural units, scale 1.
    (MELEE, "WeaponMeleeRangeIncMod",
     ((1.96, 2.40), (2.59, 3.17), (1.57, 1.92), (2.07, 2.54)), 1.0, 0.02),
    (MELEE, "ComboDurationMod",
     ((8.20, 10.02), (10.83, 13.23), (6.56, 8.02), (8.66, 10.59)), 1.0, 0.02),
    (MELEE, "WeaponMeleeComboInitialBonusMod",
     ((24.81, 30.32), (32.74, 40.02), (19.85, 24.26), (26.20, 32.02)), 1.0, 0.06),
]

# Wiki faction-damage row expressed as full multipliers (engine stores the bonus).
WIKI_FACTION_MULTIPLIERS = {
    (3, 1): (1.46, 1.56),
    (2, 1): (1.60, 1.74),
    (3, 0): (1.36, 1.45),
    (2, 0): (1.48, 1.59),
}

# Wiki malus columns: tag -> ((3+1 low, 3+1 high), (2+1 low, 2+1 high)) magnitudes.
WIKI_CURSE_RANGES = {
    "WeaponDamageAmountMod": ((133.65, 163.35), (88.21, 107.81)),
    "WeaponCritChanceMod": ((121.49, 148.49), (80.18, 98.00)),
    "WeaponFireRateMod": ((48.62, 59.43), (32.09, 39.22)),
}


class WikiWeightedFormulaTests(unittest.TestCase):
    def test_bonus_weights_equal_wiki_table(self) -> None:
        for layout, wiki_weight in WIKI_BONUS_WEIGHTS.items():
            engine_weight = SPECIFIC_FIT_ATTENUATION * buff_layout_factor(*layout)
            self.assertAlmostEqual(engine_weight, wiki_weight, delta=1e-7)

    def test_malus_weights_equal_wiki_table(self) -> None:
        for layout, wiki_weight in WIKI_MALUS_WEIGHTS.items():
            engine_weight = -SPECIFIC_FIT_ATTENUATION * curse_layout_factor(*layout)
            self.assertAlmostEqual(engine_weight, wiki_weight, delta=1e-7)

    def test_grade_band_matches_90_to_110_percent(self) -> None:
        self.assertEqual((GRADE_MIN_FACTOR, GRADE_MAX_FACTOR), (0.9, 1.1))

    def test_only_the_four_rollable_layouts_are_generated(self) -> None:
        # Wiki: 2-3 positive attributes and at most one negative.
        self.assertEqual([(n, c) for _, n, c in BUFF_LAYOUTS],
                         [(2, 0), (3, 0), (2, 1), (3, 1)])
        self.assertEqual([(n, c) for _, n, c in CURSE_LAYOUTS], [(2, 1), (3, 1)])


class WikiRangeTableTests(unittest.TestCase):
    def test_buff_range_endpoints(self) -> None:
        for riven_type, tag, wiki_ranges, scale, tolerance in WIKI_BUFF_RANGES:
            for (num_buffs, num_curses), (wiki_low, wiki_high) in zip(
                ((3, 1), (2, 1), (3, 0), (2, 0)), wiki_ranges, strict=True
            ):
                low = average_buff(
                    riven_type, tag, num_buffs=num_buffs, num_curses=num_curses, grade_t=0.0
                ) * scale
                high = average_buff(
                    riven_type, tag, num_buffs=num_buffs, num_curses=num_curses, grade_t=1.0
                ) * scale
                self.assertAlmostEqual(low, wiki_low, delta=tolerance, msg=(tag, "low"))
                self.assertAlmostEqual(high, wiki_high, delta=tolerance, msg=(tag, "high"))

    def test_faction_damage_multipliers(self) -> None:
        for (num_buffs, num_curses), (wiki_low, wiki_high) in WIKI_FACTION_MULTIPLIERS.items():
            low = 1.0 + average_buff(
                RIFLE, "WeaponFactionDamageGrineer",
                num_buffs=num_buffs, num_curses=num_curses, grade_t=0.0,
            )
            high = 1.0 + average_buff(
                RIFLE, "WeaponFactionDamageGrineer",
                num_buffs=num_buffs, num_curses=num_curses, grade_t=1.0,
            )
            self.assertEqual((round(low, 2), round(high, 2)), (wiki_low, wiki_high))

    def test_curse_magnitudes(self) -> None:
        for tag, (wiki_31, wiki_21) in WIKI_CURSE_RANGES.items():
            for num_buffs, (wiki_low, wiki_high) in ((3, wiki_31), (2, wiki_21)):
                low = abs(average_curse(RIFLE, tag, num_buffs=num_buffs, grade_t=0.0)) * 100
                high = abs(average_curse(RIFLE, tag, num_buffs=num_buffs, grade_t=1.0)) * 100
                low, high = sorted((low, high))
                self.assertAlmostEqual(low, wiki_low, delta=0.011, msg=(tag, "curse low"))
                self.assertAlmostEqual(high, wiki_high, delta=0.011, msg=(tag, "curse high"))


if __name__ == "__main__":
    unittest.main()
