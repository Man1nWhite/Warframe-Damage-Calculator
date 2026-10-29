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
from dataclasses import replace
from unittest import mock

from modules.kuva_nukor_sim import DummyTarget, MagneticSource
from modules.status_damage import heat_tick
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
    RivenTraits,
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

    def test_riven_needs_three_distinct_positives_and_at_most_one_splice(self) -> None:
        for positives in (("Viral", "Multishot"),
                          ("Viral", "Multishot", "Not A Stat"),
                          ("Viral", "Viral", "Multishot"),
                          ("Viral", "Magnetic", "Multishot")):
            with self.subTest(positives=positives), self.assertRaises(ValueError):
                RivenTraits(positives)

    def test_incomplete_cursed_riven_is_rejected_instead_of_ignoring_its_negative(self) -> None:
        loadout = replace(BUILD_BY_KEY["heat_pair"],
                          riven=RivenTraits(RIVEN_VIRAL_MS_CD.positives, cursed=True))
        with self.assertRaisesRegex(ValueError, "(?i)curse|negative"):
            build_verglas(loadout)

    def test_invalid_weapon_mod_loadouts_fail_loudly(self) -> None:
        base = BUILD_BY_KEY["heat_pair"]
        invalid = (
            replace(base, mods=base.mods + ("Vile Acceleration",)),  # nine with Riven
            replace(base, mods=base.mods[:-1] + ("Serration",)),
            replace(base, mods=base.mods[:-2] + ("Critical Delay", "Point Strike")),
            replace(base, mods=base.mods[:-1] + ("Galvanized Chamber",)),
        )
        for loadout in invalid:
            with self.subTest(mods=loadout.mods), self.assertRaises(ValueError):
                build_verglas(loadout)


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

    def test_magnetic_source_receives_even_combined_electricity_mods(self) -> None:
        # High Voltage combines into Magnetic. The break Electricity still
        # benefits, including an Electricity Riven positive when present.
        for loadout in (
            BUILD_BY_KEY["heat_pair"],
            replace(BUILD_BY_KEY["heat_pair"],
                    riven=RivenTraits(("Viral", "Electricity", "Critical Damage"))),
        ):
            with self.subTest(loadout=loadout):
                build = build_verglas(loadout)
                with mock.patch("modules.verglas_prime_sim.MagneticSource",
                                wraps=MagneticSource) as source:
                    simulate(build, DummyTarget(1e12, 0, 1e9), seed=7, max_time=0.1)
                source.assert_called_once()
                self.assertAlmostEqual(source.call_args.kwargs["electricity_bonus"],
                                       build.effects["ELEC"])
        self.assertGreater(build.effects["ELEC"], 0.6)

    def test_status_damage_depends_on_equipped_elementalist(self) -> None:
        equipped = BUILD_BY_KEY["heat_pair"]
        absent = replace(equipped, key="no_elementalist",
                         mods=tuple(mod for mod in equipped.mods if mod != "Rifle Elementalist"))
        for loadout, bonus in ((equipped, 0.9), (absent, 0.0)):
            with self.subTest(loadout=loadout.key):
                build = build_verglas(loadout)
                target = DummyTarget(1e12, 0, 1e9)
                with mock.patch("modules.verglas_prime_sim.MagneticSource",
                                wraps=MagneticSource) as source, \
                     mock.patch("modules.verglas_prime_sim.heat_tick", wraps=heat_tick) as tick:
                    simulate(build, target, seed=7, max_time=2.5)
                self.assertAlmostEqual(source.call_args.kwargs["status_damage_bonus"], bonus)
                self.assertGreater(tick.call_count, 0)
                for call in tick.call_args_list:
                    self.assertAlmostEqual(call.kwargs["status_damage_bonus"], bonus)

    def test_status_duration_riven_reaches_the_live_statuses(self) -> None:
        loadout = replace(BUILD_BY_KEY["heat_pair"],
                          riven=RivenTraits(("Viral", "Multishot", "Status Duration")))
        build = build_verglas(loadout)
        duration_mult = 1.0 + build.effects["STATUS_DURATION"]
        target = DummyTarget(1e12, 2700, 1e9)
        with mock.patch.object(target, "add_heat", wraps=target.add_heat) as heat, \
             mock.patch.object(target, "add_magnetic", wraps=target.add_magnetic) as magnetic, \
             mock.patch.object(target, "absorb", wraps=target.absorb) as absorb:
            simulate(build, target, seed=7, max_time=2.0)
        self.assertGreater(heat.call_count, 0)
        self.assertGreater(magnetic.call_count, 0)
        self.assertAlmostEqual(heat.call_args.args[3], 6.0 * duration_mult)
        self.assertAlmostEqual(magnetic.call_args.args[1], 6.0 * duration_mult)
        self.assertAlmostEqual(magnetic.call_args.args[2].duration_multiplier, duration_mult)
        self.assertAlmostEqual(absorb.call_args.args[2], 0.5 * duration_mult)

    def test_trace_records_fired_up_cap_once(self) -> None:
        target = DummyTarget(1e12, 0, 1e9)
        trial = simulate(self.build, target, seed=7, max_time=4.0, trace=True)
        self.assertEqual(sum("Fired Up capped" in line for line in trial.trace), 1)

    def test_fired_up_counts_own_heat_ticks_between_weapon_hits(self) -> None:
        build = replace(self.build, fire_rate=1.0, multishot=1.0, status_chance=1.0)
        with mock.patch.object(type(build), "proc_weights", return_value=(["HEAT"], [1.0])), \
             mock.patch.object(type(build), "type_damage", autospec=True,
                               side_effect=type(build).type_damage) as damage:
            trial = simulate(build, DummyTarget(1e12, 0, 0), seed=7, max_time=2.5)
        self.assertEqual([call.args[1] for call in damage.call_args_list], [1, 3, 5])
        self.assertEqual(trial.fired_up_peak, 5)

    def test_fired_up_counts_own_magnetic_break_electricity_ticks(self) -> None:
        build = replace(self.build, fire_rate=1.0, multishot=1.0,
                        status_chance=1.0, crit_chance=0.0)
        with mock.patch.object(type(build), "proc_weights", return_value=(["MAG"], [1.0])), \
             mock.patch.object(type(build), "type_damage", autospec=True,
                               return_value={"MAG": 100.0}) as damage:
            trial = simulate(build, DummyTarget(1e12, 0, 300), seed=7, max_time=2.5)
        # First hit procs Magnetic; the second breaks Overguard and triggers
        # an immediate Electricity tick, followed by another tick at t=2.
        self.assertEqual(trial.overguard_break_time, 1.0)
        self.assertEqual([call.args[1] for call in damage.call_args_list], [1, 2, 5])

    def test_cold_proc_is_applied_once_and_does_not_refresh_freeze(self) -> None:
        build = replace(self.build, fire_rate=1.0, multishot=1.0, status_chance=1.0)
        target = DummyTarget(1e12, 0, 0)
        with mock.patch.object(type(build), "proc_weights", return_value=(["COLD"], [1.0])):
            simulate(build, target, seed=7, max_time=2.5)
        self.assertEqual(target.cold_stacks(2.5), 3)

        frozen = DummyTarget(1e12, 0, 0)
        for _ in range(10):
            frozen.add_cold(0, 6)
        with mock.patch.object(type(build), "proc_weights", return_value=(["COLD"], [1.0])):
            simulate(build, frozen, seed=7, max_time=2.5)
        self.assertEqual(frozen.cold_stacks(3.0), 3)
        self.assertEqual(frozen.unique_status_count(6.0), 0)

    def test_external_damage_over_time_does_not_stack_fired_up(self) -> None:
        build = replace(self.build, fire_rate=0.25, status_chance=0.0)
        heat_primed = DummyTarget(1e12, 0, 0)
        heat_primed.add_heat(0, 100.0, 1.0, 6.0)
        magnetic_primed = DummyTarget(1e12, 0, 1)
        magnetic_primed.add_magnetic(0, 6.0, MagneticSource())
        for target in (heat_primed, magnetic_primed):
            with self.subTest(target=target):
                trial = simulate(build, target, seed=7, max_time=2.5)
                self.assertEqual(trial.attacks, 1)
                self.assertEqual(trial.fired_up_peak, 1)


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
