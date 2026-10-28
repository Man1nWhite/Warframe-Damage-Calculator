"""Analytical Jat Kittag heavy-slam comparison, not a TTK simulator.

The candidate builds' source mechanics and limitations are documented in
``docs/jat_kittag_slam_spam_comparison.md``. In particular, this module does
NOT model Melee Afflictions, Blast detonations, Gas clouds, Vulcan Blitz,
armor changes, shield/Overguard routing, target movement, or a measured slam
cadence. Its direct-hit and status-roll calculations are deliberately kept
separate from a simple Initial Combo recovery scenario.

Assumptions: rank-5 Melee Afflictions, all three Galvanized kill effects at
four stacks, no external buffs or other combo sources, one slam landing per
chosen interval, no other source of status or elemental damage. Rank-8
Rivens use 1.20 normalized disposition and midpoint +3/-1 attributes. Gas on
such a Riven is a *spliced Gas attribute*, not a Heat + Toxin roll. A spliced
Gas attribute remains a separate damage type when regular Toxin is combined
with Electricity into Corrosive.

Run from the repository root:
    python -m modules.jat_kittag_slam_analysis
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from modules.status_damage import PROC_DURATION, magnetic_break_electric_tick, wiki_quantized_damage

# The current WARFRAME Wiki's weapon, mod and Riven values. Initial combo is
# the unrounded 4 * 20.35 Galvanized Reflex value; actual UI/engine rounding
# is not established by this analytical model.
SLAM_BASE = 600.0
PRESSURE_POINT = 1.65
SEISMIC_MULTIPLIER = 3.0
REFLEX_INITIAL_COMBO = 81.4
REFLEX_EFFICIENCY = 0.50
INITIAL_COMBO_REGEN = 40.0
MAX_EFFICIENCY = 0.90
BASE_CRIT_CHANCE = 0.15
BASE_CRIT_MULTIPLIER = 2.0
GALV_CRIT_CHANCE = 1.10
GALV_CRIT_DAMAGE = 1.20
GALV_STATUS_CHANCE = 1.20
GALV_STATUS_DAMAGE = 0.80
PRIMED_FEVER_STRIKE = 1.65

# Midpoints of the rank-8, 1.20 disposition, 3-positive/1-negative layout.
# See the Wiki's Melee Attribute Ranges. The rounded normal attributes match
# the repository's source/riven_stats_average_1_2.csv; the Spliced Gas and
# Spliced Status Damage midpoint is 0.90 * 1.20 * 0.9375 = 1.0125.
R3_ELEMENT = 1.0125
R3_STATUS_DAMAGE = 1.0125
R3_SLAM_DAMAGE = 1.197 * 1.20 * 0.9375
R3_HEAVY_ATTACK_DAMAGE = 1.197 * 1.20 * 0.9375
R3_CRIT_CHANCE = 2.025
R3_CRIT_DAMAGE = 1.0125
R3_MELEE_DAMAGE = 1.853
R3_HEAVY_EFFICIENCY = 0.826
R3_INITIAL_COMBO = 27.6

COMMON_MODS = (
    "Primed Pressure Point",
    "Seismic Wave",
    "Galvanized Elementalist",
    "Galvanized Reflex",
    "Vulcan Blitz",
    "Galvanized Steel",
)
COMMON_WITHOUT_PRESSURE = tuple(name for name in COMMON_MODS
                                if name != "Primed Pressure Point")


@dataclass(frozen=True)
class Build:
    """Fixed and flexible weapon mod slots; the arcane is a separate slot.

    Most scenarios have six common mods and two flexible slots; scenarios
    dropping Primed Pressure Point have five common mods and three flexible
    slots. ``types`` is the unquantized distribution relative to the 600-base
    slam. Corrosive/Gas values already include their primary elements.
    ``gas_bonus`` is literal +Gas, distinct from Heat and Toxin bonuses.
    """

    key: str
    label: str
    flex_slots: tuple[str, ...]
    types: Mapping[str, float]
    fixed_mods: tuple[str, ...] = COMMON_MODS
    extra_efficiency: float = 0.0
    initial_combo_bonus: float = 0.0
    melee_damage_bonus: float = 0.0
    heavy_attack_damage_bonus: float = 0.0
    slam_damage_bonus: float = 0.0
    crit_chance_bonus: float = 0.0
    crit_damage_bonus: float = 0.0
    status_chance_bonus: float = 0.0
    status_damage_bonus: float = 0.0
    gas_bonus: float = 0.0

    @property
    def weapon_mods(self) -> tuple[str, ...]:
        return self.fixed_mods + self.flex_slots

    @property
    def pressure_point_bonus(self) -> float:
        return PRESSURE_POINT if "Primed Pressure Point" in self.weapon_mods else 0.0

    @property
    def efficiency(self) -> float:
        return min(MAX_EFFICIENCY, REFLEX_EFFICIENCY + self.extra_efficiency)

    @property
    def initial_combo(self) -> float:
        return REFLEX_INITIAL_COMBO + self.initial_combo_bonus

    @property
    def crit_chance(self) -> float:
        # Galvanized Steel and Riven critical chance bonuses double on heavy
        # attacks; the initial +1 does not.
        return BASE_CRIT_CHANCE * (
            1.0 + 2.0 * (GALV_CRIT_CHANCE + self.crit_chance_bonus)
        )

    @property
    def crit_multiplier(self) -> float:
        return BASE_CRIT_MULTIPLIER * (
            1.0 + GALV_CRIT_DAMAGE + self.crit_damage_bonus
        )

    @property
    def average_crit_multiplier(self) -> float:
        # Crit tiers add (crit_multiplier - 1) per tier. This is the Wiki's
        # expected-value formula, ignoring exact binary32/crit quantization.
        return 1.0 + self.crit_chance * (self.crit_multiplier - 1.0)

    @property
    def status_rolls(self) -> float:
        return 1.0 + GALV_STATUS_CHANCE + self.status_chance_bonus

    @property
    def status_damage_multiplier(self) -> float:
        return 1.0 + GALV_STATUS_DAMAGE + self.status_damage_bonus

    def proc_share(self, kind: str) -> float:
        """Damage-weighted proc share on an enemy with no status immunity.

        The unquantized Arsenal-like distribution is used. Faction weaknesses
        do not affect proc weighting, but actual status immunity would.
        """
        return self.types.get(kind, 0.0) / sum(self.types.values())

    def probability_of(self, kind: str) -> float:
        return probability_at_least_one(self.status_rolls, self.proc_share(kind))

    def probability_of_both(self, a: str, b: str) -> float:
        if a == b:
            raise ValueError("the two status types must be distinct")
        return probability_both(self.status_rolls, self.proc_share(a),
                                self.proc_share(b))

    def probability_of_three(self, a: str, b: str, c: str) -> float:
        if len({a, b, c}) != 3:
            raise ValueError("the three status types must be distinct")
        return probability_three(self.status_rolls, self.proc_share(a),
                                 self.proc_share(b), self.proc_share(c))

    def direct_average(self, combo: int, *,
                       faction_types: Mapping[str, float] | None = None) -> float:
        """Raw expected center-slam damage *only*, before target defenses.

        The damage-type values are quantized to 1/32 of modded base per the
        Wiki's damage page. The actual critical multiplier's binary32/engine
        quantization is not represented; this is an illustrative expectation,
        not a complete enemy hit or damage-per-second model. The optional
        multipliers represent damage-type weakness, not faction-mod bonuses.
        """
        if not 1 <= combo <= 12:
            raise ValueError("combo tier must be between 1 and 12")
        # Heavy Attack Damage is additive with regular Melee Damage. Slam
        # Damage, including the spliced Riven attribute, shares the separate
        # Seismic Wave bracket. DoT/Afflictions interactions are not modeled.
        damage_base = SLAM_BASE * (1.0 + self.pressure_point_bonus + self.melee_damage_bonus
                                   + self.heavy_attack_damage_bonus)
        factors = faction_types or {}
        quantized_sum = sum(
            wiki_quantized_damage(damage_base * weight, damage_base)
            * factors.get(kind, 1.0)
            for kind, weight in self.types.items()
        )
        return (quantized_sum * (SEISMIC_MULTIPLIER + self.slam_damage_bonus)
                * combo * self.average_crit_multiplier)


# Unless otherwise stated, entries use the six COMMON_MODS plus two flexible
# slots. All entries must fit eight weapon mods, and can use at most one Riven.
# The newer Fever + Focus + Riven case omits Primed Pressure Point and thus
# uses COMMON_WITHOUT_PRESSURE plus three flexible slots.
BUILDS: tuple[Build, ...] = (
    Build("focus_energy", "Focus Energy + Primed Fever Strike",
          ("Primed Fever Strike", "Focus Energy"),
          {"BLAST": 1.0, "CORROSIVE": 2.25}, extra_efficiency=0.40),
    Build("focus_radon", "Focus Radon + Primed Fever Strike",
          ("Primed Fever Strike", "Focus Radon"),
          {"BLAST": 1.0, "TOXIN": 1.65, "RADIATION": 0.60},
          extra_efficiency=0.40),
    Build("volcanic_edge", "Volcanic Edge + Primed Fever Strike",
          ("Primed Fever Strike", "Volcanic Edge"),
          {"BLAST": 1.0, "GAS": 2.25}, status_chance_bonus=0.60),
    Build("molten_impact", "Molten Impact + Primed Fever Strike",
          ("Primed Fever Strike", "Molten Impact"),
          {"BLAST": 1.0, "GAS": 2.55}),
    Build("shocking_touch", "Shocking Touch + Primed Fever Strike",
          ("Primed Fever Strike", "Shocking Touch"),
          {"BLAST": 1.0, "CORROSIVE": 2.55}),
    Build("virulent_scourge", "Virulent Scourge + Primed Fever Strike",
          ("Primed Fever Strike", "Virulent Scourge"),
          {"BLAST": 1.0, "TOXIN": 2.25}, status_chance_bonus=0.60),
    # No splice required: all three traits below are normally rollable.
    Build("normal_eff_cc_damage", "Efficiency + Crit Chance + Damage; Fever",
          ("Primed Fever Strike", "Riven: Efficiency / Crit Chance / Melee Damage"),
          {"BLAST": 1.0, "TOXIN": 1.65},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          melee_damage_bonus=R3_MELEE_DAMAGE),
    Build("normal_eff_cc_cd", "Efficiency + Crit Chance + Crit Damage; Fever",
          ("Primed Fever Strike", "Riven: Efficiency / Crit Chance / Crit Damage"),
          {"BLAST": 1.0, "TOXIN": 1.65},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          crit_damage_bonus=R3_CRIT_DAMAGE),
    Build("normal_eff_cc_initial", "Efficiency + Crit Chance + Initial Combo; Fever",
          ("Primed Fever Strike", "Riven: Efficiency / Crit Chance / Initial Combo"),
          {"BLAST": 1.0, "TOXIN": 1.65},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          initial_combo_bonus=R3_INITIAL_COMBO),
    # Spliced Slam or Heavy Attack Damage cannot be combined with spliced
    # Gas on the same Riven: each build has exactly one spliced attribute.
    Build("slam_eff_cc", "Spliced Slam Damage + Efficiency + Crit Chance; Fever",
          ("Primed Fever Strike", "Riven: Slam Damage / Efficiency / Crit Chance"),
          {"BLAST": 1.0, "TOXIN": 1.65},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          slam_damage_bonus=R3_SLAM_DAMAGE),
    Build("heavy_eff_cc", "Spliced Heavy Attack Damage + Efficiency + Crit Chance; Fever",
          ("Primed Fever Strike", "Riven: Heavy Damage / Efficiency / Crit Chance"),
          {"BLAST": 1.0, "TOXIN": 1.65},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          heavy_attack_damage_bonus=R3_HEAVY_ATTACK_DAMAGE),
    # +Gas is the spliced attribute; the other two are regular Riven stats.
    Build("gas_eff_cc", "Spliced Gas + Efficiency + Crit Chance; Fever",
          ("Primed Fever Strike", "Riven: Gas / Efficiency / Crit Chance"),
          {"BLAST": 1.0, "TOXIN": 1.65, "GAS": R3_ELEMENT},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          gas_bonus=R3_ELEMENT),
    # With Fever Strike and no other source of Electricity, Cold becomes
    # Viral. Spliced Gas and innate Blast stay independent of that pair.
    Build("gas_cold_cc", "Spliced Gas + Cold + Crit Chance; Fever",
          ("Primed Fever Strike", "Riven: Gas / Cold / Crit Chance"),
          {"BLAST": 1.0, "GAS": R3_ELEMENT, "VIRAL": 1.65 + R3_ELEMENT},
          crit_chance_bonus=R3_CRIT_CHANCE, gas_bonus=R3_ELEMENT),
    # Gas + Magnetic + Toxin requires both primary components on the Riven.
    # Put the Riven before Fever so Cold/Electricity pair with each other.
    Build("gas_cold_electric", "Spliced Gas + Cold + Electricity; Fever",
          ("Riven: Gas / Cold / Electricity", "Primed Fever Strike"),
          {"BLAST": 1.0, "GAS": R3_ELEMENT, "MAGNETIC": 2 * R3_ELEMENT,
           "TOXIN": 1.65}, gas_bonus=R3_ELEMENT),
    # Alternatively, splice Magnetic and let ordinary Heat combine with Fever
    # into Gas. One Riven cannot contain two different spliced attributes.
    Build("mag_heat_eff", "Spliced Magnetic + Heat + Efficiency; Fever",
          ("Primed Fever Strike", "Riven: Magnetic / Heat / Efficiency"),
          {"BLAST": 1.0, "GAS": 1.65 + R3_ELEMENT, "MAGNETIC": R3_ELEMENT},
          extra_efficiency=R3_HEAVY_EFFICIENCY),
    Build("mag_heat_cc", "Spliced Magnetic + Heat + Crit Chance; Fever",
          ("Primed Fever Strike", "Riven: Magnetic / Heat / Crit Chance"),
          {"BLAST": 1.0, "GAS": 1.65 + R3_ELEMENT, "MAGNETIC": R3_ELEMENT},
          crit_chance_bonus=R3_CRIT_CHANCE),
    Build("gas_eff_damage", "Spliced Gas + Efficiency + Melee Damage; Fever",
          ("Primed Fever Strike", "Riven: Gas / Efficiency / Melee Damage"),
          {"BLAST": 1.0, "TOXIN": 1.65, "GAS": R3_ELEMENT},
          extra_efficiency=R3_HEAVY_EFFICIENCY,
          melee_damage_bonus=R3_MELEE_DAMAGE, gas_bonus=R3_ELEMENT),
    Build("gas_eff_cd", "Spliced Gas + Efficiency + Crit Damage; Fever",
          ("Primed Fever Strike", "Riven: Gas / Efficiency / Crit Damage"),
          {"BLAST": 1.0, "TOXIN": 1.65, "GAS": R3_ELEMENT},
          extra_efficiency=R3_HEAVY_EFFICIENCY,
          crit_damage_bonus=R3_CRIT_DAMAGE, gas_bonus=R3_ELEMENT),
    Build("gas_eff_initial", "Spliced Gas + Efficiency + Initial Combo; Fever",
          ("Primed Fever Strike", "Riven: Gas / Efficiency / Initial Combo"),
          {"BLAST": 1.0, "TOXIN": 1.65, "GAS": R3_ELEMENT},
          extra_efficiency=R3_HEAVY_EFFICIENCY,
          initial_combo_bonus=R3_INITIAL_COMBO, gas_bonus=R3_ELEMENT),
    # Swap Fever for Focus Energy: ordinary Riven Toxin combines into
    # Corrosive, while an optional spliced Gas attribute remains separate.
    # For Gas + Electricity, put this dual-element Riven *before* Focus
    # Energy in mod order, so its Heat and Toxin combine with one another.
    Build("focus_gas_electric_cc", "Heat + Toxin + Crit Chance; Focus Energy",
          ("Riven: Heat / Toxin / Crit Chance", "Focus Energy"),
          {"BLAST": 1.0, "GAS": 2 * R3_ELEMENT, "ELECTRICITY": 0.60},
          extra_efficiency=0.40, crit_chance_bonus=R3_CRIT_CHANCE),
    # Replacing Fever with Focus lets the user's Cold stat form Magnetic,
    # but there is then no standalone Toxin for shield bypass.
    Build("focus_gas_cold_cc", "Spliced Gas + Cold + Crit Chance; Focus Energy",
          ("Focus Energy", "Riven: Gas / Cold / Crit Chance"),
          {"BLAST": 1.0, "GAS": R3_ELEMENT, "MAGNETIC": 0.60 + R3_ELEMENT},
          extra_efficiency=0.40, crit_chance_bonus=R3_CRIT_CHANCE,
          gas_bonus=R3_ELEMENT),
    # Focus Energy stays uncombined because there is no Cold or Toxin.
    # Spliced Gas remains separate, with Pressure Point in the shared mods.
    Build("focus_gas_cc_cd", "Spliced Gas + Crit Chance + Crit Damage; Focus Energy",
          ("Focus Energy", "Riven: Gas / Crit Damage / Crit Chance"),
          {"BLAST": 1.0, "GAS": R3_ELEMENT, "ELECTRICITY": 0.60},
          extra_efficiency=0.40, crit_chance_bonus=R3_CRIT_CHANCE,
          crit_damage_bonus=R3_CRIT_DAMAGE, gas_bonus=R3_ELEMENT),
    # User's exact follow-up drops Primed Pressure Point. The Riven's Cold
    # and Focus Electricity pair before Fever's Toxin, leaving Toxin separate.
    Build("focus_fever_gas_cold_damage", "Fever + Focus + Gas / Cold / Damage; no PPP",
          ("Focus Energy", "Riven: Gas / Cold / Melee Damage", "Primed Fever Strike"),
          {"BLAST": 1.0, "GAS": R3_ELEMENT, "MAGNETIC": 0.60 + R3_ELEMENT,
           "TOXIN": PRIMED_FEVER_STRIKE},
          fixed_mods=COMMON_WITHOUT_PRESSURE, extra_efficiency=0.40,
          melee_damage_bonus=R3_MELEE_DAMAGE, gas_bonus=R3_ELEMENT),
    # Comparison only: identical slots and elements, replacing Riven Damage
    # with Crit Chance without reintroducing Pressure Point.
    Build("focus_fever_gas_cold_cc", "Fever + Focus + Gas / Cold / Crit; no PPP",
          ("Focus Energy", "Riven: Gas / Cold / Crit Chance", "Primed Fever Strike"),
          {"BLAST": 1.0, "GAS": R3_ELEMENT, "MAGNETIC": 0.60 + R3_ELEMENT,
           "TOXIN": PRIMED_FEVER_STRIKE},
          fixed_mods=COMMON_WITHOUT_PRESSURE, extra_efficiency=0.40,
          crit_chance_bonus=R3_CRIT_CHANCE, gas_bonus=R3_ELEMENT),
    Build("normal_corrosive_cc_damage", "Toxin + Crit Chance + Damage; Focus Energy",
          ("Focus Energy", "Riven: Toxin / Crit Chance / Melee Damage"),
          {"BLAST": 1.0, "CORROSIVE": 0.60 + R3_ELEMENT},
          extra_efficiency=0.40, crit_chance_bonus=R3_CRIT_CHANCE,
          melee_damage_bonus=R3_MELEE_DAMAGE),
    Build("normal_corrosive_cc_cd", "Toxin + Crit Chance + Crit Damage; Focus Energy",
          ("Focus Energy", "Riven: Toxin / Crit Chance / Crit Damage"),
          {"BLAST": 1.0, "CORROSIVE": 0.60 + R3_ELEMENT},
          extra_efficiency=0.40, crit_chance_bonus=R3_CRIT_CHANCE,
          crit_damage_bonus=R3_CRIT_DAMAGE),
    Build("normal_corrosive_cc_initial", "Toxin + Crit Chance + Initial Combo; Focus Energy",
          ("Focus Energy", "Riven: Toxin / Crit Chance / Initial Combo"),
          {"BLAST": 1.0, "CORROSIVE": 0.60 + R3_ELEMENT},
          extra_efficiency=0.40, crit_chance_bonus=R3_CRIT_CHANCE,
          initial_combo_bonus=R3_INITIAL_COMBO),
    Build("gas_corrosive_cc", "Spliced Gas + Toxin + Crit Chance; Focus Energy",
          ("Focus Energy", "Riven: Gas / Toxin / Crit Chance"),
          {"BLAST": 1.0, "CORROSIVE": 0.60 + R3_ELEMENT, "GAS": R3_ELEMENT},
          extra_efficiency=0.40, crit_chance_bonus=R3_CRIT_CHANCE,
          gas_bonus=R3_ELEMENT),
    Build("gas_corrosive_damage", "Spliced Gas + Toxin + Melee Damage; Focus Energy",
          ("Focus Energy", "Riven: Gas / Toxin / Melee Damage"),
          {"BLAST": 1.0, "CORROSIVE": 0.60 + R3_ELEMENT, "GAS": R3_ELEMENT},
          extra_efficiency=0.40, melee_damage_bonus=R3_MELEE_DAMAGE,
          gas_bonus=R3_ELEMENT),
    # This ordinary Riven is NOT a direct +Gas mod: Heat combines with Fever.
    Build("heat_eff_cc", "Heat + Efficiency + Crit Chance; Fever (no splice)",
          ("Primed Fever Strike", "Riven: Heat / Efficiency / Crit Chance"),
          {"BLAST": 1.0, "GAS": 1.65 + R3_ELEMENT},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE),
    # Volcanic Edge replaces Fever. Toxin from the Riven combines with Heat.
    Build("toxin_eff_cc_edge", "Toxin + Efficiency + Crit Chance; Volcanic Edge",
          ("Volcanic Edge", "Riven: Toxin / Efficiency / Crit Chance"),
          {"BLAST": 1.0, "GAS": 0.60 + R3_ELEMENT},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          status_chance_bonus=0.60),
    Build("status_eff_cc", "Spliced Status Damage + Efficiency + Crit Chance; Fever",
          ("Primed Fever Strike", "Riven: Status Damage / Efficiency / Crit Chance"),
          {"BLAST": 1.0, "TOXIN": 1.65},
          extra_efficiency=R3_HEAVY_EFFICIENCY, crit_chance_bonus=R3_CRIT_CHANCE,
          status_damage_bonus=R3_STATUS_DAMAGE),
)
BUILD_BY_KEY = {build.key: build for build in BUILDS}


def _probability_none(status_rolls: float, share: float) -> float:
    if status_rolls < 0.0 or not 0.0 <= share <= 1.0:
        raise ValueError("status rolls and type probability must be valid")
    guaranteed = math.floor(status_rolls)
    extra = status_rolls - guaranteed
    return (1.0 - share) ** guaranteed * (1.0 - extra * share)


def probability_at_least_one(status_rolls: float, share: float) -> float:
    """Chance of at least one chosen proc in the independent-roll model."""
    return 1.0 - _probability_none(status_rolls, share)


def probability_both(status_rolls: float, a: float, b: float) -> float:
    """Chance of at least one of each of two distinct proc types."""
    if a < 0.0 or b < 0.0 or a + b > 1.0 + 1e-12:
        raise ValueError("status shares must be nonnegative and sum to at most one")
    result = (1.0 - _probability_none(status_rolls, a)
              - _probability_none(status_rolls, b)
              + _probability_none(status_rolls, min(1.0, a + b)))
    return min(1.0, max(0.0, result))  # eliminate floating-point negative zero


def probability_three(status_rolls: float, a: float, b: float, c: float) -> float:
    """Chance of at least one of each of three distinct proc types."""
    if min(a, b, c) < 0.0 or a + b + c > 1.0 + 1e-12:
        raise ValueError("status shares must be nonnegative and sum to at most one")
    result = (1.0 - _probability_none(status_rolls, a)
              - _probability_none(status_rolls, b) - _probability_none(status_rolls, c)
              + _probability_none(status_rolls, min(1.0, a + b))
              + _probability_none(status_rolls, min(1.0, a + c))
              + _probability_none(status_rolls, min(1.0, b + c))
              - _probability_none(status_rolls, min(1.0, a + b + c)))
    return min(1.0, max(0.0, result))


def magnetic_break_electric_total(max_defense: float, stacks: int, *,
                                 status_damage_bonus: float = 0.0,
                                 electricity_bonus: float = 0.0,
                                 faction_bonus: float = 0.0,
                                 duration_multiplier: float = 1.0) -> float:
    """Wiki-based total forced Electricity proc on Magnetic defense break.

    Computes nominal damage over the unmodified six-second duration, capped
    at ten Magnetic stacks. A supplied duration multiplier scales the total
    linearly; fractional durations can differ due to discrete tick timing.
    The Wiki says status damage and faction bonuses apply twice and Electricity
    mods apply even when combined. It excludes target type modifiers, armor,
    gates, immunity and Afflictions-created statuses; it is not health damage
    or TTK. Bonuses belong to the source that applied Magnetic.
    """
    if (max_defense < 0 or not isinstance(stacks, int) or stacks < 0
            or status_damage_bonus < -1 or electricity_bonus < -1
            or faction_bonus < -1 or duration_multiplier < 0):
        raise ValueError("invalid Magnetic break inputs")
    return (magnetic_break_electric_tick(
        max_defense, stacks, status_damage_bonus=status_damage_bonus,
        electricity_bonus=electricity_bonus, faction_bonus=faction_bonus,
    ) * PROC_DURATION * duration_multiplier)


def combo_tier(points: float) -> int:
    if points < 0.0:
        raise ValueError("combo points must be nonnegative")
    return min(12, 1 + math.floor(points / 20.0))


def first_recovery_time(initial_combo: float, efficiency: float,
                        threshold: float, regen: float = INITIAL_COMBO_REGEN) -> float:
    """Time to reach a threshold once, starting at full Initial Combo."""
    if initial_combo < 0 or not 0 <= efficiency <= 1 or regen <= 0:
        raise ValueError("invalid combo parameters")
    if threshold > initial_combo:
        raise ValueError("threshold exceeds the Initial Combo floor")
    return max(0.0, threshold - initial_combo * efficiency) / regen


def sustainable_interval(threshold: float, efficiency: float,
                         regen: float = INITIAL_COMBO_REGEN) -> float:
    """Minimum ideal interval to sustain a threshold indefinitely.

    Unlike ``first_recovery_time``, this assumes the preceding hit may have
    occurred right at the threshold rather than at full Initial Combo.
    """
    if threshold < 0 or not 0 <= efficiency <= 1 or regen <= 0:
        raise ValueError("invalid combo parameters")
    return threshold * (1.0 - efficiency) / regen


def combo_sequence(initial_combo: float, efficiency: float, interval: float,
                   slams: int, *, starting_points: float | None = None) -> list[tuple[float, int]]:
    """Idealized points and tier immediately before each consecutive slam.

    Initial Combo regeneration occurs only while the post-spend count is below
    that Initial Combo floor. Counts above it can be retained but do not get
    free regeneration; no hits, blocks or other sources add combo. No rounding
    or discrete frame updates are modeled. Intervals are illustrative inputs,
    not weapon fire-rate or an estimate of human jump/landing timing.
    """
    if initial_combo < 0 or not 0 <= efficiency <= 1 or interval < 0 or slams < 0:
        raise ValueError("invalid combo sequence parameters")
    points = initial_combo if starting_points is None else starting_points
    if points < 0:
        raise ValueError("starting_points must be nonnegative")
    out = []
    for _ in range(slams):
        out.append((points, combo_tier(points)))
        after = points * efficiency
        points = after + min(max(initial_combo - after, 0.0),
                             INITIAL_COMBO_REGEN * interval)
    return out


def direct_sequence_average(build: Build, interval: float, slams: int = 8,
                            *, faction_types: Mapping[str, float] | None = None) -> float:
    seq = combo_sequence(build.initial_combo, build.efficiency, interval, slams)
    if not seq:
        raise ValueError("at least one slam is required")
    return sum(build.direct_average(tier, faction_types=faction_types)
               for _, tier in seq) / len(seq)


def _format_types(build: Build) -> str:
    return "+".join(build.types)


def main() -> None:
    print("Jat Kittag: analytical scenarios only; not a TTK or room-clear model")
    print("All Galvanized stacks assumed. Riven values are +3/-1 midpoints.\n")
    print("Build | types | eff | starting tier | crit | status | P(Blast) | "
          "P(Gas) | P(Tox) | P(Corr) | P(Elec) | P(Viral) | P(Mag) | P(Gas+Blast) | "
          "P(Gas+Mag) | P(Gas+other) | E[Gas] | E[Blast] | direct x5 neutral | "
          "8-hit direct neutral/reference | 8-hit direct Grineer/reference")
    reference_build = BUILD_BY_KEY["focus_energy"]
    reference = direct_sequence_average(reference_build, 0.65)
    grineer_types = {"CORROSIVE": 1.5}
    reference_grineer = direct_sequence_average(reference_build, 0.65,
                                                 faction_types=grineer_types)
    for build in BUILDS:
        second = next((kind for kind in ("TOXIN", "CORROSIVE", "ELECTRICITY",
                                         "VIRAL", "MAGNETIC")
                       if kind in build.types), None)
        both = (f"{second}:{build.probability_of_both('GAS', second):.2%}"
                if "GAS" in build.types and second is not None else "—")
        gas_blast = (f"{build.probability_of_both('GAS', 'BLAST'):.2%}"
                     if "GAS" in build.types else "—")
        gas_mag = (f"{build.probability_of_both('GAS', 'MAGNETIC'):.2%}"
                   if "GAS" in build.types and "MAGNETIC" in build.types else "—")
        print(f"{build.key} | {_format_types(build)} | {build.efficiency:.0%} | "
              f"{combo_tier(build.initial_combo)} | {build.crit_chance:.2%} | "
              f"{build.status_rolls:.3f} | {build.probability_of('BLAST'):.2%} | "
              f"{build.probability_of('GAS'):.2%} | {build.probability_of('TOXIN'):.2%} | "
              f"{build.probability_of('CORROSIVE'):.2%} | "
              f"{build.probability_of('ELECTRICITY'):.2%} | "
              f"{build.probability_of('VIRAL'):.2%} | "
              f"{build.probability_of('MAGNETIC'):.2%} | {gas_blast} | {gas_mag} | {both} | "
              f"{build.status_rolls * build.proc_share('GAS'):.3f} | "
              f"{build.status_rolls * build.proc_share('BLAST'):.3f} | "
              f"{build.direct_average(5):,.0f} | "
              f"{direct_sequence_average(build, 0.65) / reference:.3f} | "
              f"{direct_sequence_average(build, 0.65, faction_types=grineer_types) / reference_grineer:.3f}")
    requested = BUILD_BY_KEY["focus_fever_gas_cold_damage"]
    three = requested.probability_of_three("GAS", "MAGNETIC", "TOXIN")
    one_stack = magnetic_break_electric_total(
        100.0, 1, status_damage_bonus=GALV_STATUS_DAMAGE, electricity_bonus=0.60)
    print("\nRequested no-Pressure build (normal first-slam rolls, no prior statuses):")
    print(f"P(Gas + Magnetic + Toxin) = {three:.2%}; "
          f"Wiki-based Magnetic-break Electricity = {one_stack:.3f}% of maximum "
          "defense per stack nominal total over 6s before target mitigation.")
    print("\nIllustrative combo tiers over 8 consecutive slams:")
    for interval in (0.5, 0.65, 0.75, 1.0):
        parts = []
        for key in ("focus_energy", "volcanic_edge", "gas_eff_initial"):
            b = BUILD_BY_KEY[key]
            tiers = ''.join(str(tier) for _, tier in
                            combo_sequence(b.initial_combo, b.efficiency, interval, 8))
            parts.append(f"{key}={tiers}")
        print(f"{interval:.2f}s: " + "; ".join(parts))


if __name__ == "__main__":
    main()
