"""Reproduce the experimental Ocucor Enervate versus Flare comparison.

Run ``python -m modules.ocucor_comparison`` from the repository root. JSON
records describe paired seeded trials; the report documents all assumptions.
The room scenarios are deliberately idealized, and the single-hit Enervate
AFCC does not model multi-target charging/reset. Results are not measured TTKs.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from contextlib import nullcontext
from typing import Any, TypedDict
from unittest.mock import patch

import modules.kuva_nukor_sim as nukor
from modules.damage_routing import RoutedDamage, route_enemy_hit
from modules.enemy_scaling import HEAVY_GUNNER, MODE_STEEL_PATH, scale_enemy
from modules.ocucor_sim import (
    ARCANE_ENERVATE,
    ARCANE_FLARE,
    FLARE_MAX_STACKS,
    DummyTarget,
    build_ocucor,
    simulate,
    simulate_room,
)
from modules.trial_statistics import sample_percentile


def make_target(eximus: bool, cls: type[DummyTarget] = DummyTarget) -> DummyTarget:
    """A fresh, unprimed level-150 Steel Path Heavy Gunner."""
    enemy = scale_enemy(HEAVY_GUNNER, level=150, eximus=eximus,
                        mode=MODE_STEEL_PATH)
    return cls(enemy.health, enemy.armor, enemy.overguard)


class _StartSettings(TypedDict):
    """Start-of-shot settings shared by the single-target and room models."""

    starting_tendrils: int
    starting_flare_stacks: int
    enervate_extra_pct: float
    heat_seed_mode: str
    ramp_heat_seed: bool
    puncture_cap: int


class SharedHeatClockTarget(DummyTarget):
    """Sensitivity: every live Heat stack contributes at the group's pulse."""

    def consume_heat_tick(self, when: float, duration: float):
        if self.next_heat_tick(duration) != when:
            return []
        self.prune(when, duration)
        self._next_heat_tick = when + 1.0
        return list(self.heat_procs)


def discard_overguard_overflow(damage_by_type, **kwargs):
    """User-asserted depletion gate: discard the breaking hit's overflow.

    This adds no timed invulnerability. The Wiki distinguishes player and
    enemy Overguard; the report also runs the Wiki-based overflow alternative.
    """
    result = route_enemy_hit(damage_by_type, **kwargs)
    if result.broke_overguard:
        return RoutedDamage(result.overguard, 0.0, True)
    return result


def _summarize(results, attempted: int, *, room: bool) -> dict:
    time_attr = "clear_time" if room else "ttk"
    observed = [r for r in results if math.isfinite(getattr(r, time_attr))]
    if not observed:
        return {"attempted": attempted, "timed_out": attempted,
                "mean_s": None, "median_s": None, "p90_s": None}
    times = [getattr(r, time_attr) for r in observed]
    cap_times = [r.flare_cap_time for r in observed if r.flare_cap_time is not None]
    data = {
        "attempted": attempted,
        "timed_out": attempted - len(observed),
        "mean_s": statistics.mean(times),
        "median_s": sample_percentile(times, 0.5),
        "p90_s": sample_percentile(times, 0.9),
        "reload_pct": 100.0 * sum(r.reloads > 0 for r in observed) / len(observed),
        "flare_cap_pct": 100.0 * len(cap_times) / len(observed),
        "flare_cap_median_s_if_reached": (sample_percentile(cap_times, 0.5)
                                          if cap_times else None),
    }
    if room:
        data.update({
            "mean_tendrils_per_tick": statistics.mean(
                r.average_tendrils_per_tick for r in observed),
            "mean_primary_direct_kills": statistics.mean(
                r.primary_direct_kills for r in observed),
            "mean_tendril_direct_kills": statistics.mean(
                r.tendril_direct_kills for r in observed),
            "mean_status_kills": statistics.mean(r.status_kills for r in observed),
        })
    else:
        data.update({
            "overguard_break_median_s": sample_percentile(
                (r.overguard_break_time for r in observed), 0.5),
            "puncture_stacks_median_at_death": sample_percentile(
                (r.final_puncture_stacks for r in observed), 0.5),
            "flare_stacks_median_at_death": sample_percentile(
                (r.final_flare_stacks for r in observed), 0.5),
        })
    return data


def _paired_difference(enervate, flare, *, room: bool) -> dict | None:
    attr = "clear_time" if room else "ttk"
    differences = [getattr(f, attr) - getattr(e, attr)
                   for e, f in zip(enervate, flare, strict=True)
                   if math.isfinite(getattr(e, attr))
                   and math.isfinite(getattr(f, attr))]
    if not differences:
        return None
    mean = statistics.mean(differences)
    interval = None
    if len(differences) > 1:
        margin = 1.96 * statistics.stdev(differences) / math.sqrt(len(differences))
        interval = [mean - margin, mean + margin]
    return {"complete_pairs": len(differences),
            "mean_flare_minus_enervate_s": mean,
            "approx_95pct_monte_carlo_interval_s": interval}


def compare(name: str, *, eximus: bool, trials: int, seed: int,
            tendrils: int, room: bool = False, n_enemies: int = 10,
            gate_overguard: bool = True, shared_heat_clock: bool = False,
            heat_seed_mode: str = "per_hit", ramp_heat_seed: bool = False,
            puncture_cap: int = 5, enervate_extra_pct: float = 0.0,
            full_beam_ramp: bool = False) -> dict:
    """Compare the requested Riven with averaged Enervate and cold/full Flare.

    Seed pairing reduces sampling noise but cannot remove model uncertainty.
    The same initial tendril state and enemy setup is used for all three runs.
    """
    if trials < 1:
        raise ValueError("trials must be positive")
    if room and full_beam_ramp:
        raise ValueError("the room model always starts each fresh target cold")
    target_type = SharedHeatClockTarget if shared_heat_clock else DummyTarget
    def factory():
        return make_target(eximus, target_type)
    patch_route = (patch.object(nukor, "route_enemy_hit", discard_overguard_overflow)
                   if gate_overguard else nullcontext())
    settings = {
        "eximus": eximus,
        "starting_tendrils": tendrils,
        "room_targets": n_enemies if room else None,
        "gate_overguard_overflow": gate_overguard,
        "shared_heat_clock": shared_heat_clock,
        "heat_seed_mode": heat_seed_mode,
        "ramp_heat_seed": ramp_heat_seed,
        "puncture_cap": puncture_cap,
        "enervate_extra_pct": enervate_extra_pct,
        "full_beam_ramp": full_beam_ramp,
    }
    setups = (("enervate", ARCANE_ENERVATE, 0),
              ("flare_cold", ARCANE_FLARE, 0),
              ("flare_full", ARCANE_FLARE, FLARE_MAX_STACKS))
    # Room runs yield RoomResult, single-target runs OcucorTrial; both carry
    # the timing attribute that _summarize and _paired_difference read.
    outcomes: dict[str, list[Any]] = {}
    with patch_route:
        for label, arcane, initial_flare in setups:
            build = build_ocucor(arcane, "Multishot")
            kwargs: _StartSettings = {
                "starting_tendrils": tendrils,
                "starting_flare_stacks": initial_flare,
                "enervate_extra_pct": (enervate_extra_pct
                                       if arcane == ARCANE_ENERVATE else 0.0),
                "heat_seed_mode": heat_seed_mode,
                "ramp_heat_seed": ramp_heat_seed,
                "puncture_cap": puncture_cap,
            }
            if room:
                outcomes[label] = [
                    simulate_room(arcane, "Multishot", n_enemies,
                                  seed=seed + i, factory=factory,
                                  max_time=60.0, **kwargs)
                    for i in range(trials)
                ]
            else:
                outcomes[label] = [
                    simulate(build, factory(), seed=seed + i, max_time=30.0,
                             full_beam_ramp=full_beam_ramp, **kwargs)
                    for i in range(trials)
                ]
    record = {"scenario": name, "seed_start": seed, "settings": settings}
    record.update({label: _summarize(values, trials, room=room)
                   for label, values in outcomes.items()})
    record["paired"] = {
        label: _paired_difference(outcomes["enervate"], outcomes[label], room=room)
        for label in ("flare_cold", "flare_full")
    }
    print(json.dumps(record, allow_nan=False), flush=True)
    return record


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261028)
    parser.add_argument("--single-trials", type=int, default=2000)
    parser.add_argument("--room-trials", type=int, default=300)
    parser.add_argument("--sensitivity-trials", type=int, default=800)
    args = parser.parse_args(argv)
    if min(args.single_trials, args.room_trials, args.sensitivity_trials) < 1:
        parser.error("trial counts must be positive")

    for eximus in (False, True):
        target = "eximus" if eximus else "ordinary"
        for tendrils in (0, 4):
            compare(f"single_{target}_{tendrils}_tendrils", eximus=eximus,
                    trials=args.single_trials, seed=args.seed, tendrils=tendrils)
            compare(f"room10_{target}_{tendrils}_tendrils", eximus=eximus,
                    trials=args.room_trials, seed=args.seed, tendrils=tendrils,
                    room=True)

    n = args.sensitivity_trials
    common = {"eximus": True, "trials": n, "seed": args.seed, "tendrils": 4}
    compare("wiki_overguard_overflow", **common, gate_overguard=False)
    compare("all_live_heat_stacks_tick", **common, shared_heat_clock=True)
    compare("first_whole_heat_seed_inherited", **common, heat_seed_mode="first_hit")
    compare("beam_ramp_in_heat_seed", **common, ramp_heat_seed=True)
    compare("puncture_cap_three", **common, puncture_cap=3)
    compare("idealized_full_target_ramp", **common, full_beam_ramp=True)

    # Hypothetical extra AFCC points, NOT estimates of real multi-beam Enervate.
    for extra in (50.0, 100.0):
        compare(f"room10_eximus_extra_enervate_{int(extra)}pct",
                eximus=True, trials=args.room_trials, seed=args.seed,
                tendrils=4, room=True, enervate_extra_pct=extra)
    # Same-seed baseline subset for a like-for-like sensitivity table.
    compare("baseline_eximus_4_subset", **common)


if __name__ == "__main__":
    main()
