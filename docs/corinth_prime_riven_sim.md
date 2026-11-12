# Corinth Prime Riven Choice: what to fish for on the Cannonade build

> **Experimental report — model output, not an in-game measurement.** The TTKs
> below come from [`modules/corinth_prime_sim.py`](../modules/corinth_prime_sim.py)
> running on the repository's audited core. Read the
> [formula audit](formula_audit.md) before quoting a number: the armor curve,
> the status routing and the Cannonade fire-rate reading all move the answers,
> and two of them move it more than the gap between the top rolls.

**Short answer.** Fish for **+Damage, +Critical Damage, +Damage to Grineer**
(any harmless curse). It is the fastest roll on every reading tested, at
**0.80 s mean** against the level-150 Steel Path Heavy Gunner versus **2.51 s**
with Galvanized Acceleration instead of a Riven. +Critical Chance is a
near-equal substitute for +Critical Damage, and **+Damage / +Damage to
Grineer** is the best two-positive roll. On the splicing question: the only
splice worth considering is **Corrosive** (Toxin + Electricity), and
`+Corrosive / +Damage / +Damage to Grineer` is the single fastest roll measured
here (**0.73 s**) — but only because this repository's audited armor formula
makes the first Corrosive stack worth ~2.3x. On the alternative linear
armor→DR reading the same roll is **0.88 s**, i.e. slower than the plain
crit roll. Treat the splice as an optional gamble, not a requirement.

## The build the request fixes

Galvanized Acceleration is the mod the Riven replaces: it grants projectile
speed only, and the Corinth Prime's primary fire is hitscan, so it is the
free slot. Everything else is the user's list.

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
headshots, punch-through geometry and the Eximus Overguard variant are out of
scope; the dummy is the plain `steel_path_heavy_gunner(150)` — 286,139.57 HP,
2,700 armor (90% DR), no Overguard.

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

* **Steady-state DPS** — Viral saturated at 10 stacks, no Corrosive, armor at
  its unscratched 2,700. It is the ranking the fixed mods make obvious, and it
  cannot see an armor strip that only exists once the shooting starts.
* **Seeded Monte Carlo TTK** — pellet-by-pellet hits, per-pellet crit and
  status rolls, live Viral/Corrosive/Puncture stacks, Electricity and Slash
  ticks, and the trigger clock. Kills therefore land on shot times (0.00,
  0.71, 1.41, 2.12 s ...), so the **mean** is the sort key and the median can
  jump a whole pull.

Status rules are the ones already audited elsewhere in the repository: Viral
2 + 0.25 x (stacks - 1) to 10 stacks / 4.25x; Corrosive 26% of current armor on
the first stack and +6% per further stack, 10 stacks / 80%, 8 s; Puncture +5
absolute crit points per stack to 5 stacks; Electricity six 0.5x ticks with the
first on application and the Electricity elemental bonus applied; Slash six
0.35x ticks that bypass armor. Bane-style faction damage multiplies direct hits
once and the DoT seeds twice. Proc types are drawn from the modded damage
distribution. Heat, Toxin, Cold, Blast and Gas cannot appear in this build's
modelled layouts (Cold and Toxin are always inside Viral, a Heat Riven makes
Radiation, and no fixed mod supplies Heat), so the simulator refuses a layout
that would proc them instead of dropping the proc silently.

## Results

### Steady-state DPS (Viral saturated, no Corrosive)

| Riven (3 positives + curse) | DPS | DPS at 10 Corrosive | Sustained |
| --- | ---: | ---: | ---: |
| +Damage / +Critical Damage / +Damage to Grineer | **476,156** | 2,732,851 | 392,706 |
| +Damage / +Critical Chance / +Damage to Grineer | 464,339 | 2,665,030 | 382,960 |
| +Critical Chance / +Critical Damage / +Damage to Grineer | 442,044 | 2,537,068 | 364,572 |
| +Damage / +Critical Chance / +Critical Damage | 429,986 | 2,498,611 | 354,628 |
| +Damage / +Damage to Grineer / +Electricity | 416,032 | 2,420,681 | 343,119 |
| **+Corrosive / +Damage / +Damage to Grineer** (spliced) | 411,101 | 2,391,216 | 339,052 |
| no Riven (Galvanized Acceleration) | 135,928 | — | 112,106 |

| Riven (2 positives + curse) | DPS | DPS at 10 Corrosive | Sustained |
| --- | ---: | ---: | ---: |
| +Damage / +Damage to Grineer | **416,903** | 2,384,020 | 343,838 |
| +Critical Damage / +Damage to Grineer | 379,273 | 2,168,836 | 312,802 |
| +Critical Chance / +Damage to Grineer | 367,936 | 2,104,006 | 303,452 |
| +Damage / +Critical Damage | 365,583 | 2,124,368 | 301,512 |
| +Critical Chance / +Critical Damage | 336,926 | 1,957,844 | 277,877 |
| **+Corrosive / +Damage to Grineer** (spliced) | 315,344 | 1,835,308 | 260,077 |

The "DPS at 10 Corrosive" column is a what-if: the same build against a fully
stripped target. It shows how much of the Corrosive roll's value is the armor
strip rather than its own damage.

### Monte Carlo TTK, level-150 Steel Path Heavy Gunner (500 seeded trials each)

| Riven | Mean | Median | p90 | Viral at kill | Corrosive at kill |
| --- | ---: | ---: | ---: | ---: | ---: |
| **+Corrosive / +Damage / +Damage to Grineer** | **0.73 s** | 0.71 s | 1.00 s | 3 | 1 |
| +Damage / +Critical Damage / +Damage to Grineer | 0.80 s | 0.71 s | 1.41 s | 4 | 0 |
| +Damage / +Critical Chance / +Damage to Grineer | 0.83 s | 0.71 s | 1.41 s | 4 | 0 |
| +Critical Chance / +Critical Damage / +Damage to Grineer | 0.83 s | 0.71 s | 1.41 s | 4 | 0 |
| +Corrosive / +Damage to Grineer (2 positives) | 0.85 s | 0.71 s | 1.41 s | 3 | 2 |
| +Damage / +Critical Chance / +Critical Damage | 0.85 s | 0.71 s | 1.41 s | 4 | 0 |
| +Damage / +Damage to Grineer (2 positives) | 0.97 s | 0.71 s | 1.41 s | 4 | 0 |
| +Damage / +Critical Damage (2 positives) | 1.05 s | 1.00 s | 1.41 s | 5 | 0 |
| no Riven (Galvanized Acceleration) | 2.51 s | 2.71 s | 2.82 s | 9 | 0 |

Every non-Corrosive roll at the top kills in two or three trigger pulls, which
is why the medians cluster on 0.71 s and the ordering has to be read from the
means. The same ordering holds at 800 trials and at a second seed, and it also
holds with Primary Overcharge switched off (19.8 pellets per pull): the
Corrosive roll leads at 1.48 s against 1.64 s for the crit roll.

### The armor-curve sensitivity

`docs/formula_audit.md` records that the [Armor](https://wiki.warframe.com/w/Armor)
page gives `0.9 x sqrt(armor / 2700)` at or below 2,700 and `armor / (armor +
300)` above it, and notes that the two branches agree only at the 2,700 cap.
A 2,700-armor Heavy Gunner sits exactly on that seam, so the same rolls were
re-run with the surviving-damage fraction forced to the linear reading
(`ARMOR_CURVE_LINEAR` in the module — a sensitivity switch, not a second
model):

| Riven | Audited curve | Linear armor reading |
| --- | ---: | ---: |
| +Damage / +Critical Damage / +Damage to Grineer | 0.80 s | **0.80 s** |
| +Damage / +Critical Chance / +Damage to Grineer | 0.83 s | 0.83 s |
| +Critical Chance / +Critical Damage / +Damage to Grineer | 0.83 s | 0.83 s |
| +Corrosive / +Damage / +Damage to Grineer | **0.73 s** | 0.88 s |
| +Damage / +Damage to Grineer (2 positives) | 0.97 s | 0.97 s |
| no Riven | 2.51 s | 2.51 s |

One Corrosive stack takes the target from 2,700 to 1,998 armor. On the audited
curve that multiplies incoming damage by 2.26 (10% of the hit survives at 2,700,
22.6% at 1,998); on the linear reading it multiplies it by 1.31. The Corrosive
splice is the only recommendation in this report that changes sides under a
different reading of that page, so it is reported as an optional upgrade
instead of the headline.

### Which line is worth what

Steady-state DPS with the other slots held fixed, three-positive layout,
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
Heat x1.16, Status Chance x1.09.

Read it as dilution. Cannonade already supplies +240% base damage, so a
+185.3% Riven line is only x1.55; Galvanized Hell and Primary Overcharge
already supply +480% multishot, so +134.7% multishot is only x1.23. Bane is a
separate multiplier that also double dips the DoTs, and Critical Damage
multiplies an already-high 5.875x crit. Element positives look weak because
the build already has 3.90 of elemental damage and Viral is capped at 4.25x —
extra Viral is damage, not another multiplier. A +Heat roll is the worst of
them because the Riven's element pairs with Primed Charged Shell into
Radiation, deleting the Electricity DoT.

### Curses

Mean TTK of the recommended roll with each available Shotgun curse (500 trials
each):

| Curse | Mean TTK | Note |
| --- | ---: | --- |
| -Damage to Corpus / -Damage to Infested | 0.73 s | free against Grineer |
| -Ammo Maximum, -Weapon Recoil, -Projectile Speed, -Magazine Capacity, -Reload Speed | 0.73 s | no effect on this fight |
| -Fire Rate / Attack Speed | 0.73 s | free **only** because Cannonade locks fire rate |
| -Slash | 0.73 s | bleeds are a few percent of a two-pull kill |
| -Impact / -Puncture | 0.74-0.75 s | Puncture also drops crit-chance stacks |
| -Status Duration | 0.83 s | shorter Viral/Electricity |
| -Multishot / -Critical Chance | 0.96 s | |
| -Critical Damage | 1.01 s | |
| -Status Chance | 1.14 s | fewer Viral and Corrosive procs |

The vendored shotgun table has no Zoom trait (the rifle and pistol tables do),
so the usual free -Zoom curse is not on the menu here. -Punch Through is a
positive-only trait in this table, not a curse.

## Recommendation

1. **Best all-round: +Damage / +Critical Damage / +Damage to Grineer.** Top of
   the steady-state ranking, top under the linear armor reading, second under
   the audited one, and the cheapest way to be fast against any Grineer
   target. Swap +Critical Damage for +Critical Chance if that is what rolls
   first; they are within 3%.
2. **Cheapest: +Damage / +Damage to Grineer** (two positives + curse). 0.97 s
   mean, about 88% of the three-positive roll's damage, and far easier to buy.
3. **Splicer: Corrosive, and only Corrosive.** `+Corrosive / +Damage / +Damage
   to Grineer` is the fastest roll in the audited model (0.73 s) and the
   best two-positive splice (0.85 s), but it is slower than the plain crit roll
   under the linear armor reading. Viral splicing merely re-rolls the Viral the
   build already has; Blast and Gas add a few percent of proc damage; Magnetic
   has no Overguard to eat on a plain Heavy Gunner; Radiation has no proc at
   all. The Splicer also costs a weekly resource, so spend it only if you want
   the armor-strip build.
4. **Curse: take -Damage to Corpus or -Damage to Infested first**, then
   -Ammo Maximum, -Weapon Recoil, -Projectile Speed, -Magazine Capacity or
   -Reload Speed. -Fire Rate is free if Cannonade's "Fire Rate cannot be
   modified" also suppresses penalties — that is the reading used here and is
   not verified in game; do not pay a premium for it. Avoid -Status Duration
   and worse.
5. **Do not fish for:** +Fire Rate (dead under Cannonade), +Punch Through or
   +Projectile Speed (no damage on a single target), +Multishot (only x1.23 at
   average grade because of the +480% already in the build), Status Chance
   (x1.06), or any element positive unless it comes with two of the three top
   lines.

## Reproducing

```bash
python -m modules.corinth_prime_sim --trials 500 --top 6 --sensitivity --curses
python -m unittest tests.test_corinth_prime_sim -v
```

The module is deterministic for a given base seed (`--seed`, default
20261112). The report's tables are the output of the first command; the tests
pin the Riven table values, the element hierarchy, the Cannonade fire-rate
lock, the corrosive/viral stack rules, the two ranked rolls' steady-state DPS
and the armor-curve mapping.

## Limits worth knowing

* One target, point blank, no falloff, no headshots, no Overguard. Against a
  Corrupted Heavy Gunner or a Corpus target the Bane line does nothing and the
  ordering changes.
* The arcane is assumed at its 250% cap for the whole fight; at 0% the build
  fires 19.8 pellets per pull and the order is unchanged but everything is
  ~1.7x slower.
* Galvanized Hell's four kill stacks are assumed up front. At zero stacks the
  build loses 120% multishot.
* Cannonade's fire-rate lock is read as covering penalties too. If it does not,
  a -Fire Rate curse is the worst possible roll rather than a free one.
* Blast, Gas, Heat, Toxin and Cold procs are outside the Monte Carlo; layouts
  that would roll them are ranked analytically only, where their proc damage is
  a few percent and is not counted.
* Every TTK here is model output under the repository's audited formulas, not
  a measurement of the live game.
