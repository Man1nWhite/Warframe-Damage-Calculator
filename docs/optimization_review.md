# Optimisation review: damage models and the calculation path

Reviewed **2026-10-28** on the repository at
`ac627f9` plus this branch's changes. A **second pass** the same evening (§7)
re-measured all five simulators and took four more wins; the tables in §2
describe the first pass only. This file records what was measured
before changing anything, what was changed, what the change cost in
readability, and which further opportunities exist but were **not** taken.
It is not a claim that the simulators are fast in absolute terms: they are
research models that run tens of thousands of trials per report.

Companion documents: [`formula_audit.md`](formula_audit.md) (scope and open
deviations), [`wiki_formula_verification.md`](wiki_formula_verification.md)
(the per-formula verdicts this pass re-read).

---

## 1. Method

Every published figure in `docs/` is model output with a pinned seed, so a
speed change is acceptable only when the results are **bit-identical** —
"close enough" is not a criterion, because a reordered RNG draw silently
invalidates a 44-record JSONL artifact that has a recorded SHA-256.

`tools/bench_models.py` (new in this pass) makes that checkable:

```bash
python tools/bench_models.py --snapshot /tmp/before.json   # before editing
python tools/bench_models.py --check /tmp/before.json      # after editing
```

It runs the Jat Kittag slam, Kuva Nukor and Ocucor models on fixed seeds,
serialises the *complete* trial records (not a rounded summary) and compares a
SHA-256. Timing is wall-clock milliseconds per trial, best of three runs, on
one core; it is a regression indicator, not a benchmark of the game.

The harness itself was checked against the unmodified tree: the digest
`d87cd4b4af939dca…` is produced by both the pre-change and post-change code
for the same seeds.

## 2. Measurements

`ms/trial`, best of three; identical seeds before and after.

| Model | Before | After | Change |
| --- | --- | --- | --- |
| `jat_kittag_sim.simulate` | 9.54 | 7.71 | **−19%** |
| `kuva_nukor_sim.simulate` | 1.16 | 1.06 | −9% |
| `ocucor_sim.simulate` | 3.70 | 3.34 | −10% |

Consequences at the scales this repository actually runs:

- the documented Jat slam-count sweep (170,000 trials, seed `20261028`) is a
  single-process job; at 9.54 ms/trial it is ~45 min of CPU, at 7.71 ms/trial
  ~36 min. Re-running it is still a lunch break, not a command.
  **Corrected in §7.4:** the sweep runs `jat_kittag_slam_counts`, not the model
  timed above, and the complete suite measures ≈ 55–60 s.
- the whole unit-test suite is ~9 s (614 tests before this pass added its
  own) either way, so the change is not visible there.
- the desktop calculator's per-keystroke path was measured separately and is
  not a bottleneck (section 5).

## 3. What was changed

1. **`damage_routing.route_enemy_hit` builds one dictionary instead of two.**
   The route allocated a faction-modified `typed` dict comprehension and then
   walked the same input a second time to total Overguard. It is now a single
   pass that fills both. The accumulation order of every sum is unchanged, so
   the floating-point result is identical; the health loop still sees the same
   insertion order.
2. **`jat_kittag_sim._next_status_tick` scans instead of building generators.**
   It used two generator expressions plus `min(..., default=inf)` twice and was
   called once per simulated event. A hand-written loop keeps the deliberate
   asymmetry between Gas (`<` expiry) and Toxin (`<=` expiry) and returns the
   same value.
3. **The critical-tier expression has one implementation.** Five files spelled
   out `1 + tier * (crit_multiplier - 1)` — seven sites in total, including two
   Cold-aware ones. They now call `crit.crit_multiplier_for_tier`, so the
   `Damage/Calculation`/`Critical_Hit` tier rule cannot drift per weapon. This
   is the cheapest of the three changes (the arithmetic is identical) and the
   one that removes a real correctness risk: a future fix to the tier rule
   previously had to be applied seven times.

Nothing else in the model was rewritten. In particular the tick loops, the
proc-selection calls and the `absorb` path are untouched: see section 4 for the
measurements that justify each remaining hot spot.

## 4. Opportunities identified but **not** taken

Ranked by measured cost in the Jat slam model (cProfile, 20 trials, 0.73 s
total after the changes above). Each is a deliberate "no" or "not yet".

1. **Linear scans over status-proc lists (~20% of the profile).**
   `_next_status_tick`, `next_toxin_tick`, `next_magnetic_electric_tick`,
   `has_live_status` and `current_armor` each walk a list. Toxin procs are
   uncapped and Melee Afflictions adds twelve per trigger, so the lists grow
   through a long fight and the cost is quadratic in proc count.
   A heap or a cached "earliest pending tick" would fix the asymptotics, but
   neither is safe to add casually: `_process_status_ticks` resolves same-time
   Gas pulses together and then routes each Toxin tick **in list order**, and
   routing order changes how a hit that breaks Overguard splits across layers.
   Any reordering — including a stable heap — must be proven to keep that order
   for the same seeds, which the digest tool can check, but the change is worth
   more than the ~10–15% it would buy.
2. **`DummyTarget.current_armor` recomputed per hit (~7%).**
   Every routed instance recomputes the Heat strip (a `min` over the Heat proc
   list) and multiplies by the Corrosive factor. Both inputs change only when a
   proc is added or expires. Caching is possible but the invalidation points
   are spread over `prune`, `add_heat`, `consume_heat_tick` and the Jat
   subclass; a stale cache would quietly change armour and therefore damage.
   Not worth the risk for 7%.
3. **`rng.choices` rebuilds its candidate lists per slam (~3%).**
   `list(build.proc_weights)` and `list(build.proc_weights.values())` are
   rebuilt on every slam in three simulators. Hoisting them out of the loop is
   behaviour-neutral and mechanical; it was left alone because it touches three
   simulators for a single-digit win once (1) and (2) are the real targets.
   **Taken in §7.3 item 4.**
   The pre-computed cumulative weights that `random.choices` builds internally
   are *not* a safe hand-optimisation: reproducing them means re-implementing
   the sampler, which is exactly the kind of change that silently shifts seeds.
4. **Parallelising the Jat sweep.** The sweep is embarrassingly parallel across
   trials, so eight workers would cut ~36 min to ~5 min. It is not done because
   the delivered artifact must keep its SHA-256 and its record order; that needs
   an ordered map, a documented worker count in the report and a new seed
   convention, which is a research decision, not a refactor.
5. **Batch DB reads in the GUI.** `ModRepository.fetch_ranked_effects_many`
   already batches the eight slots into one connection and one statement per
   400 keys. The remaining per-keystroke cost is one weapon lookup (0.17 ms),
   one effect fetch (0.33 ms) and one mod search while typing (1.9 ms). Caching
   them across keystrokes would need invalidation on rebuild/refresh and the
   staleness bug is worse than 2 ms; the tables also repaint in Qt, which
   dominates anyway. Left as is, documented here so it is not re-investigated.
6. **Emulating binary32 in the models.** The wiki specifies binary32
   intermediates for quantization, DoT and the critical multiplier. Doing that
   with `numpy.float32` scalar conversions would be slower *and* would change
   every published number; the current binary64 choice is documented as a
   deviation in [`formula_audit.md`](formula_audit.md) §4.9.

## 5. Accuracy opportunities found while checking the formulas

These are not speed work; they are the places where following the wiki exactly
would change a result, so they need a scenario that shows the difference before
they are worth modelling.

1. **Headshot criticals were missing their own expression.** `Critical_Hit`
   gives `Headshot Multi × (1 + Tier × (2 × Total Critical Damage − 1))`, which
   is *not* the weak-point average already implemented from
   `Damage/Calculation`. `modules/crit.py` now has
   `headshot_crit_multiplier` with the wiki's Lanka example (49.8) pinned. No
   simulator uses it: none of the bundled models fires at heads, and the page
   excludes non-head weak points and 1.0x-headshot weapons, so wiring it in
   needs a scenario first.
2. **Status-immunity renormalisation** (`Status_Effect`): a proc type the enemy
   is immune to is removed from the proc-type pool and the remaining chances are
   renormalised. No bundled target has status immunities, so
   `status_damage.proc_type_chances` still only divides by total damage.
3. **Shields** are not modelled at all, so Toxin's shield bypass, Magnetic's
   shield multiplier and the Magnetic break's shield-based seed are all
   untestable in this repository. Adding shields is the largest single accuracy
   gain available and also the largest model change; it needs its own report.
4. **AoE critical rules.** The wiki excludes Cold's Freeze bonus from AoE
   damage (modelled) and describes separate penalty/benefit rules for other AoE
   critical additions (not modelled). No bundled build depends on the gap.

## 6. Reproducing this review

```bash
python tools/bench_models.py --snapshot /tmp/before.json    # reference
#   ... edit modules/ ...
python tools/bench_models.py --check /tmp/before.json       # must match
python tools/bench_models.py --trials 20 --repeats 3        # ms/trial table
python -m unittest discover -s tests -q                     # 627 tests, one skip
python -m ruff check . && python -m mypy
```

Results are machine-dependent; the *digest* is not.

---

## 7. Second pass, 2026-10-28 (late evening): the per-hit path

The first pass took the two cheapest structural wins (single-pass routing, a
hand-written status-tick scan) and stopped. This pass went back to the profile
with the wiki open: every formula inside a hot loop was re-read before it was
touched, so a "faster" expression cannot quietly become a different formula.
The per-page verdicts are in
[`wiki_formula_verification.md`](wiki_formula_verification.md) §7; this section
records the measurements and the changes.

### 7.1 Procedure

1. `python tools/bench_models.py --snapshot /tmp/before.json` on the
   unmodified tree. The harness now covers **all five** simulators (Jat slam,
   Kuva Nukor, Ocucor, Akarius Prime, Alternox Prime) plus the scalar
   slam-count model that generates the 44-record JSONL artifact, instead of the
   original three models, so a change to any of them is digest-checked.
2. Optimise, then `python tools/bench_models.py --check /tmp/before.json`.
   Exit 0 means the complete trial records — every field except the free-text
   trace — hash to the same SHA-256.
3. Timing: `--trials 20 --repeats 5`, best of three runs, on one core.
   Baseline re-measured in a `git worktree` of the pre-change commit with the
   same harness, so the two columns are the same measurement.

### 7.2 Measurements

`ms/trial`, best of three runs of best-of-five repeats, one core.

| Model | Before | After | Change |
| --- | --- | --- | --- |
| `jat_kittag_sim.simulate` | 6.76 | 5.39 | **−20%** |
| `kuva_nukor_sim.simulate` | 0.95 | 0.77 | **−19%** |
| `ocucor_sim.simulate` | 2.98 | 2.33 | **−22%** |
| `akarius_sim.simulate` | 0.81 | 0.72 | −11% |
| `alternox_prime_sim.simulate` | 1.25 | 1.11 | −11% |
| `jat_kittag_slam_counts` (per 100-trial summary, untouched model) | 24.84 | 25.23 | noise |

The digest is identical before and after (`sha256 476ec4f75e018a89…`), so every
figure in `docs/` that was produced by these models still reproduces. The suite
stays around 10 s (630 tests, one GUI skip, including the new artifact guard).

**Run-to-run variance is about ±10% on this machine**, which is larger than the
two smallest rows, so the comparison was repeated with the baseline and the
optimised tree interleaved (three rounds, same harness, best value of each):

| Model | Before | After | Interleaved change |
| --- | --- | --- | --- |
| `jat_kittag_sim` | 6.65 | 5.53 | −17% |
| `ocucor_sim` | 2.94 | 2.36 | −20% |
| `kuva_nukor_sim` | 0.91 | 0.82 | −10% |
| `akarius_sim` | 0.86 | 0.76 | −12% |
| `alternox_prime_sim` | 1.17 | 1.19 | within noise |
| `jat_kittag_slam_counts` (untouched; the noise floor) | 26.64 | 26.29 | −1% |

Read the headline as **−15…−20% on the two models that dominate the bulk runs**
(Jat slam and Ocucor), ~10% on Nukor and Akarius, and *not measurable* on
Alternox, rather than as the exact percentages in the first table. The
untouched slam-count model moving by 1% sets the floor for what counts as a
result here.

### 7.3 What changed

1. **`damage_routing.route_enemy_hit` builds no intermediate dictionary.** The
   first pass collapsed two dictionaries into one; this pass removed it
   entirely. Overguard only needs the starting amounts, and the health
   components only need their faction-modified values once the absorbed
   fraction is known, so the function now scans `damage_by_type` twice instead
   of building `{type: modified value}` and walking it. Both scans visit the
   keys in the same order and perform the same multiplications
   (`amount * modifier * fraction`, left to right), so `health_damage`
   accumulates bit-identically. The armor factor is also skipped when the
   target has no armor, where it was multiplied by zero terms anyway.
   This is the only change that reaches the Akarius/Alternox models, which is
   why their improvement is smaller: they mostly do direct hits.
2. **`DummyTarget.prune` stops rebuilding live lists.** It is called once per
   simulated damage instance, and it allocated a fresh copy of the Heat stack
   list (up to ~90 proc objects in a 6 s Ocucor fight) on every call. It now
   scans first and only rebuilds when a proc has actually expired. The
   `_heat_ended_at` / `_next_heat_tick` bookkeeping runs in exactly the cases
   it ran in before, because "nothing expired" implies the pruned list is
   non-empty.
3. **`current_armor`, `next_heat_tick`, `next_toxin_tick` and
   `next_magnetic_electric_tick` scan with loops instead of
   `min`/`max(generator)`.** The values are identical (`min` over `start`,
   `max` over `refreshed`, `min` over `next_tick` with the same `<` versus
   `<=` expiry asymmetry), but a generator expression costs a resume per
   element, and `current_armor` is on the per-hit path. This is the same trade
   the first pass made for `_next_status_tick`.
4. **`random.choices` candidate lists are hoisted out of the loops** (the third
   item of §4.1, now taken). The candidate list and weight list are fixed for a
   build, so they are built once per trial in `jat_kittag_sim` (single-target
   and room), `kuva_nukor_sim` (single-target and room) and `ocucor_sim`
   (single-target and room). `random.choices` itself, and therefore every
   draw, is untouched — the sampler still builds its own cumulative weights.
5. **`JatBuild.quantized_type_damage` caches the per-type 1/32 quantization.**
   `wiki_quantized_damage(single, modded_base)` depends only on the build, but
   it ran once per type per slam (~3 × 180 = 540 calls per trial). It is now a
   `cached_property`, so a `dataclasses.replace` on the build recomputes it and
   a test pins that (`tests/test_jat_kittag_sim.py`). The per-hit brackets are
   still applied in the original order — `quantized * seismic * combo * crit *
   faction` — because re-associating float products would change the last bits.
6. **`_process_status_ticks` and `apply_melee_afflictions` are single-pass.**
   The tick resolver accumulates Gas seeds and advances each due proc in one
   walk instead of building a "due" list first, and the Afflictions trigger
   counts live stacks and sums their weighted seeds in one walk, rebuilding a
   list only when something has expired. Seed sums keep list order, the
   averaging and the 10-stack cap are unchanged.
7. **`tools/bench_models.py` now hashes six models** — the five simulators plus
   the slam-count model behind the JSONL artifact. Widening the harness was a
   prerequisite, not a side effect: without it the Akarius/Alternox changes in
   (1) would have been unprotected by any digest, and the artifact's model had
   no equivalence check at all. `tests/test_bench_models.py` pins the model
   list, and the new `tests/test_slam_results_artifact.py` re-simulates the
   cheapest artifact row (1,000 trials, ~0.3 s) and requires it to match the
   committed record exactly — the guard whose absence let the staleness in §7.4
   below go unnoticed.

### 7.4 A correction to §2: the 170,000-trial sweep is not a lunch break

The harness widening turned up a wrong statement in §2. That bullet says the
documented slam-count sweep costs "~45 min / ~36 min of CPU". The sweep
(`modules.jat_kittag_slam_count_sweep`) does **not** call
`jat_kittag_sim.simulate`: it drives `modules.jat_kittag_slam_counts`, an
independent scalar model — the repository says so in
`docs/jat_kittag_expected_slams.md` ("the model is independent of the
invalidated `modules/jat_kittag_sim.py`"). Measured per-trial costs of
`summarize` (100-trial samples, this machine):

| Scenario target | ms/trial |
| --- | --- |
| `sp150_eximus` | 0.19 – 0.26 |
| `sp150_normal` | 0.13 |
| `icebind1000_eximus_6p` | 0.36 – 0.49 |
| `normal_status_no_afflictions` (no afflictions, longest fights) | 1.14 |

Weighted by the scenario table in `jat_kittag_slam_count_sweep.SCENARIOS`
(170,000 trials over 44 records), the whole suite is **48 s of single-core CPU**
— measured by running it, not estimated. Consequences:

- Re-running the sweep to reproduce its JSONL is a coffee, not a lunch break;
  the "needs an ordered map and eight workers" argument in §4.4 was solving a
  problem that does not exist. Parallelising it would save ~40 s.
- The expensive model is the *other* one: `jat_kittag_sim.simulate` at
  5–7 ms/trial is what a large exploratory sweep would spend minutes on, and it
  is the one this pass optimised. Any future report that runs
  `jat_kittag_sim` at scale should scale its cost from the §7.2 row.
- No published number is affected — only the estimate of how long it takes to
  reproduce one.
- Running it also turned up a **stale artifact**, which was then **regenerated**.
  The committed `docs/jat_kittag_expected_slams_results.jsonl` predated the
  critical-damage quantization, so 34 of its 44 records no longer reproduced
  (by ≤ 0.04 slams; no median or percentile moves). The cause was proven by
  disabling `crit.quantize_crit_multiplier` and reproducing the old file
  exactly; the new file is deterministic across runs and its SHA-256 is
  `7c584c3454239dbd…` (was `94422cf20a535c30…`). Seven sensitivity cells moved
  in the second decimal. Full record:
  [`jat_kittag_expected_slams.md`](jat_kittag_expected_slams.md#regeneration-record-2026-10-28).

### 7.5 Opportunities identified but **not** taken, again

1. **The Heat stack list is still unbounded and scanned per hit.** `prune` and
   `current_armor` are O(stack count), and the count grows with fight length
   (~90 procs after 6 s of Ocucor fire), so a long fight is still quadratic in
   the number of applications. Fixing it properly means a running sum over
   "procs that have been alive for at least 1 s" instead of the list — i.e.
   changing what `heat_procs` *is*, which tests and the comparison modules
   inspect. Not worth it for the ~10% of the Ocucor model it would buy.
2. **`route_enemy_hit` is still the top entry in the Jat profile (~10%).** A
   single-damage-type fast path would remove one dict iteration for the
   dominant `{"GAS": …}` / `{"TOXIN": …}` calls, but it duplicates the health
   accumulation for one special case; the duplication is a bigger correctness
   risk than the ~3% it buys.
3. **The remaining linear scans over status lists** (§4.1) are unchanged: the
   ordering constraints on same-time Gas pulses and on Toxin routing order are
   the reason, and nothing measured this pass changes that conclusion.
4. **Binary32 emulation, parallelising the sweep, GUI read batching** — all
   still rejected for the reasons in §4.

The three simulator tables in `docs/` that quote timings (`optimization_review`
§2, `next_session_handoff.md`) describe the *first* pass; the numbers above
supersede them for the models they name.

### 7.6 Reproducing this pass

```bash
git worktree add /tmp/baseline fed4507        # the pre-change tree
cp tools/bench_models.py /tmp/baseline/tools/ # same harness, five models
(cd /tmp/baseline && python tools/bench_models.py --trials 20 --repeats 5)
python tools/bench_models.py --check /tmp/before.json        # must match
python tools/bench_models.py --trials 20 --repeats 5        # after
python -m unittest discover -s tests -q                     # 627 tests
python -m ruff check . && python -m mypy
```
