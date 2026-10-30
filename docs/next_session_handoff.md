# Next-session handoff

## Current state

- Repo: `/home/user/Warframe-Damage-Calculator` (`Man1nWhite/Warframe-Damage-Calculator`).
- Work happens on branch `arena/8c8c0412-warframe-damage-calculator`; do not switch or rename it.
- Base: `9b2a1d0` (merge of PR #9). Uncommitted work is the current audit round; read `git status` and the diff before repeating investigations.
- The audit brief is unchanged: keep finding and fixing confirmed defects, preserve user data, and state verification limits honestly.

## Verification environment

- Python venv: `/home/user/.cache/wdc-venv`; Qt shims: `/home/user/.cache/wdc-qtlibs` (`libxkbcommon.so.0` via `xkb.map`, `libGL`, `libEGL`, `libdbus-1`); exports in `/home/user/.cache/wdcenv.sh`.
- These caches are outside the repository and are not snapshotted. Rebuild them (venv + shim libraries) if a later session starts without them; `libxkbcommon.so.0` is the one that blocks `QtGui` import on a bare image.
- Offscreen recipe: `source /home/user/.cache/wdcenv.sh && WDC_REQUIRE_GUI_TESTS=1 $VENV tools/run_tests_ci.py`.

## Verification status (this round)

- Full required-offscreen suite: **868 tests OK** in ~40 s (`tools/run_tests_ci.py`, `WDC_REQUIRE_GUI_TESTS=1`).
- `ruff check .` clean; `python -m mypy` clean (**38 source files**); `tools/bench_models.py --check` reproduces the stored digest `53f9bcd7469a73ce…` (simulators unchanged).
- Coverage (informational, not enforced): 93 % of `modules/` and `gui/` statements, measured before this round's edits.

## What changed this round

- **Both Ocucor artifacts were stale and are regenerated.** `docs/ocucor_enervate_flare_results.jsonl` (17 scenarios, 35,100 runs) and `docs/ocucor_viral_dilution_results.jsonl` (35 scenarios, 50,880 trials) no longer reproduced after the Cold-aware critical-damage change; means moved by up to ~0.05 s while the steady-state ordering held. The two reports' tables and prose now match the new artifacts.
- **Artifact drift guard added.** `modules/ocucor_comparison.scenarios(...)` and `modules/ocucor_viral_comparison.scenarios(...)` now own the scenario list, order and arguments, and `tests/test_ocucor_artifacts.py` checks every record's name, order, settings and trial counts, then re-runs the cheapest scenario of each artifact at its recorded trial count and requires an exact match (~9 s of the suite).
- **`require_json_depth` no longer lets unbalanced closing brackets buy headroom**; the running depth stops at zero. Regression test added.
- **Dead parameter removed:** `build_application(db_path)` ignored its argument (only `main.py` called it with one).
- **`.coverage` and coverage output are ignored** so local coverage runs cannot be committed by accident.

## Known open items (not defects)

- The artifacts still need manual regeneration when a simulator changes; the guard only re-runs one scenario per artifact, so a room-model-only change is caught by review, not by that test. Both reports state this.
- Three `PLW2901` loop-variable reassignments (`database_migration.py`, `verglas_prime_sim.py`, `weapon_export_policy.py`) are readable as written and were left alone rather than reshaped for a lint rule the project does not enable.
- The mod-slot `QComboBox` is editable but only changes state through `currentIndexChanged`: text typed without picking an item leaves the previous mod selected while the box shows other text. This is a UI wart, not a calculation bug; changing it needs a product decision.
- `_bane_bonus`'s label-free fallback treats a stored `1.0` as a +100 % bonus. No production call site omits the stat label, so it is unreachable today; do not "fix" it without deciding how `+100 %` bonuses are stored.
- `_publish_seed_exports_locked`/`seed_source_files` deliberately fail loudly when the filesystem has no hard links (see `tests/test_app_paths.py`), instead of risking a partial copy.

## Next steps

1. Continue the targeted audit; add a regression test with every confirmed fix.
2. Re-run the full offscreen suite, `ruff`, `mypy`, and `bench_models.py --check` if simulator or GUI code changes.
3. Regenerate the Ocucor artifacts (and update both reports) whenever `ocucor_sim`, `kuva_nukor_sim` routing, or the shared crit/status models change.
4. Keep documentation concise and consistent; never describe simulator output as in-game validation.
