"""Ocucor simulation: arcane choice (Enervate vs Cascadia Flare) and Riven stat.

WARNING: Experimental simulation, not a validated TTK or build-ranking model.
See docs/formula_audit.md for routing assumptions and status approximations.

By default the Riven has +Viral / -Zoom plus one selectable positive stat
(average-grade Pistol Riven, 2 positives + 1 curse; values from
source/riven_stats_average_1_2.csv). Explicit Multishot, Viral and reload
bonuses can also model other Riven layouts. Two arcanes are compared:

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
  the default hitscan rule applies -- at three kill stacks its +120% per
  live status type ADDS to the ordinary +damage pool (the same bracket as
  Cascadia Flare and a Damage Riven).
* Sentient Surge (Ocucor augment): +60% crit chance and +60% status chance
  per active Tendril, additive, up to 4 Tendrils (+240%); kills refill 20%
  of the magazine. A lone target can still receive the stat bonus from
  tendrils carried over from earlier kills, but tendrils do not damage the
  primary target. In a room they can attack other targets independently.
* Puncture adds five absolute critical-chance percentage points per live
  stack. Enervate uses the Wiki's long-run single-hit AFCC approximation;
  it does not validate the different multi-target charge/reset behavior.

Target is the SP150 Eximus Heavy Gunner dummy (1,716,837.41 health,
2,700 armor / 90% DR, 269,918.97 Overguard). Heat consolidation/armor strip,
Viral stacks, Overguard routing and 1/32 quantization reuse the tested
primitives from modules.kuva_nukor_sim.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from modules.constants import FACTION_MULTIPLIERS
# Preserve historically importable simulator helpers for external callers.
from modules.enemy_scaling import enemy_armor_damage_reduction as armor_damage_reduction  # noqa: F401
from modules.trial_statistics import sample_percentile
from modules.kuva_nukor_sim import (
    DummyTarget,
    HeatProc as HeatProc,
    enervate_afcc,
    heat_tick,
    roll_multishot,
    steel_path_dummy_factory,
    viral_magnetic_multiplier as viral_magnetic_multiplier,
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
BASE_RELOAD_TIME = 1.6
RELOAD_TIME = BASE_RELOAD_TIME / 1.6  # +60% reload speed from Elementalist
RAMP_TIME = 0.6
RAMP_START = 0.2

# --- Mods -------------------------------------------------------------------

GALV_DIFFUSION_MS = 2.30
GALV_SHOT_STATUS = 0.80
GALV_SHOT_CO = 1.20           # additive CO bracket (default hitscan rule)
LETHAL_TORRENT_FR = 0.60
LETHAL_TORRENT_MS = 0.60
PRIMED_HEATED_CHARGE = 1.65
PRIMED_TARGET_CRACKER = 1.10  # max-rank +110% Critical Damage
PISTOL_ELEMENTALIST_SD = 0.90
PISTOL_ELEMENTALIST_RELOAD_SPEED = 0.60
RIVEN_VIRAL = 1.337           # 2 positives + 1 curse, average grade
RIVEN_ZOOM_CURSE = -0.476

# Average Riven values for the selectable second positive (2 pos + 1 curse).
RIVEN_STATS = {
    "Critical Damage": 1.337,
    "Critical Chance": 2.227,
    "Damage": 3.261,
    "Fire Rate": 1.109,
    "Status Chance": 1.337,
    "Multishot": 1.778,
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
    reload_time: float = RELOAD_TIME

    def describe(self) -> str:
        return (
            f"{self.arcane} / Riven {self.riven_stat}: MS x{self.multishot:.2f}, "
            f"FR {self.fire_rate:.2f}/s, merged status {self.merged_status:.2f}, "
            f"cc {self.crit_chance_pct:.2f}% (AFCC {self.afcc_pct:.2f}%), "
            f"cm {self.crit_multiplier:.3f}"
        )


def build_ocucor(arcane: str = ARCANE_ENERVATE,
                 riven_stat: str = "Critical Damage", *,
                 riven_multishot_bonus: float | None = None,
                 riven_viral_bonus: float = RIVEN_VIRAL,
                 riven_reload_speed_bonus: float = 0.0) -> OcucorBuild:
    """Build the fixed mods with optional explicit positive Riven values.

    The optional values are fractional bonuses (1.347 means +134.7%), not
    total multipliers. They allow comparing Riven layouts without using the
    two-positive defaults for a three-positive roll.
    """
    if arcane not in (ARCANE_ENERVATE, ARCANE_FLARE):
        raise ValueError(f"unknown arcane: {arcane!r}")
    if riven_stat not in RIVEN_STATS:
        raise ValueError(f"unknown riven stat: {riven_stat!r}")
    if riven_multishot_bonus is not None and riven_stat != "Multishot":
        raise ValueError("a Multishot override requires the Multishot Riven")
    for name, value in (("Viral", riven_viral_bonus),
                        ("reload speed", riven_reload_speed_bonus),
                        ("Multishot", riven_multishot_bonus)):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError(f"{name} Riven bonus must be finite and non-negative")
    riven = RIVEN_STATS[riven_stat]
    if riven_multishot_bonus is not None:
        riven = riven_multishot_bonus

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
    sd_mult = 1.0  # Elementalist changes status damage, not duration

    modded_base_single = BASE_TOTAL * bracket
    modded_base_merged = modded_base_single * multishot
    type_damage = {
        "RAD": BASE_RADIATION * bracket,
        "PUNC": BASE_PUNCTURE * bracket,
        "HEAT": modded_base_single * PRIMED_HEATED_CHARGE,
        "VIRAL": modded_base_single * riven_viral_bonus,
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
        reload_time=BASE_RELOAD_TIME / (
            1.0 + PISTOL_ELEMENTALIST_RELOAD_SPEED + riven_reload_speed_bonus),
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
    final_tendrils: int = 0
    final_puncture_stacks: int = 0
    final_flare_stacks: int = 0
    flare_cap_time: float | None = None
    final_viral_stacks: int = 0
    viral_cap_time: float | None = None


def _scaled_type_damage(build: OcucorBuild, flare_stacks: int,
                        status_count: int = 1) -> dict:
    # Build values are normalized at one status. Change only the CO portion.
    bracket = build.base_damage_bracket + GALV_SHOT_CO * (status_count - 1)
    if build.arcane == ARCANE_FLARE:
        bracket += min(flare_stacks, FLARE_MAX_STACKS) * FLARE_PER_STACK
    scale = bracket / build.base_damage_bracket
    return {k: v * scale for k, v in build.type_damage.items()}


def effective_crit_chance_pct(build: OcucorBuild, tendrils: int,
                              puncture_stacks: int, *,
                              enervate_extra_pct: float = 0.0) -> float:
    """Crit chance for a weapon hit, with live Surge and Puncture bonuses.

    Enervate uses the Wiki's long-run, single-hit AFCC. ``enervate_extra_pct``
    is an explicitly hypothetical sensitivity for additional multi-target
    charging, not a measurement or an implementation of the reset cycle.
    """
    ordinary = (build.crit_chance_pct
                + 100.0 * BASE_CRIT_CHANCE * SURGE_PER_TENDRIL * tendrils
                + 5.0 * puncture_stacks)
    if build.arcane == ARCANE_ENERVATE:
        return enervate_afcc(ordinary) + enervate_extra_pct
    return ordinary


def effective_status_per_beam(build: OcucorBuild, tendrils: int) -> float:
    return build.status_per_beam + BASE_STATUS * SURGE_PER_TENDRIL * tendrils


def _validate_start(build: OcucorBuild, starting_tendrils: int,
                    starting_flare_stacks: int, enervate_extra_pct: float,
                    heat_seed_mode: str, puncture_cap: int) -> None:
    if not isinstance(starting_tendrils, int) or not 0 <= starting_tendrils <= 4:
        raise ValueError("starting tendrils must be an integer from 0 to 4")
    if (not isinstance(starting_flare_stacks, int)
            or not 0 <= starting_flare_stacks <= FLARE_MAX_STACKS):
        raise ValueError("starting Flare stacks must be an integer from 0 to 40")
    if starting_flare_stacks and build.arcane != ARCANE_FLARE:
        raise ValueError("only Cascadia Flare can start with Flare stacks")
    if not math.isfinite(enervate_extra_pct) or enervate_extra_pct < 0:
        raise ValueError("extra Enervate crit chance must be finite and non-negative")
    if enervate_extra_pct and build.arcane != ARCANE_ENERVATE:
        raise ValueError("extra Enervate crit chance requires Enervate")
    if heat_seed_mode not in {"per_hit", "first_hit"}:
        raise ValueError("Heat seed mode must be 'per_hit' or 'first_hit'")
    if not isinstance(puncture_cap, int) or not 1 <= puncture_cap <= 5:
        raise ValueError("Puncture cap must be an integer from 1 to 5")


def _add_heat(target: DummyTarget, when: float, seed: float, crit_factor: float,
              duration: float, mode: str) -> None:
    """Add a Heat stack; first-whole-seed inheritance is a sensitivity only."""
    target.prune(when, duration)
    if mode == "first_hit" and target.heat_procs:
        seed = target.heat_procs[0].seed
        crit_factor = target.heat_procs[0].crit_factor
    target.add_heat(when, seed, crit_factor, duration)


def _beam_progress_after_pause(progress: float, pause: float) -> float:
    # After a 0.8 s delay, assume the full ramp falls linearly over 2 s.
    decay = max(0.0, pause - 0.8) * RAMP_TIME / 2.0
    return max(0.0, min(RAMP_TIME, progress) - decay)


def simulate(build: OcucorBuild,
             target: DummyTarget,
             *,
             seed: int = 1,
             trace: bool = False,
             trace_interval_s: float = 0.5,
             max_time: float = 600.0,
             starting_tendrils: int = 0,
             starting_flare_stacks: int = 0,
             full_beam_ramp: bool = False,
             enervate_extra_pct: float = 0.0,
             heat_seed_mode: str = "per_hit",
             ramp_heat_seed: bool = False,
             puncture_cap: int = 5) -> OcucorTrial:
    """Single target; retained tendrils grant stats but do not hit the target.

    Any starting tendrils/Flare stacks are idealized carryover from previous
    combat. Galvanized kill stacks are always full, but target statuses start
    empty unless the caller deliberately primes the target.
    """
    _validate_start(build, starting_tendrils, starting_flare_stacks,
                    enervate_extra_pct, heat_seed_mode, puncture_cap)
    rng = random.Random(seed)
    dt = build.tick_interval
    ammo = MAGAZINE
    now = 0.0
    beam_time = RAMP_TIME if full_beam_ramp else 0.0
    tendrils = starting_tendrils
    reloads = 0
    ticks = 0
    heat_count = 0
    flare_stacks = starting_flare_stacks
    flare_peak = flare_stacks
    flare_cap_time = 0.0 if flare_stacks == FLARE_MAX_STACKS else None
    flare_expiries: list[float] = [FLARE_DURATION] * flare_stacks
    viral_cap_time = 0.0 if target.viral_stacks(0.0) >= 10 else None
    log: list[str] = []
    buckets = {"direct_og": 0.0, "dot_og": 0.0, "direct_hp": 0.0,
               "dot_hp": 0.0, "break": 0.0}

    def crit_factor(when: float) -> float:
        cc = effective_crit_chance_pct(
            build, tendrils, target.puncture_stacks(when),
            enervate_extra_pct=enervate_extra_pct) / 100.0
        full = int(math.floor(cc))
        tier = full + (1 if rng.random() < (cc - full) else 0)
        return 1.0 + tier * (build.crit_multiplier - 1.0)

    def roll(k: int) -> list[str]:
        return rng.choices(list(build.proc_weights),
                           weights=list(build.proc_weights.values()), k=k)

    faction_types = FACTION_MULTIPLIERS["Grineer"]

    def process_magnetic(when: float) -> None:
        target.prune(when, build.proc_duration)
        for _, result in target.process_magnetic_electric_until(
                when, build.heat_ramp_interval,
                faction_type_modifiers=faction_types):
            buckets["break"] += result.health

    def route(damage: dict[str, float], when: float, is_dot: bool) -> None:
        target.prune(when, build.proc_duration)
        result = target.absorb(damage, when, build.heat_ramp_interval,
                               faction_type_modifiers=faction_types)
        buckets["dot_og" if is_dot else "direct_og"] += result.overguard
        buckets["dot_hp" if is_dot else "direct_hp"] += result.health
        if result.broke_overguard:
            if trace:
                log.append(f"  t={when:6.2f}s Overguard broke")
            process_magnetic(when)

    def dot_tick(when: float) -> None:
        ready_heat = target.consume_heat_tick(when, build.proc_duration)
        if not ready_heat:
            return
        weighted_seeds = sum(p.seed * p.crit_factor for p in ready_heat)
        tick = heat_tick(weighted_seeds,
                         elemental_bonus=build.heat_bonus,
                         status_damage_bonus=PISTOL_ELEMENTALIST_SD,
                         accumulator=True)
        route({"HEAT": tick}, when, is_dot=True)

    def advance_events(until: float) -> float | None:
        while target.health > 0:
            next_heat = target.next_heat_tick(build.proc_duration)
            next_electric = target.next_magnetic_electric_tick()
            event = min(next_heat, next_electric)
            if event > until:
                break
            if next_electric <= next_heat:
                process_magnetic(event)
            else:
                dot_tick(event)
            if target.health <= 0:
                return event
        return None

    while now < max_time and target.health > 0:
        # Expire Flare stacks.
        flare_expiries = [t for t in flare_expiries if t > now]
        flare_stacks = len(flare_expiries)

        if ammo <= 0:
            reloads += 1
            tendrils = 0  # They vanish as reload begins, including if cancelled.
            reload_end = now + build.reload_time
            death_time = advance_events(min(reload_end, max_time))
            if death_time is not None:
                now = death_time
                break
            if reload_end >= max_time:
                now = max_time
                break
            now = reload_end
            ammo = MAGAZINE
            beam_time = _beam_progress_after_pause(beam_time, build.reload_time)
            continue

        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break

        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START) * beam_time / RAMP_TIME)
        beams = roll_multishot(rng, build.multishot)
        cf = crit_factor(now)
        status_count = target.unique_status_count(now)
        types = _scaled_type_damage(build, flare_stacks, status_count)
        bracket = (build.base_damage_bracket + GALV_SHOT_CO * (status_count - 1)
                   + (min(flare_stacks, FLARE_MAX_STACKS) * FLARE_PER_STACK
                      if build.arcane == ARCANE_FLARE else 0.0))
        modded_base_merged = BASE_TOTAL * bracket * beams
        direct = {name: wiki_quantized_damage(single * beams, modded_base_merged)
                  * ramp * cf for name, single in types.items()} if modded_base_merged > 0 else {}
        route(direct, now, is_dot=False)
        killed_by_direct = target.health <= 0

        merged_status = effective_status_per_beam(build, tendrils) * beams
        guaranteed = int(math.floor(merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < merged_status - guaranteed else 0)
        heat_this_tick = False
        for ptype in roll(n_procs):
            if ptype == "HEAT":
                heat_this_tick = True
                heat_count += 1
            # Fatal Heat applications can still charge Flare, but no status
            # needs to be retained on a dead target.
            if killed_by_direct:
                continue
            if ptype == "PUNC":
                target.add_puncture(now, 10.0 * build.status_duration_mult,
                                    max_stacks=puncture_cap)
                continue
            duration = (12.0 * build.status_duration_mult if ptype == "RAD"
                        else build.proc_duration)
            target.record_status(ptype, now, duration)
            if ptype == "HEAT":
                _add_heat(target, now, modded_base_merged,
                          cf * (ramp if ramp_heat_seed else 1.0),
                          build.proc_duration, heat_seed_mode)
            elif ptype == "VIRAL":
                target.viral_expiries.append(now + build.proc_duration)
                if len(target.viral_expiries) > 10:
                    target.viral_expiries.pop(0)
                if len(target.viral_expiries) == 10 and viral_cap_time is None:
                    viral_cap_time = now

        # Flare: at most one stack per damage instance (merged beam tick).
        if build.arcane == ARCANE_FLARE and heat_this_tick:
            flare_stacks = min(flare_stacks + 1, FLARE_MAX_STACKS)
            flare_peak = max(flare_peak, flare_stacks)
            if flare_stacks == FLARE_MAX_STACKS and flare_cap_time is None:
                flare_cap_time = now
            # All stacks share one refreshed 10-second expiration timer.
            flare_expiries = [now + FLARE_DURATION] * flare_stacks

        ammo -= AMMO_PER_TICK
        if ammo <= 0:
            tendrils = 0
        ticks += 1
        beam_time += dt
        if target.health <= 0:
            break
        now += dt
        if trace and ticks % max(1, int(trace_interval_s / dt)) == 0:
            armor = target.current_armor(now, build.heat_ramp_interval)
            log.append(
                f"  t={now:6.2f}s og={max(target.overguard,0):12.0f} "
                f"hp={max(target.health,0):12.0f} armor={armor:8.1f} "
                f"heat={len(target.heat_procs):3d} "
                f"viral={target.viral_stacks(now):2d} flare={flare_stacks:2d}")

    if target.health > 0 and now >= max_time:
        death_time = advance_events(max_time)
        now = death_time if death_time is not None else max_time

    target.prune(now, build.proc_duration)
    ttk = now if target.health <= 0 else math.inf
    return OcucorTrial(
        ttk=ttk,
        overguard_break_time=(target.overguard_broken_at
                              if target.overguard_broken_at is not None
                              else 0.0 if target.overguard_max <= 0 else math.inf),
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
        final_tendrils=tendrils,
        final_puncture_stacks=target.puncture_stacks(now),
        final_flare_stacks=sum(expiry > now for expiry in flare_expiries),
        flare_cap_time=flare_cap_time,
        final_viral_stacks=target.viral_stacks(now),
        viral_cap_time=viral_cap_time,
    )


def run_trials(arcane: str,
               riven_stat: str,
               trials: int = 300,
               base_seed: int = 20261027,
               factory=steel_path_dummy_factory) -> dict:
    """Summarize observed kills and report attempted and timed-out trials."""
    if trials < 1:
        raise ValueError("trials must be positive")
    build = build_ocucor(arcane, riven_stat)
    ttks, og_times, flares, armors = [], [], [], []
    for i in range(trials):
        result = simulate(build, factory(), seed=base_seed + i)
        if math.isfinite(result.ttk):
            ttks.append(result.ttk)
            og_times.append(result.overguard_break_time)
            flares.append(result.flare_stacks_peak)
            armors.append(result.final_armor)
    return {
        "arcane": arcane,
        "riven_stat": riven_stat,
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
        "flare_peak_median": sample_percentile(flares, 0.5),
        "armor_median": sample_percentile(armors, 0.5),
    }


# --- Illustrative room simulation ------------------------------------------

@dataclass
class RoomResult:
    clear_time: float
    n_enemies: int
    kill_times: list
    tendril_peak: int
    reloads: int
    flare_peak: int = 0
    trace: list = field(default_factory=list)
    flare_cap_time: float | None = None
    average_tendrils_per_tick: float = 0.0
    primary_direct_kills: int = 0
    tendril_direct_kills: int = 0
    status_kills: int = 0


def simulate_room(arcane: str,
                  riven_stat: str,
                  n_enemies: int,
                  *,
                  seed: int = 1,
                  factory=steel_path_dummy_factory,
                  max_time: float = 600.0,
                  starting_tendrils: int = 0,
                  starting_flare_stacks: int = 0,
                  enervate_extra_pct: float = 0.0,
                  heat_seed_mode: str = "per_hit",
                  ramp_heat_seed: bool = False,
                  puncture_cap: int = 5,
                  build_override: OcucorBuild | None = None) -> RoomResult:
    """Stationary, densely grouped room, *not* a validated gameplay ranking.

    Every new target is in range, visible and immediately acquired. The main
    beam and up to four tendrils attack different living targets, independently
    rolling crit/status; a per-target ramp begins cold. Primary direct kills and
    any status kills can create tendrils, but direct tendril kills cannot.
    Sentient Surge refills ammunition from an assumed sufficient reserve.

    Crits use the single-hit Enervate AFCC regression even when multiple beams
    hit at once. Actual multi-target charging/reset is not simulated. The
    optional extra flat crit percentage is a hypothetical sensitivity at four
    extra beams, linearly scaled to the number actually hitting other targets;
    it is not a prediction of the real effect. There is no movement, cover,
    acquisition delay, other weapons or abilities. ``build_override`` permits
    explicit Riven values and must match the named arcane and Riven stat.
    """
    if not isinstance(n_enemies, int) or n_enemies < 1:
        raise ValueError("n_enemies must be a positive integer")
    build = build_override if build_override is not None else build_ocucor(arcane, riven_stat)
    if build.arcane != arcane or build.riven_stat != riven_stat:
        raise ValueError("build override must match the named arcane and Riven stat")
    _validate_start(build, starting_tendrils, starting_flare_stacks,
                    enervate_extra_pct, heat_seed_mode, puncture_cap)
    rng = random.Random(seed)
    targets = [factory() for _ in range(n_enemies)]
    ammo = MAGAZINE
    now = 0.0
    reloads = 0
    tendrils = starting_tendrils
    tendril_peak = tendrils
    kill_times: list[tuple[int, float]] = []
    killed: set[int] = set()
    kill_counts = {"primary_direct": 0, "tendril_direct": 0, "status": 0}
    dt = build.tick_interval
    flare_stacks = starting_flare_stacks
    flare_peak = flare_stacks
    flare_cap_time = 0.0 if flare_stacks == FLARE_MAX_STACKS else None
    flare_expiries: list[float] = [FLARE_DURATION] * flare_stacks
    # Beam ramp is per target, not a global free warm-up on a fresh target.
    beam_progress = [0.0] * n_enemies
    last_hit: list[float | None] = [None] * n_enemies
    ticks = 0
    tendril_tick_sum = 0
    faction_types = FACTION_MULTIPLIERS["Grineer"]

    def alive() -> list[int]:
        return [i for i, t in enumerate(targets) if t.health > 0]

    def record_death(idx: int, when: float, cause: str) -> None:
        nonlocal tendrils, ammo, tendril_peak
        if idx in killed or targets[idx].health > 0:
            return
        killed.add(idx)
        kill_times.append((idx, when))
        kill_counts[cause] += 1
        if (cause != "tendril_direct" and tendrils < SURGE_MAX_TENDRILS
                and any(t.health > 0 for t in targets)):
            tendrils += 1
            tendril_peak = max(tendril_peak, tendrils)
        ammo = min(MAGAZINE, ammo + MAGAZINE * SURGE_REFILL)

    def process_magnetic(idx: int, when: float) -> None:
        t = targets[idx]
        t.prune(when, build.proc_duration)
        t.process_magnetic_electric_until(
            when, build.heat_ramp_interval, faction_type_modifiers=faction_types)

    def route(idx: int, damage: dict[str, float], when: float) -> None:
        t = targets[idx]
        t.prune(when, build.proc_duration)
        result = t.absorb(damage, when, build.heat_ramp_interval,
                          faction_type_modifiers=faction_types)
        if result.broke_overguard and t.health > 0:
            process_magnetic(idx, when)
            record_death(idx, when, "status")

    def next_ramp(idx: int, when: float) -> float:
        progress = beam_progress[idx]
        if last_hit[idx] is not None:
            progress = _beam_progress_after_pause(progress, when - last_hit[idx])
        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START) * progress / RAMP_TIME)
        beam_progress[idx] = min(RAMP_TIME, progress + dt)
        last_hit[idx] = when
        return ramp

    def fire_beam(idx: int, when: float, shot_tendrils: int,
                  beams: int, flare: int, extra_cc: float, *, primary: bool) -> bool:
        t = targets[idx]
        if t.health <= 0:
            return False
        cc = effective_crit_chance_pct(
            build, shot_tendrils, t.puncture_stacks(when),
            enervate_extra_pct=extra_cc) / 100.0
        full = int(math.floor(cc))
        tier = full + (1 if rng.random() < cc - full else 0)
        cf = 1.0 + tier * (build.crit_multiplier - 1.0)
        ramp = next_ramp(idx, when)
        status_count = t.unique_status_count(when)
        types = _scaled_type_damage(build, flare, status_count)
        bracket = (build.base_damage_bracket + GALV_SHOT_CO * (status_count - 1)
                   + (min(flare, FLARE_MAX_STACKS) * FLARE_PER_STACK
                      if build.arcane == ARCANE_FLARE else 0.0))
        seed_value = BASE_TOTAL * bracket * beams
        direct = {name: wiki_quantized_damage(v * beams, seed_value) * ramp * cf
                  for name, v in types.items()} if seed_value > 0 else {}
        route(idx, direct, when)
        killed_by_direct = t.health <= 0
        if killed_by_direct:
            record_death(idx, when, "primary_direct" if primary else "tendril_direct")

        merged_status = effective_status_per_beam(build, shot_tendrils) * beams
        guaranteed = int(math.floor(merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < merged_status - guaranteed else 0)
        heat = False
        for ptype in rng.choices(list(build.proc_weights),
                                 weights=list(build.proc_weights.values()),
                                 k=n_procs):
            if ptype == "HEAT":
                heat = True  # Fatal applications also count for Flare.
            if killed_by_direct:
                continue
            if ptype == "PUNC":
                t.add_puncture(when, 10.0 * build.status_duration_mult,
                               max_stacks=puncture_cap)
                continue
            duration = (12.0 * build.status_duration_mult if ptype == "RAD"
                        else build.proc_duration)
            t.record_status(ptype, when, duration)
            if ptype == "HEAT":
                _add_heat(t, when, seed_value,
                          cf * (ramp if ramp_heat_seed else 1.0),
                          build.proc_duration, heat_seed_mode)
            elif ptype == "VIRAL":
                t.viral_expiries.append(when + build.proc_duration)
                if len(t.viral_expiries) > 10:
                    t.viral_expiries.pop(0)
        return heat

    def room_dot(when: float) -> None:
        for idx, t in enumerate(targets):
            if t.health <= 0:
                continue
            ready_heat = t.consume_heat_tick(when, build.proc_duration)
            if not ready_heat:
                continue
            seeds = sum(p.seed * p.crit_factor for p in ready_heat)
            tick = heat_tick(seeds, elemental_bonus=build.heat_bonus,
                             status_damage_bonus=PISTOL_ELEMENTALIST_SD,
                             accumulator=True)
            route(idx, {"HEAT": tick}, when)
            record_death(idx, when, "status")

    def advance_events(until: float) -> float | None:
        while alive():
            next_heat = min((t.next_heat_tick(build.proc_duration) for t in targets
                             if t.health > 0), default=math.inf)
            next_electric = min((t.next_magnetic_electric_tick() for t in targets
                                 if t.health > 0), default=math.inf)
            event = min(next_heat, next_electric)
            if event > until:
                break
            if next_electric <= next_heat:
                for idx, t in enumerate(targets):
                    if t.health > 0:
                        process_magnetic(idx, event)
                        record_death(idx, event, "status")
            else:
                room_dot(event)
            if not alive():
                return event
        return None

    while now < max_time and alive():
        flare_expiries = [expiry for expiry in flare_expiries if expiry > now]
        flare_stacks = len(flare_expiries)
        if ammo <= 0:
            reloads += 1
            tendrils = 0
            reload_end = now + build.reload_time
            death_time = advance_events(min(reload_end, max_time))
            if death_time is not None:
                now = death_time
                break
            if reload_end >= max_time:
                now = max_time
                break
            now = reload_end
            ammo = MAGAZINE
            continue
        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break

        living = alive()
        shot_tendrils = tendrils
        tendril_tick_sum += shot_tendrils
        ticks += 1
        ammo -= AMMO_PER_TICK
        if ammo <= 0:
            tendrils = 0  # Emptying the magazine immediately removes them.
        beams = roll_multishot(rng, build.multishot)
        # An intentionally hypothetical multi-target Enervate sensitivity:
        # the requested shift is largest at four beams and zero with no extra
        # target. Linear interpolation is not a model of the actual reset.
        secondary_beams = min(shot_tendrils, len(living) - 1)
        extra_cc = enervate_extra_pct * secondary_beams / SURGE_MAX_TENDRILS
        # All beams in a volley use the same pre-volley Flare level and
        # tendril count, and one crit/status roll per separate target.
        heat_instances = int(fire_beam(living[0], now, shot_tendrils, beams,
                                       flare_stacks, extra_cc, primary=True))
        for idx in living[1:1 + shot_tendrils]:
            heat_instances += int(fire_beam(idx, now, shot_tendrils, beams,
                                            flare_stacks, extra_cc, primary=False))
        if build.arcane == ARCANE_FLARE and heat_instances:
            flare_stacks = min(flare_stacks + heat_instances, FLARE_MAX_STACKS)
            flare_expiries = [now + FLARE_DURATION] * flare_stacks
            flare_peak = max(flare_peak, flare_stacks)
            if flare_stacks == FLARE_MAX_STACKS and flare_cap_time is None:
                flare_cap_time = now
        if not alive():
            break
        now += dt

    if alive() and now >= max_time:
        death_time = advance_events(max_time)
        now = death_time if death_time is not None else max_time

    return RoomResult(
        clear_time=now if not alive() else math.inf,
        n_enemies=n_enemies,
        kill_times=kill_times,
        tendril_peak=tendril_peak,
        reloads=reloads,
        flare_peak=flare_peak,
        flare_cap_time=flare_cap_time,
        average_tendrils_per_tick=tendril_tick_sum / ticks if ticks else 0.0,
        primary_direct_kills=kill_counts["primary_direct"],
        tendril_direct_kills=kill_counts["tendril_direct"],
        status_kills=kill_counts["status"],
    )
