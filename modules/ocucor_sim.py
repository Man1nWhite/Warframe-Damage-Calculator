"""Ocucor simulation: arcane choice (Enervate vs Cascadia Flare) and Riven stat.

The Riven is fixed at +Viral / -Zoom plus one selectable positive stat
(average-grade Pistol Riven, 2 positives + 1 curse; values from
source/riven_stats_average_1_2.csv). Two arcanes are compared:

* Secondary Enervate: averaged through the wiki AFCC formula (the arcane adds
  absolute crit chance per hit, not a damage bonus despite the shorthand).
* Cascadia Flare: +12% generic damage per Heat status application for 10 s,
  one stack per damage instance, 40 stacks / +480% cap. The stack ramp is
  simulated tick by tick.

Weapon model (wiki Ocucor, retrieved 2026-10-27):

* 11 base damage (10 Radiation, 1 Puncture), 16% crit, 1.8x crit multiplier,
  12 ticks/s beam, 24% status, magazine 60, reload 1.6 s, 0.5 ammo per tick,
  20 m range, generic 20% -> 100% damage ramp over 0.6 s.
* Continuous beam: multishot beams merge (summed damage and status chance,
  single crit roll).
* Galvanized Shot stacking: Ocucor is not in the GunCO exception table, so
  the default hitscan rule applies -- its +120% CO bonus ADDS to the ordinary
  +damage pool (the same bracket as Cascadia Flare and a Damage Riven).
* Sentient Surge (Ocucor augment): +60% crit chance and +60% status chance
  per active Tendril, additive, up to 4 Tendrils (+240%); kills refill 20%
  of the magazine. Tendrils only exist after a kill, so against a single
  target the augment is inert until the fight is over; it only matters in
  the room-clear simulation. Tendril beams use the same base damage with
  independent crit and status rolls.

Target is the SP150 Eximus Heavy Gunner dummy (1,716,837.41 health,
2,700 armor / 90% DR, 269,918.97 Overguard). Heat consolidation/armor strip,
Viral stacks, Overguard routing and 1/32 quantization reuse the tested
primitives from modules.kuva_nukor_sim.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from modules.enemy_scaling import armor_damage_reduction
from modules.kuva_nukor_sim import (
    DummyTarget,
    HeatProc,
    enervate_afcc,
    heat_tick,
    steel_path_dummy_factory,
    viral_magnetic_multiplier,
    wiki_quantized_damage,
)

# --- Base weapon ------------------------------------------------------------

BASE_RADIATION = 10.0
BASE_PUNCTURE = 1.0
BASE_TOTAL = 11.0
BASE_CRIT_CHANCE = 0.16
BASE_CRIT_MULT = 1.8
BASE_FIRE_RATE = 12.0
BASE_STATUS = 0.24
MAGAZINE = 60
AMMO_PER_TICK = 0.5
RELOAD_TIME = 1.6
RAMP_TIME = 0.6
RAMP_START = 0.2

# --- Mods -------------------------------------------------------------------

GALV_DIFFUSION_MS = 2.30
GALV_SHOT_STATUS = 0.80
GALV_SHOT_CO = 1.20           # additive CO bracket (default hitscan rule)
LETHAL_TORRENT_FR = 0.60
LETHAL_TORRENT_MS = 0.60
PRIMED_HEATED_CHARGE = 1.65
PRIMED_TARGET_CRACKER = 1.20
PISTOL_ELEMENTALIST_SD = 0.90
RIVEN_VIRAL = 1.337           # 2 positives + 1 curse, average grade
RIVEN_ZOOM_CURSE = -0.476

# Average Riven values for the selectable second positive (2 pos + 1 curse).
RIVEN_STATS = {
    "Critical Damage": 1.337,
    "Critical Chance": 1.484,
    "Damage": 2.471,
    "Fire Rate": 0.840,
    "Status Chance": 1.485,
    "Multishot": 1.347,
}

# Cascadia Flare.
FLARE_PER_STACK = 0.12
FLARE_MAX_STACKS = 40
FLARE_DURATION = 10.0

# Sentient Surge.
SURGE_PER_TENDRIL = 0.60
SURGE_MAX_TENDRILS = 4
SURGE_REFILL = 0.20

ARCANE_ENERVATE = "Secondary Enervate"
ARCANE_FLARE = "Cascadia Flare"


@dataclass(frozen=True)
class OcucorBuild:
    arcane: str
    riven_stat: str
    multishot: float
    fire_rate: float
    tick_interval: float
    status_per_beam: float
    merged_status: float
    crit_chance_pct: float       # modded crit chance (Enervate: pre-arcane)
    afcc_pct: float              # Enervate only; equals modded chance for Flare
    crit_multiplier: float
    status_duration_mult: float
    heat_ramp_interval: float
    proc_duration: float
    base_damage_bracket: float   # without Flare stacks
    heat_bonus: float
    type_damage: dict
    modded_base_merged: float
    proc_weights: dict

    def describe(self) -> str:
        return (
            f"{self.arcane} / Riven {self.riven_stat}: MS x{self.multishot:.2f}, "
            f"FR {self.fire_rate:.2f}/s, merged status {self.merged_status:.2f}, "
            f"cc {self.crit_chance_pct:.2f}% (AFCC {self.afcc_pct:.2f}%), "
            f"cm {self.crit_multiplier:.3f}"
        )


def build_ocucor(arcane: str = ARCANE_ENERVATE,
                 riven_stat: str = "Critical Damage") -> OcucorBuild:
    if arcane not in (ARCANE_ENERVATE, ARCANE_FLARE):
        raise ValueError(f"unknown arcane: {arcane!r}")
    if riven_stat not in RIVEN_STATS:
        raise ValueError(f"unknown riven stat: {riven_stat!r}")
    riven = RIVEN_STATS[riven_stat]

    multishot = 1.0 + GALV_DIFFUSION_MS + LETHAL_TORRENT_MS + (
        riven if riven_stat == "Multishot" else 0.0)
    fire_rate = BASE_FIRE_RATE * (
        1.0 + LETHAL_TORRENT_FR + (riven if riven_stat == "Fire Rate" else 0.0))
    status_per_beam = BASE_STATUS * (
        1.0 + GALV_SHOT_STATUS
        + (riven if riven_stat == "Status Chance" else 0.0))
    crit_chance = BASE_CRIT_CHANCE * (
        1.0 + (riven if riven_stat == "Critical Chance" else 0.0))
    crit_mult = BASE_CRIT_MULT * (
        1.0 + PRIMED_TARGET_CRACKER
        + (riven if riven_stat == "Critical Damage" else 0.0))
    bracket = 1.0 + GALV_SHOT_CO + (
        riven if riven_stat == "Damage" else 0.0)
    sd_mult = 1.0 + PISTOL_ELEMENTALIST_SD

    modded_base_single = BASE_TOTAL * bracket
    modded_base_merged = modded_base_single * multishot
    type_damage = {
        "RAD": BASE_RADIATION * bracket,
        "PUNC": BASE_PUNCTURE * bracket,
        "HEAT": modded_base_single * PRIMED_HEATED_CHARGE,
        "VIRAL": modded_base_single * RIVEN_VIRAL,
    }
    total = sum(type_damage.values())
    weights = {k: v / total for k, v in type_damage.items()}
    afcc = (enervate_afcc(crit_chance * 100.0)
            if arcane == ARCANE_ENERVATE else crit_chance * 100.0)

    return OcucorBuild(
        arcane=arcane,
        riven_stat=riven_stat,
        multishot=multishot,
        fire_rate=fire_rate,
        tick_interval=1.0 / fire_rate,
        status_per_beam=status_per_beam,
        merged_status=status_per_beam * multishot,
        crit_chance_pct=crit_chance * 100.0,
        afcc_pct=afcc,
        crit_multiplier=crit_mult,
        status_duration_mult=sd_mult,
        heat_ramp_interval=0.5 * sd_mult,
        proc_duration=6.0 * sd_mult,
        base_damage_bracket=bracket,
        heat_bonus=PRIMED_HEATED_CHARGE,
        type_damage=type_damage,
        modded_base_merged=modded_base_merged,
        proc_weights=weights,
    )


# --- Single-target simulation ----------------------------------------------

@dataclass
class OcucorTrial:
    ttk: float
    overguard_break_time: float
    ticks: int
    reloads: int
    heat_procs: int
    flare_stacks_peak: int
    final_armor: float
    direct_to_overguard: float = 0.0
    dot_to_overguard: float = 0.0
    direct_to_health: float = 0.0
    dot_to_health: float = 0.0
    break_electric: float = 0.0
    trace: list = field(default_factory=list)


def _scaled_type_damage(build: OcucorBuild, flare_stacks: int) -> dict:
    bracket = build.base_damage_bracket
    if build.arcane == ARCANE_FLARE:
        bracket += min(flare_stacks, FLARE_MAX_STACKS) * FLARE_PER_STACK
    scale = bracket / build.base_damage_bracket
    return {k: v * scale for k, v in build.type_damage.items()}


def simulate(build: OcucorBuild,
             target: DummyTarget,
             *,
             seed: int = 1,
             trace: bool = False,
             trace_interval_s: float = 0.5,
             max_time: float = 600.0) -> OcucorTrial:
    rng = random.Random(seed)
    dt = build.tick_interval
    cc = build.afcc_pct / 100.0
    ammo = MAGAZINE
    now = 0.0
    next_dot = 1.0
    beam_time = 0.0
    reloads = 0
    ticks = 0
    heat_count = 0
    flare_stacks = 0
    flare_peak = 0
    flare_expiries: list[float] = []
    log: list[str] = []
    buckets = {"direct_og": 0.0, "dot_og": 0.0, "direct_hp": 0.0,
               "dot_hp": 0.0, "break": 0.0}

    def crit_factor() -> float:
        full = int(math.floor(cc))
        tier = full + (1 if rng.random() < (cc - full) else 0)
        return 1.0 + tier * (build.crit_multiplier - 1.0)

    def roll(k: int) -> list[str]:
        return rng.choices(list(build.proc_weights),
                           weights=list(build.proc_weights.values()), k=k)

    def break_overguard(when: float) -> None:
        target.broken = True
        target.overguard = 0.0
        if trace:
            log.append(f"  t={when:6.2f}s Overguard broke")

    def route(amount: float, when: float, is_dot: bool) -> None:
        if amount <= 0:
            return
        if target.overguard > 0:
            target.overguard -= amount
            buckets["dot_og" if is_dot else "direct_og"] += amount
            if target.overguard <= 0:
                break_overguard(when)
            return
        armor = target.current_armor(when, build.heat_ramp_interval)
        amount *= (1.0 - armor_damage_reduction(armor))
        amount *= viral_magnetic_multiplier(target.viral_stacks(when))
        target.health -= amount
        buckets["dot_hp" if is_dot else "direct_hp"] += amount

    def dot_tick(when: float) -> None:
        target.prune(when, build.proc_duration)
        if not target.heat_procs:
            return
        weighted_seeds = sum(p.seed * p.crit_factor
                             for p in target.heat_procs)
        tick = heat_tick(weighted_seeds,
                         elemental_bonus=build.heat_bonus,
                         accumulator=True)
        route(tick, when, is_dot=True)

    og_break_time: Optional[float] = None
    while now < max_time and target.health > 0:
        # Expire Flare stacks.
        flare_expiries = [t for t in flare_expiries if t > now]
        flare_stacks = len(flare_expiries)

        if ammo <= 0:
            reloads += 1
            reload_end = now + RELOAD_TIME
            while next_dot <= reload_end and target.health > 0:
                dot_tick(next_dot)
                next_dot += 1.0
            now = reload_end
            ammo = MAGAZINE
            continue

        while next_dot <= now and target.health > 0:
            dot_tick(next_dot)
            next_dot += 1.0
        if target.health <= 0:
            break

        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START) * beam_time / RAMP_TIME)
        cf = crit_factor()
        types = _scaled_type_damage(build, flare_stacks)
        modded_base_merged = (
            BASE_TOTAL
            * (build.base_damage_bracket
               + (min(flare_stacks, FLARE_MAX_STACKS) * FLARE_PER_STACK
                  if build.arcane == ARCANE_FLARE else 0.0))
            * build.multishot)

        direct = 0.0
        for name, single in types.items():
            direct += wiki_quantized_damage(
                single * build.multishot, modded_base_merged)
        route(direct * ramp * cf, now, is_dot=False)

        guaranteed = int(math.floor(build.merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < build.merged_status - guaranteed else 0)
        heat_this_tick = False
        for ptype in roll(n_procs):
            if ptype == "HEAT":
                for proc in target.heat_procs:
                    proc.refreshed = now
                target.heat_procs.append(
                    HeatProc(now, modded_base_merged, cf, now))
                heat_count += 1
                heat_this_tick = True
            elif ptype == "VIRAL":
                target.viral_expiries.append(now + build.proc_duration)
                if len(target.viral_expiries) > 10:
                    target.viral_expiries.pop(0)
            # RAD/PUNC procs have no single-target DPS effect.

        # Flare: at most one stack per damage instance (merged beam tick).
        if (build.arcane == ARCANE_FLARE and heat_this_tick
                and flare_stacks < FLARE_MAX_STACKS):
            flare_stacks += 1
            flare_peak = max(flare_peak, flare_stacks)
            flare_expiries.append(now + FLARE_DURATION)

        ammo -= AMMO_PER_TICK
        ticks += 1
        beam_time += dt
        now += dt
        if target.broken and og_break_time is None:
            og_break_time = now
        if trace and ticks % max(1, int(trace_interval_s / dt)) == 0:
            armor = target.current_armor(now, build.heat_ramp_interval)
            log.append(
                f"  t={now:6.2f}s og={max(target.overguard,0):12.0f} "
                f"hp={max(target.health,0):12.0f} armor={armor:8.1f} "
                f"heat={len(target.heat_procs):3d} "
                f"viral={target.viral_stacks(now):2d} flare={flare_stacks:2d}")

    ttk = now if target.health <= 0 else math.inf
    return OcucorTrial(
        ttk=ttk,
        overguard_break_time=og_break_time if og_break_time is not None else ttk,
        ticks=ticks,
        reloads=reloads,
        heat_procs=heat_count,
        flare_stacks_peak=flare_peak,
        final_armor=target.current_armor(
            ttk if math.isfinite(ttk) else now, build.heat_ramp_interval),
        direct_to_overguard=buckets["direct_og"],
        dot_to_overguard=buckets["dot_og"],
        direct_to_health=buckets["direct_hp"],
        dot_to_health=buckets["dot_hp"],
        break_electric=buckets["break"],
        trace=log,
    )


def run_trials(arcane: str,
               riven_stat: str,
               trials: int = 300,
               base_seed: int = 20261027,
               factory=steel_path_dummy_factory) -> dict:
    build = build_ocucor(arcane, riven_stat)
    ttks, og_times, flares, armors = [], [], [], []
    for i in range(trials):
        result = simulate(build, factory(), seed=base_seed + i)
        if math.isfinite(result.ttk):
            ttks.append(result.ttk)
            og_times.append(result.overguard_break_time)
            flares.append(result.flare_stacks_peak)
            armors.append(result.final_armor)
    ttks.sort()

    def pct(vals: list[float], p: float) -> float:
        idx = min(len(vals) - 1, int(round(p * (len(vals) - 1))))
        return vals[idx]

    return {
        "arcane": arcane,
        "riven_stat": riven_stat,
        "build": build,
        "trials": len(ttks),
        "ttk_mean": sum(ttks) / len(ttks),
        "ttk_median": pct(ttks, 0.5),
        "ttk_p90": pct(ttks, 0.9),
        "ttk_min": ttks[0],
        "ttk_max": ttks[-1],
        "overguard_median": pct(og_times, 0.5),
        "flare_peak_median": pct(flares, 0.5),
        "armor_median": pct(armors, 0.5),
    }


# --- Room clear with Tendrils + Sentient Surge ------------------------------

@dataclass
class RoomResult:
    clear_time: float
    n_enemies: int
    kill_times: list
    tendril_peak: int
    reloads: int
    flare_peak: int = 0
    trace: list = field(default_factory=list)


def simulate_room(arcane: str,
                  riven_stat: str,
                  n_enemies: int,
                  *,
                  seed: int = 1,
                  factory=steel_path_dummy_factory,
                  max_time: float = 600.0) -> RoomResult:
    """Dense room: primary beam on one target, Tendrils on the others.

    Each kill spawns a Tendril (max 4). Every beam tick, each Tendril fires a
    full-damage beam at another living target with independent crit/status
    rolls; Sentient Surge grants +60% crit and +60% status per Tendril.
    """
    build = build_ocucor(arcane, riven_stat)
    rng = random.Random(seed)
    targets = [factory() for _ in range(n_enemies)]
    ammo = MAGAZINE
    now = 0.0
    next_dot = 1.0
    beam_time = 0.0
    reloads = 0
    tendrils = 0
    tendril_peak = 0
    kill_times: list[tuple[int, float]] = []
    dt = build.tick_interval
    flare_stacks = 0
    flare_peak = 0
    flare_expiries: list[float] = []

    def alive() -> list[int]:
        return [i for i, t in enumerate(targets) if t.health > 0]

    def record_deaths(when: float) -> None:
        nonlocal tendrils, ammo, tendril_peak
        for i, t in enumerate(targets):
            if t.health <= 0 and not getattr(t, "_killed", False):
                t._killed = True
                kill_times.append((i, when))
                if tendrils < SURGE_MAX_TENDRILS and any(
                        t.health > 0 for t in targets):
                    tendrils += 1
                    tendril_peak = max(tendril_peak, tendrils)
                ammo = min(MAGAZINE, ammo + MAGAZINE * SURGE_REFILL)

    def cc_pct() -> float:
        # Sentient Surge adds +60% crit chance per Tendril, ADDITIVE with mods.
        riven_cc = (RIVEN_STATS[build.riven_stat]
                    if build.riven_stat == "Critical Chance" else 0.0)
        modded = BASE_CRIT_CHANCE * (
            1.0 + riven_cc + SURGE_PER_TENDRIL * tendrils)
        if build.arcane == ARCANE_ENERVATE:
            return enervate_afcc(modded * 100.0) / 100.0
        return modded

    def status_chance() -> float:
        riven_status = (RIVEN_STATS[build.riven_stat]
                        if build.riven_stat == "Status Chance" else 0.0)
        per_beam = BASE_STATUS * (
            1.0 + GALV_SHOT_STATUS + riven_status
            + SURGE_PER_TENDRIL * tendrils)
        return per_beam * build.multishot

    def fire_beam(idx: int, when: float, cf: float,
                  merged_status: float, seed_value: float,
                  flare: int) -> bool:
        t = targets[idx]
        types = _scaled_type_damage(build, flare)
        direct = sum(wiki_quantized_damage(v * build.multishot, seed_value)
                     for v in types.values())
        if t.overguard > 0:
            t.overguard -= direct * cf
            if t.overguard <= 0:
                t.broken = True
                t.overguard = 0.0
        else:
            armor = t.current_armor(when, build.heat_ramp_interval)
            t.health -= (direct * cf * (1.0 - armor_damage_reduction(armor))
                         * viral_magnetic_multiplier(t.viral_stacks(when)))
        guaranteed = int(math.floor(merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < merged_status - guaranteed else 0)
        heat = False
        for ptype in rng.choices(list(build.proc_weights),
                                 weights=list(build.proc_weights.values()),
                                 k=n_procs):
            if ptype == "HEAT":
                for proc in t.heat_procs:
                    proc.refreshed = when
                t.heat_procs.append(HeatProc(when, seed_value, cf, when))
                heat = True
            elif ptype == "VIRAL":
                t.viral_expiries.append(when + build.proc_duration)
                if len(t.viral_expiries) > 10:
                    t.viral_expiries.pop(0)
        return heat

    def room_dot(when: float) -> None:
        for t in targets:
            if t.health <= 0 or not t.heat_procs:
                continue
            t.prune(when, build.proc_duration)
            if not t.heat_procs:
                continue
            seeds = sum(p.seed * p.crit_factor for p in t.heat_procs)
            tick = heat_tick(seeds, elemental_bonus=build.heat_bonus)
            if t.overguard > 0:
                t.overguard -= tick
                if t.overguard <= 0:
                    t.broken = True
                    t.overguard = 0.0
            else:
                armor = t.current_armor(when, build.heat_ramp_interval)
                t.health -= (tick * (1.0 - armor_damage_reduction(armor))
                             * viral_magnetic_multiplier(t.viral_stacks(when)))

    while now < max_time and alive():
        flare_expiries = [t for t in flare_expiries if t > now]
        flare_stacks = len(flare_expiries)
        if ammo <= 0:
            reloads += 1
            reload_end = now + RELOAD_TIME
            while next_dot <= reload_end and alive():
                room_dot(next_dot)
                record_deaths(next_dot)
                next_dot += 1.0
            now = reload_end
            ammo = MAGAZINE
            tendrils = 0  # wiki: Tendrils and Surge bonuses reset on reload
            continue
        while next_dot <= now and alive():
            room_dot(next_dot)
            record_deaths(next_dot)
            next_dot += 1.0
        if not alive():
            break

        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START)
                   * beam_time / RAMP_TIME)
        cc = cc_pct()
        merged_status = status_chance()
        flare_bonus = (min(flare_stacks, FLARE_MAX_STACKS) * FLARE_PER_STACK
                       if build.arcane == ARCANE_FLARE else 0.0)
        seed_value = (BASE_TOTAL
                      * (build.base_damage_bracket + flare_bonus)
                      * build.multishot)

        def roll_cf() -> float:
            full = int(math.floor(cc))
            tier = full + (1 if rng.random() < (cc - full) else 0)
            return (1.0 + tier * (build.crit_multiplier - 1.0)) * ramp

        living = alive()
        primary = living[0]
        # Each beam instance can add at most one Flare stack.
        heat_instances = 0
        if fire_beam(primary, now, roll_cf(), merged_status, seed_value,
                     flare_stacks):
            heat_instances += 1
        # Tendrils beam other living targets.
        for idx in living[1:1 + tendrils]:
            if fire_beam(idx, now, roll_cf(), merged_status, seed_value,
                         flare_stacks):
                heat_instances += 1
        if build.arcane == ARCANE_FLARE:
            for _ in range(heat_instances):
                if flare_stacks >= FLARE_MAX_STACKS:
                    break
                flare_stacks += 1
                flare_expiries.append(now + FLARE_DURATION)
            flare_peak = max(flare_peak, flare_stacks)
        record_deaths(now)

        ammo -= AMMO_PER_TICK
        beam_time += dt
        now += dt

    return RoomResult(
        clear_time=now if not alive() else math.inf,
        n_enemies=n_enemies,
        kill_times=kill_times,
        tendril_peak=tendril_peak,
        reloads=reloads,
        flare_peak=flare_peak,
    )
