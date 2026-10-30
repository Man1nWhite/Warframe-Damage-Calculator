# Warframe Damage Calculator — a fork kept to test the damage data

> **This repository is a fork.** The application is
> [DeadxxSmile/Warframe-Damage-Calculator](https://github.com/DeadxxSmile/Warframe-Damage-Calculator),
> the TenZeroGG calculator whose math DeadxxSmile (TenZeroGG) and Xadreus built.
> `Man1nWhite/Warframe-Damage-Calculator` keeps that app and uses it as a test
> bench for the damage data: every formula is re-read from the
> [WARFRAME Wiki](https://wiki.warframe.com), pinned by a regression test, and
> corrected where the code disagreed with the source. Upstream stays the place
> to download the app, report app bugs and follow feature work.

## What this fork tests

The fork changes what the numbers *do*, not what the app looks like. Every
check below runs against the bundled data snapshot; only re-reading the wiki
itself needs network access:

- **Every formula family against the Wiki.**
  [`docs/wiki_formula_verification.md`](docs/wiki_formula_verification.md)
  records, page by page (about thirty pages read as raw wikitext on 2026-10-28),
  what the Wiki says, where the repository implements it and whether the two
  agree; [`docs/formula_audit.md`](docs/formula_audit.md) holds the scope limits,
  the source conflicts and the history of the corrections.
- **A re-runnable check.** `tools/wiki_audit.py` re-reads the audited pages,
  extracts the numbers next to each claim's keyword and compares them with the
  code, with `--save-snapshot` / `--baseline` turning two runs into a diff of
  exactly which numbers appeared or disappeared.
- **A behaviour-neutral optimisation gate.** The simulators are the slowest
  part of the tree, and every published figure is seeded model output.
  `tools/bench_models.py --snapshot` / `--check` hashes complete fixed-seed
  trial records from all six simulators and the scalar slam-count model, so a
  speed change can be checked for bit-identical results in those scenarios.
  Adding Verglas changes the digest: take a new reference before optimizing;
  older snapshots are not comparable. [`docs/optimization_review.md`](docs/optimization_review.md)
  records the timings and opportunities that were deliberately left.
- **Exact numbers under test.** The suite pins worked examples and regressions
  (armor reduction, 32-quantization, DoT ticks, crit tiers, Cold/Blast stack
  caps, Riven values, Condition Overload) instead of asserting that "something
  changed"; it runs offline in about eight seconds.
- **Corrections the testing found,** each committed on its own: the 12-bit
  quantization of the base critical-damage multiplier, Cold's four-stack cap on
  Overguard, Blast's boss cap and death-triggered detonation, Void's Overguard
  bonus, the equipped slots being aggregated inside the calculator (callers that
  passed only `equipped_mods` silently lost their +Damage and Bane bonuses), and
  the legacy `Zairman` faction spelling.

What the fork does **not** do: it ships no releases or installers, it may lag
behind upstream, and it is not a support channel for the app. The GPL-3.0
license and the disclaimer below are the upstream project's and cover this copy
too; the added documents, tests and `tools/wiki_audit.py` fall under the same
license.

### Reproducing the damage tests

```bash
python -m unittest discover -s tests -q     # the whole suite, offline
python -m ruff check . && python -m mypy    # the gates CI runs

# Re-read the audited pages and record the numbers the code is pinned to.
python tools/wiki_audit.py --save-snapshot docs/wiki_numbers.json
# After a game update, show only the numbers that appeared or disappeared.
python tools/wiki_audit.py --baseline docs/wiki_numbers.json

# Prove an optimisation left the simulated results bit-identical.
python tools/bench_models.py --snapshot /tmp/before.json   # before editing
python tools/bench_models.py --check /tmp/before.json      # after editing
python tools/bench_models.py --trials 20 --repeats 3       # ms/trial table
```

The snapshot is written by the first command and is not committed, since it
needs the live pages. `--topic TEXT` narrows the audit to one area (for example
`--topic "Blast"`) and `--pages DIR` reads saved page text, so a later run can
be made without network access; the exit codes are documented under
[Re-running the wiki audit](#re-running-the-wiki-audit).

## A note from the upstream project

*A note on development: this app's UI and structure were generated entirely
using ChatGPT, but the underlying math is the result of countless hours of
manual testing and coding.*

Ages ago, I started the TenZero.GG project to make a better site to create and share Warframe builds. While I handled the bulk of the overarching project, my collaborator Xadreus and I teamed up heavily on the incredibly complex damage calculations and the underlying math. Together, we worked our tails off to accurately recreate the game's systems, matching not just the HUD stats, but the real-world values you actually see when using weapons in a mission. We honestly had the most accurate calculations of any model we could find online.

Unfortunately, life loves to get in the way of passion projects. Between college for Xadreus and it being over a decade and a half since I last touched webdev, the site itself suffered. But our math and our testing spreadsheets were rock solid.

Instead of letting all the work Xadreus and I put into those accurate damage calculations go to waste, I figured: why not throw our spreadsheet at ChatGPT and see if I could vibe code out a Python app? I wanted to give something back to the amazing Warframe community so our work actually means something, even if the original site never gets built. I absolutely plan to get my hands dirty in the code later to add features and make it look better, but with real life pulling me away, using AI was the best way to get this tool into your hands now. I hope you understand, and I hope you enjoy it!

**The application (upstream, TenZeroGG v1.0.1).** A desktop Warframe damage
calculator built around the calculator engine and packaged as a PyQt6 desktop
app. Everything from here down documents that application; the fork adds the
verification layer described above and otherwise leaves the app as upstream has
it.

## Current Features

> **Scope:** results are estimates, not a complete combat model. See the
> [formula audit](docs/formula_audit.md) for verified examples, wiki source
> disagreements, unsupported mechanics and known simulation errors, and the
> [wiki verification report](docs/wiki_formula_verification.md) for the
> per-formula checks.

- PyQt6 dark mode UI
- SQLite database for weapons and mods
- Real mod selection with rank support
- Slot-order elemental combining
- Arsenal-style totals and a wiki-sourced, non-critical health-damage estimate
  treating each exported row as one hit. Some rows combine separate direct and
  radial attacks, so their displayed Final value is not a reliable per-hit result.
- Built-in FAQ dialog that explains the calculator logic
- Settings dialog for:
  - refreshing Warframe data from DE
  - rebuilding the SQLite database in-app
  - showing where the app stores its AppData-backed files
- App data stored in the user's AppData-backed calculator folder for easier packaging later
- Save and load build files as JSON

The bundled player Grimoire export, for example, lists 150 Electricity: the
[Wiki](https://wiki.warframe.com/w/Grimoire) separates its primary attack into
100 direct plus 50 radial damage. WDC currently treats that 150 as one hit;
it does not model the separate hits, radial falloff, or alternate fire. This
limitation also applies to other aggregated attack rows. When the exported base
amount exceeds the supported damage components, the result includes a warning
that its totals are incomplete. For example, Shadow Clones' exported Finisher
damage is not modeled; it is not silently treated as Void or True damage.
The comparison dialog shows these warnings separately for both builds.

Armor and Valence Base must be representable, finite, non-negative numbers; a
blank field means zero. Valence Base is an absolute damage amount, not a
percentage. Invalid text or a numeric overflow leaves the entered text and
equipped mods in place, shows an inline error, and clears the results until
corrected. Such a build
cannot be saved or compared. Invalid numeric values (including explicit JSON
`null`) and duplicate object keys in an existing build file are rejected without
changing the file or the current build. Omitted numeric fields in older builds
still default to zero. Build files are limited to 4 MiB on both load and save;
loading also limits JSON nesting to 64 levels.

Negative damage-type bonuses can reduce their own damage bucket to zero but
cannot subtract from another type. Elemental bonuses still scale from base
damage before type-specific reductions; combinations of unusual negative
elemental effects remain an approximation rather than an in-game-validated
formula.

If the database is locked or unreadable, the app keeps the existing equipped
slots instead of treating failed mod reads as an empty loadout. Failed
calculations are marked unavailable and their old numbers are cleared; once
the database is accessible again, recalculate to retry. Loading a saved build
checks its mod effects and calculates it before replacing the current build,
so a failed read or calculation leaves the current build in place.

## App Data Layout

The app stores its working files in:

- Windows: `%APPDATA%\WDC`
- Fallback on non-Windows systems: `~/.local/share/WDC`

Inside that folder the app keeps:

- `data/weapons.db`
- `data/backups/weapons-pre-v*.sqlite3` (created before a legacy upgrade)
- `data/backups/weapons-pre-rebuild-v*.sqlite3` (created before a full rebuild of an existing database)
- `source/ExportWeapons_en_Cleaned.zip`
- `source/ExportKeys_en_Cleaned.zip`
- `source/Warframe-Damage-Calculator_v2.xlsx`
- `source/.wdc-export-backup-*/` (displaced original exports retained after refresh)
- `builds/*.json`

The app does not write a settings file; any other file in this folder (for
example a `settings.json` left by an earlier build) is left untouched.

## Running

Requires **Python 3.11 or newer** (CI covers 3.11 and 3.12; the code uses
`datetime.UTC`, `zip(strict=...)` and PEP 604/585 annotations).

```bash
pip install -r requirements.txt
python main.py
```

If there is no database, the app prompts before attempting to download fresh
DE data; the prompt warns that rebuilding replaces the mod/effect catalog and
matching weapon rows, and any existing database is backed up first. The Settings
dialog can also rebuild offline using saved local export files. On first use,
the two exports are seeded together from the bundled
snapshot. If only one saved export is present, WDC does **not** fill the other
from a potentially different snapshot: restore a known matching pair or use a
fresh download before rebuilding. Independent reference files are staged and
published individually without overwriting a file created during the copy.
Automatic seeding and refresh require hard-link support on the app-data
filesystem; if unavailable, WDC stops publication before moving saved exports.
After closing WDC, a complete matching export pair and needed reference files
can instead be copied there manually without overwriting existing user files.

For resource safety, downloads and source archive snapshots are limited to
512 MiB, the expanded manifest to 32 MiB, each export JSON to 128 MiB, and
the workbook's declared total uncompressed size to 128 MiB. Oversized sources
are rejected before they can replace saved exports or be imported; an online
refresh can still fall back to the saved pair. These limits are not a guarantee
of fixed memory use when parsing otherwise valid data.

## Existing Databases And Backups

On startup, legacy databases are upgraded **before** weapon values are shown.
The upgrade corrects the older Heat/Cold/Electricity export mapping, reparses
mod effects, repairs the known Grimoire export collision when safe, and adds
missing Void damage from matching exports, including Sirocco. It uses the saved
local exports and makes no network request. SQLite's backup API first
creates a uniquely named, consistent copy
in `data/backups/`, including committed WAL data. The import and version mark
are committed together; on failure the database is left unmodified by the
upgrade, and startup stops with an error rather than displaying stale data.
Databases from a newer, unsupported app version are also refused.

Build JSON, settings, unrelated tables, and custom weapon/mod/effect rows are
retained, including custom rows colliding with exported names or IDs. A
revision-0 upgrade refreshes source-matching official weapons and mods; a
revision-1 upgrade refreshes official mods. Identifiable edits to those rows
are rejected rather than overwritten. The old mod parsers and current parser
can legitimately disagree, so derived fields and missing effects are reparsed;
the backup retains their original state if those fields had been intentionally
edited. Extra columns on existing mod and weapon rows are preserved. If a
reparsed official effect contains data in a custom column, or a custom trigger
could run on a table being updated, the upgrade stops for manual review rather
than risking user data. Declared foreign keys referencing affected catalog rows,
or unresolved links into those tables, also cause a refusal; links to untouched
custom rows can remain. Revision 1/2 may also repair Grimoire: that requires
both player and Doppelganger entries in the saved export and an exact match
with the old row. Custom or already-correct Grimoire rows are not replaced.
Before resolving a custom-schema refusal, copy the database and export any
annotations; effects can change position during reparse, so their association
must be reviewed manually. Preserve and review triggers and foreign-key links
before changing them. Relationships without declared foreign keys cannot be
automatically identified.

Revision 4 repairs a zero Void component on matching official rows, without
replacing other columns. For the known Sirocco ID, a missing or mismatched
source aborts the upgrade instead of marking the database current. Edited rows
with nonzero Void and custom rows are left intact. If an affected row was
edited or its matching export is unavailable, first copy the database and
source files to a safe location; restore a matching export or preserve the
edited row under a non-DE identifier before retrying. Do not blindly rebuild:
a full rebuild can overwrite matching names.

Both saved export ZIPs must be readable and free of an interrupted-publication
marker. If the database main file is missing or empty while a `-wal`, `-shm`,
or `-journal` sidecar exists, WDC refuses to open or recreate it: SQLite can
discard an orphaned WAL when opening a new database, and the sidecar may hold
committed user data. Close every SQLite/WDC process, preserve the main file and
all sidecars together, and restore or inspect the matching database before
retrying. The refusal applies to zero-byte sidecars and sidecar symlinks too.
The upgrade refuses an older or partial export that does not cover the
official mod rows/effect fragments it would refresh; revision 0 also requires
coverage of official weapon rows. Restore matching exports and restart if this
check fails. The spreadsheet is optional. Custom rows using a `/Lotus/`
identifier may need a non-DE identifier before upgrading. Future same-name
export entries with conflicting modeled fields are rejected for review rather
than silently selected, except for the explicitly identified Grimoire pair.

Backups are retained until removed manually. To restore one, close all WDC and
other SQLite connections. Move the current `data/weapons.db` and any
`data/weapons.db-wal`, `data/weapons.db-shm` or `data/weapons.db-journal`
sidecars together into a separate safe folder; do not leave old sidecars beside
the restored file. Then copy
the desired standalone backup to `data/weapons.db`. A restored legacy backup
will attempt the upgrade again on the next startup.

## Rebuilding The Database Manually

```bash
python build_database.py
```

The command reads saved local exports without downloading. For a legacy
database it performs the same backed-up upgrade described above instead of a
full rebuild. For a current or new database it performs a full rebuild. The
two Settings rebuild actions also perform a full catalog rebuild (the download
option tries DE first). A full rebuild **replaces the mod/effect catalog**,
including custom rows, and overwrites weapon entries with matching names;
unmatched weapons are retained. Builds and settings are separate files, and
Settings asks for confirmation. A rebuild also refuses catalog triggers and
foreign-key links to affected rows when those could alter or orphan data in
other tables; review such schemas before retrying.

Before changing an existing database, a full rebuild uses SQLite's backup API
to create a uniquely named copy in `data/backups/`, including committed WAL
data, and reports its path. If backup fails, the rebuild is not started; if a
later write fails, its transaction rolls back and the backup is retained. A
new or empty database has no prior data to back up. Close other WDC instances
before rebuilding: detected writes during backup abort the rebuild, but this
is not a general cross-process locking protocol. Backups are not automatically
pruned. For extra protection, keep a separate copy outside the app-data folder.

## Recovering An Interrupted Data Refresh

The two saved export ZIPs cannot be replaced as one atomic filesystem operation.
If a refresh or first-time seed is interrupted during publication, or rollback
fails, WDC retains `source/.wdc-refresh-*/PUBLISHING.json` and refuses to
import or refresh the possibly mixed files. To recover:

1. Close **all** WDC instances. Make a separate copy of the whole app-data
   `source` folder, including the hidden `.wdc-refresh-*` and
   `.wdc-export-backup-*` directories; do not rebuild or refresh yet.
2. Inspect `PUBLISHING.json`. For `"mode": "seed-no-clobber"`, WDC did not
   replace an existing destination, but another program may have created or
   edited one while seeding. Preserve all destinations and the `staged_copy`
   files separately; do **not** delete a destination merely because its
   `previous_copy` is `null`. Decide which files to keep and restore a verified
   matching pair, or move both destinations to a safe location before retrying
   a fresh first-time seed.
3. For `"mode": "refresh-no-clobber"` or older markers, inspect the
   `destination`, its `previous_copy` and `staged_copy` in the staging
   directory, and any `displaced_copy` in the indicated `recovery_directory`.
   The displaced original can include a later edit and may not match the older
   recovery copy. Preserve all of these separately before restoring anything,
   including any destination that appeared after a `null` `previous_copy`.
   Restore a verified matching pair of **both** exports; never overwrite an
   unreviewed destination or newer edit.
4. If a required previous copy is missing, the marker is unreadable, or there
   are multiple interrupted stages and their order is unclear, do not guess or
   simply delete the marker: retain the copies and obtain a known-good matching
   pair of exports. Once the saved pair is verified and restored, remove the
   resolved staging directory (including its marker), then retry. Older markers
   may not contain a `recovery_directory`.

An interruption during an independent reference-file copy can leave a hidden
`source/.wdc-reference-*` staging directory. It is not read as a reference
file; after closing all WDC instances, it can be removed once any contents the
user wants to keep have been copied elsewhere.

WDC also fingerprints the saved export pair before downloading and checks it
again before publication, so even a same-size, same-mtime edit made during the
network request is not silently overwritten. During publication WDC retains
actually displaced originals in `source/.wdc-export-backup-*` and creates the
new destinations without clobbering files created in the meantime. Unrelated
readers can briefly observe a missing destination during the move. Those
backups are not automatically pruned, even after successful refreshes; close
other programs and review them before removing them. The marker and copies
protect against ordinary exceptions and many process interruptions; WDC does
not automatically roll back a failed publication because an unrelated program
may have changed a destination. This is **not** a power-loss durability
guarantee. Cooperating WDC processes use a persistent `source/.wdc-exports.lock`
OS lock to serialize export publication and import reads; nested reads by the
same thread reuse the lock. The lock does not prevent unrelated programs from
editing files and does not lock the database for the whole rebuild. Close other
WDC instances before refreshing or rebuilding. Export publication and the
database rebuild are separate operations: if the rebuild fails after a
successful refresh, the saved exports can be newer than the unchanged database;
retry after resolving the error.

## Riven Stat Tables

Riven stat data is not present in the cleaned DE export (the Riven
`upgradeEntries` tables are stripped), so WDC vendors a community-verified
Riven stat table and ports the in-game value formula in `modules/riven.py`.
The vendored base values come from a community-maintained DE export mirror.
Selected generated range endpoints and layout weights are checked against the
[WARFRAME Wiki Riven Mods page](https://wiki.warframe.com/w/Riven_Mods)
(see `tests/test_riven_wiki.py`); not every possible stat or roll was audited.

- `source/riven_tags.json` - per-tag base values for all seven Riven types
  (Rifle, Shotgun, Pistol, Kitgun, Melee, Zaw, Archgun), derived from DE's
  Riven `upgradeEntries` via [warframe-riven-info](https://github.com/calamity-inc/warframe-riven-info)
- `source/riven_stats_average_1_2.json` / `.csv` - generated average-grade
  tables at **1.2 disposition**, max rank (rank 8, x9 steps), covering the
  combined-stat layouts 2 positives, 3 positives, 2 positives + 1 negative and
  3 positives + 1 negative (plus negative-stat columns for each). These are the
  only four rollable layouts: a Riven has 2-3 positive stats and at most one
  negative, per the wiki
- The wiki's weighted layout table (0.99 / 1.2375 / 0.75 / 0.9375 bonus and
  -0.495 / -0.75 malus) equals the engine's layout factors multiplied by the
  1.5 specific-fit constant; the two are numerically equivalent
- Average grade means the midpoint random roll (grade factor 1.0); the full
  per-stat roll band is 0.9x-1.1x and is available through `modules/riven.py`
- Stats that map onto the damage engine carry a `wdc_code` (e.g. `HEAT`,
  `TRUE`, `BANE_GRINEER`); utility stats such as critical chance or fire rate
  are labeled but not yet consumed by the calculator
- Riven Disposition was retired in Hotfix 44.1.3 (2026-10-22): all weapons are
  now normalized to the 1.2x these tables use
- Unrollable signs are `null` in JSON and blank in CSV: for example, elemental
  damage cannot be a negative trait. Punch Through values are plain meters;
  faction values are bonuses, so add 1 for the displayed multiplier. The
  table does not filter weapon-specific restrictions
- Splicing-system attributes (weakpoint damage, combined elemental damage,
  ammo efficiency, etc.) are not part of the Riven upgrade tables and are not
  included. Calculations use Python binary64, not bit-exact game binary32
  arithmetic

Regenerate the tables (any disposition works):

```bash
python build_riven_tables.py                    # 1.2 disposition
python build_riven_tables.py --disposition 1.0
```

## Condition Overload (GunCO) Stacking Tables

CO-type bonuses (the melee Condition Overload mod, Galvanized
Aptitude/Shot/Savvy, Secondary Shiver, the Cedo's innate bonus, Shattering
Frost and Incarnon Genesis perks) are intended to stack **additively** with
ordinary +% damage mods, but many projectile attacks instead apply them
**multiplicatively** - a long-standing, wiki-documented engine quirk. The
catalog is a curated snapshot of the
[Condition Overload (Mechanic) wiki page](https://wiki.warframe.com/w/Condition_Overload_(Mechanic))
(last edited 2026-10-05, retrieved 2026-10-27) and cross-checked against the
community GunCO rule table in `source/conditionOverload.ts` (wiki pull Oct
2026 plus rainy's GunCO sheet 38.0.12; sheet-only rows are flagged
`gunco_sheet`).

- `source/gunco_mechanic.json` / `.csv` - 118 attack rules across primaries,
  secondaries, melees, exalted weapons, archguns, robotic weapons and amps:
  77 multiplicative, 25 additive with a non-1.0 scale, 16 where no bonus
  applies. The CSV is one row per weapon x attack. Kitgun chamber names that
  exist in both slots (Sporelacer, Tombfinger) carry a section field; pass
  `section=` to the resolver to disambiguate
- `modules/condition_overload.py` - `resolve_co_behavior(weapon, attack)`
  resolver plus `apply_co(...)` implementing both damage formulas
- `tests/test_condition_overload.py` - wiki-pinned rule and formula tests

The two stacking modes (`B` = base, `M` = pooled ordinary damage multiplier
such as Serration, `c` = total CO-type bonus fraction, `s` = per-attack scale):

| Mode | Formula | Wiki behavior |
| --- | --- | --- |
| Multiplying | `B x M x (1 + c x s) x other` | #1, mostly projectiles, not intended |
| Adding | `B x (M x other + c x s)` | #2-#4, intended, most hitscan weapons |
| Does not apply | CO contribution is 0 | #5, explosion radii and known bugs |

The wiki catalog lists only discrepant attacks; the resolver defaults to
additive +100% for unlisted attacks, additive direct-hit-only for unlisted
hitscan AoE, and "does not apply" for unlisted projectile explosion radii.
Example: with Serration (x2.65) and a +100% CO bonus on a base-100 hit, an
additive attack deals 365 while a multiplicative one deals 530.

Regenerate the tables after updating the vendored TS source:

```bash
python build_gunco_tables.py
```

## Mod Selection And Compatibility

The desktop screen models unconditional, non-critical direct damage. It does
not apply crit, status, modded multishot, trigger-dependent, set-bonus, or other
unsupported effects. Its stricter parser avoids interpreting Blast radius,
physical conversion, conditional bonuses, and Conclave mods as permanent
PvE damage; it can also omit valid effects it cannot safely interpret.

Mod filtering is **partial**, not a complete Arsenal legality check:

- A pinned, offline [WFCD primary-class snapshot](source/weapon_mod_classes.json)
  separates rifle and shotgun mod families. The Wiki explicitly says
  [Coda Bubonico](https://wiki.warframe.com/w/Coda_Bubonico) uses shotgun mods,
  so its conflicting WFCD Rifle classification is overridden. The snapshot is
  attributed under [WFCD's MIT license](source/WFCD_LICENSE.txt); its pinned
  source and reproduction command are in `tools/build_weapon_mod_classes.py`.
- Selected weapon augments, known melee subclasses and non-player categories
  are checked conservatively. Unknown official primary families and unknown
  restricted classes are hidden rather than guessed. Custom non-`/Lotus/`
  mods are retained; generic rifle/shotgun mods remain available for custom
  weapons with unknown families, with a warning. Companion, Archwing and other
  unsupported categories expose custom mods only.
- The three known Cannonade mods are hidden until their semi-auto/Incarnon eligibility is
  modeled. The picker does **not** enforce duplicates, conflicting mod variants,
  capacity, every augment restriction, or every conditional. Verify the build
  independently. An old saved build with a now-hidden mod is rejected with a
  warning; its JSON and the current UI are not changed.

## Formula Reference and Enemy Scaling

- [Formula audit](docs/formula_audit.md) — findings, source disagreements,
  tested scope and known limitations.
- [Wiki verification report](docs/wiki_formula_verification.md) — every
  formula family checked against the WARFRAME Wiki on 2026-10-28, with the page
  it was read from, the code that implements it and any documented deviation.
- [Damage and status reference](docs/damage_formula_reference.md) — the
  wiki's direct-hit, armor, trigger, status and DoT formulas. The Python DoT
  helpers use binary64, not exact in-game binary32 arithmetic.
- [Target dummy models](docs/target_dummy_models.md) — Heavy Gunner level
  scaling and the explicit article-versus-gadget Overguard disagreement.

### Re-running the wiki audit

`tools/wiki_audit.py` re-reads the audited wiki pages, extracts the numbers
next to a keyword for each claim in its registry, and compares them with the
value the code uses. It is a reporting tool: a number that moved is something
to review, not something it changes for you.

```bash
# Read the pages (cached under wiki_pages/, which is not committed) and save
# the extracted numbers so a later run can diff against them.
python tools/wiki_audit.py --save-snapshot docs/wiki_numbers.json

# After a game update, re-read (delete wiki_pages/ first for fresh text) and
# show exactly which numbers appeared or disappeared.
python tools/wiki_audit.py --baseline docs/wiki_numbers.json
```

`--topic TEXT` filters the claims (for example `--topic "Blast"`), `--json`
prints a machine-readable report, and `--pages DIR` points at a different cache.
Exit codes: `0` every audited number still matches the code, `1` a number moved
or the code drifted from its audited value, `2` a page or keyword could not be
read, so the audit is incomplete.

One claim (the four-stack Blast cap on `Damage/Calculation`) is stated in prose
next to no keyword, so its registry entry is `optional`. When that page cannot
be read the claim is reported as `[unverified]` and the exit code is unchanged,
which keeps a network-less run of the Blast topic at `0`; a drift in
`BLAST_MAX_STACKS_BOSS` itself is still reported as `code-changed` (`1`) and the
JSON payload carries `"optional": true`. `tests/test_wiki_audit.py` runs the
whole thing offline against saved page text.

The desktop calculator is limited to a non-critical direct hit on health; it
is not a complete TTK, shield, Overguard, crit, or status simulator. The wiki's
ordinary enemy armor reduction is `0.9*sqrt(armor/2700)` at or below 2700;
exceptional armor above 2700 uses `armor/(armor+300)`.

## Experimental Weapon Simulations

The repository also contains simulations for [Kuva Nukor](docs/kuva_nukor_build_sim.md),
[Akarius Prime](docs/akarius_prime_riven_sim.md),
[Ocucor](docs/ocucor_riven_sim.md),
[Jat Kittag](docs/jat_kittag_heavy_slam_sim.md),
[Alternox Prime](docs/alternox_prime_riven_sim.md), and
[Verglas Prime](docs/verglas_prime_sim.md). Newer, explicitly
experimental comparisons for [Kuva Nukor](docs/kuva_nukor_three_mod_comparison.md),
[Akarius Prime](docs/akarius_prime_viral_corrosive_comparison.md), and
[Ocucor](docs/ocucor_enervate_flare_comparison.md) record their assumptions,
sensitivity checks, and reproducible results. An additional
[Ocucor Riven follow-up](docs/ocucor_viral_dilution_comparison.md) tests the
Viral/Heat weighting and Reload Speed tradeoff. The new
[Jat Kittag heavy-slam analysis](docs/jat_kittag_slam_spam_comparison.md)
compares combo recovery, Gas and Riven options without claiming a validated
TTK or crowd-clear ranking. A separate [Gas / Cold / Damage build analysis](docs/jat_kittag_gas_cold_damage_build.md)
examines Fever + Focus Energy without Primed Pressure Point. An experimental
[slam-count comparison](docs/jat_kittag_expected_slams.md) contrasts that build
with Gas / Crit Damage / Crit Chance and Primed Pressure Point, showing how
unverified Afflictions and status-timing hypotheses change the results.

**Do not treat simulated TTKs or rankings as validated in-game results.**
Historical reports predate corrected mechanics and are retained only as marked
archives; the crit multipliers quoted in them predate the
[12-bit base-multiplier quantization](docs/damage_formula_reference.md#14-total-crit-aoe-and-weak-points)
adopted on 2026-10-28, which moves those figures by at most 0.2%. Several simulations model Overguard overflow and Magnetic break ticks;
the new Jat slam-count experiment instead assumes no overflow at the user's
request. All still rely on unverified routing assumptions, simplified status timing and
weapon-specific approximations; see the
[formula audit](docs/formula_audit.md) before interpreting any output. Trial
summaries report attempted and timed-out runs; their TTK statistics include
successful kills only.

## Tests

For the current audit, safe workflows, open issues, and next steps, see the
[development handoff](docs/next_session_handoff.md).

Install `requirements.txt`, then run:

```bash
python -m unittest discover -s tests -q
```

The suite is fully offline and takes roughly eight seconds on a laptop. Each
migration or rebuild test parses the same bundled exports, so the workbook and
both JSON export parsers in `modules/importer.py` cache parsed results by path
and file contents. A same-size replacement with a preserved timestamp is still
reparsed, and the parsed bytes are the bytes used for the cache key. A
locked-database test exercises the real backup path, so it shortens
`modules.database_backup.BACKUP_LOCK_DEADLINE_SECONDS` instead of waiting out
the production five seconds.

### Code style

Linting is enforced from `ruff.toml` (`E`, `W`, `F`, `I`, `UP`, `B`; `E501` is
off because the UI tooltips, data tables and wiki URLs are deliberately long).
CI runs exactly the same command, so a local run is authoritative:

```bash
pip install -r requirements-dev.txt
python -m ruff check .
```

### Type checking

`mypy.ini` type-checks `modules/` (every formula, the mod engine, the importer
and the migration pipeline) with `--check-untyped-defs`, so the body of a
function is checked even where its signature is still unannotated. This is
deliberately a partial gate: it catches recorded mistakes such as a float
written into an integer counter, an `Optional` used without a guard, or a loop
variable reused for a different record type, without demanding a full
annotation campaign. `gui/`, `tests/` and `tools/` are out of scope; CI runs the
same command, so a local run is authoritative:

```bash
python -m mypy
```

### GUI test prerequisites

The Qt integration tests exercise real widgets, ordered mod selection,
save/load/compare, offline rebuild, and migration startup. They run with Qt's
`offscreen` platform, not a physical display or GPU. They skip if PyQt6 or its
native libraries are missing; set `WDC_REQUIRE_GUI_TESTS=1` to make that a
failure instead. On headless Linux, install the system GL/EGL, xkbcommon and
D-Bus libraries (for example Ubuntu packages `libgl1`, `libegl1`,
`libxkbcommon0`, and `libdbus-1-3`), then run:

```bash
QT_QPA_PLATFORM=offscreen WDC_REQUIRE_GUI_TESTS=1 python -m unittest discover -s tests -q
```

The repository's GitHub Actions workflow is configured to run the full suite
with Qt required on Linux and Windows; its presence does not mean a particular
commit has passed remote CI. Offscreen widget tests do not validate native
desktop rendering or gameplay. Windows packaging work is very low priority,
possibly for 2028; the currently defined workflow still automatically schedules
its Windows packaging-smoke job on pushes and pull requests. For the focused CI
lint check, install `requirements-dev.txt` and run:

```bash
python -m ruff check --select F,E9 modules gui tests tools main.py build_database.py build_gunco_tables.py build_riven_tables.py
```

## Notes

- The updater now uses streamed downloads with file-size validation before it runs Python LZMA decoding on Warframe's manifest index.
- Truncated downloads are caught early with a clearer error message.
- 7-Zip is no longer required for normal refreshes.
- The current focus is the core damage path, not every secondary combat system in Warframe yet.


## Building A Windows EXE And Installer

This project includes:

- `WDC.spec` for PyInstaller
- `build_exe.bat` to build the app into `dist\WDC`
- `installer\WDC.iss` for Inno Setup
- `build_installer.bat` to compile the installer into `installer_output`
- `installer\BUILDING.md` with quick build steps

Typical build flow:

```bat
build_exe.bat
build_installer.bat
```

A separate, test-only PyInstaller smoke check builds an instrumented bundle in
a temporary directory, uses isolated app data, and exercises offscreen widget
calculations, build save/load, and an offline database rebuild:

```bash
python -m pip install -r requirements-build.txt
python tests/run_packaging_smoke.py
```

The test hook is not included in the production bundle. This smoke test does
not replace a native-display check, an Inno Setup installer test, or a live DE
refresh. The CI workflow defines a Windows packaging job, but a local or remote
run must pass before claiming a particular build is verified.

## License

Distributed under the GNU GPL-3.0 license; please check the `LICENSE` file in the GitHub repository for more information.

## Disclaimer

The following is the disclaimer that applies to all scripts, functions, one-liners, etc. This disclaimer supersedes any disclaimer included in any script, function, one-liner, etc.

You running this script/function means you will not blame the author(s) if this breaks your stuff. This script/function is provided **AS IS** without warranty of any kind. Author(s) disclaim all implied warranties including, without limitation, any implied warranties of merchantability or of fitness for a particular purpose.

The entire risk arising out of the use or performance of the sample scripts and documentation remains with you.

In no event shall author(s) be held liable for any damages whatsoever (including, without limitation, damages for loss of business profits, business interruption, loss of business information, or other pecuniary loss) arising out of the use of or inability to use the script or documentation.

Neither this script/function, nor any part of it other than those parts that are explicitly copied from others, may be republished without author(s) express written permission.

The author(s) retain the right to alter this disclaimer at any time.

For the most up to date version of the disclaimer, see:  
https://ucunleashed.com/code-disclaimer
