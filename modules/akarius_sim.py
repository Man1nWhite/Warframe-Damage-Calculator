"""Akarius Prime Riven choice simulation: Viral vs Corrosive.

WARNING: Experimental simulation, not a validated TTK or build-ranking model.
See docs/formula_audit.md for routing assumptions and status approximations.

Compares two otherwise identical Riven rolls on an Akarius Prime against the
Steel Path level 150 Eximus Heavy Gunner dummy (modules.enemy_scaling):

    Riven A: +133.7% Critical Damage, +133.7% Viral,     -47.6% Zoom
    Riven B: +133.7% Critical Damage, +133.7% Corrosive, -47.6% Zoom

Critical Damage and Zoom use the Pistol Riven, 2-positive/1-negative,
midpoint-grade column of source/riven_stats_average_1_2.csv. The CSV does
not contain spliced traits; Viral and Corrosive use the Wiki's 90% pistol
base with the same layout formula. The Zoom curse does not affect modeled
damage, and its impact on aiming is omitted.

Weapon model (wiki Akarius Prime, retrieved 2026-10-27):

* Two damage instances per rocket, each with its own status roll; independent
  crit rolls for impact and detonation are a simplifying assumption:
  - Rocket Impact: 68 Impact, projectile (direct hit).
  - Rocket Detonation: 509 Blast in a 7.8 m AoE (direct target = no falloff in
    this model; initial hit and explosion apply status separately).
* 18% crit chance, 2.0x crit multiplier, 34% status chance on both; burst of
  2 rockets (0.12 s apart) at 3.667 rockets/s; magazine 8, reload 2.4 s.
* Galvanized Shot stacking comes from this repository's own GunCO tables
  (source/gunco_mechanic.json): the Akarius Prime "Rocket Impact" is one of
  the discrepant projectile attacks whose CO-type bonus MULTIPLIES against
  ordinary +damage mods; Akarius Prime's Rocket Detonation receives no CO.
  With Hornet Strike +220%, three kill stacks, and one live status:
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
from collections.abc import Callable
from dataclasses import dataclass, field

from modules.crit import quantize_crit_multiplier

# Preserve historically importable simulator helpers for external callers.
from modules.enemy_scaling import enemy_armor_damage_reduction as armor_damage_reduction  # noqa: F401
from modules.kuva_nukor_sim import (
    BLAST_MAX_STACKS,
    BLAST_SINGLE_COEF,
    PISTOL_ELEMENTALIST_SD,
    BlastProc,
    DummyTarget,
    enervate_afcc,
    heat_tick,
    steel_path_eximus_heavy_gunner,
    wiki_quantized_damage,
)
from modules.kuva_nukor_sim import (
    HeatProc as HeatProc,
)
from modules.kuva_nukor_sim import (
    _heat_strip_fraction as _heat_strip_fraction,
)
from modules.kuva_nukor_sim import (
    viral_magnetic_multiplier as viral_magnetic_multiplier,
)
from modules.status_damage import blast_stack_damage
from modules.trial_statistics import sample_percentile

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
BASE_RELOAD_TIME = 2.4
RELOAD_TIME = BASE_RELOAD_TIME / 1.6  # +60% reload speed from Elementalist

# --- Mods -------------------------------------------------------------------

GALV_DIFFUSION_MS = 2.30
GALV_SHOT_STATUS = 0.80
GALV_SHOT_CO = 1.20          # 3 stacks x 40% per unique status type (cap)
HORNET_STRIKE = 2.20
LETHAL_TORRENT_FR = 0.60
LETHAL_TORRENT_MS = 0.60
PRIMED_HEATED_CHARGE = 1.65
PRIMED_TARGET_CRACKER = 1.10  # max-rank +110% Critical Damage
RIVEN_CRIT_DAMAGE = 1.337    # 2 positives + 1 curse, average grade
RIVEN_ELEMENT = 1.337
RIVEN_ZOOM_CURSE = -0.476    # not used in the damage-only model

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
    intra_burst_delay: float
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
    # Wiki Critical Hit: quantized base multiplier, then relative bonuses.
    crit_mult = quantize_crit_multiplier(BASE_CRIT_MULT) * (
        1.0 + PRIMED_TARGET_CRACKER + RIVEN_CRIT_DAMAGE)
    sd_mult = 1.0  # Elementalist changes status damage, not duration

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
        burst_cycle=(1.0 / fire_rate + (BURST_COUNT - 1)
                     * BURST_DELAY / (1.0 + LETHAL_TORRENT_FR)),
        intra_burst_delay=BURST_DELAY / (1.0 + LETHAL_TORRENT_FR),
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
    heat_dot_to_overguard: float = 0.0
    blast_proc_to_overguard: float = 0.0
    direct_to_health: float = 0.0
    heat_dot_to_health: float = 0.0
    blast_proc_to_health: float = 0.0
    break_electric: float = 0.0
    trace: list = field(default_factory=list)


# Grineer health/armor type modifiers (modules.constants FACTION_MULTIPLIERS).
GRINEER_TYPE_MOD = {"IMPACT": 1.5, "CORR": 1.5, "CORROSIVE": 1.5}


def simulate(build: AkariusBuild,
             target: AkariusTarget,
             *,
             seed: int = 1,
             trace: bool = False,
             trace_interval_s: float = 0.5,
             max_time: float = 600.0,
             direct_hits: bool = True) -> AkariusTrial:
    """Simulate one target with full-strength detonations and optional impacts.

    ``direct_hits=False`` is an idealized splash-only test, not a room model:
    another target or surface is assumed to trigger every explosion, but it is
    not simulated and no radial damage from other enemies' Blast procs is
    included. Rocket falloff, flight time, and finite reserve ammo are omitted.
    """
    rng = random.Random(seed)
    cc = build.afcc_pct / 100.0
    ammo = MAGAZINE
    now = 0.0
    reloads = 0
    shots = 0
    heat_count = 0
    corrosive_count = 0
    log: list[str] = []
    buckets = {"direct_og": 0.0, "heat_og": 0.0, "blast_og": 0.0,
               "direct_hp": 0.0, "heat_hp": 0.0, "blast_hp": 0.0,
               "break": 0.0}
    riven_key = build.riven.upper()

    def crit_factor() -> float:
        full = int(math.floor(cc))
        tier = full + (1 if rng.random() < (cc - full) else 0)
        return 1.0 + tier * (build.crit_multiplier - 1.0)

    def roll(weights: dict) -> str:
        return rng.choices(list(weights), weights=list(weights.values()))[0]

    def process_magnetic(when: float) -> None:
        target.prune(when, build.proc_duration)
        for _, result in target.process_magnetic_electric_until(
                when, build.heat_ramp_interval,
                faction_type_modifiers=GRINEER_TYPE_MOD):
            buckets["break"] += result.health

    def route(damage: dict[str, float], when: float, category: str,
              viral_stacks_override: int | None = None) -> None:
        target.prune(when, build.proc_duration)
        result = target.absorb(damage, when, build.heat_ramp_interval,
                               faction_type_modifiers=GRINEER_TYPE_MOD,
                               viral_stacks_override=viral_stacks_override)
        buckets[category + "_og"] += result.overguard
        buckets[category + "_hp"] += result.health
        if result.broke_overguard:
            if trace:
                log.append(f"  t={when:6.2f}s Overguard broke "
                           f"(mag x{target.mag_stacks(when)})")
            process_magnetic(when)

    def add_proc(ptype: str, when: float, cf: float,
                 seed_value: float) -> None:
        nonlocal heat_count, corrosive_count
        duration = (build.blast_fuse if ptype == "BLAST" else
                    build.corrosive_duration if ptype == "CORROSIVE" else build.proc_duration)
        target.record_status(ptype, when, duration)
        if ptype == "HEAT":
            target.add_heat(when, seed_value, cf, build.proc_duration)
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
                target.clear_status("BLAST")
                route({"BLAST": amount}, when, "blast")
        # IMPACT proc (stagger) has no single-target DPS effect.

    def dot_tick(when: float) -> None:
        ready_heat = target.consume_heat_tick(when, build.proc_duration)
        if ready_heat:
            weighted_seeds = sum(p.seed * p.crit_factor for p in ready_heat)
            tick = heat_tick(weighted_seeds,
                             elemental_bonus=build.heat_bonus,
                             status_damage_bonus=PISTOL_ELEMENTALIST_SD,
                             accumulator=True)
            route({"HEAT": tick}, when, "heat")

    def detonate_expired_blasts(when: float) -> None:
        due = [p for p in target.blast_stacks if p.fuse_end <= when]
        for p in due:
            target.blast_stacks.remove(p)
            # Damage/Calculation: an expiring stack deals max(1, 0.3 x H).
            amount = blast_stack_damage(
                p.seed, BLAST_SINGLE_COEF, crit_factor=p.crit_factor,
                status_damage_bonus=PISTOL_ELEMENTALIST_SD)
            route({"BLAST": amount}, when, "blast")
            if target.health <= 0:
                break

    def advance_events(until: float) -> float | None:
        while target.health > 0:
            next_heat = target.next_heat_tick(build.proc_duration)
            next_electric = target.next_magnetic_electric_tick()
            next_blast = min((p.fuse_end for p in target.blast_stacks),
                             default=math.inf)
            event = min(next_heat, next_electric, next_blast)
            if event > until:
                break
            if next_electric <= min(next_heat, next_blast):
                process_magnetic(event)
            elif next_heat <= next_blast:
                dot_tick(event)
            else:
                detonate_expired_blasts(event)
            if target.health <= 0:
                return event
        return None

    def fire_instance(when: float, cf: float, instance: dict,
                      weights: dict, base_modded: float,
                      shot_viral_stacks: int) -> None:
        # A projectile's CO multiplier uses statuses already present before
        # this instance. The explosion's GunCO behavior is NONE. Viral on
        # direct hits uses the pre-shot snapshot, rather than being amplified
        # by new Viral procs from other projectiles of the same shot.
        scale = 1.0
        if instance is build.impact_instance:
            count = target.unique_status_count(when)
            scale = (1.0 + GALV_SHOT_CO * count) / (1.0 + GALV_SHOT_CO)
        base_modded *= scale
        damage = {name: wiki_quantized_damage(value * scale, base_modded) * cf
                  for name, value in instance.items()} if base_modded > 0 else {}
        route(damage, when, "direct", shot_viral_stacks)
        if target.health <= 0:
            return
        # One independent status roll per damage instance.
        if rng.random() < build.status_per_instance:
            add_proc(roll(weights), when, cf, base_modded)

    shot_clock = 0.0       # wall-clock time of the next rocket
    now = 0.0
    while now < max_time and target.health > 0:
        if ammo <= 0:
            reloads += 1
            shot_clock += RELOAD_TIME
            death_time = advance_events(min(shot_clock, max_time))
            if death_time is not None:
                now = death_time
                break
            if shot_clock >= max_time:
                now = max_time
                break
            ammo = MAGAZINE

        # Burst delay and inter-burst delay are both reduced by fire-rate mods.
        in_burst = shots % BURST_COUNT
        when = shot_clock
        if when >= max_time:
            death_time = advance_events(max_time)
            now = death_time if death_time is not None else max_time
            break
        if in_burst == BURST_COUNT - 1:
            shot_clock = when + 1.0 / build.fire_rate
        else:
            shot_clock = when + build.intra_burst_delay
        now = when

        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break

        rockets = int(math.floor(build.multishot))
        if rng.random() < build.multishot - rockets:
            rockets += 1
        shot_viral_stacks = target.viral_stacks(when)
        for _ in range(rockets):
            if direct_hits:
                cf = crit_factor()
                fire_instance(when, cf, build.impact_instance,
                              build.proc_weights_impact,
                              build.impact_base_modded, shot_viral_stacks)
                if target.health <= 0:
                    break
            cf_aoe = crit_factor()
            fire_instance(when, cf_aoe, build.blast_instance,
                          build.proc_weights_blast,
                          build.blast_base_modded, shot_viral_stacks)
        shots += 1
        ammo -= 1
        if trace and shots % max(1, int(trace_interval_s
                                        / (build.burst_cycle / BURST_COUNT))) == 0:
            armor = target.current_armor(now, build.heat_ramp_interval)
            log.append(
                f"  t={now:6.2f}s og={max(target.overguard,0):12.0f} "
                f"hp={max(target.health,0):12.0f} armor={armor:8.1f} "
                f"heat={len(target.heat_procs):3d} "
                f"riven={target.corrosive_stacks(now) if riven_key == 'CORROSIVE' else target.viral_stacks(now):2d}")

    target.prune(now, build.proc_duration)
    ttk = now if target.health <= 0 else math.inf
    return AkariusTrial(
        ttk=ttk,
        overguard_break_time=(target.overguard_broken_at
                              if target.overguard_broken_at is not None
                              else 0.0 if target.overguard_max <= 0 else math.inf),
        shots=shots,
        reloads=reloads,
        heat_procs=heat_count,
        corrosive_procs=corrosive_count,
        final_armor=target.current_armor(
            ttk if math.isfinite(ttk) else now, build.heat_ramp_interval),
        direct_to_overguard=buckets["direct_og"],
        heat_dot_to_overguard=buckets["heat_og"],
        blast_proc_to_overguard=buckets["blast_og"],
        direct_to_health=buckets["direct_hp"],
        heat_dot_to_health=buckets["heat_hp"],
        blast_proc_to_health=buckets["blast_hp"],
        break_electric=buckets["break"],
        trace=log,
    )


def run_trials(riven: str,
               trials: int = 300,
               base_seed: int = 20261027,
               *,
               target_factory: Callable[[], AkariusTarget] | None = None,
               max_time: float = 600.0,
               direct_hits: bool = True) -> dict:
    """Summarize successful kills and report attempted/timed-out trials.

    ``target_factory`` must construct a fresh target for each trial. The
    default remains the level-150 Steel Path Eximus Heavy Gunner. Set
    ``direct_hits=False`` for an idealized splash-only individual target;
    see :func:`simulate` for its limitations.
    """
    if trials < 1:
        raise ValueError("trials must be positive")
    build = build_akarius(riven)
    factory = target_factory if target_factory is not None else akarius_dummy_factory
    ttks, og_times, armors, reloads_list, shots_list = [], [], [], [], []
    for i in range(trials):
        result = simulate(build, factory(), seed=base_seed + i,
                          max_time=max_time, direct_hits=direct_hits)
        if math.isfinite(result.ttk):
            ttks.append(result.ttk)
            og_times.append(result.overguard_break_time)
            armors.append(result.final_armor)
            reloads_list.append(result.reloads)
            shots_list.append(result.shots)
    return {
        "riven": riven,
        "build": build,
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
        "reloads_mean": sum(reloads_list) / len(reloads_list) if reloads_list else math.nan,
        "shots_mean": sum(shots_list) / len(shots_list) if shots_list else math.nan,
        "first_magazine_kills": sum(n == 0 for n in reloads_list),
    }
