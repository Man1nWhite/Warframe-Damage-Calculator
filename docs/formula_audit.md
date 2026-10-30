# Formula audit: WARFRAME Wiki

Reviewed against the English WARFRAME Wiki on **2026-10-27**. The wiki is a
community-maintained reference and several relevant pages are marked as works
in progress; it is not a guarantee of Digital Extremes' current implementation.
This audit covers the repository's formula families, not a proof that every
weapon, catalog entry, game update, or edge case is correct. It uses the Wiki
and public community discussions rather than assuming in-game verification;
export snapshots and player reports may be incomplete or outdated.

## 2026-10-29 follow-up: data safety and simulator corrections

### History-guided regression pass

- Negative type modifiers are summed before their damage bucket is floored at
  zero; physical negatives do not reduce the base used by elemental mods.
  Flooring a negative combined-element bucket is a conservative model, not
  in-game verification of every unusual negative elemental interaction.
- Above the normal 2700 armor cap, the remaining damage fraction now uses
  `300 / (armor + 300)` rather than subtracting a rounded ratio from one.
  Tiny positive armored hits retain their per-type minimum even if the product
  underflows; normal-cap calculations keep the same numerical path.
- Akarius now applies guaranteed and fractional procs above 100% status and
  stops firing additional rockets at a dead target. Alternox and Akarius stop
  adding subsequent procs when a Blast detonation kills. The fatal hit still
  reports its overkill, but later hits no longer inflate totals. In a ten-seed
  fixed benchmark only Akarius changed (one direct-damage total); all TTKs and
  the other six benchmark models' records were unchanged.
- Saved builds reject duplicate keys, explicit `null` numeric values, excessive
  size and deeply nested JSON without changing the active build or the file.
  Missing numeric fields retain their older zero default. The mod category
  filter now recognizes Orokin and Murmur faction effects and distinguishes
  elemental from base damage, while allowing mixed-effect mods in both.
- Export JSON, archive snapshots and workbook expansion now have explicit size
  limits before those sources can be imported or published; a failed online
  refresh can still fall back to the saved pair. Pretty-printed export ZIPs are
  written incrementally within the JSON limit. These bounds reduce
  decompression/allocation risks but are not a fixed memory guarantee.
- Publication no longer overwrites a destination in the gap after its last
  fingerprint check: existing originals are moved into retained backup
  directories, checked again, and staged replacements are linked without
  clobbering newly created files. Backups also preserve late writes to an open
  original file. Interrupted publication retains its marker for review; all
  refreshes now require hard-link support and backups are not auto-pruned.

- The desktop filter keeps the active weapon and unsaved mod slots when a
  search hides the weapon. Missing damage components now produce an explicit
  result/UI warning rather than an apparently complete zero or partial total;
  the comparison dialog shows warnings for both builds. Locked or unreadable
  database queries are no longer treated as empty mod data: failed calculations
  clear stale numbers, and failed catalog reads preserve the active build. Armor
  and Valence reject negative/non-finite values instead of silently treating
  them as zero; a blank means zero. Overflowing computations and non-finite
  weapon damage, multishot or used mod totals are rejected rather than shown
  as valid results. Loading
  preflights the complete saved calculation before replacing the current build.
  Import caches use actual file bytes, preventing stale parses after restores
  or replacements that preserve a file's size and modification time.
- The shared percentile helper now handles equal infinities and interpolation
  between large finite extremes without producing an accidental NaN or
  infinity; NaN samples are rejected. This is a helper edge-case correction,
  not evidence that ordinary successful simulator trials had infinite samples.
- DE export index 13 is Void. A fresh import and the bundled revision-4
  database represent Sirocco's 2,000 Void; guarded migration updates only the
  missing Void column on matching official rows. Revision-0/1 reimports also
  protect custom collisions and reject identifiable official edits. Mod and
  weapon rows retain extra columns; custom effect annotations, affected foreign
  keys and triggers on updated tables stop the upgrade for review rather than
  being orphaned, lost or invoked. Full rebuilds also refuse affected links and
  catalog triggers that could alter other user tables. All upgrades retain an
  SQLite backup; parser-derived legacy edits are not
  always distinguishable from old parser bugs. Shadow Clones' index-19 Finisher
  damage remains unmodeled rather than being guessed as a different type.
- Cold is capped at four stacks under active Overguard or boss immunity. Ten
  stacks freeze for half the Cold status duration, without refresh or new
  stacks during Freeze, then leave three. The remaining stacks' exact expiry
  is not specified by the cited Wiki; the model uses the freezing proc's
  original expiry. Ocucor now applies the Cold critical bonus in both paths.
- Verglas uses the equipped Electricity and Status Damage bonuses and scaled
  proc durations, and eligible owned DoT ticks build Fired Up. Unsupported
  cursed Rivens and several impossible loadouts are rejected. Its updated
  [results](verglas_prime_sim.md) remain sensitive to the Magnetic-break
  assumption and unverified dynamic Heat inheritance; they are not in-game
  benchmarks. Magnetic's status bonus affects shields and Overguard, while
  Magnetic damage itself is neutral to Grineer health.
- Further data-safety audit: failed refresh publication keeps its recovery marker
  and previous copies instead of rolling back over destinations that an
  unrelated process may have edited; absent targets use no-clobber publication.
  A content hash plus file identity detects edits made during download even if
  size and modification time are restored; new files created during that window
  are preserved. Symlinked export entries are rejected, and lock/recovery checks include
  symlink-target directories. A missing or empty database with any WAL, SHM or
  rollback-journal entry is refused before SQLite can discard a recoverable
  sidecar; a child-process crash/WAL test covers preservation. A locked existing
  database no longer looks like a first-run database, and the bootstrap prompt
  now discloses catalog replacement. Export parsing rejects weapon ZIPs with
  multiple JSON members, duplicate upgrade members and duplicate JSON object
  keys instead of silently importing whichever candidate the parser selected.
  Download validation no longer compares transparently decompressed HTTP bytes
  with the encoded Content-Length. Downloads are bounded to 512 MiB, and LZMA
  manifest expansion is capped at 32 MiB with incremental decoding to avoid
  allocating an unbounded expansion.

The earlier dated sections are an audit history and may describe behavior
before these corrections. The behavior-neutral benchmark now includes Verglas;
reference snapshots made before it was added cannot be compared directly.

## 2026-10-28 follow-up: full formula re-check against the Wiki

Every formula family in the repository was re-read against the live Wiki
wikitext on 2026-10-28 (direct hit and quantization, status chance and proc
weighting, DoT ticks and per-type coefficients, Blast, Corrosive, Heat,
Magnetic, Viral, Puncture, Cold, critical hits, enemy scaling, Riven values,
Condition Overload and the arcane/mod constants used by the simulators). The
per-item verdict is in [wiki_formula_verification.md](wiki_formula_verification.md);
the two substantive gaps found were both about
[critical hits](https://wiki.warframe.com/w/Critical_Hit):

- **The base critical-damage multiplier was never quantized.** The Wiki stores
  it as a 12-bit code, `Code(x) = floor(clamp(x, 0, 32) × 4095/32 + 0.5)` and
  `decoded = Code(x) × 32/4095`. `modules/crit.py` now implements that
  encoding and all six damage models use it (Kuva Nukor 5.0 → 5.001221,
  Ocucor 1.8 → 1.797314, Akarius 2.0 → 2.000488, Alternox and Verglas
  2.2 → 2.203663, Jat Kittag 2.0 → 2.000488). The change is at most 0.2% per build, but the
  earlier figures were not exact.
- **Cold's critical-damage bonus was not reachable from a simulation.** The
  [Cold page](https://wiki.warframe.com/w/Damage/Cold_Damage) grants +0.10x
  with the first Freeze stack, +0.05x per subsequent stack, +1.0x while frozen
  and a 4-stack cap under Overguard; it is additive with Critical Damage mods
  and does not apply to AoE. `modules/crit.py` implements the table, and every
  simulator now builds its crit factor from
  `DummyTarget.crit_damage_multiplier`, which adds the bonus for that target's
  live Freeze stacks (and opts the Akarius radial Blast instance out). Many
  bundled builds combine Cold into another element; primed targets and custom
  Cold-capable builds exercise the standalone `COLD` branch.

The same pass added `modules/crit.py` (modded critical chance, tiers,
normal/critical/average shot, direct+radial sum, weak-point form) plus two
pinned test files, `tests/test_crit_wiki.py` and
`tests/test_wiki_cross_checks.py`. Pinned expectations that encoded an
unquantized base multiplier were rewritten as
`quantize_crit_multiplier(…) × bonus` rather than adjusted by hand.

Nothing else needed a code change: the faction matrix reproduces every
non-neutral cell of the [Overview Table](https://wiki.warframe.com/w/Damage/Overview_Table),
the armor, scaling, DoT, proc-weighting, Blast, Corrosive, Heat-strip,
Magnetic-break, Riven and Condition Overload families match their pages, and
the arcane/mod constants (Cascadia Flare 12% × 40, Sentient Surge 60% per
tendril, Secondary Enervate AFCC, Primed Target Cracker +110%) are correct.
This is a documentation-level agreement, not in-game validation.

### Second pass (same day): end-to-end checks and small fixes

The same pages were re-read through the API and the checks were pushed one
level further, from "the expression matches" to "the repository reproduces the
wiki's own numbers":

- **Quantization end to end.** The
  [Nagantaka Prime example](https://wiki.warframe.com/w/Damage/Calculation#Adding_Physical_and/or_Elemental_Mods/Bonuses)
  now runs through `DamageCalculator` — Puncture 32.4375, Slash 156.78125,
  Viral 259.5, Heat 156.78125, Gas 346, total 951.5, Impact 1.73 quantized to
  0 — and is pinned in `tests/test_crit_wiki.py`.
- **Faction matrix rebuilt from the per-type pages.** All fourteen factions
  were re-derived from the "DAMAGE EFFICACY" quote on each of the thirteen
  damage-type pages (Impact, Puncture, Slash, Cold, Electricity, Heat, Toxin,
  Blast, Corrosive, Gas, Magnetic, Radiation, Viral) and every non-neutral cell
  matches `modules/constants.py`. The overview table's wikitext is malformed
  (resistance `-` markers land on row separators), so the per-type quotes are
  the reference of record for this check.
- **Blast stack expiry.** `Damage/Calculation` states that a stack which
  expires on its own deals `max(1, 0.3 × H)`. The three Blast simulators now
  apply that floor; it is unreachable for the bundled builds (their seeds are
  hundreds of damage), so no pinned number moved.
- **Critical-hit arithmetic.** The tier table, `1 + tier × (CDM − 1)`, the
  average shot, the headshot-crit form and the Cold table were re-checked line
  by line; `modules/crit.py`'s docstring had one wrong decoder output
  (`2.0002442` instead of `2.0004884` for code 256) and that was corrected.
- **Documented deviations that turned out to be non-issues.**
  Cascadia Flare's
  [one-stack-per-damage-instance rule](https://wiki.warframe.com/w/Cascadia_Flare)
  was already enforced by `ocucor_sim` (a new test now pins it), the
  [Corrosive](https://wiki.warframe.com/w/Damage/Corrosive_Damage) armor
  formula `(1 − 50% Heat)·[1 − (20% + 6%·n)]·(1 − 18%·Corrosive Projection)` is
  already multiplicative in `JatTarget.current_armor` (projections aside,
  which no bundled build carries), and
  [Puncture's](https://wiki.warframe.com/w/Damage/Puncture_Damage) flat
  critical chance cannot apply to the Jat Kittag slam build, which deals no
  Puncture damage.
- **CI parity.** `ruff check --select F,E9` (the selection the workflow uses)
  and `compileall` are clean on the current tree.

## 2026-10-28 follow-up: imported mod effects and compatibility

The old parser could mistake [Firestorm's Blast radius](https://wiki.warframe.com/w/Firestorm),
[Comet Rounds' conversion](https://wiki.warframe.com/w/Comet_Rounds), or
[Proton Snap's conditional Wall Latch bonus](https://wiki.warframe.com/w/Proton_Snap)
for unconditional direct damage. It now accepts exact supported damage labels
and rejects leading trigger clauses. Existing official effects are rechecked
on read; custom non-`/Lotus/` effects are not reinterpreted. The exact label
`Melee Damage` remains supported: [Primed Pressure Point](https://wiki.warframe.com/w/Primed_Pressure_Point)
gives +165% base damage at rank 10. The rank-10 export row named Pressure Point
with +200% and a heavy-kill identifier does not match the Wiki's documented
variants and is excluded pending independent identification. Conditional
[Condition Overload](https://wiki.warframe.com/w/Condition_Overload) is not
turned into a permanent base bonus. The parser is intentionally incomplete:
conditions may be split from saved text, and false negatives remain possible.

Primary compatibility is bounded by a pinned WFCD snapshot, with the explicit
[Wiki correction for Coda Bubonico](https://wiki.warframe.com/w/Coda_Bubonico)
using shotgun rather than rifle mods. It also checks selected augment and
melee-subclass restrictions, but not all conflicts, duplicates, mod capacity,
fire modes, conditions or set effects. See [README mod selection](../README.md#mod-selection-and-compatibility)
and `modules/mod_compatibility.py` for the exact conservative rules and unknown
cases. Rev-1 databases receive a backed-up mod-only reparse; rev-0 databases
still receive the weapon-index correction as well. This is not an assertion
that every export row or game mechanic has been verified.

## 2026-10-28 follow-up: Primed Target Cracker

The Nukor, Ocucor and Akarius simulators incorrectly used +120% Critical
Damage for max-rank Primed Target Cracker. The
[Wiki's rank table](https://wiki.warframe.com/w/Primed_Target_Cracker) gives
**+110%**. The three simulator constants and their independent stat fixtures
have been corrected. Earlier archived simulation results remain invalid. A
new, explicitly experimental [Nukor three-mod comparison](kuva_nukor_three_mod_comparison.md)
illustrates how sensitive a specific test is to target and model assumptions;
it does not validate these simulators against the game.

## 2026-10-28 follow-up: Akarius multishot Viral timing

For projectile multishot, the [Viral Wiki](https://wiki.warframe.com/w/Damage/Viral_Damage)
says same-shot hits do not benefit from each other's Viral procs, whereas
[Galvanized Shot](https://wiki.warframe.com/w/Galvanized_Shot) counts
multishot hits sequentially. The Akarius simulator now snapshots Viral at the
start of each ammo shot while retaining live status counts for GunCO and live
Viral for delayed damage. Grouping impact and detonation under that snapshot,
independent crit rolls, and fixed hit ordering are still weapon-specific
assumptions. Deterministic tests cover the chosen behavior, not in-game
validation. The new [Akarius comparison](akarius_prime_viral_corrosive_comparison.md)
shows a Heat-timing sensitivity that reverses the Eximus mean ordering and
includes a one-hit Overguard overflow-discard sensitivity.

## 2026-10-28 follow-up: Ocucor Riven, Puncture, and tendrils

The old Ocucor simulator mixed up several Riven layouts: a 1.2-disposition,
max-rank two-positive/one-negative Pistol Multishot midpoint is **+177.8%**,
not +134.7%. Its selectable midpoint values now match the corresponding CSV
column. The single-target simulator can start with carried-over Sentient Surge
tendrils, tracks Puncture's flat crit bonus, and drops tendrils on an empty
magazine or reload. The illustrative room model distinguishes primary/status
kills from direct tendril kills, resets target ramp on a fresh target, and
credits fatal Heat applications to Flare. These are unit-tested assumptions,
not validation against gameplay. The [Ocucor comparison](ocucor_enervate_flare_comparison.md)
uses the requested Multishot/Viral Riven and tests Flare ramp, Heat assumptions,
and an explicitly hypothetical multi-target Enervate sensitivity. The Wiki's
single-hit AFCC formula does **not** validate the latter's crowd behavior. A
[later Riven comparison](ocucor_viral_dilution_comparison.md) tests the effect
of different positive-layout weights, Viral status dilution and a separate
Reload Speed value; these are still experimental simulations.

## 2026-10-28 follow-up: Jat Kittag heavy-slam spam

The historical Jat simulation does not support reliable Afflictions/Gas/Blast
rankings. A new [analytical comparison](jat_kittag_slam_spam_comparison.md)
separates Initial Combo recovery, approximate status probabilities and
**direct-only** benchmarks from unknown TTK and area damage. It compares Focus
Energy and Focus Radon, ordinary Gas, and two feasible spliced-Gas Rivens
without adding a ninth weapon mod. It also distinguishes first recovery from
long-run combo sustainability. The Wiki's first-hit status eligibility and
Lifted +12 bug are documented, but current Blast and damaging-DoT requirements
are disputed; no definitive arcane or crowd-clear ranking is asserted. A
[follow-up build](jat_kittag_gas_cold_damage_build.md) deliberately drops Primed
Pressure Point to fit Fever, Focus Energy and a spliced Gas / Cold / Damage
Riven. It validates the specified element order and reports only idealized
first-hit rolls, neutral direct damage, and a conditional Wiki-derived Magnetic
break calculation—not a defense-routing or Afflictions simulation. A later,
separate [slam-count sensitivity experiment](jat_kittag_expected_slams.md)
models two exact eight-mod builds with sampled crit/status rolls, a user-requested
no-overflow rule and explicit alternative Afflictions/status-timing hypotheses.
It is not a validated gameplay TTK, and its isolated shieldless targets do not
establish a crowd-clear or shielded-enemy ranking.

## 2026-10-28 follow-up: Riven table trait eligibility

The generated Riven tables incorrectly listed negative primary elements, Punch
Through, melee damage, Initial Combo and Additional Combo Count Chance, and
listed a positive Chance to Gain Combo Count. The [Riven Mods Wiki](https://wiki.warframe.com/w/Riven_Mods)
marks those signs unavailable. Its rank-8 Initial Combo row conflicts with its
coefficient legend; [Melee Combo](https://wiki.warframe.com/w/Melee_Combo)
explicitly says Initial Combo is positive-only, so the generator follows that
more specific statement. Unrollable entries are now `null` in JSON and blank in
CSV, rather than plausible-looking numbers. Punch Through is displayed in
meters, not percent, and the negative-only Chance to Gain Combo Count uses the
Wiki's inverted display sign. The 1.2 tables were regenerated; other existing
rollable values were compared and did not change. The Alternox CSV loader now
skips unavailable traits and preserves plain/faction units instead of dividing
all entries by 100; its compared percent-based values were unchanged.
Weapon-specific roll restrictions and spliced traits remain out of scope;
binary64 is not exact in-game binary32 arithmetic. The earlier simulation
artifacts are unchanged.

## 2026-10-28 follow-up: weapon export collisions and hit components

The bundled DE export contains two different `Grimoire` rows. The old importer
used the last name-keyed row, selecting the Doppelganger's 25 Impact/Puncture
instead of the player weapon. `modules/weapon_export_policy.py` now explicitly
prioritizes the player ID regardless of export order, rejects a missing player
entry and unrecognized same-name conflicts in modeled fields, and retains the
old entry for safe legacy-coverage checks. Revision 3 repairs an existing
revision-1/2 row only if it exactly matches the saved Doppelganger entry; it
retains a SQLite backup and refuses to overwrite an edited row. Revision 0
reimports covered export rows with the custom-row and identifiable-edit guards
noted above. Same-name entries that differ only in ID are not fully resolved
by this guard.

The player export's **150 Electricity is not a single 150-damage hit**: the
[Grimoire Wiki](https://wiki.warframe.com/w/Grimoire) separates primary fire
into 100 direct plus 50 radial. The desktop model still treats the exported row
as one instance, with no radial falloff or separate quantization. Its Final
value is therefore not a reliable per-hit prediction for this and other rows
that aggregate distinct components. Alternate fire and per-attack modeling
remain unimplemented. This correction is export- and Wiki-checked, not
in-game validation.

The mod aggregator and calculator now share the Wiki's last-listed Riven
primary-element ordering; tests include mixed primary, secondary and faction
stats across slots. Riven recognition still relies on the word `Riven` in the
mod name, and a plain already-aggregated dictionary cannot preserve slot
provenance. Do not assume arbitrary named Rivens are detected.

## Scope and findings

| Area | Checked and changed | Remaining limitations |
| --- | --- | --- |
| Desktop direct-hit calculator | Uses signed nearest-1/32 quantization of modded base damage, without intermediate display rounding. Applies the faction/type table, square-root armor DR and the exceptional >2700 armor branch. Arsenal totals use innate multishot, or one hit for melee rows without multishot. | Treats the exported row as **one non-critical health hit**; some rows combine multiple real hits and cannot be interpreted per hit. It does not calculate falloff, shields, Overguard, critical hits, status effects, enemy-specific resistances, special attacks, modded multishot, or actual DPS. Data/attack modes imported from the export can be incomplete. |
| Export/import data | Corrected DE `damagePerShot` indices for Heat (3), Cold (4), Electricity (5) and Void (13); select the player Grimoire over its Doppelganger. The bundled database is revision 4; legacy databases upgrade from local exports with a backup and preservation guards. | Export snapshots may be stale, aggregate hits, omit attack modes or include unmodeled types (such as Shadow Clones' Finisher damage). Incomplete base components produce a warning. Some legacy derived-field edits are indistinguishable from parser bugs; keep backups. |
| Mods, progenitors, factions | Ordered mod effects are passed to the calculator. Primaries are paired in slot order, followed by innate and progenitor primaries in Heat/Cold/Electricity/Toxin order; the last-listed Riven elemental stat has priority. A pre-combined element remains independent. `X1.55` is interpreted as a +55% faction bonus, not +155%; Narmer does not inherit Grineer/Corpus bane. | A bare `CalculationInputs.mods` dictionary cannot preserve the original pairing history; callers needing exact slot-order resolution should pass `equipped_mods`. Only names containing `Riven` trigger the Riven-order rule. Complex negative elemental stats, nonstandard weapon inheritance, and spliced Riven entry in the desktop UI have not been fully validated. |
| Enemy scaling | Added faction-specific shield curves, Eximus base shields, and unrounded enemy armor DR for damage. Heavy Gunner gadget fixtures and independently transcribed shield/armor examples are tested. | The model follows the wiki infobox **gadget** for Overguard level difference; the article disagrees, as described below. Python binary64 and rounded gadget EHP are not exact in-game binary32 emulation. Supplying the right enemy base stats, faction curves and special exceptions remains the caller's responsibility. |
| Status damage | Wiki examples for Slash, Heat, Toxin, Electricity, Gas, faction double dipping, critical seeds and the tick-group `+1` accumulator have tests. Heat armor strip is one shared 15/30/40/50% ramp. Cold/Freeze adds Critical Damage, caps at four under Overguard or on a boss, freezes at ten for half its status duration and leaves three stacks. | `status_damage.py` uses Python binary64, not the wiki's binary32 intermediate operations. Per-type immunity renormalization, Heat inheritance and exact post-Freeze residual-stack expiries are not modeled. Some simulators use simplified tick clocks. |
| CO / GunCO | The cap on Galvanized's per-status bonus is per type, not a cap on the sum across types; multiplicative `scale` is applied to its CO term. The Cedo and Secondary Shiver source descriptions were corrected. Tests cover selected wiki attack examples and formulas. | The attack catalog is a dated snapshot of community-sourced, changing, attack-specific behavior; **not every row has been independently verified**. The desktop calculator does not automatically apply CO. Simulation assumptions about kill stacks and target statuses must be supplied correctly. |
| Riven tables | Selected Wiki rank-8 range endpoints, rollable trait signs, display units, and the four standard positive/negative layout weights are covered by tests; current default disposition is 1.2. | The vendored tag catalog and every possible stat/roll were not independently verified. Binary32 rounding is not emulated; spliced traits and weapon-specific restrictions are not fully modeled. Historical fingerprint tests use older explicit dispositions and are not assertions about today's disposition. |
| Weapon simulations | Corrected Elementalist's reload/status-damage bonuses, shared Heat strip, stat stacking, burst timing, live GunCO counts, Microwave timing and beam multishot sampling. All six simulators use typed shieldless Overguard/health routing and timed Magnetic-break Electricity; Jat uses faction and combo in its DoT seeds. Added unit and deterministic integration fixtures. | **Experimental, not validated TTK calculators.** Unverified routing assumptions and proc, timing and weapon-specific approximations below materially affect results. Previous rankings and recommendations are invalid. Passing tests do not establish accuracy of a complete simulated fight. |

## Known simulation limitations

1. **Overguard routing is an approximation.** The six simulators now route
   typed hits through enemy Overguard into health without a depletion gate,
   applying Magnetic to Overguard and Viral/armor to health. The exact
   allocation of a mixed hit across the breaking boundary is not specified by
   the wiki: the implementation assumes proportional overflow. Faction *type*
   modifiers apply to the health layer only, because the Overguard page states
   the layer is neutral to every type but Void; the faction *damage* bonus of
   Bane-style mods is a separate multiplier and still reaches both layers.
   Simulated targets have no shields and do not model all other defenses or
   immunities.
2. **Magnetic break behavior is not settled.** The model follows the dedicated
   Magnetic page's forced Electricity proc: `3% × max Overguard × stacks` over
   the six-second base duration, with source status/faction bonuses each
   applied twice, Electricity bonus and modified duration. The first tick is
   immediate and later ticks use current armor and Viral. The general Damage
   and Overguard pages have differing immediate-damage wording. The special
   proc's `+1` accumulator is not specified there and is omitted; the most
   recent Magnetic applier supplies all source modifiers when sources differ.
   Electricity's area damage to *other* room targets is not modeled, and the
   `break_electric` bucket is a model result, not a validated game value.
3. **Blast is approximate and sources disagree.** The simulators use the
   dedicated Blast page's 30%-per-stack single-target hit plus 300%-per-stack
   radial to surrounding enemies, detonating at ten stacks, or four when the
   target is constructed with `boss=True` (the cap the generic
   Damage/Calculation page attributes to bosses and some Eximus). Which Eximus
   share that cap is not documented, so the bundled reference targets stay at
   ten and the Akarius sensitivity runs the four-stack variant explicitly.
   Death-triggered detonations and routing still need in-game checks.
4. **Some proc timing and inheritance are simplified.** Heat groups now tick
   from their first application, Nukor Toxin and Jat Toxin tick independently,
   and Jat Gas/Alternox Electricity use application-relative pulses. The
   eligibility of newly added Heat stacks and synchronization/consolidation of
   other same-time pulses remain modeling assumptions. The Nukor/Ocucor models
   merge same-target beam damage and status chance so multishot contributes
   to both proc seeds and proc counts, as the [Multishot Wiki](https://wiki.warframe.com/w/Multishot)
   describes; that does not establish every weapon-specific interaction.
   First-proc Heat inheritance across sources or changing same-source buffs,
   exact restoration, many immunities and binary32 intermediate arithmetic are
   not modeled (the base critical-damage multiplier *is* quantized, and Cold's
   Freeze bonus is applied from the target's stacks). Beam ramp recovery/reloads are
   approximate; the Nukor model applies ramp to direct hits but not status
   seeds, whose ramp interaction is not established here. The Nukor room
   simulation rolls status on a fatal direct hit only to apply the Blast
   rule (a killing blow that procs Blast still detonates, and a death settles
   the stacks the target already had); every other proc from a fatal hit is
   discarded, and its room results still cannot support crowd-clear rankings.
5. **Jat Kittag:** Melee Afflictions' immediate damage and full cross-status,
   faction and status-damage re-seeding are omitted; Blast procs, Gas damage
   to nearby room targets, exact Lifted timing, and Seismic Wave's effect on
   DoT seeds are not fully modeled. Whether a live damaging DoT is required to
   replicate non-damaging statuses such as Corrosive/Viral is **disputed**:
   a [2026 forum report](https://forums.warframe.com/topic/1512645-melee-afflictions-the-dot-requirement-and-blast-status/)
   describes such a requirement with exceptions, while the
   [Wiki's Afflictions page](https://wiki.warframe.com/w/Melee_Afflictions)
   gives an incomplete and potentially outdated account. Neither is a
   definitive current answer. The historical simulator also assumes the
   target must already be Lifted, although the Wiki says a status from the
   triggering hit can be eligible. The modeled heavy-slam seed includes combo
   and faction, with faction applied again at tick time.
6. **Alternox and data:** the analytic DPS calculation assumes maintained kill
   stacks and saturated Viral where applicable; its average-crit/status
   calculation cannot reproduce every consolidated pulse. The stochastic
   default target is a plain shieldless Heavy Gunner, and its Riven candidate
   grid covers only a subset of elemental orders. The bundled database is a
   snapshot: for example, its Akarius Prime fire rate is 3.9007 while the
   wiki infobox shows 3.67; the simulator uses the latter.
7. **Other loadout assumptions:** kill-stack uptime, averaged Secondary
   Enervate below 140% crit chance, fixed enemy positions, weak points,
   multi-target interactions and special weapon/ability interactions are
   simplified. Trial summaries sort samples and use linearly interpolated
   percentiles; `trials_attempted` and `timed_out` expose censored runs, while
   the reported statistics include successful kills only. Infinity means no
   kill was observed within the simulation cutoff, not that a kill is
   impossible. Values produced by rerunning a simulation are model outputs,
   not independently verified wiki facts.

The old per-weapon reports are retained as explicitly marked historical
archives, not recommendations. No new ranking is claimed by this audit.

## Source disagreements and choices

- [Enemy Level Scaling](https://wiki.warframe.com/w/Enemy_Level_Scaling)
  states `level - 1` for Overguard; the live
  [enemy infobox gadget](https://wiki.warframe.com/w/MediaWiki:Gadget-enemyinfoboxslider.js)
  uses `level - base_level`. `enemy_scaling.py` follows the gadget; the two
  choices give different dummy Overguard and EHP values.
- [Damage/Calculation](https://wiki.warframe.com/w/Damage/Calculation)
  describes the scale as **modded base damage / 32**, but also contains
  conflicting prose about whether base-damage and faction bonuses enter the
  scale. The direct calculator uses modded base damage for the scale and
  applies faction bonuses after quantization; this choice is not a claim
  that the contradiction has been resolved.
- [Magnetic Damage](https://wiki.warframe.com/w/Damage/Magnetic_Damage)
  describes a forced Electricity proc on shield/Overguard break; the general
  [Damage](https://wiki.warframe.com/w/Damage) and
  [Overguard](https://wiki.warframe.com/w/Overguard) pages use wording that
  can imply an immediate hit instead. Simulators follow the dedicated page as
  an approximation, not as a verified exact mechanic.
- **Player and enemy gating differ.** The Overguard Wiki states that player
  Overguard has a 0.5-second invulnerability gate, but enemy Overguard has no
  invulnerability gate [2](https://wiki.warframe.com/w/Overguard). Enemy
  shields instead have a short gate with 95% damage reduction, weak-point and
  other exceptions [4](https://wiki.warframe.com/w/Shield). The simulations
  here do not model shields. A forum claim that both enemy shields and
  Overguard discard all excess damage appears alongside contrary replies
  [8](https://forums.warframe.com/topic/1410924-how-do-magnetic-procs-affect-damage-that-carries-over-to-health/);
  it does not establish the mixed-hit overflow calculation.
- Community discussions do not resolve the remaining Overguard questions.
  One Reddit discussion
  says faction bonuses apply regardless of health type [1](https://www.reddit.com/r/Warframe/comments/1fqur7h/faction_weaknesses/),
  while a calculator author says their spreadsheet was changed to use
  Overguard's own resistances [27](https://www.reddit.com/r/Warframe/comments/1hrl099/weapon_builderdamage_calculator_spreadsheet/).
  Another player reports that Elementalist boosts the Magnetic-break proc
  [17](https://www.reddit.com/r/Warframe/comments/1exd62z/why_you_should_get_a_magnetic_progenitor_bonus/),
  but this does not establish the full double-dipping formula. These are
  community reports, not definitive measurements; Reddit was reviewed through
  indexed search excerpts because direct page retrieval was denied.
- [Blast Damage](https://wiki.warframe.com/w/Damage/Blast_Damage) and the
  generic calculation page describe different Blast detonation/cap behavior;
  simulations use the former as an approximation, not a settled answer.
- [Armor](https://wiki.warframe.com/w/Armor) gives the square-root enemy
  formula at or below 2700 and a different `armor/(armor+300)` branch above
  2700. The normal enemy scaling model floors/clamps ordinary armor; the
  direct calculator accepts a manually entered exceptional armor value. The
  Wiki also describes a minimum of 1 per damage type reduced by armor; the
  desktop calculator and shared typed routing apply a minimum to positive
  damage, but the separate scalar Jat slam-count model does not. That is a
  further limitation for sufficiently small damage events, not a validated
  change to the archived sweep.

## Main references

- [Damage and elemental modding](https://wiki.warframe.com/w/Damage),
  [Damage/Calculation](https://wiki.warframe.com/w/Damage/Calculation),
  [Damage type table](https://wiki.warframe.com/w/Damage/Overview_Table),
  [Faction Damage Bonus](https://wiki.warframe.com/w/Faction_Damage_Bonus)
- [Armor](https://wiki.warframe.com/w/Armor),
  [Enemy Level Scaling](https://wiki.warframe.com/w/Enemy_Level_Scaling),
  [Overguard](https://wiki.warframe.com/w/Overguard)
- [Damage over Time](https://wiki.warframe.com/w/Damage_over_Time),
  [Status Effect](https://wiki.warframe.com/w/Status_Effect),
  [Heat](https://wiki.warframe.com/w/Damage/Heat_Damage),
  [Blast](https://wiki.warframe.com/w/Damage/Blast_Damage),
  [Magnetic](https://wiki.warframe.com/w/Damage/Magnetic_Damage)
- [Condition Overload (Mechanic)](https://wiki.warframe.com/w/Condition_Overload_(Mechanic)),
  [Galvanized Shot](https://wiki.warframe.com/w/Galvanized_Shot),
  [Cedo](https://wiki.warframe.com/w/Cedo),
  [Secondary Shiver](https://wiki.warframe.com/w/Secondary_Shiver)
- [Riven Mods](https://wiki.warframe.com/w/Riven_Mods),
  [Pistol Elementalist](https://wiki.warframe.com/w/Pistol_Elementalist),
  [Cascadia Flare](https://wiki.warframe.com/w/Cascadia_Flare),
  [Melee](https://wiki.warframe.com/w/Melee),
  [Seismic Wave](https://wiki.warframe.com/w/Seismic_Wave),
  [Melee Afflictions](https://wiki.warframe.com/w/Melee_Afflictions)
- [Continuous Weapon](https://wiki.warframe.com/w/Continuous_Weapon),
  [Multishot](https://wiki.warframe.com/w/Multishot),
  [Fire Rate](https://wiki.warframe.com/w/Fire_Rate),
  [Hek](https://wiki.warframe.com/w/Hek),
  [Ignis Wraith](https://wiki.warframe.com/w/Ignis_Wraith),
  [Tenet Glaxion](https://wiki.warframe.com/w/Tenet_Glaxion),
  [Alternox Prime](https://wiki.warframe.com/w/Alternox_Prime)

Run all offline tests with `python -m unittest discover -s tests -q`. The
independent wiki fixtures live in `tests/test_damage_formulas.py`,
`tests/test_enemy_scaling.py`, `tests/test_status_damage.py`,
`tests/test_riven_wiki.py`, and `tests/test_condition_overload.py`;
`tests/test_database_calculator_integration.py` checks bundled weapon and mod
fields. `tests/test_damage_routing.py`,
`tests/test_simulator_status_regressions.py` and
`tests/test_simulator_routing_integration.py` exercise selected routing,
status, source-modifier and cutoff invariants; `tests/test_trial_statistics.py`
checks summary percentiles and timeouts. None establish validated TTKs.

## 2026-10-28 (evening): live re-read and a behaviour-neutral optimisation pass

The core pages were fetched from the Wiki again today and compared expression
by expression with the code. The per-formula table is §6 of
[wiki_formula_verification.md](wiki_formula_verification.md); no formula had
drifted, so no pinned number moved.

One expression was **missing** rather than wrong: `Critical_Hit`'s headshot
critical multiplier `Headshot Multi × (1 + Tier × (2 × Total CDM − 1))` is not
the weak-point average that `Damage/Calculation` defines and that
`modules/crit.py` already implemented. It is now
`crit.headshot_crit_multiplier`, pinned to the page's Lanka example (49.8) and
to its exclusions (heads only, 1.0x-headshot weapons never benefit). No
simulator calls it: none of the bundled models fires at heads, and the page
gives no way to apply it to body parts, so wiring it in would need a scenario
that shows a difference.

The same pass removed duplication that could hide future drift: the critical
tier expression `1 + tier × (CDM − 1)` was spelled out at seven sites in five
modules and now comes from `crit.crit_multiplier_for_tier`. The optimisation
review (timings, the remaining opportunities and why they were declined) is
[optimization_review.md](optimization_review.md); results are bit-identical,
verified by `tools/bench_models.py`.

Still open, unchanged by this pass: the Jat Kittag Riven critical-damage
constant (`1.013` versus the derived `1.0125`), status-immunity
renormalisation, shields, AoE critical rules, and the Overguard-level-input
conflict recorded in §4.1.
