"""Deterministic routing/timing integration checks, not validated TTKs.

Mixed-hit overflow allocation and faction type modifiers on Overguard are
explicit model assumptions; the tests pin the chosen implementation.
"""
import math
import unittest
from dataclasses import replace
from unittest.mock import patch

import modules.akarius_sim as akarius
import modules.alternox_prime_sim as alternox
import modules.jat_kittag_sim as jat
import modules.kuva_nukor_sim as nukor
import modules.ocucor_sim as ocucor
from modules.constants import FACTION_MULTIPLIERS
from modules.damage_routing import route_enemy_hit
from modules.status_damage import magnetic_break_electric_tick


class SimulatorRoutingIntegrationTests(unittest.TestCase):
    @staticmethod
    def cases():
        """One attack before t=3, with no random statuses or criticals."""
        return (
            ("Nukor", replace(nukor.build_nukor(), multishot=1,
                              status_per_beam=0, afcc_pct=0, tick_interval=3),
             nukor.DummyTarget, lambda b, t, cutoff: nukor.simulate(b, t, max_time=cutoff)),
            ("Ocucor", replace(ocucor.build_ocucor(), multishot=1,
                               status_per_beam=0, afcc_pct=0, tick_interval=3),
             nukor.DummyTarget, lambda b, t, cutoff: ocucor.simulate(b, t, max_time=cutoff)),
            ("Akarius", replace(akarius.build_akarius(), multishot=1,
                                status_per_instance=0, afcc_pct=0,
                                intra_burst_delay=3, burst_cycle=6),
             akarius.AkariusTarget, lambda b, t, cutoff: akarius.simulate(b, t, max_time=cutoff)),
            ("Jat", replace(jat.build_jat_kittag("Corrosive (Shocking Touch)"),
                            status_per_slam=0, crit_chance=0, slam_interval=3),
             jat.JatTarget, lambda b, t, cutoff: jat.simulate(
                 b, t, afflictions=False, max_time=cutoff)),
            ("Alternox", replace(alternox.build_alternox(), multishot=1,
                                 status_per_pellet=0, crit_chance=0, fire_rate=1 / 3),
             alternox.AlternoxTarget, lambda b, t, cutoff: alternox.simulate(b, t, max_time=cutoff)),
        )

    def test_all_simulators_route_mixed_hit_and_source_attributed_break_ticks(self):
        source = nukor.MagneticSource(status_damage_bonus=0.3, faction_bonus=0.2,
                                      electricity_bonus=0.4, duration_multiplier=2)
        # The target started with 10,000 OG but has only one point left.
        # Its break proc uses the maximum, while overflow uses the remainder.
        raw_tick = magnetic_break_electric_tick(
            10_000, 1, status_damage_bonus=0.3, faction_bonus=0.2,
            electricity_bonus=0.4)
        for name, build, target_class, simulate in self.cases():
            for cutoff, expected_times in ((0.75, [0.0]), (1.1, [0.0, 1.0])):
                with self.subTest(weapon=name, cutoff=cutoff):
                    target = target_class(1e9, 2700, 10_000)
                    target.overguard = 1
                    target.add_magnetic(0, 6, source)
                    target.viral_expiries.append(0.5)  # expires before t=1
                    captured = []
                    original = target.absorb

                    def capture(damage, when, ramp, **kwargs):
                        result = original(damage, when, ramp, **kwargs)
                        captured.append((damage, when, result))
                        return result

                    with patch.object(target, "absorb", side_effect=capture):
                        trial = simulate(build, target, cutoff)
                    self.assertTrue(math.isinf(trial.ttk))
                    self.assertEqual(target.overguard, 0)
                    self.assertEqual(target.overguard_broken_at, 0)

                    direct, when, outcome = captured[0]
                    self.assertGreater(len(direct), 1)  # retain type components
                    self.assertEqual(when, 0)
                    expected = route_enemy_hit(
                        direct, overguard=1, armor=2700,
                        magnetic_stacks=1, viral_stacks=1,
                        faction_type_modifiers=FACTION_MULTIPLIERS["Grineer"])
                    self.assertTrue(outcome.broke_overguard)
                    self.assertAlmostEqual(outcome.overguard, expected.overguard)
                    self.assertAlmostEqual(outcome.health, expected.health)
                    self.assertGreater(outcome.health, 0)  # no enemy depletion gate

                    electric = [(damage, time, result) for damage, time, result in captured
                                if set(damage) == {"ELEC"}]
                    self.assertEqual([time for _, time, _ in electric], expected_times)
                    for damage, time, result in electric:
                        self.assertAlmostEqual(damage["ELEC"], raw_tick)
                        viral = 2 if time == 0 else 1
                        self.assertAlmostEqual(result.health, raw_tick * viral * 0.1)
                    self.assertEqual(target.next_magnetic_electric_tick(), 1 if cutoff < 1 else 2)

    def test_beam_room_settles_pending_event_at_cutoff_but_not_after(self):
        for module, build in (
            (nukor, replace(nukor.build_nukor(), type_damage={}, multishot=1,
                            status_per_beam=0, afcc_pct=0, tick_interval=2)),
            (ocucor, replace(ocucor.build_ocucor(), type_damage={}, multishot=1,
                             status_per_beam=0, afcc_pct=0, tick_interval=2)),
        ):
            for cutoff, expected_health in ((0.4, 1000), (0.75, 900)):
                with self.subTest(module=module.__name__, cutoff=cutoff):
                    made = []
                    def factory():
                        target = nukor.DummyTarget(1000, 0, 0)
                        target.magnetic_break_procs.append(
                            nukor.MagneticBreakProc(0.5, 2.5, 100))
                        made.append(target)
                        return target
                    if module is nukor:
                        result = module.simulate_room(build, 1, factory=factory,
                                                      max_time=cutoff)
                    else:
                        with patch.object(ocucor, "build_ocucor", return_value=build):
                            result = ocucor.simulate_room(build.arcane, build.riven_stat, 1,
                                                          factory=factory, max_time=cutoff)
                    self.assertTrue(math.isinf(result.clear_time))
                    self.assertEqual(made[0].health, expected_health)
                    self.assertEqual(made[0].next_magnetic_electric_tick(),
                                     0.5 if cutoff < 0.5 else 1.5)

    def test_blast_fuses_resolve_at_their_deadline_before_cutoff(self):
        cases = (
            ("Nukor", replace(nukor.build_nukor(), type_damage={}, multishot=1,
                              status_per_beam=0, afcc_pct=0, tick_interval=3),
             nukor.DummyTarget, lambda b, t, cutoff: nukor.simulate(b, t, max_time=cutoff)),
            ("Akarius", replace(akarius.build_akarius(), impact_instance={}, blast_instance={},
                                multishot=1, status_per_instance=0, afcc_pct=0,
                                intra_burst_delay=3, burst_cycle=6),
             akarius.AkariusTarget, lambda b, t, cutoff: akarius.simulate(b, t, max_time=cutoff)),
            ("Alternox", replace(alternox.build_alternox(), multishot=1,
                                 status_per_pellet=0, fire_rate=1 / 3,
                                 mix=alternox.ElementMix({}, ())),
             alternox.AlternoxTarget, lambda b, t, cutoff: alternox.simulate(b, t, max_time=cutoff)),
        )
        for name, build, target_class, simulate in cases:
            for cutoff in (0.4, 0.6):
                with self.subTest(weapon=name, cutoff=cutoff):
                    target = target_class(10, 0, 0)
                    target.blast_stacks.append(nukor.BlastProc(0, 0.5, 40, 1))
                    result = simulate(build, target, cutoff)
                    if cutoff < 0.5:
                        self.assertEqual(target.health, 10)
                        self.assertTrue(math.isinf(result.ttk))
                    else:
                        self.assertLessEqual(target.health, 0)
                        self.assertEqual(result.ttk, 0.5)
                        if name != "Alternox":
                            # No Overguard existed at the start; it was not
                            # still present until the eventual death time.
                            self.assertEqual(result.overguard_break_time, 0)

    def test_alternox_applied_magnetic_retains_rifle_source_modifiers(self):
        # One Magnetic-only proc at t=0; a later manually broken OG lets us
        # inspect its source rather than attributing the break to another hit.
        build = replace(alternox.build_alternox((alternox.R_BLAST, alternox.R_ELEC,
                                                 alternox.R_DAMAGE)),
                        multishot=1, status_per_pellet=1, crit_chance=0,
                        mix=alternox.ElementMix({"MAG": 1.0}, ("MAG",)))
        target = alternox.AlternoxTarget(1e9, 0, 1e9)
        alternox.simulate(build, target, max_time=0.01, elementalist=0.9)
        self.assertEqual(target.mag_stacks(0), 1)
        self.assertEqual(target.magnetic_source.status_damage_bonus, 0.9)
        self.assertEqual(target.magnetic_source.electricity_bonus,
                         build.riven[alternox.R_ELEC])


class PerProcTimingTests(unittest.TestCase):
    def test_alternox_analytic_status_damage_inherits_crit_tiers(self):
        build = replace(alternox.build_alternox(), crit_chance=1.5,
                        crit_multiplier=3, galv_kill_stacks=0,
                        multishot=1, fire_rate=1, status_per_pellet=1)
        result = alternox.expected_dps(build, viral_stacks=0)
        weights = build.mix.weights()
        expected_crit = 1 + 1.5 * (3 - 1)
        self.assertAlmostEqual(result.electric_proc_dps,
            weights["ELEC"] * (build.modded_base * expected_crit + 1)
            * 0.5 * 1.9 * 6)
        self.assertAlmostEqual(result.blast_proc_dps,
            weights["BLAST"] * build.modded_base * expected_crit * 0.3 * 1.9)

    def jat_build(self):
        return replace(jat.build_jat_kittag("Killing Blow"), type_damage={},
                       status_per_slam=0, slam_interval=10, faction_bracket=1,
                       toxin_elemental_bonus=0, status_damage_bonus=0)

    def test_jat_gas_starts_immediately_and_toxin_after_one_second(self):
        for cutoff, expected in ((0.24, 0), (0.25, 20.5),
                                 (1.24, 20.5), (1.25, 61.5),
                                 (6.25, 12 * 20.5)):
            with self.subTest(cutoff=cutoff):
                target = jat.JatTarget(1e9, 0, 0)
                target.gas_procs.append(jat.GasProc(0.25, 40, 1))
                target.toxin_procs.append(jat.ToxinProc(0.25, 40, 1))
                result = jat.simulate(self.jat_build(), target, afflictions=False,
                                      max_time=cutoff)
                self.assertAlmostEqual(result.dot_to_health, expected)

    def test_heat_groups_tick_relative_to_first_application(self):
        cases = (
            ("Nukor", replace(nukor.build_nukor(), type_damage={}, multishot=1,
                              status_per_beam=0, afcc_pct=0, tick_interval=10,
                              heat_bonus=0, proc_duration=6),
             nukor.DummyTarget, lambda b, t, cutoff: nukor.simulate(b, t, max_time=cutoff)),
            ("Ocucor", replace(ocucor.build_ocucor(), type_damage={}, multishot=1,
                               status_per_beam=0, afcc_pct=0, tick_interval=10,
                               heat_bonus=0, proc_duration=6),
             nukor.DummyTarget, lambda b, t, cutoff: ocucor.simulate(b, t, max_time=cutoff)),
            ("Akarius", replace(akarius.build_akarius(), impact_instance={}, blast_instance={},
                                multishot=1, status_per_instance=0, afcc_pct=0,
                                intra_burst_delay=10, burst_cycle=20,
                                heat_bonus=0, proc_duration=6),
             akarius.AkariusTarget, lambda b, t, cutoff: akarius.simulate(b, t, max_time=cutoff)),
        )
        for name, build, target_class, simulate in cases:
            for cutoff, ticks in ((1.24, 0), (1.25, 1), (2.25, 2),
                                  (6.25, 6), (6.75, 6)):
                with self.subTest(weapon=name, cutoff=cutoff):
                    target = target_class(1e9, 0, 0)
                    target.heat_procs.append(nukor.HeatProc(0.25, 40, 1, 0.25))
                    simulate(build, target, cutoff)
                    self.assertAlmostEqual(target.health, 1e9 - ticks * 20.5 * 1.9,
                                           places=6)

    def test_no_initial_overguard_is_reported_from_time_zero(self):
        build = replace(ocucor.build_ocucor(), type_damage={}, multishot=1,
                        status_per_beam=0, afcc_pct=0, tick_interval=10,
                        heat_bonus=0, proc_duration=6)
        target = nukor.DummyTarget(10, 0, 0)
        target.heat_procs.append(nukor.HeatProc(0.25, 40, 1, 0.25))
        result = ocucor.simulate(build, target, max_time=2)
        self.assertEqual(result.ttk, 1.25)
        self.assertEqual(result.overguard_break_time, 0)

        target = jat.JatTarget(10, 0, 0)
        target.gas_procs.append(jat.GasProc(0.25, 40, 1))
        result = jat.simulate(self.jat_build(), target, afflictions=False, max_time=2)
        self.assertEqual(result.ttk, 0.25)
        self.assertEqual(result.overguard_break_time, 0)

    def test_heat_refresh_keeps_pulse_phase(self):
        target = nukor.DummyTarget(1000, 0, 0)
        target.add_heat(0.25, 40, 1, 6)
        target.add_heat(0.75, 80, 1, 6)
        self.assertEqual(target.next_heat_tick(6), 1.25)
        first = target.consume_heat_tick(1.25, 6)
        self.assertEqual([p.seed for p in first], [40])
        self.assertEqual(target.next_heat_tick(6), 2.25)
        second = target.consume_heat_tick(2.25, 6)
        self.assertEqual([p.seed for p in second], [40, 80])

    def test_heat_tick_and_expiry_do_not_lose_fractional_timestamps(self):
        target = nukor.DummyTarget(1000, 0, 0)
        start = 1 / 12  # Common beam cadence; (start + 1) - start is < 1 in binary64.
        target.add_heat(start, 40, 1, 6)
        self.assertEqual([p.seed for p in target.consume_heat_tick(start + 1, 6)], [40])

        target = nukor.DummyTarget(1000, 0, 0)
        start = 4.293594722082491  # Subtraction makes the exact expiry appear late.
        target.add_heat(start, 40, 1, 6)
        target.toxin_procs.append(nukor.ToxinProc(start, 40, 1))
        target.prune(start + 6, 6)
        self.assertEqual(len(target.heat_procs), 1)
        self.assertEqual(len(target.toxin_procs), 1)

    def test_beam_rooms_keep_heat_pulses_per_target(self):
        for module, build in (
            (nukor, replace(nukor.build_nukor(), type_damage={}, multishot=1,
                            status_per_beam=0, afcc_pct=0, tick_interval=10,
                            heat_bonus=0, proc_duration=6)),
            (ocucor, replace(ocucor.build_ocucor(), type_damage={}, multishot=1,
                             status_per_beam=0, afcc_pct=0, tick_interval=10,
                             heat_bonus=0, proc_duration=6)),
        ):
            with self.subTest(module=module.__name__):
                made = []
                def factory():
                    target = nukor.DummyTarget(1000, 0, 0)
                    start = 0.25 if not made else 0.75
                    target.heat_procs.append(nukor.HeatProc(start, 40, 1, start))
                    made.append(target)
                    return target
                if module is nukor:
                    nukor.simulate_room(build, 2, factory=factory, max_time=1.5)
                else:
                    with patch.object(ocucor, "build_ocucor", return_value=build), \
                         patch.object(ocucor, "BASE_STATUS", 0):
                        ocucor.simulate_room(build.arcane, build.riven_stat, 2,
                                             factory=factory, max_time=1.5)
                self.assertAlmostEqual(made[0].health, 1000 - 20.5 * 1.9)
                self.assertEqual(made[1].health, 1000)

    def test_heat_expiry_is_pruned_before_final_armor(self):
        build = replace(nukor.build_nukor(), type_damage={}, multishot=1,
                        status_per_beam=0, afcc_pct=0, tick_interval=10,
                        heat_bonus=0, proc_duration=6, heat_ramp_interval=0.5)
        target = nukor.DummyTarget(1e9, 2700, 0)
        target.heat_procs.append(nukor.HeatProc(0.25, 40, 1, 0.25))
        result = nukor.simulate(build, target, max_time=8)
        # Expires at 6.25; at 7.75 the restore steps from 50% to 40% strip.
        self.assertAlmostEqual(result.final_armor, 2700 * 0.6)

    def test_jat_applies_faction_bonus_to_seed_and_tick(self):
        build = replace(self.jat_build(), status_per_slam=1,
                        proc_weights={"TOXIN": 1}, crit_chance=0,
                        faction_bracket=1.55)
        target = jat.JatTarget(1e9, 0, 0)
        result = jat.simulate(build, target, afflictions=False, max_time=1.1)
        self.assertEqual(result.toxin_procs, 1)
        self.assertAlmostEqual(target.toxin_procs[0].seed, build.modded_base * 1.55)
        self.assertAlmostEqual(result.dot_to_health,
                               (build.modded_base * 1.55 + 1) * 0.5 * 1.55)

    def test_nukor_toxin_ticks_are_independent_and_application_relative(self):
        build = replace(nukor.build_nukor(), type_damage={}, multishot=1,
                        status_per_beam=0, afcc_pct=0, tick_interval=20,
                        toxin_bonus=0, proc_duration=6)
        for cutoff, expected in ((1.24, 0), (1.25, 20.5 * 1.9),
                                 (1.75, (20.5 + 40.5) * 1.9)):
            with self.subTest(cutoff=cutoff):
                target = nukor.DummyTarget(1e9, 0, 0)
                target.toxin_procs.extend([nukor.ToxinProc(0.25, 40, 1),
                                           nukor.ToxinProc(0.75, 80, 1)])
                result = nukor.simulate(build, target, max_time=cutoff)
                self.assertAlmostEqual(result.dot_to_health, expected)

        # An expired stack's next nominal pulse must not piggyback on a live
        # stack that happens to tick at the same time.
        target = nukor.DummyTarget(1e9, 0, 0)
        target.toxin_procs.extend([nukor.ToxinProc(0, 40, 1),
                                   nukor.ToxinProc(6, 80, 1)])
        result = nukor.simulate(build, target, max_time=7.1)
        self.assertAlmostEqual(result.dot_to_health,
                               (6 * 20.5 + 40.5) * 1.9)

    def test_jat_slam_proc_seed_inherits_combo_once(self):
        build = replace(self.jat_build(), status_per_slam=1,
                        proc_weights={"TOXIN": 1}, crit_chance=0)
        target = jat.JatTarget(1e9, 0, 0)
        result = jat.simulate(build, target, afflictions=False,
                              combo_multiplier=4, max_time=1.1)
        self.assertEqual(result.toxin_procs, 1)
        self.assertEqual(target.toxin_procs[0].seed, build.modded_base * 4)
        self.assertAlmostEqual(result.dot_to_health,
                               (build.modded_base * 4 + 1) * 0.5)

    def test_jat_room_uses_a_fresh_factory_target_and_its_existing_state(self):
        build = self.jat_build()
        made = []
        def factory():
            target = jat.JatTarget(1000, 0, 0)
            target.toxin_procs.append(jat.ToxinProc(0.25, 40 + 40 * len(made), 1))
            made.append(target)
            return target
        with patch.object(jat, "build_jat_kittag", return_value=build):
            result = jat.simulate_room("ignored", 2, factory=factory,
                                       afflictions=False, max_time=1.3)
        self.assertTrue(math.isinf(result.clear_time))
        self.assertEqual(len(made), 2)
        self.assertAlmostEqual(made[0].health, 1000 - 20.5)
        self.assertAlmostEqual(made[1].health, 1000 - 40.5)

    def test_nukor_room_toxin_ticks_keep_per_target_timing(self):
        build = replace(nukor.build_nukor(), type_damage={}, multishot=1,
                        status_per_beam=0, afcc_pct=0, tick_interval=20,
                        toxin_bonus=0, proc_duration=6)
        made = []
        def factory():
            target = nukor.DummyTarget(1000, 0, 0)
            target.toxin_procs.append(nukor.ToxinProc(
                0.25 if not made else 0.75, 40, 1))
            made.append(target)
            return target
        nukor.simulate_room(build, 2, factory=factory, max_time=1.5)
        self.assertAlmostEqual(made[0].health, 1000 - 20.5 * 1.9)
        self.assertEqual(made[1].health, 1000)

    def test_jat_room_proc_seed_inherits_faction_and_combo(self):
        build = replace(self.jat_build(), status_per_slam=1,
                        proc_weights={"TOXIN": 1}, crit_chance=0,
                        faction_bracket=1.55)
        target = jat.JatTarget(1e9, 0, 0)
        with patch.object(jat, "build_jat_kittag", return_value=build):
            jat.simulate_room("ignored", 1, factory=lambda: target,
                              combo_multiplier=4, afflictions=False, max_time=1.1)
        self.assertEqual(len(target.toxin_procs), 1)
        self.assertAlmostEqual(target.toxin_procs[0].seed,
                               build.modded_base * 1.55 * 4)
        expected_tick = (build.modded_base * 1.55 * 4 + 1) * 0.5 * 1.55
        self.assertAlmostEqual(target.health, 1e9 - expected_tick, places=6)

    def test_alternox_electric_proc_uses_application_relative_tick_times(self):
        build = replace(alternox.build_alternox(), multishot=1,
                        status_per_pellet=0, fire_rate=0.1,
                        mix=alternox.ElementMix({}, ()))
        for cutoff, expected in ((0.24, 0), (0.25, 20.5 * 1.9),
                                 (1.25, 2 * 20.5 * 1.9),
                                 (6.25, 6 * 20.5 * 1.9)):
            with self.subTest(cutoff=cutoff):
                target = alternox.AlternoxTarget(1000, 0, 0)
                target.electric_procs.append(alternox.ElectricProc(0.25, 40, 1))
                alternox.simulate(build, target, max_time=cutoff)
                self.assertAlmostEqual(target.health, 1000 - expected)


if __name__ == "__main__":
    unittest.main()
