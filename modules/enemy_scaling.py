"""Enemy level-scaling model, ported from the WARFRAME wiki infobox calculator.

Faithful Python port of the live gadget behind every enemy infobox
(``MediaWiki:Gadget-enemyinfoboxslider.js``, oldid 2816353, retrieved
2026-10-27), cross-checked against:

* https://wiki.warframe.com/w/Enemy_Level_Scaling
* https://wiki.warframe.com/w/Armor
* https://wiki.warframe.com/w/Eximus and /w/Overguard
* https://wiki.warframe.com/w/The_Steel_Path and /w/Empowered_Enemies
* https://wiki.warframe.com/w/Heavy_Gunner

The gadget is the authoritative implementation: its checkboxes (Eximus,
Steel Path, Archon Hunt/Netracell/Archimedea, The Icebind + player count)
match the two target-dummy configurations requested.

Pipeline (order matters and mirrors the gadget exactly)
-------------------------------------------------------
1. Eximus units swap to their own base stats (when defined) and gain a base
   Overguard of 12.
2. Steel Path / Archimedea additive base-health bonuses (0 for a Heavy
   Gunner) are added.
3. Eximus base health is replaced by the piecewise Eximus scaler, driven by
   the level difference ``q = current_level - base_level`` (0.25 coefficient
   for armored/shielded units, 0.375 otherwise).
4. Mission mode multipliers are applied to the *base* stats, before level
   scaling:
     - Steel Path: health and shields x2.5 (armor is untouched);
     - Empowered (Archon Hunt / Netracell / Archimedea):
       health and shields x(2.0 + 0.5 * players);
     - The Icebind: health, shields and armor x(3.0 + players).
5. Level multipliers use two power curves blended by a smoothstep:
     q < lo          -> weight 0 (pure f1)
     q > hi          -> weight 1 (pure f2)
     lo <= q <= hi   -> s = 3*T^2 - 2*T^3, T = (q - lo) / (hi - lo)
     multiplier = 1 + f1(q) + (f2(q) - f1(q)) * s
   Health/shields/armor transition between q = 70 and 80; Overguard between
   q = 45 and 50; Grineer outgoing damage between q = 1 and 25.
6. Health/shields/Overguard are rounded to 2 decimals; armor is floored and
   then clamped to [200, 2700] when positive.
7. Enemy armor damage reduction is
     DR = round(sqrt(3 * armor) * 100) / 10000
   i.e. 0.9 * sqrt(armor / 2700) rounded to 4 decimals (90% at the 2700 cap).
8. EHP = round(health / (1 - DR) + shields, 2) + overguard. Overguard is an
   unarmored buffer: it ignores armor DR and damage-type resistances (only
   Void takes a x1.5 modifier against it) and is never multiplied by the
   Steel Path / Empowered / Icebind modifiers.

Note on the armor formula: the prose on wiki.warframe.com/w/Armor and
/w/Damage/Calculation still shows the pre-U36 linear formula
``0.9 * armor / 2700`` (both pages carry "work in progress" banners). The
current in-game formula since Update 36 (Jade Shadows, 2024) is the square
root form above, confirmed by the maintained infobox gadget, the Fandom
mirror wiki and current community testing -- and it is what this
repository's ``modules/calculator.py`` already implements.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Armor bounds for level-scaled enemy armor.
ARMOR_CAP = 2700
ARMOR_FLOOR = 200

# Every Eximus spawns with this much base Overguard unless overridden.
OVERGUARD_BASE = 12

# Mission mode identifiers.
MODE_NORMAL = "normal"
MODE_STEEL_PATH = "steel_path"
MODE_EMPOWERED = "empowered"  # Archon Hunt / Netracell / Archimedea
MODE_ICEBIND = "icebind"

STEEL_PATH_MULTIPLIER = 2.5


def js_round(value: float) -> float:
    """JavaScript ``Math.round``: round half towards +infinity.

    All wiki gadget values are non-negative, so ``floor(x + 0.5)`` matches.
    """
    return math.floor(value + 0.5)


def round2(value: float) -> float:
    """Round to 2 decimals using the gadget's Math.round convention."""
    return js_round(value * 100.0) / 100.0


def smoothstep_transition(q: int, low: int, high: int) -> float:
    """Smoothstep blend weight ``s`` used between the f1 and f2 curves.

    Mirrors ``scaler.trans(start, end, curr_lvl)`` in the wiki gadget:
    0 below ``low``, 1 above ``high``, ``3T^2 - 2T^3`` in between.
    """
    if q < low:
        return 0.0
    if q > high:
        return 1.0
    t = (q - low) / (high - low)
    return 3.0 * t * t - 2.0 * t * t * t


@dataclass(frozen=True)
class ScalingCurve:
    """Pair of power curves ``f1``/``f2`` plus their transition window."""

    f1_coef: float
    f1_expo: float
    f2_coef: float
    f2_expo: float
    trans_low: int
    trans_high: int

    def f1(self, q: int) -> float:
        return self.f1_coef * q ** self.f1_expo

    def f2(self, q: int) -> float:
        return self.f2_coef * q ** self.f2_expo

    def multiplier(self, q: int) -> float:
        """Full level multiplier at level difference ``q``."""
        s = smoothstep_transition(q, self.trans_low, self.trans_high)
        return 1.0 + self.f1(q) + (self.f2(q) - self.f1(q)) * s


# Grineer health curve (Heavy Gunner). Coefficients come straight from the
# Heavy Gunner infobox parameter string and Enemy_Level_Scaling.
GRINEER_HEALTH = ScalingCurve(0.015, 2.12, 10.7332, 0.72, 70, 80)
GRINEER_ARMOR = ScalingCurve(0.005, 1.75, 0.4, 0.75, 70, 80)
OVERGUARD = ScalingCurve(0.0015, 4.0, 260.0, 0.9, 45, 50)
# Grineer outgoing damage curve; the gadget applies a final x2 faction factor.
GRINEER_DAMAGE = ScalingCurve(0.015, 1.75, 0.0075, 1.55, 1, 25)
GRINEER_DAMAGE_FINAL_MULT = 2.0

# Eximus base-health piecewise scaler coefficients.
EXIMUS_COEF_ARMORED = 0.25   # unit has shields or armor (Heavy Gunner)
EXIMUS_COEF_FLESH = 0.375    # unit has neither


@dataclass(frozen=True)
class EnemyBase:
    """Codex/base-level stats of an enemy unit."""

    name: str
    base_level: int
    health: float
    armor: float
    shields: float = 0.0
    overguard: float = 0.0
    faction: str = "Grineer"
    health_curve: ScalingCurve = GRINEER_HEALTH
    armor_curve: ScalingCurve = GRINEER_ARMOR
    overguard_curve: ScalingCurve = OVERGUARD
    damage_curve: Optional[ScalingCurve] = GRINEER_DAMAGE
    damage_final_mult: float = GRINEER_DAMAGE_FINAL_MULT
    # Note: shielded enemies would use a separate shield scaling curve in the
    # gadget; the Heavy Gunner has no shields, so none is modeled here and
    # shields reuse the health curve in scale_enemy (0 stays 0 regardless).
    # Eximus-specific base stats; None means the ordinary base stat is kept.
    eximus_health: Optional[float] = None
    eximus_armor: Optional[float] = None
    eximus_shields: Optional[float] = None
    eximus_overguard: Optional[float] = None
    # Additive Steel Path / Archimedea base-health bonuses (0 for Heavy Gunner).
    steel_path_health_bonus: float = 0.0
    steel_path_shield_bonus: float = 0.0
    archimedea_health_bonus: float = 0.0


HEAVY_GUNNER = EnemyBase(
    name="Heavy Gunner",
    base_level=8,
    health=300.0,
    armor=500.0,
    shields=0.0,
    faction="Grineer",
    eximus_health=300.0,
)


def eximus_base_health(base_health: float, q: int, armored: bool = True) -> float:
    """Piecewise Eximus base-health scaler at level difference ``q``.

    Port of the ``is_eximus`` block in the wiki gadget. The armored variant
    uses coefficient 0.25; flesh-only units use 0.375. Shields follow their
    own simpler branch and are irrelevant for the shieldless Heavy Gunner.
    """
    coef = EXIMUS_COEF_ARMORED if armored else EXIMUS_COEF_FLESH
    if q <= 15:
        return max(base_health * 1.1, coef * (base_health + 900.0))
    if q <= 25:
        ramp = 1.0 + 0.025 * (q - 15)
    elif q <= 35:
        ramp = 1.25 + 0.125 * (q - 25)
    elif q <= 50:
        ramp = 2.5 + (2.0 / 15.0) * (q - 35)
    elif q <= 100:
        ramp = 4.5 + 0.03 * (q - 50)
    else:
        ramp = 6.0
    return max(base_health * 1.1, coef * (base_health + 900.0) * ramp)


def empowered_multiplier(players: int) -> float:
    """Archon Hunt / Netracell / Archimedea health/shield multiplier."""
    if not 1 <= players <= 4:
        raise ValueError("Empowered Enemies supports 1-4 players")
    return 2.0 + 0.5 * players


def icebind_multiplier(players: int) -> float:
    """The Icebind health/shield/armor multiplier (4x at 1 player, 9x at 6)."""
    if not 1 <= players <= 6:
        raise ValueError("The Icebind supports 1-6 players")
    return 3.0 + 1.0 * players


def armor_damage_reduction(armor: float) -> float:
    """Enemy armor DR: ``round(sqrt(3 * armor) * 100) / 10000``.

    Equivalent to ``0.9 * sqrt(armor / 2700)`` with 4-decimal rounding;
    returns 0 for unarmored targets and caps at 0.9 for the 2700 armor cap.
    """
    if armor <= 0:
        return 0.0
    return js_round(math.sqrt(3.0 * armor) * 100.0) / 10000.0


def enemy_damage_multiplier(curve: ScalingCurve, q: int,
                            final_mult: float = 1.0) -> float:
    """Outgoing-damage level multiplier of an enemy (faction factor included)."""
    return curve.multiplier(q) * final_mult


@dataclass(frozen=True)
class ScaledEnemy:
    """Fully scaled defensive (and reference offensive) stats."""

    name: str
    level: int
    mode: str
    players: int
    eximus: bool
    base_health_used: float
    base_armor_used: float
    health: float
    shields: float
    armor: float
    armor_dr: float
    overguard: float
    ehp: float
    health_multiplier: float
    armor_multiplier: float
    overguard_multiplier: float
    outgoing_damage_multiplier: float = 0.0
    notes: tuple = field(default_factory=tuple)


def scale_enemy(enemy: EnemyBase,
                level: int,
                *,
                eximus: bool = False,
                mode: str = MODE_NORMAL,
                players: int = 1) -> ScaledEnemy:
    """Scale ``enemy`` to ``level`` under the given mission configuration.

    ``mode`` is one of MODE_NORMAL, MODE_STEEL_PATH, MODE_EMPOWERED and
    MODE_ICEBIND. ``players`` only matters for Empowered (1-4) and Icebind
    (1-6). Steel Path and the Empowered Enemies modifier never stack.
    """
    if level < enemy.base_level:
        raise ValueError(
            f"level {level} is below base level {enemy.base_level}")
    if mode not in (MODE_NORMAL, MODE_STEEL_PATH, MODE_EMPOWERED, MODE_ICEBIND):
        raise ValueError(f"unknown mode: {mode!r}")

    q = level - enemy.base_level
    notes = []

    # 1. Base stats, with Eximus replacements where defined.
    base_health = float(enemy.health)
    base_armor = float(enemy.armor)
    base_shields = float(enemy.shields)
    base_overguard = float(enemy.overguard)
    if eximus:
        if enemy.eximus_health is not None:
            base_health = float(enemy.eximus_health)
        if enemy.eximus_armor is not None:
            base_armor = float(enemy.eximus_armor)
        if enemy.eximus_shields is not None:
            base_shields = float(enemy.eximus_shields)
        base_overguard = OVERGUARD_BASE
        if enemy.eximus_overguard is not None:
            base_overguard = float(enemy.eximus_overguard)

    # 2. Additive mission base-stat bonuses (zero for a Heavy Gunner).
    if mode == MODE_STEEL_PATH:
        base_health += enemy.steel_path_health_bonus
        base_shields += enemy.steel_path_shield_bonus
    if mode == MODE_EMPOWERED:
        base_health += enemy.archimedea_health_bonus

    # 3. Eximus piecewise base-health scaler.
    if eximus:
        armored = base_armor > 0 or base_shields > 0
        base_health = eximus_base_health(base_health, q, armored=armored)

    # 4. Mission multipliers on the base stats (before level scaling).
    if mode == MODE_STEEL_PATH:
        base_health *= STEEL_PATH_MULTIPLIER
        base_shields *= STEEL_PATH_MULTIPLIER
    elif mode == MODE_EMPOWERED:
        mult = empowered_multiplier(players)
        base_health *= mult
        base_shields *= mult
    elif mode == MODE_ICEBIND:
        mult = icebind_multiplier(players)
        base_health *= mult
        base_shields *= mult
        base_armor *= mult
        notes.append(f"Icebind x{mult:g} applied to base health/shields/armor")

    # 5. Level curves.
    health_mult = enemy.health_curve.multiplier(q)
    armor_mult = enemy.armor_curve.multiplier(q)
    health = round2(base_health * health_mult)
    shields = round2(base_shields * health_mult) if base_shields > 0 else 0.0

    # 6. Armor: floor, then clamp to [200, 2700] (only when armored).
    raw_armor = math.floor(base_armor * armor_mult)
    if raw_armor > 0:
        armor = float(min(max(raw_armor, ARMOR_FLOOR), ARMOR_CAP))
        if raw_armor > ARMOR_CAP:
            notes.append("level/mission armor exceeds 2700; capped at 2700")
    else:
        armor = 0.0

    # 7. Armor damage reduction.
    dr = armor_damage_reduction(armor)

    # 8. Overguard (independent of mission HP/armor multipliers).
    if base_overguard > 0:
        overguard_mult = enemy.overguard_curve.multiplier(q)
        overguard = round2(base_overguard * overguard_mult)
    else:
        overguard_mult = 0.0
        overguard = 0.0

    # 9. EHP: armored health + unarmored shields, rounded, then Overguard.
    ehp = round2(health / (1.0 - dr) + shields) + overguard

    outgoing = 0.0
    if enemy.damage_curve is not None:
        outgoing = enemy_damage_multiplier(
            enemy.damage_curve, q, enemy.damage_final_mult)

    return ScaledEnemy(
        name=enemy.name,
        level=level,
        mode=mode,
        players=players,
        eximus=eximus,
        base_health_used=base_health,
        base_armor_used=base_armor,
        health=health,
        shields=shields,
        armor=armor,
        armor_dr=dr,
        overguard=overguard,
        ehp=ehp,
        health_multiplier=health_mult,
        armor_multiplier=armor_mult,
        overguard_multiplier=overguard_mult,
        outgoing_damage_multiplier=outgoing,
        notes=tuple(notes),
    )


# --- Requested target-dummy presets -------------------------------------

def steel_path_eximus_heavy_gunner(level: int = 150) -> ScaledEnemy:
    """Dummy A: Eximus Heavy Gunner on The Steel Path (solo-agnostic)."""
    return scale_enemy(HEAVY_GUNNER, level, eximus=True,
                       mode=MODE_STEEL_PATH)


def steel_path_heavy_gunner(level: int = 150) -> ScaledEnemy:
    """Plain (non-Eximus) Heavy Gunner on The Steel Path: no Overguard."""
    return scale_enemy(HEAVY_GUNNER, level, eximus=False,
                       mode=MODE_STEEL_PATH)


def icebind_eximus_heavy_gunner(level: int = 1000,
                                players: int = 6) -> ScaledEnemy:
    """Dummy B: Eximus Heavy Gunner in The Icebind (default full 6-player)."""
    return scale_enemy(HEAVY_GUNNER, level, eximus=True,
                       mode=MODE_ICEBIND, players=players)
