"""Tick-by-tick kill simulation for a Kuva Nukor build vs the SP150 Eximus dummy.

Weapon and mechanic references include the WARFRAME wiki (retrieved
2026-10-27), but the simulation makes approximations documented in
``docs/formula_audit.md``. Mixed-hit Overguard overflow and Magnetic break
interactions retain unverified assumptions. Selected inputs:

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
  (+80% status chance, +120% direct damage per status at 3 kill stacks).
  Their kill stacks are assumed precharged; Galvanized Shot counts live
  unique target statuses, including Kuva Nukor's hidden Microwave status.
* Secondary Enervate: +10% absolute crit chance per hit, reset after six
  Big Critical Hits. The wiki publishes the closed-form Average Final Crit
  Chance AFCC(x); we use it directly instead of re-simulating the arcane.
* Heat (Heat_Damage): consolidated DoT, 0.5 coefficient, armor strip ramping
  15/30/40/50% in total, with ramp intervals of 0.5 s scaled by
  status duration. New procs refresh every active Heat stack's duration
  but do not add extra armor-strip factors.
* Viral / Magnetic (Viral_Damage, Magnetic_Damage, Overguard):
  multiplier 2 + 0.25 * (stacks - 1), 10 stack cap (4.25x). Viral amplifies
  health only, Magnetic amplifies shields/Overguard only. Overguard takes no
  armor DR and has a neutral intrinsic table except Void (x1.5). The model
  additionally applies faction type modifiers, an unverified interpretation.
  On break, it approximates the dedicated Magnetic page's Electricity proc,
  including source modifiers and application-relative ticks; other pages
  describe the break differently and shields are not modeled.
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

# Preserve the old simulator-level import for external callers.
from modules.enemy_scaling import (
    enemy_armor_damage_reduction as armor_damage_reduction,  # noqa: F401
    steel_path_eximus_heavy_gunner,
)
from modules.constants import FACTION_MULTIPLIERS
from modules.damage_routing import RoutedDamage, route_enemy_hit, status_vulnerability
from modules.crit import quantize_crit_multiplier
from modules.trial_statistics import sample_percentile
from modules import status_damage
from modules.status_damage import (
    blast_stack_damage, heat_tick, magnetic_break_electric_tick, toxin_tick,
    wiki_quantized_damage,
)

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
BASE_RELOAD_TIME = 2.0
RELOAD_TIME = BASE_RELOAD_TIME / 1.6  # Pistol Elementalist: +60% reload speed
RAMP_TIME = 0.6
RAMP_START = 0.3                 # Nukor ramps 30% -> 100%, not the generic 20%
BLAST_FUSE_BASE = 1.5            # seconds per Blast stack, scaled by status duration
# Coefficients live in status_damage so every simulator shares one definition.
BLAST_MAX_STACKS = status_damage.BLAST_MAX_STACKS
BLAST_SINGLE_COEF = status_damage.BLAST_SINGLE_COEF  # 30% per stack, proc target
BLAST_RADIAL_COEF = status_damage.BLAST_RADIAL_COEF  # 300% per stack, 5 m radial

# --- Fixed mods in the build ----------------------------------------------

GALV_DIFFUSION_MS = 2.30          # +110% base, +4x30% on kill
GALV_SHOT_STATUS = 0.80
GALV_SHOT_DAMAGE = 1.20           # 3 stacks x 40% per status type
LETHAL_TORRENT_FR = 0.60
LETHAL_TORRENT_MS = 0.60
PRIMED_HEATED_CHARGE = 1.65
PRIMED_TARGET_CRACKER = 1.10  # max-rank +110% Critical Damage
PISTOL_ELEMENTALIST_SD = 0.90

# Average Pistol Riven, 3 positives + 1 curse (source/riven_stats_average_1_2)
RIVEN_VIRAL = 1.013
RIVEN_CRIT_DAMAGE = 1.013
RIVEN_STATUS_DURATION = 1.125
RIVEN_ZOOM_CURSE = -0.721         # gameplay-neutral

PROC_BASE_DURATION = 6.0
VIRAL_MAG_CAP = 10

# Last-slot candidates. Frostbite combines the free Heat and Cold into Blast,
# removing Heat procs and their armor strip; the other choices preserve Heat.
# "No 8th mod" is the seven-mod baseline used to quantify the slot's value.
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


def roll_multishot(rng: random.Random, expected: float) -> int:
    """Integer beams/projectiles: floor(multishot), plus its fractional roll."""
    whole = max(0, math.floor(expected))
    return whole + (1 if rng.random() < expected - whole else 0)


def galv_shot_scale(damage_bonus_at_one_status: float, status_count: int) -> float:
    """Scale an additive one-status build to the live status count."""
    base_bracket = 1.0 + damage_bonus_at_one_status
    live_bracket = base_bracket + GALV_SHOT_DAMAGE * (status_count - 1)
    return max(0.0, live_bracket) / base_bracket


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
    return status_vulnerability(stacks)


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
    # Wiki Critical Hit: the base multiplier is a quantized 12-bit value,
    # then relative Critical Damage bonuses scale it.
    crit_mult = quantize_crit_multiplier(BASE_CRIT_MULT) * (
        1.0 + PRIMED_TARGET_CRACKER + RIVEN_CRIT_DAMAGE
        + extra.get("crit_damage", 0.0))
    sd_mult = 1.0 + RIVEN_STATUS_DURATION

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
    next_tick: float | None = None

    def __post_init__(self) -> None:
        if self.next_tick is None:
            self.next_tick = self.start + 1.0


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
    """Shared Heat armor-strip fraction since the first active proc."""
    if age < ramp_interval:
        return 0.0
    if age < 2 * ramp_interval:
        return 0.15
    if age < 3 * ramp_interval:
        return 0.30
    if age < 4 * ramp_interval:
        return 0.40
    return 0.50


@dataclass(frozen=True)
class MagneticSource:
    """Bonuses of the source applying Magnetic (one source per target here)."""

    status_damage_bonus: float = 0.0
    faction_bonus: float = 0.0
    electricity_bonus: float = 0.0
    duration_multiplier: float = 1.0


@dataclass
class MagneticBreakProc:
    next_tick: float
    end: float
    tick_damage: float


class DummyTarget:
    """Eximus Heavy Gunner L150 Steel Path, with live status state."""

    def __init__(self, health: float, armor: float, overguard: float):
        self.max_health = health
        self.health = health
        self.max_armor = armor
        self.overguard_max = overguard
        self.overguard = overguard
        self.heat_procs: list[HeatProc] = []
        self._heat_ended_at: float | None = None
        self._next_heat_tick: float | None = None
        # Latest expiry per unique type, for Galvanized Shot/GunCO.
        self._status_expiries: dict[str, float] = {}
        self.toxin_procs: list[ToxinProc] = []
        self.blast_stacks: list[BlastProc] = []
        self.viral_expiries: list[float] = []
        self.puncture_expiries: list[float] = []
        self.mag_expiries: list[float] = []
        self.magnetic_source = MagneticSource()
        self.magnetic_break_procs: list[MagneticBreakProc] = []
        self.broken = False
        self.overguard_broken_at: float | None = None

    def record_status(self, kind: str, when: float, duration: float) -> None:
        self._status_expiries[kind] = max(
            self._status_expiries.get(kind, 0.0), when + duration)

    def clear_status(self, kind: str) -> None:
        self._status_expiries.pop(kind, None)

    def unique_status_count(self, now: float) -> int:
        self._status_expiries = {kind: end for kind, end in self._status_expiries.items()
                                 if end > now}
        return len(self._status_expiries)

    def viral_stacks(self, now: float) -> int:
        self.viral_expiries = [t for t in self.viral_expiries if t > now]
        return len(self.viral_expiries)

    def add_puncture(self, when: float, duration: float = 10.0,
                     max_stacks: int = 5) -> None:
        """Add a Puncture stack, refreshing the oldest at the normal cap.

        Puncture grants five flat critical-chance percentage points per stack
        against weapon hits. GunCO still counts Puncture as just one type.
        """
        if duration <= 0 or max_stacks < 1:
            raise ValueError("Puncture duration and maximum must be positive")
        self.puncture_stacks(when)
        # Keep application order: the Wiki says a capped stack replaces the
        # oldest application even when another stack expires sooner.
        self.puncture_expiries.append(when + duration)
        self.puncture_expiries = self.puncture_expiries[-max_stacks:]
        self._status_expiries["PUNC"] = max(self.puncture_expiries)

    def puncture_stacks(self, now: float) -> int:
        self.puncture_expiries = [t for t in self.puncture_expiries if t > now]
        return len(self.puncture_expiries)

    def mag_stacks(self, now: float) -> int:
        self.mag_expiries = [t for t in self.mag_expiries if t > now]
        return len(self.mag_expiries)

    def add_magnetic(self, when: float, duration: float,
                     source: MagneticSource = MagneticSource()) -> None:
        """Record a Magnetic stack and the applying source's modifiers.

        Each simulated fight currently uses one source; if several distinct
        sources are injected, the last-applied source is used as an explicit
        approximation for the whole break proc.
        """
        if duration <= 0:
            return
        self.mag_stacks(when)
        self.mag_expiries.append(when + duration)
        self.mag_expiries = self.mag_expiries[-VIRAL_MAG_CAP:]
        self.magnetic_source = source
        self.record_status("MAG", when, duration)

    def add_heat(self, when: float, seed: float, crit_factor: float,
                 duration: float) -> None:
        """Refresh the shared Heat group without restarting its pulse clock."""
        self.prune(when, duration)
        if not self.heat_procs:
            self._next_heat_tick = when + 1.0
            self._heat_ended_at = None
        for proc in self.heat_procs:
            proc.refreshed = when
        self.heat_procs.append(HeatProc(when, seed, crit_factor, when))

    def next_heat_tick(self, duration: float) -> float:
        """Next consolidated Heat pulse, anchored to the first application."""
        if not self.heat_procs:
            return math.inf
        if self._next_heat_tick is None:
            # Also support callers that pre-populate heat_procs directly.
            first = min(p.start for p in self.heat_procs) + 1.0
            self._next_heat_tick = first + max(0, math.ceil(-first))
        expiry = max(p.refreshed for p in self.heat_procs) + duration
        return self._next_heat_tick if self._next_heat_tick <= expiry else math.inf

    def consume_heat_tick(self, when: float, duration: float) -> list[HeatProc]:
        """Advance the group clock and return stacks eligible for this pulse."""
        if self.next_heat_tick(duration) != when:
            return []
        self.prune(when, duration)
        self._next_heat_tick = when + 1.0
        return [p for p in self.heat_procs if when >= p.start + 1.0]

    def next_toxin_tick(self, duration: float) -> float:
        """The next independent Toxin pulse, including one exactly at expiry."""
        return min((p.next_tick for p in self.toxin_procs
                    if p.next_tick <= p.start + duration), default=math.inf)

    def next_magnetic_electric_tick(self) -> float:
        return min((p.next_tick for p in self.magnetic_break_procs
                    if p.next_tick < p.end), default=math.inf)

    def process_magnetic_electric_until(
            self, when: float, heat_ramp_interval: float, *,
            faction_type_modifiers: dict[str, float] | None = None
    ) -> list[tuple[float, RoutedDamage]]:
        """Settle due break-proc ticks, at their own application-relative times."""
        events = []
        while self.health > 0 and self.next_magnetic_electric_tick() <= when:
            tick_at = self.next_magnetic_electric_tick()
            due = [p for p in self.magnetic_break_procs
                   if p.next_tick == tick_at and p.next_tick < p.end]
            # One target has one Overguard break in the current model. If
            # several are injected, same-time Electricity pulses consolidate.
            amount = sum(p.tick_damage for p in due)
            for proc in due:
                proc.next_tick += 1.0
            self.magnetic_break_procs = [p for p in self.magnetic_break_procs
                                         if p.next_tick < p.end]
            outcome = self.absorb({"ELEC": amount}, tick_at,
                                  heat_ramp_interval,
                                  faction_type_modifiers=faction_type_modifiers)
            events.append((tick_at, outcome))
        return events

    def current_armor(self, now: float, ramp_interval: float) -> float:
        if self.heat_procs:
            start = min(proc.start for proc in self.heat_procs)
            strip = _heat_strip_fraction(now - start, ramp_interval)
        elif self._heat_ended_at is not None:
            # After expiry Heat restores armor at 1.5s intervals (scaled by
            # duration), 50 -> 40 -> 30 -> 15 -> 0%.
            step = max(0, int((now - self._heat_ended_at) / (3 * ramp_interval)))
            strip = (0.50, 0.40, 0.30, 0.15, 0.0)[min(step, 4)]
        else:
            strip = 0.0
        return float(self.max_armor) * (1.0 - strip)

    def prune(self, now: float, proc_duration: float) -> None:
        old_heat = self.heat_procs
        self.heat_procs = [p for p in old_heat
                           if now <= p.refreshed + proc_duration]
        if old_heat and not self.heat_procs:
            self._heat_ended_at = max(p.refreshed for p in old_heat) + proc_duration
            self._next_heat_tick = None
        self.toxin_procs = [p for p in self.toxin_procs
                            if now <= p.start + proc_duration]

    def absorb(self, amount: float | dict[str, float], when: float,
               heat_ramp_interval: float, *,
               faction_type_modifiers: dict[str, float] | None = None,
               armor_bypass: bool = False,
               viral_stacks_override: int | None = None) -> RoutedDamage:
        """Apply one shieldless hit, allowing enemy Overguard overflow.

        Projectile multishot callers may snapshot Viral at shot start so that
        the same shot's newly applied Viral does not amplify its other hits.
        Other callers use the live stack count by default.
        """
        damage = {"OTHER": amount} if isinstance(amount, (int, float)) else amount
        result = route_enemy_hit(
            damage, overguard=self.overguard,
            armor=self.current_armor(when, heat_ramp_interval),
            magnetic_stacks=self.mag_stacks(when),
            viral_stacks=(self.viral_stacks(when) if viral_stacks_override is None
                          else viral_stacks_override),
            faction_type_modifiers=faction_type_modifiers,
            armor_bypass=armor_bypass,
        )
        self.overguard = max(0.0, self.overguard - result.overguard)
        self.health -= result.health
        if result.broke_overguard:
            self._break_overguard(when)
        return result

    def _break_overguard(self, when: float) -> None:
        self.broken = True
        self.overguard_broken_at = when
        self.overguard = 0.0
        stacks = self.mag_stacks(when)
        source = self.magnetic_source
        duration = max(0.0, 6.0 * source.duration_multiplier)
        if stacks and duration:
            tick = magnetic_break_electric_tick(
                self.overguard_max, stacks,
                status_damage_bonus=source.status_damage_bonus,
                faction_bonus=source.faction_bonus,
                electricity_bonus=source.electricity_bonus,
            )
            self.magnetic_break_procs.append(MagneticBreakProc(when, when + duration, tick))
            self.record_status("ELEC", when, duration)

    def blast_single_damage(self, status_damage_bonus: float) -> float:
        """Sum of per-stack 30% detonations against the proc target itself."""
        return sum(blast_stack_damage(p.seed, BLAST_SINGLE_COEF, floor=0.0,
                                      crit_factor=p.crit_factor,
                                      status_damage_bonus=status_damage_bonus)
                   for p in self.blast_stacks)

    def blast_radial_damage(self, status_damage_bonus: float) -> float:
        """Combined 5 m radial: 300% modded base per stack, crit snapshots."""
        return sum(blast_stack_damage(p.seed, BLAST_RADIAL_COEF, floor=0.0,
                                      crit_factor=p.crit_factor,
                                      status_damage_bonus=status_damage_bonus)
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

    faction_types = FACTION_MULTIPLIERS["Grineer"]
    magnetic_source = MagneticSource(
        status_damage_bonus=PISTOL_ELEMENTALIST_SD,
        duration_multiplier=build.status_duration_mult,
    )

    def process_magnetic(when: float) -> None:
        target.prune(when, build.proc_duration)
        for _, result in target.process_magnetic_electric_until(
                when, build.heat_ramp_interval,
                faction_type_modifiers=faction_types):
            buckets["break"] += result.health

    def route(damage: dict[str, float], when: float, category: str) -> None:
        target.prune(when, build.proc_duration)
        result = target.absorb(damage, when, build.heat_ramp_interval,
                               faction_type_modifiers=faction_types)
        buckets[category + "_og"] += result.overguard
        buckets[category + "_hp"] += result.health
        if result.broke_overguard:
            if trace:
                log.append(f"  t={when:6.2f}s Overguard broke "
                           f"(mag x{target.mag_stacks(when)})")
            # Electricity procs have their first pulse at application.
            process_magnetic(when)

    def dot_tick(when: float) -> None:
        # Consolidated Heat tick: one accumulator, per-proc crit snapshots.
        ready_heat = target.consume_heat_tick(when, build.proc_duration)
        if ready_heat:
            weighted_seeds = sum(p.seed * p.crit_factor for p in ready_heat)
            tick = heat_tick(
                weighted_seeds,
                elemental_bonus=build.heat_bonus,
                status_damage_bonus=PISTOL_ELEMENTALIST_SD,
                accumulator=True,
            )
            route({"HEAT": tick}, when, "dot")
    def toxin_tick_at(when: float) -> None:
        for proc in target.toxin_procs:
            if (proc.next_tick != when or target.health <= 0
                    or proc.next_tick > proc.start + build.proc_duration):
                continue
            proc.next_tick += 1.0
            tick = toxin_tick(
                proc.seed * proc.crit_factor,
                elemental_bonus=build.toxin_bonus,
                status_damage_bonus=PISTOL_ELEMENTALIST_SD,
                accumulator=True,
            )
            route({"TOXIN": tick}, when, "dot")

    def detonate_expired_blasts(when: float) -> None:
        """Normal 1.5 s fuses: single-target 30% per stack, no radial."""
        due = [p for p in target.blast_stacks if p.fuse_end <= when]
        for p in due:
            target.blast_stacks.remove(p)
            # Damage/Blast_Damage and Damage/Calculation: an expiring stack
            # deals max(1, 0.3 x H).
            amount = blast_stack_damage(
                p.seed, BLAST_SINGLE_COEF, crit_factor=p.crit_factor,
                status_damage_bonus=PISTOL_ELEMENTALIST_SD)
            route({"BLAST": amount}, when, "blast")
            if target.health <= 0:
                break

    def add_blast(when: float, cf: float, seed_value: float) -> None:
        nonlocal blast_count
        target.blast_stacks.append(
            BlastProc(when, when + build.blast_fuse,
                      seed_value, cf))
        blast_count += 1
        if len(target.blast_stacks) >= BLAST_MAX_STACKS:
            amount = target.blast_single_damage(PISTOL_ELEMENTALIST_SD)
            target.blast_stacks.clear()
            target.clear_status("BLAST")
            route({"BLAST": amount}, when, "blast")

    def advance_events(until: float) -> float | None:
        """Process timed effects in chronological order, returning death time."""
        while target.health > 0:
            next_heat = target.next_heat_tick(build.proc_duration)
            next_electric = target.next_magnetic_electric_tick()
            next_blast = min((p.fuse_end for p in target.blast_stacks),
                             default=math.inf)
            next_toxin = target.next_toxin_tick(build.proc_duration)
            event = min(next_heat, next_electric, next_blast, next_toxin)
            if event > until:
                break
            if next_electric <= min(next_heat, next_blast, next_toxin):
                process_magnetic(event)
            elif next_toxin <= min(next_heat, next_blast):
                toxin_tick_at(event)
            elif next_heat <= next_blast:
                dot_tick(event)
            else:
                detonate_expired_blasts(event)
            if target.health <= 0:
                return event
        return None

    while now < max_time and target.health > 0:
        # Timed procs and fuses continue through reload, up to the cutoff.
        if ammo <= 0:
            reloads += 1
            reload_end = now + RELOAD_TIME
            deadline = min(reload_end, max_time)
            death_time = advance_events(deadline)
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

        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START) * beam_time / RAMP_TIME)
        cf = crit_factor()

        # Beam instances hitting this target merge; sample the integer count
        # once so damage and status chance share the same multishot roll.
        beams = roll_multishot(rng, build.multishot)
        scale = galv_shot_scale(build.damage_bonus, target.unique_status_count(now))
        seed_value = build.modded_base_single * beams * scale
        direct = {name: wiki_quantized_damage(single * beams * scale, seed_value)
                  * ramp * cf for name, single in build.type_damage.items()} if seed_value > 0 else {}
        route(direct, now, "direct")
        if target.health <= 0:
            ammo -= AMMO_PER_TICK
            ticks += 1
            beam_time += dt
            break

        # Microwave is inflicted by the hit and benefits following hits only.
        target.record_status("MICROWAVE", now, math.inf)
        merged_status = build.status_per_beam * beams
        guaranteed = int(math.floor(merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < merged_status - guaranteed else 0)
        for ptype in roll_proc_types(n_procs):
            duration = (build.blast_fuse if ptype == "BLAST" else
                        (12.0 * build.status_duration_mult if ptype == "RAD" else build.proc_duration))
            target.record_status(ptype, now, duration)
            if ptype == "HEAT":
                target.add_heat(now, seed_value, cf, build.proc_duration)
                heat_count += 1
            elif ptype == "VIRAL":
                target.viral_expiries.append(now + build.proc_duration)
                if len(target.viral_expiries) > VIRAL_MAG_CAP:
                    target.viral_expiries.pop(0)
            elif ptype == "MAG":
                target.add_magnetic(now, build.proc_duration, magnetic_source)
            elif ptype == "TOXIN":
                target.toxin_procs.append(
                    ToxinProc(now, seed_value, cf))
            elif ptype == "BLAST":
                add_blast(now, cf, seed_value)
            if target.health <= 0:
                break
            # RAD proc (confusion) has no single-target DPS effect.

        ammo -= AMMO_PER_TICK
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
                f"viral={target.viral_stacks(now):2d} "
                f"mag={target.mag_stacks(now):2d}")

    # An attack interval can cross the cutoff while timed effects are due.
    if target.health > 0 and now >= max_time:
        death_time = advance_events(max_time)
        now = death_time if death_time is not None else max_time

    target.prune(now, build.proc_duration)
    ttk = now
    if target.health > 0:
        ttk = math.inf
    return TrialResult(
        ttk=ttk,
        overguard_break_time=(target.overguard_broken_at
                              if target.overguard_broken_at is not None
                              else 0.0 if target.overguard_max <= 0 else math.inf),
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
    beam_time = 0.0
    reloads = 0
    beam_ticks = 0
    radial_events = 0
    totals = {"direct": 0.0, "dot": 0.0, "radial": 0.0}
    kill_times: list[tuple[int, float]] = []
    log: list[str] = []

    faction_types = FACTION_MULTIPLIERS["Grineer"]
    magnetic_source = MagneticSource(
        status_damage_bonus=PISTOL_ELEMENTALIST_SD,
        duration_multiplier=build.status_duration_mult,
    )

    def process_magnetic(t: DummyTarget, when: float) -> None:
        t.prune(when, build.proc_duration)
        before = max(t.health, 0.0)
        t.process_magnetic_electric_until(
            when, build.heat_ramp_interval, faction_type_modifiers=faction_types)
        totals["dot"] += before - max(t.health, 0.0)

    def absorb_target(t: DummyTarget, damage: dict[str, float], when: float,
                      category: str) -> None:
        t.prune(when, build.proc_duration)
        before = max(t.health, 0.0) + max(t.overguard, 0.0)
        result = t.absorb(damage, when, build.heat_ramp_interval,
                          faction_type_modifiers=faction_types)
        totals[category] += before - max(t.health, 0.0) - max(t.overguard, 0.0)
        if result.broke_overguard:
            process_magnetic(t, when)

    def alive() -> list[int]:
        return [i for i, t in enumerate(targets) if t.health > 0]

    def record_deaths(when: float) -> None:
        # A radial can kill another target earlier in the list; settle the
        # chain until no unrecorded deaths remain.
        while True:
            pending = [(i, t) for i, t in enumerate(targets)
                       if t.health <= 0 and not getattr(t, "_killed", False)]
            if not pending:
                return
            for i, t in pending:
                t._killed = True
                kill_times.append((i, when))
                if t.blast_stacks:
                    radial(i, when, on_death=True)

    def radial(source_idx: int, when: float, *, on_death: bool = False) -> None:
        nonlocal radial_events
        source = targets[source_idx]
        amount = source.blast_radial_damage(PISTOL_ELEMENTALIST_SD)
        source.blast_stacks.clear()
        source.clear_status("BLAST")
        if amount <= 0:
            return
        radial_events += 1
        for j, t in enumerate(targets):
            if j == source_idx or t.health <= 0:
                continue
            absorb_target(t, {"BLAST": amount}, when, "radial")

    def crit_factor() -> float:
        full = int(math.floor(cc))
        tier = full + (1 if rng.random() < (cc - full) else 0)
        return 1.0 + tier * (build.crit_multiplier - 1.0)

    def roll_proc_types(k: int) -> list[str]:
        return rng.choices(list(build.proc_weights),
                           weights=list(build.proc_weights.values()), k=k)

    def apply_procs(idx: int, when: float, cf: float,
                    beams: int, seed_value: float) -> None:
        t = targets[idx]
        t.record_status("MICROWAVE", when, math.inf)
        merged_status = build.status_per_beam * beams
        guaranteed = int(math.floor(merged_status))
        n_procs = guaranteed + (1 if rng.random()
                                < merged_status - guaranteed else 0)
        for ptype in roll_proc_types(n_procs):
            duration = (build.blast_fuse if ptype == "BLAST" else
                        (12.0 * build.status_duration_mult if ptype == "RAD" else build.proc_duration))
            t.record_status(ptype, when, duration)
            if ptype == "HEAT":
                t.add_heat(when, seed_value, cf, build.proc_duration)
            elif ptype == "VIRAL":
                t.viral_expiries.append(when + build.proc_duration)
                if len(t.viral_expiries) > VIRAL_MAG_CAP:
                    t.viral_expiries.pop(0)
            elif ptype == "MAG":
                t.add_magnetic(when, build.proc_duration, magnetic_source)
            elif ptype == "TOXIN":
                t.toxin_procs.append(
                    ToxinProc(when, seed_value, cf))
            elif ptype == "BLAST":
                t.blast_stacks.append(
                    BlastProc(when, when + build.blast_fuse,
                              seed_value, cf))
                if len(t.blast_stacks) >= BLAST_MAX_STACKS:
                    # 10-stack early detonation: 30%/stack to itself plus a
                    # 300%/stack radial on every other target in the room.
                    single = t.blast_single_damage(PISTOL_ELEMENTALIST_SD)
                    absorb_target(t, {"BLAST": single}, when, "direct")
                    radial(idx, when)
            if t.health <= 0:
                break

    def room_dot_tick(when: float) -> None:
        for t in targets:
            if t.health <= 0:
                continue
            ready_heat = t.consume_heat_tick(when, build.proc_duration)
            if ready_heat:
                weighted_seeds = sum(p.seed * p.crit_factor for p in ready_heat)
                tick = heat_tick(weighted_seeds,
                                 elemental_bonus=build.heat_bonus,
                                 status_damage_bonus=PISTOL_ELEMENTALIST_SD,
                                 accumulator=True)
                absorb_target(t, {"HEAT": tick}, when, "dot")
    def room_toxin_tick(when: float) -> None:
        for t in targets:
            if t.health <= 0:
                continue
            for proc in t.toxin_procs:
                if (proc.next_tick != when or t.health <= 0
                        or proc.next_tick > proc.start + build.proc_duration):
                    continue
                proc.next_tick += 1.0
                tick = toxin_tick(proc.seed * proc.crit_factor,
                                  elemental_bonus=build.toxin_bonus,
                                  status_damage_bonus=PISTOL_ELEMENTALIST_SD,
                                  accumulator=True)
                absorb_target(t, {"TOXIN": tick}, when, "dot")

    def detonate_blasts(when: float) -> None:
        for t in targets:
            if t.health <= 0:
                continue
            for p in [p for p in t.blast_stacks if p.fuse_end <= when]:
                t.blast_stacks.remove(p)
                amount = blast_stack_damage(
                    p.seed, BLAST_SINGLE_COEF, crit_factor=p.crit_factor,
                    status_damage_bonus=PISTOL_ELEMENTALIST_SD)
                absorb_target(t, {"BLAST": amount}, when, "dot")
                if t.health <= 0:
                    break

    def advance_events(until: float) -> float | None:
        while alive():
            next_heat = min((t.next_heat_tick(build.proc_duration) for t in targets
                             if t.health > 0), default=math.inf)
            next_electric = min((t.next_magnetic_electric_tick() for t in targets
                                 if t.health > 0), default=math.inf)
            next_blast = min((p.fuse_end for t in targets if t.health > 0
                              for p in t.blast_stacks), default=math.inf)
            next_toxin = min((t.next_toxin_tick(build.proc_duration) for t in targets
                              if t.health > 0), default=math.inf)
            event = min(next_heat, next_electric, next_blast, next_toxin)
            if event > until:
                break
            if next_electric <= min(next_heat, next_blast, next_toxin):
                for t in targets:
                    if t.health > 0:
                        process_magnetic(t, event)
            elif next_toxin <= min(next_heat, next_blast):
                room_toxin_tick(event)
            elif next_heat <= next_blast:
                room_dot_tick(event)
            else:
                detonate_blasts(event)
            record_deaths(event)
            if not alive():
                return event
        return None

    while now < max_time and alive():
        if ammo <= 0:
            reloads += 1
            reload_end = now + RELOAD_TIME
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

        ramp = min(1.0, RAMP_START + (1.0 - RAMP_START) * beam_time / RAMP_TIME)
        cf = crit_factor()
        beams = roll_multishot(rng, build.multishot)
        living = alive()
        # Primary target at full damage, up to two chains at 50%.
        for rank, idx in enumerate(living[:1 + CHAIN_TARGETS]):
            mult = 1.0 if rank == 0 else CHAIN_DAMAGE_MULT
            t = targets[idx]
            if t.health <= 0:
                continue
            scale = galv_shot_scale(build.damage_bonus, t.unique_status_count(now))
            seed_value = build.modded_base_single * beams * scale
            damage = {name: wiki_quantized_damage(single * beams * scale, seed_value)
                      * ramp * mult * cf
                      for name, single in build.type_damage.items()} if seed_value > 0 else {}
            absorb_target(t, damage, now, "direct")
            if t.health > 0:
                apply_procs(idx, now, cf, beams, seed_value * mult)
        record_deaths(now)

        ammo -= AMMO_PER_TICK
        beam_ticks += 1
        beam_time += dt
        if not alive():
            break
        now += dt
        if trace and beam_ticks % max(1, int(1.0 / dt)) == 0:
            log.append(
                f"  t={now:6.2f}s alive={len(alive())}/{n_enemies} "
                f"radials={radial_events}")

    if alive() and now >= max_time:
        death_time = advance_events(max_time)
        now = death_time if death_time is not None else max_time

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
    """Summarize successful Monte Carlo trials for one last-mod candidate.

    ``target_factory`` must return a fresh :class:`DummyTarget` per trial.
    The summary includes attempted and timed-out counts; TTK statistics are
    conditional on observed kills within the simulation cutoff.
    """
    if trials < 1:
        raise ValueError("trials must be positive")
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
    return {
        "last_mod": last_mod,
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
        "reloads_mean": sum(reloads_list) / len(reloads_list) if reloads_list else math.nan,
        "final_armor_median": sample_percentile(armors, 0.5),
    }
