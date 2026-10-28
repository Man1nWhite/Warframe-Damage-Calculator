# Optimisation review: damage models and the calculation path

Reviewed **2026-10-28** on the repository at
`ac627f9` plus this branch's changes. This file records what was measured
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
python -m unittest discover -s tests -q                     # 626 tests, one skip
python -m ruff check . && python -m mypy
```

Results are machine-dependent; the *digest* is not.
