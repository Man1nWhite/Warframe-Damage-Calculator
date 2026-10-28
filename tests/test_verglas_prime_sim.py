"""Tests for the Verglas Prime trials against Dummy A.

The stat pins are hand-computed from the wiki pages cited in the module
docstring; the simulation tests pin invariants (Overguard routing, the Heat
strip cap, Fired Up's ramp, seeded reproducibility) rather than a ranking.
"""
from __future__ import annotations

import io
import math
import unittest
from contextlib import redirect_stdout
from unittest import mock

from modules.verglas_prime_sim import (
    BASE_DAMAGE,
    BASE_DAMAGE_TYPE,
    BUILD_BY_KEY,
    MAGAZINE,
    RELOAD_TIME,
    RIFLE_ELEMENTALIST_SD,
    RIVEN_VIRAL_MS_CD,
    SUMMONERS_WRATH,
    Loadout,
    Trial,
    VerglasBuild,
    _static_effects,
    build_verglas,
    eximus_dummy_factory,
    heavy_gunner_factory,
    main,
    run_trials,
    simulate,
    verglas_prime_weapon,
)

DUMMY = eximus_dummy_factory()


class WeaponStatTest(unittest.TestCase):
    """Wiki stat block and mod table wiring."""

    def test_wiki_stat_block(self) -> None:
        weapon = verglas_prime_weapon()
        self.assertEqual(weapon.dmg, BASE_DAMAGE)
        self.assertEqual(weapon.damage[BASE_DAMAGE_TYPE], 32.0)
        self.assertEqual(sum(weapon.damage.values()), 32.0)  # Cold only, no IPS
        self.assertAlmostEqual(weapon.critchan, 0.14)
        self.assertAlmostEqual(weapon.critmult, 2.20)
        self.assertAlmostEqual(weapon.statchan, 0.36)
        self.assertAlmostEqual(weapon.firerate, 12.0)
        self.assertEqual((MAGAZINE, RELOAD_TIME), (80, 1.60))

    def test_resolved_build_stats(self) -> None:
        build = build_verglas(BUILD_BY_KEY["user_list_crit_pair"])
        # 1 + Split Chamber 0.90 + Riven 0.81
        self.assertAlmostEqual(build.multishot, 2.71)
        # 14% x (1 + Critical Delay 200%)
        self.assertAlmostEqual(build.crit_chance, 0.42)
        # quantized 2.20 x (1 + Vital Sense 1.20 + Riven 1.08)
        self.assertAlmostEqual(build.crit_multiplier, 7.228, places=3)
        # 36% x (1 + Rime Rounds 0.60 + High Voltage 0.60)
        self.assertAlmostEqual(build.status_chance, 0.792)
        # 12/s x (1 - Critical Delay 0.20)
        self.assertAlmostEqual(build.fire_rate, 9.6)

    def test_element_groups(self) -> None:
        crit = build_verglas(BUILD_BY_KEY["user_list_crit_pair"])
        # Rime Rounds + High Voltage pair into Magnetic before Fired Up lands.
        self.assertEqual(sorted(crit.hud_by_type_zero), ["MAG", "VIRAL"])
        self.assertEqual(sorted(crit.hud_by_type_full), ["HEAT", "MAG", "VIRAL"])
        heat = build_verglas(BUILD_BY_KEY["heat_pair"])
        self.assertEqual(sorted(heat.hud_by_type_zero), ["HEAT", "MAG", "VIRAL"])
        # Cold + Toxin become Viral, so this loadout has no Magnetic at all.
        viral = build_verglas(BUILD_BY_KEY["viral_heat"])
        self.assertEqual(sorted(viral.hud_by_type_full), ["HEAT", "VIRAL"])

    def test_fired_up_ramp_in_type_damage(self) -> None:
        build = build_verglas(BUILD_BY_KEY["heat_pair"])
        cold_start = build.type_damage(0)["HEAT"]
        capped = build.type_damage(20)["HEAT"]
        self.assertGreater(cold_start, 0.0)  # Hellfire/Thermite already stack Heat
        self.assertAlmostEqual(capped, build.hud_by_type_full["HEAT"])
        self.assertAlmostEqual(build.type_damage(10)["HEAT"],
                               0.5 * (cold_start + capped))
        # Non-Heat groups ignore the Sentinel ramp.
        self.assertAlmostEqual(build.type_damage(0)["VIRAL"],
                               build.type_damage(20)["VIRAL"])

    def test_punch_through_does_not_claim_bodies(self) -> None:
        self.assertEqual(build_verglas(BUILD_BY_KEY["user_list_crit_pair"])
                         .headroom_bodies, 0)  # 0.6 m: less than one 1.2 m body
        self.assertEqual(build_verglas(BUILD_BY_KEY["heat_primed_shred"])
                         .headroom_bodies, 2)  # 0.6 + 2.2 = 2.8 m

    def test_fired_up_is_not_a_weapon_slot(self) -> None:
        loadout = Loadout("bad", ("Fired Up",), RIVEN_VIRAL_MS_CD)
        with self.assertRaises(ValueError):
            _static_effects(loadout)

    def test_unknown_mod_fails_loudly(self) -> None:
        loadout = Loadout("bad", ("Not A Mod",), RIVEN_VIRAL_MS_CD)
        with self.assertRaises(KeyError):
            _static_effects(loadout)

    def test_unsupported_proc_type_is_rejected(self) -> None:
        # Malignant Force + Hellfire combine into Gas, which this model omits.
        loadout = Loadout("gas", ("Malignant Force", "Hellfire"), RIVEN_VIRAL_MS_CD)
        with self.assertRaises(ValueError):
            build_verglas(loadout)

    def test_riven_needs_three_positives(self) -> None:
        from modules.verglas_prime_sim import RivenTraits

        with self.assertRaises(ValueError):
            RivenTraits(("Viral", "Multishot"))
        with self.assertRaises(ValueError):
            RivenTraits(("Viral", "Multishot", "Not A Stat"))


class DummyTest(unittest.TestCase):
    """The two dummy factories to match ``enemy_scaling``."""

    def test_eximus_dummy(self) -> None:
        self.assertAlmostEqual(DUMMY.max_health, 1_716_837.41, places=1)
        self.assertAlmostEqual(DUMMY.max_armor, 2_700.0, places=6)
        self.assertAlmostEqual(DUMMY.overguard_max, 269_918.97, places=1)

    def test_plain_dummy_has_no_overguard(self) -> None:
        plain = heavy_gunner_factory()
        self.assertAlmostEqual(plain.max_health, 286_139.57, places=1)
        self.assertEqual(plain.overguard_max, 0.0)


class SimulateTest(unittest.TestCase):
    """Invariants of a single trial."""

    build: VerglasBuild
    trial: Trial

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = build_verglas(BUILD_BY_KEY["user_list_crit_pair"])
        cls.trial = simulate(cls.build, eximus_dummy_factory(), seed=7)

    def test_seeded_reproducibility(self) -> None:
        again = simulate(self.build, eximus_dummy_factory(), seed=7)
        self.assertEqual(again, self.trial)

    def test_trial_ordering(self) -> None:
        trial = self.trial
        self.assertIsInstance(trial, Trial)
        self.assertTrue(math.isfinite(trial.ttk))
        self.assertLess(trial.overguard_break_time, trial.ttk)
        self.assertGreater(trial.attacks, 0)
        self.assertEqual(trial.fired_up_peak, 20)  # ramps inside one magazine

    def test_overguard_routing(self) -> None:
        # Overguard is depleted exactly, never overdrawn into health.
        absorbed = self.trial.direct_to_overguard + self.trial.dot_to_overguard
        self.assertAlmostEqual(absorbed, DUMMY.overguard_max, delta=1.0)
        # Every point of health damage is accounted for, with at most one
        # overkill tick of overshoot.
        total = (self.trial.direct_to_health + self.trial.dot_to_health
                 + self.trial.break_electric)
        self.assertGreaterEqual(total, DUMMY.max_health)
        self.assertLess(total, DUMMY.max_health * 1.10)

    def test_heat_strip_caps_at_half_armor(self) -> None:
        self.assertAlmostEqual(self.trial.final_armor, 1_350.0)

    def test_break_electric_needs_magnetic_stacks(self) -> None:
        self.assertGreater(self.trial.magnetic_procs, 0)
        self.assertGreater(self.trial.break_electric, 0.0)
        # The Cold+Toxin loadout has no Magnetic group, so no break burst.
        viral = build_verglas(BUILD_BY_KEY["viral_heat"])
        trial = simulate(viral, eximus_dummy_factory(), seed=7)
        self.assertEqual(trial.magnetic_procs, 0)
        self.assertEqual(trial.break_electric, 0.0)
        self.assertTrue(math.isfinite(trial.ttk))  # still kills on paper damage

    def test_timeout_is_reported_not_hidden(self) -> None:
        trial = simulate(self.build, eximus_dummy_factory(), seed=7,
                         max_time=2.0)
        self.assertEqual(trial.ttk, math.inf)
        self.assertTrue(math.isfinite(trial.overguard_break_time))


class RunTrialsTest(unittest.TestCase):
    """Monte Carlo summaries."""

    def test_summary_shape(self) -> None:
        summary = run_trials(build_verglas(BUILD_BY_KEY["heat_pair"]), trials=5,
                             base_seed=11)
        self.assertEqual(summary["trials"], 5)
        self.assertEqual(summary["kills"] + summary["timeouts"], 5)
        self.assertEqual(summary["kills"], 5)
        self.assertLessEqual(summary["ttk_p10"], summary["ttk_median"])
        self.assertLessEqual(summary["ttk_median"], summary["ttk_p90"])
        for key in ("overguard_median", "heat_procs_median", "reloads_median",
                    "final_armor_median", "direct_health_median",
                    "dot_health_median", "break_electric_median"):
            self.assertIn(key, summary)

    def test_all_timeouts(self) -> None:
        summary = run_trials(build_verglas(BUILD_BY_KEY["heat_pair"]), trials=3,
                             base_seed=11, max_time=0.1)
        self.assertEqual(summary["kills"], 0)
        self.assertEqual(summary["timeouts"], 3)
        self.assertEqual(summary["ttk_median"], math.inf)

    def test_trials_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            run_trials(build_verglas(BUILD_BY_KEY["heat_pair"]), trials=0)

    def test_final_build_keeps_magnetic_viral_and_heat(self) -> None:
        build = build_verglas(BUILD_BY_KEY["final_recommended"])
        self.assertEqual(sorted(build.hud_by_type_full),
                         ["HEAT", "MAG", "VIRAL"])
        # 0.6 m from Rifle Elementalist + 2.2 m from Primed Shred.
        self.assertAlmostEqual(build.punch_through, 2.8)
        self.assertEqual(build.headroom_bodies, 2)

    def test_final_build_beats_the_crit_pair(self) -> None:
        final = run_trials(build_verglas(BUILD_BY_KEY["final_recommended"]),
                           trials=15, base_seed=99)
        crit = run_trials(build_verglas(BUILD_BY_KEY["user_list_crit_pair"]),
                          trials=15, base_seed=99)
        self.assertLess(final["ttk_median"], crit["ttk_median"])

    def test_heat_pair_beats_the_crit_pair(self) -> None:
        """The comparison the report makes, on shared seeds."""
        crit = run_trials(build_verglas(BUILD_BY_KEY["user_list_crit_pair"]),
                          trials=15, base_seed=99)
        heat = run_trials(build_verglas(BUILD_BY_KEY["heat_pair"]), trials=15,
                          base_seed=99)
        self.assertLess(heat["ttk_median"], crit["ttk_median"])

    def test_summoners_wrath_and_elementalist_are_the_assumed_values(self) -> None:
        self.assertEqual(SUMMONERS_WRATH, 0.75)
        self.assertEqual(RIFLE_ELEMENTALIST_SD, 0.90)


class CommandLineTest(unittest.TestCase):
    """The module CLI."""

    def test_single_build_report(self) -> None:
        buffer = io.StringIO()
        with mock.patch("sys.argv", ["verglas", "--trials", "2",
                                     "--build", "heat_pair"]), \
                redirect_stdout(buffer):
            main()
        output = buffer.getvalue()
        self.assertIn("Verglas Prime", output)
        self.assertIn("heat_pair", output)
        self.assertIn("resolved build", output)
        self.assertIn("Overguard-break Electricity", output)

    def test_unknown_build_is_an_error(self) -> None:
        with mock.patch("sys.argv", ["verglas", "--trials", "1",
                                     "--build", "nope"]), \
                redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyError):
                main()


if __name__ == "__main__":
    unittest.main()
