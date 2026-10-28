# Akarius Prime: Viral vs Corrosive Riven

**Experimental comparison, 2026-10-28.** These are simulated times, not
in-game measurements. The ranking of the durable target changes under a
plausible Heat-timing alternative, and this is **not a crowd-clear model**.
The older [Akarius report](akarius_prime_riven_sim.md) is an invalidated
historical archive; none of its TTKs are reused here.

## Bottom line

For the two **unprimed level-150 Steel Path Grineer** targets below, Corrosive
is faster against the ordinary Heavy Gunner in the default model. Viral is
faster against the Eximus in the default model, but an alternative Heat pulse
assumption reverses its mean ordering. Thus the Eximus result is not robust
enough to declare a winner.

If a companion, teammate, or other source reliably applies Viral, the
**Corrosive Riven is the better candidate for this armored Grineer setup**:
a separate five-stack external Viral sensitivity strongly favors it. That
sensitivity is not the unprimed baseline and does not include the time needed
to prime. Without external Viral, the tradeoff depends on target durability,
faction, and the unresolved mechanics described below; neither candidate is
proven to be the best all-purpose or room-clearing choice.

## Identical builds

Both configurations use max-rank **Galvanized Diffusion, Galvanized Shot,
Hornet Strike, Lethal Torrent, Primed Heated Charge, Primed Target Cracker,
Pistol Elementalist**, the Riven, and **Secondary Enervate**. All Galvanized
kill stacks are already active and maintained throughout. The Riven is the
only change:

| Riven | Positive 1 | Positive 2 | Negative |
| --- | ---: | ---: | ---: |
| Viral | +133.7% Critical Damage | +133.7% Viral | −47.6% Zoom |
| Corrosive | +133.7% Critical Damage | +133.7% Corrosive | −47.6% Zoom |

These are hypothetical midpoint-grade, max-rank **two-positive/one-negative**
Pistol Rivens, with normalized 1.2 disposition. Viral and Corrosive are
already-combined **spliced** traits; each has a 90% pistol base value, so
`0.90 × 1.2 × 1.2375 = 1.3365`, rounded here to 1.337. They are not ordinary
single-element rolls. Splicing preserves the positive/negative layout and
inherits a consumed trait's higher grade; the midpoint used here is not
necessarily the population average of spliced Rivens. Your actual rolls may
have different values. [5](https://wiki.warframe.com/w/Riven_Mods)
[1](https://wiki.warframe.com/w/Riven_Splicer)

Both builds retain innate Blast and separate Heat. The −Zoom has no effect
on damage in this simulation; its effects on aiming and accuracy are not
modeled. The Wiki lists Akarius Prime's 68 Impact direct hit, 509 Blast
rocket detonation, 34% status, 18% crit, eight-round magazine, and separate
impact/detonation status application. The real explosion has a 7.8 m radius
and falls from 100% to 30% damage at the edge. [1](https://wiki.warframe.com/w/Akarius_Prime)

### Shared simulated stats

- **3.9 multishot:** three rockets, with a 90% chance of a fourth, per ammo
  shot. Each rocket can contribute an Impact hit and a detonation hit in
  the direct-hit scenario.
- **61.2% status per damage instance:** `34% × (1 + 0.80)`. At the chosen
  damage proportions, the three eligible status types have weights of roughly
  25.08%, 41.38%, and 33.53% for Impact/Blast, Heat, and Viral/Corrosive,
  respectively, conditional on a status roll.
- **111.45% average final critical chance:** `102.45 + 0.5 × 18`, using the
  Wiki's steady-state Secondary Enervate approximation. The model samples
  crit tiers from that average, rather than simulating the arcane's actual
  ramp, resets, simultaneous-hit behavior, or complete crit-tier distribution.
  [1](https://wiki.warframe.com/w/Secondary_Enervate)
- **6.874× first-tier critical multiplier:** `2 × (1 + 1.10 + 1.337)`.
  Max-rank Primed Target Cracker is +110%, not +120%.
  [1](https://wiki.warframe.com/w/Primed_Target_Cracker)
- **1.5 s non-sprinting reload:** `2.4 / (1 + 0.60)`. Pistol Elementalist
  gives +90% status damage and +60% reload speed, not status duration.
  [1](https://wiki.warframe.com/w/Pistol_Elementalist)
- Lethal Torrent gives the modeled `5.8672` arsenal fire-rate value and
  `0.075 s` intra-burst delay. The two-shot burst cycle is about `0.24544 s`,
  not simply one divided by 5.8672. Reloading also includes the post-shot
  delay. The model does not use Akarius's faster sprinting/Gauss reload.
  [2](https://wiki.warframe.com/w/Fire_Rate)

### Galvanized Shot and Viral timing

At full kill stacks, Galvanized Shot gives +120% damage per **distinct live
status**, not three free target statuses. For Akarius Prime, the Wiki lists
Rocket Impact as multiplicative with Hornet Strike and Rocket Detonation as
receiving no GunCO bonus. For example, at one live status the modeled Impact
bracket is `(1 + 2.2) × (1 + 1.2) = 7.04`, versus `1 + 2.2 = 3.2` for the
detonation. The mod's +80% status chance still applies to both instances.
[11](https://wiki.warframe.com/w/Condition_Overload_(Mechanic))
[2](https://wiki.warframe.com/w/Galvanized_Shot)

The Wiki says same-shot multishot hits cannot benefit from each other's Viral
procs, whereas Galvanized Shot counts multishot hits sequentially. The
simulation now snapshots Viral at the start of each individual ammo shot,
while GunCO sees statuses applied by earlier hits. The next shot of the burst
can benefit from those Viral stacks. Grouping both Impact and Detonation from
each rocket under the same Viral snapshot, processing impacts/explosions in
a fixed order, and independently rolling their crits are **model assumptions**;
actual weapon-specific travel and ordering have not been established here.
Heat ticks and Blast proc explosions, including early detonation, use the
then-live Viral stacks; this is another timing assumption.
[1](https://wiki.warframe.com/w/Damage/Viral_Damage)
[2](https://wiki.warframe.com/w/Galvanized_Shot)

## Targets and simulation setup

Both targets are shieldless, level-150 Steel Path Heavy Gunners from the
repository's enemy-scaling model:

| Target | Health | Armor | Overguard |
| --- | ---: | ---: | ---: |
| Ordinary | 286,139.57 | 2,700 | 0 |
| Eximus | 1,716,837.41 | 2,700 | 269,918.97 |

The infobox gadget and Wiki scaling article differ on Overguard's level
formula; this model follows the gadget. Grineer's +50% modifier to Impact and
Corrosive damage is modeled separately from Corrosive status armor strip, and
now applies to the health bar only: the Overguard page states the layer is
neutral to every type but Void. The measured rows below that predate that
change are marked, because the "neutral faction/type modifiers" sensitivity is
now the default and the baseline row no longer reproduces. [8](https://wiki.warframe.com/w/Damage/Corrosive_Damage)

Unless a sensitivity explicitly says otherwise, each trial starts with **no
target statuses**, no external primer, companion or ability buffs, no faction
mod, and no headshots. Shots always connect; there is no travel time, missed
rocket, partial radial damage, sprint reload, enemy movement, or finite ammo
reserve. Crit and status outcomes are seeded pseudorandom draws. First impact
is at `t = 0`; DOT and reload events continue until the kill or 600-second
cutoff. Thus the values are not full real-world encounter durations.

The model uses one shared Heat strip ramp: 15/30/40/50% at half-second
intervals after the first Heat proc, multiplicatively combined with Corrosive
strip. By default, a Heat stack contributes at a shared pulse only after it
has existed for one second. Corrosive starts at 26% strip, adds 6% per stack
up to 80% at 10, and lasts eight seconds; no Emerald shard raises the cap.
[3](https://wiki.warframe.com/w/Damage/Heat_Damage)
[8](https://wiki.warframe.com/w/Damage/Corrosive_Damage)

## Results: direct impact plus full-strength detonation

Results are seconds from the first modeled hit to death. Percentiles are
interpolated from successful trials; **all 53,000 runs across the eleven
scenarios completed**, with zero timeouts. Seed for trial `i` is
`20261028 + i`, shared between builds. Extra
decimal places expose modeled burst/Heat timing, not in-game precision.

| Target | Trials per Riven | Riven | Mean | Median | p90 | Median Overguard break |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Eximus | 5,000 | Viral | 2.1826 | 2.0000 | 2.4818 | 0.0750 |
| Eximus | 5,000 | Corrosive | 2.3174 | 2.4818 | 2.5568 | 0.0000 |
| Ordinary | 2,500 | Viral | 0.4113 | 0.4909 | 0.4909 | n/a |
| Ordinary | 2,500 | Corrosive | 0.2907 | 0.3204 | 0.3204 | n/a |

The Eximus result is particularly sensitive to delayed Heat pulses and the
reload boundary: almost all kills happen after the first reload has begun.
A break time of zero means Overguard broke during the first simulated ammo
shot, not instant damage at a real distance.

For context, the paired-seed mean difference `Corrosive − Viral` is
`+0.1349 s` for Eximus and `−0.1206 s` for ordinary targets. Approximate 95%
**Monte Carlo sampling intervals** are `[+0.1279, +0.1418]` and
`[−0.1231, −0.1181]` seconds, respectively. These are conditional on this
simulator and **do not account for model error**; the Heat sensitivity below
is more consequential than sampling uncertainty.

## Idealized splash-only individual target

The target receives full-strength rocket detonations but **no projectile
impacts or Impact procs**. Another target or surface is assumed to trigger
every explosion but is not simulated. There is no distance falloff, Blast
chain reaction, enemy density, travel time, or cross-target damage. This is a
separate one-target stress test, **not** damage-per-room or kills-per-minute.

| Target | Trials per Riven | Riven | Mean | Median | p90 |
| --- | ---: | --- | ---: | ---: | ---: |
| Eximus | 2,500 | Viral | 2.8643 | 2.8022 | 3.0000 |
| Eximus | 2,500 | Corrosive | 3.2054 | 3.2181 | 3.2931 |
| Ordinary | 2,500 | Viral | 0.7080 | 0.7363 | 0.8113 |
| Ordinary | 2,500 | Corrosive | 0.5786 | 0.5659 | 0.7363 |

All splash-only trials completed. This model preserves the same target-specific
ordering as the direct-hit baseline but cannot establish the relative clearing
speed of real groups. In particular, Blast proc explosions affect surrounding
enemies, which this simulation does not include.
[1](https://wiki.warframe.com/w/Damage/Blast_Damage)

## Sensitivities and uncertainty

Each Eximus direct-hit sensitivity uses **2,000 trials per Riven**, the same
seeds and zero timeouts. The first row is a same-seed, 2,000-trial subset of
the baseline; each later row changes only the stated assumption.

| Eximus direct-hit scenario | Viral mean | Corrosive mean | What changed |
| --- | ---: | ---: | --- |
| Baseline subset | 2.1851 | 2.3168 | Default Heat, ten-stack Blast, faction-type routing on both layers (now obsolete: the default applies them to health only, which is the row below) |
| All live Heat stacks contribute at each group pulse | 1.9334 | 1.8904 | Alternative unverified Heat eligibility; **mean ordering reverses** |
| Four-stack early Blast detonation | 2.2198 | 2.3457 | Hybrid: retain default single-target settlement |
| Neutral faction/type modifiers on Overguard | 2.1874 | 2.3392 | Apply Grineer modifiers to health only (the current default) |
| Discard the breaking hit's Overguard overflow | 2.1887 | 2.3274 | One-hit overflow discard only; no timed invulnerability |
| Constant expected crit damage | 2.1798 | 2.3222 | Same expected crit multiplier, no tier variability |
| Start with five external Viral stacks | 2.0305 | 0.5008 | Both targets pre-primed for six seconds |

The Heat alternatives bracket a real modeling uncertainty; neither is
claimed as verified. The Wiki's dedicated Blast page describes ten stacks,
while its general calculation page describes a four-stack Eximus/boss cap and
a different settlement. Merely changing the cap while retaining the other
page's single-target rule is a sensitivity, not a resolution.
[1](https://wiki.warframe.com/w/Damage/Blast_Damage)
[4](https://wiki.warframe.com/w/Damage/Calculation)

The five-stack pre-prime is applied to **both** Rivens at time zero, counts
as one live GunCO status, lasts six seconds, and assumes zero setup time. On
the ordinary target it yields mean times of **0.2537 s Viral** and
**0.0827 s Corrosive** (2,000 trials each, no timeouts). It illustrates the
value of combining externally supplied Viral with the Riven's Corrosive; it
does not predict companion uptime or prove an actual encounter duration.

The default shieldless enemy model allows proportional mixed-hit overflow
through Overguard. The overflow-discard sensitivity reflects the proposed
gating behavior, without asserting that it occurs in-game. The Wiki explicitly
distinguishes a player Overguard invulnerability gate from **no enemy
Overguard invulnerability gate**; enemy shields have separate gating behavior
and are not represented here. Neither build applies Magnetic, so this
comparison does not exercise Magnetic break procs. For context, the Wiki's
forced Electricity proc from Magnetic on Shield/Overguard break totals 3% of
maximum defense per Magnetic stack over six seconds before modifiers, rather
than that amount on every tick. [1](https://wiki.warframe.com/w/Overguard)
[3](https://wiki.warframe.com/w/Shield)
[4](https://wiki.warframe.com/w/Damage/Magnetic_Damage)

Other material unknowns include mixed-hit boundary allocation, Heat
inheritance, exact crit/DoT rounding, real projectile and impact/explosion
ordering, status immunities and different factions. In particular, Viral
status immunity or a faction's different damage-type modifiers can change
this comparison. The Riven's exact grade and availability of armor strip or
external Viral also matter. See the [formula audit](formula_audit.md).

As context rather than validation, a Reddit Akarius build discussion also
notes that Galvanized Shot's damage bonus affects the impact rather than the
explosion [1](https://www.reddit.com/r/Warframe/comments/1uxg99d/akarius_build/).
A separate community status-only comparison and a forum discussion note
that existing Heat armor strip can favor Viral over Corrosive; neither is a
measurement of this specific loadout, whose direct Corrosive damage, shot
and proc timing, and Overguard also enter the model.
[1](https://www.reddit.com/r/Warframe/comments/1jeqhfy/corrosive_vs_viral_comparison_post_jade_shadows/)
[14](https://forums.warframe.com/topic/1518428-i-need-clarity-for-status-element-effect/)

## Reproduce

From the repository root, with Python 3 and no GUI dependencies:

```bash
python -m modules.akarius_comparison
```

The command prints one JSON record per scenario, including seed, trial count,
timeouts, mean/median/p90, and paired differences. Defaults are 5,000 trials
per Riven for Eximus direct hits, 2,500 for ordinary direct hits and each
splash-only target, and 2,000 for each sensitivity. To reproduce the
2,000-trial baseline subset in the sensitivity table, add
`--eximus-trials 2000`. To do a quick smoke run:

```bash
python -m modules.akarius_comparison --eximus-trials 5 --ordinary-trials 5 \
  --splash-trials 5 --sensitivity-trials 5
```

For a direct programmatic baseline without sensitivity experiments:

```python
from modules.akarius_sim import RIVEN_VIRAL, RIVEN_CORROSIVE, run_trials
from modules.akarius_comparison import ordinary_gunner_factory

for riven in (RIVEN_VIRAL, RIVEN_CORROSIVE):
    result = run_trials(riven, trials=2500, base_seed=20261028,
                        target_factory=ordinary_gunner_factory)
    print(riven, result["ttk_mean"], result["ttk_median"],
          result["ttk_p90"], result["trials_attempted"], result["timed_out"])
```

The source for these scenarios is [`modules/akarius_comparison.py`](../modules/akarius_comparison.py);
weapon mechanics are in [`modules/akarius_sim.py`](../modules/akarius_sim.py).
The comparison's routing and Blast sensitivity patches are scoped to their own
serial runs and do not change simulator defaults.
