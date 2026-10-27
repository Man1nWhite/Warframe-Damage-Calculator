"""Alternox Prime Riven choice simulation (normal-fire, primary slot).

The user's build is fixed at eight mods plus a Riven:

    Serration, Galvanized Aptitude, Galvanized Chamber, Rifle Elementalist,
    Primed Cryo Rounds, Vital Sense, Critical Delay, + Riven.

The Riven already carries a **Blast** positive; this module ranks the
other two positives. A combined element on a Riven is a SPLICED trait:
since Update 44.1 (2026-10-07) the Riven Splicer workbench merges two
base-element traits into one combined trait (Heat + Cold -> Blast), one
spliced trait per Riven, and the wiki gives Combined Elemental Damage the
same value range as ordinary Elemental Damage (retrieved 2026-10-27).
Being pre-combined, the trait never participates in further Arsenal
combines, so the Primed Cryo Cold is still free to pair with a Riven
Toxin positive. Riven averages come from
``source/riven_stats_average_1_2.csv`` (``LotusRifleRandomModRare``, the
1.20-disposition normalized table, 3 positives + 1 curse column; the 2026
Riven Disposition retirement normalized every weapon to 1.20). The CSV
only carries base attributes, so combined-element names resolve to the
base-element average (identical wiki range; see
``COMBINED_ELEMENT_STATS``).

Weapon model (wiki Alternox Prime, retrieved 2026-10-27), normal attack:

* 75 pure Electricity per projectile, RoF 5.33/s, crit chance 20%,
  crit multiplier 2.2x, status chance 40%, magazine 42, reload 1.8 s,
  projectile weapon with infinite body punch-through.
* Critical Delay: +200% crit chance, -20% fire rate. Vital Sense: +120%
  crit damage. Serration: +165% base damage. Primed Cryo Rounds: +165%
  Cold. Rifle Elementalist: x1.9 Status Damage (final multiplicative
  term, +0.6 punch-through irrelevant here).
* Galvanized Aptitude: static +80% status chance; on kill +40% DIRECT
  damage per status type on the target, stacking twice (per-type cap
  +80%, 20 s). It is a Condition-Overload-type ("GunCO") bonus and never
  buffs AoE/radial hits.
* Galvanized Chamber: +80% multishot plus +30% per kill stack, five
  stacks -> 1 + 0.8 + 1.5 = 3.3 projectiles per trigger pull. Multishot
  pellets are sequential hits, so later pellets already see statuses
  applied by earlier pellets of the same pull.
* GunCO stacking mode is resolved through modules.condition_overload and
  the curated ``source/gunco_mechanic.json`` catalog: the Alternox Prime
  Normal Attack is an explicit ``multiply`` rule (projectile behavior,
  wiki-measured, "not intended" but live), i.e. the CO bonus is its own
  multiplier outside the Serration bracket. Electric and Blast procs
  snapshot the CO-multiplied Modded Base Damage of their source hit.
* Element combining with the fixed Cold: a Riven Toxin positive becomes
  Viral, Heat becomes a second Blast source, Electricity becomes
  Magnetic; with no elemental positive the Cold stays standalone. The
  innate Electricity never combines. There is only one Cold source, so
  pairs containing two of Toxin/Heat/Electricity are rejected
  (``combine_elements`` raises): only one combine is possible and the
  other element would stay standalone, a different build not covered by
  the candidate grid.
* Status models: Electricity (Tesla) ticks 6 times over 6 s at 0.5x MBD
  per tick times the Electricity elemental bonus; Blast (Detonate) fuses
  for 1.5 s then hits the proc target for 0.3x MBD per stack, and 10
  stacks detonate immediately at 3.0x MBD on the target (the 5 m radial
  is excluded - single dummy, and radii never receive GunCO); Viral
  stacks give 2 + 0.25*(n-1) health damage, capped at 10 stacks / 4.25x.
* Simulation conventions shared with the kuva_nukor/akarius sims: one
  independent status roll per pellet, and a status chance above 100%
  (Status Chance Riven builds reach ~153%) grants floor(sc) guaranteed
  procs plus one fractional roll; the 1/32 wiki quantization acts on
  pre-crit per-type damage with crit applied afterwards; DoT ticks and
  Blast fuses are evaluated on the integer-second clock (a 1.5 s fuse
  therefore resolves at the next integer second), and proc damage
  bypasses quantization using full-precision seeds. Rifle Elementalist
  is +90% Status Damage only (wiki, retrieved 2026-10-27) - it never
  extends proc duration, which stays at the 6 s base.
"""
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from modules.condition_overload import apply_co, resolve_co_behavior
from modules.enemy_scaling import armor_damage_reduction, steel_path_heavy_gunner
from modules.kuva_nukor_sim import (
    BlastProc,
    DummyTarget,
    viral_magnetic_multiplier,
    wiki_quantized_damage,
)
from modules.status_damage import ELEMENTAL_DOT_COEFFICIENT

# --- Weapon base stats (wiki Alternox Prime, Normal Attack) -----------------

WEAPON = "Alternox Prime"
NORMAL_ATTACK = "Normal Attack"
ELEC_BASE = 75.0
BASE_FIRE_RATE = 5.33
BASE_CRIT_CHANCE = 0.20
BASE_CRIT_MULT = 2.20
BASE_STATUS = 0.40
MAGAZINE = 42
RELOAD_TIME = 1.80

# --- Fixed mods -------------------------------------------------------------

SERRATION = 1.65
PRIMED_CRYO_COLD = 1.65
VITAL_SENSE_CD = 1.20
CRIT_DELAY_CC = 2.00
CRIT_DELAY_ROF_PENALTY = 0.20
GALV_APTITUDE_STATUS = 0.80
APTITUDE_PER_STATUS = 0.40       # +40% direct damage per status type, per stack
APTITUDE_STACK_CAP = 2          # on-kill stacks
APTITUDE_PER_TYPE_CAP = 0.80    # max +80% per unique status type
CHAMBER_BASE_MS = 0.80
CHAMBER_PER_STACK = 0.30
CHAMBER_STACK_CAP = 5
RIFLE_ELEMENTALIST_SD = 0.90    # x1.9 Status Damage
BLAST_FUSE = 1.5                # seconds until a Blast stack detonates
BLAST_SINGLE_COEF = 0.30
BLAST_STACK_CAP = 10
ELEC_TICK_COEF = ELEMENTAL_DOT_COEFFICIENT   # 0.5
ELEC_PROC_TICKS = 6
VIRAL_CAP = 10
PROC_DURATION = 6.0

# Riven stat keys (names match the CSV stat_name column where applicable).
R_DAMAGE = "Damage"
R_CC = "Critical Chance"
R_CD = "Critical Damage"
R_MS = "Multishot"
R_FIRE_RATE = "Fire Rate / Attack Speed"
R_STATUS = "Status Chance"
R_TOXIN = "Toxin"
R_HEAT = "Heat"
R_ELEC = "Electricity"
R_BLAST = "Blast"

# The two-positive candidates evaluated alongside the fixed Blast roll.
RIVEN_PAIR_OPTIONS = (
    (R_DAMAGE, R_TOXIN),
    (R_FIRE_RATE, R_TOXIN),
    (R_CD, R_TOXIN),
    (R_CC, R_TOXIN),
    (R_MS, R_TOXIN),
    (R_STATUS, R_TOXIN),
    (R_DAMAGE, R_FIRE_RATE),
    (R_CD, R_FIRE_RATE),
    (R_CC, R_CD),
    (R_DAMAGE, R_CD),
    (R_CC, R_FIRE_RATE),
    (R_MS, R_FIRE_RATE),
    (R_DAMAGE, R_CC),
    (R_DAMAGE, R_MS),
    (R_CC, R_MS),
    (R_FIRE_RATE, R_STATUS),
    (R_CD, R_STATUS),
    (R_DAMAGE, R_STATUS),
    (R_CC, R_STATUS),
    (R_MS, R_STATUS),
)

_RIVEN_CSV = "riven_stats_average_1_2.csv"
_RIVEN_TYPE = "LotusRifleRandomModRare"

# Combined elements are absent from the vendored CSV (its WDC table only
# lists base attributes). Since Update 44.1 (2026-10-07) a Riven can hold
# one SPLICED combined-element trait (Riven Splicer: e.g. Heat + Cold ->
# Blast); the wiki Riven Base Values table gives "Combined Elemental
# Damage" the identical range to "Elemental Damage", and the spliced trait
# inherits the higher consumed value, so at average grade every element
# shares the same number. Toxin is an arbitrary base-element representative.
COMBINED_ELEMENT_STATS = frozenset((
    "Blast", "Viral", "Magnetic", "Corrosive", "Gas", "Radiation"))


def _source_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "source"


def load_rifle_riven_averages(
    column: str = "buff_3_pos_1_neg",
    csv_path: Optional[str | Path] = None,
) -> dict[str, float]:
    """Average Rifle Riven values (fraction, e.g. 1.856 == +185.6%).

    Reads the vendored 1.20-disposition table; ``column`` may be any of
    the layout columns in ``source/riven_stats_average_1_2.csv``.
    """
    path = Path(csv_path) if csv_path else _source_dir() / _RIVEN_CSV
    out: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["riven_type"] != _RIVEN_TYPE:
                continue
            out[row["stat_name"]] = float(row[column]) / 100.0
    if not out:
        raise ValueError(f"no {_RIVEN_TYPE} rows found in {path}")
    return out


# --- Element combine ---------------------------------------------------------

@dataclass(frozen=True)
class ElementMix:
    """Result of combining the fixed Cold, innate Elec and Riven elements."""

    factors: dict[str, float]      # damage-type -> additive elemental factor
    status_types: tuple[str, ...]  # unique damaging status types produced

    @property
    def total_factor(self) -> float:
        return sum(self.factors.values())

    def weights(self) -> dict[str, float]:
        total = self.total_factor
        return {k: v / total for k, v in self.factors.items()}


def combine_elements(riven: dict[str, float]) -> ElementMix:
    """Map Riven element positives onto the fixed Primed Cryo Cold.

    The Riven's Blast is pre-combined and stays Blast. There is only one
    Cold source, so at most one Riven element can combine; a second
    elemental positive would remain standalone (in-game mod order decides
    which), which the candidate pairs in this module avoid.
    """
    elements = [name for name in (R_TOXIN, R_HEAT, R_ELEC)
                if riven.get(name)]
    if len(elements) > 1:
        raise ValueError(
            "one Cold source can combine with only one Riven element; "
            f"got {elements}")
    cold = PRIMED_CRYO_COLD
    factors: dict[str, float] = {"ELEC": 1.0, "BLAST": riven.get(R_BLAST, 0.0)}
    if R_TOXIN in riven:
        factors["VIRAL"] = cold + riven[R_TOXIN]
    elif R_HEAT in riven:
        factors["BLAST"] += cold + riven[R_HEAT]
    elif R_ELEC in riven:
        factors["MAG"] = cold + riven[R_ELEC]
    else:
        factors["COLD"] = cold
    # Only positive factors can actually proc and count as GunCO types.
    types = tuple(name for name, factor in factors.items() if factor > 0.0)
    return ElementMix(factors, types)


def gunco_bonus(status_types: int, kill_stacks: int) -> float:
    """Galvanized Aptitude direct-damage fraction before the +1.

    Per unique status type each kill stack adds 40%, capped at 80% per
    type (wiki rank table: at 2 stacks, 3 types -> +240%, 4 -> +320%).
    """
    if status_types <= 0 or kill_stacks <= 0:
        return 0.0
    per_type = min(APTITUDE_PER_STATUS * kill_stacks, APTITUDE_PER_TYPE_CAP)
    return status_types * per_type


# --- Build -------------------------------------------------------------------

@dataclass
class AlternoxBuild:
    positions: tuple[str, ...]
    riven: dict[str, float]
    galv_kill_stacks: int
    crit_chance: float
    crit_multiplier: float
    fire_rate: float
    multishot: float
    status_per_pellet: float
    base_bracket: float            # 1 + Serration + Riven Damage
    mix: ElementMix
    co_behavior_mode: str
    co_scale: float
    modded_base: float             # base x base bracket (before GunCO)
    reload_time: float = RELOAD_TIME

    @property
    def status_types(self) -> int:
        return len(self.mix.status_types)

    def gunco_multiplier(self) -> float:
        return 1.0 + gunco_bonus(self.status_types, self.galv_kill_stacks)


def build_alternox(
    positions: tuple[str, ...] = (R_BLAST, R_FIRE_RATE, R_TOXIN),
    galv_kill_stacks: int = APTITUDE_STACK_CAP,
    chamber_stacks: int = CHAMBER_STACK_CAP,
    riven_column: str = "buff_3_pos_1_neg",
    riven_values: Optional[dict[str, float]] = None,
    blast_value: Optional[float] = None,
) -> AlternoxBuild:
    """Build one Riven configuration on top of the fixed eight mods.

    ``blast_value`` overrides the fixed Blast trait's roll (fraction, e.g.
    0.60 == +60%); by default the average-grade element value from the
    wiki/CSV convention is used. The two ranked positives always use
    average-grade values so the comparison is roll-quality neutral.
    """
    if not 0 <= galv_kill_stacks <= APTITUDE_STACK_CAP:
        raise ValueError("galv_kill_stacks must be between 0 and 2")
    if not 0 <= chamber_stacks <= CHAMBER_STACK_CAP:
        raise ValueError("chamber_stacks must be between 0 and 5")
    averages = riven_values or load_rifle_riven_averages(riven_column)

    def _value(stat: str) -> float:
        if stat in averages:
            return averages[stat]
        if stat in COMBINED_ELEMENT_STATS:
            return averages[R_TOXIN]
        raise KeyError(f"unknown Riven stat {stat!r}")

    riven = {stat: _value(stat) for stat in positions}
    if blast_value is not None:
        if R_BLAST not in riven:
            raise ValueError("blast_value requires the Blast trait position")
        riven[R_BLAST] = blast_value

    crit_chance = BASE_CRIT_CHANCE * (
        1.0 + CRIT_DELAY_CC + riven.get(R_CC, 0.0))
    crit_multiplier = BASE_CRIT_MULT * (
        1.0 + VITAL_SENSE_CD + riven.get(R_CD, 0.0))
    fire_rate = BASE_FIRE_RATE * (
        1.0 - CRIT_DELAY_ROF_PENALTY) * (1.0 + riven.get(R_FIRE_RATE, 0.0))
    multishot = (1.0 + CHAMBER_BASE_MS
                 + CHAMBER_PER_STACK * chamber_stacks
                 + riven.get(R_MS, 0.0))
    status_per_pellet = BASE_STATUS * (
        1.0 + GALV_APTITUDE_STATUS) * (1.0 + riven.get(R_STATUS, 0.0))
    base_bracket = 1.0 + SERRATION + riven.get(R_DAMAGE, 0.0)
    mix = combine_elements(riven)
    behavior = resolve_co_behavior(WEAPON, NORMAL_ATTACK)
    return AlternoxBuild(
        positions=tuple(positions),
        riven=riven,
        galv_kill_stacks=galv_kill_stacks,
        crit_chance=crit_chance,
        crit_multiplier=crit_multiplier,
        fire_rate=fire_rate,
        multishot=multishot,
        status_per_pellet=status_per_pellet,
        base_bracket=base_bracket,
        mix=mix,
        co_behavior_mode=behavior.mode,
        co_scale=behavior.scale,
        modded_base=ELEC_BASE * base_bracket,
    )


# --- Analytic expected DPS ---------------------------------------------------

@dataclass
class DpsReport:
    positions: tuple[str, ...]
    direct_dps: float
    electric_proc_dps: float
    blast_proc_dps: float
    viral_multiplier: float
    total_dps: float
    sustained_dps: float          # reload-adjusted
    status_types: int
    gunco_multiplier: float


def _crit_expectation(build: AlternoxBuild) -> float:
    cc = build.crit_chance
    return 1.0 + min(cc, 1.0) * (build.crit_multiplier - 1.0)


def expected_dps(
    build: AlternoxBuild,
    *,
    viral_stacks: int = VIRAL_CAP,
    elementalist: float = RIFLE_ELEMENTALIST_SD,
) -> DpsReport:
    """Steady-state expected DPS of the normal-fire build.

    Assumes the Galvanized kill stacks are maintained (sustained-fight
    convention) and that Viral, when the build can proc it, is saturated
    at ``viral_stacks``. Multishot uses the expected pellet count.
    """
    weights = build.mix.weights()
    co_bonus = gunco_bonus(build.status_types, build.galv_kill_stacks)
    crit = _crit_expectation(build)
    pellets_per_s = build.fire_rate * build.multishot
    factor_total = build.mix.total_factor
    sd_mult = 1.0 + elementalist
    viral = (viral_magnetic_multiplier(viral_stacks)
             if "VIRAL" in build.mix.factors else 1.0)

    # Direct hits: GunCO resolved through the catalog behavior.
    per_pellet = apply_co(
        ELEC_BASE, co_bonus, build.base_bracket * factor_total,
        crit, mode=build.co_behavior_mode, scale=build.co_scale)
    direct_dps = per_pellet * pellets_per_s

    # Proc seeds snapshot the CO-multiplied Modded Base Damage.
    seed_mbd = build.modded_base * (1.0 + co_bonus)
    procs_per_s = pellets_per_s * build.status_per_pellet
    elec_bonus = 1.0  # no standalone Electricity mod (innate does not combine)
    electric_dps = (
        procs_per_s * weights.get("ELEC", 0.0)
        * ELEC_TICK_COEF * seed_mbd * elec_bonus * sd_mult
        * ELEC_PROC_TICKS)
    # Blast fuses average out to one 0.3x MBD detonation per proc.
    blast_dps = (
        procs_per_s * weights.get("BLAST", 0.0)
        * BLAST_SINGLE_COEF * seed_mbd * sd_mult)

    total = (direct_dps + electric_dps + blast_dps) * viral
    mag_seconds = MAGAZINE / build.fire_rate
    uptime = mag_seconds / (mag_seconds + build.reload_time)
    return DpsReport(
        positions=build.positions,
        direct_dps=direct_dps * viral,
        electric_proc_dps=electric_dps * viral,
        blast_proc_dps=blast_dps * viral,
        viral_multiplier=viral,
        total_dps=total,
        sustained_dps=total * uptime,
        status_types=build.status_types,
        gunco_multiplier=1.0 + co_bonus,
    )


def rank_riven_pairs(
    galv_kill_stacks: int = APTITUDE_STACK_CAP,
    viral_stacks: int = VIRAL_CAP,
) -> list[DpsReport]:
    """All candidate pairs (Blast fixed) ranked by steady-state DPS."""
    reports = []
    for pair in RIVEN_PAIR_OPTIONS:
        build = build_alternox((R_BLAST,) + pair, galv_kill_stacks)
        reports.append(expected_dps(build, viral_stacks=viral_stacks))
    reports.sort(key=lambda r: -r.total_dps)
    return reports


# --- Stochastic hit-by-hit simulation ---------------------------------------

@dataclass
class ElectricProc:
    start: float
    seed: float
    crit_factor: float


class AlternoxTarget(DummyTarget):
    """Plain SP150 Heavy Gunner plus Electric/Blast/Viral/Cold proc state."""

    def __init__(self, health: float, armor: float, overguard: float = 0.0):
        super().__init__(health, armor, overguard)
        self.electric_procs: list[ElectricProc] = []
        self.cold_expiries: list[float] = []

    def live_electric(self, now: float) -> list[ElectricProc]:
        self.electric_procs = [p for p in self.electric_procs
                               if now - p.start < PROC_DURATION]
        return self.electric_procs

    def live_blast(self, now: float) -> list[BlastProc]:
        return [p for p in self.blast_stacks if p.fuse_end > now]

    def cold_stacks(self, now: float) -> int:
        self.cold_expiries = [t for t in self.cold_expiries if t > now]
        return len(self.cold_expiries)


@dataclass
class AlternoxTrial:
    ttk: float
    shots: int
    pellets: int
    reloads: int
    viral_procs: int
    electric_procs: int
    blast_procs: int
    blast_detonations: int
    final_viral_stacks: int
    trace: list = field(default_factory=list)


def alternox_dummy_factory() -> AlternoxTarget:
    """Plain non-Eximus SP150 Heavy Gunner (286,139.57 HP, 2,700 armor)."""
    gunner = steel_path_heavy_gunner(150)
    return AlternoxTarget(gunner.health, gunner.armor, gunner.overguard)


def _pellet_count(rng: random.Random, multishot: float) -> int:
    whole = int(math.floor(multishot))
    return whole + (1 if rng.random() < (multishot - whole) else 0)


def _crit_factor(rng: random.Random, build: AlternoxBuild) -> float:
    if rng.random() < min(build.crit_chance, 1.0):
        return build.crit_multiplier
    return 1.0


def simulate(
    build: AlternoxBuild,
    target: AlternoxTarget,
    *,
    seed: int = 1,
    max_time: float = 600.0,
    elementalist: float = RIFLE_ELEMENTALIST_SD,
    trace: bool = False,
) -> AlternoxTrial:
    """Hit-by-hit normal-fire trial with reloads, procs and GunCO per hit."""
    rng = random.Random(seed)
    now = 0.0
    next_tick = 1.0
    ammo = MAGAZINE
    shots = pellets_total = reloads = 0
    viral_procs = elec_procs = blast_procs = detonations = 0
    log: list[str] = []
    sd_mult = 1.0 + elementalist
    weights = build.mix.weights()
    proc_types = list(weights)

    def resolve_ticks(when: float) -> None:
        """Electricity DoT ticks and Blast fuses scheduled at integer secs."""
        for proc in target.live_electric(when):
            amount = (ELEC_TICK_COEF * proc.seed * proc.crit_factor
                      * sd_mult)
            amount *= 1.0 - armor_damage_reduction(
                target.current_armor(when, 1.0))
            amount *= viral_magnetic_multiplier(target.viral_stacks(when))
            target.health -= amount
        fused = [p for p in target.blast_stacks if p.fuse_end <= when]
        if fused:
            amount = sum(BLAST_SINGLE_COEF * p.seed * p.crit_factor
                         for p in fused) * sd_mult
            amount *= 1.0 - armor_damage_reduction(
                target.current_armor(when, 1.0))
            amount *= viral_magnetic_multiplier(target.viral_stacks(when))
            target.health -= amount
            target.blast_stacks = [
                p for p in target.blast_stacks if p.fuse_end > when]

    while now < max_time and target.health > 0:
        while next_tick <= now and target.health > 0:
            resolve_ticks(next_tick)
            next_tick += 1.0
        if target.health <= 0:
            break
        if ammo <= 0:
            now += build.reload_time
            reloads += 1
            ammo = MAGAZINE
            continue

        shots += 1
        ammo -= 1
        for _ in range(_pellet_count(rng, build.multishot)):
            pellets_total += 1
            # GunCO recomputes per hit from statuses currently on target.
            live_types = set(build.mix.status_types)
            if "VIRAL" in build.mix.factors and not target.viral_stacks(now):
                live_types.discard("VIRAL")
            if "MAG" in build.mix.factors and not target.mag_stacks(now):
                live_types.discard("MAG")
            if not target.live_electric(now):
                live_types.discard("ELEC")
            if not target.live_blast(now):
                live_types.discard("BLAST")
            if "COLD" in build.mix.factors and not target.cold_stacks(now):
                live_types.discard("COLD")
            co_bonus = gunco_bonus(len(live_types), build.galv_kill_stacks)
            cf = _crit_factor(rng, build)

            # Repo convention (akarius/kuva_nukor): 1/32 quantization acts
            # on the pre-crit type value, the crit multiplier lands after.
            direct = 0.0
            for factor in build.mix.factors.values():
                uncritted = apply_co(
                    ELEC_BASE, co_bonus,
                    build.base_bracket * factor, 1.0,
                    mode=build.co_behavior_mode, scale=build.co_scale)
                direct += wiki_quantized_damage(
                    uncritted, build.modded_base) * cf
            direct *= (1.0 - armor_damage_reduction(
                target.current_armor(now, 1.0)))
            direct *= viral_magnetic_multiplier(target.viral_stacks(now))
            target.health -= direct

            # Status chance above 100% guarantees floor(sc) procs plus one
            # fractional roll (same convention as the Kuva Nukor sim); the
            # base 72% build always takes the single fractional path.
            guaranteed_procs = int(math.floor(build.status_per_pellet))
            n_procs = guaranteed_procs + (
                1 if rng.random()
                < build.status_per_pellet - guaranteed_procs else 0)
            for _ in range(n_procs):
                ptype = rng.choices(proc_types,
                                    weights=[weights[t] for t in proc_types],
                                    k=1)[0]
                proc_seed = build.modded_base * (1.0 + co_bonus)
                if ptype == "ELEC":
                    target.electric_procs.append(
                        ElectricProc(now, proc_seed, cf))
                    elec_procs += 1
                elif ptype == "BLAST":
                    target.blast_stacks.append(
                        BlastProc(now, now + BLAST_FUSE, proc_seed, cf))
                    blast_procs += 1
                    if len(target.blast_stacks) >= BLAST_STACK_CAP:
                        # All ten stacks detonate at 0.3x MBD each.
                        amount = sum(BLAST_SINGLE_COEF * p.seed
                                     * p.crit_factor
                                     for p in target.blast_stacks) * sd_mult
                        amount *= (1.0 - armor_damage_reduction(
                            target.current_armor(now, 1.0)))
                        amount *= viral_magnetic_multiplier(
                            target.viral_stacks(now))
                        target.health -= amount
                        detonations += 1
                        target.blast_stacks.clear()
                elif ptype == "VIRAL":
                    target.viral_expiries.append(now + PROC_DURATION)
                    target.viral_expiries = target.viral_expiries[-VIRAL_CAP:]
                    viral_procs += 1
                elif ptype == "MAG":
                    target.mag_expiries.append(now + PROC_DURATION)
                    target.mag_expiries = target.mag_expiries[-VIRAL_CAP:]
                elif ptype == "COLD":
                    # Slow has no single-target DPS effect, but Cold is a
                    # live status type for Galvanized Aptitude/GunCO.
                    target.cold_expiries.append(now + PROC_DURATION)
            if target.health <= 0:
                # Remaining multishot pellets of this pull never land.
                break

        now += 1.0 / build.fire_rate
        if trace and shots % 5 == 0:
            log.append(
                f"t={now:6.2f}s hp={max(target.health, 0):12.0f} "
                f"viral={target.viral_stacks(now):2d} "
                f"elec={len(target.live_electric(now)):2d} "
                f"blast={len(target.live_blast(now)):2d}")

    ttk = now if target.health <= 0 else math.inf
    return AlternoxTrial(
        ttk=ttk, shots=shots, pellets=pellets_total, reloads=reloads,
        viral_procs=viral_procs, electric_procs=elec_procs,
        blast_procs=blast_procs, blast_detonations=detonations,
        final_viral_stacks=target.viral_stacks(ttk if math.isfinite(ttk)
                                               else now),
        trace=log,
    )


def run_trials(positions: tuple[str, ...],
               trials: int = 200,
               base_seed: int = 20261027,
               galv_kill_stacks: int = APTITUDE_STACK_CAP,
               factory=alternox_dummy_factory) -> dict:
    """Median TTK over stochastic trials for one Riven configuration."""
    build = build_alternox(positions, galv_kill_stacks)
    ttks, reloads, viral = [], [], []
    for i in range(trials):
        result = simulate(build, factory(), seed=base_seed + i)
        if math.isfinite(result.ttk):
            ttks.append(result.ttk)
            reloads.append(result.reloads)
            viral.append(result.final_viral_stacks)
    ttks.sort()
    if not ttks:
        # Every trial timed out (e.g. max_time too short for the build).
        return {
            "positions": positions,
            "build": build,
            "trials": 0,
            "ttk_median": math.inf,
            "ttk_mean": math.inf,
            "ttk_p90": math.inf,
            "reloads_median": 0,
            "viral_median": 0,
        }

    def pct(p: float) -> float:
        return ttks[min(len(ttks) - 1, int(round(p * (len(ttks) - 1))))]

    return {
        "positions": positions,
        "build": build,
        "trials": len(ttks),
        "ttk_median": pct(0.5),
        "ttk_mean": sum(ttks) / len(ttks),
        "ttk_p90": pct(0.9),
        "reloads_median": reloads[len(reloads) // 2],
        "viral_median": viral[len(viral) // 2],
    }
