"""Status Effect (proc) damage formulas from the WARFRAME wiki.

Pure-Python port of the formulas documented on:

* https://wiki.warframe.com/w/Damage/Calculation (section "Damage Over Time")
* https://wiki.warframe.com/w/Damage_over_Time
* https://wiki.warframe.com/w/Status_Effect
* https://wiki.warframe.com/w/Damage/Slash_Damage, /Heat_Damage, /Toxin_Damage,
  /Electricity_Damage and /Gas_Damage

Retrieved 2026-10-27. The five damaging status effects (Slash, Heat, Toxin,
Electricity, Gas) all use the same tick structure:

    Unrounded Tick Damage = (sum(S_i) + 1) * C * M

where ``S_i`` are the full-precision modded-base damage seeds consolidated into
the tick group, ``C`` is the status coefficient (0.35 for Slash, 0.5 for the
elemental DoTs) and ``M`` is the product of the remaining applicable
modifiers. The accumulator starts at 1 (not 0) for weapon-generated procs;
when several seeds share a tick the ``+1`` is included only once, so it is
neither a per-stack bonus nor a flat final +1 damage.

"Modded Base Damage" for proc seeds deliberately ignores physical and
elemental damage bonuses:

    Modded Base = Base * (1 + Base Damage Bonuses) * (1 + Faction Bonuses)

Faction bonuses therefore apply twice to damaging procs (once inside the
seed, once as an explicit multiplier), which the wiki calls double dipping.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

# Status coefficients (fraction of modded base damage per tick).
SLASH_COEFFICIENT = 0.35
ELEMENTAL_DOT_COEFFICIENT = 0.5  # Heat, Toxin, Electricity, Gas

# Standard proc timing (seconds).
PROC_DURATION = 6.0
SINGLE_TARGET_DELAY = 1.0  # Slash / Heat / Toxin
AOE_PROC_DELAY = 0.0  # Electricity / Gas (last tick deals no damage)
DEFAULT_TICK_RATE = 1.0  # status DoTs tick once per second

# Stack caps.
GAS_MAX_STACKS = 10
BLAST_MAX_STACKS = 10


def modded_base_damage(base_damage: float,
                       base_damage_bonus: float = 0.0,
                       faction_bonus: float = 0.0) -> float:
    """Modded base damage used as a proc seed.

    Physical and elemental +damage mods do NOT enter this value; only total
    base-damage bonuses (Serration, Hornet Strike, ...) and faction bonuses.
    """
    return base_damage * (1.0 + base_damage_bonus) * (1.0 + faction_bonus)


def proc_tick_damage(
    seed_damage: float,
    coefficient: float,
    *,
    elemental_bonus: float = 0.0,
    faction_bonus: float = 0.0,
    status_damage_bonus: float = 0.0,
    crit_multiplier: float = 1.0,
    body_part_multiplier: float = 1.0,
    extra_seeds: float = 0.0,
    accumulator: bool = True,
) -> float:
    """Unrounded damage of one DoT tick.

    Implements ``(sum(S_i) + 1) * C * M`` from Damage/Calculation. Use
    ``extra_seeds`` when several procs consolidate into the same tick group;
    the +1 accumulator is then still counted exactly once.

    ``elemental_bonus`` is the matching literal-element bonus only
    (Hellfire for Heat, Leaded Gas/Valence Formation for Gas, ...). Component
    mods do not buff combined-element DoTs: Heat/Toxin mods never buff Gas,
    and Slash has no elemental term at all.

    ``accumulator=False`` reproduces the simplified formula shown on the
    per-damage-type wiki pages (Slash/Heat/Toxin/Electricity/Gas), which omit
    the engine's +1 seed accumulator; the Damage/Calculation page documents
    the exact binary32 accumulator behavior used in game.
    """
    if coefficient <= 0:
        raise ValueError("coefficient must be positive")
    base = seed_damage + extra_seeds + (1.0 if accumulator else 0.0)
    modifiers = (
        (1.0 + elemental_bonus)
        * (1.0 + faction_bonus)
        * (1.0 + status_damage_bonus)
        * crit_multiplier
        * body_part_multiplier
    )
    return base * coefficient * modifiers


def slash_tick(seed_damage: float, **modifiers) -> float:
    """Bleed tick. Cinematic damage: ignores armor, no elemental term."""
    modifiers.pop("elemental_bonus", None)  # no elemental mod buffs Slash
    return proc_tick_damage(seed_damage, SLASH_COEFFICIENT, **modifiers)


def heat_tick(seed_damage: float, **modifiers) -> float:
    """Ignite tick (0.5 coefficient; Heat mods buff it)."""
    return proc_tick_damage(seed_damage, ELEMENTAL_DOT_COEFFICIENT, **modifiers)


def toxin_tick(seed_damage: float, **modifiers) -> float:
    """Poison tick (0.5 coefficient; bypasses shields)."""
    return proc_tick_damage(seed_damage, ELEMENTAL_DOT_COEFFICIENT, **modifiers)


def electricity_tick(seed_damage: float, **modifiers) -> float:
    """Tesla Chain tick (0.5 coefficient; 3 m AoE chain)."""
    return proc_tick_damage(seed_damage, ELEMENTAL_DOT_COEFFICIENT, **modifiers)


def gas_tick(seed_damage: float, **modifiers) -> float:
    """Gas Cloud tick (0.5 coefficient; literal Gas mods only)."""
    return proc_tick_damage(seed_damage, ELEMENTAL_DOT_COEFFICIENT, **modifiers)


def total_ticks(duration: float = PROC_DURATION,
                delay: float = SINGLE_TARGET_DELAY,
                tick_rate: float = DEFAULT_TICK_RATE) -> int:
    """Nominal tick count: ``floor(tick_rate * (duration - delay)) + 1``.

    Slash/Heat/Toxin (1 s delay, 6 s) -> 6 damaging ticks at t = 1..6 s.
    Electricity/Gas (no delay, 6 s) -> 7 nominal ticks, but the final tick at
    t = 6 s deals no damage, so only 6 damaging ticks (t = 0..5 s).
    """
    return math.floor(tick_rate * (duration - delay)) + 1


def damaging_ticks(duration: float = PROC_DURATION,
                   delay: float = SINGLE_TARGET_DELAY,
                   tick_rate: float = DEFAULT_TICK_RATE,
                   last_tick_empty: bool = False) -> int:
    """Number of ticks that actually deal damage."""
    ticks = total_ticks(duration, delay, tick_rate)
    return ticks - 1 if last_tick_empty else ticks


def proc_type_chances(damage_distribution: Mapping[str, float]) -> dict[str, float]:
    """Per-damage-type proc weight = type damage / total damage.

    Since Update 27.2 (2020-03-05) physical types carry no extra 4x weighting;
    the removed 0.25x elemental multiplier makes every damage point count
    equally. Enemy status immunities remove the exempt type and renormalize.
    """
    total = sum(damage_distribution.values())
    if total <= 0:
        raise ValueError("damage distribution must have a positive total")
    return {name: value / total for name, value in damage_distribution.items()}


def average_procs_per_shot(status_chance: float,
                           multishot: float,
                           forced_procs: float = 0.0) -> float:
    """Average status effects per trigger pull.

    ``Average Procs Per Shot = Multishot * (Forced Procs + Status Chance per
    Projectile)``. Arsenal status chance is already the per-pellet probability;
    multishot never changes the per-pellet chance, only the number of rolls.
    """
    return multishot * (forced_procs + status_chance)


def average_procs_per_second(status_chance: float,
                             multishot: float,
                             fire_rate: float,
                             forced_procs: float = 0.0) -> float:
    """Average procs per shot multiplied by effective fire rate."""
    return average_procs_per_shot(status_chance, multishot, forced_procs) * fire_rate


def beam_merged_status_chance(status_chance_per_beam: float,
                              multishot: float) -> float:
    """Status chance of a continuous-weapon tick after multishot merges.

    Beam multishot instances hitting the same target merge into one damage
    instance whose damage AND status chance are the sum of the beams (crit
    chance stays that of a single beam). The merged, larger seed makes
    damaging procs double dip multishot on continuous weapons.
    """
    return status_chance_per_beam * multishot


def wiki_quantized_damage(type_damage: float, modded_base_damage: float) -> float:
    """Wiki 1/32 damage-type quantization used by direct hits.

    ``Quantized(x) = sign(x) * floor(|x| * 32 + 0.5) / 32`` where
    ``x = type_damage / modded_base_damage``. DoT ticks bypass this
    quantization and use full-precision binary32 seeds instead.
    """
    if modded_base_damage <= 0:
        raise ValueError("modded_base_damage must be positive")
    x = type_damage / modded_base_damage
    quantized = math.copysign(math.floor(abs(x) * 32.0 + 0.5) / 32.0, x)
    return quantized * modded_base_damage


@dataclass(frozen=True)
class StatusProc:
    """One damaging status effect specification."""

    damage_type: str
    coefficient: float
    duration: float
    delay: float
    last_tick_empty: bool
    aoe: bool
    max_stacks: int | None
    armor_bypass: bool


# Reference table for the five damaging procs (base, unmodded duration).
STATUS_PROCS = {
    "slash": StatusProc("Slash", SLASH_COEFFICIENT, 6.0, 1.0, False, False,
                        None, True),
    "heat": StatusProc("Heat", ELEMENTAL_DOT_COEFFICIENT, 6.0, 1.0, False,
                       False, None, False),
    "toxin": StatusProc("Toxin", ELEMENTAL_DOT_COEFFICIENT, 6.0, 1.0, False,
                        False, None, False),
    "electricity": StatusProc("Electricity", ELEMENTAL_DOT_COEFFICIENT, 6.0,
                              0.0, True, True, None, False),
    "gas": StatusProc("Gas", ELEMENTAL_DOT_COEFFICIENT, 6.0, 0.0, True, True,
                      GAS_MAX_STACKS, False),
}
