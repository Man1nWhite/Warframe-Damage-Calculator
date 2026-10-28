# Development handoff — 2026-10-28

This is a snapshot of the repository audit and the work needed next, not a
claim that every Warframe mechanic has been verified. Start by checking
`git status` and reviewing the diff. The working tree at handoff contains
substantial intentional calculator, test, documentation, database, and
simulation changes; **do not reset or discard them**. The source files and
saved reports are the source of truth if this note becomes outdated.

## What the project does

- `main.py` starts the PyQt6 application after checking/migrating the app-data
  database. `gui/app.py` implements the weapon/mod pickers, calculator, build
  JSON, comparison and data settings.
- `modules/importer.py` converts the saved DE weapon and upgrade ZIPs plus an
  optional spreadsheet to SQLite. `modules/database_backup.py`,
  `modules/database_revision.py` and `modules/database_migration.py` manage
  backups, the schema/data revision and the transactional legacy upgrade. The
  checked-in `data/weapons.db` is a corrected **revision 3 snapshot**, not
  live game data. `modules/weapon_export_policy.py` handles one reviewed
  name collision and rejects unrecognized conflicting modeled rows.
- `modules/calculator.py`, `modules/mod_engine.py`, `modules/mod_parser.py`,
  `modules/models.py`, `modules/status_damage.py`, `modules/damage_routing.py`
  and `modules/enemy_scaling.py` implement the core and shared formulas. The
  desktop treats an exported row as a non-critical hit to health, **not** a
  full combat or time-to-kill model. Some rows already combine separate hits,
  so their displayed Final value is not a per-hit estimate.
- `modules/*_sim.py` and the newer `*_comparison.py` / Jat slam modules are
  research experiments. See [the formula audit](formula_audit.md),
  [damage reference](damage_formula_reference.md), and
  [target assumptions](target_dummy_models.md) for the specific coverage and
  caveats. Passing tests shows internal consistency, not gameplay validation.
- `source/` contains the bundled export and reference snapshots; build JSON,
  user settings, downloaded exports and the working database normally live
  separately in `%APPDATA%/WDC` or `~/.local/share/WDC`.

## Changes and findings from this audit

1. **Data refresh:** `modules/updater.py` validates complete LZMA streams,
   retains a narrowly checked DE known-size-header compatibility path, parses
   UTF-8/JSON without altering string whitespace, stages both ZIPs on the
   destination filesystem, and validates the parsed import in temporary
   SQLite before publication. Ordinary failures roll back replacements.
   `modules/export_safety.py` detects a retained publication marker after a
   process interruption or failed rollback and refuses a potentially mixed
   pair. `tests/test_updater.py` includes staged-write and replacement fault
   injection and a subprocess exiting immediately after the first replacement.
   [README recovery instructions](../README.md#recovering-an-interrupted-data-refresh)
   explain how to restore both old files. First-time seeding now stages and
   publishes the pair with the same marker, and never fills just one missing
   saved ZIP from a different bundled snapshot. This is **not** cross-process
   locking or guaranteed power-loss durability; export publication and DB
   rebuild are separate operations.
2. **Database/resource handling:** repositories now close SQLite connections
   explicitly, import transactions roll back on failure, and workbooks close
   even if worksheet loading fails. Legacy migration preserves unrelated/custom
   rows subject to its coverage checks. A manual full rebuild still replaces
   custom mods and effects, but now first makes a SQLite-consistent backup of an
   existing database, reports its path, and aborts if the backup fails or an
   intervening write is detected. A new/empty database gets no empty backup;
   the empty-file check is guarded against concurrent initialization. Fault
   tests include committed WAL data, a preflight race, and a process exit
   mid-transaction. See [README database safety](../README.md#existing-databases-and-backups)
   and [manual rebuild](../README.md#rebuilding-the-database-manually).
3. **Saved builds:** the GUI preflights JSON, compatible weapons/mods/ranks and
   finite numeric inputs before applying a build, clears omitted slots, and
   saves via a same-directory temporary file and atomic replacement. GUI tests
   exercise invalid files and preservation of the previous file on a failed
   save. This is not a power-loss guarantee.
4. **Performance:** equipped-mod and comparison lookups batch ranked mod
   effects in one connection and use indexed predicates, while preserving
   duplicate slots and different ranks. On this local hot-cache microbenchmark,
   1,000 sets of eight lookups had median times of about **1.217 s separately
   versus 0.240 s batched** (~5.1x); this is not an end-to-end GUI benchmark.
   Requests are chunked below the traditional SQLite parameter limit. Jat fight
   constants are computed once per fight rather than on each slam. Three local
   2,000-trial timings indicated roughly a 5% median improvement (not a
   controlled benchmark); the full existing 44-record/170,000-trial Jat sweep
   regenerated byte-for-byte on the same interpreter and seed. No global cache
   of mutable build assumptions was added. `WDC.spec` no longer collects every
   unrelated PyQt6 submodule: in one local Linux build the bundle fell from
   about **297 MiB to 169 MiB** and missing-library warnings fell from 46 to 9.
   These figures depend on the Python/Qt environment and are not Windows build
   measurements. A later offscreen widget microbenchmark with eight equipped
   slots and 53 available mods measured 25 unchanged filter refreshes at a
   median **0.412 s before versus 0.083 s after** (~5x; five runs each, same
   local interpreter/data). Intermediate slot signals no longer cause eight
   recalculations per refresh; real selection/rank changes recalculate once
   after all slots update. Clearing all slots now also recalculates once. This
   narrow synthetic measurement is not end-to-end performance or a display test.
5. **Cleanup:** three tracked stale `.bak` files were removed only after each
   was checked byte-for-byte against `HEAD`; Git retains those historical
   versions. `.gitignore` excludes backup and local tool caches. Focused Ruff
   `F,E9` checks were added to CI via `requirements-dev.txt`; historical
   simulator compatibility re-exports remain available. Invalid negative or
   non-finite proc weights are rejected in `modules/status_damage.py`.
6. **Riven table accuracy:** removed impossible trait signs (JSON `null`, CSV
   blank), fixed Punch Through meters and the display sign of the negative-only
   combo-gain trait, and regenerated the 1.2 snapshots. The Wiki's rank table
   conflicts with its Initial Combo legend; the Melee Combo page explicitly says
   Initial Combo is positive-only, which the generator follows. Other existing
   rollable values were compared and did not change; previous simulation
   artifacts were not regenerated. The Alternox loader skips unavailable cells
   and now respects plain/faction units; its compared percent values did not
   change. Binary32 rounding, weapon-specific restrictions and spliced traits
   remain outside this table.
7. **Imported direct effects:** `modules/mod_parser.py` now accepts exact
   damage labels (including `Melee Damage`), rejects leading and recognized
   cross-token conditions, and no longer reads Blast radius, physical
   conversion, or other unrelated text as direct damage. `modules/mod_effect_policy.py` checks official saved
   effects on reads, excludes Conclave and a known Proton Snap legacy false
   positive, and leaves custom effects alone. A rank-10, +200% export entry named
   Pressure Point does not match the Wiki variants and is excluded pending
   identification. Revision 2 reparses saved official mod rows; the later
   revision-3 upgrade refreshes revision-1 mods plus the targeted, guarded
   Grimoire correction described below, while revision 0 also repairs covered
   weapons. Untyped Tome compatibility no longer falls back to a generic
   primary slot. Coverage checks require removed old effect fragments to occur
   in the original source rank, even if another effect survives at that rank.
   Actual Git HEAD revision-0 and the prior revision-1 DB migrated successfully
   in temporary copies. No personal AppData database was overwritten. Rebuilds
   and legacy upgrades still need complete saved export files and are not a
   substitute for reviewing unfamiliar conditions.
8. **Bounded mod compatibility:** `modules/mod_compatibility.py` filters
   rifle/shotgun families and selected augment/subclass cases, excludes known
   unsupported categories and Cannonade trigger rules, and warns that the
   result is not a full legality check. `source/weapon_mod_classes.json` is an
   attributed, pinned WFCD extract with the Wiki's Coda Bubonico shotgun
   override; `tools/build_weapon_mod_classes.py` reproduces it, with license at
   `source/WFCD_LICENSE.txt`. For unknown official primary families,
   family-restricted mods are hidden, not guessed; custom mods remain available. Saved builds containing now-hidden
   mods fail preflight without altering the JSON or current UI. Offscreen widget
   regressions cover rifle/shotgun selection, weapon augments, Primed Pressure
   Point's 2.65× base multiplier, custom mod save/load, and rejection of an
   incompatible saved build. Duplicate/conflicting mods, capacity, and many
   conditional rules remain unmodeled.
9. **Riven element ordering:** the mod aggregator formerly read Riven primary
   effects in listed order while the calculator reversed them, producing
   contradictory totals. Both now call `ordered_mod_effects` in
   `modules/mod_engine.py`; mixed primary/secondary/faction effects, repeated
   types and multiple slots have a regression, as do all 256 four-primary
   sequences across ordinary and Riven slots. This rule still identifies a
   Riven by `Riven` in its name, not all generated Riven names. A bare
   pre-aggregated `mods` dictionary also cannot express full slot provenance.
   The [Wiki damage hierarchy](https://wiki.warframe.com/w/Damage#Modding)
   gives the last listed Riven primary priority; this is not gameplay testing.
10. **Grimoire collision and hit scope:** DE's saved export has both the player
    Grimoire and a 25-damage Doppelganger under the same name; the old import
    overwrote the player row. `modules/weapon_export_policy.py` explicitly
    prefers the player ID independent of source order and fails on a missing
    player or unknown same-name conflicts in modeled fields. It retains both
    rows for legacy coverage; IDs with identical modeled fields are not fully
    disambiguated. Revision 3 repairs an exact saved-export Doppelganger match
    with a backup, but refuses a missing/mismatched source or edited legacy
    row. Revision 1 performs this repair alongside its mod refresh; revision 2
    changes only the targeted weapon. Tests cover custom preservation, partial
    sources, write failure and abrupt process exit. Actual revision-0, 1 and
    2 databases were migrated in temporary copies; the revision-2 candidate
    changed exactly one weapon and no mod/effect rows, and matched a fresh
    import. The checked-in snapshot was updated; no personal AppData was used.
    The [Grimoire Wiki](https://wiki.warframe.com/w/Grimoire) splits primary
    fire into 100 direct and 50 radial Electricity, whereas its public export
    reports 150 together. The desktop treats that as one hit: it does **not**
    model separate quantization, radial falloff or alternate fire. The GUI and
    README now warn about aggregated rows; an attack-component model is future
    work, not a verified change to previous simulations.
11. **Filter correctness:** when a weapon's available mod list became empty,
    the old UI could clear selections without recalculating, leaving stale
    totals. Filter refresh now recalculates exactly once if it drops a mod or
    clamps its rank and zero times if it merely changes the displayed picker.
    The offscreen tests also verify preserved selections and result widgets.

The checked-in SQLite snapshot was checked with `PRAGMA integrity_check` and
returned `ok`, with revision 3, 827 weapons, 1,594 mods and 1,856 effects at
the time of this audit. It remains a dated, curated source snapshot: a valid
SQLite file does not prove all game data or formulas are current.

## Validation and reproducibility

Install the runtime dependencies from `requirements.txt`; install
`requirements-dev.txt` for the focused lint. The following commands are
cross-platform except for the shell-specific environment-variable syntax:

```bash
python -m ruff check --select F,E9 modules gui tests tools main.py build_database.py build_gunco_tables.py build_riven_tables.py
python -m compileall -q modules gui tests tools main.py build_database.py build_gunco_tables.py build_riven_tables.py
git diff --check
QT_QPA_PLATFORM=offscreen WDC_REQUIRE_GUI_TESTS=1 python -m unittest discover -s tests -v
```

The final local run on Python 3.11 passed **546 tests**, including the real
Qt integration tests with `WDC_REQUIRE_GUI_TESTS=1`; none were skipped. The
local log was `/tmp/wdc-audit-final-tests.log` (temporary, not a deliverable).
On
Linux install Qt's native GL/EGL, xkbcommon and D-Bus libraries first; see the
[README tests section](../README.md#tests). On Windows set those two variables
with the shell's usual syntax. The GitHub Actions matrix specifies Linux
3.11/3.12 and Windows 3.12 with Qt required, but **remote CI has not been run
as part of this audit**. The local sandbox used `offscreen` and temporary
native-library workarounds; it does not establish native display/GPU rendering.
A Linux PyInstaller bundle was built with a temporary shared Python runtime.
A newly rebuilt, instrumented bundle passed offscreen weapon/mod calculation,
save/load, Coda Bubonico's bundled shotgun classification, Primed Pressure
Point's base multiplier, and isolated offline rebuild including the player
Grimoire collision fix; its 827 weapon rows passed SQLite integrity check. A
second rebuild confirmed that its retained backup contains custom data removed
from the rebuilt catalog. The temporary log was
`/tmp/wdc-audit-final-packaging.log`. Reproduce that optional check with
`python -m pip install -r requirements-build.txt` followed by
`python tests/run_packaging_smoke.py`. The test-only spec and runtime hook are
not included in the production bundle. The workflow defines a Windows
packaging-smoke job, but it has not run remotely. **Windows packaging is very
low priority**, with a possible revisit in **2028** rather than a current
requirement. This priority does not disable the existing automatic job: the
current workflow would still schedule it on pushes and pull requests. Linux
offscreen success is not a Windows EXE or installer test. Runtime/build
dependencies are not fully pinned, so results may vary with future releases.

### Remote CI route (checked 2026-10-28)

At a **pre-publication** check, the repository's default branch had no
registered GitHub Actions workflow, no runs were listed, and the session branch
was not yet on the remote. Those observations are historical; check Git and
GitHub again for the current PR, branch, and workflow status. A read-only
request for Actions repository-permission settings returned HTTP 403 ("Resource
not accessible by integration"), despite the repo view reporting an admin role;
this does **not** establish whether Actions is enabled or whether a
push-triggered run would work. A local PyYAML structural check confirmed the
expected triggers, matrix, required GUI environment and packaging job; this is
neither `actionlint` nor a remote Actions execution.

The user subsequently requested a pull request for this work. A push may
trigger the workflow from the pushed commit if Actions is enabled. Inspect the
branch's run and failed logs with:

```bash
gh run list --branch arena/2d220a36-warframe-damage-calculator
gh run watch <run-id> --exit-status
gh run view <run-id> --log-failed
```

Do not claim a remote pass until the run finishes. `workflow_dispatch` cannot
be used for a workflow that is not present on the default branch. If Actions
settings or logs remain inaccessible, check the integration's Actions
permissions or repository settings rather than assuming the code passed. Future
publication should be approved by the user; the GitHub repository is public.

The current workflow includes Windows's ordinary test matrix entry **and** a
separate automatically scheduled Windows packaging job. Packaging is very low
priority (possibly 2028); do not silently disable or delete that job. Ask the
user before changing its scheduling if they do not want it to run during
remote CI.

For quick Jat smoke tests, use a reduced trial scale and write to a new file:

```bash
python -m modules.jat_kittag_slam_count_sweep --sample-scale 0.01 > jat-smoke.jsonl
```

The full sweep without `--sample-scale` uses seed `20261028`, 170,000 trials
across 44 JSONL records, and can be compared against
`docs/jat_kittag_expected_slams_results.jsonl`. Its SHA-256 at handoff is
`94422cf20a535c30d58e32fd584bdca1672ae37c8a0edd4232cc22112218c982`.
Do not overwrite that delivered artifact without deliberately reviewing changed
assumptions and results.
[The Jat report](jat_kittag_expected_slams.md) defines both eight-mod builds,
targets, metrics and sensitivity cases. The other delivered reports include
reproduction commands: [Kuva Nukor](kuva_nukor_three_mod_comparison.md),
[Akarius Prime](akarius_prime_viral_corrosive_comparison.md),
[Ocucor Enervate/Flare](ocucor_enervate_flare_comparison.md), and
[Ocucor Viral weighting](ocucor_viral_dilution_comparison.md). Many simulations
report only successful kills in TTK statistics; always check attempted trials
and timeouts. Seeds and trial counts belong with any new result.

## Known limitations and suggested next work

1. **Continue the formula-by-formula audit.** The user's request is to check
   formulas against the official Wiki, but the existing audit verifies selected
   examples and records disagreements; it is not exhaustive. Record the exact
   page/revision, date, assumptions and independent fixtures when extending it.
   Review negative IPS/combined-element quantization before imposing any new
   blanket clamp: the [calculation page](https://wiki.warframe.com/w/Damage/Calculation)
   and available patch/forum evidence do not settle every interaction.
   Review the dated GunCO/Riven catalogs and source data for subsequent updates.
2. **Keep the simulations explicitly experimental.** The historical Jat
   simulator omits key Blast and Afflictions effects; its marked historical
   rankings are invalid. The new Jat event model explores hypotheses about
   Afflictions trigger/reseeding, cloned Gas, Blast and tick clocks, Seismic
   status seeds, and damage routing. Its scalar health router also omits the
   Wiki's per-type armor damage minimum for small events. It has not been
   validated against a game engine. The user requested Wiki, Reddit and forum
   research rather than an expectation of in-game testing. Percentiles are
   model outcomes, not bounds
   on real play; do not present any simulated count as a measured result.
3. **Gates and Magnetic:** the user explicitly requested that excess damage be
   discarded on Shield/Overguard break in the latest Jat scenario. The Wiki
   distinguishes player and enemy gates; older simulators instead use
   proportional enemy Overguard overflow. Document the choice per model rather
   than silently harmonizing them. The dedicated Magnetic Wiki describes
   Electricity totaling 3% of maximum defense per stack over six seconds,
   with source modifiers; other pages differ in wording. See the formula audit
   and the individual reports before changing behavior.
4. **Remote CI and updater networking.** With approval, publish the current
   branch and inspect its push-triggered GitHub Actions run as described above.
   Exercise an actual DE refresh later from an environment allowed to access
   its endpoints, using isolated app data. The sandbox's restricted network
   prevented a live refresh; fixtures and a historical manifest sample were
   tested instead. A real display test remains separate from offscreen tests.
   **Windows packaging is very low priority, possibly 2028:** native Windows
   PyInstaller/installer and Windows-specific LZMA checks are not an immediate
   acceptance requirement.
5. **Strengthen publication safety if concurrent use matters.** A filesystem
   lock/shared protocol for readers and writers, durable directory/file sync
   appropriate to each platform, and a recoverable versioned snapshot or
   manifest-pointer design would be needed for stronger multi-process and
   power-loss guarantees. Do not remove a recovery marker as a shortcut. The
   refresh may succeed and publish new ZIPs even if the later DB build fails;
   retry after resolving the error. Both migration and full rebuild now create
   SQLite backups, but their pre-write change detection is not a universal
   cross-process lock, and backups currently require manual pruning.
6. **Improve reliability/coverage incrementally.** Consider pinning or locking
   runtime and packaging dependencies, testing more OS/Python combinations,
   adding current real-export fixtures without checking in large data, and
   benchmarking whole UI interactions. Review other validation boundaries and
   signal-order edge cases before expanding accepted saved-build formats.
7. **Extend compatibility only with evidence.** Verify new weapon families
   against the Wiki, update the pinned snapshot and its license/override
   provenance, and add tests for the specific affected weapons. The community
   source already had one incorrect mod-family label, so do not assume all its
   entries are authoritative. The GUI does not check duplicate/conflicting
   mods, capacity, exact Cannonade eligibility, all special weapon categories,
   complete set bonuses or every separated conditional. Its conservative
   filtering can omit valid official mods; custom mods and files must remain
   recoverable. The original exported +200% rank-10 "Pressure Point" row needs
   independent identification before it can be enabled. Gameplay checks may be
   recorded for future work but are not expected from this user.
8. **Model attack components rather than guessing a single hit.** Grimoire's
   Wiki-sourced direct/radial split demonstrates that the public export row
   can merge events. Audit other weapons against per-attack Wiki data and
   design explicit attack/mode/component selection before claiming per-hit
   output or separately quantized/falloff damage. The current bundled database
   also contains 172 zero-damage `Pistols` rows corresponding to 180 export
   rows (some duplicate names): pet, hoverboard, Zaw, Kitgun and other parts
   rather than usable secondaries; those source rows lack a weapon `slot`. Preserve custom rows and investigate source metadata before
   hiding entries: zero damage alone is not proof that a future weapon is
   invalid. Do not silently delete user data or assume all duplicate IDs are
   equivalent.
9. **Give Rivens an explicit identity and ordered stats.** The name-substring
   heuristic does not recognize every real Riven name. Any replacement needs a
   backward-compatible saved-build/data migration, explicit treatment of spliced
   secondary elements, and Wiki-sourced tests; do not infer Riven identity from
   elemental values or silently rewrite old builds.

Do not silently change earlier build constraints, assumption tables, seeds,
or result artifacts. If evidence changes a mechanic, update tests and reports
with a clear distinction between researched facts, assumptions and model output.
