"""Tests for the Ocucor arcane/Riven simulation."""
from __future__ import annotations

import math
import unittest

from modules.enemy_scaling import steel_path_eximus_heavy_gunner
from modules.kuva_nukor_sim import DummyTarget
from modules.ocucor_sim import (
    ARCANE_ENERVATE,
    ARCANE_FLARE,
    BASE_CRIT_CHANCE,
    BASE_FIRE_RATE,
    BASE_STATUS,
    FLARE_MAX_STACKS,
    GALV_SHOT_CO,
    MAGAZINE,
    RAMP_START,
    RAMP_TIME,
    RIVEN_STATS,
    RIVEN_VIRAL,
    _scaled_type_damage,
    build_ocucor,
    run_trials,
    simulate,
    simulate_room,
)

DUMMY = steel_path_eximus_heavy_gunner(150)


def factory() -> DummyTarget:
    return DummyTarget(DUMMY.health, DUMMY.armor, DUMMY.overguard)


class BuildStatTests(unittest.TestCase):
    def test_default_build_stats(self) -> None:
        b = build_ocucor()  # Enervate + Critical Damage Riven
        self.assertEqual(b.arcane, ARCANE_ENERVATE)
        # 1 + 230% Galvanized Diffusion + 60% Lethal Torrent.
        self.assertAlmostEqual(b.multishot, 3.9)
        # 12 ticks/s x (1 + 60% Lethal Torrent).
        self.assertAlmostEqual(b.fire_rate, BASE_FIRE_RATE * 1.6)
        self.assertAlmostEqual(b.tick_interval, 1.0 / b.fire_rate)
        # 24% x (1 + 80% Galv Shot) per beam, merged across multishot.
        self.assertAlmostEqual(b.status_per_beam, BASE_STATUS * 1.8)
        self.assertAlmostEqual(b.merged_status,
                               BASE_STATUS * 1.8 * 3.9)
        # AFCC for a 16% modded crit chance (Enervate regression branch 1).
        self.assertAlmostEqual(b.crit_chance_pct, 16.0)
        self.assertAlmostEqual(b.afcc_pct, 102.45 + 0.5 * 16.0)
        # 1.8 x (1 + 120% PTC + 133.7% CD Riven).
        self.assertAlmostEqual(b.crit_multiplier, 1.8 * 3.537)
        # Galv Shot CO adds to the ordinary damage bracket for Ocucor.
        self.assertAlmostEqual(b.base_damage_bracket, 1.0 + GALV_SHOT_CO)
        # Pistol Elementalist status-duration multiplier.
        self.assertAlmostEqual(b.status_duration_mult, 1.9)
        self.assertAlmostEqual(b.heat_ramp_interval, 0.5 * 1.9)
        self.assertAlmostEqual(b.proc_duration, 6.0 * 1.9)

    def test_each_riven_stat_changes_only_its_stat(self) -> None:
        cd = build_ocucor(riven_stat="Critical Damage")
        dmg = build_ocucor(riven_stat="Damage")
        fr = build_ocucor(riven_stat="Fire Rate")
        ms = build_ocucor(riven_stat="Multishot")
        sc = build_ocucor(riven_stat="Status Chance")
        cc = build_ocucor(riven_stat="Critical Chance")
        self.assertAlmostEqual(dmg.base_damage_bracket,
                               1.0 + GALV_SHOT_CO + RIVEN_STATS["Damage"])
        self.assertAlmostEqual(fr.fire_rate,
                               BASE_FIRE_RATE * (1 + 0.6 + RIVEN_STATS["Fire Rate"]))
        self.assertAlmostEqual(ms.multishot, 3.9 + RIVEN_STATS["Multishot"])
        self.assertAlmostEqual(sc.status_per_beam,
                               BASE_STATUS * (1 + 0.8 + RIVEN_STATS["Status Chance"]))
        self.assertAlmostEqual(cc.crit_chance_pct,
                               100 * BASE_CRIT_CHANCE * (1 + RIVEN_STATS["Critical Chance"]))
        # The non-selected stats stay identical across variants.
        self.assertAlmostEqual(dmg.multishot, cd.multishot)
        self.assertAlmostEqual(fr.multishot, cd.multishot)
        self.assertAlmostEqual(sc.multishot, cd.multishot)
        self.assertAlmostEqual(cc.multishot, cd.multishot)
        # Non-CD variants keep the un-Rivened crit multiplier (1.8 x 2.2);
        # non-Damage variants keep the 2.2 bracket.
        for other in (dmg, fr, ms, sc, cc):
            self.assertAlmostEqual(other.crit_multiplier, 1.8 * 2.2)
        for other in (fr, ms, sc, cc):
            self.assertAlmostEqual(other.base_damage_bracket,
                                   cd.base_damage_bracket)
        self.assertAlmostEqual(ms.crit_chance_pct, cd.crit_chance_pct)

    def test_flare_uses_modded_crit_not_afcc(self) -> None:
        b = build_ocucor(arcane=ARCANE_FLARE)
        self.assertAlmostEqual(b.afcc_pct, b.crit_chance_pct)
        self.assertAlmostEqual(b.afcc_pct, 16.0)

    def test_invalid_inputs_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_ocucor(arcane="Might of Vetala")
        with self.assertRaises(ValueError):
            build_ocucor(riven_stat="Zoom")

    def test_damage_type_mix_and_weights(self) -> None:
        b = build_ocucor()
        # Innate Radiation/Puncture survive; Heat and Riven Viral are free
        # elements and never combine into anything else.
        self.assertEqual(set(b.type_damage), {"RAD", "PUNC", "HEAT", "VIRAL"})
        self.assertAlmostEqual(sum(b.proc_weights.values()), 1.0)
        self.assertAlmostEqual(b.type_damage["VIRAL"],
                               11.0 * b.base_damage_bracket * RIVEN_VIRAL)
        self.assertAlmostEqual(b.type_damage["HEAT"],
                               11.0 * b.base_damage_bracket * 1.65)
        self.assertAlmostEqual(b.type_damage["RAD"],
                               10.0 * b.base_damage_bracket)
        # Heat is the heaviest proc type.
        self.assertGreater(b.proc_weights["HEAT"], b.proc_weights["VIRAL"])
        self.assertGreater(b.proc_weights["VIRAL"], b.proc_weights["RAD"])


class FlareMechanicTests(unittest.TestCase):
    def test_flare_scales_the_damage_bracket(self) -> None:
        b = build_ocucor(arcane=ARCANE_FLARE)
        base = _scaled_type_damage(b, 0)
        full = _scaled_type_damage(b, FLARE_MAX_STACKS)
        # Bracket 2.2 -> 2.2 + 40 * 0.12 = 7.0.
        self.assertAlmostEqual(full["RAD"] / base["RAD"],
                               (2.2 + FLARE_MAX_STACKS * 0.12) / 2.2)
        self.assertAlmostEqual(full["RAD"], 10.0 * 7.0)

    def test_enervate_build_never_gains_flare_stacks(self) -> None:
        b = build_ocucor(arcane=ARCANE_ENERVATE)
        result = simulate(b, factory(), seed=7)
        self.assertEqual(result.flare_stacks_peak, 0)

    def test_flare_stacks_accumulate_and_are_capped(self) -> None:
        b = build_ocucor(arcane=ARCANE_FLARE)
        result = simulate(b, factory(), seed=7)
        self.assertGreater(result.flare_stacks_peak, 0)
        self.assertLessEqual(result.flare_stacks_peak, FLARE_MAX_STACKS)


class RampTests(unittest.TestCase):
    def test_ramp_envelope(self) -> None:
        def ramp(beam_time: float) -> float:
            return min(1.0, RAMP_START
                       + (1.0 - RAMP_START) * beam_time / RAMP_TIME)
        self.assertAlmostEqual(ramp(0.0), 0.2)
        self.assertAlmostEqual(ramp(RAMP_TIME), 1.0)
        self.assertAlmostEqual(ramp(RAMP_TIME / 2.0), 0.6)
        self.assertLess(ramp(0.1), 1.0)

    def test_capped_time_run_deals_damage_but_does_not_finish(self) -> None:
        b = build_ocucor()
        huge = DummyTarget(10**12, DUMMY.armor, DUMMY.overguard)
        result = simulate(b, huge, seed=3, max_time=0.25)
        self.assertEqual(result.ttk, math.inf)
        self.assertGreater(result.direct_to_overguard, 0.0)
        self.assertGreater(huge.overguard, 0.0)
        # 0.25 s at 19.2 ticks/s -> 4 full ticks plus the partial step.
        self.assertIn(result.ticks, (4, 5))


class SimulationTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self) -> None:
        b = build_ocucor()
        r1 = simulate(b, factory(), seed=99)
        r2 = simulate(b, factory(), seed=99)
        self.assertEqual(r1.ttk, r2.ttk)
        self.assertEqual(r1.ticks, r2.ticks)
        self.assertEqual(r1.heat_procs, r2.heat_procs)

    def test_kill_breaks_overguard_then_strips_armor_and_procs_viral(self) -> None:
        b = build_ocucor()
        target = factory()
        result = simulate(b, target, seed=11)
        self.assertTrue(math.isfinite(result.ttk))
        self.assertTrue(target.broken)
        self.assertLessEqual(result.overguard_break_time, result.ttk)
        self.assertGreater(result.direct_to_overguard, 0.0)
        self.assertGreater(result.direct_to_health, 0.0)
        self.assertGreater(result.heat_procs, 0)
        # Heat strips effectively fully (multiplicative, approaches zero);
        # Viral stacks are still live at the kill.
        self.assertLess(result.final_armor, 1.0)
        self.assertGreater(len(target.viral_expiries), 0)
        self.assertGreater(len(target.viral_expiries), 0)

    def test_damage_riven_beats_crit_chance_riven_with_enervate(self) -> None:
        dmg = run_trials(ARCANE_ENERVATE, "Damage", trials=40)
        cc = run_trials(ARCANE_ENERVATE, "Critical Chance", trials=40)
        self.assertLess(dmg["ttk_median"], cc["ttk_median"])

    def test_enervate_outperforms_flare_on_single_target(self) -> None:
        enervate = [run_trials(ARCANE_ENERVATE, s, trials=30)["ttk_median"]
                    for s in RIVEN_STATS]
        flare = [run_trials(ARCANE_FLARE, s, trials=30)["ttk_median"]
                 for s in RIVEN_STATS]
        self.assertLess(min(enervate), min(flare))

    def test_magazine_supports_at_least_120_ticks_before_reload(self) -> None:
        b = build_ocucor()
        huge = DummyTarget(10**12, DUMMY.armor, DUMMY.overguard)
        result = simulate(b, huge, seed=5,
                          max_time=MAGAZINE / 0.5 * b.tick_interval - 0.01)
        self.assertEqual(result.reloads, 0)
        result2 = simulate(b, DummyTarget(10**12, DUMMY.armor, DUMMY.overguard),
                           seed=5,
                           max_time=MAGAZINE / 0.5 * b.tick_interval + 0.1)
        self.assertGreaterEqual(result2.reloads, 1)


class RoomSimTests(unittest.TestCase):
    def test_single_target_room_spawns_no_tendrils(self) -> None:
        result = simulate_room(ARCANE_ENERVATE, "Damage", 1, seed=4)
        self.assertEqual(result.tendril_peak, 0)
        self.assertEqual(len(result.kill_times), 1)
        self.assertTrue(math.isfinite(result.clear_time))

    def test_room_grows_tendrils_up_to_four_and_clears(self) -> None:
        result = simulate_room(ARCANE_ENERVATE, "Damage", 6, seed=4)
        self.assertTrue(math.isfinite(result.clear_time))
        self.assertEqual(len(result.kill_times), 6)
        self.assertGreaterEqual(result.tendril_peak, 1)
        self.assertLessEqual(result.tendril_peak, 4)

    def test_room_flare_tracking_is_arcane_gated(self) -> None:
        en = simulate_room(ARCANE_ENERVATE, "Damage", 5, seed=8)
        fl = simulate_room(ARCANE_FLARE, "Damage", 5, seed=8)
        self.assertEqual(en.flare_peak, 0)
        self.assertGreater(fl.flare_peak, 0)
        self.assertLessEqual(fl.flare_peak, FLARE_MAX_STACKS)

    def test_tendrils_speed_up_multi_target_clear(self) -> None:
        solo = run_trials(ARCANE_ENERVATE, "Damage", trials=20)
        room = simulate_room(ARCANE_ENERVATE, "Damage", 10, seed=21)
        # Ten separate solo fights vs one shared room with Tendril beams.
        self.assertLess(room.clear_time, 10.0 * solo["ttk_median"])


if __name__ == "__main__":
    unittest.main()
