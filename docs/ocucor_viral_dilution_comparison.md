# Ocucor: less Viral, more Heat weighting?

**Experimental follow-up to the [Ocucor arcane comparison](ocucor_enervate_flare_comparison.md), not an in-game measurement.** The same seven fixed mods, fully stacked Galvanized mods, target setup, and averaged Secondary Enervate are used.

## Answer

**Lowering Viral does increase the fraction of status rolls that become Heat.**
But adding Reload Speed as a third Riven positive also lowers **Multishot** at
comparable roll quality. In this particular trade, the extra Heat weighting
almost exactly offsets the fewer status rolls, while the average Heat proc
has a smaller merged-beam damage seed. The proposed roll was generally slower in the
isolated Heavy Gunner tests; it was effectively tied in some short fights. It
is not a clear upgrade for the purpose of boosting Heat.

There are exceptions and uncertainties: the idealized multi-target model can
change ordering with reload and tendril trajectories, and its Enervate average
is not validated for multiple targets. The result should not be generalized
into a universal ranking for all enemies, real Riven grades, or gameplay.

## Compared Rivens

Both hypothetical Rivens are max rank at normalized 1.2, with midpoint-grade
traits. "ViralM" in the question is interpreted as **spliced Viral**. No exact
roll values were supplied.

| Riven | Multishot | Spliced Viral | Reload Speed | Zoom |
| --- | ---: | ---: | ---: | ---: |
| Previous: 2 positive, 1 negative | +177.8% | +133.7% | — | −47.6% |
| Proposed: 3 positive, 1 negative | +134.7% | +101.3% | +56.2% | −72.1% |

The third positive changes the Wiki's positive-layout multiplier from
**1.2375 to 0.9375**, so the other positives are lower at the same grade.
The Viral estimates are `90% × 1.2 × layout multiplier`, rounded to one
place; the other midpoint values are in the repository's
[Riven table](../source/riven_stats_average_1_2.csv). Actual grades vary. Zoom
is assumed not to affect damage or aim.
[13](https://wiki.warframe.com/w/Riven_Mods)
[2](https://wiki.warframe.com/w/Riven_Splicer)

With Pistol Elementalist's +60% Reload Speed, the calculated reload times are
`1.6 / (1 + 0.60) = 1.000 s` versus
`1.6 / (1 + 0.60 + 0.562) = 0.740 s`. The latter saves **0.260 s when a
reload occurs**, but it does not prevent Ocucor losing its tendrils when the
magazine empties or reloading begins. Sentient Surge's kill refill is assumed
to have sufficient reserve ammo. [8](https://wiki.warframe.com/w/Reload)
[2](https://wiki.warframe.com/w/Ocucor)
[1](https://wiki.warframe.com/w/Sentient_Surge)

## What changes in the damage mix?

Primed Heated Charge remains unchanged: **the Riven does not increase the
Heat damage bonus itself**. Lower Viral changes the conditional probability
that a status roll selects Heat. With Radiation, Puncture, Heat and Viral as
the four damage types, before faction-type modifiers:

| Quantity | Previous 2-positive | Proposed 3-positive |
| --- | ---: | ---: |
| Total Multishot | 5.678× | 5.247× |
| Heat share of status rolls | 41.38% | 45.05% |
| Viral share of status rolls | 33.53% | 27.65% |
| Expected Heat procs per tick, four tendrils | 2.369 | 2.382 |
| Expected Viral procs per tick, four tendrils | 1.919 | 1.463 |

The Heat share increases about **8.85% relative**, but the reduced Multishot
almost cancels it in the expected number of Heat procs per tick. Viral applies
less frequently. A Viral proc amplifies damage **to health**, including Heat
ticks, and ten stacks cap the multiplier; maintaining it still matters.
[1](https://wiki.warframe.com/w/Status_Effect)
[5](https://wiki.warframe.com/w/Damage/Viral_Damage)

For continuous weapons, same-target multishot merges damage and status chance,
so it affects damaging procs twice. If both builds have the **same live
statuses, base-damage bracket, and crit factor**, and ignoring quantization,
the proposed Riven's expected direct hit is about **84.9%** of the previous
one. Its expected total Heat **seed** per tick is about **92.9%**, despite the
slightly larger number of Heat procs. The Heat-seed comparison uses the actual
five/six-beam probability, `E[beams²] × Heat weight`; it is not a prediction
of final damage or time to kill. [11](https://wiki.warframe.com/w/Multishot)
[2](https://wiki.warframe.com/w/Damage/Heat_Damage)

## Single-target simulation

The same shieldless level-150 Steel Path Heavy Gunners from the previous
comparison: ordinary has 286,139.57 health / 2,700 armor; Eximus has
1,716,837.41 health / 2,700 armor / 269,918.97 Overguard. All target statuses
start empty, and there are no primers, faction mods, headshots, misses, or
ability effects. The main run discards the breaking hit's Overguard overflow
as previously requested. It does **not** add a timed invulnerability gate;
the Wiki distinguishes player and enemy Overguard gating.
[14](https://wiki.warframe.com/w/Overguard)

Each target begins with a cold beam ramp. Four starting tendrils and full
Flare are idealized carryover states, not free extra hits on the main target.
Each row below uses **800 trials per Riven** with shared seeds. Times are mean
seconds; shorter is better.

| Target / starting tendrils | Arcane | Previous 2-positive | Proposed 3-positive |
| --- | --- | ---: | ---: |
| Eximus / 4 | Enervate | 4.030 | 4.206 |
| Eximus / 4 | Flare, starts at 0 | 4.086 | 4.361 |
| Eximus / 4 | Flare, starts at 40 | 3.985 | 4.025 |
| Eximus / 0 | Enervate | 5.821 | 6.103 |
| Eximus / 0 | Flare, starts at 0 | 7.218 | 7.551 |
| Eximus / 0 | Flare, starts at 40 | 6.651 | 7.058 |
| Ordinary / 4 | Enervate | 2.002 | 2.002 |
| Ordinary / 4 | Flare, starts at 0 | 2.005 | 2.013 |
| Ordinary / 4 | Flare, starts at 40 | 2.000 | 2.002 |
| Ordinary / 0 | Enervate | 2.148 | 2.379 |
| Ordinary / 0 | Flare, starts at 0 | 2.968 | 3.065 |
| Ordinary / 0 | Flare, starts at 40 | 2.636 | 2.869 |

With four tendrils, neither Riven reloaded in these single-target trials, so
+Reload Speed provided **no benefit** there. The modeled Eximus reached ten
Viral stacks in a median **0.208 s** with the previous Riven versus **0.313 s**
with the proposed one; both reached ten before death in every trial. Because
many kills occur at the assumed whole-second Heat pulse, small differences in
these numbers are especially sensitive to pulse timing. The model samples
crit tiers from Enervate's long-run single-hit average and does not simulate
its actual multi-beam charge/reset behavior.
[10](https://wiki.warframe.com/w/Secondary_Enervate)

For the zero-tendril Eximus with **cold Flare**, the proposed Riven's reload
benefit can be isolated by a deliberately artificial control that keeps its
Multishot/Viral values but removes its +Reload Speed. That control averaged
**7.614 s**, versus **7.551 s** with Reload Speed; the previous Riven averaged
**7.218 s**. Damage-over-time can kill during a reload, so a 0.260 s shorter
reload does not necessarily save 0.260 s of measured TTK.

## Does lowering Viral alone help?

For causal isolation, we also tried a **counterfactual**, not an attainable
all-midpoint two-positive Riven: keep the previous +177.8% Multishot and
reload time, but reduce Viral from +133.7% to +101.3%. Against the Eximus,
the mean went from **4.030 to 4.008 s** with four tendrils and Enervate, and
from **4.086 to 4.035 s** with four tendrils and cold Flare. With full Flare,
it was essentially tied (3.985 versus 3.989 s). Against the ordinary target
with no tendrils, the same isolated change instead went from **2.148 to 2.180 s**
with Enervate. Thus status dilution *can* help in the model, but the small
change is target-, phase-, and timing-dependent—not proof that less Viral is
always better.

A **realizable** comparison within the two-positive layout keeps Multishot at
its midpoint +177.8% but uses a minimum-grade Viral trait, approximately
+120.3%, instead of +133.7%. Against the four-tendril Eximus, over 400 trials
per roll, Enervate averaged **4.024 versus 4.019 s**; cold Flare averaged
**4.071 versus 4.065 s**; full Flare averaged **3.982 versus 3.982 s**. Each
paired Monte Carlo interval includes zero. These results are essentially tied
within sampling noise, and Heat-model uncertainty is larger still.

## Illustrative rooms and sensitivities

Ten-target rooms assume immediate perfect acquisition, all enemies in range,
no cover or movement, a fresh ramp on each target, and sufficient reserve
ammo. They include tendril damage and refill, but still apply the Wiki's
**single-hit** Enervate average to all targets, rather than modeling actual
multi-beam charging. Each entry uses 120 trials per Riven and is **not a
validated room-clear ranking**.

| Ten identical targets / initial tendrils | Arcane | Previous 2-positive | Proposed 3-positive |
| --- | --- | ---: | ---: |
| Eximus / 4 | Enervate | 8.228 s | 9.077 s |
| Eximus / 4 | Flare, starts at 0 | 8.066 s | 8.349 s |
| Eximus / 4 | Flare, starts at 40 | 8.049 s | 8.282 s |
| Eximus / 0 | Enervate | 25.027 s | 26.706 s |
| Eximus / 0 | Flare, starts at 0 | 22.613 s | 23.389 s |
| Eximus / 0 | Flare, starts at 40 | 24.899 s | 23.803 s |
| Ordinary / 4 | Enervate | 4.056 s | 4.049 s |
| Ordinary / 4 | Flare, starts at 0 | 4.055 s | 4.049 s |
| Ordinary / 4 | Flare, starts at 40 | 4.055 s | 4.049 s |

The zero-tendril, full-Flare Eximus room goes in the opposite direction from
the single-target result. Its particular target deaths, retargeting, refill,
and reload paths change with the roll, so it is a counterexample to treating
one isolated-target TTK as a universal clearing ranking.

A second control removes only the +Reload Speed from the proposed Riven in
the same zero-tendril rooms. With Enervate the three-positive control averaged
**27.065 s without** the extra reload speed versus **26.706 s with** it; the
previous Riven averaged **25.027 s**. With full Flare the two control means
were **23.677 s without** versus **23.803 s with** the extra speed; the paired
sampling interval for that difference includes zero. Faster reload changes
when shots, status ticks, kills, refills and tendril losses interact; these
synthetic results should not be interpreted as a universal effect of reload
speed.

For a four-tendril Eximus, changing Heat assumptions also changed absolute
TTK substantially. With every live Heat stack contributing on the next
shared pulse, Enervate averaged **3.087 s** versus **3.387 s**; if every Heat
stack instead inherited the first proc's whole base/crit seed, it averaged
**6.843 s** versus **7.508 s**. These alternatives are unverified. With ten
external Viral stacks applied before firing, Enervate averaged **4.023 s**
versus **4.176 s**; the external primer's setup time was not modeled. Each
sensitivity uses 400 trials per Riven.
[2](https://wiki.warframe.com/w/Damage/Heat_Damage)
[19](https://forums.warframe.com/topic/1507457-how-on-earth-does-heat-inherit-actually-work/)

## Reproduce

The comparison is implemented in
[`modules/ocucor_viral_comparison.py`](../modules/ocucor_viral_comparison.py),
with explicit Riven values and reload time supported by
[`modules/ocucor_sim.py`](../modules/ocucor_sim.py). Regression tests are in
[`tests/test_ocucor_viral_dilution.py`](../tests/test_ocucor_viral_dilution.py).
The [aggregate JSONL results](ocucor_viral_dilution_results.jsonl) contain all
scenario settings, successful/timeout counts, percentiles, and paired
Monte Carlo intervals. Seeds are `20261028 + i`. All **50,880 trials** across
35 scenarios completed; there were **no timeouts**.

```bash
python -m modules.ocucor_viral_comparison \
  --single-trials 800 --room-trials 120 --sensitivity-trials 400 \
  > ocucor_viral_results.jsonl
python -m unittest tests.test_ocucor_viral_dilution tests.test_ocucor_comparison -v
```

All model limitations in the [prior Ocucor report](ocucor_enervate_flare_comparison.md)
and [formula audit](formula_audit.md) continue to apply. Confidence intervals
in the JSONL quantify random sampling error, **not** errors in the model.
