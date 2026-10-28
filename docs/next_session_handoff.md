# Next-session handoff — 2026-10-28 (afternoon pass)

Snapshot of the repository, what the last session verified, and what to do next.
It is not a claim that every Warframe mechanic is correct. Start by checking
`git status`, `git log --oneline -12` and the current pull request; the code,
tests and reports are the source of truth if this note goes stale. The longer
handoff written by the previous pass — the full audit narrative, the bundle-size
and filter-refresh measurements — is in git history at
`8dea645:docs/next_session_handoff.md` and was condensed here.

- Branch: `arena/53406422-warframe-damage-calculator`
- HEAD at handoff: `470e9dd` (pushed)
- Base of this branch's work: `30b5a9f` (merge of PR #2)

## Verified state

Run from the repository root with `requirements.txt` and
`requirements-dev.txt` installed. All four were run at this commit:

```bash
python -m ruff check .                  # All checks passed
python -m mypy                          # Success: no issues found in 35 source files
python -m unittest discover -s tests -q  # 614 tests, OK (skipped=1), ~7.2 s
python -m compileall -q modules gui tests tools main.py build_database.py \
    build_gunco_tables.py build_riven_tables.py
```

- The single skip is the Qt integration suite: this sandbox has no PyQt6/GL, so
  **GUI edits are compile-checked only**. On a machine with Qt, run
  `QT_QPA_PLATFORM=offscreen WDC_REQUIRE_GUI_TESTS=1 python -m unittest discover -s tests -q`
  before trusting any `gui/` change; `tools/run_tests_ci.py` is what CI runs.
- Slowest module: `tests/test_database_migration.py` (~3.3 s). It parses the
  bundled exports repeatedly; the parsers are memoized on
  `(resolved path, mtime_ns, size)` in `modules/importer.py`, so changing files
  mid-run invalidates the cache on purpose.
- `tools/wiki_audit.py` works offline against saved page text only. With a
  fixture directory holding just `Damage__Blast_Damage.wikitext`,
  `python tools/wiki_audit.py --pages DIR --topic Blast` prints three `ok`
  claims plus one `unverified` claim and exits `0`; a full run with the other
  pages missing exits `2`. The live wiki is unreachable from this sandbox, so
  `docs/wiki_numbers.json` does not exist yet — see item 3 below.

## What this session changed

Earlier passes on this branch (`d54bd43` … `8dea645`) re-derived every formula
family from the WARFRAME Wiki, added the per-formula reports, the lint/type
gates, source-parse caching and `tools/wiki_audit.py`. This session added:

1. `4178f0a` **The calculator aggregates the equipped slots itself.** Callers
   that passed only `equipped_mods` (no pre-aggregated `mods` dictionary) lost
   +Damage, Bane and elemental bonuses: the seeded Grineer build reported
   `hud_total 934.2` / `quanta 5.40625` instead of `2525.1426` / `14.326562`.
   Slots are now authoritative and `inputs.mods` is ignored when slots are
   present; the dictionary-only path is unchanged. `Zairman` is aliased to
   `Zariman` so old saves keep their Bane multiplier.
2. `a3adebb` **The wiki audit no longer fails on a claim it cannot read.** The
   four-stack Blast cap is stated in prose on `Damage/Calculation`, so the
   keyword extraction cannot verify it and every Blast run exited `2` even
   with all readable numbers matching. Claims can now be `optional`: they
   report `[unverified]`, do not change the exit code, and still report code
   drift as `code-changed` (exit 1).
3. `7e00fb1` **A dying target detonates its Blast stacks** in the Kuva Nukor
   room model (Damage/Blast_Damage: ten stacks *or* the target dying, including
   a Blast proc from the killing blow). `RoomResult.death_detonations` reports
   them: the Frostbite build now has 8 death-driven detonations out of 31
   radials, previously none.
4. `3c98f61` **README describes the repository as a fork** kept for damage
   testing, with upstream credited and the app docs kept below.
5. `470e9dd` **Cleanup pass.** See the list below; the numbers of every bundled
   scenario are unchanged.

## Cleanup findings (what was wrong and why it mattered)

- Dead code: `modules/rounding.py` (no importer), the `app_paths` settings
  helpers, and `CalculationInputs.mod_for`. The README listed `settings.json`
  among the files the app keeps; the app never wrote or read one.
- Duplicated sources of truth: the six combined elements were spelled out twice
  in `calculator.py` while `constants.COMBINED_ELEMENT_TYPES` sat unused; the
  `Zairman` alias lived in the calculator *and* as a `BANE_CODE_MAP` key.
  Both now come from `modules/constants.py` (`faction_key`, the element set),
  and `ModAggregator.aggregate` normalises the faction too.
- An unknown faction raised `KeyError` from a table lookup; the calculator now
  raises `ValueError("Unknown faction: ...")`, matching the GUI's build
  preflight.
- `akarius_sim.corrosive_armor_factor` hardcoded `0.20 + 0.06n` next to unused
  `CORROSIVE_FIRST_STACK`/`CORROSIVE_PER_STACK` constants that documented the
  same numbers; it now uses them (values verified identical, 0.74/0.68/0.20).
- Constants no model read were removed (`SLAM_RADIUS`, `COMBO_DURATION`,
  `R_EFFICIENCY`, `RANK_STEPS`, `AOE_PROC_DELAY`, `CHAIN_RANGE_M`,
  `BLAST_RADIUS_M`, `VIRAL_BASE_DURATION`, `HUD_ROUNDING_PRECISION`,
  `DEFAULT_HUD_DECIMALS`, `FINAL_DAMAGE_DECIMALS`). The facts they recorded
  (10 m slam radius, 9 m chain, 5 m Blast radial, the 5 s combo window) are in
  the module docstrings.
- The GUI aggregated the slots a second time on every keystroke and passed the
  result as `mods`, which the calculator now ignores; both call sites pass only
  `equipped_mods` and the unused `mod_aggregator` attribute is gone.
- Non-finite export values are rejected inside the source parsers (once per
  unchanged file) instead of once per payload: `test_database_migration` went
  from 3.9 s to 3.3 s.
- `docs/wiki_formula_verification.md` claimed `test_wiki_cross_checks.py` holds
  18 tests; it holds 24.

## Repository map

- `main.py` → `gui/app.py`: the PyQt6 app. Startup migrates or bootstraps the
  AppData database (`%APPDATA%/WDC`, else `~/.local/share/WDC`).
- `modules/importer.py`, `database*.py`, `updater.py`, `export_safety.py`,
  `weapon_export_policy.py`: data pipeline, transactional migration, backups,
  staged export publication.
- `modules/calculator.py`, `mod_engine.py`, `mod_parser.py`, `models.py`,
  `status_damage.py`, `damage_routing.py`, `crit.py`, `enemy_scaling.py`,
  `constants.py`: the core model. Tables live only in `constants.py`.
- `modules/*_sim.py`, `*_comparison.py`, `jat_kittag_slam_*.py`: experimental
  research models; their reports are in `docs/`.
- `docs/formula_audit.md` (scope, source conflicts, open deviations) and
  `docs/wiki_formula_verification.md` (per-formula verdicts, dated pages) are
  the authoritative write-ups; `tools/wiki_audit.py` re-checks the numbers.
- `data/weapons.db` is a curated revision-3 snapshot, not live game data;
  `source/` holds the bundled exports and reference tables.

## Open items, in suggested order

1. **Three documented wiki deviations are still open** (see
   `docs/formula_audit.md`): Cold's critical-damage bonus is implemented and
   tested but no bundled scenario can produce a standalone Cold proc; the
   four-stack Blast cap is not exercised by any scenario; faction type
   modifiers are applied to Overguard, which the wiki does not confirm. Change
   these only with page evidence plus a scenario that shows the difference, and
   update both reports.
2. **Jat Kittag Riven crit damage:** `jat_kittag_sim.R3_CRIT_DAMAGE` is `1.013`
   (three decimals) while `jat_kittag_slam_analysis.R3_CRIT_DAMAGE` is the
   derived `1.0125` midpoint. The 0.05 % gap is documented in a comment; the
   tests pass either way, but published numbers in `docs/jat_kittag_*.md` were
   generated with `1.013`. Decide one value, regenerate the affected reports,
   and say so in the commit.
3. **Create `docs/wiki_numbers.json` from a networked machine** and commit it,
   so the audit's `--baseline` diff becomes usable in review. Then decide
   whether a weekly audit run is worth a workflow (it must tolerate an
   unreachable wiki: exit 2 means "incomplete", not "wrong").
4. **Exercise the Qt suite** (`WDC_REQUIRE_GUI_TESTS=1`) for the GUI changes in
   `470e9dd`/`4178f0a`; nothing here could run it.
5. **Remote CI:** inspect `gh pr checks` and the latest Actions run rather than
   trusting this note. The historical Windows full-suite failure was a
   SQLite-handle cleanup bug that fixtures now close explicitly; confirm it
   passes. **Windows packaging is very low priority** (possibly 2028) — do not
   disable or delete the packaging job without asking.
6. **Live DE refresh** is untested here (network blocked); the updater's
   staging, markers and recovery are covered by fixtures only.
7. **Longer-standing work:** model attack components instead of treating one
   export row as one hit (Grimoire's 100 direct + 50 radial), give Rivens an
   explicit identity instead of the name-substring heuristic, strengthen
   publication safety for concurrent use, and extend mod-compatibility coverage
   only with evidence.

## Reproduction recipes

```bash
# Full gate
python -m ruff check . && python -m mypy && python -m unittest discover -s tests -q

# One module, timed
time python -m unittest tests.test_database_migration -q

# Offline wiki audit against saved text (no network)
mkdir -p /tmp/wiki_pages   # put Damage__Blast_Damage.wikitext there
python tools/wiki_audit.py --pages /tmp/wiki_pages --topic Blast

# Jat sweep smoke test, if touching the slam models
python -m modules.jat_kittag_slam_count_sweep --sample-scale 0.01 > jat-smoke.jsonl
```

Delivered artifacts must not be regenerated casually: the full Jat sweep uses
seed `20261028`, 170,000 trials over 44 JSONL records, and
`docs/jat_kittag_expected_slams_results.jsonl` has SHA-256
`94422cf20a535c30d58e32fd584bdca1672ae37c8a0edd4232cc22112218c982`.
Simulated numbers are model output, not measurements; keep seeds, trial counts
and timeouts with any new result, and check attempted-versus-killed trials.

## Do not

- Do not silently change assumptions, seeds or delivered result artifacts; if
  evidence changes a mechanic, update tests and reports and separate researched
  facts from assumptions and model output.
- Do not reintroduce the duplicated tables this pass removed: factions, the
  combined-element set and the bane map live in `modules/constants.py`.
- Do not report a CI pass from a pending or failed run, and do not present
  sandbox results as native-display, Windows-installer or in-game validation.
