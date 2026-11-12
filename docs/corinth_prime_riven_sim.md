# Corinth Prime Riven Choice: what to fish for on the Cannonade build

> **Experimental report — model output, not an in-game measurement.** The TTKs
> below come from [`modules/corinth_prime_sim.py`](../modules/corinth_prime_sim.py)
> running on the repository's audited core. Read the
> [formula audit](formula_audit.md) before quoting a number: the armor curve,
> the Overguard routing and the Cannonade fire-rate reading all move the
> answers, and two of them move it more than the gap between the top rolls.

**Target: level 150 Steel Path Eximus Heavy Gunner** (1,716,837 HP at 2,700
armor behind 269,919 Overguard). The plain, non-Eximus Gunner is kept as a
second column throughout, because the two targets do not give the same answer.

**Short answer (original Viral + Electricity base): splice Corrosive and take
`+Corrosive / +Damage / +Damage to Grineer`.** It is the fastest roll on both readings of the armor formula —
**2.67 s mean** against the Eximus target versus **4.29 s** for the best
non-spliced roll and **11.69 s** with Galvanized Acceleration instead of a
Riven. Every one of the six Corrosive-spliced three-positive rolls beats every
non-spliced roll by more than 1.3 s, and even a two-positive
`+Corrosive / +Damage to Grineer` (2.97 s) beats the best ordinary three-positive
roll (4.29 s). On a 2,700-armor target with 1.7M HP, the armor strip is worth
more than any third stat line.

That flips the earlier plain-Gunner answer. With only 286k HP the fight is over
in one or two trigger pulls, so the strip never compounds and
`+Damage / +Critical Damage / +Damage to Grineer` was the better buy (0.92 s vs
0.77 s for Corrosive). Against the Eximus the health pool is six times larger
and the Corrosive roll wins on both armor readings.

**Short answer (base re-paired to Corrosive + Cold): fish Viral, not
Magnetic.** With Corrosive already in the fixed mods, `+Viral / +Damage /
+Damage to Grineer` runs **2.43 s** — better than the 2.67 s that the original
base can reach at best — while the best Magnetic splice is **3.88 s**, worse
than simply taking `+Damage / +Critical Damage / +Damage to Grineer` (3.16 s)
with no splice at all. The full comparison is in
[the Corrosive + Cold variant section](#variant-base-re-paired-to-corrosive--cold).

## The build the request fixes

Galvanized Acceleration is the mod the Riven replaces: it grants projectile
speed only, and the Corinth Prime's primary fire is hitscan, so it is the free
slot. Everything else is the user's list.

| Slot | Mod / item | Effect modelled |
| --- | --- | --- |
| 1 | Semi-Shotgun Cannonade | +240% damage, +1.5 m punch-through; **fire rate cannot be modified** |
| 2 | Galvanized Hell (4 kill stacks) | +110% + 4 x 30% = **+230% multishot** |
| 3 | Primed Ravage | +110% critical damage |
| 4 | Blunderbuss | +90% critical chance |
| 5 | Primed Chilling Grasp | +165% Cold |
| 6 | Toxic Barrage | +60% Toxin, +60% status chance |
| 7 | Primed Charged Shell | +165% Electricity |
| 8 | **Riven** (average grade, 1.20 disposition) | the question, below |
| Arcane | Primary Overcharge | "+35% of Max Energy as Multishot, capped at 250%" — assumed at the 250% cap |

Weapon data ([Corinth Prime](https://wiki.warframe.com/w/Corinth_Prime),
`source/ExportWeapons_en_Cleaned.zip`): 25.2 Impact / 37.8 Puncture / 27 Slash
per pellet (90 total), **six pellets**, 30% crit at 2.8x, 9% status per pellet,
1.4167 attacks/s, magazine 20, 3.0 s reload. Mod values come from the rank
tables in `source/ExportKeys_en_Cleaned.zip`; Primary Overcharge is
`/Lotus/Upgrades/CosmeticEnhancers/Offensive/MultishotForMaxEnergy` in
`ExportRelicArcane_en_Cleaned.json`.

Resolved stats of the Riven-less build:

```
multishot   6 x (1 + 2.30 + 2.50) = 34.8 pellets per trigger pull
fire rate   1.4167/s   (Cannonade locks it; Fire Rate rolls do nothing)
crit        30% x 1.90 = 57.0% at 2.7976 x 2.10 = 5.875x
status      9% x 1.60 = 14.4% per pellet  ->  ~5 procs per trigger pull
modded base 90 x 3.40 = 306.0              per-pellet damage 1,499.4
elements    Viral 2.25 (Cold 1.65 + Toxin 0.60) + Electricity 1.65
```

The alt-fire airburst, range falloff (the export carries no falloff data),
headshots and punch-through geometry are out of scope.

## The two targets

[`docs/target_dummy_models.md`](target_dummy_models.md), `modules/enemy_scaling.py`:

| Target | Health | Armor | Overguard | Effective HP |
| --- | ---: | ---: | ---: | ---: |
| `plain` — SP150 Heavy Gunner | 286,139.57 | 2,700 (90% DR) | 0 | 2.86M |
| `eximus` — SP150 Eximus Heavy Gunner | 1,716,837.41 | 2,700 (90% DR) | 269,918.97 | 17.4M |

Overguard follows [`modules/damage_routing.py`](../modules/damage_routing.py)
and the [Overguard](https://wiki.warframe.com/w/Overguard) page: the layer is
neutral to every damage type except Void, so the Grineer type table (Corrosive
x1.5, Impact x1.5, Heat x0.5) applies to **health only**, while a Bane-style
faction *damage* bonus is applied to the hit before routing and therefore
reaches both layers. Status effects still apply while Overguard stands (that
page grants "immunity to most crowd control effects", not to Viral/Corrosive),
so procs that land during the Overguard phase do their damage to Overguard.

`--target eximus` is the CLI default; `--target plain` reproduces the earlier
run. The factory's own default stays `plain` so the fixed-seed digest in
`tools/bench_models.py` keeps its reference value.

## How the Riven is valued

Values are the average (midpoint) grade of
`source/riven_stats_average_1_2.csv`, Shotgun Riven rows, after Hotfix 44.1.3
normalized every disposition to 1.20. Three positives + one curse reads
Damage +185.3%, Critical Chance / Critical Damage / Status Chance / element
+101.3%, Multishot +134.7%, Damage to Grineer +51%; two positives + one curse
is larger (Damage +244.6%, crit/element +133.7%, Multishot +177.8%, Bane
+67%).

Combined elements are **spliced** traits. Per the
[Riven Splicer](https://wiki.warframe.com/w/Riven_Splicer) notes in
[`jat_kittag_slam_spam_comparison.md`](jat_kittag_slam_spam_comparison.md), the
two consumed traits are replaced by the combined trait **and a re-rollable
trait**, so splicing keeps the layout: a three-positive Riven can hold one
combined trait plus two ordinary positives. The combined trait inherits the
higher consumed value, which at average grade is the ordinary element value,
and being pre-combined it never joins the Cold/Toxin/Electricity groups of the
fixed mods.

The sweep covers 754 three-positive rolls (286 ordinary, 468 spliced) and 156
two-positive rolls, all with a curse. Two ranking aids are reported:

* **Steady-state DPS** — health only, Viral saturated at 10 stacks, no
  Corrosive, armor at its unscratched 2,700, no Overguard. It is a one-line
  damage comparison, not a time-to-kill, and it cannot see an armor strip that
  only exists once the shooting starts.
* **Seeded Monte Carlo TTK** — pellet-by-pellet hits, per-pellet crit and
  status rolls, live Viral/Corrosive/Puncture stacks, Overguard overflow,
  Electricity and Slash ticks, and the trigger clock. Kills land on shot times
  (0.00, 0.71, 1.41, 2.12 s ...), so the **mean** is the sort key and the
  median can jump a whole pull. **This is the ranking the recommendation
  follows.**

The element pairing is a build option, not a Riven property: with
`--elements viral_electric` (default) Cold and Toxin form Viral and Electricity
stays single; with `--elements corrosive_cold` Toxin and Electricity form
Corrosive and Cold stays single. Same mods, same magnitudes.

Status rules are the ones already audited elsewhere in the repository: Viral
2 + 0.25 x (stacks - 1) to 10 stacks / 4.25x; Corrosive 26% of current armor on
the first stack and +6% per further stack, 10 stacks / 80%, 8 s; Puncture +5
absolute crit points per stack to 5 stacks; Electricity six 0.5x ticks with the
first on application and the Electricity elemental bonus applied; Slash six
0.35x ticks that bypass armor. Bane-style faction damage multiplies direct hits
once and the DoT seeds twice. Proc types are drawn from the modded damage
distribution. Cold, Magnetic and Corrosive are all modelled, including Cold's
four-stack cap under Overguard and its Critical Damage bonus, and Magnetic's
Overguard amplification plus the Electricity released when the layer breaks.
Heat, Toxin, Blast and Gas are not: a Heat Riven pairs with the fixed
Electricity into Radiation, so the simulator refuses a layout that would proc
one of them instead of dropping the proc silently.

## Results — Eximus target

### Monte Carlo TTK (500 seeded trials per roll, audited armor curve)

| Riven | Mean | Median | p90 | Overguard broken at | Viral | Corrosive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **+Corrosive / +Damage / +Damage to Grineer** | **2.67 s** | 2.82 s | 3.53 s | 0.00 s | 8 | 4 |
| +Corrosive / +Damage to Grineer (2 positives) | 2.97 s | 2.82 s | 3.53 s | 0.00 s | 8 | 5 |
| +Damage / +Critical Damage / +Damage to Grineer | 4.29 s | 4.24 s | 4.94 s | 0.00 s | 10 | 0 |
| +Damage / +Critical Chance / +Damage to Grineer | 4.45 s | 4.24 s | 4.94 s | 0.00 s | 10 | 0 |
| +Damage / +Multishot / +Damage to Grineer | 4.58 s | 4.41 s | 4.94 s | 0.00 s | 10 | 0 |
| +Critical Chance / +Critical Damage / +Damage to Grineer | 4.62 s | 4.76 s | 4.94 s | 0.00 s | 10 | 0 |
| +Damage / +Critical Chance / +Critical Damage | 4.64 s | 4.94 s | 4.94 s | 0.00 s | 10 | 0 |
| +Damage / +Damage to Grineer (2 positives) | 4.80 s | 4.94 s | 5.24 s | 0.00 s | 10 | 0 |
| +Critical Damage / +Damage to Grineer (2 positives) | 5.11 s | 4.94 s | 5.65 s | 0.00 s | 10 | 0 |
| +Multishot / +Damage to Grineer (2 positives) | 5.62 s | 5.65 s | 6.35 s | 0.00 s | 10 | 0 |
| no Riven (Galvanized Acceleration) | 11.69 s | 11.47 s | 12.71 s | 0.71 s | 10 | 0 |

The Overguard column is the median time at which the layer broke. It reads
0.00 s for every roll listed because the first trigger pull resolves at t = 0
and already out-damages the 269,919 Overguard; only the un-rivend build needs a
second pull (0.71 s). Overguard is therefore a flat ~0.7 s tax, not a phase
that changes the ranking — it is the six-fold health increase that does.

### Every Corrosive splice beats every ordinary roll (300 trials each)

The finalists above come from the steady-state table, which deliberately does
not rank the Corrosive rolls high. To check that no other roll sneaks past, the
top 24 steady-state rolls plus every spliced roll in the top 50 (32 rolls) were
run against the Eximus target:

| Rank | Roll | Mean TTK |
| ---: | --- | ---: |
| 1 | +Corrosive / +Damage / +Damage to Grineer | 2.65 s |
| 2 | +Corrosive / +Damage / +Critical Damage | 2.74 s |
| 3 | +Corrosive / +Critical Damage / +Damage to Grineer | 2.76 s |
| 4 | +Corrosive / +Damage / +Critical Chance | 2.81 s |
| 5 | +Corrosive / +Critical Chance / +Damage to Grineer | 2.84 s |
| 6 | +Corrosive / +Critical Chance / +Critical Damage | 2.90 s |
| 7 | +Damage / +Critical Damage / +Damage to Grineer (best non-spliced) | 4.26 s |

All six Corrosive three-positive combinations are within 0.25 s of each other
and 1.36 s clear of the best ordinary roll. The two-positive layout behaves the
same way: `+Corrosive / +Damage` 2.91 s and `+Corrosive / +Damage to Grineer`
2.94 s, then `+Damage / +Damage to Grineer` 4.77 s and `+Critical Damage /
+Damage to Grineer` 5.09 s.

### The armor-curve sensitivity

`docs/formula_audit.md` records that the [Armor](https://wiki.warframe.com/w/Armor)
page gives `0.9 x sqrt(armor / 2700)` at or below 2,700 and `armor / (armor +
300)` above it, and notes that the two branches agree only at the 2,700 cap.
A 2,700-armor Heavy Gunner sits exactly on that seam, and only a Corrosive
roll ever moves off it, so the sensitivity table changes exactly two rows:

| Riven | Audited curve | Linear armor reading |
| --- | ---: | ---: |
| +Corrosive / +Damage / +Damage to Grineer | **2.67 s** | **3.70 s** |
| +Corrosive / +Damage to Grineer (2 positives) | 2.97 s | 4.20 s |
| +Damage / +Critical Damage / +Damage to Grineer | 4.29 s | 4.29 s |
| +Damage / +Critical Chance / +Damage to Grineer | 4.45 s | 4.45 s |
| no Riven | 11.69 s | 11.69 s |

The Corrosive splice wins on both readings — by 38% on the audited curve and by
14% on the linear one — which is what makes it a recommendation rather than a
gamble. The strip is worth less on the linear reading because that branch's
damage fraction falls away from 10% much faster as armor comes off: one stack
takes the target from 2,700 to 1,998 armor, which multiplies incoming damage by
2.26 on the audited curve and by only 1.31 on the linear one.

### Steady-state DPS (health only, Viral saturated, no Overguard)

Included because it is the table that would mislead you, and because it shows
why. The "at 10 Corrosive" column is a what-if: the same build against a fully
stripped target — an armor level only a Corrosive roll can actually reach.

| Riven (3 positives + curse) | DPS | DPS at 10 Corrosive | Sustained |
| --- | ---: | ---: | ---: |
| +Damage / +Critical Damage / +Damage to Grineer | **476,156** | 2,732,851 | 392,706 |
| +Damage / +Critical Chance / +Damage to Grineer | 464,339 | 2,665,030 | 382,960 |
| +Critical Chance / +Critical Damage / +Damage to Grineer | 442,044 | 2,537,068 | 364,572 |
| +Damage / +Critical Chance / +Critical Damage | 429,986 | 2,498,611 | 354,628 |
| +Damage / +Damage to Grineer / +Electricity | 416,032 | 2,420,681 | 343,119 |
| **+Corrosive / +Damage / +Damage to Grineer** (spliced) | 411,101 | 2,391,216 | 339,052 |
| +Damage / +Multishot / +Damage to Grineer | 411,029 | 2,359,062 | 338,993 |
| no Riven (Galvanized Acceleration) | 135,928 | — | 112,106 |

| Riven (2 positives + curse) | DPS | DPS at 10 Corrosive | Sustained |
| --- | ---: | ---: | ---: |
| +Damage / +Damage to Grineer | **416,903** | 2,384,020 | 343,838 |
| +Critical Damage / +Damage to Grineer | 379,273 | 2,168,836 | 312,802 |
| +Critical Chance / +Damage to Grineer | 367,936 | 2,104,006 | 303,452 |
| +Damage / +Critical Damage | 365,583 | 2,124,368 | 301,512 |
| +Critical Chance / +Critical Damage | 336,926 | 1,957,844 | 277,877 |
| **+Corrosive / +Damage to Grineer** (spliced) | 315,344 | 1,835,308 | 260,077 |

Read the two tables together and the trap is visible: the crit rolls sit on top
because they multiply the *unscratched* 2,700 armor better, and the Corrosive
roll sits sixth because its own DPS is lower at every fixed armor value. What
the steady-state number cannot express is that the Corrosive roll is the only
one that *creates* the 540-armor row: at 10 stacks armor damage climbs from 10%
to 40% of the hit, a 4x multiplier that compounds over the six or seven pulls
the Eximus target survives.

### Which line is worth what

Steady-state health DPS with the other slots held fixed, three-positive layout,
average grade:

| Third line alongside +Damage / +Critical Damage | DPS | vs a dead line |
| --- | ---: | ---: |
| +Damage to Grineer | 476,156 | x1.59 |
| +Critical Chance | 429,986 | x1.43 |
| +Electricity | 369,698 | x1.23 |
| +Multishot | 369,408 | x1.23 |
| +Toxin or +Cold | 348,688 | x1.16 |
| +Heat (pairs Electricity into Radiation) | 331,619 | x1.11 |
| +Status Chance | 319,089 | x1.06 |
| +Status Duration / +Reload Speed / +Magazine Capacity | 299,785 | x1.00 |

Two-positive layout, alongside +Damage: Bane x1.78, Critical Damage x1.56,
Critical Chance x1.52, Electricity x1.31, Multishot x1.31, Cold/Toxin x1.22,
Heat x1.16, Status Chance x1.09. A spliced Corrosive line is worth only x1.03
at face value by the same method — it adds a sixth damage type, which also
dilutes the Slash and Electricity proc shares — and then it strips armor, which
is the whole point: the strip is worth about x4, the line itself almost nothing.

Read it as dilution. Cannonade already supplies +240% base damage, so a
+185.3% Riven line is only x1.55; Galvanized Hell and Primary Overcharge
already supply +480% multishot, so +134.7% multishot is only x1.23. Bane is a
separate multiplier that also double dips the DoTs. A +Heat roll is the worst
of them because the Riven's element pairs with Primed Charged Shell into
Radiation, deleting the Electricity DoT.

### Curses

Mean TTK of the recommended roll with each available Shotgun curse (500 trials
each, Eximus target):

| Curse | Mean TTK | Note |
| --- | ---: | --- |
| -Ammo Maximum, -Damage to Corpus, -Damage to Infested | 2.67 s | free against Grineer |
| -Weapon Recoil, -Projectile Speed, -Magazine Capacity, -Reload Speed | 2.67 s | no effect on this fight |
| -Fire Rate / Attack Speed | 2.67 s | free **only** because Cannonade locks fire rate |
| -Slash | 2.66 s | bleed ticks are a small share of a stripped-armor kill |
| -Impact / -Puncture | 2.69-2.75 s | Puncture also removes crit-chance stacks |
| -Critical Chance | 3.24 s | |
| -Multishot | 3.34 s | fewer pellets, fewer procs |
| -Critical Damage | 3.44 s | |
| -Status Chance | 3.83 s | fewer Corrosive stacks, slower strip |
| -Status Duration | 5.33 s | 8 s strip windows shrink: the worst curse here |

The vendored shotgun table has no Zoom trait (the rifle and pistol tables do),
so the usual free -Zoom curse is not on the menu. -Punch Through is a
positive-only trait in this table, not a curse. Compared with the plain target,
-Status Chance and -Status Duration are much more expensive here: the strip is
the damage, so weakening it costs a third to half the fight.

## Variant: base re-paired to Corrosive + Cold

The three elemental mods can be paired the other way: Toxin and Electricity
combine, Cold stays single. Same mods, same percentages, different pairing —
`--elements corrosive_cold`. That leaves the Riven free to carry a spliced
**Viral** or **Magnetic** trait, which is the question.

### Viral vs Magnetic vs nothing (Eximus, 500 trials per row)

| Riven (Corrosive + Cold base) | Audited curve | Linear armor reading |
| --- | ---: | ---: |
| **+Viral / +Damage / +Damage to Grineer** | **2.43 s** | **3.41 s** |
| +Viral / +Damage / +Critical Damage | 2.52 s | 3.53 s |
| +Viral / +Critical Damage / +Damage to Grineer | 2.55 s | 3.57 s |
| +Damage / +Critical Damage / +Damage to Grineer (no splice) | 3.16 s | 4.64 s |
| +Corrosive / +Damage / +Damage to Grineer (duplicate Corrosive) | 3.32 s | 4.96 s |
| **+Magnetic / +Damage / +Damage to Grineer** | 3.88 s | 5.66 s |
| +Radiation / +Damage / +Damage to Grineer | 3.90 s | 5.68 s |
| +Magnetic / +Damage / +Critical Damage | 4.06 s | 5.93 s |
| no Riven (Galvanized Acceleration) | 7.60 s | 11.58 s |

**Viral wins by 1.45 s and it is not close.** The reasons are worth stating,
because "Magnetic shreds Overguard" is true and still not what this fight
needs:

* Overguard is 269,919 of the target's 2.0M total health and dies inside the
  first trigger pull for every roll on this page, Magnetic or not. Magnetic's
  4.25x Overguard amplification has one pull to act on and the break
  Electricity (3% of maximum Overguard per stack, ~81k at ten stacks) is a
  third of a pull's health damage.
* The health layer is 1.7M HP behind 90% DR. Viral's 4.25x multiplies all of
  that, and it stacks off the Riven's own proc share within two pulls.
* Magnetic adds a *neutral* damage type to a 2,700-armor Grineer (no type
  bonus, no strip) and takes proc share away from Corrosive, so it slows the
  strip while it pays for itself only on a layer that is already free.

### Is the switch itself worth making?

| Build | Audited | Linear |
| --- | ---: | ---: |
| Corrosive + Cold base, +Viral / +Damage / +Damage to Grineer | **2.43 s** | **3.41 s** |
| Viral + Electricity base, +Corrosive / +Damage / +Damage to Grineer | 2.67 s | 3.70 s |
| Corrosive + Cold base, no Riven | 7.60 s | 11.58 s |
| Viral + Electricity base, no Riven | 11.69 s | 11.69 s |

Yes, by about 9-10% at the top and far more before the Riven: with the base
already stripping armor, the un-rivend build drops from 11.69 s to 7.60 s.
The Corrosive + Cold base also makes the Riven decision cheaper — the splicer
now buys Viral instead of Corrosive, and Viral is the trait the original base
was getting for free.

Two things the switch costs: the fixed Electricity DoT disappears (it is now
inside Corrosive), and the Riven must carry Viral or the build loses the health
amplifier entirely — a non-spliced Riven on this base is 3.16 s, i.e. the worst
of the three "reasonable" configurations.

Cold is not a passenger, though: with 165% Cold in the build it holds 5-9
stacks at the kill on the Eximus target, adding +0.25x Critical Damage while
Overguard stands (four-stack cap) and +0.30x to +0.50x once the layer is gone,
on a 5.875x base.

## Results — plain target, for comparison

500 seeded trials, Corrosive rolls only on the left of the pairs:

| Riven | Audited curve | Linear armor reading |
| --- | ---: | ---: |
| +Corrosive / +Damage / +Damage to Grineer | **0.77 s** | 0.95 s |
| +Corrosive / +Damage to Grineer (2 positives) | 0.89 s | 1.25 s |
| +Damage / +Critical Damage / +Damage to Grineer | 0.92 s | **0.92 s** |
| +Damage / +Critical Chance / +Damage to Grineer | 0.95 s | 0.95 s |
| +Critical Chance / +Critical Damage / +Damage to Grineer | 1.02 s | 1.02 s |
| +Damage / +Damage to Grineer (2 positives) | 1.15 s | 1.15 s |
| no Riven | 2.79 s | 2.79 s |

Against the plain Gunner the two answers are within 0.15 s of each other and
trade places with the armor reading, because a 286k-HP fight is over before the
strip compounds. If you also farm ordinary Grineer, the Corrosive roll covers
both cases; if you specifically want the plain-target best case, the crit roll
is 0.03 s quicker on the linear reading.

## Recommendation

0. **If you switch the base to Corrosive + Cold, fish Viral**: `+Viral /
   +Damage / +Damage to Grineer` (2.43 s / 3.41 s). Do not fish Magnetic
   (3.88 s / 5.66 s) — it is slower than a plain `+Damage / +Critical Damage /
   +Damage to Grineer` Riven, and the switch only pays off if the Riven carries
   Viral. The rest of this list assumes the original Viral + Electricity base.
1. **Splice Corrosive and take `+Corrosive / +Damage / +Damage to Grineer`.**
   2.67 s Eximus / 0.77 s plain on the audited curve, 3.70 s / 0.95 s on the
   linear one — first on every reading tested, and 38% faster than the best
   ordinary roll on the Eximus target.
2. **Any of the other Corrosive pairings is fine.** `+Corrosive / +Critical
   Damage / +Damage to Grineer` (2.76 s), `+Corrosive / +Damage / +Critical
   Damage` (2.74 s) and the crit-chance variants (2.81-2.90 s) are all inside
   half a second of the leader. Do not re-roll a Corrosive splice chasing the
   exact second line.
3. **Budget: `+Corrosive / +Damage` or `+Corrosive / +Damage to Grineer`**
   (2.91 s / 2.94 s, two positives plus curse). Either beats the best
   non-spliced three-positive roll (4.29 s) with one fewer positive — the
   Splicer is doing the work of the missing line.
4. **If you will not splice:** `+Damage / +Damage to Grineer` is the cheapest
   ordinary roll worth owning (4.80 s Eximus) and `+Damage / +Critical Damage /
   +Damage to Grineer` the strongest (4.29 s).
5. **Curse: -Damage to Corpus or -Damage to Infested first**, then -Ammo
   Maximum, -Weapon Recoil, -Projectile Speed, -Magazine Capacity, -Reload
   Speed. -Fire Rate is free if Cannonade's "Fire Rate cannot be modified" also
   suppresses penalties — that is the reading used here and is not verified in
   game. **Do not accept -Status Duration or -Status Chance** on a Corrosive
   Riven: they cost 2x and 1.4x the fight respectively.
6. **Do not fish for:** +Fire Rate (dead under Cannonade), +Punch Through or
   +Projectile Speed (no damage on a single target), +Multishot (only x1.23 at
   average grade), Status Chance (x1.06 before it becomes a strip enabler),
   +Heat (turns Electricity into Radiation), or any other splice — Viral
   duplicates the Viral already in the build, Blast/Gas add a few percent of
   proc damage, and Magnetic's Overguard amplification is worth well under the
   Corrosive strip even before this model's documented undercount of it.

## Reproducing

```bash
# Eximus target (default), with the sensitivity and curse tables
python -m modules.corinth_prime_sim --trials 500 --top 8 --sensitivity --curses
# the plain Gunner tables in this report
python -m modules.corinth_prime_sim --trials 500 --top 8 --sensitivity --curses --target plain
# the Corrosive + Cold variant (Viral vs Magnetic)
python -m modules.corinth_prime_sim --trials 500 --top 8 --elements corrosive_cold
python -m unittest tests.test_corinth_prime_sim -v
```

The module is deterministic for a given base seed (`--seed`, default
20261112). The tests pin the Riven table values, the element hierarchy, the
Cannonade fire-rate lock, the Corrosive/Viral/Puncture stack rules, both target
stat blocks, the Overguard-first routing (health untouched while the layer
stands, Overguard neutral to the Grineer type table), the "crit factor appears
once in a DoT seed" invariant, the two ranked rolls' steady-state DPS and the
armor-curve mapping.

## Limits worth knowing

* One target, point blank, no falloff, no headshots, no shield phase. Against a
  Corrupted Heavy Gunner or a Corpus target the Bane line does nothing and the
  ordering changes.
* The arcane is assumed at its 250% cap for the whole fight; at 0% the build
  fires 19.8 pellets per pull and everything is ~1.7x slower.
* Galvanized Hell's four kill stacks are assumed up front.
* Cannonade's fire-rate lock is read as covering penalties too. If it does not,
  a -Fire Rate curse is the worst possible roll rather than a free one.
* Overguard does not gate status application in this model; if the game blocks
  procs while the layer stands, the Corrosive rolls lose a stack or two in the
  first pull and nothing else changes, because that phase is under one pull.
* Magnetic is modelled as inert, so a Magnetic-spliced Riven is undercounted.
  It ranks well below every Corrosive roll anyway.
* Blast, Gas, Heat and Toxin procs are outside the Monte Carlo; layouts that
  would roll them are ranked analytically only, with their proc damage
  unmodelled. Cold is modelled, but its Freeze only matters for the plain
  target (Overguard caps Cold at four stacks).
* Every TTK here is model output under the repository's audited formulas, not
  a measurement of the live game.
