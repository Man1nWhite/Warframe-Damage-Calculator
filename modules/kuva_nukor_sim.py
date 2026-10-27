"""Tick-by-tick kill simulation for a Kuva Nukor build vs the SP150 Eximus dummy.

The weapon model and every mechanic come from the WARFRAME wiki (retrieved
2026-10-27):

* Kuva Nukor: 21 Radiation base, 7% crit chance, 5.0x crit multiplier,
  10 attacks/s, 50% status chance, magazine 77, reload 2.0 s, held beam
  (continuous hitscan). Magnetic progenitor bonus adds 60% of base damage as
  Magnetic (12.6).
* Continuous_Weapon / Kuva_Nukor: tick interval = 1 / modded fire rate; the
  Nukor ramps from 30% to 100% over 0.6 s on target and costs 0.5 ammo per
  tick; multishot beams merge into one instance whose damage AND status
  chance are the sums (single crit roll); its beam chains to up to two extra
  enemies within 9 m at 50% damage.
* Galvanized Diffusion (+230% multishot at 4 stacks) and Galvanized Shot
  (+80% status chance, +120% direct damage at 3 stacks) are taken at full
  stacks per the requested assumptions.
* Secondary Enervate: +10% absolute crit chance per hit, reset after six
  Big Critical Hits. The wiki publishes the closed-form Average Final Crit
  Chance AFCC(x); we use it directly instead of re-simulating the arcane.
* Heat (Heat_Damage): consolidated DoT, 0.5 coefficient, armor strip ramping
  15/30/40/50% per proc with ramp intervals of 0.5 s scaled by
  (1 + status duration); each proc is its own multiplicative factor on
  CURRENT armor; new procs refresh every active Heat stack's duration.
* Viral / Magnetic (Viral_Damage, Magnetic_Damage, Overguard):
  multiplier 2 + 0.25 * (stacks - 1), 10 stack cap (4.25x). Viral amplifies
  health only, Magnetic amplifies shields/Overguard only. Overguard takes no
  armor DR and is neutral to every type except Void (x1.5). On Overguard
  break, Magnetic deals 3% of max Overguard per stack (30% at 10 stacks) as
  Electricity damage.
* Blast (Blast_Damage): each stack fuses for 1.5 s x status duration, then
  hits its proc target for 30% of modded base. At 10 stacks or on target
  death all stacks detonate early into a 5 m, no-falloff radial dealing 300%
  of modded base per stack to surrounding enemies (the proc target itself is
  excluded from the radial). Crit snapshots sum per stack; Heat + Cold
  combine into Blast and remove the Heat element (and its armor strip).
* Riven averages use source/riven_stats_average_1_2.csv (Pistol, 3 positive
  stats + 1 curse, average grade, disposition 1.2). The repository's Riven
  tables intentionally omit combined-element tags; a Viral roll is assigned
  the same average as the single-element pistol stats (101.3%), which is how
  the wiki Riven tables list combined-element rolls.

The target is dummy A from modules.enemy_scaling: Eximus Heavy Gunner,
level 150, The Steel Path (1,716,837.41 health, 2,700 armor, 269,918.97
Overguard). Body shots, single target (no beam chaining), no faction mod.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from modules.enemy_scaling import (
    armor_damage_reduction,
    steel_path_eximus_heavy_gunner,
)
from modules.status_damage import heat_tick, toxin_tick, wiki_quantized_damage

# --- Weapon base -----------------------------------------------------------

BASE_RADIATION = 21.0
PROGENITOR_MAGNETIC = 0.60
BASE_MAGNETIC = BASE_RADIATION * PROGENITOR_MAGNETIC  # 12.6
BASE_TOTAL = BASE_RADIATION + BASE_MAGNETIC           # 33.6
BASE_CRIT_CHANCE = 0.07
BASE_CRIT_MULT = 5.0
BASE_FIRE_RATE = 10.0
BASE_STATUS = 0.50
MAGAZINE = 77
AMMO_PER_TICK = 0.5              # continuous-beam cost (Nukor characteristics)
RELOAD_TIME = 2.0
RAMP_TIME = 0.6
RAMP_START = 0.3                 # Nukor ramps 30% -> 100%, not the generic 20%
BLAST_FUSE_BASE = 1.5            # seconds per Blast stack, scaled by status duration
BLAST_MAX_STACKS = 10
BLAST_SINGLE_COEF = 0.3          # 30% of modded base per stack to the proc target
BLAST_RADIAL_COEF = 3.0          # 300% of modded base per stack in the 5 m explosion

# --- Fixed mods in the build ----------------------------------------------

GALV_DIFFUSION_MS = 2.30          # +110% base, +4x30% on kill
GALV_SHOT_STATUS = 0.80
GALV_SHOT_DAMAGE = 1.20           # 3 stacks x 40% per status type
LETHAL_TORRENT_FR = 0.60
LETHAL_TORRENT_MS = 0.60
PRIMED_HEATED_CHARGE = 1.65
PRIMED_TARGET_CRACKER = 1.20
PISTOL_ELEMENTALIST_SD = 0.90

# Average Pistol Riven, 3 positives + 1 curse (source/riven_stats_average_1_2)
RIVEN_VIRAL = 1.013
RIVEN_CRIT_DAMAGE = 1.013
RIVEN_STATUS_DURATION = 1.125
RIVEN_ZOOM_CURSE = -0.721         # gameplay-neutral

PROC_BASE_DURATION = 6.0
VIRAL_MAG_CAP = 10

# Last-slot candidates. Each preserves the free Heat element (any second
# base element would combine with Heat into Blast/Gas/Radiation and remove
# Heat procs and therefore the armor strip). "No 8th mod" is the seven-mod
# baseline used to quantify the slot's value.
LAST_MODS = {
    "No 8th mod": {},
    "Hornet Strike": {"damage": 2.20},
    "Primed Pistol Gambit": {"crit_chance": 1.87},
    "Hollow Point": {"crit_damage": 0.60, "damage": -0.15},
    "Scorch": {"heat": 0.60, "status": 0.60},
    "Frostbite": {"cold": 0.60, "status": 0.60},
    "Anemic Agility": {"fire_rate": 0.90, "damage": -0.15},
}
BASELINE_LAST_MOD = "Primed Pistol Gambit"


def enervate_afcc(modded_crit_chance_pct: float) -> float:
    """Average Final Crit Chance (percent) with Secondary Enervate.

    Piecewise regression published on the Secondary Enervate wiki page.
    ``modded_crit_chance_pct`` is the ordinary modded crit chance in percent
    (e.g. 7 for a bare Kuva Nukor); the returned value already includes it.
    """
    x = modded_crit_chance_pct
    if x < 110:
        return 102.45 + 0.5 * x
    if x < 140:
        return 128.8 - 0.0075 * x + 0.00244 * x * x
    if x < 150:
        return 77.5 + 0.7 * x
    if x < 160:
        return 70.0 + 0.75 * x
    if x < 170:
        return 62.0 + 0.8 * x
    if x < 180:
        return 53.5 + 0.85 * x
    if x < 190:
        return 44.5 + 0.9 * x
    if x < 200:
        return 35.0 + 0.95 * x
    return 25.0 + x


def viral_magnetic_multiplier(stacks: int) -> float:
    """2 + 0.25*(n-1), capped at 10 stacks (4.25x); 0 stacks -> 1.0."""
    if stacks <= 0:
        return 1.0
    n = min(stacks, VIRAL_MAG_CAP)
    return 2.0 + 0.25 * (n - 1)


@dataclass(frozen=True)
class NukorBuild:
    """Fully modded Kuva Nukor stats for one last-mod choice."""

    last_mod: str
    multishot: float
    fire_rate: float
    tick_interval: float
    status_per_beam: float
    merged_status: float
    crit_chance_per_beam_pct: float
    afcc_pct: float
    crit_multiplier: float
    status_duration_mult: float
    proc_duration: float
    heat_ramp_interval: float
    damage_bonus: float
    heat_bonus: float
    blast_bonus: float
    viral_bonus: float
    toxin_bonus: float
    blast_fuse: float
    # Per-beam damage distribution (before multishot/ramp/crit).
    type_damage: dict
    modded_base_single: float
    modded_base_merged: float
    proc_weights: dict

    def describe(self) -> str:
        return (
            f"{self.last_mod}: MS x{self.multishot:.2f}, FR {self.fire_rate:.1f}/s, "
            f"status {self.merged_status:.2f}/tick, AFCC {self.afcc_pct:.2f}%, "
            f"cm {self.crit_multiplier:.3f}, tick {self.tick_interval*1000:.1f} ms"
        )


def build_nukor(last_mod: str = BASELINE_LAST_MOD) -> NukorBuild:
    """Assemble modded stats for the fixed seven mods plus ``last_mod``."""
    if last_mod not in LAST_MODS:
        raise ValueError(f"unknown last mod: {last_mod!r}")
    extra = LAST_MODS[last_mod]

    multishot = 1.0 * (1.0 + GALV_DIFFUSION_MS + LETHAL_TORRENT_MS)
    fire_rate = BASE_FIRE_RATE * (1.0 + LETHAL_TORRENT_FR + extra.get("fire_rate", 0.0))
    damage_bonus = GALV_SHOT_DAMAGE + extra.get("damage", 0.0)
    cold_bonus = extra.get("cold", 0.0)
    heat_bonus = PRIMED_HEATED_CHARGE + extra.get("heat", 0.0)
    # Heat + Cold combine into Blast: the mod percentages add, the Heat
    # element (and therefore Heat procs/armor strip) disappears entirely.
    blast_bonus = heat_bonus + cold_bonus if cold_bonus else 0.0
    viral_bonus = RIVEN_VIRAL
    toxin_bonus = extra.get("toxin", 0.0)
    status_per_beam = BASE_STATUS * (
        1.0 + GALV_SHOT_STATUS + extra.get("status", 0.0))
    crit_chance = BASE_CRIT_CHANCE * (1.0 + extra.get("crit_chance", 0.0))
    crit_mult = BASE_CRIT_MULT * (
        1.0 + PRIMED_TARGET_CRACKER + RIVEN_CRIT_DAMAGE
        + extra.get("crit_damage", 0.0))
    sd_mult = 1.0 + PISTOL_ELEMENTALIST_SD + RIVEN_STATUS_DURATION

    modded_base_single = BASE_TOTAL * (1.0 + damage_bonus)
    modded_base_merged = modded_base_single * multishot
    type_damage = {
        "RAD": BASE_RADIATION * (1.0 + damage_bonus),
        "MAG": BASE_MAGNETIC * (1.0 + damage_bonus),
        "VIRAL": modded_base_single * viral_bonus,
    }
    if blast_bonus:
        type_damage["BLAST"] = modded_base_single * blast_bonus
    else:
        type_damage["HEAT"] = modded_base_single * heat_bonus
    if toxin_bonus:
        type_damage["TOXIN"] = modded_base_single * toxin_bonus
    single_total = sum(type_damage.values())
    proc_weights = {k: v / single_total for k, v in type_damage.items()}

    merged_status = status_per_beam * multishot
    return NukorBuild(
        last_mod=last_mod,
        multishot=multishot,
        fire_rate=fire_rate,
        tick_interval=1.0 / fire_rate,
        status_per_beam=status_per_beam,
        merged_status=merged_status,
        crit_chance_per_beam_pct=crit_chance * 100.0,
        afcc_pct=enervate_afcc(crit_chance * 100.0),
        crit_multiplier=crit_mult,
        status_duration_mult=sd_mult,
        proc_duration=PROC_BASE_DURATION * sd_mult,
        heat_ramp_interval=0.5 * sd_mult,
        damage_bonus=damage_bonus,
        heat_bonus=heat_bonus,
        blast_bonus=blast_bonus,
        viral_bonus=viral_bonus,
        toxin_bonus=toxin_bonus,
        blast_fuse=BLAST_FUSE_BASE * sd_mult,
        type_damage=type_damage,
        modded_base_single=modded_base_single,
        modded_base_merged=modded_base_merged,
        proc_weights=proc_weights,
    )


# --- Simulation -------------------------------------------------------------

@dataclass
class HeatProc:
    start: float                 # strip-age origin (never reset by refresh)
    seed: float                  # merged-tick modded base snapshot
    crit_factor: float           # crit multiplier snapshot at application
    refreshed: float             # last duration refresh (expiry clock)


@dataclass
class ToxinProc:
    start: float
    seed: float
    crit_factor: float


@dataclass
class BlastProc:
    start: float                  # application time
    fuse_end: float               # normal-expiry detonation time
    seed: float                   # merged-tick modded base snapshot
    crit_factor: float            # crit multiplier snapshot at application


@dataclass
class TrialResult:
    ttk: float
    overguard_break_time: float
    beam_time: float
    reloads: int
    ticks: int
    heat_procs: int
    final_armor: float
    blast_procs: int = 0
    blast_radials: int = 0
    direct_to_overguard: float = 0.0
    dot_to_overguard: float = 0.0
    direct_to_health: float = 0.0
    dot_to_health: float = 0.0
    blast_to_health: float = 0.0
    blast_to_overguard: float = 0.0
    break_electric: float = 0.0
    trace: list = field(default_factory=list)


def _heat_strip_fraction(age: float, ramp_interval: float) -> float:
    """Single Heat proc's current armor-strip fraction at age ``age``."""
    if age < ramp_interval:
        return 0.0
    if age < 2 * ramp_interval:
        return 0.15
    if age < 3 * ramp_interval:
        return 0.30
    if age < 4 * ramp_interval:
        return 0.40
    return 0.50


class DummyTarget:
    """Eximus Heavy Gunner L150 Steel Path, with live status state."""

    def __init__(self, health: float, armor: float, overguard: float):
        self.max_health = health
        self.health = health
        self.max_armor = armor
        self.overguard_max = overguard
        self.overguard = overguard
        self.heat_procs: list[HeatProc] = []
        self.toxin_procs: list[ToxinProc] = []
        self.blast_stacks: list[BlastProc] = []
        self.viral_expiries: list[float] = []
        self.mag_expiries: list[float] = []
        self.broken = False

    def viral_stacks(self, now: float) -> int:
        self.viral_expiries = [t for t in self.viral_expiries if t > now]
        return len(self.viral_expiries)

    def mag_stacks(self, now: float) -> int:
        self.mag_expiries = [t for t in self.mag_expiries if t > now]
        return len(self.mag_expiries)

    def current_armor(self, now: float, ramp_interval: float) -> float:
        armor = float(self.max_armor)
        for proc in self.heat_procs:
            armor *= 1.0 - _heat_strip_fraction(now - proc.start, ramp_interval)
        return armor

    def prune(self, now: float, proc_duration: float) -> None:
        self.heat_procs = [p for p in self.heat_procs
                           if now - p.refreshed < proc_duration]
        self.toxin_procs = [p for p in self.toxin_procs
                            if now - p.start < proc_duration]

    def absorb(self, amount: float, when: float,
               heat_ramp_interval: float) -> None:
        """Route one damage instance through Overguard then armored health."""
        if amount <= 0:
            return
        if self.overguard > 0:
            amount *= viral_magnetic_multiplier(self.mag_stacks(when))
            self.overguard -= amount
            if self.overguard <= 0:
                self._break_overguard(when, heat_ramp_interval)
            return
        armor = self.current_armor(when, heat_ramp_interval)
        amount *= (1.0 - armor_damage_reduction(armor))
        amount *= viral_magnetic_multiplier(self.viral_stacks(when))
        self.health -= amount

    def _break_overguard(self, when: float, heat_ramp_interval: float) -> None:
        self.broken = True
        stacks = self.mag_stacks(when)
        if stacks:
            electric = 0.03 * self.overguard_max * min(stacks, VIRAL_MAG_CAP)
            armor = self.current_armor(when, heat_ramp_interval)
            self.health -= electric * (1.0 - armor_damage_reduction(armor))
        self.overguard = 0.0

    def blast_single_damage(self, status_damage_bonus: float) -> float:
        """Sum of per-stack 30% detonations against the proc target itself."""
        return sum(BLAST_SINGLE_COEF * p.seed
                   * (1.0 + status_damage_bonus) * p.crit_factor
                   for p in self.blast_stacks)

    def blast_radial_damage(self, status_damage_bonus: float) -> float:
        """Combined 5 m radial: 300% modded base per stack, crit snapshots."""
        return sum(BLAST_RADIAL_COEF * p.seed
                   * (1.0 + status_damage_bonus) * p.crit_factor
                   for p in self.blast_stacks)


def simulate(build: NukorBuild,
             target: DummyTarget,
             *,
             seed: int = 1,
             trace: bool = False,
             trace_interval_s: float = 0.5,
             max_time: float = 600.0) -> TrialResult:
    """One Monte Carlo trial; returns time-to-kill and phase telemetry."""
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
    blast_count = 0
    log: list[str] = []
    buckets = {"direct_og": 0.0, "dot_og": 0.0, "direct_hp": 0.0,
               "dot_hp": 0.0, "break": 0.0, "blast_hp": 0.0,
               "blast_og": 0.0}

    def crit_factor() -> float:
        full = int(math.floor(cc))
        if rng.random() < (cc - full):
            tier = full + 1
        else:
            tier = full
        return 1.0 + tier * (build.crit_multiplier - 1.0)

    def roll_proc_types(k: int) -> list[str]:
        types = list(build.proc_weights)
        weights = list(build.proc_weights.values())
        return rng.choices(types, weights=weights, k=k)

    def apply_direct(amount: float, when: float) -> None:
        if target.overguard > 0:
            amount *= viral_magnetic_multiplier(target.mag_stacks(when))
            target.overguard -= amount
            buckets["direct_og"] += amount
            if target.overguard <= 0:
                break_overguard(when)
            return
        armor = target.current_armor(when, build.heat_ramp_interval)
        dr = armor_damage_reduction(armor)
        amount *= (1.0 - dr)
        amount *= viral_magnetic_multiplier(target.viral_stacks(when))
        target.health -= amount
        buckets["direct_hp"] += amount

    def break_overguard(when: float) -> None:
        target.broken = True
        stacks = target.mag_stacks(when)
        if stacks:
            electric = 0.03 * target.overguard_max * min(stacks, VIRAL_MAG_CAP)
            armor = target.current_armor(when, build.heat_ramp_interval)
            dealt = electric * (1.0 - armor_damage_reduction(armor))
            target.health -= dealt
            buckets["break"] += dealt
        target.overguard = 0.0
        if trace:
            log.append(f"  t={when:6.2f}s Overguard broke (mag x{stacks})")

    def dot_tick(when: float) -> None:
        target.prune(when, build.proc_duration)
        # Consolidated Heat tick: one accumulator, per-proc crit snapshots.
        if target.heat_procs:
            weighted_seeds = sum(p.seed * p.crit_factor
                                 for p in target.heat_procs)
            tick = heat_tick(
                weighted_seeds,
                elemental_bonus=build.heat_bonus,
                accumulator=True,
            )
            if target.overguard > 0:
                dealt = tick * viral_magnetic_multiplier(
                    target.mag_stacks(when))
                target.overguard -= dealt
                buckets["dot_og"] += dealt
                if target.overguard <= 0:
                    break_overguard(when)
            else:
                armor = target.current_armor(when, build.heat_ramp_interval)
                dealt = (
                    tick * (1.0 - armor_damage_reduction(armor))
                    * viral_magnetic_multiplier(target.viral_stacks(when)))
                target.health -= dealt
                buckets["dot_hp"] += dealt
        # Independent Toxin procs.
        for proc in list(target.toxin_procs):
            tick = toxin_tick(
                proc.seed * proc.crit_factor,
                elemental_bonus=build.toxin_bonus,
                accumulator=True,
            )
            if target.overguard > 0:
                dealt = tick * viral_magnetic_multiplier(
                    target.mag_stacks(when))
                target.overguard -= dealt
                buckets["dot_og"] += dealt
                if target.overguard <= 0:
                    break_overguard(when)
            else:
                armor = target.current_armor(when, build.heat_ramp_interval)
                dealt = (
                    tick * (1.0 - armor_damage_reduction(armor))
                    * viral_magnetic_multiplier(target.viral_stacks(when)))
                target.health -= dealt
                buckets["dot_hp"] += dealt

    def detonate_expired_blasts(when: float) -> None:
        """Normal 1.5 s fuses: single-target 30% per stack, no radial."""
        due = [p for p in target.blast_stacks if p.fuse_end <= when]
        if not due:
            return
        for p in due:
            target.blast_stacks.remove(p)
            amount = (BLAST_SINGLE_COEF * p.seed
                      * (1.0 + PISTOL_ELEMENTALIST_SD) * p.crit_factor)
            if target.overguard > 0:
                amount *= viral_magnetic_multiplier(target.mag_stacks(when))
                target.overguard -= amount
                buckets["blast_og"] += amount
                if target.overguard <= 0:
                    break_overguard(when)
            else:
                armor = target.current_armor(when, build.heat_ramp_interval)
                amount *= (1.0 - armor_damage_reduction(armor))
                amount *= viral_magnetic_multiplier(target.viral_stacks(when))
                target.health -= amount
                buckets["blast_hp"] += amount

    def add_blast(when: float, cf: float) -> None:
        nonlocal blast_count
        target.blast_stacks.append(
            BlastProc(when, when + build.blast_fuse,
                      build.modded_base_merged, cf))
        blast_count += 1
        if len(target.blast_stacks) >= BLAST_MAX_STACKS:
            # Early detonation: 10 x 30% to the proc target at once. The
            # 5 m radial has no other targets in the single-target model.
            amount = target.blast_single_damage(PISTOL_ELEMENTALIST_SD)
            target.blast_stacks.clear()
            if target.overguard > 0:
                amount *= viral_magnetic_multiplier(target.mag_stacks(when))
                target.overguard -= amount
                buckets["blast_og"] += amount
                if target.overguard <= 0:
                    break_overguard(when)
            else:
                armor = target.current_armor(when, build.heat_ramp_interval)
                amount *= (1.0 - armor_damage_reduction(armor))
                amount *= viral_magnetic_multiplier(target.viral_stacks(when))
                target.health -= amount
                buckets["blast_hp"] += amount

    og_break_time: Optional[float] = None
    while now < max_time and target.health > 0:
        # Reload: DoTs and Blast fuses keep running while trigger is released.
        if ammo <= 0:
            reloads += 1
            reload_end = now + RELOAD_TIME
            while next_dot <= reload_end and target.health > 0:
                dot_tick(next_dot)
                detonate_expired_blasts(next_dot)
                next_dot += 1.0
            detonate_expired_blasts(reload_end)
            now = reload_end
            ammo = MAGAZINE
            continue

        # Due DoT seconds and Blast fuses before this beam tick.
        while next_dot <= now and target.health > 0:
            dot_tick(next_dot)
            detonate_expired_blasts(next_dot)
            next_dot += 1.0
        detonate_expired_blasts(now)
        if target.health <= 0:
            break

        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START) * beam_time / RAMP_TIME)
        cf = crit_factor()

        # Direct damage of the merged tick (1/32 quantization per type).
        direct = 0.0
        for name, single in build.type_damage.items():
            merged = single * build.multishot
            q = wiki_quantized_damage(merged, build.modded_base_merged)
            direct += q
        apply_direct(direct * ramp * cf, now)

        # Status rolls: guaranteed procs plus one fractional roll.
        guaranteed = int(math.floor(build.merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < build.merged_status - guaranteed else 0)
        for ptype in roll_proc_types(n_procs):
            if ptype == "HEAT":
                # A new Heat proc refreshes every active stack's duration,
                # but not their armor-strip ramp age.
                for proc in target.heat_procs:
                    proc.refreshed = now
                target.heat_procs.append(
                    HeatProc(now, build.modded_base_merged, cf, now))
                heat_count += 1
            elif ptype == "VIRAL":
                target.viral_expiries.append(now + build.proc_duration)
                if len(target.viral_expiries) > VIRAL_MAG_CAP:
                    target.viral_expiries.pop(0)
            elif ptype == "MAG":
                target.mag_expiries.append(now + build.proc_duration)
                if len(target.mag_expiries) > VIRAL_MAG_CAP:
                    target.mag_expiries.pop(0)
            elif ptype == "TOXIN":
                target.toxin_procs.append(
                    ToxinProc(now, build.modded_base_merged, cf))
            elif ptype == "BLAST":
                add_blast(now, cf)
            # RAD proc (confusion) has no single-target DPS effect.

        ammo -= AMMO_PER_TICK
        ticks += 1
        beam_time += dt
        now += dt
        if trace and ticks % max(1, int(trace_interval_s / dt)) == 0:
            armor = target.current_armor(now, build.heat_ramp_interval)
            log.append(
                f"  t={now:6.2f}s og={max(target.overguard,0):12.0f} "
                f"hp={max(target.health,0):12.0f} armor={armor:8.1f} "
                f"heat={len(target.heat_procs):3d} "
                f"viral={target.viral_stacks(now):2d} "
                f"mag={target.mag_stacks(now):2d}")
        if target.broken and og_break_time is None:
            og_break_time = now

    ttk = now
    if target.health > 0:
        ttk = math.inf
    return TrialResult(
        ttk=ttk,
        overguard_break_time=og_break_time if og_break_time is not None else ttk,
        beam_time=beam_time,
        reloads=reloads,
        ticks=ticks,
        heat_procs=heat_count,
        blast_procs=blast_count,
        final_armor=target.current_armor(ttk if math.isfinite(ttk) else now,
                                         build.heat_ramp_interval),
        direct_to_overguard=buckets["direct_og"],
        dot_to_overguard=buckets["dot_og"],
        direct_to_health=buckets["direct_hp"],
        dot_to_health=buckets["dot_hp"],
        blast_to_health=buckets["blast_hp"],
        blast_to_overguard=buckets["blast_og"],
        break_electric=buckets["break"],
        trace=log,
    )


def steel_path_dummy_factory() -> "DummyTarget":
    """Fresh dummy A (Eximus Heavy Gunner L150 Steel Path) for one trial."""
    dummy = steel_path_eximus_heavy_gunner(150)
    return DummyTarget(dummy.health, dummy.armor, dummy.overguard)


# --- Room clear (beam chaining + Blast radial AoE) -------------------------

CHAIN_TARGETS = 2            # Kuva Nukor chains to up to two extra enemies
CHAIN_DAMAGE_MULT = 0.5      # each chain deals 50% of the main beam
CHAIN_RANGE_M = 9.0
BLAST_RADIUS_M = 5.0         # Blast radial radius, no falloff


@dataclass
class RoomResult:
    clear_time: float
    n_enemies: int
    kill_times: list
    beam_ticks: int
    reloads: int
    radial_events: int
    radial_damage_total: float
    direct_damage_total: float
    dot_damage_total: float
    trace: list = field(default_factory=list)


def simulate_room(build: NukorBuild,
                  n_enemies: int,
                  *,
                  seed: int = 1,
                  factory=steel_path_dummy_factory,
                  trace: bool = False,
                  max_time: float = 600.0) -> RoomResult:
    """Clear a dense pack (all targets within chain and 5 m Blast radius)."""
    rng = random.Random(seed)
    dt = build.tick_interval
    cc = build.afcc_pct / 100.0
    targets = [factory() for _ in range(n_enemies)]
    ammo = MAGAZINE
    now = 0.0
    next_dot = 1.0
    beam_time = 0.0
    reloads = 0
    beam_ticks = 0
    radial_events = 0
    totals = {"direct": 0.0, "dot": 0.0, "radial": 0.0}
    kill_times: list[tuple[int, float]] = []
    log: list[str] = []

    def alive() -> list[int]:
        return [i for i, t in enumerate(targets) if t.health > 0]

    def record_deaths(when: float) -> None:
        for i, t in enumerate(targets):
            if t.health <= 0 and not getattr(t, "_killed", False):
                t._killed = True
                kill_times.append((i, when))
                # On-kill Blast detonation: remaining stacks explode radially.
                if t.blast_stacks:
                    radial(i, when, on_death=True)

    def radial(source_idx: int, when: float, *, on_death: bool = False) -> None:
        nonlocal radial_events
        source = targets[source_idx]
        amount = source.blast_radial_damage(PISTOL_ELEMENTALIST_SD)
        source.blast_stacks.clear()
        if amount <= 0:
            return
        radial_events += 1
        for j, t in enumerate(targets):
            if j == source_idx or t.health <= 0:
                continue
            before = t.health + max(t.overguard, 0.0)
            t.absorb(amount, when, build.heat_ramp_interval)
            totals["radial"] += before - max(t.health, 0.0) - max(t.overguard, 0.0)

    def crit_factor() -> float:
        full = int(math.floor(cc))
        tier = full + (1 if rng.random() < (cc - full) else 0)
        return 1.0 + tier * (build.crit_multiplier - 1.0)

    def roll_proc_types(k: int) -> list[str]:
        return rng.choices(list(build.proc_weights),
                           weights=list(build.proc_weights.values()), k=k)

    def apply_procs(idx: int, when: float, cf: float) -> None:
        t = targets[idx]
        guaranteed = int(math.floor(build.merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < build.merged_status - guaranteed else 0)
        for ptype in roll_proc_types(n_procs):
            if ptype == "HEAT":
                for proc in t.heat_procs:
                    proc.refreshed = when
                t.heat_procs.append(
                    HeatProc(when, build.modded_base_merged, cf, when))
            elif ptype == "VIRAL":
                t.viral_expiries.append(when + build.proc_duration)
                if len(t.viral_expiries) > VIRAL_MAG_CAP:
                    t.viral_expiries.pop(0)
            elif ptype == "MAG":
                t.mag_expiries.append(when + build.proc_duration)
                if len(t.mag_expiries) > VIRAL_MAG_CAP:
                    t.mag_expiries.pop(0)
            elif ptype == "TOXIN":
                t.toxin_procs.append(
                    ToxinProc(when, build.modded_base_merged, cf))
            elif ptype == "BLAST":
                t.blast_stacks.append(
                    BlastProc(when, when + build.blast_fuse,
                              build.modded_base_merged, cf))
                if len(t.blast_stacks) >= BLAST_MAX_STACKS:
                    # 10-stack early detonation: 30%/stack to itself plus a
                    # 300%/stack radial on every other target in the room.
                    single = t.blast_single_damage(PISTOL_ELEMENTALIST_SD)
                    before = t.health + max(t.overguard, 0.0)
                    t.absorb(single, when, build.heat_ramp_interval)
                    totals["direct"] += (
                        before - max(t.health, 0.0) - max(t.overguard, 0.0))
                    radial(idx, when)

    def room_dot_tick(when: float) -> None:
        for idx, t in enumerate(targets):
            if t.health <= 0:
                continue
            t.prune(when, build.proc_duration)
            if t.heat_procs:
                weighted_seeds = sum(p.seed * p.crit_factor
                                     for p in t.heat_procs)
                tick = heat_tick(weighted_seeds,
                                 elemental_bonus=build.heat_bonus,
                                 accumulator=True)
                before = t.health + max(t.overguard, 0.0)
                t.absorb(tick, when, build.heat_ramp_interval)
                totals["dot"] += (
                    before - max(t.health, 0.0) - max(t.overguard, 0.0))
            for proc in list(t.toxin_procs):
                tick = toxin_tick(proc.seed * proc.crit_factor,
                                  elemental_bonus=build.toxin_bonus,
                                  accumulator=True)
                before = t.health + max(t.overguard, 0.0)
                t.absorb(tick, when, build.heat_ramp_interval)
                totals["dot"] += (
                    before - max(t.health, 0.0) - max(t.overguard, 0.0))
            due = [p for p in t.blast_stacks if p.fuse_end <= when]
            for p in due:
                t.blast_stacks.remove(p)
                amount = (BLAST_SINGLE_COEF * p.seed
                          * (1.0 + PISTOL_ELEMENTALIST_SD) * p.crit_factor)
                before = t.health + max(t.overguard, 0.0)
                t.absorb(amount, when, build.heat_ramp_interval)
                totals["dot"] += (
                    before - max(t.health, 0.0) - max(t.overguard, 0.0))

    quantized_total = sum(
        wiki_quantized_damage(single * build.multishot,
                              build.modded_base_merged)
        for single in build.type_damage.values())

    while now < max_time and alive():
        if ammo <= 0:
            reloads += 1
            reload_end = now + RELOAD_TIME
            while next_dot <= reload_end and alive():
                room_dot_tick(next_dot)
                record_deaths(next_dot)
                next_dot += 1.0
            now = reload_end
            ammo = MAGAZINE
            continue

        while next_dot <= now and alive():
            room_dot_tick(next_dot)
            record_deaths(next_dot)
            next_dot += 1.0
        if not alive():
            break

        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START) * beam_time / RAMP_TIME)
        cf = crit_factor()
        living = alive()
        # Primary target at full damage, up to two chains at 50%.
        for rank, idx in enumerate(living[:1 + CHAIN_TARGETS]):
            mult = 1.0 if rank == 0 else CHAIN_DAMAGE_MULT
            t = targets[idx]
            before = t.health + max(t.overguard, 0.0)
            t.absorb(quantized_total * ramp * mult * cf, now,
                     build.heat_ramp_interval)
            totals["direct"] += (
                before - max(t.health, 0.0) - max(t.overguard, 0.0))
            apply_procs(idx, now, cf)
        record_deaths(now)

        ammo -= AMMO_PER_TICK
        beam_ticks += 1
        beam_time += dt
        now += dt
        if trace and beam_ticks % max(1, int(1.0 / dt)) == 0:
            log.append(
                f"  t={now:6.2f}s alive={len(alive())}/{n_enemies} "
                f"radials={radial_events}")

    return RoomResult(
        clear_time=now if not alive() else math.inf,
        n_enemies=n_enemies,
        kill_times=kill_times,
        beam_ticks=beam_ticks,
        reloads=reloads,
        radial_events=radial_events,
        radial_damage_total=totals["radial"],
        direct_damage_total=totals["direct"],
        dot_damage_total=totals["dot"],
        trace=log,
    )


def run_trials(last_mod: str,
               target_factory=steel_path_dummy_factory,
               trials: int = 300,
               base_seed: int = 20261027) -> dict:
    """Monte Carlo TTK distribution for one last-mod candidate.

    ``target_factory`` must return a fresh :class:`DummyTarget` per trial.
    """
    build = build_nukor(last_mod)
    ttks, og_times, reloads_list, armors = [], [], [], []
    for i in range(trials):
        result = simulate(build, target_factory(), seed=base_seed + i)
        if not math.isfinite(result.ttk):
            continue
        ttks.append(result.ttk)
        og_times.append(result.overguard_break_time)
        reloads_list.append(result.reloads)
        armors.append(result.final_armor)
    ttks.sort()
    og_times.sort()

    def pct(sorted_vals: list[float], p: float) -> float:
        idx = min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1))))
        return sorted_vals[idx]

    return {
        "last_mod": last_mod,
        "build": build,
        "trials": len(ttks),
        "ttk_mean": sum(ttks) / len(ttks),
        "ttk_median": pct(ttks, 0.5),
        "ttk_p90": pct(ttks, 0.9),
        "ttk_min": ttks[0],
        "ttk_max": ttks[-1],
        "overguard_median": pct(og_times, 0.5),
        "reloads_mean": sum(reloads_list) / len(reloads_list),
        "final_armor_median": pct(armors, 0.5),
    }
