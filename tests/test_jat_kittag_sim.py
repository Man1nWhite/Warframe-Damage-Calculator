"""Tests for the Jat Kittag heavy-slam last-slot/Riven simulation."""
from __future__ import annotations

import math
import unittest

from modules.crit import quantize_crit_multiplier
from modules.jat_kittag_sim import (
    ALL_OPTIONS,
    AFFLICTION_STACKS,
    COMBO_REGEN_PER_SEC,
    CORROSIVE_DURATION,
    DUAL_STAT_ELEMENT,
    FEVER_TOXIN,
    GALV_STEEL_CC,
    GasProc,
    JatTarget,
    LIFTED_AFFLICTION_STACKS,
    MOD_SLOTS,
    PPP,
    RIVEN_SLOTS,
    R3_ATTACK_SPEED,
    R3_CRIT_CHANCE,
    R3_CRIT_DAMAGE,
    R_CRIT_CHANCE,
    R_MELEE_DAMAGE,
    SEISMIC_WAVE,
    SLAM_BASE,
    TTK_TABLE_OPTIONS,
    ToxinProc,
    _combine_elements,
    apply_melee_afflictions,
    build_jat_kittag,
    build_loadout,
    combo_tier,
    has_live_dot,
    has_live_status,
    plain_heavy_gunner_factory,
    run_trials,
    simulate,
    simulate_room,
)
from modules.kuva_nukor_sim import steel_path_dummy_factory

DUMMY = steel_path_dummy_factory()


def factory() -> JatTarget:
    return JatTarget(DUMMY.max_health, DUMMY.max_armor, DUMMY.overguard_max)


class ComboTierTests(unittest.TestCase):
    def test_tier_thresholds(self) -> None:
        self.assertEqual(combo_tier(0), 1)
        self.assertEqual(combo_tier(19.9), 1)
        self.assertEqual(combo_tier(20), 2)
        self.assertEqual(combo_tier(120), 7)
        self.assertEqual(combo_tier(220), 12)
        self.assertEqual(combo_tier(999), 12)


class ElementCombineTests(unittest.TestCase):
    def test_fever_toxin_combinations(self) -> None:
        # Heat + Toxin -> Gas; Electric + Toxin -> Corrosive;
        # Cold + Toxin -> Viral; Toxin alone stays Toxin.
        self.assertEqual(
            _combine_elements(0.9, 0.0, 0.0, FEVER_TOXIN), {"GAS": 2.55})
        self.assertEqual(
            _combine_elements(0.0, 0.0, 0.9, FEVER_TOXIN), {"CORR": 2.55})
        self.assertEqual(
            _combine_elements(0.0, 0.9, 0.0, FEVER_TOXIN), {"VIRAL": 2.55})
        self.assertEqual(
            _combine_elements(0.0, 0.0, 0.0, FEVER_TOXIN),
            {"TOXIN": FEVER_TOXIN})


class BuildStatTests(unittest.TestCase):
    def test_shared_fixed_mod_stats(self) -> None:
        b = build_jat_kittag("Killing Blow")
        # 15% x (1 + 110% Galv Steel, doubled on Heavy Attacks).
        self.assertAlmostEqual(b.crit_chance,
                               0.15 * (1 + 2 * GALV_STEEL_CC))
        self.assertAlmostEqual(b.crit_multiplier, quantize_crit_multiplier(2.0))
        self.assertAlmostEqual(b.seismic_bracket, 1 + SEISMIC_WAVE)
        self.assertEqual(b.status_per_slam, 1.0)
        self.assertAlmostEqual(b.slam_interval, 1.0)
        self.assertAlmostEqual(b.heavy_efficiency, 0.5)
        self.assertAlmostEqual(b.status_damage_bonus, 0.8)
        self.assertAlmostEqual(sum(b.proc_weights.values()), 1.0)

    def test_damage_brackets(self) -> None:
        base = build_jat_kittag("Gas (Molten Impact)")
        self.assertAlmostEqual(base.damage_bracket, 1 + PPP)
        kb = build_jat_kittag("Killing Blow")
        self.assertAlmostEqual(kb.damage_bracket, 1 + PPP + 1.2)
        riv = build_jat_kittag("Riven MD+CD")
        self.assertAlmostEqual(riv.damage_bracket, 1 + PPP + R_MELEE_DAMAGE)
        # Faction is its own bracket.
        smite = build_jat_kittag("Primed Smite Grineer")
        self.assertAlmostEqual(smite.faction_bracket, 1.55)

    def test_slam_type_mix(self) -> None:
        gas = build_jat_kittag("Gas (Molten Impact)")
        self.assertEqual(set(gas.type_damage), {"BLAST", "GAS"})
        corr = build_jat_kittag("Corrosive (Shocking Touch)")
        self.assertEqual(set(corr.type_damage), {"BLAST", "CORR"})
        viral = build_jat_kittag("Viral (North Wind)")
        self.assertEqual(set(viral.type_damage), {"BLAST", "VIRAL"})
        # No combining element: standalone Toxin survives.
        kb = build_jat_kittag("Killing Blow")
        self.assertEqual(set(kb.type_damage), {"BLAST", "TOXIN"})
        # Gas DoT seed ignores elemental mods: same bracket -> same base.
        organ = build_jat_kittag("Organ Shatter")
        self.assertAlmostEqual(gas.modded_base, organ.modded_base)
        self.assertAlmostEqual(gas.modded_base, SLAM_BASE * (1 + PPP))
        # Killing Blow instead grows the shared damage bracket.
        self.assertAlmostEqual(kb.modded_base, SLAM_BASE * (1 + PPP + 1.2))

    def test_riven_crit_chance_doubles_on_heavy(self) -> None:
        b = build_jat_kittag("Riven CC+CD")
        expected = 0.15 * (1 + 2 * GALV_STEEL_CC + 2 * R_CRIT_CHANCE)
        self.assertAlmostEqual(b.crit_chance, expected)
        self.assertGreater(b.crit_chance, 1.0)  # guaranteed yellow tier
        self.assertAlmostEqual(
            b.crit_multiplier, quantize_crit_multiplier(2.0) * (1 + 1.337))

    def test_riven_attack_speed_and_status(self) -> None:
        spd = build_jat_kittag("Riven MD+AtkSpd")
        self.assertAlmostEqual(spd.slam_interval, 1 / 1.815)
        status = build_jat_kittag("Riven MD+Status")
        self.assertAlmostEqual(status.status_per_slam, 1 + 1.337)

    def test_invalid_option_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_jat_kittag("Primed Fury")

    def test_option_coverage(self) -> None:
        self.assertEqual(set(ALL_OPTIONS),
                         set(MOD_SLOTS) | set(RIVEN_SLOTS))


class SimulationTests(unittest.TestCase):
    def test_deterministic_for_same_seed(self) -> None:
        b = build_jat_kittag("Riven MD+CD")
        r1 = simulate(b, factory(), seed=123, combo_multiplier=7.0)
        r2 = simulate(b, factory(), seed=123, combo_multiplier=7.0)
        self.assertEqual(r1.ttk, r2.ttk)
        self.assertEqual(r1.slams, r2.slams)

    def test_overguard_breaks_before_health_takes_damage(self) -> None:
        b = build_jat_kittag("Riven CC+CD")
        target = factory()
        result = simulate(b, target, seed=5, combo_multiplier=7.0)
        self.assertTrue(math.isfinite(result.ttk))
        self.assertTrue(target.broken)
        self.assertLessEqual(result.overguard_break_time, result.ttk)
        self.assertGreater(result.direct_to_overguard, 0.0)
        self.assertGreater(result.direct_to_health, 0.0)

    def test_combo_multiplier_scales_ttk(self) -> None:
        cold = run_trials("Riven MD+CD", trials=40, combo_multiplier=1.0)
        built = run_trials("Riven MD+CD", trials=40, combo_multiplier=7.0)
        self.assertLess(built["ttk_median"], cold["ttk_median"])

    def test_corrosive_strips_armor_and_other_builds_do_not(self) -> None:
        # Afflictions can also add stacks of non-damaging Corrosive.
        tank = JatTarget(50_000_000.0, DUMMY.max_armor, DUMMY.overguard_max)
        corr = simulate(build_jat_kittag("Corrosive (Shocking Touch)", 4),
                        tank, seed=9, combo_multiplier=1.0,
                        max_time=120.0)
        self.assertGreater(corr.corrosive_procs, 0)
        self.assertLess(corr.final_armor, DUMMY.max_armor)
        self.assertGreater(corr.affliction_triggers, 0)
        # The 80% strip cap itself (10 stacks -> factor 0.2) is pinned in
        # test_akarius_sim; natural procs approach but need not hit it.
        gas = simulate(build_jat_kittag("Gas (Molten Impact)"),
                       factory(), seed=9, combo_multiplier=1.0)
        self.assertEqual(gas.final_armor, DUMMY.max_armor)
        self.assertEqual(gas.corrosive_procs, 0)

    def test_gas_and_toxin_proc_routing(self) -> None:
        gas = simulate(build_jat_kittag("Gas (Molten Impact)"),
                       factory(), seed=11, combo_multiplier=7.0)
        self.assertGreater(gas.gas_procs, 0)
        self.assertEqual(gas.toxin_procs, 0)
        toxin = simulate(build_jat_kittag("Killing Blow"),
                         factory(), seed=11, combo_multiplier=7.0)
        self.assertGreater(toxin.toxin_procs, 0)
        self.assertEqual(toxin.gas_procs, 0)
        # Toxin bypasses shields, not armor, and still contributes.
        self.assertGreater(toxin.dot_to_health + toxin.dot_to_overguard, 0.0)

    def test_melee_afflictions_gated_and_helpful(self) -> None:
        opt = "Riven MD+Status"
        b = build_jat_kittag(opt)
        enabled = simulate(b, factory(), seed=21, combo_multiplier=7.0,
                           afflictions=True)
        disabled = simulate(b, factory(), seed=21, combo_multiplier=7.0,
                            afflictions=False)
        self.assertGreater(enabled.affliction_triggers, 0)
        self.assertEqual(disabled.affliction_triggers, 0)
        self.assertLessEqual(enabled.ttk, disabled.ttk)
        # Each trigger adds exactly six stacks of an existing status.
        self.assertEqual(AFFLICTION_STACKS, 6)

    def test_afflictions_never_add_missing_status_types(self) -> None:
        # Regression: a Toxin-only build must never gain Corrosive stacks.
        r = simulate(build_jat_kittag("Killing Blow"), factory(),
                     seed=3, combo_multiplier=1.0)
        self.assertEqual(r.corrosive_procs, 0)
        self.assertEqual(r.final_armor, DUMMY.max_armor)

    def test_each_option_produces_finite_trials(self) -> None:
        for opt in ALL_OPTIONS:
            report = run_trials(opt, trials=20, combo_multiplier=5.0,
                                galv_stacks=4)
            self.assertTrue(math.isfinite(report["ttk_median"]), opt)

    def test_toxin_dots_are_armor_mitigated(self) -> None:
        # Regression: Toxin bypasses shields only, never armor.
        b = build_jat_kittag("Killing Blow")
        armored = simulate(b, factory(), seed=4, combo_multiplier=7.0)
        soft = JatTarget(DUMMY.max_health, 0.0, DUMMY.overguard_max)
        unarmored = simulate(b, soft, seed=4, combo_multiplier=7.0)
        self.assertGreater(armored.ttk, unarmored.ttk)
        # No strip source in this build: armor is untouched.
        self.assertEqual(armored.final_armor, DUMMY.max_armor)

    def test_focus_energy_caps_efficiency_and_keeps_corrosive(self) -> None:
        b = build_jat_kittag("Corrosive (Focus Energy)")
        self.assertEqual(b.heavy_efficiency, 0.9)      # 50% Reflex + 40%
        self.assertEqual(set(b.type_damage), {"BLAST", "CORR"})
        shock = build_jat_kittag("Corrosive (Shocking Touch)")
        self.assertEqual(shock.heavy_efficiency, 0.5)
        # Weaker Electricity mod -> smaller Corrosive portion.
        self.assertLess(b.type_damage["CORR"], shock.type_damage["CORR"])

    def test_full_galvanized_stacks_stats(self) -> None:
        zero = build_jat_kittag("Killing Blow", 0)
        full = build_jat_kittag("Killing Blow", 4)
        self.assertAlmostEqual(full.crit_multiplier,
                               zero.crit_multiplier * 2.2)  # +120% CD
        self.assertAlmostEqual(full.status_per_slam, 2.2)   # +120% status
        self.assertAlmostEqual(full.initial_combo, 4 * 20.35)
        self.assertEqual(combo_tier(full.initial_combo), 5)  # 5x combo floor
        with self.assertRaises(ValueError):
            build_jat_kittag("Killing Blow", 5)

    def test_initial_combo_riven_lifts_floor_from_5x_to_6x(self) -> None:
        base = build_jat_kittag("Killing Blow", 4)
        riven = build_jat_kittag("Riven MD+InitCombo", 4)
        self.assertEqual(combo_tier(base.initial_combo), 5)
        self.assertEqual(combo_tier(riven.initial_combo), 6)

class PlainGunnerAndDualStatTests(unittest.TestCase):
    def test_plain_heavy_gunner_has_no_overguard(self) -> None:
        gunner = plain_heavy_gunner_factory()
        self.assertEqual(gunner.overguard, 0.0)
        self.assertEqual(gunner.max_armor, 2700.0)
        self.assertAlmostEqual(gunner.max_health, 286139.57, places=1)

    def test_60_60_toxin_standalone_element_and_status(self) -> None:
        b = build_jat_kittag("60/60 Toxin (Virulent Scourge)", 4)
        self.assertEqual(set(b.type_damage), {"BLAST", "TOXIN"})
        # Fever 165% + 60% dual-stat feeds both the hit and the DoT.
        self.assertAlmostEqual(b.toxin_elemental_bonus,
                               FEVER_TOXIN + DUAL_STAT_ELEMENT)
        self.assertAlmostEqual(b.status_per_slam, 2.8)   # 1 + 1.2 galv + .6
        self.assertEqual(b.heavy_efficiency, 0.5)

    def test_60_60_heat_combines_into_gas(self) -> None:
        b = build_jat_kittag("60/60 Heat (Volcanic Edge)", 4)
        self.assertEqual(set(b.type_damage), {"BLAST", "GAS"})
        self.assertNotIn("TOXIN", b.type_damage)
        self.assertAlmostEqual(b.status_per_slam, 2.8)

    def test_three_positive_riven_stats(self) -> None:
        b = build_jat_kittag("Riven CC+CD+AS", 4)
        # Heavy crit chance doubles the +202.5% Riven on top of Galv Steel.
        self.assertAlmostEqual(b.crit_chance,
                               0.15 * (1 + 2 * GALV_STEEL_CC
                                       + 2 * R3_CRIT_CHANCE))
        self.assertGreater(b.crit_chance, 1.0)          # guaranteed crits
        self.assertAlmostEqual(b.crit_multiplier,
                               quantize_crit_multiplier(2.0) * (1 + R3_CRIT_DAMAGE + 1.2))
        self.assertAlmostEqual(b.attack_speed, 1 + R3_ATTACK_SPEED)
        self.assertAlmostEqual(b.slam_interval, 1 / (1 + R3_ATTACK_SPEED),
                               places=4)
        self.assertEqual(b.heavy_efficiency, 0.5)

    def test_loadout_merges_riven_and_mod(self) -> None:
        b = build_loadout("Corrosive (Focus Energy)", "Riven CC+CD+AS", 4)
        self.assertGreater(b.crit_chance, 1.0)
        self.assertAlmostEqual(b.slam_interval, 1 / (1 + R3_ATTACK_SPEED),
                               places=4)
        self.assertEqual(set(b.type_damage), {"BLAST", "CORR"})
        self.assertEqual(b.heavy_efficiency, 0.9)      # Focus cap survives
        toxin_only = build_loadout("60/60 Toxin (Virulent Scourge)",
                                   "Riven CC+CD+AS", 4)
        self.assertAlmostEqual(toxin_only.toxin_elemental_bonus,
                               FEVER_TOXIN + DUAL_STAT_ELEMENT)
        self.assertAlmostEqual(toxin_only.status_per_slam, 2.8)

    def test_loadout_rejects_unknown_names(self) -> None:
        with self.assertRaises(ValueError):
            build_loadout("Primed Fury", "Riven CC+CD+AS")
        with self.assertRaises(ValueError):
            build_loadout("Killing Blow", "Riven Meme Roll")
        with self.assertRaises(ValueError):
            build_loadout(None, None)


class ComboRecoveryTests(unittest.TestCase):
    def test_native_cadence_holds_the_5x_floor_at_50_percent_efficiency(self):
        # 81.4 * 0.5 = 40.7 retained; +40/s over a 1.0 s slam = 80.7 >= 80.
        b = build_jat_kittag("Corrosive (Shocking Touch)", 4)
        t = plain_heavy_gunner_factory()
        r = simulate(b, t, seed=2, combo_recovery=True)
        self.assertTrue(all(tier == 5 for tier in r.combo_tiers))

    def test_fast_cadence_collapses_floor_to_tier_3(self) -> None:
        # Riven's 0.618 s interval: 40.7 + 40*0.618 = 65.4 (tier 4), then
        # 32.7 + 24.7 = 57.4 (tier 3), steady state tier 3.
        b = build_loadout("60/60 Toxin (Virulent Scourge)",
                          "Riven CC+CD+AS", 4)
        t = JatTarget(1e12, 2700.0, 0.0)
        r = simulate(b, t, seed=2, combo_recovery=True,
                     afflictions=False, max_time=4.0)
        self.assertEqual(r.combo_tiers[:4], [5, 4, 3, 3])
        self.assertTrue(all(tier == 3 for tier in r.combo_tiers[2:]))

    def test_focus_energy_holds_5x_under_the_riven_cadence(self) -> None:
        b = build_loadout("Corrosive (Focus Energy)", "Riven CC+CD+AS", 4)
        t = plain_heavy_gunner_factory()
        r = simulate(b, t, seed=2, combo_recovery=True)
        self.assertTrue(all(tier == 5 for tier in r.combo_tiers))
        # Arithmetic check for the 90% retention path.
        retained = 81.4 * 0.9
        self.assertGreaterEqual(
            min(81.4, retained + COMBO_REGEN_PER_SEC * b.slam_interval), 80.0)

    def test_recovery_matches_manual_point_accounting(self) -> None:
        # Pure arithmetic: 50% efficiency, 0.618 s interval, 40 points/s.
        points = 81.4
        tiers = []
        for _ in range(6):
            tiers.append(combo_tier(points))
            points = min(81.4, points * 0.5
                         + COMBO_REGEN_PER_SEC * (1 / 1.618))
        self.assertEqual(tiers, [5, 4, 3, 3, 3, 3])

    def test_fixed_combo_multiplier_path_unchanged(self) -> None:
        b = build_jat_kittag("Killing Blow", 4)
        t = plain_heavy_gunner_factory()
        r = simulate(b, t, seed=2, combo_multiplier=7.0)
        # Fixed-tier path: every slam is logged at the supplied multiplier.
        self.assertTrue(r.combo_tiers)
        self.assertTrue(all(tier == 7 for tier in r.combo_tiers))

    def test_afflictions_trigger_on_target_without_overguard(self) -> None:
        # First slam Lifts; from the second slam Melee Afflictions can fire.
        b = build_loadout("60/60 Toxin (Virulent Scourge)",
                          "Riven CC+CD+AS", 4)
        t = plain_heavy_gunner_factory()
        r = simulate(b, t, seed=3, combo_recovery=True)
        self.assertGreater(r.affliction_triggers, 0)
        no_affl = simulate(b, plain_heavy_gunner_factory(), seed=3,
                           combo_recovery=True, afflictions=False)
        self.assertEqual(no_affl.affliction_triggers, 0)


class TtkTableTests(unittest.TestCase):
    def test_all_three_options_kill_plain_gunner(self) -> None:
        for opt in TTK_TABLE_OPTIONS:
            r = run_trials(opt, trials=60, galv_stacks=4,
                           combo_recovery=True, riven_option="Riven CC+CD+AS",
                           factory=plain_heavy_gunner_factory)
            self.assertEqual(r["trials"], 60)
            self.assertTrue(math.isfinite(r["ttk_median"]))

class AfflictionsHelperTests(unittest.TestCase):
    def test_expired_gas_cloud_is_not_resurrected(self) -> None:
        # Expired clouds must be pruned rather than re-seeded by Afflictions.
        t = JatTarget(10_000_000.0, 2700.0, 0.0)
        t.gas_procs.append(GasProc(0.618, 1590.0, 1.0))
        stale_at = 0.618 * 11                       # age 6.18 s > 6 s
        self.assertFalse(has_live_status(t, stale_at))
        self.assertFalse(has_live_dot(t, stale_at))
        apply_melee_afflictions(t, stale_at)
        self.assertEqual(t.gas_procs, [])  # expired cloud was not re-seeded
        # Base rank-5 path: a live cloud gets exactly six extra stacks.
        live = JatTarget(10_000_000.0, 2700.0, 0.0)
        live.gas_procs.append(GasProc(stale_at - 1.0, 1590.0, 1.0))
        apply_melee_afflictions(live, stale_at, stacks=AFFLICTION_STACKS)
        self.assertEqual(len(live.gas_procs), 7)
        self.assertEqual(live.affliction_triggers, 1)

    def test_lifted_trigger_adds_twelve_stacks(self) -> None:
        # Wiki bug note (both mirrors, retrieved 2026-10-27): Lifted
        # triggers add 12 stacks instead of the rank-5 value of 6. The
        # helper's default is the Lifted value used by every slam path.
        t = JatTarget(10_000_000.0, 2700.0, 0.0)
        t.toxin_procs.append(ToxinProc(0.0, 1590.0, 1.0))
        apply_melee_afflictions(t, 1.0)
        self.assertEqual(len(t.toxin_procs), 1 + LIFTED_AFFLICTION_STACKS)
        self.assertEqual(LIFTED_AFFLICTION_STACKS, 2 * AFFLICTION_STACKS)

    def test_afflictions_never_fabricate_status_types_via_helper(self) -> None:
        t = JatTarget(10_000_000.0, 2700.0, 0.0)
        t.toxin_procs.append(ToxinProc(0.0, 1590.0, 1.0))
        apply_melee_afflictions(t, 1.0, stacks=AFFLICTION_STACKS)
        self.assertEqual(len(t.toxin_procs), 1 + AFFLICTION_STACKS)
        self.assertEqual(t.gas_procs, [])
        self.assertEqual(t.corrosive_expiries, [])
        self.assertEqual(t.viral_expiries, [])

    def test_non_damaging_statuses_are_live_and_eligible(self) -> None:
        # Corrosive/Viral stacks alone remain eligible for Afflictions.
        only_corr = JatTarget(10_000_000.0, 2700.0, 0.0)
        only_corr.corrosive_expiries.append(5.0)
        only_viral = JatTarget(10_000_000.0, 2700.0, 0.0)
        only_viral.viral_expiries.append(5.0)
        self.assertFalse(has_live_dot(only_corr, 1.0))
        self.assertFalse(has_live_dot(only_viral, 1.0))
        self.assertTrue(has_live_status(only_corr, 1.0))
        with_dot = JatTarget(10_000_000.0, 2700.0, 0.0)
        with_dot.toxin_procs.append(ToxinProc(0.0, 1590.0, 1.0))
        self.assertTrue(has_live_dot(with_dot, 1.0))

    def test_corrosive_only_build_can_trigger_afflictions(self) -> None:
        # Ample health ensures multiple slams against an unguarded target.
        for opt in ("Corrosive (Shocking Touch)",
                    "Corrosive (Focus Energy)", "Viral (North Wind)"):
            target = JatTarget(1e9, 2700, 0)
            r = simulate(build_jat_kittag(opt, 4), target, seed=5,
                         combo_multiplier=1.0, max_time=30)
            self.assertGreater(r.affliction_triggers, 0, opt)

    def test_lifted_slam_path_triggers_on_plain_gunner(self) -> None:
        # End-to-end: no Overguard means slam 1 Lifts and slam 2 can
        # trigger (the injected stack count itself is pinned above).
        b = build_loadout("60/60 Toxin (Virulent Scourge)",
                          "Riven CC+CD+AS", 4)
        r = simulate(b, plain_heavy_gunner_factory(), seed=2,
                     combo_recovery=True)
        self.assertGreaterEqual(r.affliction_triggers, 1)


class RoomSimTests(unittest.TestCase):
    def test_room_clear_accounts_for_every_kill(self) -> None:
        for n in (3, 5, 10):
            r = simulate_room("Riven CC+CD", n, seed=4,
                              combo_multiplier=7.0)
            self.assertTrue(math.isfinite(r.clear_time))
            self.assertEqual(len(r.kill_times), n)
            self.assertEqual(r.vulcan_explosions, n)

    def test_room_models_afflictions_and_disable_flag(self) -> None:
        enabled = simulate_room("Riven CC+CD", 10, seed=8,
                                combo_multiplier=5.0, galv_stacks=4)
        disabled = simulate_room("Riven CC+CD", 10, seed=8,
                                 combo_multiplier=5.0, galv_stacks=4,
                                 afflictions=False)
        self.assertGreater(enabled.affliction_triggers, 0)
        self.assertEqual(disabled.affliction_triggers, 0)

    def test_room_no_triggers_while_overguard_is_up(self) -> None:
        # Eximus factory: every target starts with Overguard. Triggers can
        # only exist once slams have broken through (and lifted) targets.
        build = build_jat_kittag("60/60 Toxin (Virulent Scourge)", 4)
        r = simulate_room("60/60 Toxin (Virulent Scourge)", 5, seed=3,
                          combo_multiplier=5.0, galv_stacks=4)
        self.assertTrue(math.isfinite(r.clear_time))
        rounds = round(r.clear_time / build.slam_interval)
        pairs = r.n_enemies * rounds
        # First slam round can never trigger anyone (Lifted is set at its
        # end), and the Overguard phase per target is excluded on top.
        self.assertGreater(r.affliction_triggers, 0)
        self.assertLess(r.affliction_triggers,
                        r.n_enemies * (rounds - 1))
        self.assertLess(r.affliction_triggers, pairs)

    def test_room_plain_targets_trigger_from_second_slam(self) -> None:
        r = simulate_room("60/60 Toxin (Virulent Scourge)", 5, seed=3,
                          combo_multiplier=5.0, galv_stacks=4,
                          factory=plain_heavy_gunner_factory)
        self.assertGreater(r.affliction_triggers, 0)

    def test_corrosive_duration_constant(self) -> None:
        self.assertEqual(CORROSIVE_DURATION, 8.0)


if __name__ == "__main__":
    unittest.main()
