# Next-session handoff

## Current state

- Repo: `/home/user/Warframe-Damage-Calculator` (`Man1nWhite/Warframe-Damage-Calculator`).
- Stay on branch `arena/f058f23e-warframe-damage-calculator`; do not switch or rename it.
- Base/HEAD: `f781ac0`; all current work is uncommitted. Preserve the user's data and fix every confirmed issue found along the way.
- User asked to keep auditing and fixing, then requested this handoff be optimized for the next AI session. Read this file first, then check `git status` and the current diff; do not repeat completed investigations unnecessarily.

## What has been fixed

The current diff includes calculator/GUI validation and preservation, simulator corrections, offline revision-4 migration, custom-schema guards, export/database safety, import-cache fixes, tests and docs. In particular:

- Invalid/non-finite/underflowed Armor and Valence inputs fail visibly; invalid builds cannot be saved or compared. Loading preflights effects and calculation before changing the current build.
- Direct calculations reject non-finite components and overflow. Shadow Clones' unmodeled Finisher damage warns rather than being guessed. Percentile edge cases are covered.
- Sirocco imports 2,000 Void. Guarded migration protects identifiable user edits/custom rows and retains a consistent SQLite backup. Custom triggers, affected foreign keys, and populated reparsed effect extensions cause refusal; rebuilds have related guards.
- Failed catalog reads do not masquerade as empty data. Missing/empty DB files with WAL/SHM/rollback-journal sidecars are refused before SQLite can discard recoverable data.
- Export publication preserves prior copies and recovery markers on uncertain failures; it never rolls back over a possibly user-edited destination. Same-size/same-mtime edits during download are detected, absent concurrent files are preserved, symlinked exports are rejected, and lock/recovery checks cover symlink targets.
- Import rejects ambiguous multi-JSON weapon ZIPs, duplicate upgrade ZIP members and duplicate JSON object keys. Cache keys and parsing use the same immutable bytes.
- HTTP `Content-Length` is not compared with Requests' transparently decoded body. Download size is capped at 512 MiB; manifest LZMA expansion is capped at 32 MiB incrementally.
- Research caveats/results are in `docs/formula_audit.md`, `docs/wiki_formula_verification.md`, and `docs/verglas_prime_sim.md`. Do not describe simulator results as in-game validation.

## Verification and limits

- Latest focused updater/importer/weapon-export/migration/rebuild suites: **115 tests passed**. Re-run with `PYTHONPATH=/home/user/.cache/wdc-review-deps python -m unittest tests.test_updater tests.test_weapon_export_safety tests.test_import_cache_safety tests.test_database_migration tests.test_database_rebuild_safety -q`.
- A prior full required-offscreen suite passed **809 tests**, before the latest refresh/import-parser changes. It has not been rerun: the refreshed environment lacks `libxkbcommon.so.0`, so QtGui cannot import. A Qt offscreen shim existed in a disposable cache but did not persist.
- Latest static checks passed: Ruff, mypy (**38 source files**), compileall, and `git diff --check`.
- Bundled DB: revision 4; `quick_check=ok`; 827 weapons, 1,594 mods, 1,856 effects. Two stored benchmark digests matched before the latest non-simulation changes.
- Native graphics, live DE refresh, Windows packaging, and remote CI for this uncommitted diff are unverified. Historical CI success is not evidence for current changes.

## Next steps

1. Re-establish a usable Qt/offscreen environment if feasible; run `PYTHONPATH=/home/user/.cache/wdc-review-deps LD_LIBRARY_PATH=/home/user/.cache/wdc-qt-libs QT_QPA_PLATFORM=offscreen WDC_REQUIRE_GUI_TESTS=1 python tools/run_tests_ci.py`. If blocked, report it accurately; do not claim a fresh full-suite pass.
2. Rerun Ruff, mypy, compileall, `git diff --check`, the focused 115-test command, database quick-check, and benchmark equivalence checks if simulator code changed.
3. Continue the targeted bug audit; add a regression before each confirmed fix. Check updated code/tests before trusting older counts or claims.
4. Keep documentation concise and consistent. Do not commit, push, or open a PR unless asked.
