"""Reproduce the documented Jat slam-count *hypothesis* sweep as JSON Lines.

Results are not measured or validated gameplay TTK.  See
``docs/jat_kittag_expected_slams.md`` for definitions and caveats.

Example: python -m modules.jat_kittag_slam_count_sweep > results.jsonl
"""
from __future__ import annotations

import argparse
import json
import math

from .jat_kittag_slam_analysis import BUILD_BY_KEY
from .jat_kittag_slam_counts import Assumptions, BUILDS, TARGETS, Target, summarize

# Sample sizes per build/target.  A limited selection keeps the artifact small
# and highlights the uncertain hypotheses rather than pretending to bound all
# possible game behavior. Normal-status-only is intentionally diagnostic.
SCENARIOS = (
    ("six_stacks", Assumptions(),
     ("sp150_eximus", "icebind1000_eximus_6p", "sp150_normal"), 10000),
    ("twelve_stacks", Assumptions(affliction_stacks=12),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("two_sequential_six_stack_passes", Assumptions(affliction_passes=2),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("per_proc_aoe_ticks", Assumptions(shared_aoe_ticks=False),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("seed_seismic_x3", Assumptions(seed_slam_factor=3),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("break_electricity_seeds", Assumptions(magnetic_break_can_seed=True),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("trigger_on_direct_og_break", Assumptions(afflict_on_break=True),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("gas_bonus_on_arcane_stacks", Assumptions(clone_gas_bonus=True),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("fast_0_40s", Assumptions(interval=.4),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("slow_1_00s", Assumptions(interval=1.0),
     ("sp150_eximus", "icebind1000_eximus_6p"), 3000),
    ("normal_status_no_afflictions", Assumptions(affliction_stacks=0),
     ("sp150_eximus",), 1000),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261028)
    parser.add_argument("--sample-scale", type=float, default=1.0,
                        help="multiply all listed trial counts (default 1)")
    args = parser.parse_args()
    if not math.isfinite(args.sample_scale) or args.sample_scale <= 0:
        parser.error("--sample-scale must be finite and positive")
    for name, assumptions, target_keys, base_trials in SCENARIOS:
        trials = max(1, round(base_trials * args.sample_scale))
        for target_key in target_keys:
            target = Target.from_scaled(TARGETS[target_key]())
            for build_key in BUILDS:
                result = summarize(BUILD_BY_KEY[build_key], target, assumptions,
                                   trials=trials, base_seed=args.seed)
                result["scenario"] = name
                result["target_key"] = target_key
                print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
