"""Critical-hit formulas transcribed from the WARFRAME Wiki.

Sources, retrieved **2026-10-28**:

* https://wiki.warframe.com/w/Critical_Hit -- critical chance (relative and
  absolute bonuses), critical damage, the 12-bit base-multiplier
  quantization, and the critical tiers used by the normal/critical shot
  formulas.
* https://wiki.warframe.com/w/Damage/Calculation#Average_Shot/Hit -- the
  arsenal average-shot, normal-shot and critical-shot expressions, including
  the AoE and weak-point variants.
* https://wiki.warframe.com/w/Damage/Cold_Damage -- the Freeze table that
  adds a flat Critical Damage multiplier per Cold stack.

Implemented here:

    Total Crit Chance   = Base Crit Chance x (1 + Relative Bonus) + Absolute Bonus
    Crit Damage         = Base Crit Damage x (1 + Relative Bonus) + Absolute Bonus
    Code(x)             = floor(clamp(x, 0, 32) x 4095/32 + 0.5)
    Quantized Base CDM  = Code(x) x 32/4095
    Damage multiplier   = 1 + Crit Tier x (Crit Damage - 1)
    Normal Shot         = Total Damage x [1 + floor(Crit Chance) x (CDM - 1)]
    Critical Shot       = Total Damage x [1 + ceil(Crit Chance)  x (CDM - 1)]
    Average Shot        = Total Damage x (1 + Crit Chance x (CDM - 1))

The wiki computes the quantization in binary32 with the clamp applied first;
this module uses Python binary64 and therefore matches the documented integer
codes, not necessarily the last bit of the in-game float. ``Damage/Calculation``
notes that exact DoT calculations should use the effective critical multiplier
of the inducing hit, which is why the quantized base value is multiplied by
the modded relative bonus before any tier is applied.
"""
from __future__ import annotations

import math

# 12-bit encoding of the base critical damage multiplier.
CRIT_CODE_MAX = 4095
CRIT_MULTIPLIER_CAP = 32.0
_CRIT_CODE_PER_UNIT = CRIT_CODE_MAX / CRIT_MULTIPLIER_CAP  # 4095 / 32
_CRIT_UNIT_PER_CODE = CRIT_MULTIPLIER_CAP / CRIT_CODE_MAX  # 32 / 4095

# Cold (Freeze) critical-damage bonus by stack count; the 10th stack freezes
# the target and doubles the maximum bonus to +1.0x.
COLD_STACK_CAP = 10
COLD_STACK_CAP_OVERGUARD = 4  # bosses and enemies with active Overguard
COLD_CRIT_DAMAGE_BY_STACK = {
    1: 0.10,
    2: 0.15,
    3: 0.20,
    4: 0.25,
    5: 0.30,
    6: 0.35,
    7: 0.40,
    8: 0.45,
    9: 0.50,
    10: 1.00,  # Frozen
}


def modded_crit_chance(base_crit_chance: float,
                       relative_bonus: float = 0.0,
                       absolute_bonus: float = 0.0) -> float:
    """``Base x (1 + Relative Bonus) + Absolute Bonus``.

    Relative bonuses (Point Strike, Riven Critical Chance, Galvanized Scope)
    are additive with each other and scale the base value; absolute bonuses
    (Arcane Avenger, Puncture's Weakened, Secondary Enervate) are flat
    percentage points added afterwards.
    """
    return base_crit_chance * (1.0 + relative_bonus) + absolute_bonus


def quantize_crit_multiplier(base_crit_multiplier: float) -> float:
    """Encode/decode the game's 12-bit base critical damage multiplier.

    The wiki says the *base* multiplier is quantized before mods but after
    effects that are additive to the base value, with ``x`` clamped to
    ``[0, 32]``:

        Code(x) = floor(clamp(x, 0, 32) * 4095 / 32 + 0.5)
        decoded  = Code(x) * 32 / 4095

    Worked example from the wiki: ``Code(1.6 + 0.4) = 256``, so the decoded
    base multiplier is ``256 * 32 / 4095 = 2.0004884005...``.
    """
    if not math.isfinite(base_crit_multiplier):
        raise ValueError("base_crit_multiplier must be finite")
    clamped = min(max(base_crit_multiplier, 0.0), CRIT_MULTIPLIER_CAP)
    code = math.floor(clamped * _CRIT_CODE_PER_UNIT + 0.5)
    return code * _CRIT_UNIT_PER_CODE


def modded_crit_multiplier(base_crit_multiplier: float,
                           relative_bonus: float = 0.0,
                           absolute_bonus: float = 0.0,
                           *,
                           quantize: bool = True) -> float:
    """Modded Critical Damage multiplier.

    ``quantize`` applies the wiki's base-multiplier quantization first, then
    the relative bonuses, then the absolute bonuses. Vital Sense/Banes and
    Cold's Freeze bonus enter through ``relative_bonus`` and ``absolute_bonus``
    respectively.
    """
    base = (quantize_crit_multiplier(base_crit_multiplier)
            if quantize else base_crit_multiplier)
    return base * (1.0 + relative_bonus) + absolute_bonus


def cold_crit_damage_bonus(stacks: int, *,
                           overguard_or_boss: bool = False) -> float:
    """Flat Critical Damage multiplier granted by Cold (Freeze) stacks.

    +0.10x for the first stack, +0.05x for each subsequent stack, +1.0x while
    Frozen at 10 stacks. Bosses and enemies with active Overguard cap at 4
    stacks (+0.25x). The bonus is additive with Critical Damage mods and does
    not apply to Area of Effect damage.
    """
    if stacks < 0:
        raise ValueError("stacks must be non-negative")
    cap = COLD_STACK_CAP_OVERGUARD if overguard_or_boss else COLD_STACK_CAP
    return COLD_CRIT_DAMAGE_BY_STACK[min(stacks, cap)] if stacks else 0.0


def crit_tiers(crit_chance: float) -> tuple[int, int]:
    """``(floor, ceil)`` critical tiers used by the normal/critical shot forms.

    Above 100% critical chance the floor is the lowest guaranteed tier and the
    ceiling the next possible one (250% -> normal shot uses tier 2, critical
    shot uses tier 3). Negative chances clamp to tier 0.
    """
    if not math.isfinite(crit_chance):
        raise ValueError("crit_chance must be finite")
    chance = max(crit_chance, 0.0)
    return math.floor(chance), math.ceil(chance)


def crit_multiplier_for_tier(crit_multiplier: float, tier: int) -> float:
    """Damage multiplier of a given critical tier: ``1 + tier x (CDM - 1)``.

    Every simulator builds its rolled critical factor from this function, so
    the tier expression has one implementation rather than one per weapon.
    """
    if tier < 0:
        raise ValueError("tier must be non-negative")
    return 1.0 + tier * (crit_multiplier - 1.0)


def headshot_crit_multiplier(crit_multiplier: float, tier: int,
                             headshot_multiplier: float = 3.0) -> float:
    """Headshot critical multiplier from ``Critical_Hit``.

        Headshot Multi x (1 + Tier x (2 x Total Critical Damage - 1))

    The wiki's example is a Lanka with Vital Sense (2.0 x (1 + 120%) = 4.4)
    at critical tier 2: ``3.0 x (1 + 2 x (2 x 4.4 - 1)) = 49.8``.

    This is the *head*-specific form, not the weak-point average of
    ``Damage/Calculation``: the extra ``2 x`` term models the headshot crit
    bonus. Applicability is the caller's decision, because the page scopes it
    to heads (a MOA's 3.0x "fanny pack" and a Corpus humanoid's removed-helmet
    headshot get no crit bonus) and states that a weapon whose *default*
    headshot multiplier is 1.0x never receives the bonus, even if that
    multiplier is later raised -- a fact this expression alone cannot see. No
    bundled simulator models headshots, so nothing in ``modules/`` calls it yet.
    """
    if tier < 0:
        raise ValueError("tier must be non-negative")
    if headshot_multiplier < 0:
        raise ValueError("headshot_multiplier must be non-negative")
    return headshot_multiplier * (1.0 + tier * (2.0 * crit_multiplier - 1.0))


def average_shot(total_damage: float, crit_chance: float,
                 crit_multiplier: float) -> float:
    """Arsenal average shot: ``Total x (1 + Crit Chance x (CDM - 1))``.

    No rounding of the critical chance is performed for this expression.
    """
    return total_damage * (1.0 + max(crit_chance, 0.0) * (crit_multiplier - 1.0))


def normal_shot(total_damage: float, crit_chance: float,
                crit_multiplier: float) -> float:
    """Lowest-tier shot: uses ``floor`` of the modded critical chance."""
    tier, _ = crit_tiers(crit_chance)
    return total_damage * crit_multiplier_for_tier(crit_multiplier, tier)


def critical_shot(total_damage: float, crit_chance: float,
                  crit_multiplier: float) -> float:
    """Next-tier shot: uses ``ceil`` of the modded critical chance."""
    _, tier = crit_tiers(crit_chance)
    return total_damage * crit_multiplier_for_tier(crit_multiplier, tier)


def direct_aoe_shot(average_hit: float, average_aoe_hit: float) -> float:
    """``Average Shot = Direct Hit + AoE Hit`` for a weapon with an AoE part."""
    return average_hit + average_aoe_hit


def weak_point_shot(average_hit: float, weak_point_multiplier: float,
                    weak_point_bonus: float = 0.0) -> float:
    """Weak-point shot formula used by Damage/Calculation.

    ``Average Shot x (Weak Point Multiplier + Weak Point Damage Bonus)``.
    Area-of-effect damage cannot headshot, and weapons without a headshot
    multiplier (e.g. Arca Plasmor) simply keep the base average shot.
    """
    return average_hit * (weak_point_multiplier + weak_point_bonus)
