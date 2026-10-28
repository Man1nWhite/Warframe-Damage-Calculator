"""Regression checks for the experimental Akarius comparison scenarios."""
import contextlib
import io
import json
import unittest

from modules.akarius_comparison import (
    _constant_mean_crit,
    _preprime_viral,
    compare,
    discard_overguard_overflow_route,
    neutral_overguard_route,
    ordinary_gunner_factory,
)
from modules.akarius_sim import RIVEN_VIRAL, build_akarius
from modules.damage_routing import route_enemy_hit


class AkariusComparisonTests(unittest.TestCase):
    def test_ordinary_factory_and_external_viral_are_independent(self):
        primed = _preprime_viral(ordinary_gunner_factory())
        fresh = ordinary_gunner_factory()
        self.assertEqual(primed.overguard, 0.0)
        self.assertEqual(primed.viral_stacks(0.0), 5)
        self.assertEqual(primed.unique_status_count(0.0), 1)
        self.assertEqual(primed.viral_stacks(6.0), 0)
        self.assertEqual(fresh.viral_stacks(0.0), 0)

    def test_neutral_overguard_applies_type_modifier_only_to_health(self):
        # Half of the unmodified mixed hit breaks OG; the other half reaches
        # health, where Corrosive receives the 1.5x Grineer type modifier.
        damage = {"CORROSIVE": 100.0, "VIRAL": 100.0}
        modifiers = {"CORROSIVE": 1.5}
        result = neutral_overguard_route(
            damage, overguard=100, armor=0, faction_type_modifiers=modifiers)
        self.assertEqual(result.overguard, 100)
        self.assertEqual(result.health, 125)
        self.assertTrue(result.broke_overguard)
        self.assertEqual(
            neutral_overguard_route(damage, overguard=0, armor=0,
                                    faction_type_modifiers=modifiers),
            route_enemy_hit(damage, overguard=0, armor=0,
                            faction_type_modifiers=modifiers))

    def test_overguard_discard_sensitivity_only_discards_breaking_hit(self):
        kwargs = {"overguard": 100.0, "armor": 0.0}
        partial = discard_overguard_overflow_route({"VIRAL": 50.0}, **kwargs)
        breaking = discard_overguard_overflow_route({"VIRAL": 200.0}, **kwargs)
        exposed = discard_overguard_overflow_route({"VIRAL": 200.0},
                                                   overguard=0.0, armor=0.0)
        self.assertFalse(partial.broke_overguard)
        self.assertEqual(partial.health, 0.0)
        self.assertTrue(breaking.broke_overguard)
        self.assertEqual(breaking.health, 0.0)
        self.assertEqual(exposed.health, 200.0)

    def test_constant_crit_preserves_average_multiplier(self):
        original = build_akarius(RIVEN_VIRAL)
        constant = _constant_mean_crit(original)
        self.assertEqual(constant.afcc_pct, 100)
        self.assertAlmostEqual(
            constant.crit_multiplier,
            1 + original.afcc_pct / 100 * (original.crit_multiplier - 1))

    def test_paired_comparison_emits_seeded_summary(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = compare("test", ordinary_gunner_factory, 3, 123,
                             direct_hits=False)
        self.assertEqual(json.loads(out.getvalue()), result)
        self.assertEqual(result["seed_start"], 123)
        self.assertFalse(result["direct_hits"])
        self.assertEqual(result["viral"]["attempted"], 3)
        self.assertEqual(result["corrosive"]["timed_out"], 0)
        self.assertEqual(result["paired"]["complete_pairs"], 3)

    def test_single_pair_does_not_claim_a_sampling_interval(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = compare("test", ordinary_gunner_factory, 1, 123)
        self.assertEqual(result["paired"]["complete_pairs"], 1)
        self.assertIsNone(result["paired"]["approx_95pct_mc_interval_s"])
        with self.assertRaises(ValueError):
            compare("empty", ordinary_gunner_factory, 0, 123)


if __name__ == "__main__":
    unittest.main()
