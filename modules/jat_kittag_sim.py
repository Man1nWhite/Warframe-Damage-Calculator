"""Jat Kittag heavy-slam simulation: last-slot mod and Riven choice.

WARNING: Experimental simulation, not a validated TTK or build-ranking model.
See docs/formula_audit.md for routing assumptions and status approximations.

The fixed build is:

* Primed Pressure Point (+165% base damage)
* Seismic Wave (+200% Slam Damage, its own multiplicative bracket)
* Galvanized Elementalist (+80% Status Damage; on-kill status chance stacks)
* Galvanized Reflex (+50% Heavy Attack Efficiency; on-kill Initial Combo)
* Vulcan Blitz (Jat Kittag-exclusive death explosion; inert on one target)
* Galvanized Steel (+110% crit chance, doubled to +220% on Heavy Attacks;
  on-kill critical-damage stacks)
* Primed Fever Strike (+165% Toxin)
* an open 8th slot: a normal mod or a Riven -- the decision modeled here.

Wiki mechanics (retrieved 2026-10-27):

* Heavy Slam: 600 Blast base (the weapon's 200 base x the universal 3x heavy
  slam multiplier), 100% status chance, forced Lifted, 10 m radius, minimum
  70% falloff at the edge (center dummy takes 100%), 1.0 slam per second.
  Heavy slams have no wind-up and add no combo points.
* Heavy-attack damage = Base x (1+damage mods) x (1+elemental mods) x heavy
  multiplier x combo multiplier; Seismic Wave's Slam Damage is a separate
  multiplicative bracket; Killing Blow's +120% is additive with Pressure
  Point; crit-chance mods (Galvanized Steel, Riven crit chance) apply twice.
* Heavy slams at zero combo deal x1. The module takes an explicit combo
  multiplier per trial so the cold-open spam case (1x) and a maintained
  tier (4x/7x/12x) can both be measured under the model's assumptions.
* Melee Afflictions (arcane): while Overguard is active it cannot trigger;
  afterwards, every slam on an already-Lifted enemy adds stacks of each
  live status effect on it (expired procs are pruned first, so nothing is
  resurrected). Rank 5 adds 6 stacks, but the wiki documents a bug where
  Lifted triggers add 12 — heavy slams force Lifted, so 12 is used here.
  Any modeled live status is eligible, including Corrosive and Viral.
  Modeled in both single-target and room simulations, but the Affliction
  Damage Hit and exact re-seeding modifiers are omitted; this is an
  approximation and cannot establish a reliable ranking.
* Gas: Heat+Toxin combine into Gas; clouds tick 6 times over 6 s, cap at 10
  instances and are armor-mitigated. Their seeds ignore Heat/Toxin bonuses;
  the model includes combo, crit, faction and status damage as applicable.
  The Seismic Wave interaction with status seeds is not verified here.
* Galvanized mods' on-kill stacks and Vulcan Blitz explosions cannot happen
  before the single dummy dies, so only their static effects enter the
  single-target sim; ``simulate_room`` models the kill-stacked behavior.

Target: SP150 Eximus Heavy Gunner dummy (1,716,837.41 health, 2,700 armor /
90% DR, 269,918.97 Overguard). Repo convention: Impact and Corrosive are
x1.5 vs Grineer, all other types neutral.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from modules.akarius_sim import corrosive_armor_factor
# Preserve historically importable simulator helpers for external callers.
from modules.enemy_scaling import (
    enemy_armor_damage_reduction as armor_damage_reduction,  # noqa: F401
    steel_path_heavy_gunner,
)
from modules.trial_statistics import sample_percentile
from modules.crit import quantize_crit_multiplier
from modules.kuva_nukor_sim import (
    DummyTarget,
    ToxinProc,
    steel_path_dummy_factory,
    viral_magnetic_multiplier as viral_magnetic_multiplier,
)
from modules.status_damage import (
    gas_tick,
    toxin_tick,
    wiki_quantized_damage,
)

# --- Weapon base stats -------------------------------------------------------

WEAPON_BASE = 200.0
HEAVY_SLAM_MULT = 3.0
SLAM_BASE = WEAPON_BASE * HEAVY_SLAM_MULT     # 600 Blast
BASE_CRIT_CHANCE = 0.15
BASE_CRIT_MULT = 2.0
BASE_STATUS = 1.0                             # slams are 100% status
SLAM_FIRE_RATE = 1.0                          # infobox attacks/sec
SLAM_RADIUS = 10.0
COMBO_DURATION = 5.0
PROC_DURATION = 6.0
CORROSIVE_DURATION = 8.0

# --- Fixed mods --------------------------------------------------------------

PPP = 1.65
SEISMIC_WAVE = 2.0                            # separate x3.0 bracket
GALV_ELEM_STATUS_DMG = 0.80
GALV_REFLEX_EFFICIENCY = 0.50
GALV_STEEL_CC = 1.10                          # x2 on heavy attacks
GALV_STEEL_KILL_CD = 0.30                     # per on-kill stack, 4 max
GALV_ELEM_KILL_STATUS = 0.30                  # per on-kill stack, 4 max
FEVER_TOXIN = 1.65
MOLTEN_HEAT = 0.90
SHOCKING_ELEC = 0.90
NORTH_COLD = 0.90
KILLING_BLOW = 1.20                           # additive with PPP on heavy
ORGAN_SHATTER_CD = 0.90
SMITE_GRINEER = 0.55
FOCUS_ENERGY_ELEC = 0.60
FOCUS_ENERGY_EFFICIENCY = 0.40
DUAL_STAT_ELEMENT = 0.60                     # 60/60 event mods
DUAL_STAT_STATUS = 0.60
EFFICIENCY_CAP = 0.90
GALV_REFLEX_IC_PER_STACK = 20.35              # rank-10 true value (4 = 81.4)
COMBO_REGEN_PER_SEC = 40.0                    # Initial Combo regen after heavy

# --- Average Riven values (normalized 1.20x) ---------------------------------

# 2 positives + 1 curse (used by the single-stat-pair Rivens).
R_MELEE_DAMAGE = 2.446
R_CRIT_CHANCE = 2.673
R_CRIT_DAMAGE = 1.337
R_ATTACK_SPEED = 0.815
R_STATUS_CHANCE = 1.337
R_ELEMENT = 1.337
R_INITIAL_COMBO = 36.4
R_EFFICIENCY = 1.091
# 3 positives + 1 curse (god roll: CC + CD + Attack Speed).
R3_CRIT_CHANCE = 2.025
R3_CRIT_DAMAGE = 1.013
R3_ATTACK_SPEED = 0.618

# --- Last-slot options -------------------------------------------------------

MOD_SLOTS = {
    "Gas (Molten Impact)": {"heat": MOLTEN_HEAT},
    "Corrosive (Shocking Touch)": {"elec": SHOCKING_ELEC},
    "Corrosive (Focus Energy)": {"elec": FOCUS_ENERGY_ELEC,
                                 "efficiency": FOCUS_ENERGY_EFFICIENCY},
    "60/60 Toxin (Virulent Scourge)": {"toxin": DUAL_STAT_ELEMENT,
                                       "status": DUAL_STAT_STATUS},
    "60/60 Heat (Volcanic Edge)": {"heat": DUAL_STAT_ELEMENT,
                                   "status": DUAL_STAT_STATUS},
    "Viral (North Wind)": {"cold": NORTH_COLD},
    "Killing Blow": {"heavy_damage": KILLING_BLOW},
    "Organ Shatter": {"crit_damage": ORGAN_SHATTER_CD},
    "Primed Smite Grineer": {"faction": SMITE_GRINEER},
}

RIVEN_SLOTS = {
    "Riven MD+CD": {"melee_damage": R_MELEE_DAMAGE,
                    "crit_damage": R_CRIT_DAMAGE},
    "Riven MD+Heat (Gas)": {"melee_damage": R_MELEE_DAMAGE,
                            "heat": R_ELEMENT},
    "Riven CC+CD": {"crit_chance": R_CRIT_CHANCE,
                    "crit_damage": R_CRIT_DAMAGE},
    "Riven MD+AtkSpd": {"melee_damage": R_MELEE_DAMAGE,
                        "attack_speed": R_ATTACK_SPEED},
    "Riven MD+Status": {"melee_damage": R_MELEE_DAMAGE,
                        "status_chance": R_STATUS_CHANCE},
    "Riven CD+Heat (Gas)": {"crit_damage": R_CRIT_DAMAGE,
                            "heat": R_ELEMENT},
    "Riven MD+InitCombo": {"melee_damage": R_MELEE_DAMAGE,
                           "initial_combo": R_INITIAL_COMBO},
    "Riven CC+CD+AS": {"crit_chance": R3_CRIT_CHANCE,
                       "crit_damage": R3_CRIT_DAMAGE,
                       "attack_speed": R3_ATTACK_SPEED},
}
ALL_OPTIONS = list(MOD_SLOTS) + list(RIVEN_SLOTS)

# The three-way comparison requested on the plain SP150 Heavy Gunner.
TTK_TABLE_OPTIONS = (
    "60/60 Toxin (Virulent Scourge)",
    "60/60 Heat (Volcanic Edge)",
    "Corrosive (Focus Energy)",
)

GRINEER_TYPE_MOD = {"IMPACT": 1.5, "CORR": 1.5}
AFFLICTION_STACKS = 6          # rank 5: added per knockdown/ragdoll trigger
# Wiki "Bugs" (both Fandom and wiki.warframe.com, retrieved 2026-10-27):
# a Lifted trigger adds 12 stacks instead of 6. Heavy slams force Lifted,
# so every trigger in this module uses the Lifted value.
LIFTED_AFFLICTION_STACKS = 12
GAS_CAP = 10
VIRAL_CAP = 10
CORROSIVE_CAP = 10


@dataclass(frozen=True)
class JatBuild:
    option: str
    is_riven: bool
    attack_speed: float
    slam_interval: float
    crit_chance: float
    crit_multiplier: float
    status_per_slam: float
    heavy_efficiency: float
    initial_combo: float
    damage_bracket: float
    faction_bracket: float
    seismic_bracket: float
    type_damage: dict
    proc_weights: dict
    modded_base: float
    toxin_elemental_bonus: float
    status_damage_bonus: float
    proc_duration: float

    def describe(self) -> str:
        return (
            f"{self.option}: cc {self.crit_chance * 100:.1f}% "
            f"cm {self.crit_multiplier:.3f}x interval {self.slam_interval:.3f}s "
            f"status/slam {self.status_per_slam:.2f} "
            f"bracket x{self.damage_bracket:.3f} "
            f"types {{{', '.join(f'{k}:{v:.0f}' for k, v in self.type_damage.items())}}}")


def combo_tier(points: float) -> int:
    """Combo multiplier for a combo-point count (20 points per tier, 12x cap)."""
    return min(12, max(1, 1 + int(points // 20)))


def _combine_elements(heat: float, cold: float, elec: float,
                      toxin: float) -> dict:
    """Warframe element combination rules for this build's component set."""
    out: dict[str, float] = {}
    if heat and toxin:
        out["GAS"] = heat + toxin
    elif elec and toxin:
        out["CORR"] = elec + toxin
    elif cold and toxin:
        out["VIRAL"] = cold + toxin
    else:
        if heat:
            out["HEAT"] = heat
        if cold:
            out["COLD"] = cold
        if elec:
            out["ELEC"] = elec
        if toxin:
            out["TOXIN"] = toxin
    return out


def _merged_spec(mod_option: Optional[str], riven_option: Optional[str]) -> dict:
    """Merge a last-slot mod spec and a Riven spec (disjoint stat keys)."""
    spec: dict = {}
    if mod_option is not None:
        if mod_option not in MOD_SLOTS:
            raise ValueError(f"unknown mod option: {mod_option!r}")
        spec.update(MOD_SLOTS[mod_option])
    if riven_option is not None:
        if riven_option not in RIVEN_SLOTS:
            raise ValueError(f"unknown Riven option: {riven_option!r}")
        for key, value in RIVEN_SLOTS[riven_option].items():
            spec[key] = spec.get(key, 0.0) + value
    if not spec:
        raise ValueError("at least one of mod_option/riven_option is required")
    return spec


def build_loadout(mod_option: Optional[str],
                  riven_option: Optional[str] = None,
                  galv_stacks: int = 0) -> JatBuild:
    """Build a full loadout: fixed mods + last-slot mod + optional Riven."""
    if not 0 <= galv_stacks <= 4:
        raise ValueError("galv_stacks must be between 0 and 4")
    spec = _merged_spec(mod_option, riven_option)
    label = " + ".join(p for p in (mod_option, riven_option) if p)
    return _build_from_spec(spec, label, riven_option is not None,
                            galv_stacks)


def build_jat_kittag(option: str, galv_stacks: int = 0) -> JatBuild:
    """Build one last-slot configuration (mod slot or Riven, not both).

    ``galv_stacks`` (0-4) assumes the Galvanized mods' on-kill effects are
    already stacked at fight start: Galv Steel adds +30% crit damage per
    stack (applied once; only its static crit chance is doubled on heavies),
    Galv Elementalist adds +30% status chance per stack, and Galv Reflex
    adds +20.35 Initial Combo per stack (81.4 at 4 stacks -> a 5x combo
    floor). The +50% efficiency and +80% status damage are static effects.
    """
    if not 0 <= galv_stacks <= 4:
        raise ValueError("galv_stacks must be between 0 and 4")
    if option in MOD_SLOTS:
        spec = dict(MOD_SLOTS[option])
        is_riven = False
    elif option in RIVEN_SLOTS:
        spec = dict(RIVEN_SLOTS[option])
        is_riven = True
    else:
        raise ValueError(f"unknown last-slot option: {option!r}")
    return _build_from_spec(spec, option, is_riven, galv_stacks)


def _build_from_spec(spec: dict, label: str, is_riven: bool,
                     galv_stacks: int) -> JatBuild:
    damage_bracket = 1.0 + PPP + spec.get("heavy_damage", 0.0) \
        + spec.get("melee_damage", 0.0)
    faction_bracket = 1.0 + spec.get("faction", 0.0)
    crit_chance = BASE_CRIT_CHANCE * (
        1.0 + 2.0 * GALV_STEEL_CC
        + 2.0 * spec.get("crit_chance", 0.0))
    # Wiki Critical Hit: quantized base multiplier, then relative bonuses.
    crit_multiplier = quantize_crit_multiplier(BASE_CRIT_MULT) * (
        1.0 + spec.get("crit_damage", 0.0)
        + GALV_STEEL_KILL_CD * galv_stacks)
    attack_speed = 1.0 + spec.get("attack_speed", 0.0)
    status_per_slam = BASE_STATUS * (
        1.0 + spec.get("status_chance", 0.0) + spec.get("status", 0.0)
        + GALV_ELEM_KILL_STATUS * galv_stacks)
    heavy_efficiency = min(EFFICIENCY_CAP,
                           GALV_REFLEX_EFFICIENCY + spec.get("efficiency", 0.0))
    initial_combo = (spec.get("initial_combo", 0.0)
                     + GALV_REFLEX_IC_PER_STACK * galv_stacks)

    toxin_bonus = FEVER_TOXIN + spec.get("toxin", 0.0)
    elements = _combine_elements(
        heat=spec.get("heat", 0.0),
        cold=spec.get("cold", 0.0),
        elec=spec.get("elec", 0.0),
        toxin=toxin_bonus,
    )
    type_damage = {"BLAST": SLAM_BASE * damage_bracket}
    for name, bonus in elements.items():
        type_damage[name] = SLAM_BASE * damage_bracket * bonus
    total = sum(type_damage.values())
    weights = {k: v / total for k, v in type_damage.items()}

    return JatBuild(
        option=label,
        is_riven=is_riven,
        attack_speed=attack_speed,
        slam_interval=SLAM_FIRE_RATE / attack_speed,
        crit_chance=crit_chance,
        crit_multiplier=crit_multiplier,
        status_per_slam=status_per_slam,
        heavy_efficiency=heavy_efficiency,
        initial_combo=initial_combo,
        damage_bracket=damage_bracket,
        faction_bracket=faction_bracket,
        seismic_bracket=1.0 + SEISMIC_WAVE,
        type_damage=type_damage,
        proc_weights=weights,
        modded_base=SLAM_BASE * damage_bracket,
        toxin_elemental_bonus=toxin_bonus,
        status_damage_bonus=GALV_ELEM_STATUS_DMG,
        proc_duration=PROC_DURATION,
    )


# --- Target with melee status state ------------------------------------------

@dataclass
class GasProc:
    start: float
    seed: float
    crit_factor: float
    next_tick: float | None = None

    def __post_init__(self) -> None:
        if self.next_tick is None:
            self.next_tick = self.start


class JatTarget(DummyTarget):
    """SP150 dummy plus Gas clouds, Corrosive stacks and Lifted state."""

    def __init__(self, health: float, armor: float, overguard: float):
        super().__init__(health, armor, overguard)
        self.gas_procs: list[GasProc] = []
        self.corrosive_expiries: list[float] = []
        self.lifted = False
        self.affliction_triggers = 0

    def corrosive_stacks(self, now: float) -> int:
        self.corrosive_expiries = [t for t in self.corrosive_expiries
                                   if t > now]
        return len(self.corrosive_expiries)

    def current_armor(self, now: float, ramp_interval: float) -> float:
        armor = super().current_armor(now, ramp_interval)
        return armor * corrosive_armor_factor(self.corrosive_stacks(now))

    def effective_armor(self, now: float) -> float:
        return self.current_armor(now, 0.5)


def _as_jat_target(target: DummyTarget) -> JatTarget:
    """Preserve factory state while adding the Jat-specific target fields."""
    if isinstance(target, JatTarget):
        return target
    adapted = JatTarget(target.max_health, target.max_armor, target.overguard_max)
    adapted.__dict__.update(target.__dict__)
    return adapted


def _next_status_tick(target: JatTarget) -> float:
    gas = (p.next_tick for p in target.gas_procs
           if p.next_tick < p.start + PROC_DURATION)
    toxin = (p.next_tick for p in target.toxin_procs
             if p.next_tick <= p.start + PROC_DURATION)
    return min(min(gas, default=math.inf), min(toxin, default=math.inf))


def _process_status_ticks(target: JatTarget, build: JatBuild, when: float,
                          route) -> None:
    """Resolve same-time Gas pulses together and Toxin ticks independently."""
    gas = [p for p in target.gas_procs
           if p.next_tick == when and p.next_tick < p.start + PROC_DURATION]
    if gas:
        seeds = sum(p.seed * p.crit_factor for p in gas)
        for proc in gas:
            proc.next_tick += 1.0
        route({"GAS": gas_tick(seeds,
              status_damage_bonus=build.status_damage_bonus,
              faction_bonus=build.faction_bracket - 1.0)}, when)
    for proc in target.toxin_procs:
        if target.health <= 0:
            break
        if proc.next_tick == when and proc.next_tick <= proc.start + PROC_DURATION:
            proc.next_tick += 1.0
            route({"TOXIN": toxin_tick(proc.seed * proc.crit_factor,
                  elemental_bonus=build.toxin_elemental_bonus,
                  status_damage_bonus=build.status_damage_bonus,
                  faction_bonus=build.faction_bracket - 1.0)}, when)


def plain_heavy_gunner_factory() -> JatTarget:
    """Non-Eximus SP150 Heavy Gunner: 286,139.57 HP, 2,700 armor, no Overguard."""
    gunner = steel_path_heavy_gunner(150)
    return JatTarget(gunner.health, gunner.armor, gunner.overguard)


def has_live_status(target: "JatTarget", when: float) -> bool:
    """True if at least one (un-expired) status stack is present."""
    if any(when < p.start + PROC_DURATION
           for p in target.gas_procs):
        return True
    if any(when < p.start + PROC_DURATION
           for p in target.toxin_procs):
        return True
    return bool(target.viral_stacks(when) or target.corrosive_stacks(when))


def has_live_dot(target: "JatTarget", when: float) -> bool:
    """True if a damaging DoT status (Gas/Toxin) is live on the target.

    This helper only classifies the stored procs. Melee Afflictions may
    also add stacks of non-damaging statuses; it is not a trigger gate.
    """
    if any(when < p.start + PROC_DURATION
           for p in target.gas_procs):
        return True
    return any(when < p.start + PROC_DURATION
               for p in target.toxin_procs)


def apply_melee_afflictions(target: "JatTarget", when: float,
                            stacks: int = LIFTED_AFFLICTION_STACKS) -> None:
    """Melee Afflictions: add stacks of every status already live on target.

    Heavy slams force Lifted, and the wiki documents a bug (carried on
    both wiki mirrors, retrieved 2026-10-27) where Lifted triggers add
    12 stacks instead of the rank-5 value of 6 — callers in this module
    therefore pass ``LIFTED_AFFLICTION_STACKS``. Expired proc lists are
    pruned first, so a new slam cannot resurrect an old effect. Statuses
    applied by the triggering slam
    itself are eligible (wiki explicitly includes them). The immediate
    Affliction Damage Hit and the wiki's "exponential" faction/Status
    Damage scaling are intentionally not modeled (conservative).
    """
    target.affliction_triggers += 1
    live_gas = [p for p in target.gas_procs
                if when < p.start + PROC_DURATION]
    target.gas_procs = live_gas
    if live_gas:
        avg_weighted_seed = sum(p.seed * p.crit_factor for p in live_gas) / len(live_gas)
        for _ in range(stacks):
            target.gas_procs.append(GasProc(when, avg_weighted_seed, 1.0))
        target.gas_procs = target.gas_procs[-GAS_CAP:]
    live_toxin = [p for p in target.toxin_procs
                  if when < p.start + PROC_DURATION]
    target.toxin_procs = live_toxin
    if live_toxin:
        avg_weighted_seed = sum(p.seed * p.crit_factor for p in live_toxin) / len(live_toxin)
        for _ in range(stacks):
            target.toxin_procs.append(ToxinProc(when, avg_weighted_seed, 1.0))
    # Stack-only effects: only extend status types already on the target.
    if target.viral_stacks(when):
        target.viral_expiries = (
            target.viral_expiries
            + [when + PROC_DURATION] * stacks)[-VIRAL_CAP:]
    if target.corrosive_stacks(when):
        target.corrosive_expiries = (
            target.corrosive_expiries
            + [when + CORROSIVE_DURATION] * stacks
        )[-CORROSIVE_CAP:]


# --- Single-target heavy-slam trial ------------------------------------------

@dataclass
class SlamTrial:
    ttk: float
    overguard_break_time: float
    slams: int
    gas_procs: int
    toxin_procs: int
    corrosive_procs: int
    viral_procs: int
    affliction_triggers: int
    final_armor: float
    direct_to_overguard: float = 0.0
    dot_to_overguard: float = 0.0
    direct_to_health: float = 0.0
    dot_to_health: float = 0.0
    break_electric: float = 0.0
    combo_tiers: list = field(default_factory=list)
    trace: list = field(default_factory=list)


def _crit_factor(rng: random.Random, cc: float, cm: float) -> float:
    full = int(math.floor(cc))
    tier = full + (1 if rng.random() < (cc - full) else 0)
    return 1.0 + tier * (cm - 1.0)


def _status_rolls(rng: random.Random, chance: float) -> int:
    guaranteed = int(math.floor(chance))
    return guaranteed + (1 if rng.random() < chance - guaranteed else 0)


def simulate(build: JatBuild,
             target: JatTarget,
             *,
             seed: int = 1,
             combo_multiplier: Optional[float] = 1.0,
             combo_recovery: bool = False,
             afflictions: bool = True,
             trace: bool = False,
             max_time: float = 600.0) -> SlamTrial:
    """Stochastic heavy-slam loop against one target.

    ``combo_multiplier`` is held constant unless ``combo_recovery`` is set.
    With recovery enabled the combo counter is simulated: each slam spends
    the counter, Heavy Attack Efficiency retains a fraction, and the spent
    Initial Combo regenerates at 40 points/s up to the build's Initial Combo
    floor (heavy slams themselves add no combo points).
    """
    rng = random.Random(seed)
    now = 0.0
    slams = 0
    counts = {"GAS": 0, "TOXIN": 0, "CORR": 0, "VIRAL": 0}
    log: list[str] = []
    buckets = {"direct_og": 0.0, "dot_og": 0.0, "direct_hp": 0.0,
               "dot_hp": 0.0, "break": 0.0}
    points = build.initial_combo
    tier_log: list[int] = []

    def process_magnetic(when: float) -> None:
        for _, result in target.process_magnetic_electric_until(
                when, 0.5, faction_type_modifiers=GRINEER_TYPE_MOD):
            buckets["break"] += result.health

    def route(damage: dict[str, float], when: float, is_dot: bool,
              bypass_armor: bool = False) -> None:
        result = target.absorb(damage, when, 0.5,
                               faction_type_modifiers=GRINEER_TYPE_MOD,
                               armor_bypass=bypass_armor)
        buckets["dot_og" if is_dot else "direct_og"] += result.overguard
        buckets["dot_hp" if is_dot else "direct_hp"] += result.health
        if result.broke_overguard:
            process_magnetic(when)

    def advance_events(until: float) -> float | None:
        while target.health > 0:
            next_electric = target.next_magnetic_electric_tick()
            next_dot = _next_status_tick(target)
            event = min(next_dot, next_electric)
            if event > until:
                break
            if next_electric <= next_dot:
                process_magnetic(event)
            else:
                _process_status_ticks(target, build, event,
                                      lambda damage, at: route(damage, at, True))
            if target.health <= 0:
                return event
        return None

    interval = build.slam_interval
    while now < max_time and target.health > 0:
        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break

        if combo_recovery:
            tier_mult = float(combo_tier(points))
        else:
            tier_mult = float(combo_multiplier)
        tier_log.append(int(tier_mult))
        cf = _crit_factor(rng, build.crit_chance, build.crit_multiplier)
        direct = {name: wiki_quantized_damage(single, build.modded_base)
                  * build.seismic_bracket * tier_mult * cf * build.faction_bracket
                  for name, single in build.type_damage.items()}
        route(direct, now, is_dot=False)
        slams += 1
        if target.health <= 0:
            break
        target.gas_procs = [p for p in target.gas_procs
                            if now < p.start + PROC_DURATION]
        target.toxin_procs = [p for p in target.toxin_procs
                              if now < p.start + PROC_DURATION]

        n_rolls = _status_rolls(rng, build.status_per_slam)
        for ptype in rng.choices(list(build.proc_weights),
                                 weights=list(build.proc_weights.values()),
                                 k=n_rolls):
            # Heavy-attack proc seeds inherit combo, as in the wiki's melee
            # status example. The 3x heavy-slam multiplier is already in
            # modded_base; faction enters here and again on each tick.
            seed = build.modded_base * build.faction_bracket * tier_mult
            if ptype == "GAS":
                target.gas_procs.append(GasProc(now, seed, cf))
                target.gas_procs = target.gas_procs[-GAS_CAP:]
                counts["GAS"] += 1
            elif ptype == "TOXIN":
                target.toxin_procs.append(ToxinProc(now, seed, cf))
                counts["TOXIN"] += 1
            elif ptype == "CORR":
                target.corrosive_expiries.append(now + CORROSIVE_DURATION)
                target.corrosive_expiries = target.corrosive_expiries[-CORROSIVE_CAP:]
                counts["CORR"] += 1
            elif ptype == "VIRAL":
                target.viral_expiries.append(now + PROC_DURATION)
                target.viral_expiries = target.viral_expiries[-VIRAL_CAP:]
                counts["VIRAL"] += 1
            # Blast proc damage is currently omitted; see formula_audit.md.

        # Melee Afflictions: impossible while Overguard is active (it grants
        # crowd-control immunity, so Lifted only sticks once broken); with no
        # Overguard the first slam Lifts and the second can trigger. The
        # gate sees only live statuses; expired procs are pruned first.
        if (afflictions and target.overguard <= 0 and target.lifted
                and has_live_status(target, now)):
            apply_melee_afflictions(target, now)
        if target.overguard <= 0:
            target.lifted = True

        # Combo: spend, retain via efficiency, then regenerate toward the
        # Initial Combo floor at 40 points/s until the next slam lands.
        if combo_recovery:
            points *= build.heavy_efficiency
        # Gas clouds pulse immediately on application (and on copied stacks).
        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break
        now += interval
        if combo_recovery:
            points = min(build.initial_combo,
                         points + COMBO_REGEN_PER_SEC * interval)
        if trace and slams % 2 == 0:
            log.append(
                f"  t={now:6.2f}s og={max(target.overguard, 0):12.0f} "
                f"hp={max(target.health, 0):12.0f} "
                f"armor={target.effective_armor(now):8.1f} "
                f"gas={len(target.gas_procs):2d} "
                f"viral={target.viral_stacks(now):2d} "
                f"corr={target.corrosive_stacks(now):2d} "
                f"affl={target.affliction_triggers:2d}")

    if target.health > 0 and now >= max_time:
        death_time = advance_events(max_time)
        now = death_time if death_time is not None else max_time

    ttk = now if target.health <= 0 else math.inf
    return SlamTrial(
        ttk=ttk,
        overguard_break_time=(target.overguard_broken_at
                              if target.overguard_broken_at is not None
                              else 0.0 if target.overguard_max <= 0 else math.inf),
        slams=slams,
        gas_procs=counts["GAS"],
        toxin_procs=counts["TOXIN"],
        corrosive_procs=counts["CORR"],
        viral_procs=counts["VIRAL"],
        affliction_triggers=target.affliction_triggers,
        final_armor=target.effective_armor(
            ttk if math.isfinite(ttk) else now),
        direct_to_overguard=buckets["direct_og"],
        dot_to_overguard=buckets["dot_og"],
        direct_to_health=buckets["direct_hp"],
        dot_to_health=buckets["dot_hp"],
        break_electric=buckets["break"],
        combo_tiers=tier_log,
        trace=log,
    )


def run_trials(option: str,
               trials: int = 300,
               base_seed: int = 20261027,
               combo_multiplier: Optional[float] = 1.0,
               galv_stacks: int = 0,
               combo_recovery: bool = False,
               riven_option: Optional[str] = None,
               factory=steel_path_dummy_factory) -> dict:
    """Summarize observed kills and report attempted and timed-out trials."""
    if trials < 1:
        raise ValueError("trials must be positive")
    if riven_option is not None:
        build = build_loadout(option, riven_option, galv_stacks)
    else:
        build = build_jat_kittag(option, galv_stacks)
    ttks, og_times, armors, affl, tiers, slam_counts = [], [], [], [], [], []
    for i in range(trials):
        target = _as_jat_target(factory())
        result = simulate(build, target, seed=base_seed + i,
                          combo_multiplier=combo_multiplier,
                          combo_recovery=combo_recovery)
        if math.isfinite(result.ttk):
            ttks.append(result.ttk)
            og_times.append(result.overguard_break_time)
            armors.append(result.final_armor)
            affl.append(result.affliction_triggers)
            slam_counts.append(result.slams)
            if result.combo_tiers:
                tiers.append(sum(result.combo_tiers) / len(result.combo_tiers))
    return {
        "option": build.option,
        "build": build,
        "combo_multiplier": combo_multiplier,
        "trials": len(ttks),
        "trials_attempted": trials,
        "timed_out": trials - len(ttks),
        "ttk_mean": sum(ttks) / len(ttks) if ttks else math.inf,
        "ttk_median": sample_percentile(ttks, 0.5, empty=math.inf),
        "ttk_p90": sample_percentile(ttks, 0.9, empty=math.inf),
        "ttk_min": min(ttks, default=math.inf),
        "ttk_max": max(ttks, default=math.inf),
        "overguard_median": sample_percentile(og_times, 0.5),
        "armor_median": sample_percentile(armors, 0.5),
        "affliction_median": sample_percentile(affl, 0.5),
        "slams_median": sample_percentile(slam_counts, 0.5),
        "combo_tier_mean": (sum(tiers) / len(tiers)) if tiers else None,
    }


# --- Room clear: AoE slams, Galvanized kill stacks, Vulcan Blitz -------------

@dataclass
class RoomTrial:
    clear_time: float
    n_enemies: int
    kill_times: list
    vulcan_explosions: int
    affliction_triggers: int = 0
    trace: list = field(default_factory=list)


def simulate_room(option: str,
                  n_enemies: int,
                  *,
                  seed: int = 1,
                  combo_multiplier: float = 7.0,
                  galv_stacks: int = 0,
                  afflictions: bool = True,
                  factory=steel_path_dummy_factory,
                  max_time: float = 600.0,
                  vulcan_falloff: float = 0.5) -> RoomTrial:
    """Dense pack inside the 10 m slam radius (center hits, no slam falloff).

    Each slam strikes every living target with independent crit/status rolls.
    Galvanized kill stacks accumulate as enemies die on top of the assumed
    ``galv_stacks`` floor; Vulcan Blitz deaths explode on the rest of the
    pack at an assumed average 50% radial falloff (linear 100%->0% across
    6 m, line of sight assumed). Melee Afflictions fire per target once it
    is Lifted with no Overguard left (``afflictions=False`` disables).
    """
    build = build_jat_kittag(option, 0)
    rng = random.Random(seed)
    targets = [_as_jat_target(factory()) for _ in range(n_enemies)]
    now = 0.0
    kill_times: list[tuple[int, float]] = []
    vulcan = 0

    def alive() -> list[JatTarget]:
        return [t for t in targets if t.health > 0]

    def process_magnetic(t: JatTarget, when: float) -> None:
        t.process_magnetic_electric_until(
            when, 0.5, faction_type_modifiers=GRINEER_TYPE_MOD)

    def route(t: JatTarget, damage: dict[str, float], when: float,
              bypass_armor: bool = False) -> None:
        result = t.absorb(damage, when, 0.5,
                          faction_type_modifiers=GRINEER_TYPE_MOD,
                          armor_bypass=bypass_armor)
        if result.broke_overguard:
            process_magnetic(t, when)

    def deaths(when: float) -> None:
        # Fixed point: a Vulcan blast can itself kill another target, whose
        # death then chains another explosion in the same pass.
        nonlocal vulcan
        while True:
            pending = [t for t in targets
                       if t.health <= 0 and not getattr(t, "_dead", False)]
            if not pending:
                return
            for t in pending:
                t._dead = True
                kill_times.append((id(t), when))
                vulcan += 1
                blast = (300.0 + 0.60 * t.max_health) * vulcan_falloff
                for other in alive():
                    route(other, {"BLAST": blast}, when)

    def advance_events(until: float) -> float | None:
        while alive():
            next_electric = min((t.next_magnetic_electric_tick() for t in targets
                                 if t.health > 0), default=math.inf)
            next_dot = min((_next_status_tick(t) for t in targets
                            if t.health > 0), default=math.inf)
            event = min(next_dot, next_electric)
            if event > until:
                break
            if next_electric <= next_dot:
                for t in targets:
                    if t.health > 0:
                        process_magnetic(t, event)
            else:
                for t in targets:
                    if t.health > 0 and _next_status_tick(t) == event:
                        _process_status_ticks(
                            t, build, event,
                            lambda damage, at, target=t: route(target, damage, at))
            deaths(event)
            if not alive():
                return event
        return None

    while now < max_time and alive():
        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break

        kills = sum(1 for t in targets if getattr(t, "_dead", False))
        steel_stacks = max(galv_stacks, min(4, kills))
        elem_stacks = max(galv_stacks, min(4, kills))
        cm = build.crit_multiplier * (1.0 + GALV_STEEL_KILL_CD * steel_stacks)
        # Rebuild the Galvanized Elementalist kill-stacked status chance.
        status_chance = build.status_per_slam * (
            1.0 + GALV_ELEM_KILL_STATUS * elem_stacks)

        for t in alive():
            cf = _crit_factor(rng, build.crit_chance, cm)
            direct = {name: wiki_quantized_damage(single, build.modded_base)
                      * build.seismic_bracket * combo_multiplier * cf * build.faction_bracket
                      for name, single in build.type_damage.items()}
            route(t, direct, now)
            if t.health <= 0:
                continue
            t.gas_procs = [p for p in t.gas_procs
                           if now < p.start + PROC_DURATION]
            t.toxin_procs = [p for p in t.toxin_procs
                             if now < p.start + PROC_DURATION]
            for ptype in rng.choices(
                    list(build.proc_weights),
                    weights=list(build.proc_weights.values()),
                    k=_status_rolls(rng, status_chance)):
                if ptype == "GAS":
                    t.gas_procs.append(GasProc(
                        now, build.modded_base * build.faction_bracket
                        * combo_multiplier, cf))
                    t.gas_procs = t.gas_procs[-GAS_CAP:]
                elif ptype == "TOXIN":
                    t.toxin_procs.append(
                        ToxinProc(now, build.modded_base * build.faction_bracket
                                  * combo_multiplier, cf))
                elif ptype == "CORR":
                    t.corrosive_expiries.append(now + CORROSIVE_DURATION)
                    t.corrosive_expiries = t.corrosive_expiries[-CORROSIVE_CAP:]
                elif ptype == "VIRAL":
                    t.viral_expiries.append(now + PROC_DURATION)
                    t.viral_expiries = t.viral_expiries[-VIRAL_CAP:]
            # Afflictions need a Lifted target and no active Overguard;
            # the first post-Overguard slam Lifts, later slams trigger.
            if (afflictions and t.overguard <= 0 and t.lifted
                    and has_live_status(t, now)):
                apply_melee_afflictions(t, now)
            if t.overguard <= 0:
                t.lifted = True
        deaths(now)
        if not alive():
            break
        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break
        now += build.slam_interval

    if alive() and now >= max_time:
        death_time = advance_events(max_time)
        if death_time is not None:
            now = death_time

    return RoomTrial(
        clear_time=now if not alive() else math.inf,
        n_enemies=n_enemies,
        kill_times=kill_times,
        vulcan_explosions=vulcan,
        affliction_triggers=sum(t.affliction_triggers for t in targets),
    )
