"""Layer-routing fixtures based on the wiki, with noted overflow assumptions."""
import unittest

from modules.damage_routing import route_enemy_hit, status_vulnerability


class DamageRoutingTests(unittest.TestCase):
    def test_wiki_stack_multipliers(self):
        self.assertEqual(status_vulnerability(0), 1)
        self.assertEqual(status_vulnerability(1), 2)
        self.assertEqual(status_vulnerability(2), 2.25)
        self.assertEqual(status_vulnerability(10), 4.25)
        self.assertEqual(status_vulnerability(20), 4.25)

    def test_enemy_overguard_does_not_gate_overflow(self):
        result = route_enemy_hit({"HEAT": 100}, overguard=40, armor=0)
        self.assertEqual(result.overguard, 40)
        self.assertEqual(result.health, 60)
        self.assertTrue(result.broke_overguard)

    def test_magnetic_bonus_stays_on_overguard_and_viral_on_health(self):
        # One Magnetic stack gives 2x to OG. 80 OG consumes 40 of the raw hit.
        # The remaining 60 hits health with Viral x2 and 2700 armor (90% DR).
        result = route_enemy_hit({"HEAT": 100}, overguard=80, armor=2700,
                                 magnetic_stacks=1, viral_stacks=1)
        self.assertAlmostEqual(result.overguard, 80)
        self.assertAlmostEqual(result.health, 12)
        self.assertTrue(result.broke_overguard)

    def test_void_bonus_is_overguard_only(self):
        result = route_enemy_hit({"VOID": 100}, overguard=75, armor=0)
        self.assertEqual(result.overguard, 75)
        self.assertEqual(result.health, 50)

    def test_mixed_instance_is_not_dependent_on_type_order(self):
        # This proportional split is an explicit model assumption, not a
        # wiki-verified example of the engine's boundary calculation. The
        # faction type modifier reaches health only: Overguard is neutral to
        # every type but Void, so the IMPACT half absorbs 50 of Overguard and
        # then deals 25 x 1.5 to health alongside HEAT's 25.
        kwargs = dict(overguard=50, armor=0,
                      faction_type_modifiers={"IMPACT": 1.5})
        a = route_enemy_hit({"IMPACT": 50, "HEAT": 50}, **kwargs)
        b = route_enemy_hit({"HEAT": 50, "IMPACT": 50}, **kwargs)
        self.assertEqual(a, b)
        self.assertEqual(a.overguard, 50)
        self.assertEqual(a.health, 62.5)

    def test_faction_type_modifiers_do_not_touch_overguard(self):
        # Overguard: "neutral to all damage types except for a 50% vulnerability
        # from Void". A 1.5x Grineer IMPACT modifier therefore only multiplies
        # the share that spills over into health.
        result = route_enemy_hit({"IMPACT": 50}, overguard=25, armor=0,
                                 faction_type_modifiers={"IMPACT": 1.5})
        self.assertAlmostEqual(result.overguard, 25)
        self.assertAlmostEqual(result.health, 37.5)
        self.assertTrue(result.broke_overguard)

    def test_exact_break_does_not_create_health_damage(self):
        result = route_enemy_hit({"IMPACT": 100}, overguard=100, armor=2700,
                                 faction_type_modifiers={"IMPACT": 1.5})
        self.assertTrue(result.broke_overguard)
        self.assertEqual(result.overguard, 100)
        self.assertEqual(result.health, 0)

    def test_no_damage_never_breaks_overguard(self):
        result = route_enemy_hit({"HEAT": 0}, overguard=10, armor=0)
        self.assertEqual((result.overguard, result.health), (0, 0))
        self.assertFalse(result.broke_overguard)

    def test_armor_minimum_is_per_positive_type(self):
        result = route_enemy_hit({"IMPACT": 0.1, "HEAT": 0.1, "COLD": 0},
                                 overguard=0, armor=2700)
        self.assertEqual(result.health, 2)

    def test_armor_bypass_does_not_get_minimum(self):
        result = route_enemy_hit({"TRUE": 0.1}, overguard=0, armor=2700)
        self.assertEqual(result.health, 0.1)

    def test_extreme_armor_does_not_round_positive_damage_to_zero(self):
        result = route_enemy_hit({"IMPACT": 1e20}, overguard=0, armor=1e20)
        self.assertAlmostEqual(result.health, 300)
        bypass = route_enemy_hit({"TRUE": 0.1}, overguard=0, armor=1e20)
        self.assertEqual(bypass.health, 0.1)

    def test_single_pass_matches_the_reference_two_pass_route(self):
        """The single-pass route must reproduce Damage/Calculation exactly.

        ``route_enemy_hit`` computes the faction-modified health components and
        the Overguard total in one pass over the damage dictionary. The route
        runs once per simulated damage instance, so that allocation was worth
        removing; this fixture keeps a literal two-pass translation of the wiki
        expressions (`typed` first, then the Overguard sum) and asserts the
        results are bit-identical, including the per-type armour floor.
        """
        cases = [
            ({"IMPACT": 50, "HEAT": 50}, dict(overguard=50, armor=0,
                                              faction_type_modifiers={"IMPACT": 1.5})),
            ({"VOID": 100}, dict(overguard=75, armor=0)),
            ({"SLASH": 156.78125, "TOXIN": 12.5, "VOID": 3.25},
             dict(overguard=1_000.0, armor=2_700.0, magnetic_stacks=4,
                  viral_stacks=7, faction_type_modifiers={"SLASH": 1.5, "TOXIN": 0.5})),
            ({"HEAT": 0.1, "IMPACT": 1e-4, "TRUE": 0.5},
             dict(overguard=0.0, armor=5_400.0, armor_bypass=False)),
            ({"GAS": 1.0, "ELEC": 1.0}, dict(overguard=0.0, armor=0.0,
                                             viral_stacks=10)),
        ]
        for damage, kwargs in cases:
            with self.subTest(damage=damage, kwargs=kwargs):
                self.assertEqual(route_enemy_hit(damage, **kwargs),
                                 _reference_route(damage, **kwargs))


def _reference_route(damage_by_type, *, overguard, armor,
                     magnetic_stacks=0, viral_stacks=0,
                     faction_type_modifiers=None, armor_bypass=False):
    """Two-pass spelling of the wiki route, kept only as a test oracle."""
    from modules.enemy_scaling import enemy_armor_damage_reduction

    modifiers = faction_type_modifiers or {}
    typed = {
        kind: max(0.0, amount) * max(0.0, modifiers.get(kind, 1.0))
        for kind, amount in damage_by_type.items()
        if amount > 0
    }
    potential_og = status_vulnerability(magnetic_stacks) * sum(
        max(0.0, amount) * (1.5 if kind == "VOID" else 1.0)
        for kind, amount in damage_by_type.items()
        if amount > 0
    )
    remaining_og = max(0.0, overguard)
    if remaining_og and potential_og:
        absorbed = min(remaining_og, potential_og)
        fraction_for_health = 1.0 - absorbed / potential_og
        broke = potential_og >= remaining_og
    else:
        absorbed = 0.0
        fraction_for_health = 1.0 if not remaining_og else 0.0
        broke = False
    health_mult = status_vulnerability(viral_stacks)
    armor_mult = 1.0 - enemy_armor_damage_reduction(armor)
    health_damage = 0.0
    for kind, amount in typed.items():
        remaining = amount * fraction_for_health
        if remaining <= 0:
            continue
        bypass = armor_bypass or kind in {"TRUE", "CINEMATIC"}
        dealt = remaining * health_mult
        if armor > 0 and not bypass:
            dealt = max(1.0, dealt * armor_mult)
        health_damage += dealt
    from modules.damage_routing import RoutedDamage
    return RoutedDamage(absorbed, health_damage, broke)


class MagneticBreakTests(unittest.TestCase):
    def test_special_tick_formula_and_cap(self):
        from modules.status_damage import magnetic_break_electric_tick
        # 3% per stack over six one-second ticks, with no modifiers.
        self.assertEqual(magnetic_break_electric_tick(1000, 3), 15)
        self.assertEqual(magnetic_break_electric_tick(1000, 100), 50)
        self.assertEqual(magnetic_break_electric_tick(1000, 0), 0)
        self.assertAlmostEqual(
            magnetic_break_electric_tick(1000, 3,
                status_damage_bonus=0.9, faction_bonus=0.3,
                electricity_bonus=0.9),
            15 * 1.9 ** 2 * 1.3 ** 2 * 1.9)

    def test_overguard_break_schedules_six_ticks_not_instant_total(self):
        from modules.kuva_nukor_sim import DummyTarget
        target = DummyTarget(1000, 0, 1000)
        target.add_magnetic(0, 6)
        target.add_magnetic(0, 6)
        target.add_magnetic(0, 6)
        outcome = target.absorb({"HEAT": 500}, 0, 0.5)
        # Three stacks -> 2.5x to OG. 500 consumes 400 base damage; 100 goes
        # to health. The 90-point break proc is pending, not instantly dealt.
        self.assertTrue(outcome.broke_overguard)
        self.assertAlmostEqual(outcome.health, 100)
        self.assertAlmostEqual(target.health, 900)
        self.assertEqual(target.unique_status_count(0), 2)  # MAG + ELEC
        first = target.process_magnetic_electric_until(0, 0.5)
        self.assertEqual(first[0][0], 0)
        self.assertEqual(first[0][1].health, 15)
        self.assertEqual(target.health, 885)
        rest = target.process_magnetic_electric_until(6, 0.5)
        self.assertEqual([t for t, _ in rest], [1, 2, 3, 4, 5])
        self.assertEqual(target.health, 810)
        self.assertEqual(target.process_magnetic_electric_until(10, 0.5), [])

    def test_duration_source_and_live_armor_viral_are_used(self):
        from modules.kuva_nukor_sim import DummyTarget, MagneticSource
        target = DummyTarget(1000, 2700, 1000)
        target.viral_expiries.append(10)
        source = MagneticSource(status_damage_bonus=0.9, duration_multiplier=2)
        target.add_magnetic(0.25, 12, source)
        target.absorb({"HEAT": 500}, 0.25, 0.5)
        self.assertEqual(target.next_magnetic_electric_tick(), 0.25)
        events = target.process_magnetic_electric_until(12.25, 0.5)
        self.assertEqual([t for t, _ in events], [0.25 + i for i in range(12)])
        # With no other armor changes, t<10 benefits from Viral x2. Later
        # ticks no longer do. 2700 armor contributes 0.1x throughout.
        normal = 1000 * 0.03 / 6 * 1.9 ** 2 * 0.1
        self.assertAlmostEqual(events[0][1].health, normal * 2)
        self.assertAlmostEqual(events[-1][1].health, normal)

    def test_magnetic_reapplication_refreshes_only_each_own_stack(self):
        from modules.kuva_nukor_sim import DummyTarget
        target = DummyTarget(1000, 0, 100)
        target.add_magnetic(0, 6)
        target.add_magnetic(5, 6)
        self.assertEqual(target.mag_stacks(5), 2)
        self.assertEqual(target.mag_stacks(6), 1)
        self.assertEqual(target.mag_stacks(11), 0)
