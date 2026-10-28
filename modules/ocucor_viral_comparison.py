"""Compare the requested Ocucor Riven layouts and Viral dilution controls.

Run ``python -m modules.ocucor_viral_comparison`` to print seeded JSONL
records. The comparison inherits the experimental assumptions and routing
sensitivities of :mod:`modules.ocucor_comparison`; see the accompanying
report. It is not validated against gameplay or real multi-target Enervate.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any, TypedDict
from unittest.mock import patch

import modules.kuva_nukor_sim as nukor
from modules.ocucor_comparison import (
    SharedHeatClockTarget,
    discard_overguard_overflow,
    make_target,
)
from modules.ocucor_sim import (
    ARCANE_ENERVATE,
    ARCANE_FLARE,
    FLARE_MAX_STACKS,
    DummyTarget,
    OcucorBuild,
    build_ocucor,
    simulate,
    simulate_room,
)
from modules.trial_statistics import sample_percentile


@dataclass(frozen=True)
class RivenSpec:
    label: str
    multishot: float   # positive Riven bonus, not total multishot
    viral: float
    reload_speed: float
    attainable_midpoint: bool

    def build(self, arcane: str) -> OcucorBuild:
        return build_ocucor(arcane, "Multishot",
                            riven_multishot_bonus=self.multishot,
                            riven_viral_bonus=self.viral,
                            riven_reload_speed_bonus=self.reload_speed)


# Rank-8, normalized 1.2, midpoint. The spliced Viral values are rounded
# display-like figures from the Wiki's 90% base and respective layout weights.
RIVEN_TWO_POS = RivenSpec("two_positive", 1.778, 1.337, 0.0, True)
RIVEN_THREE_POS = RivenSpec("three_positive_reload", 1.347, 1.013, 0.562, True)
# These two intentionally impossible-as-midpoint hybrid controls isolate the
# lower Viral amount and the extra reload speed. They are NOT proposed rolls.
RIVEN_LOWER_VIRAL = RivenSpec("lower_viral_only_control", 1.778, 1.013, 0.0, False)
RIVEN_NO_RELOAD = RivenSpec("three_positive_no_reload_control", 1.347, 1.013, 0.0, False)
# A possible two-positive roll with a minimum-grade Viral trait and a
# midpoint-grade Multishot trait. It is not an all-midpoint roll.
RIVEN_LOW_VIRAL_TWO_POS = RivenSpec("two_positive_low_viral", 1.778, 1.203, 0.0, False)
ALL_SPECS = (RIVEN_TWO_POS, RIVEN_THREE_POS, RIVEN_LOWER_VIRAL, RIVEN_NO_RELOAD)
REAL_SPECS = (RIVEN_TWO_POS, RIVEN_THREE_POS)


def target_factory(eximus: bool, *, shared_heat_clock: bool = False,
                   preprimed_viral_stacks: int = 0) -> DummyTarget:
    """Create an unprimed dummy, optionally with six-second external Viral."""
    if not 0 <= preprimed_viral_stacks <= 10:
        raise ValueError("external Viral stacks must be between 0 and 10")
    cls = SharedHeatClockTarget if shared_heat_clock else DummyTarget
    target = make_target(eximus, cls)
    if preprimed_viral_stacks:
        target.viral_expiries.extend([6.0] * preprimed_viral_stacks)
        target.record_status("VIRAL", 0.0, 6.0)
    return target


def _summarize(outcomes: list, attempted: int, *, room: bool) -> dict:
    attr = "clear_time" if room else "ttk"
    observed = [result for result in outcomes if math.isfinite(getattr(result, attr))]
    if not observed:
        return {"attempted": attempted, "timed_out": attempted,
                "mean_s": None, "median_s": None, "p90_s": None}
    times = [getattr(result, attr) for result in observed]
    result = {
        "attempted": attempted,
        "timed_out": attempted - len(observed),
        "mean_s": statistics.mean(times),
        "median_s": sample_percentile(times, 0.5),
        "p90_s": sample_percentile(times, 0.9),
        "reload_pct": 100 * sum(r.reloads > 0 for r in observed) / len(observed),
        "mean_reloads": statistics.mean(r.reloads for r in observed),
    }
    if room:
        result["mean_tendrils_per_tick"] = statistics.mean(
            r.average_tendrils_per_tick for r in observed)
    else:
        cap_times = [r.viral_cap_time for r in observed if r.viral_cap_time is not None]
        result.update({
            "viral_cap_pct": 100 * len(cap_times) / len(observed),
            "viral_cap_median_s_if_reached": (sample_percentile(cap_times, 0.5)
                                             if cap_times else None),
            "viral_stacks_median_at_death": sample_percentile(
                (r.final_viral_stacks for r in observed), 0.5),
            "heat_procs_mean_until_death": statistics.mean(r.heat_procs for r in observed),
            "overguard_break_median_s": sample_percentile(
                (r.overguard_break_time for r in observed), 0.5),
        })
    return result


def _paired(old, new, *, room: bool) -> dict | None:
    attr = "clear_time" if room else "ttk"
    pairs = [(getattr(a, attr), getattr(b, attr))
             for a, b in zip(old, new, strict=True)
             if math.isfinite(getattr(a, attr)) and math.isfinite(getattr(b, attr))]
    if not pairs:
        return None
    diffs = [b - a for a, b in pairs]
    mean = statistics.mean(diffs)
    interval = None
    if len(diffs) > 1:
        error = 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs))
        interval = [mean - error, mean + error]
    return {"complete_pairs": len(pairs),
            "mean_new_minus_old_s": mean,
            "approx_95pct_monte_carlo_interval_s": interval,
            "new_faster_pct": 100 * sum(b < a for a, b in pairs) / len(pairs),
            "equal_pct": 100 * sum(b == a for a, b in pairs) / len(pairs)}


class _StartSettings(TypedDict):
    """Start-of-shot settings shared by the single-target and room models."""

    starting_tendrils: int
    starting_flare_stacks: int
    heat_seed_mode: str


def compare(name: str, *, eximus: bool, arcane: str, initial_flare: int,
            tendrils: int, trials: int, seed: int, room: bool = False,
            n_enemies: int = 10, specs: tuple[RivenSpec, ...] = ALL_SPECS,
            shared_heat_clock: bool = False, heat_seed_mode: str = "per_hit",
            preprimed_viral_stacks: int = 0) -> dict:
    """Compare named variants with paired seeds, printing one JSON record."""
    if trials < 1:
        raise ValueError("trials must be positive")
    if len({s.label for s in specs}) != len(specs):
        raise ValueError("Riven labels must be unique")
    def factory():
        return target_factory(eximus, shared_heat_clock=shared_heat_clock,
                              preprimed_viral_stacks=preprimed_viral_stacks)
    # Room runs yield RoomResult, single-target runs OcucorTrial; both carry
    # the timing attribute that _summarize and _paired read.
    outcomes: dict[str, list[Any]] = {}
    with patch.object(nukor, "route_enemy_hit", discard_overguard_overflow):
        for spec in specs:
            build = spec.build(arcane)
            kwargs: _StartSettings = {
                "starting_tendrils": tendrils,
                "starting_flare_stacks": initial_flare,
                "heat_seed_mode": heat_seed_mode,
            }
            if room:
                outcomes[spec.label] = [
                    simulate_room(arcane, "Multishot", n_enemies, seed=seed + i,
                                  factory=factory, max_time=60.0,
                                  build_override=build, **kwargs)
                    for i in range(trials)
                ]
            else:
                outcomes[spec.label] = [
                    simulate(build, factory(), seed=seed + i, max_time=30.0, **kwargs)
                    for i in range(trials)
                ]
    pairs = {}
    for old, new in ((RIVEN_TWO_POS.label, RIVEN_THREE_POS.label),
                     (RIVEN_TWO_POS.label, RIVEN_LOWER_VIRAL.label),
                     (RIVEN_TWO_POS.label, RIVEN_LOW_VIRAL_TWO_POS.label),
                     (RIVEN_NO_RELOAD.label, RIVEN_THREE_POS.label)):
        if old in outcomes and new in outcomes:
            pairs[f"{new}_minus_{old}"] = _paired(outcomes[old], outcomes[new], room=room)
    record = {
        "scenario": name,
        "seed_start": seed,
        "settings": {
            "eximus": eximus,
            "arcane": arcane,
            "starting_flare_stacks": initial_flare,
            "starting_tendrils": tendrils,
            "room_targets": n_enemies if room else None,
            "overguard_break_hit_discards_overflow": True,
            "shared_heat_clock": shared_heat_clock,
            "heat_seed_mode": heat_seed_mode,
            "external_viral_stacks": preprimed_viral_stacks,
        },
        "variants": {spec.label: _summarize(outcomes[spec.label], trials, room=room)
                     for spec in specs},
        "paired": pairs,
    }
    print(json.dumps(record, allow_nan=False), flush=True)
    return record


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261028)
    parser.add_argument("--single-trials", type=int, default=800)
    parser.add_argument("--room-trials", type=int, default=120)
    parser.add_argument("--sensitivity-trials", type=int, default=400)
    args = parser.parse_args(argv)
    if min(args.single_trials, args.room_trials, args.sensitivity_trials) < 1:
        parser.error("trial counts must be positive")

    arcanes = (("enervate", ARCANE_ENERVATE, 0),
               ("flare_cold", ARCANE_FLARE, 0),
               ("flare_full", ARCANE_FLARE, FLARE_MAX_STACKS))
    # Main one-target comparisons, including two explicit causal controls.
    for eximus in (True, False):
        target = "eximus" if eximus else "ordinary"
        for tendrils in (4, 0):
            for arc_name, arcane, flare in arcanes:
                compare(f"single_{target}_{tendrils}_{arc_name}",
                        eximus=eximus, arcane=arcane, initial_flare=flare,
                        tendrils=tendrils, trials=args.single_trials, seed=args.seed)

    # Same-seed sensitivity variants; no claim that any Heat policy is proven.
    for sensitivity, kwargs in (
            ("shared_heat", {"shared_heat_clock": True}),
            ("first_heat_seed", {"heat_seed_mode": "first_hit"}),
            ("external_viral_10", {"preprimed_viral_stacks": 10})):
        for arc_name, arcane, flare in arcanes:
            compare(f"{sensitivity}_eximus_4_{arc_name}", eximus=True,
                    arcane=arcane, initial_flare=flare, tendrils=4,
                    trials=args.sensitivity_trials, seed=args.seed,
                    specs=REAL_SPECS, **kwargs)

    # Illustrative only: the ordinary single-hit Enervate AFCC is not a
    # simulation of charging/resetting when multiple tendrils hit targets.
    for eximus, tendrils in ((True, 4), (True, 0), (False, 4)):
        target = "eximus" if eximus else "ordinary"
        for arc_name, arcane, flare in arcanes:
            compare(f"room10_{target}_{tendrils}_{arc_name}", eximus=eximus,
                    arcane=arcane, initial_flare=flare, tendrils=tendrils,
                    trials=args.room_trials, seed=args.seed, room=True,
                    specs=REAL_SPECS)

    # A realizable, lower-grade Viral trait within the two-positive layout.
    for arc_name, arcane, flare in arcanes:
        compare(f"low_grade_viral_eximus_4_{arc_name}", eximus=True,
                arcane=arcane, initial_flare=flare, tendrils=4,
                trials=args.sensitivity_trials, seed=args.seed,
                specs=(RIVEN_TWO_POS, RIVEN_LOW_VIRAL_TWO_POS))

    # Isolate reload-speed effects in two artificial zero-tendril rooms.
    for arc_name, arcane, flare in (arcanes[0], arcanes[2]):
        compare(f"room10_eximus_0_{arc_name}_reload_control", eximus=True,
                arcane=arcane, initial_flare=flare, tendrils=0,
                trials=args.room_trials, seed=args.seed, room=True,
                specs=(RIVEN_TWO_POS, RIVEN_THREE_POS, RIVEN_NO_RELOAD))


if __name__ == "__main__":
    main()
