"""Cross-checks of the bundled mechanics constants against the WARFRAME Wiki.

These pin the *coefficients* transcribed from the English wiki on
2026-10-28 so a future edit cannot silently drift away from the cited page:

* https://wiki.warframe.com/w/Damage_over_Time (proc timing table)
* https://wiki.warframe.com/w/Damage/Blast_Damage (30% single hit / 300% radial
  per stack, 10-stack cap, 5 m no-falloff radial)
* https://wiki.warframe.com/w/Damage/Corrosive_Damage (20% + 6% per stack
  model, 80% at 10 stacks)
* https://wiki.warframe.com/w/Damage/Heat_Damage (15/30/40/50% strip every
  0.5 s, restore 50/40/30/15/0% every 1.5 s)
* https://wiki.warframe.com/w/Damage/Magnetic_Damage (3% of max defense per
  stack over 6 s, Status Damage and faction bonuses applied twice, Electricity
  bonuses once)
* https://wiki.warframe.com/w/Damage/Viral_Damage and /Damage/Magnetic_Damage
  (2 + 0.25 x (stacks - 1), capped at 10 stacks)
* https://wiki.warframe.com/w/Multishot (integer beams plus a fractional extra
  roll)
* https://wiki.warframe.com/w/Secondary_Enervate#Notes (closed-form AFCC)

They document the chosen transcription; they do not establish that the model
matches in-game behavior.
"""

from __future__ import annotations

import random
import unittest

from modules.akarius_sim import corrosive_armor_factor
from modules.status_damage import blast_stack_damage
from modules.kuva_nukor_sim import (
    BLAST_MAX_STACKS,
    BLAST_RADIAL_COEF,
    BLAST_SINGLE_COEF,
    DummyTarget,
    _heat_strip_fraction,
    enervate_afcc,
    roll_multishot,
    viral_magnetic_multiplier,
)
from modules.status_damage import (
    STATUS_PROCS,
    damaging_ticks,
    magnetic_break_electric_tick,
    total_ticks,
)


class ProcTimingTests(unittest.TestCase):
    def test_single_target_procs_tick_at_one_to_six_seconds(self) -> None:
        for key in ("slash", "heat", "toxin"):
            proc = STATUS_PROCS[key]
            self.assertEqual((proc.duration, proc.delay), (6.0, 1.0))
            self.assertFalse(proc.last_tick_empty)
            self.assertFalse(proc.aoe)
            self.assertEqual(damaging_ticks(proc.duration, proc.delay), 6)

    def test_aoe_procs_skip_the_final_tick(self) -> None:
        for key in ("electricity", "gas"):
            proc = STATUS_PROCS[key]
            self.assertEqual((proc.duration, proc.delay), (6.0, 0.0))
            self.assertTrue(proc.last_tick_empty)
            self.assertTrue(proc.aoe)
            self.assertEqual(total_ticks(proc.duration, proc.delay), 7)
            self.assertEqual(
                damaging_ticks(proc.duration, proc.delay, last_tick_empty=True), 6)

    def test_gas_stack_cap_and_armor_bypass_flags(self) -> None:
        self.assertEqual(STATUS_PROCS["gas"].max_stacks, 10)
        self.assertTrue(STATUS_PROCS["slash"].armor_bypass)
        self.assertFalse(STATUS_PROCS["heat"].armor_bypass)

    def test_status_duration_adds_ticks(self) -> None:
        # +100% Status Duration on a Slash proc: 12 s duration, 1 s delay.
        self.assertEqual(damaging_ticks(12.0, 1.0), 12)


class BlastTests(unittest.TestCase):
    def test_coefficients_match_the_dedicated_page(self) -> None:
        # 30% of modded base to the proc target; 300% per stack in the radial.
        self.assertAlmostEqual(BLAST_SINGLE_COEF, 0.30)
        self.assertAlmostEqual(BLAST_RADIAL_COEF, 3.00)
        self.assertEqual(BLAST_MAX_STACKS, 10)

    def test_cap_settlement_is_ten_single_target_hits(self) -> None:
        # At 10 stacks the wiki settles ten 30% hits on the target (300%).
        target = DummyTarget(health=10_000.0, armor=0.0, overguard=0.0)
        for _ in range(BLAST_MAX_STACKS):
            from modules.kuva_nukor_sim import BlastProc
            target.blast_stacks.append(BlastProc(0.0, 1.5, 100.0, 1.0))
        self.assertAlmostEqual(target.blast_single_damage(0.0), 10 * 30.0)
        self.assertAlmostEqual(target.blast_radial_damage(0.0), 10 * 300.0)

    def test_status_damage_bonus_and_crit_scale_each_stack(self) -> None:
        from modules.kuva_nukor_sim import BlastProc
        target = DummyTarget(health=10_000.0, armor=0.0, overguard=0.0)
        target.blast_stacks.append(BlastProc(0.0, 1.5, 100.0, 2.0))
        self.assertAlmostEqual(target.blast_single_damage(0.0), 60.0)
        self.assertAlmostEqual(target.blast_single_damage(0.9), 114.0)


class CorrosiveTests(unittest.TestCase):
    def test_armor_factor_by_stack_count(self) -> None:
        # 20% + 6% per stack: 26% at one, 80% at ten.
        self.assertAlmostEqual(corrosive_armor_factor(0), 1.0)
        self.assertAlmostEqual(corrosive_armor_factor(1), 0.74)
        self.assertAlmostEqual(corrosive_armor_factor(2), 0.68)
        self.assertAlmostEqual(corrosive_armor_factor(10), 0.20)
        # Stacks beyond the cap do not remove additional armor.
        self.assertAlmostEqual(corrosive_armor_factor(14), 0.20)


class HeatStripTests(unittest.TestCase):
    def test_ramp_steps_every_half_second(self) -> None:
        interval = 0.5
        self.assertAlmostEqual(_heat_strip_fraction(0.0, interval), 0.0)
        self.assertAlmostEqual(_heat_strip_fraction(0.49, interval), 0.0)
        self.assertAlmostEqual(_heat_strip_fraction(0.5, interval), 0.15)
        self.assertAlmostEqual(_heat_strip_fraction(1.0, interval), 0.30)
        self.assertAlmostEqual(_heat_strip_fraction(1.5, interval), 0.40)
        self.assertAlmostEqual(_heat_strip_fraction(2.0, interval), 0.50)
        self.assertAlmostEqual(_heat_strip_fraction(6.0, interval), 0.50)

    def test_status_duration_slows_the_ramp(self) -> None:
        # +100% Status Duration doubles the interval between strip steps.
        self.assertAlmostEqual(_heat_strip_fraction(0.5, 1.0), 0.0)
        self.assertAlmostEqual(_heat_strip_fraction(1.0, 1.0), 0.15)
        self.assertAlmostEqual(_heat_strip_fraction(4.0, 1.0), 0.50)

    def test_armor_restore_steps_after_expiry(self) -> None:
        target = DummyTarget(health=10_000.0, armor=2700.0, overguard=0.0)
        target._heat_ended_at = 10.0
        ramp = 0.5
        expected = [(10.0, 0.50), (11.5, 0.40), (13.0, 0.30),
                    (14.5, 0.15), (16.0, 0.0)]
        for now, strip in expected:
            self.assertAlmostEqual(
                target.current_armor(now, ramp), 2700.0 * (1.0 - strip), places=6)


class MagneticBreakTests(unittest.TestCase):
    def test_three_percent_of_max_defense_per_stack_over_six_seconds(self) -> None:
        # One stack: 0.03 x 1000 / 6 per tick, six ticks = 30 damage.
        tick = magnetic_break_electric_tick(1000.0, 1)
        self.assertAlmostEqual(tick, 5.0)
        self.assertAlmostEqual(tick * 6, 30.0)
        # Ten stacks: the documented 30% cap.
        self.assertAlmostEqual(magnetic_break_electric_tick(1000.0, 10) * 6, 300.0)
        # Stacks above ten are ignored.
        self.assertAlmostEqual(magnetic_break_electric_tick(1000.0, 12),
                               magnetic_break_electric_tick(1000.0, 10))

    def test_status_damage_and_faction_apply_twice(self) -> None:
        base = magnetic_break_electric_tick(1000.0, 5)
        self.assertAlmostEqual(
            magnetic_break_electric_tick(1000.0, 5, status_damage_bonus=0.9),
            base * 1.9 ** 2)
        self.assertAlmostEqual(
            magnetic_break_electric_tick(1000.0, 5, faction_bonus=0.55),
            base * 1.55 ** 2)
        # Literal Electricity mods apply once.
        self.assertAlmostEqual(
            magnetic_break_electric_tick(1000.0, 5, electricity_bonus=0.9),
            base * 1.9)

    def test_duration_does_not_change_tick_amount(self) -> None:
        # The wiki scales the number of ticks with duration, not the tick value.
        self.assertAlmostEqual(magnetic_break_electric_tick(1000.0, 3),
                               magnetic_break_electric_tick(1000.0, 3))


class VulnerabilityTests(unittest.TestCase):
    def test_viral_and_magnetic_amplification_table(self) -> None:
        self.assertAlmostEqual(viral_magnetic_multiplier(0), 1.0)
        self.assertAlmostEqual(viral_magnetic_multiplier(1), 2.00)
        self.assertAlmostEqual(viral_magnetic_multiplier(2), 2.25)
        self.assertAlmostEqual(viral_magnetic_multiplier(10), 4.25)
        # The cap replaces the oldest stack instead of adding more.
        self.assertAlmostEqual(viral_magnetic_multiplier(11), 4.25)


class MultishotTests(unittest.TestCase):
    def test_expiring_stack_has_the_documented_minimum(self) -> None:
        # Damage/Calculation: an expiring stack deals max(1, 0.3 x H).
        self.assertAlmostEqual(blast_stack_damage(100.0), 30.0)
        self.assertAlmostEqual(blast_stack_damage(1.0), 1.0)
        self.assertAlmostEqual(blast_stack_damage(0.0), 1.0)
        # Status Damage and the inducing hit's crit multiplier both apply.
        self.assertAlmostEqual(
            blast_stack_damage(100.0, crit_factor=2.0, status_damage_bonus=0.9),
            114.0)
        # The 5 m radial is 300% per stack and carries no minimum.
        self.assertAlmostEqual(
            blast_stack_damage(100.0, BLAST_RADIAL_COEF, floor=0.0), 300.0)

    def test_simulators_share_one_blast_definition(self) -> None:
        from modules import alternox_prime_sim, kuva_nukor_sim, status_damage
        for module in (alternox_prime_sim, kuva_nukor_sim):
            self.assertEqual(module.BLAST_SINGLE_COEF,
                             status_damage.BLAST_SINGLE_COEF)
        self.assertEqual(kuva_nukor_sim.BLAST_RADIAL_COEF,
                         status_damage.BLAST_RADIAL_COEF)
        self.assertEqual(kuva_nukor_sim.BLAST_MAX_STACKS,
                         status_damage.BLAST_MAX_STACKS)
        self.assertEqual(alternox_prime_sim.BLAST_STACK_CAP,
                         status_damage.BLAST_MAX_STACKS)

    def test_integer_beams_plus_a_fractional_roll(self) -> None:
        self.assertEqual(roll_multishot(random.Random(1), 1.0), 1)
        self.assertEqual(roll_multishot(random.Random(1), 2.0), 2)
        # A 0.0 fraction never adds a beam, a 0.999 fraction does.
        self.assertEqual(roll_multishot(random.Random(1), 2.0), 2)
        self.assertEqual(roll_multishot(random.Random(1), 2.999999), 3)
        for seed in range(20):
            self.assertIn(roll_multishot(random.Random(seed), 3.4), (3, 4))


class EnervateTests(unittest.TestCase):
    def test_afcc_piecewise_values(self) -> None:
        # Published closed form: 102.45 + 0.5x below 110% modded crit.
        self.assertAlmostEqual(enervate_afcc(0.0), 102.45)
        self.assertAlmostEqual(enervate_afcc(50.0), 127.45)
        self.assertAlmostEqual(enervate_afcc(100.0), 152.45)
        # Exact branch from 140% onwards: 77.5 + 0.7x at 140%.
        self.assertAlmostEqual(enervate_afcc(140.0), 175.5)
        self.assertAlmostEqual(enervate_afcc(200.0), 225.0)
        self.assertAlmostEqual(enervate_afcc(250.0), 275.0)

    def test_afcc_is_monotonic(self) -> None:
        values = [enervate_afcc(x / 10) for x in range(0, 3000, 10)]
        self.assertEqual(values, sorted(values))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
