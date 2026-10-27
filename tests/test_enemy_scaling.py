"""Tests for the enemy level-scaling model.

The base-level Heavy Gunner anchor (500 armor -> 38.73% DR, EHP 489.64) is
taken verbatim from the live Heavy Gunner infobox on wiki.warframe.com,
which is rendered by MediaWiki:Gadget-enemyinfoboxslider.js -- the same
algorithm modules/enemy_scaling.py ports. All other values are regression
anchors computed from that port; the two target dummies are pinned end to
end.
"""
from __future__ import annotations

import math
import unittest

from modules.enemy_scaling import (
    ARMOR_CAP,
    ARMOR_FLOOR,
    HEAVY_GUNNER,
    MODE_ICEBIND,
    MODE_NORMAL,
    MODE_STEEL_PATH,
    OVERGUARD_BASE,
    ScalingCurve,
    armor_damage_reduction,
    empowered_multiplier,
    enemy_damage_multiplier,
    eximus_base_health,
    icebind_eximus_heavy_gunner,
    icebind_multiplier,
    js_round,
    round2,
    scale_enemy,
    smoothstep_transition,
    steel_path_eximus_heavy_gunner,
)


class RoundingTests(unittest.TestCase):
    def test_js_round_half_up(self) -> None:
        self.assertEqual(js_round(0.5), 1)
        self.assertEqual(js_round(1.5), 2)
        self.assertEqual(js_round(2.4), 2)
        # 3.125 is exact in binary; half must round up (not banker's rounding).
        self.assertEqual(round2(3.125), 3.13)


class SmoothstepTests(unittest.TestCase):
    def test_transition_windows(self) -> None:
        # Health/armor window 70-80, Overguard window 45-50.
        self.assertEqual(smoothstep_transition(69, 70, 80), 0.0)
        self.assertEqual(smoothstep_transition(70, 70, 80), 0.0)
        self.assertEqual(smoothstep_transition(80, 70, 80), 1.0)
        self.assertEqual(smoothstep_transition(81, 70, 80), 1.0)
        self.assertAlmostEqual(smoothstep_transition(75, 70, 80), 0.5)
        # T = 0.4 -> s = 3*0.16 - 2*0.064 = 0.352
        self.assertAlmostEqual(smoothstep_transition(47, 45, 50), 0.352)

    def test_curve_endpoints(self) -> None:
        curve = ScalingCurve(0.015, 2.12, 10.7332, 0.72, 70, 80)
        self.assertEqual(curve.multiplier(0), 1.0)
        # q = 90 is past the upper endpoint: pure f2.
        q = 90
        self.assertAlmostEqual(curve.multiplier(q), 1.0 + curve.f2(q))
        # q = 50 is below the lower endpoint: pure f1.
        self.assertAlmostEqual(curve.multiplier(50), 1.0 + curve.f1(50))


class ArmorReductionTests(unittest.TestCase):
    def test_live_infobox_anchor_500_armor(self) -> None:
        # Heavy Gunner infobox: 500 armor -> 38.73% DR.
        self.assertEqual(armor_damage_reduction(500), 0.3873)

    def test_cap_and_floor_values(self) -> None:
        self.assertEqual(armor_damage_reduction(ARMOR_CAP), 0.9)
        self.assertEqual(armor_damage_reduction(ARMOR_FLOOR),
                         js_round(math.sqrt(3.0 * ARMOR_FLOOR) * 100) / 10000)
        self.assertEqual(armor_damage_reduction(0), 0.0)

    def test_icebind_pre_cap_armor(self) -> None:
        # 500 base armor x4 (solo Icebind) = 2000 at base level, below cap.
        self.assertEqual(armor_damage_reduction(2000), 0.7746)


class EximusBaseHealthTests(unittest.TestCase):
    def test_piecewise_branches_armored(self) -> None:
        # 0.25 coefficient because the Heavy Gunner is armored.
        self.assertEqual(eximus_base_health(300, 0), 330.0)       # max(330, 300)
        self.assertEqual(eximus_base_health(300, 15), 330.0)
        self.assertEqual(eximus_base_health(300, 20), 337.5)      # 300 * 1.125
        self.assertEqual(eximus_base_health(300, 100), 1800.0)    # ramp reaches 6
        self.assertEqual(eximus_base_health(300, 101), 1800.0)
        self.assertEqual(eximus_base_health(300, 992), 1800.0)

    def test_flesh_variant_coefficient(self) -> None:
        # 0.375 * (300 + 900) = 450 beats 330 at q <= 15.
        self.assertEqual(eximus_base_health(300, 0, armored=False), 450.0)


class MissionMultiplierTests(unittest.TestCase):
    def test_empowered_table(self) -> None:
        self.assertEqual([empowered_multiplier(n) for n in range(1, 5)],
                         [2.5, 3.0, 3.5, 4.0])

    def test_icebind_table(self) -> None:
        self.assertEqual([icebind_multiplier(n) for n in range(1, 7)],
                         [4.0, 5.0, 6.0, 7.0, 8.0, 9.0])

    def test_player_count_bounds(self) -> None:
        with self.assertRaises(ValueError):
            empowered_multiplier(0)
        with self.assertRaises(ValueError):
            icebind_multiplier(7)


class HeavyGunnerAnchorTests(unittest.TestCase):
    def test_base_level_matches_live_infobox(self) -> None:
        hg = scale_enemy(HEAVY_GUNNER, 8)
        self.assertEqual(hg.health, 300.0)
        self.assertEqual(hg.armor, 500.0)
        self.assertEqual(hg.armor_dr, 0.3873)
        self.assertEqual(hg.ehp, 489.64)  # infobox "EHP 489.64"
        self.assertEqual(hg.overguard, 0.0)

    def test_base_level_eximus(self) -> None:
        ex = scale_enemy(HEAVY_GUNNER, 8, eximus=True)
        self.assertEqual(ex.base_health_used, 330.0)
        self.assertEqual(ex.overguard, float(OVERGUARD_BASE))
        # 330 / (1 - 0.3873) = 538.60, plus 12 Overguard.
        self.assertEqual(ex.ehp, 550.6)

    def test_steel_path_does_not_touch_armor(self) -> None:
        normal = scale_enemy(HEAVY_GUNNER, 8)
        sp = scale_enemy(HEAVY_GUNNER, 8, mode=MODE_STEEL_PATH)
        self.assertEqual(sp.armor, normal.armor)
        self.assertAlmostEqual(sp.health, normal.health * 2.5)

    def test_icebind_multiplies_base_armor_before_cap(self) -> None:
        solo = scale_enemy(HEAVY_GUNNER, 8, mode=MODE_ICEBIND, players=1)
        self.assertEqual(solo.base_armor_used, 2000.0)  # 500 * 4
        self.assertEqual(solo.armor, 2000.0)
        full = scale_enemy(HEAVY_GUNNER, 8, mode=MODE_ICEBIND, players=6)
        self.assertEqual(full.base_armor_used, 4500.0)  # 500 * 9 -> capped
        self.assertEqual(full.armor, float(ARMOR_CAP))

    def test_level_below_base_rejected(self) -> None:
        with self.assertRaises(ValueError):
            scale_enemy(HEAVY_GUNNER, 7)


class GrineerDamageCurveTests(unittest.TestCase):
    def test_outgoing_damage_factor(self) -> None:
        # At base level every curve is 1; Grineer carry a final x2 factor.
        hg = scale_enemy(HEAVY_GUNNER, 8)
        self.assertEqual(hg.outgoing_damage_multiplier, 2.0)
        self.assertAlmostEqual(
            enemy_damage_multiplier(
                ScalingCurve(0.015, 1.75, 0.0075, 1.55, 1, 25), 0, 2.0),
            2.0)


class TargetDummyATests(unittest.TestCase):
    """Eximus Heavy Gunner, level 150, The Steel Path."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dummy = steel_path_eximus_heavy_gunner(150)

    def test_mode_and_eximus(self) -> None:
        d = self.dummy
        self.assertTrue(d.eximus)
        self.assertEqual(d.mode, MODE_STEEL_PATH)
        self.assertEqual(d.level, 150)

    def test_base_health_stack(self) -> None:
        # Eximus scaler (q=142 > 100) -> 1800, then Steel Path x2.5.
        self.assertEqual(self.dummy.base_health_used, 4500.0)

    def test_armor_capped(self) -> None:
        self.assertEqual(self.dummy.armor, float(ARMOR_CAP))
        self.assertEqual(self.dummy.armor_dr, 0.9)

    def test_full_stats_pinned(self) -> None:
        d = self.dummy
        self.assertEqual(d.health, 1_716_837.41)
        self.assertEqual(d.overguard, 269_918.97)
        self.assertAlmostEqual(d.ehp, 17_438_293.07, places=2)
        self.assertEqual(d.shields, 0.0)
        # Health at 90% DR is worth 10x against the health bar.
        self.assertAlmostEqual(d.health / (1.0 - d.armor_dr) + d.overguard,
                               d.ehp, places=2)


class TargetDummyBTests(unittest.TestCase):
    """Eximus Heavy Gunner, level 1000, The Icebind (all squad sizes)."""

    def test_full_squad_table(self) -> None:
        expected_health = [
            11_113_007.01,
            13_891_258.76,
            16_669_510.52,
            19_447_762.27,
            22_226_014.02,
            25_004_265.78,
        ]
        expected_ehp = [
            112_682_523.08,
            140_465_040.58,
            168_247_558.18,
            196_030_075.68,
            223_812_593.18,
            251_595_110.78,
        ]
        for players in range(1, 7):
            d = icebind_eximus_heavy_gunner(1000, players)
            self.assertEqual(d.armor, float(ARMOR_CAP))
            self.assertEqual(d.armor_dr, 0.9)
            self.assertEqual(d.overguard, 1_552_452.98)  # squad-independent
            self.assertEqual(d.base_health_used, 1800.0 * (3.0 + players))
            self.assertEqual(d.health, expected_health[players - 1])
            self.assertAlmostEqual(d.ehp, expected_ehp[players - 1], places=2)

    def test_full_squad_default_preset(self) -> None:
        d = icebind_eximus_heavy_gunner()
        self.assertEqual(d.players, 6)
        self.assertEqual(d.level, 1000)
        self.assertEqual(d.base_armor_used, 4500.0)  # 500 * 9, pre-cap
        self.assertEqual(d.health, 25_004_265.78)
        self.assertEqual(d.ehp, 251_595_110.78)
        self.assertIn("Icebind x9", d.notes[0])

    def test_overguard_independent_of_squad_size(self) -> None:
        og = {icebind_eximus_heavy_gunner(1000, n).overguard
              for n in range(1, 7)}
        self.assertEqual(og, {1_552_452.98})


if __name__ == "__main__":
    unittest.main()
