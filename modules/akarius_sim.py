"""Akarius Prime Riven choice simulation: Viral vs Corrosive.

Compares two otherwise identical Riven rolls on an Akarius Prime against the
Steel Path level 150 Eximus Heavy Gunner dummy (modules.enemy_scaling):

    Riven A: +133.7% Critical Damage, +133.7% Viral,     -47.6% Zoom
    Riven B: +133.7% Critical Damage, +133.7% Corrosive, -47.6% Zoom

The averages are the Pistol Riven, 2 positive stats + 1 curse, average-grade
column of source/riven_stats_average_1_2.csv (combined elements use the same
average as single-element rolls; the Zoom curse is gameplay-neutral).

Weapon model (wiki Akarius Prime, retrieved 2026-10-27):

* Two damage instances per rocket, each with its own crit and status roll:
  - Rocket Impact: 68 Impact, projectile (direct hit).
  - Rocket Detonation: 509 Blast in a 7.8 m AoE (point-blank = no falloff in
    this model; initial hit and explosion apply status separately).
* 18% crit chance, 2.0x crit multiplier, 34% status chance on both; burst of
  2 rockets (0.12 s apart) at 3.667 rockets/s; magazine 8, reload 2.4 s.
* Galvanized Shot stacking comes from this repository's own GunCO tables
  (source/gunco_mechanic.json): the Akarius Prime "Rocket Impact" is one of
  the discrepant projectile attacks whose CO-type bonus MULTIPLIES against
  ordinary +damage mods, while projectile explosion radii never receive CO.
  So with Hornet Strike +220% and Galvanized Shot at its 3-stack cap:
    Rocket Impact bracket = (1 + 2.2) x (1 + 1.2) = 7.04
    Rocket Detonation     = (1 + 2.2)               = 3.2
* Galvanized Diffusion +230% and Lethal Torrent +60% give 3.9 multishot
  (3 guaranteed rockets + a 90% fourth); Lethal Torrent also gives +60% fire
  rate. Secondary Enervate is averaged through the wiki AFCC formula.

Status mechanics reuse modules.kuva_nukor_sim: Heat consolidation and armor
strip, Blast fuses, Viral/Magnetic stack multipliers, Overguard routing and
1/32 quantization. Corrosive is added here: first stack removes 26% of
CURRENT armor (20% + 6%), each further stack 6%, 80% at 10 stacks; it is
multiplicative with the Heat strip and lasts 8 s x status duration.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from modules.enemy_scaling import armor_damage_reduction
from modules.kuva_nukor_sim import (
    BLAST_MAX_STACKS,
    BLAST_SINGLE_COEF,
    PISTOL_ELEMENTALIST_SD,
    BlastProc,
    DummyTarget,
    HeatProc,
    _heat_strip_fraction,
    enervate_afcc,
    heat_tick,
    steel_path_eximus_heavy_gunner,
    viral_magnetic_multiplier,
    wiki_quantized_damage,
)

# --- Akarius Prime base stats ----------------------------------------------

IMPACT_BASE = 68.0          # Rocket Impact
BLAST_BASE = 509.0          # Rocket Detonation
BASE_CRIT_CHANCE = 0.18
BASE_CRIT_MULT = 2.0
BASE_FIRE_RATE = 3.667
BASE_STATUS = 0.34
BURST_COUNT = 2
BURST_DELAY = 0.12
MAGAZINE = 8
RELOAD_TIME = 2.4

# --- Mods -------------------------------------------------------------------

GALV_DIFFUSION_MS = 2.30
GALV_SHOT_STATUS = 0.80
GALV_SHOT_CO = 1.20          # 3 stacks x 40% per unique status type (cap)
HORNET_STRIKE = 2.20
LETHAL_TORRENT_FR = 0.60
LETHAL_TORRENT_MS = 0.60
PRIMED_HEATED_CHARGE = 1.65
PRIMED_TARGET_CRACKER = 1.20
RIVEN_CRIT_DAMAGE = 1.337    # 2 positives + 1 curse, average grade
RIVEN_ELEMENT = 1.337
RIVEN_ZOOM_CURSE = -0.476    # gameplay-neutral

CORROSIVE_FIRST_STACK = 0.26
CORROSIVE_PER_STACK = 0.06
CORROSIVE_CAP = 10
CORROSIVE_BASE_DURATION = 8.0
VIRAL_BASE_DURATION = 6.0
HEAT_BASE_DURATION = 6.0

RIVEN_VIRAL = "Viral"
RIVEN_CORROSIVE = "Corrosive"


def corrosive_armor_factor(stacks: int) -> float:
    """Multiplicative armor factor from Corrosive procs (26% + 6%/stack)."""
    n = min(max(stacks, 0), CORROSIVE_CAP)
    if n == 0:
        return 1.0
    return 1.0 - (0.20 + 0.06 * n)


@dataclass(frozen=True)
class AkariusBuild:
    riven: str
    multishot: float
    fire_rate: float
    burst_cycle: float
    status_per_instance: float
    afcc_pct: float
    crit_multiplier: float
    status_duration_mult: float
    heat_bonus: float
    impact_bracket: float
    blast_bracket: float
    # Per-rocket, per-instance damage distributions (before multishot/crit).
    impact_instance: dict
    blast_instance: dict
    impact_base_modded: float
    blast_base_modded: float
    proc_weights_impact: dict
    proc_weights_blast: dict
    heat_ramp_interval: float
    corrosive_duration: float
    proc_duration: float
    blast_fuse: float

    def describe(self) -> str:
        return (
            f"{self.riven} riven: MS x{self.multishot:.2f}, "
            f"FR {self.fire_rate:.3f}/s, status {self.status_per_instance:.3f} "
            f"per instance, AFCC {self.afcc_pct:.2f}%, cm {self.crit_multiplier:.3f}, "
            f"brackets impact x{self.impact_bracket:.3f} / blast x{self.blast_bracket:.2f}"
        )


def build_akarius(riven: str = RIVEN_VIRAL) -> AkariusBuild:
    if riven not in (RIVEN_VIRAL, RIVEN_CORROSIVE):
        raise ValueError(f"unknown riven element: {riven!r}")

    multishot = 1.0 + GALV_DIFFUSION_MS + LETHAL_TORRENT_MS
    fire_rate = BASE_FIRE_RATE * (1.0 + LETHAL_TORRENT_FR)
    status_per_instance = BASE_STATUS * (1.0 + GALV_SHOT_STATUS)
    afcc = enervate_afcc(BASE_CRIT_CHANCE * 100.0)  # no +crit-chance mods
    crit_mult = BASE_CRIT_MULT * (
        1.0 + PRIMED_TARGET_CRACKER + RIVEN_CRIT_DAMAGE)
    sd_mult = 1.0 + PISTOL_ELEMENTALIST_SD

    # GunCO table: Rocket Impact CO multiplies; detonation radius gets none.
    impact_bracket = (1.0 + HORNET_STRIKE) * (1.0 + GALV_SHOT_CO)
    blast_bracket = 1.0 + HORNET_STRIKE

    impact_modded = IMPACT_BASE * impact_bracket
    blast_modded = BLAST_BASE * blast_bracket

    impact_instance = {
        "IMPACT": impact_modded,
        "HEAT": impact_modded * PRIMED_HEATED_CHARGE,
        riven.upper(): impact_modded * RIVEN_ELEMENT,
    }
    blast_instance = {
        "BLAST": blast_modded,
        "HEAT": blast_modded * PRIMED_HEATED_CHARGE,
        riven.upper(): blast_modded * RIVEN_ELEMENT,
    }
    weights_impact = {k: v / sum(impact_instance.values())
                      for k, v in impact_instance.items()}
    weights_blast = {k: v / sum(blast_instance.values())
                     for k, v in blast_instance.items()}

    return AkariusBuild(
        riven=riven,
        multishot=multishot,
        fire_rate=fire_rate,
        burst_cycle=BURST_COUNT / fire_rate,
        status_per_instance=status_per_instance,
        afcc_pct=afcc,
        crit_multiplier=crit_mult,
        status_duration_mult=sd_mult,
        heat_bonus=PRIMED_HEATED_CHARGE,
        impact_bracket=impact_bracket,
        blast_bracket=blast_bracket,
        impact_instance=impact_instance,
        blast_instance=blast_instance,
        impact_base_modded=impact_modded,
        blast_base_modded=blast_modded,
        proc_weights_impact=weights_impact,
        proc_weights_blast=weights_blast,
        heat_ramp_interval=0.5 * sd_mult,
        corrosive_duration=CORROSIVE_BASE_DURATION * sd_mult,
        proc_duration=HEAT_BASE_DURATION * sd_mult,
        blast_fuse=1.5 * sd_mult,
    )


# --- Target with Corrosive state -------------------------------------------

class AkariusTarget(DummyTarget):
    def __init__(self, health: float, armor: float, overguard: float):
        super().__init__(health, armor, overguard)
        self.corrosive_expiries: list[float] = []

    def corrosive_stacks(self, now: float) -> int:
        self.corrosive_expiries = [t for t in self.corrosive_expiries
                                   if t > now]
        return len(self.corrosive_expiries)

    def current_armor(self, now: float, ramp_interval: float) -> float:
        heat_armor = super().current_armor(now, ramp_interval)
        return heat_armor * corrosive_armor_factor(
            self.corrosive_stacks(now))


def akarius_dummy_factory() -> AkariusTarget:
    dummy = steel_path_eximus_heavy_gunner(150)
    return AkariusTarget(dummy.health, dummy.armor, dummy.overguard)


# --- Simulation -------------------------------------------------------------

@dataclass
class AkariusTrial:
    ttk: float
    overguard_break_time: float
    shots: int
    reloads: int
    heat_procs: int
    corrosive_procs: int
    final_armor: float
    direct_to_overguard: float = 0.0
    blast_proc_to_overguard: float = 0.0
    direct_to_health: float = 0.0
    heat_dot_to_health: float = 0.0
    blast_proc_to_health: float = 0.0
    break_electric: float = 0.0
    trace: list = field(default_factory=list)


# Grineer health/armor type modifiers (modules.constants FACTION_MULTIPLIERS).
GRINEER_TYPE_MOD = {"IMPACT": 1.5, "CORR": 1.5}


def simulate(build: AkariusBuild,
             target: AkariusTarget,
             *,
             seed: int = 1,
             trace: bool = False,
             trace_interval_s: float = 0.5,
             max_time: float = 600.0) -> AkariusTrial:
    rng = random.Random(seed)
    cc = build.afcc_pct / 100.0
    ammo = MAGAZINE
    now = 0.0
    next_dot = 1.0
    reloads = 0
    shots = 0
    heat_count = 0
    corrosive_count = 0
    log: list[str] = []
    buckets = {"direct_og": 0.0, "blast_og": 0.0, "direct_hp": 0.0,
               "heat_hp": 0.0, "blast_hp": 0.0, "break": 0.0}
    riven_key = build.riven.upper()

    def crit_factor() -> float:
        full = int(math.floor(cc))
        tier = full + (1 if rng.random() < (cc - full) else 0)
        return 1.0 + tier * (build.crit_multiplier - 1.0)

    def roll(weights: dict) -> str:
        return rng.choices(list(weights), weights=list(weights.values()))[0]

    def type_mod(name: str) -> float:
        return GRINEER_TYPE_MOD.get(name, 1.0)

    def route(amount: float, when: float, name: str, bucket: str) -> None:
        if amount <= 0:
            return
        if target.overguard > 0:
            # Overguard: no armor, no damage-type or Viral modifiers.
            target.overguard -= amount
            buckets[bucket] += amount
            if target.overguard <= 0:
                break_overguard(when)
            return
        armor = target.current_armor(when, build.heat_ramp_interval)
        amount *= (1.0 - armor_damage_reduction(armor))
        amount *= viral_magnetic_multiplier(target.viral_stacks(when))
        amount *= type_mod(name)
        target.health -= amount
        buckets[bucket] += amount

    def break_overguard(when: float) -> None:
        target.broken = True
        stacks = target.mag_stacks(when)
        if stacks:
            electric = 0.03 * target.overguard_max * min(stacks, 10)
            armor = target.current_armor(when, build.heat_ramp_interval)
            dealt = electric * (1.0 - armor_damage_reduction(armor))
            target.health -= dealt
            buckets["break"] += dealt
        target.overguard = 0.0
        if trace:
            log.append(f"  t={when:6.2f}s Overguard broke (mag x{stacks})")

    def add_proc(ptype: str, when: float, cf: float,
                 seed_value: float) -> None:
        nonlocal heat_count, corrosive_count
        if ptype == "HEAT":
            for proc in target.heat_procs:
                proc.refreshed = when
            target.heat_procs.append(
                HeatProc(when, seed_value, cf, when))
            heat_count += 1
        elif ptype == "VIRAL":
            target.viral_expiries.append(when + build.proc_duration)
            if len(target.viral_expiries) > 10:
                target.viral_expiries.pop(0)
        elif ptype == "CORROSIVE":
            target.corrosive_expiries.append(
                when + build.corrosive_duration)
            if len(target.corrosive_expiries) > CORROSIVE_CAP:
                target.corrosive_expiries.pop(0)
            corrosive_count += 1
        elif ptype == "BLAST":
            target.blast_stacks.append(
                BlastProc(when, when + build.blast_fuse, seed_value, cf))
            if len(target.blast_stacks) >= BLAST_MAX_STACKS:
                amount = target.blast_single_damage(PISTOL_ELEMENTALIST_SD)
                target.blast_stacks.clear()
                route(amount, when, "BLAST", "blast_hp")
        # IMPACT proc (stagger) has no single-target DPS effect.

    def dot_tick(when: float) -> None:
        target.prune(when, build.proc_duration)
        if target.heat_procs:
            weighted_seeds = sum(p.seed * p.crit_factor
                                 for p in target.heat_procs)
            tick = heat_tick(weighted_seeds,
                             elemental_bonus=build.heat_bonus,
                             accumulator=True)
            if target.overguard > 0:
                target.overguard -= tick
                if target.overguard <= 0:
                    break_overguard(when)
            else:
                armor = target.current_armor(when, build.heat_ramp_interval)
                dealt = (tick * (1.0 - armor_damage_reduction(armor))
                         * viral_magnetic_multiplier(
                             target.viral_stacks(when)))
                target.health -= dealt
                buckets["heat_hp"] += dealt
        due = [p for p in target.blast_stacks if p.fuse_end <= when]
        for p in due:
            target.blast_stacks.remove(p)
            amount = (BLAST_SINGLE_COEF * p.seed
                      * (1.0 + PISTOL_ELEMENTALIST_SD) * p.crit_factor)
            route(amount, when, "BLAST",
                  "blast_og" if target.overguard > 0 else "blast_hp")

    def fire_instance(when: float, cf: float, instance: dict,
                      weights: dict, base_modded: float) -> None:
        # Direct damage with 1/32 quantization per type.
        for name, value in instance.items():
            q = wiki_quantized_damage(value, base_modded)
            route(q * cf, when, name,
                  "direct_og" if target.overguard > 0 else "direct_hp")
        # One independent status roll per damage instance.
        if rng.random() < build.status_per_instance:
            add_proc(roll(weights), when, cf, base_modded)

    og_break_time: Optional[float] = None
    shot_clock = 0.0       # wall-clock time of the next rocket
    now = 0.0
    while now < max_time and target.health > 0:
        if ammo <= 0:
            reloads += 1
            shot_clock += RELOAD_TIME
            while next_dot <= shot_clock and target.health > 0:
                dot_tick(next_dot)
                next_dot += 1.0
            ammo = MAGAZINE

        # Burst timing: two rockets per cycle, 0.12 s apart, then recovery.
        in_burst = shots % BURST_COUNT
        when = shot_clock
        if in_burst == BURST_COUNT - 1:
            shot_clock = when + BURST_DELAY + (
                build.burst_cycle - BURST_DELAY)
        else:
            shot_clock = when + BURST_DELAY
        now = when

        while next_dot <= now and target.health > 0:
            dot_tick(next_dot)
            next_dot += 1.0
        if target.health <= 0:
            break

        rockets = int(math.floor(build.multishot))
        if rng.random() < build.multishot - rockets:
            rockets += 1
        for _ in range(rockets):
            cf = crit_factor()
            fire_instance(when, cf, build.impact_instance,
                          build.proc_weights_impact,
                          build.impact_base_modded)
            if target.health <= 0:
                break
            cf_aoe = crit_factor()
            fire_instance(when, cf_aoe, build.blast_instance,
                          build.proc_weights_blast,
                          build.blast_base_modded)
        shots += 1
        ammo -= 1
        if target.broken and og_break_time is None:
            og_break_time = now
        if trace and shots % max(1, int(trace_interval_s
                                        / (build.burst_cycle / BURST_COUNT))) == 0:
            armor = target.current_armor(now, build.heat_ramp_interval)
            log.append(
                f"  t={now:6.2f}s og={max(target.overguard,0):12.0f} "
                f"hp={max(target.health,0):12.0f} armor={armor:8.1f} "
                f"heat={len(target.heat_procs):3d} "
                f"riven={target.corrosive_stacks(now) if riven_key == 'CORROSIVE' else target.viral_stacks(now):2d}")

    ttk = now if target.health <= 0 else math.inf
    return AkariusTrial(
        ttk=ttk,
        overguard_break_time=og_break_time if og_break_time is not None else ttk,
        shots=shots,
        reloads=reloads,
        heat_procs=heat_count,
        corrosive_procs=corrosive_count,
        final_armor=target.current_armor(
            ttk if math.isfinite(ttk) else now, build.heat_ramp_interval),
        direct_to_overguard=buckets["direct_og"],
        blast_proc_to_overguard=buckets["blast_og"],
        direct_to_health=buckets["direct_hp"],
        heat_dot_to_health=buckets["heat_hp"],
        blast_proc_to_health=buckets["blast_hp"],
        break_electric=buckets["break"],
        trace=log,
    )


def run_trials(riven: str,
               trials: int = 300,
               base_seed: int = 20261027) -> dict:
    build = build_akarius(riven)
    ttks, og_times, armors, reloads_list = [], [], [], []
    for i in range(trials):
        result = simulate(build, akarius_dummy_factory(),
                          seed=base_seed + i)
        if math.isfinite(result.ttk):
            ttks.append(result.ttk)
            og_times.append(result.overguard_break_time)
            armors.append(result.final_armor)
            reloads_list.append(result.reloads)
    ttks.sort()
    og_times.sort()

    def pct(vals: list[float], p: float) -> float:
        idx = min(len(vals) - 1, int(round(p * (len(vals) - 1))))
        return vals[idx]

    return {
        "riven": riven,
        "build": build,
        "trials": len(ttks),
        "ttk_mean": sum(ttks) / len(ttks),
        "ttk_median": pct(ttks, 0.5),
        "ttk_p90": pct(ttks, 0.9),
        "ttk_min": ttks[0],
        "ttk_max": ttks[-1],
        "overguard_median": pct(og_times, 0.5),
        "armor_median": pct(armors, 0.5),
        "reloads_mean": sum(reloads_list) / len(reloads_list),
    }
