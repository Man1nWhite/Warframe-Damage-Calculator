# Jat Kittag: estimated slams for the two requested builds

**These are model scenarios, not a validated gameplay time-to-kill.** Melee
Afflictions, its interaction with Blast, the timing of added AoE status stacks,
and the effect of Seismic Wave on status seeds are not fully established for
this attack. The figures below are useful for comparing assumptions; the real
number can be outside the displayed outcome percentiles and sensitivity cases.
Do not reuse the invalidated historical Jat simulator's rankings.

## Builds and common setup

Both use **Seismic Wave, Galvanized Elementalist, Galvanized Reflex, Vulcan
Blitz, Galvanized Steel, Focus Energy**, and **rank-5 Melee Afflictions** in
its separate arcane slot. All Galvanized effects start and remain at maximum
stacks; that is a precondition even though the simulated target is isolated.
No frame, companion, aura, faction mod, armor strip, or other damage source is
included. Both have 90% heavy attack efficiency. We assume 5x combo for every
slam and a fixed **0.65 seconds between landings**. This cadence is illustrative,
not measured or derived from attack speed; the focus is continuous slamming,
not waiting for the DoTs to expire. The first slam lands at time zero.

| Build | Remaining two weapon slots | Slam damage types |
| --- | --- | --- |
| **A: earlier** | Spliced **Gas / Cold / Melee Damage** Riven, Primed Fever Strike; **no Primed Pressure Point** | Blast, Gas, Magnetic, Toxin |
| **B: new** | Spliced **Gas / Critical Damage / Critical Chance** Riven, Primed Pressure Point; **no Primed Fever Strike** | Blast, Gas, Electricity |

These are both eight-mod builds. In A, place Focus Energy and the Riven before
Primed Fever Strike so Cold + Electricity form Magnetic and Fever remains
Toxin. B has no ordinary Cold or Toxin mod to combine with Focus Energy. The
**Gas is a spliced attribute**, not a normal Gas roll. B has **no Magnetic,
Toxin, Viral, or Corrosive** in this setup. Actual Riven rolls and their
negative attributes can change the result. The calculations use midpoint
rank-8, normalized-disposition-1.20, three-positive/one-negative values:
+101.25% spliced Gas in both; +101.25% Cold and +185.3% melee damage in A;
+101.25% crit damage and +202.5% crit chance in B. The negative is assumed
not to affect any modeled statistic.

At 5x, before target defenses, the mean **direct hit alone** is about 356,917
for A and 426,821 for B; B's value is about 19.6% larger. This does **not**
include status damage or prove a 19.6% kill-speed difference. A has 48% heavy
crit chance and a 4.4x crit multiplier. B has 108.75% heavy crit chance and a
6.425x multiplier: 91.25% yellow and 8.75% orange crits. Both have 220% status
chance: two independent normal status rolls and a 20% chance of a third.

| Normal first-slam proc probability, approximate | A | B |
| --- | ---: | ---: |
| Gas | 37.2% | 65.4% |
| Blast | 36.8% | 64.8% |
| Toxin | 55.7% | — |
| Magnetic | 54.7% | — |
| Electricity | — | 43.4% |
| Gas and Electricity together | — | 21.6% |

These probabilities use unquantized damage-type weights and do not count
Afflictions or a forced Blast proc. The [Jat Kittag Wiki infobox](https://wiki.warframe.com/w/Jat_Kittag)
lists **Lifted**, not Blast, as the forced proc for the heavy slam.

## Single-target estimates

Both targets are stationary, shieldless Heavy Gunners struck at the **center of
one radial heavy-slam hit**, with no direct weapon-contact hit, no falloff,
headshot, nearby Gas/Electricity overlap, or other external hit. Their scaling
and caveats are in [the target-dummy report](target_dummy_models.md).

| Target | Health | Overguard | Armor / DR |
| --- | ---: | ---: | ---: |
| Level 150 Steel Path **Eximus** | 1,716,837 | 269,919 | 2,700 / 90% |
| Level 1000 **Icebind Eximus, six players** | 25,004,266 | 1,552,453 | 2,700 / 90% |
| Level 150 Steel Path, **ordinary** | 286,140 | 0 | 2,700 / 90% |

The first row below represents the displayed-rank assumption of one +6-stack
Afflictions pass whenever the modeled Lifted trigger is eligible. The other
rows use the same assumptions. Means are averages of simulated **integer slam
counts**. Parentheses show the median and the 10th–90th percentile of simulated
counts, **not** a confidence interval for actual gameplay.

| Target | A: Gas/Cold/Damage + Fever | B: Gas/Crit Damage/Crit Chance + PPP |
| --- | ---: | ---: |
| SP 150 Eximus | **6.0** (median 6; 5–7) | **4.6** (median 4; 4–6) |
| Icebind 1000 Eximus, six players | **9.3** (median 9; 8–11) | **9.4** (median 9; 8–10) |
| SP 150 ordinary | **3.6** (median 3; 3–5) | **2.4** (median 2; 2–3) |

There are 10,000 trials **per build per target**, with independent crit and
weighted status rolls. All 60,000 trials in this table killed the target. A
DoT killing the enemy between landings is counted with the slams already made;
it does not count the next scheduled slam. The means and percentiles describe
only the specified toy model and should not be rounded into guarantees.

Within this scenario, B is favored against the SP 150 targets. On the much
larger Icebind Eximus, the means are effectively a tie for practical purposes:
A's Magnetic-break Electricity and Toxin can contribute to Afflictions
cross-seeding, while B has stronger/more consistent crits, Gas and Electricity.
Changing the uncertain mechanics can change even that relative order.

## Sensitivity: plausible alternatives, not bounds

Only the named assumption changes from the +6-stack scenario, unless otherwise
stated. Each cell is a mean number of slams from 3,000 trials per build and
target. These examples do **not** bracket all possible real behaviors.

| Mechanical hypothesis | SP 150 Eximus A / B | Icebind 1000 six-player Eximus A / B |
| --- | ---: | ---: |
| One +6 pass, shared AoE pulses, 0.65 s (main table) | 6.00 / 4.59 | 9.33 / 9.41 |
| One +12 pass instead of +6 | 5.29 / 4.11 | 8.20 / 8.07 |
| Two **sequential** +6 passes per eligible slam | 4.65 / 3.60 | 6.76 / 6.72 |
| Per-proc AoE clocks rather than the shared-pulse approximation | 5.80 / 4.29 | 8.99 / 8.98 |
| Seismic's 3x slam bracket also multiplies status seeds | 5.02 / 3.82 | 7.80 / 7.28 |
| Magnetic-break Electricity also contributes its inferred seed to Afflictions | 5.97 / 4.58 | 8.56 / 9.40 |
| Lifted can trigger on the **direct** hit that breaks Overguard | 5.52 / 4.39 | 8.49 / 8.71 |
| Literal Gas bonus also applies to Afflictions-created Gas stacks | 5.78 / 4.44 | 9.12 / 8.98 |
| 0.40 s between landings | 6.64 / 4.98 | 10.19 / 10.14 |
| 1.00 s between landings | 5.10 / 4.28 | 8.21 / 8.68 |

Faster spam can require **more slams** because there is less elapsed time for
ticks between attacks; this does not imply it takes longer in seconds. One
+12 pass and two +6 passes are distinct hypotheses: the latter lets the
second pass re-seed from the first. The [Afflictions Wiki](https://wiki.warframe.com/w/Melee_Afflictions)
lists +6 at rank 5 and describes a +12 Lifted bug; it does not establish which
of these implementations is correct for the current Jat Kittag attack.

## Exactly what the model assumes

* One sampled critical tier per slam, two or three weighted normal statuses,
  and a 5x combo multiplier. It routes direct damage, Gas, Electricity,
  Toxin, and single-target Blast damage through Overguard and then health.
  The baseline includes ordinary Blast fuses (1.5 s, or early at ten stacks),
  but not the 5 m Blast explosion against **other** enemies. It includes no
  guaranteed Blast status beyond the normal rolls.
* Gas stacks cap at ten and replace the oldest; Toxin and Electricity stack.
  The baseline approximates Gas and Electricity with shared, one-second
  type-specific pulses; the first effect of a type ticks immediately, but
  adding stacks to an already active effect does not create a separate
  immediate pulse. The Wiki describes consolidated Electricity ticks and
  immediate AoE status damage, but exact timing of new and Arcane-added stacks
  is not resolved here. The per-proc-clock case tests another interpretation.
  Both are approximations, not game event traces. Toxin first ticks after 1 s.
* Afflictions uses the Wiki's per-type mean of damaging proc base seeds and
  sums those means for its new stacks; +80% Galvanized Elementalist status
  damage applies to the original and again to new stacks. Current-hit
  statuses can supply a seed. New Toxin and Electricity stacks receive their
  respective melee elemental bonuses; the baseline does **not** assume the
  literal Gas bonus applies to *Arcane-created* Gas stacks. The baseline
  treats the Wiki's “Affliction Damage Hit” as a seed and does not add a
  separate immediate hit. A CLI option explores an alternative interpretation.
* For the model, a damaging DoT is required to replicate statuses, and Lifted
  cannot trigger while Overguard is active. The main case defers the trigger
  to a later slam if the target had Overguard at that slam's start. The
  alternative permits it when the **direct slam** breaks Overguard. A [2026
  forum report](https://forums.warframe.com/topic/1512645-melee-afflictions-the-dot-requirement-and-blast-status/)
  describes a DoT requirement with exceptions; a separate [Jat report](https://forums.warframe.com/topic/1515280-jat-kittag-melee-afflictions/)
  describes inconsistent Blast behavior. Neither establishes all current
  mechanics, and the Wiki is marked for update. Exact Blast re-seeding,
  same-hit ordering and any separate Arcane damage remain uncertain.
* On an Overguard break, existing Magnetic stacks create Electricity with
  the Wiki's **3% of maximum defense per stack over six seconds**, before
  modifiers and mitigation—not 3% per tick. The baseline uses +80% status
  damage twice and Focus Energy's +60% Electricity once, even though Focus
  combines into Magnetic in A. Thus its nominal total is `0.03 x 1.8^2 x 1.6`
  = **15.552% of maximum Overguard per stack over six seconds**, before
  defenses and other effects. Whether the same attack's Magnetic application
  occurs before its break, and how that special Electricity proc should seed
  Afflictions, are not settled; the main case excludes its magnitude as an
  Afflictions seed and a sensitivity includes an inferred seed.
* At your request, the **breaking damage event has no overflow** into health.
  Subsequent damage events can hit health immediately; no 0.5-second timed
  immunity is imposed. The [Overguard Wiki](https://wiki.warframe.com/w/Overguard)
  distinguishes a player's timed gate and says enemies have no invulnerability
  gate. The no-overflow rule is therefore an **explicit comparison assumption**,
  not a claim that the Wiki confirms an enemy gate. The targets have no shields,
  so these runs do not test shield gates or Toxin shield bypass.
* All relevant damage types are treated as neutral to these Grineer targets;
  health retains 90% armor reduction and Overguard has no armor reduction.
  Exact binary32, critical, damage-type and status-tick `+1` rounding,
  proc grouping, animation, CC timing and engine ordering are approximated.
  The fixed 5x combo assumes no other combo sources and no loss of stacked
  Galvanized bonuses. Icebind's optional Archaic Armor and Bolstered
  Belligerents restrictions are not modeled.

## Shields and crowds

A's Magnetic stacks amplify shield/Overguard damage and can create Electricity
on a defense break; A's Toxin can bypass **shields**, though not Overguard or
armor. B has neither normal Magnetic nor Toxin, so results against shielded
Corpus cannot be inferred from the Grineer table. Actual shield gating and
break-event ordering must be specified separately.

For groups, B's higher Gas and Blast proc probabilities and normal Electricity
are attractive, but the isolated-target model excludes nearby Gas clouds,
Electricity area damage, Blast explosions, and all crowd geometry. **Vulcan
Blitz** only explodes on a kill, so it does not help before the isolated
initial target dies; its 60%-of-dead-target-maximum-health component, flat
Blast damage, 6 m radius, falloff, line of sight and target mitigation can
change a crowd result substantially. Do not treat either single-target table
as a room-clear ranking.

## Reproduction and references

```bash
# Complete documented suite: 44 rows / 170,000 trials, JSON Lines
.venv/bin/python -m modules.jat_kittag_slam_count_sweep > docs/jat_kittag_expected_slams_results.jsonl

# Main model on SP150 Eximus; add e.g. --affliction-passes 2,
# --stacks 12, --seed-slam-factor 3, or --per-proc-aoe-ticks for alternatives.
.venv/bin/python -m modules.jat_kittag_slam_counts --target sp150_eximus --trials 10000
.venv/bin/python -m unittest tests.test_jat_kittag_slam_analysis \
    tests.test_jat_kittag_slam_counts tests.test_slam_results_artifact
```

The [raw results](jat_kittag_expected_slams_results.jsonl) contain scenario
parameters, seed, counts, distributions, standard errors and timeout counts.
Passing tests establishes internal consistency, not game accuracy. The model
is independent of the invalidated `modules/jat_kittag_sim.py`.

### Regeneration record (2026-10-28)

The artifact was regenerated from the current tree on 2026-10-28. It had gone
stale: the copy committed before that date predated the 12-bit base
critical-damage quantization (`Critical_Hit`; see `formula_audit.md`,
2026-10-28), so 34 of its 44 records no longer reproduced. The cause was
established before anything was overwritten, not assumed:

- Jat Kittag's base multiplier is now the decoded `2.0004884` rather than `2.0`.
  Build B (`focus_gas_cc_cd`) is the crit-damage build, so its means move in the
  second decimal; build A's records move only in the third decimal or beyond;
- with `crit.quantize_crit_multiplier` replaced by the identity, the current
  model reproduced the old artifact **exactly** — every mean, trigger mean and
  histogram bucket — so nothing else had drifted;
- the quantization is the wiki's rule and is correct, so the artifact, not the
  code, was the stale half.

Scope of the change:

- command unchanged: `python -m modules.jat_kittag_slam_count_sweep`, seed
  `20261028`, 170,000 trials over 44 records, ~50 s;
- the run is deterministic: two consecutive runs produced byte-identical files
  (SHA-256 `7c584c3454239dbd6be79a83fe2a695f4bbcc389fdbfff0beef62146f091000e`,
  which replaces `94422cf20a535c30d58e32fd584bdca1672ae37c8a0edd4232cc22112218c982`);
- `attempted`, `kills` (all trials killed), `timeouts` (zero everywhere),
  `median_slams`, `p10_slams` and `p90_slams` are unchanged in **every** record,
  so the distributions and the main table above are untouched;
- the largest mean shift is 0.041 slams (`two_sequential_six_stack_passes`,
  Icebind, build B: 6.7650 → 6.7243).

Seven cells of the sensitivity table moved in the second decimal and were
updated from the new file rather than by hand. Five are shifts caused by this
regeneration; two more (`3.61`, `5.11`) were already 0.01 high against the
previous file as well (`3.6047`, `5.1047`) and are corrected here:

| Sensitivity row | Icebind A / B, previous → regenerated |
| --- | --- |
| One +6 pass, shared AoE pulses (main table) | 9.33 / **9.45 → 9.41** |
| One +12 pass instead of +6 | 8.20 / **8.10 → 8.07** |
| Two sequential +6 passes | 6.76 / **6.77 → 6.72** (SP 150 B: **3.61 → 3.60**) |
| Per-proc AoE clocks | 8.99 / **8.99 → 8.98** |
| Magnetic-break Electricity seeds Afflictions | 8.56 / **9.44 → 9.40** |
| Literal Gas bonus on Afflictions stacks | 9.12 / **9.02 → 8.98** |
| 1.00 s between landings | 8.21 / 8.68 (SP 150 A: **5.11 → 5.10**) |

No conclusion in this document depends on the changed digits: build B remains
favoured against both SP 150 targets, and the Icebind row is still effectively
a tie. Treat the JSONL as reproducible only against the tree that carries this
note; if a later change moves any of these numbers, the cause belongs in a new
entry here, not in a silent overwrite. `tests/test_slam_results_artifact.py`
now enforces that for the cheapest row: it re-simulates the 1,000-trial
`normal_status_no_afflictions` scenario (~0.3 s) and requires the computed
summary to equal the committed record exactly, so a formula change that is not
mirrored into this file fails the suite instead of passing silently.

Sources: [Jat Kittag](https://wiki.warframe.com/w/Jat_Kittag),
[Melee](https://wiki.warframe.com/w/Melee),
[Melee Afflictions](https://wiki.warframe.com/w/Melee_Afflictions),
[Gas](https://wiki.warframe.com/w/Damage/Gas_Damage),
[Electricity](https://wiki.warframe.com/w/Damage/Electricity_Damage),
[Toxin](https://wiki.warframe.com/w/Damage/Toxin_Damage),
[Blast](https://wiki.warframe.com/w/Damage/Blast_Damage),
[Magnetic](https://wiki.warframe.com/w/Damage/Magnetic_Damage),
[Overguard](https://wiki.warframe.com/w/Overguard),
[Vulcan Blitz](https://wiki.warframe.com/w/Vulcan_Blitz),
[Riven Splicer](https://wiki.warframe.com/w/Riven_Splicer), and the above
forum reports. These are community-maintained Wiki/forum sources, not an
official engine specification.
