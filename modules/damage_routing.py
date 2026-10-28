"""Approximate damage routing for shieldless enemy simulation targets.

The WARFRAME Wiki describes Overguard as a layer before health, with no enemy
Overguard depletion gate. Magnetic stacks amplify only Overguard; Viral
stacks amplify only health. Void has an additional 1.5x Overguard modifier.
See https://wiki.warframe.com/w/Overguard and
https://wiki.warframe.com/w/Damage/Calculation.

The wiki does not specify the exact distribution of a mixed damage instance
that breaks Overguard. This model assumes that the same fraction of each
component remains for health. Faction *type* modifiers (the Grineer table, for
example) are applied to the health layer only: ``Overguard`` states the layer
is neutral to all damage types except Void's +50%, and lists no per-faction
table. The faction *damage* bonus of Bane-style mods is a separate multiplier
that the simulators apply before routing, so it still reaches both layers. It
does not model shields, other enemy defenses, or exact engine float/rounding
order.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .enemy_scaling import enemy_armor_damage_reduction

# Overguard is neutral to every damage type except Void (Overguard page).
VOID_OVERGUARD_MULTIPLIER = 1.5


def status_vulnerability(stacks: int) -> float:
    """Magnetic-to-Overguard or Viral-to-health multiplier, capped at 10."""
    return 1.0 if stacks <= 0 else 2.0 + 0.25 * (min(stacks, 10) - 1)


@dataclass(frozen=True)
class RoutedDamage:
    """Actual damage to each layer, before clamping the health at zero."""

    overguard: float
    health: float
    broke_overguard: bool


def route_enemy_hit(
    damage_by_type: Mapping[str, float],
    *,
    overguard: float,
    armor: float,
    magnetic_stacks: int = 0,
    viral_stacks: int = 0,
    faction_type_modifiers: Mapping[str, float] | None = None,
    armor_bypass: bool = False,
) -> RoutedDamage:
    """Route a single mixed hit through Overguard and health.

    Values in ``damage_by_type`` include the attack's own multipliers but not
    target defenses or faction type modifiers. Faction type modifiers apply to
    the health layer only, because ``Overguard`` is neutral to every type but
    Void (which takes +50%). If the hit breaks Overguard, the proportion of the
    *original* hit not consumed by that layer proceeds to health; Magnetic's
    Overguard-only multiplier does not carry over.
    """
    modifiers = faction_type_modifiers or {}
    # One pass builds both the faction-modified health components and the
    # Overguard total. The route is called once per simulated damage instance,
    # so the two dictionaries and the second scan the obvious spelling needs
    # were the hottest allocation site in the tick simulators; the sums below
    # keep the original per-type order, which makes this a pure refactor.
    typed: dict[str, float] = {}
    overguard_total = 0.0
    for kind, amount in damage_by_type.items():
        if amount <= 0:
            continue
        typed[kind] = amount * max(0.0, modifiers.get(kind, 1.0))
        if kind == "VOID":
            overguard_total += amount * VOID_OVERGUARD_MULTIPLIER
        else:
            overguard_total += amount
    potential_og = status_vulnerability(magnetic_stacks) * overguard_total
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
    return RoutedDamage(absorbed, health_damage, broke)
