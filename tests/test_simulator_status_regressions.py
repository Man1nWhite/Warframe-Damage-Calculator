"""Focused simulation invariants from wiki status/CO mechanics.

These do not validate the simulators' complete damage or TTK predictions;
see docs/formula_audit.md for their known limitations.
"""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

import modules.kuva_nukor_sim as nukor
import modules.ocucor_sim as ocucor
import modules.akarius_sim as akarius
import modules.jat_kittag_sim as jat
from modules.akarius_sim import AkariusTarget, build_akarius, simulate as simulate_akarius


class LiveGunCOTests(TestCase):
    def test_target_absorb_viral_override_and_live_default(self):
        # Other simulators still use the currently live stacks by default.
        target = nukor.DummyTarget(10_000.0, 0.0, 0.0)
        target.viral_expiries.append(6.0)
        live = target.absorb({"VIRAL": 100.0}, 0.0, 0.5)
        snap_zero = target.absorb({"VIRAL": 100.0}, 0.0, 0.5,
                                  viral_stacks_override=0)
        snap_three = target.absorb({"VIRAL": 100.0}, 0.0, 0.5,
                                   viral_stacks_override=3)
        expired = target.absorb({"VIRAL": 100.0}, 7.0, 0.5)
        self.assertAlmostEqual(live.health, 200.0)
        self.assertAlmostEqual(snap_zero.health, 100.0)
        self.assertAlmostEqual(snap_three.health, 250.0)
        self.assertAlmostEqual(expired.health, 100.0)

    def test_pistol_elementalist_reload_speed_not_duration(self):
        # Pistol Elementalist: +60% reload speed and +90% status damage.
        for sim in (nukor, ocucor, akarius):
            self.assertAlmostEqual(sim.RELOAD_TIME, sim.BASE_RELOAD_TIME / 1.6)
            self.assertEqual(sim.PISTOL_ELEMENTALIST_SD, 0.90)
        self.assertEqual(akarius.build_akarius().status_duration_mult, 1.0)
        self.assertEqual(ocucor.build_ocucor().status_duration_mult, 1.0)
        self.assertEqual(nukor.build_nukor().status_duration_mult, 2.125)

    def test_jat_toxin_stacks_tick_independently_for_six_ticks(self):
        build = replace(jat.build_jat_kittag("Killing Blow"),
                        type_damage={}, status_per_slam=0.0, slam_interval=1.0,
                        faction_bracket=1.0, toxin_elemental_bonus=0.0,
                        status_damage_bonus=0.0)
        target = jat.JatTarget(1e9, 0, 0)
        target.toxin_procs.extend([jat.ToxinProc(0, 40, 1), jat.ToxinProc(0, 40, 1)])
        result = jat.simulate(build, target, afflictions=False, max_time=6.1)
        # Each independent stack gets its own +1 accumulator, ticks 1..6.
        self.assertAlmostEqual(result.dot_to_health, 6 * 2 * (40 + 1) * 0.5)

    def test_nukor_first_hit_has_no_microwave_and_later_hit_has_one(self):
        build = replace(nukor.build_nukor(), multishot=1.0, status_per_beam=0.0)
        target = nukor.DummyTarget(1e9, 0, 0)
        with patch.object(nukor, "galv_shot_scale", wraps=nukor.galv_shot_scale) as calc:
            nukor.simulate(build, target, seed=1, max_time=build.tick_interval * 1.5)
        self.assertEqual([call.args[1] for call in calc.call_args_list], [0, 1])
        self.assertEqual(target.unique_status_count(10000), 1)  # Microwave persists

    def test_nukor_room_counts_statuses_per_target(self):
        build = replace(nukor.build_nukor(), multishot=1.0, status_per_beam=0.0)
        made = []

        def factory():
            target = nukor.DummyTarget(1e9, 0, 0)
            if len(made) == 0:
                target.record_status("HEAT", 0, 100)
                target.record_status("VIRAL", 0, 100)
            elif len(made) == 2:
                target.record_status("RAD", 0, 100)
            made.append(target)
            return target

        with patch.object(nukor, "galv_shot_scale", wraps=nukor.galv_shot_scale) as calc:
            nukor.simulate_room(build, 3, factory=factory, seed=1,
                                max_time=build.tick_interval / 2)
        self.assertEqual([call.args[1] for call in calc.call_args_list], [2, 0, 1])
        self.assertEqual([t.unique_status_count(0) for t in made], [3, 1, 2])

    def test_blast_cap_detonation_clears_live_gunco_type(self):
        build = replace(nukor.build_nukor(), multishot=1.0,
                        status_per_beam=10.0, proc_weights={"BLAST": 1.0})
        target = nukor.DummyTarget(1e9, 0, 0)
        result = nukor.simulate(build, target, seed=1,
                                max_time=build.tick_interval / 2)
        self.assertEqual(result.blast_procs, 10)
        self.assertEqual(target.blast_stacks, [])
        self.assertEqual(target.unique_status_count(0), 1)  # Microwave only

    def test_ocucor_first_hit_does_not_benefit_from_its_own_heat(self):
        build = replace(ocucor.build_ocucor(), multishot=1.0,
                        status_per_beam=1.0, proc_weights={"HEAT": 1.0})
        target = nukor.DummyTarget(1e9, 0, 0)
        with patch.object(ocucor, "_scaled_type_damage",
                          wraps=ocucor._scaled_type_damage) as calc:
            ocucor.simulate(build, target, seed=1,
                            max_time=build.tick_interval * 1.5)
        self.assertEqual([call.args[2] for call in calc.call_args_list], [0, 1])

    def test_akarius_first_impact_precedes_its_procs(self):
        build = replace(build_akarius(), multishot=1.0,
                        status_per_instance=1.0,
                        proc_weights_impact={"IMPACT": 1.0},
                        proc_weights_blast={"HEAT": 1.0})
        target = AkariusTarget(1e9, 0, 0)
        seen = []
        original = target.unique_status_count

        def count(now):
            value = original(now)
            seen.append(value)
            return value

        with patch.object(target, "unique_status_count", side_effect=count):
            result = simulate_akarius(build, target, seed=1,
                                      max_time=build.intra_burst_delay * 1.5)
        self.assertEqual(result.shots, 2)
        self.assertEqual(seen, [0, 2])  # Impact and Heat from first rocket
        self.assertEqual(target.unique_status_count(0.1), 2)

    def test_akarius_corrosive_gets_grineer_health_modifier(self):
        # No statuses, crits, armor, or Overguard: the only difference is
        # Grineer's 1.5x Corrosive type modifier (Viral is neutral).
        from modules.akarius_sim import RIVEN_CORROSIVE, RIVEN_VIRAL
        common = dict(multishot=1.0, status_per_instance=0.0,
                      afcc_pct=0.0, crit_multiplier=1.0)
        corr = replace(build_akarius(RIVEN_CORROSIVE), **common)
        viral = replace(build_akarius(RIVEN_VIRAL), **common)
        corr_result = simulate_akarius(corr, AkariusTarget(1e9, 0, 0),
                                       seed=1, max_time=0.01)
        viral_result = simulate_akarius(viral, AkariusTarget(1e9, 0, 0),
                                        seed=1, max_time=0.01)
        self.assertGreater(corr_result.direct_to_health,
                           viral_result.direct_to_health)

    def test_flare_refreshes_the_shared_expiration_timer(self):
        build = replace(ocucor.build_ocucor(arcane=ocucor.ARCANE_FLARE),
                        multishot=1.0, status_per_beam=1.0, tick_interval=1.0)
        target = nukor.DummyTarget(1e12, 0, 0)
        procs = [["HEAT"] if tick in (0, 9) else ["VIRAL"]
                 for tick in range(20)]
        with patch("modules.ocucor_sim.random.Random.choices", side_effect=procs), \
             patch.object(ocucor, "_scaled_type_damage",
                          wraps=ocucor._scaled_type_damage) as calc:
            ocucor.simulate(build, target, seed=1, max_time=20.0)
        stacks = [call.args[1] for call in calc.call_args_list]
        self.assertEqual(stacks[9], 1)
        self.assertEqual(stacks[10], 2)  # first stack was refreshed at t=9
        self.assertEqual(stacks[18], 2)
        self.assertEqual(stacks[19], 0)  # both share the t=19 expiry

    def test_akarius_does_not_fire_past_max_time(self):
        build = build_akarius()
        result = simulate_akarius(build, AkariusTarget(1e9, 0, 0), seed=1,
                                  max_time=build.intra_burst_delay / 2)
        self.assertEqual(result.shots, 1)
