"""Reproduce the experimental Akarius Prime Viral/Corrosive comparison.

Run ``python -m modules.akarius_comparison`` from the repository root. This
is a collection of one-target Monte Carlo scenarios, not a validated room
simulator or a prediction of in-game time to kill. See the accompanying report
for assumptions and the meaning of each sensitivity.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from contextlib import AbstractContextManager, nullcontext
from dataclasses import replace
from typing import Any
from unittest.mock import patch

import modules.kuva_nukor_sim as nukor
from modules.akarius_sim import (
    RIVEN_CORROSIVE,
    RIVEN_VIRAL,
    AkariusTarget,
    akarius_dummy_factory,
    build_akarius,
    simulate,
)
from modules.damage_routing import RoutedDamage, route_enemy_hit, status_vulnerability
from modules.enemy_scaling import HEAVY_GUNNER, MODE_STEEL_PATH, scale_enemy
from modules.trial_statistics import sample_percentile


def ordinary_gunner_factory() -> AkariusTarget:
    """A fresh level-150 Steel Path, non-Eximus Heavy Gunner."""
    scaled = scale_enemy(HEAVY_GUNNER, level=150, eximus=False,
                         mode=MODE_STEEL_PATH)
    return AkariusTarget(scaled.health, scaled.armor, scaled.overguard)


def _copy_as(target: AkariusTarget, cls: type[AkariusTarget]) -> AkariusTarget:
    return cls(target.health, target.max_armor, target.overguard)


class SharedHeatClockTarget(AkariusTarget):
    """Alternate unvalidated assumption: every live stack contributes per pulse."""

    def consume_heat_tick(self, when: float, duration: float):
        if self.next_heat_tick(duration) != when:
            return []
        self.prune(when, duration)
        self._next_heat_tick = when + 1.0
        return list(self.heat_procs)


def _preprime_viral(target: AkariusTarget) -> AkariusTarget:
    """Five external Viral stacks at t=0, expiring after six seconds."""
    target.viral_expiries.extend([6.0] * 5)
    target.record_status("VIRAL", 0.0, 6.0)
    return target


def neutral_overguard_route(damage_by_type, *, overguard, armor,
                            magnetic_stacks=0, viral_stacks=0,
                            faction_type_modifiers=None, armor_bypass=False):
    """Sensitivity: faction damage-type modifiers apply to health, not OG.

    As in the default model, a breaking mixed hit retains the same fraction of
    every damage type for the health layer. This is a stress test for an
    unresolved routing assumption, not a claim of verified engine behavior.
    """
    if overguard <= 0:
        return route_enemy_hit(
            damage_by_type, overguard=0, armor=armor,
            magnetic_stacks=magnetic_stacks, viral_stacks=viral_stacks,
            faction_type_modifiers=faction_type_modifiers,
            armor_bypass=armor_bypass)
    potential = status_vulnerability(magnetic_stacks) * sum(
        max(0.0, amount) * (1.5 if kind == "VOID" else 1.0)
        for kind, amount in damage_by_type.items())
    if potential <= 0:
        return RoutedDamage(0.0, 0.0, False)
    absorbed = min(overguard, potential)
    fraction = 1.0 - absorbed / potential
    health = route_enemy_hit(
        {kind: amount * fraction for kind, amount in damage_by_type.items()},
        overguard=0, armor=armor, viral_stacks=viral_stacks,
        faction_type_modifiers=faction_type_modifiers,
        armor_bypass=armor_bypass).health
    return RoutedDamage(absorbed, health, potential >= overguard)


def discard_overguard_overflow_route(damage_by_type, **kwargs):
    """Sensitivity: discard the health overflow of the hit that breaks OG.

    This tests an asserted depletion-gate behavior; it does not add a timed
    invulnerability window. The Wiki distinguishes enemy and player gates.
    """
    result = route_enemy_hit(damage_by_type, **kwargs)
    if result.broke_overguard:
        return RoutedDamage(result.overguard, 0.0, True)
    return result


def _constant_mean_crit(build):
    # Preserve expected direct-hit critical damage while removing crit-tier
    # variability. It is not a simulation of Enervate's actual reset cycle.
    mean_factor = 1.0 + (build.afcc_pct / 100.0) * (build.crit_multiplier - 1.0)
    return replace(build, afcc_pct=100.0, crit_multiplier=mean_factor)


def _summarize(results, attempted):
    observed = [r for r in results if math.isfinite(r.ttk)]
    ttks = [r.ttk for r in observed]
    if not observed:
        return {"attempted": attempted, "timed_out": attempted,
                "mean": None, "median": None, "p90": None}
    return {
        "attempted": attempted,
        "timed_out": attempted - len(observed),
        "mean": statistics.mean(ttks),
        "median": sample_percentile(ttks, 0.5),
        "p90": sample_percentile(ttks, 0.9),
        "overguard_break_median": sample_percentile(
            (r.overguard_break_time for r in observed), 0.5),
        "final_armor_median": sample_percentile((r.final_armor for r in observed), 0.5),
        "shots_mean": statistics.mean(r.shots for r in observed),
        "before_first_reload_pct": 100.0 * sum(r.reloads == 0 for r in observed) / len(observed),
    }


def compare(name, target_factory, trials, seed, *, direct_hits=True,
            build_transform=None, neutral_og=False, discard_og_overflow=False,
            blast_cap=None):
    """Run paired seeds and print one JSON record, with timeout counts."""
    if trials < 1:
        raise ValueError("trials must be positive")
    if neutral_og and discard_og_overflow:
        raise ValueError("routing sensitivities must be tested separately")
    build_transform = build_transform or (lambda b: b)
    # Module globals are patched only within this serial sensitivity run.
    if neutral_og:
        og_patch: AbstractContextManager[Any] = patch.object(
            nukor, "route_enemy_hit", neutral_overguard_route)
    elif discard_og_overflow:
        og_patch = patch.object(nukor, "route_enemy_hit", discard_overguard_overflow_route)
    else:
        og_patch = nullcontext()
    if blast_cap is not None:
        import modules.akarius_sim as akarius
        cap_patch: AbstractContextManager[Any] = patch.object(
            akarius, "BLAST_MAX_STACKS", blast_cap)
    else:
        cap_patch = nullcontext()
    results = {}
    with og_patch, cap_patch:
        for riven in (RIVEN_VIRAL, RIVEN_CORROSIVE):
            build = build_transform(build_akarius(riven))
            results[riven] = [simulate(build, target_factory(), seed=seed + i,
                                       direct_hits=direct_hits)
                              for i in range(trials)]
    viral = results[RIVEN_VIRAL]
    corrosive = results[RIVEN_CORROSIVE]
    differences = [c.ttk - v.ttk for v, c in zip(viral, corrosive, strict=True)
                   if math.isfinite(v.ttk) and math.isfinite(c.ttk)]
    paired = None
    if differences:
        mean = statistics.mean(differences)
        interval = None
        if len(differences) > 1:
            error = 1.96 * statistics.stdev(differences) / math.sqrt(len(differences))
            interval = [mean - error, mean + error]
        paired = {"complete_pairs": len(differences),
                  "mean_corrosive_minus_viral_s": mean,
                  "approx_95pct_mc_interval_s": interval}
    record = {"scenario": name, "seed_start": seed,
              "direct_hits": direct_hits,
              "viral": _summarize(viral, trials),
              "corrosive": _summarize(corrosive, trials),
              "paired": paired}
    print(json.dumps(record, allow_nan=False), flush=True)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261028)
    parser.add_argument("--eximus-trials", type=int, default=5000)
    parser.add_argument("--ordinary-trials", type=int, default=2500)
    parser.add_argument("--splash-trials", type=int, default=2500)
    parser.add_argument("--sensitivity-trials", type=int, default=2000)
    args = parser.parse_args(argv)
    if min(args.eximus_trials, args.ordinary_trials, args.splash_trials,
           args.sensitivity_trials) < 1:
        parser.error("trial counts must be positive")

    eximus = akarius_dummy_factory
    ordinary = ordinary_gunner_factory
    compare("direct_eximus", eximus, args.eximus_trials, args.seed)
    compare("direct_ordinary", ordinary, args.ordinary_trials, args.seed)
    compare("splash_only_eximus", eximus, args.splash_trials, args.seed,
            direct_hits=False)
    compare("splash_only_ordinary", ordinary, args.splash_trials, args.seed,
            direct_hits=False)

    n = args.sensitivity_trials
    compare("shared_heat_pulse_eximus",
            lambda: _copy_as(eximus(), SharedHeatClockTarget), n, args.seed)
    compare("four_stack_blast_eximus", eximus, n, args.seed, blast_cap=4)
    compare("constant_average_crit_eximus", eximus, n, args.seed,
            build_transform=_constant_mean_crit)
    compare("neutral_overguard_eximus", eximus, n, args.seed, neutral_og=True)
    compare("discard_overguard_overflow_eximus", eximus, n, args.seed,
            discard_og_overflow=True)
    compare("five_external_viral_eximus", lambda: _preprime_viral(eximus()),
            n, args.seed)
    compare("five_external_viral_ordinary", lambda: _preprime_viral(ordinary()),
            n, args.seed)


if __name__ == "__main__":
    main()
