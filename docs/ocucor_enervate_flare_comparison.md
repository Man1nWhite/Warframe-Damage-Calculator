# Ocucor: Secondary Enervate vs. Cascadia Flare

**Experimental simulation, not an in-game measurement or a definitive room-clear ranking.**
Reviewed against the English WARFRAME Wiki and community discussions on 28 October 2026.

A [follow-up comparison](ocucor_viral_dilution_comparison.md) tests a
three-positive Multishot/Viral/Reload Riven and the Viral/Heat tradeoff.

## Short answer

- **After a reload, with no tendrils:** averaged Secondary Enervate was faster in the
  single-target model, even against fully charged Flare. Against the level-150
  Steel Path Eximus dummy, mean time to kill was **5.824 s with Enervate**,
  **6.653 s with full Flare**, or **7.224 s with Flare starting at zero**.
- **With four retained tendrils:** the same Eximus test was nearly tied:
  **4.031 s Enervate**, **3.989 s full Flare**, and **4.091 s cold Flare**.
  All three medians were 4.000 s. The narrow differences are less reliable
  than the simulator's Heat-timing and Enervate assumptions.
- **At a fully stacked, steady-state damage snapshot**, full Flare can have
  the stronger hit: in the example below it is about **18.4% stronger** than
  the single-hit Enervate average. That does not translate directly into the
  same time-to-kill advantage.
- **For actual groups, there is no trustworthy overall winner here.** Ocucor's
  tendrils can change how Enervate charges and resets. The Wiki's published
  single-hit average does not tell us its true multi-target average, and our
  simplified room test cannot establish it. If you want a conditional choice:
  the modeled post-reload single-target case favors **Enervate**, while
  **Flare** is competitive with sustained tendrils, Heat, and stacks. The best
  real-world choice remains uncertain without resolving multi-beam Enervate
  and Heat behavior.

## The exact build

Galvanized Diffusion, Galvanized Shot, Lethal Torrent, Primed Heated Charge,
Primed Target Cracker, Sentient Surge, Pistol Elementalist, and a Riven with
**Multishot, Viral, and −Zoom**. All mods and both compared arcanes are max
rank. **Both Galvanized mods have all kill stacks active throughout**, as
requested; this does *not* pre-apply statuses to a fresh enemy.

No roll values were supplied, so the Riven is a hypothetical max-rank,
midpoint-grade **two-positive/one-negative** roll at the normalized 1.2 Riven
value: **+177.8% Multishot, +133.7% Viral, −47.6% Zoom**. The Multishot and
Zoom figures come from the repository's
[1.2 Riven table](../source/riven_stats_average_1_2.csv). Viral is a
precombined **spliced** trait: the Wiki lists a 90% base, giving
`90% × 1.2 × 1.2375 = 133.65%`, rounded to 133.7%. A real roll can differ;
−Zoom is assumed not to change aim or damage. The earlier Ocucor simulator
incorrectly used the three-positive-layout Multishot figure of +134.7% for
this two-positive layout; it has been corrected.
[1](https://wiki.warframe.com/w/Damage/Viral_Damage)
[2](https://wiki.warframe.com/w/Riven_Splicer)
[3](https://wiki.warframe.com/w/Riven_Mods)

### What those mods produce

- **5.678× Multishot:** `1 + 2.30 + 0.60 + 1.778`; five beams, with a
  67.8% chance of a sixth, merged into one damage instance per target.
- **19.2 beam ticks/s:** `12 × (1 + 0.60)`. **3.78× first-tier crit
  multiplier:** `1.8 × (1 + 1.10)`; max-rank Primed Target Cracker is +110%.
- Before Sentient Surge, status chance is **43.2% per beam** and averages
  **2.4529 status rolls per merged tick**. At four tendrils these become
  **100.8% per beam** and **5.7234 rolls per merged tick**. Same-target beam
  Multishot merges its damage and status chance and uses one crit roll;
  damaging status seeds also inherit the merged damage.
- Pistol Elementalist supplies **+90% status damage** and **+60% reload
  speed**. The modeled reload is `1.6 / 1.6 = 1.0 s`; it does not increase
  status duration.
[4](https://wiki.warframe.com/w/Ocucor)
[5](https://wiki.warframe.com/w/Continuous_Weapon)
[6](https://wiki.warframe.com/w/Primed_Target_Cracker)
[7](https://wiki.warframe.com/w/Pistol_Elementalist)

### Tendrils, Puncture, and the two arcanes

Each Sentient Surge tendril adds +60% *relative* crit chance and status chance,
up to +240%. Stored tendrils therefore raise Ocucor's ordinary crit chance
from **16% to 54.4%** at four. A target's Puncture status adds another **5
flat percentage points per stack**, normally up to +25 points; the stack is
applied after the hit that created it. Reloading or emptying the magazine
removes tendrils. Kills refill 20% of the magazine from reserve.
[8](https://wiki.warframe.com/w/Sentient_Surge)
[9](https://wiki.warframe.com/w/Damage/Puncture_Damage)

Secondary Enervate is a **flat crit-chance** arcane, not a base-damage buff.
Following the request to average its benefit, the simulator uses the Wiki's
long-run single-hit average final crit chance `AFCC(x) = 102.45 + 0.5x` in
this range, with `x` including the target's live Puncture bonus. Thus:

| State | Ordinary crit chance `x` | Enervate average final crit chance |
| --- | ---: | ---: |
| Zero tendrils, no Puncture | 16.0% | 110.45% |
| Four tendrils, no Puncture | 54.4% | 129.65% |
| Four tendrils, five Puncture stacks | 79.4% | 142.15% |

The simulator samples crit tiers from that average; it does **not** simulate
the real charge, resets, or full crit-tier distribution. Enervate is treated
as already at its long-run average even in a cold-start encounter, whereas
cold Flare actually ramps. The Wiki also describes extra complications when
Ocucor tendrils hit multiple targets: separate hits, simultaneous big crits,
and a 30-trigger-per-second limit. It notes that crit chance can exceed 200%,
but that is **not** a measured average for this build.
[10](https://wiki.warframe.com/w/Secondary_Enervate)

Cascadia Flare provides **+12% base damage per Heat application**, maximum
**40 stacks / +480%**, at most one stack per damage instance, with a shared
10-second refresh timer. Fatal Heat applications count. It is additive with
other base damage and is modeled additively with Ocucor's Galvanized Shot.
At full Galvanized stacks the latter gives **+120% per distinct live status**;
a newly applied status does not boost its own merged beam hit. Four distinct
self-applied types are possible: Radiation, Puncture, Heat, and Viral.
[11](https://wiki.warframe.com/w/Cascadia_Flare)
[12](https://wiki.warframe.com/w/Galvanized_Shot)
[13](https://wiki.warframe.com/w/Condition_Overload_(Mechanic))

### A useful steady-state hit comparison

Assume **four tendrils, all four distinct statuses, five Puncture stacks, and
40 Flare stacks**, with the same target and hit conditions for both arcanes.
The direct-damage brackets are `1 + 4 × 1.2 = 5.8` for Enervate and
`5.8 + 4.8 = 10.6` for Flare. Their expected crit factors are respectively
`1 + 1.4215 × (3.78 − 1) = 4.9518` and
`1 + 0.794 × (3.78 − 1) = 3.2073`. Hence:

`Full Flare / single-hit-average Enervate = (10.6 × 3.2073) / (5.8 × 4.9518) ≈ 1.184`.

Under exactly those static assumptions, Flare's **direct hit** is about 18.4%
stronger. An Enervate average final crit chance of roughly **174.9%** would
instead break even—about **32.7 additional percentage points** over the
single-hit formula. This is a mathematical threshold, **not a prediction**
that multi-target Enervate attains it. Live status counts, Heat inheritance,
crit distributions, and proc timing affect actual kills.

## Targets and setup

Unprimed, shieldless level-150 Steel Path Heavy Gunners, using the repository's
scaling model:

| Target | Health | Armor | Overguard |
| --- | ---: | ---: | ---: |
| Ordinary | 286,139.57 | 2,700 | 0 |
| Eximus | 1,716,837.41 | 2,700 | 269,918.97 |

All targets start without statuses; there are no external primers, faction
mods, headshots, abilities, missed hits, movement, or finite reserve-ammo
constraints. The first hit is at `t = 0`. Each fresh target's beam begins at
20% damage and ramps to 100% over 0.6 s. Four initial tendrils or full Flare
are idealized carryover from earlier combat; no time to obtain them is charged.
A lone main-beam target receives the retained tendrils' Sentient Surge stat
bonuses, **not extra tendril damage**. [4](https://wiki.warframe.com/w/Ocucor)

The primary results honor the stated **Overguard overflow-discard** assumption:
the hit that breaks Overguard does not spill excess damage into health. This
adds no timed invulnerability. The Wiki explicitly distinguishes the player's
0.5 s Overguard gate from enemies, which have no invulnerability gate; exact
breaking-hit overflow is a separate routing uncertainty. A proportional-overflow
alternative is tested below. These targets have no shields, and the build has
no Magnetic procs, so neither shield gating nor Magnetic's break-triggered
Electricity proc enters the reported results.
[14](https://wiki.warframe.com/w/Overguard)
[15](https://wiki.warframe.com/w/Damage/Magnetic_Damage)

By default, Heat has a shared 15/30/40/50% armor-strip ramp at half-second
intervals. Heat stacks share a pulse clock, but each stack is assumed eligible
only after it has existed for one second. Each new Heat proc snapshots its own
base-damage and crit seed; the beam's initial damage ramp is applied to direct
hits but not to that seed. These are **model choices**, not established
weapon-specific facts. Other Heat timing, whole-seed inheritance, and ramp
choices are tested below. [16](https://wiki.warframe.com/w/Damage/Heat_Damage)

## Single-target results

Each cell is **mean seconds (median seconds)** over 1,500 paired-seed trials
per setup. Shorter is faster. Flare is either zero stacks or 40 stacks at
`t = 0`; Enervate uses the average above in both comparisons.

| Target | Initial tendrils | Enervate | Flare, zero stacks | Flare, 40 stacks |
| --- | ---: | ---: | ---: | ---: |
| Ordinary | 0 | 2.149 (2.135) | 2.965 (3.000) | 2.634 (2.656) |
| Ordinary | 4 | 2.003 (2.000) | 2.005 (2.000) | 2.001 (2.000) |
| Eximus | 0 | 5.829 (6.000) | 7.228 (7.000) | 6.655 (7.000) |
| Eximus | 4 | 4.032 (4.000) | 4.093 (4.000) | 3.990 (4.000) |

The repeated whole-second medians come from the assumed shared Heat pulse,
not evidence of in-game precision. Against the four-tendril Eximus, the
paired mean difference `Flare − Enervate` was **−0.042 s** for full Flare
(approximate 95% Monte Carlo interval **−0.050 to −0.035 s**) and **+0.061 s**
for cold Flare (**+0.052 to +0.070 s**). These intervals describe sampling
noise *within this model*, not uncertainty about the model itself.

In the cold-Flare Eximus runs, all trials reached 40 stacks: median time was
**2.813 s** with zero initial tendrils and **2.135 s** with four. Against an
ordinary target with four tendrils, only **0.7%** reached 40 before death;
this highlights why preloaded Flare and startup are different comparisons.
For the zero-tendril Eximus, a reload occurred in **0.9%** of Enervate trials,
**95.7%** of cold-Flare trials, and **58.5%** of full-Flare trials.

## Illustrative ten-target rooms—not a gameplay ranking

Each room has ten identical, stationary, unprimed targets simultaneously in
range and line of sight. The primary beam immediately switches to the next
living target; up to four tendrils attack other targets. The model gives each
target its own cold damage ramp and independent crit/status rolls. Primary
beam direct kills and status kills can create tendrils; direct tendril kills
cannot. Magazine refill, empty-magazine tendril loss, reloads, and Flare
ramping are simulated, but positioning, acquisition delay, mixed enemies,
cover, team effects, and actual multi-target Enervate charging are not.
[4](https://wiki.warframe.com/w/Ocucor)

Each cell is mean room-clear seconds from 250 trials per setup. **Enervate
still uses the single-hit AFCC on every beam**, so this table is only an
illustration of this particular approximation.

| Ten targets | Initial tendrils | Enervate | Flare, zero stacks | Flare, 40 stacks |
| --- | ---: | ---: | ---: | ---: |
| Ordinary | 0 | 8.275 | 9.200 | 8.887 |
| Ordinary | 4 | 4.054 | 4.053 | 4.053 |
| Eximus | 0 | 25.223 | 22.480 | 24.585 |
| Eximus | 4 | 8.218 | 8.060 | 8.047 |

With four initial tendrils, cold Flare reached its cap in a median **0.417 s**
in these rooms, because separate targets supply separate damage instances.
The unusual zero-tendril Eximus ordering—cold Flare clearing faster than
preloaded Flare—is an interaction of this artificial model's different kill,
retargeting, refill, and reload trajectories, not a claim that more damage is
inherently harmful. All those room trials involved a reload.

To show how much the **unknown** multi-target Enervate average matters, we
also injected an entirely hypothetical additional average crit chance. The
extra is +50 or +100 percentage points when four tendrils are hitting other
targets, linearly scaled down with fewer such beams. It is **not calculated
from Enervate's actual reset mechanics**:

| Ten Eximus, initially four tendrils | Enervate mean | Full Flare mean |
| --- | ---: | ---: |
| Single-hit average, no extra | 8.218 s | 8.047 s |
| Hypothetical +50 points at four extra beams | 8.011 s | 8.047 s |
| Hypothetical +100 points at four extra beams | 6.669 s | 8.047 s |

The reversal demonstrates sensitivity, not that either extra value is correct.
The community also discusses this Ocucor-specific interaction, but those
reports are not a substitute for a measured average.
[17](https://www.reddit.com/r/Warframe/comments/1hkrd35/ocucor_cascadia_flare_vs_secondary_enervate/)
[18](https://forums.warframe.com/topic/1470605-ocucor-help-me-understand-this-weird-but-awesome-weapon/)

## Single-target sensitivity checks

These use the same first 600 seeds, a four-tendril Eximus, and the same
user-asserted overflow discard unless the row says otherwise. Each number is
mean seconds over 600 trials; only the stated assumption changes.

| Scenario | Enervate | Flare, zero | Flare, full |
| --- | ---: | ---: | ---: |
| Baseline, same-seed subset | 4.026 | 4.081 | 3.980 |
| Proportional breaking-hit Overguard overflow | 4.006 | 4.063 | 3.975 |
| Every live Heat stack contributes at the group's next pulse | 3.087 | 3.364 | 3.020 |
| First Heat proc's **entire** base/crit seed inherited by later stacks | 6.863 | 8.060 | 4.907 |
| Beam ramp also scales new Heat seeds | 4.096 | 4.153 | 4.015 |
| Cap Puncture at three stacks throughout | 4.034 | 4.175 | 4.002 |
| Idealized target starts at full beam ramp | 4.025 | 4.078 | 3.964 |

The Heat alternatives are deliberately unvalidated. The Wiki documents
inheritance of the first source's Heat/faction modifiers and notes exceptions
such as Elementalist; community explanations differ on whether the **entire**
first base/crit seed persists. The whole-seed row is a stress test, not an
assertion that it is correct. Similarly, the Wiki's patch notes mention a
three-stack Puncture cap for VIP enemies with Overguard; whether that exactly
covers this ordinary Eximus is not established here, and the sensitivity
applies the cap for the whole fight. The full-ramp row is idealized because
its target otherwise starts with no statuses.
[9](https://wiki.warframe.com/w/Damage/Puncture_Damage)
[16](https://wiki.warframe.com/w/Damage/Heat_Damage)
[19](https://forums.warframe.com/topic/1507457-how-on-earth-does-heat-inherit-actually-work/)

## Reproduce and inspect

The runner, simulator, and regression tests are
[`modules/ocucor_comparison.py`](../modules/ocucor_comparison.py),
[`modules/ocucor_sim.py`](../modules/ocucor_sim.py), and
[`tests/test_ocucor_comparison.py`](../tests/test_ocucor_comparison.py).
The [aggregate JSONL results](ocucor_enervate_flare_results.jsonl) record every
scenario, seed, timeout count, median, p90, and paired interval. Trial `i`
uses seed `20261028 + i`. All **35,100** runs across 17 scenarios completed;
there were **zero timeouts**. Single-target and room cutoffs are 30 and 60 s.

```bash
python -m modules.ocucor_comparison \
  --single-trials 1500 --room-trials 250 --sensitivity-trials 600 \
  > ocucor_results.jsonl
python -m unittest tests.test_ocucor_comparison tests.test_ocucor_sim -v
```

[`tests/test_ocucor_artifacts.py`](../tests/test_ocucor_artifacts.py) guards the
JSONL against silent staleness: it checks every record's scenario, order,
settings and trial count, re-runs one scenario at its recorded trial count and
requires an exact match. Regenerate the JSONL whenever a simulator change lands;
this artifact was last regenerated for the Cold-aware critical-damage change,
which moved most means by less than 0.05 s.

The [formula audit](formula_audit.md) records broader routing and simulator
limitations. The older [Ocucor report](ocucor_riven_sim.md) is a historical
archive and its numbers and rankings remain invalid.
