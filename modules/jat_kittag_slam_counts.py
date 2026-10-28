"""Experimental, single-target slam-count sensitivities, NOT a gameplay TTK.

This is independent of the invalidated historical ``jat_kittag_sim``.  It is
an explicit hypothesis about underspecified interactions, not a validated
engine implementation.  See docs/jat_kittag_expected_slams.md before using it.

The target is one stationary, shieldless Grineer Heavy Gunner; all damage
is neutral to that faction and health has a fixed armor DR.  The model follows
critical tiers, 2 or 3 weighted status rolls, normal Gas/Electricity/Toxin,
Blast's single-target fuse, a user-requested no-overflow Overguard break, and
a special Magnetic-break Electricity proc.  It supports *hypothetical* Melee
Afflictions scenarios and their repeated status-damage re-seeding.

Not simulated: shields, other enemies, radial overlaps, buffs, weakpoints,
real movement, changing combo/stacks, conditional invulnerability, damage
attenuation, or exact engine event order and rounding.  Afflictions triggering,
Gas clone scaling, Blast interaction, Seismic seeding, Magnetic-break seeding
and Gas timing are uncertain; scenario outputs cannot be called measured TTK.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass

from .crit import crit_multiplier_for_tier
from .damage_routing import status_vulnerability
from .enemy_scaling import (
    ScaledEnemy,
    icebind_eximus_heavy_gunner,
    steel_path_eximus_heavy_gunner,
    steel_path_heavy_gunner,
)
from .jat_kittag_slam_analysis import (
    BUILD_BY_KEY,
    PRIMED_FEVER_STRIKE,
    SLAM_BASE,
    Build,
    sustainable_interval,
)
from .status_damage import magnetic_break_electric_tick
from .trial_statistics import sample_percentile

STATUS_DAMAGE_MULTIPLIER = 1.8  # max Galvanized Elementalist
ELECTRICITY_MULTIPLIER = 1.6  # Focus Energy, even when combined into Magnetic
PROC_DURATION = 6.0
BLAST_FUSE = 1.5
GAS_CAP = 10
MAGNETIC_CAP = 10
BLAST_CAP = 10
TIME_DIGITS = 9


def _time(value: float) -> float:
    """Stable event ordering for decimal slam intervals and whole-second ticks."""
    return round(value, TIME_DIGITS)


@dataclass(frozen=True)
class Assumptions:
    """One chosen mechanical hypothesis; none is guaranteed to match the game.

    ``affliction_stacks=0`` removes the arcane for a diagnostic baseline.
    With stacks, this model requires any live damaging DoT before replication;
    it assumes triggering-hit statuses count, but defers Lifted on an
    Overguard-breaking blow unless ``afflict_on_break`` is selected.  A direct
    slam which breaks Overguard is the only same-slam break eligible in that
    alternative; a subsequent status tick is not treated as a new Lifted.
    ``affliction_passes=2`` is a separate hypothesis that two sequential
    triggers occur on a slam; it is not the same as adding 12 stacks once.
    """
    interval: float = 0.65
    combo: int = 5
    affliction_stacks: int = 6
    affliction_passes: int = 1
    afflict_on_break: bool = False
    seed_slam_factor: float = 1.0
    clone_gas_bonus: bool = False
    shared_aoe_ticks: bool = True
    magnetic_break_can_seed: bool = False
    apply_affliction_hit: bool = False
    statuses: bool = True
    max_slams: int = 1000

    def __post_init__(self) -> None:
        if self.combo != 5:
            raise ValueError("Only the stated fully stacked 5x combo is modeled")
        if not math.isfinite(self.interval) or self.interval < sustainable_interval(80.0, .9):
            raise ValueError("5x is not sustainable at the requested interval")
        if self.affliction_stacks < 0 or not isinstance(self.affliction_stacks, int):
            raise ValueError("affliction_stacks must be a non-negative integer")
        if self.affliction_passes not in (1, 2):
            raise ValueError("affliction_passes must be 1 or 2")
        if not math.isfinite(self.seed_slam_factor) or self.seed_slam_factor <= 0:
            raise ValueError("seed_slam_factor must be positive")
        if self.max_slams <= 0:
            raise ValueError("max_slams must be positive")


@dataclass(frozen=True)
class Target:
    """Enemy snapshot; the simulation is deliberately restricted to no shields."""
    name: str
    health: float
    overguard: float
    armor_dr: float

    @classmethod
    def from_scaled(cls, enemy: ScaledEnemy) -> Target:
        if enemy.shields:
            raise ValueError("Shielded enemies are not modeled")
        if enemy.health <= 0 or enemy.overguard < 0 or not 0 <= enemy.armor_dr < 1:
            raise ValueError("Invalid target defenses")
        return cls(enemy.name, enemy.health, enemy.overguard, enemy.armor_dr)


@dataclass
class DotGroup:
    kind: str
    count: int
    # MBD as used by the Wiki's Affliction per-type average; already includes
    # status damage, crit and combo, but not the elemental tick multiplier.
    proc_mbd: float
    tick: float
    next_tick: float
    expires: float
    last_tick: float
    can_seed: bool = True


@dataclass
class BlastGroup:
    count: int
    damage: float
    expires: float


@dataclass(frozen=True)
class Trial:
    slams: int
    death_time: float | None
    triggers: int
    overguard_break_slam: int | None

    @property
    def killed(self) -> bool:
        return self.death_time is not None


class Fight:
    """One event-ordered fight under a particular, documented assumption set."""

    def __init__(self, build: Build, target: Target, assumptions: Assumptions):
        if build.key not in ("focus_fever_gas_cold_damage", "focus_gas_cc_cd"):
            raise ValueError("This experiment only models the two requested builds")
        self.build = build
        self.target = target
        self.a = assumptions
        # Build and assumptions are fixed for this fight. Avoid repeatedly
        # resolving quantized direct damage and mod properties on every slam.
        crit_chance = build.crit_chance
        self._crit_tiers = math.floor(crit_chance)
        self._extra_crit_chance = crit_chance - self._crit_tiers
        self._crit_multiplier = build.crit_multiplier
        self._noncrit = build.direct_average(assumptions.combo) / build.average_crit_multiplier
        status_rolls = build.status_rolls
        self._whole_status_rolls = math.floor(status_rolls)
        self._extra_status_chance = status_rolls - self._whole_status_rolls
        self._status_kinds = tuple(build.types)
        self._status_weights = tuple(build.types.values())
        self._seed_before_crit = (SLAM_BASE * (1 + build.pressure_point_bonus
                                              + build.melee_damage_bonus
                                              + build.heavy_attack_damage_bonus)
                                  * assumptions.combo)
        self._status_damage_multiplier = build.status_damage_multiplier
        self.health = target.health
        self.overguard = target.overguard
        self.dots: list[DotGroup] = []
        # Shared periodic pulses are a coarse interpretation of consolidated
        # Electricity/Gas ticks; initial application is immediate, but adding
        # stacks to an existing cloud does not create a separate immediate
        # pulse. Per-proc clocks remain an explicit sensitivity scenario.
        self.aoe_next: dict[str, float | None] = {"GAS": None, "ELECTRICITY": None}
        self.blast: list[BlastGroup] = []
        self.magnetic: list[float] = []
        self.slams = 0
        self.triggers = 0
        self.break_slam: int | None = None
        self.death_time: float | None = None

    def _elemental(self, kind: str, *, cloned: bool) -> float:
        if kind == "GAS":
            return (1 + self.build.gas_bonus
                    if not cloned or self.a.clone_gas_bonus else 1.0)
        if kind == "TOXIN":
            return 1 + (PRIMED_FEVER_STRIKE
                        if "Primed Fever Strike" in self.build.weapon_mods else 0.0)
        if kind == "ELECTRICITY":
            return ELECTRICITY_MULTIPLIER
        raise ValueError(f"unsupported DoT {kind}")

    def _add_dot(self, kind: str, count: int, proc_mbd: float, now: float,
                 *, cloned: bool = False, forced_tick: float | None = None,
                 can_seed: bool = True) -> None:
        if count <= 0:
            return
        if kind == "GAS":
            # Gas replaces the oldest instances, not necessarily the weakest.
            excess = max(0, sum(d.count for d in self.dots if d.kind == "GAS")
                         + count - GAS_CAP)
            for old in self.dots:
                if old.kind == "GAS" and excess:
                    remove = min(old.count, excess)
                    old.count -= remove
                    excess -= remove
            self.dots = [d for d in self.dots if d.count]
            count = min(count, GAS_CAP)
        tick = (0.5 * proc_mbd * self._elemental(kind, cloned=cloned)
                if forced_tick is None else forced_tick)
        delayed = kind == "TOXIN"
        shared = self.a.shared_aoe_ticks and kind in self.aoe_next
        if shared and self.aoe_next[kind] is None:
            self.aoe_next[kind] = _time(now)
        self.dots.append(DotGroup(kind, count, proc_mbd, tick,
                                  math.inf if shared else _time(now + (1.0 if delayed else 0.0)),
                                  _time(now + PROC_DURATION),
                                  _time(now + (6.0 if delayed else 5.0)),
                                  can_seed))

    def _route(self, damage: float, now: float) -> None:
        if damage <= 0 or self.health <= 0:
            return
        if self.overguard > 0:
            applied = damage * status_vulnerability(len(self.magnetic))
            if applied < self.overguard:
                self.overguard -= applied
                return
            # User's specified no-overflow-per-damage-event assumption, NOT
            # an assertion that enemy Overguard has a player-style timed gate.
            self.overguard = 0.0
            self.break_slam = self.slams
            if self.magnetic:
                tick = magnetic_break_electric_tick(
                    self.target.overguard, len(self.magnetic),
                    status_damage_bonus=STATUS_DAMAGE_MULTIPLIER - 1,
                    electricity_bonus=ELECTRICITY_MULTIPLIER - 1,
                )
                # This back-calculated MBD is only a hypothetical alternative:
                # whether this special proc seeds Afflictions this way is unknown.
                mbd = 2 * tick / ELECTRICITY_MULTIPLIER
                self._add_dot("ELECTRICITY", 1, mbd, now,
                              forced_tick=tick,
                              can_seed=self.a.magnetic_break_can_seed)
            return
        self.health -= damage * (1 - self.target.armor_dr)
        if self.health <= 0:
            self.death_time = now

    def _detonate(self, groups: list[BlastGroup], now: float) -> None:
        # The wiki describes 10 individual single-target hits; no surrounding
        # explosion hits the afflicted host.  Different event order/gates are
        # possible in the engine and are not validated here.
        for group in groups:
            for _ in range(group.count):
                self._route(group.damage, now)
                if self.health <= 0:
                    return

    def _add_blast(self, count: int, damage: float, now: float) -> None:
        while count and self.health > 0:
            current = sum(g.count for g in self.blast)
            added = min(count, BLAST_CAP - current)
            self.blast.append(BlastGroup(added, damage, _time(now + BLAST_FUSE)))
            count -= added
            if current + added == BLAST_CAP:
                groups, self.blast = self.blast, []
                self._detonate(groups, now)

    def _expire_magnetic(self, now: float) -> None:
        self.magnetic = [expiry for expiry in self.magnetic if expiry > now]

    def _add_magnetic(self, count: int, now: float) -> None:
        self._expire_magnetic(now)
        self.magnetic.extend([_time(now + PROC_DURATION)] * count)
        self.magnetic = self.magnetic[-MAGNETIC_CAP:]

    def advance(self, until: float) -> float | None:
        """Process all events up to ``until``; a death uses previous slam count."""
        until = _time(until)
        while self.health > 0:
            candidates = [min(d.next_tick, d.expires) for d in self.dots]
            candidates.extend(t for t in self.aoe_next.values() if t is not None)
            candidates.extend(g.expires for g in self.blast)
            if not candidates:
                break
            now = min(candidates)
            if now > until:
                break
            self._expire_magnetic(now)
            for kind in ("GAS", "ELECTRICITY", "TOXIN"):
                if self.a.shared_aoe_ticks and kind in self.aoe_next:
                    if self.aoe_next[kind] != now:
                        continue
                    # The last AoE tick at the exact six-second expiry is zero.
                    due = [d for d in self.dots if d.kind == kind and d.expires > now]
                    self.aoe_next[kind] = _time(now + 1) if due else None
                else:
                    due = [d for d in self.dots if d.kind == kind and d.next_tick == now]
                    for dot in due:
                        next_tick = _time(dot.next_tick + 1)
                        dot.next_tick = next_tick if next_tick <= dot.last_tick else math.inf
                damage = sum(d.tick * d.count for d in due)
                self._route(damage, now)
                if self.health <= 0:
                    return now
            # Toxin ticks at its exact six-second expiry before removal.
            self.dots = [d for d in self.dots if d.expires > now]
            if self.a.shared_aoe_ticks:
                for kind in self.aoe_next:
                    if not any(d.kind == kind for d in self.dots):
                        self.aoe_next[kind] = None
            expired = [g for g in self.blast if g.expires <= now]
            self.blast = [g for g in self.blast if g.expires > now]
            self._detonate(expired, now)
            if self.health <= 0:
                return now
        self._expire_magnetic(until)
        return None

    def _afflict(self, now: float) -> None:
        """Hypothetical cross-type averaging, not an engine-validated formula."""
        by_type: dict[str, list[DotGroup]] = {}
        for dot in self.dots:
            # Even if the break proc's strength is excluded as a source, it is
            # still an Electricity status which could be replicated if another
            # eligible damaging DoT supplies an Affliction seed.
            by_type.setdefault(dot.kind, []).append(dot)
        seed = 0.0
        for groups in by_type.values():
            eligible = [g for g in groups if g.can_seed]
            count = sum(g.count for g in eligible)
            if count:
                seed += sum(g.proc_mbd * g.count for g in eligible) / count
        if not seed:
            return  # one disputed, explicit DoT-required hypothesis
        self.triggers += 1
        if self.a.apply_affliction_hit:
            # Alternative interpretation of the Wiki's 'Affliction Damage Hit'.
            # Its physical damage type/timing is not established here. On these
            # Grineer targets all relevant types have the same health modifier.
            self._route(seed, now)
            if self.health <= 0:
                return
        cloned_mbd = seed * STATUS_DAMAGE_MULTIPLIER
        for kind in ("GAS", "ELECTRICITY", "TOXIN"):
            if kind in by_type:
                self._add_dot(kind, self.a.affliction_stacks, cloned_mbd,
                              now, cloned=True)
        if self.blast:
            self._add_blast(self.a.affliction_stacks, 0.3 * cloned_mbd, now)
        if self.magnetic:
            self._add_magnetic(self.a.affliction_stacks, now)

    def slam(self, rng: random.Random, now: float) -> None:
        """Resolve one radial heavy slam, then eligible statuses and Afflictions."""
        if self.health <= 0:
            return
        self._expire_magnetic(now)
        self.slams += 1
        had_overguard = self.overguard > 0
        tier = self._crit_tiers + (rng.random() < self._extra_crit_chance)
        crit = crit_multiplier_for_tier(self._crit_multiplier, tier)
        self._route(self._noncrit * crit, now)
        broke_directly = had_overguard and self.overguard <= 0
        if self.health <= 0 or not self.a.statuses:
            return

        rolls = self._whole_status_rolls + (rng.random() < self._extra_status_chance)
        counts = Counter(rng.choices(self._status_kinds, weights=self._status_weights, k=rolls))
        seed = (self._seed_before_crit * crit * self.a.seed_slam_factor
                * self._status_damage_multiplier)
        if counts["MAGNETIC"]:
            self._add_magnetic(counts["MAGNETIC"], now)
        for kind in ("GAS", "ELECTRICITY", "TOXIN"):
            if counts[kind]:
                self._add_dot(kind, counts[kind], seed, now)
        if counts["BLAST"]:
            self._add_blast(counts["BLAST"], 0.3 * seed, now)
        if self.health <= 0:
            return
        # A newly started Gas/Electricity effect pulses immediately. Shared
        # clocks consolidate later stacks, or per-proc clocks are selected as
        # a sensitivity. Then this triggering hit may seed Afflictions.
        self.advance(now)
        if self.health <= 0:
            return
        lift_eligible = (not had_overguard or
                         (self.a.afflict_on_break and broke_directly))
        if self.a.affliction_stacks and lift_eligible and self.overguard <= 0:
            for _ in range(self.a.affliction_passes):
                self._afflict(now)
                self.advance(now)
                if self.health <= 0:
                    break


def simulate_trial(build: Build, target: Target, assumptions: Assumptions,
                   *, seed: int = 20261028) -> Trial:
    rng = random.Random(seed)
    fight = Fight(build, target, assumptions)
    for i in range(assumptions.max_slams):
        now = _time(i * assumptions.interval)
        if fight.advance(now) is not None:
            break
        fight.slam(rng, now)
        if fight.health <= 0:
            break
    # A death after the final allowed slam but before the next scheduled slam
    # is still a kill with that many slams, not a timeout.
    if fight.health > 0:
        fight.advance(_time(assumptions.max_slams * assumptions.interval))
    return Trial(fight.slams, fight.death_time, fight.triggers, fight.break_slam)


def summarize(build: Build, target: Target, assumptions: Assumptions,
              trials: int = 10000, base_seed: int = 20261028) -> dict:
    """Summarize actual slam counts; timeouts are not silently omitted."""
    if trials <= 0:
        raise ValueError("trials must be positive")
    results = [simulate_trial(build, target, assumptions, seed=base_seed + i)
               for i in range(trials)]
    killed = [x for x in results if x.killed]
    counts = [x.slams for x in killed]
    summary = {
        "build": build.key, "target": asdict(target),
        "assumptions": asdict(assumptions), "seed": base_seed,
        "attempted": trials, "kills": len(killed), "timeouts": trials - len(killed),
        "mean_slams": statistics.fmean(counts) if counts else None,
        "mean_slams_se": (statistics.stdev(counts) / math.sqrt(len(counts))
                          if len(counts) > 1 else None),
        "median_slams": statistics.median(counts) if counts else None,
        "p10_slams": sample_percentile(counts, .1) if counts else None,
        "p90_slams": sample_percentile(counts, .9) if counts else None,
        "slam_count_histogram": dict(sorted(Counter(counts).items())),
        "mean_triggers": statistics.fmean(x.triggers for x in killed) if killed else None,
    }
    if summary["timeouts"]:
        # These are conditional on killing within the configured cutoff, not
        # an unbiased all-trial expected kill count.
        summary["conditional_on_kill"] = True
    return summary


TARGETS: dict[str, Callable[[], ScaledEnemy]] = {
    "sp150_eximus": lambda: steel_path_eximus_heavy_gunner(150),
    "sp150_normal": lambda: steel_path_heavy_gunner(150),
    "icebind1000_eximus_6p": lambda: icebind_eximus_heavy_gunner(1000, players=6),
}
BUILDS = ("focus_fever_gas_cold_damage", "focus_gas_cc_cd")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261028)
    parser.add_argument("--target", choices=TARGETS, default="sp150_eximus")
    parser.add_argument("--interval", type=float, default=.65)
    parser.add_argument("--stacks", type=int, default=6)
    parser.add_argument("--affliction-passes", type=int, default=1)
    parser.add_argument("--seed-slam-factor", type=float, default=1.0)
    parser.add_argument("--afflict-on-break", action="store_true")
    parser.add_argument("--clone-gas-bonus", action="store_true")
    parser.add_argument("--per-proc-aoe-ticks", action="store_true")
    parser.add_argument("--magnetic-break-can-seed", action="store_true")
    parser.add_argument("--apply-affliction-hit", action="store_true")
    parser.add_argument("--direct-only", action="store_true")
    args = parser.parse_args()
    assumptions = Assumptions(
        interval=args.interval, affliction_stacks=args.stacks,
        affliction_passes=args.affliction_passes,
        afflict_on_break=args.afflict_on_break,
        seed_slam_factor=args.seed_slam_factor,
        clone_gas_bonus=args.clone_gas_bonus,
        shared_aoe_ticks=not args.per_proc_aoe_ticks,
        magnetic_break_can_seed=args.magnetic_break_can_seed,
        apply_affliction_hit=args.apply_affliction_hit,
        statuses=not args.direct_only,
    )
    target = Target.from_scaled(TARGETS[args.target]())
    for key in BUILDS:
        print(json.dumps(summarize(BUILD_BY_KEY[key], target, assumptions,
                                   args.trials, args.seed), sort_keys=True))


if __name__ == "__main__":
    main()
