# Jat Kittag Heavy Slam: Last-Slot Mod and Riven Simulation

Slam-by-slam Monte Carlo simulation for a Jat Kittag heavy-slam build against
the Steel Path level 150 Eximus Heavy Gunner dummy (1,716,837.41 health,
2,700 armor / 90% DR, 269,918.97 Overguard). Code:
[`modules/jat_kittag_sim.py`](../modules/jat_kittag_sim.py), tests:
[`tests/test_jat_kittag_sim.py`](../tests/test_jat_kittag_sim.py).

The fixed seven mods are Primed Pressure Point, Seismic Wave, Galvanized
Elementalist, Galvanized Reflex, Vulcan Blitz, Galvanized Steel and Primed
Fever Strike. The open 8th slot is the decision: seven normal mods
(including Focus Energy) and seven average-grade Riven rolls are compared.
**All Galvanized on-kill effects are assumed at 4 stacks from t=0**, per the
build assumption.

## Heavy-slam mechanics modeled (wiki, retrieved 2026-10-27)

- The heavy slam is its own attack: **600 Blast** (the weapon's 200 base ×
  the universal 3× heavy-slam multiplier), 100% status chance, forced
  **Lifted**, 10 m radius, 100%→70% radial falloff (the center dummy takes
  100%), cadence 1.0 slam/s per the weapon infobox. Heavy slams have **no
  wind-up** and **add no combo points**.
- Damage chain: `600 × (1 + damage mods) × (1 + elemental mods) × Seismic
  Wave ×3.0 × combo multiplier × crit × faction`. Seismic Wave is a
  separate multiplicative bracket; Killing Blow's +120% is **additive with
  Pressure Point**; Galvanized Steel's +110% crit chance and Riven crit
  chance are **doubled on Heavy Attacks**.
- **Full Galvanized stacks (the headline assumption).** Four on-kill
  stacks of each Galvanized mod are active from the first slam:
  - Galv Reflex: +20.35 Initial Combo/stack → **81.4 points = a 5× combo
    floor** (`combo_tier(81.4) = 5`), on top of the static +50% Heavy
    Attack Efficiency.
- **Combo recovery after a heavy is not instant (corrected model).** A
  heavy slam spends the counter; Heavy Attack Efficiency retains a
  fraction (50% baseline, capped at 90% with Focus Energy), and the spent
  Initial Combo then **regenerates at 40 points/s** (wiki Melee page,
  retrieved 2026-10-27) back up to the 81.4-point floor — heavy slams add
  no points themselves. At the native 1.0 s cadence, 50% efficiency
  retains 40.7 points and 40 points regen before the next slam, so 5×
  holds. At the 3-positive Riven's 0.618 s cadence only 24.7 points
  regen: the floor collapses 5× → 4× → a steady **3×** with 50%
  efficiency, while 90% efficiency (Focus Energy) retains 73.3 points and
  holds 5×. `simulate(..., combo_recovery=True)` runs this stateful
  model; the older fixed-tier path remains for reference runs.
  - Galv Steel: +30% crit damage/stack → crit multiplier 2.0 × 2.2 =
    **4.4× baseline** (the static +110% crit chance, doubled to +220% on
    heavies, gives 48% modded crit chance).
  - Galv Elementalist: +30% status chance/stack → **2.2 status rolls per
    slam** (two guaranteed procs + 20% chance of a third), on top of the
    static +80% Status Damage.
- Combo tiers run 2× at 20 points up to 12× at 220. The multiplier is
  common to every option, so option rankings do not depend on the tier;
  results are reported at the 5× floor and at 1×/7×/12× references.
- **Melee Afflictions** cannot trigger while Overguard is active
  (Overguard is CC immune, so Lifted never sticks); once broken — or on a
  target with no Overguard at all, where the first slam Lifts immediately
  — every subsequent slam on an already Lifted enemy adds stacks of each
  status already on it, **including statuses applied by the triggering
  slam itself** (wiki, retrieved 2026-10-27). Rank 5 adds 6 stacks, but
  the wiki documents a bug, carried on both wiki mirrors, where a Lifted
  trigger adds **12 stacks** — heavy slams force Lifted, so 12 is used
  throughout this sim. A damaging DoT (here Gas or Toxin) must be live
  for the arcane to fire at all: pure Corrosive/Viral/Blast profiles
  never trigger it. The immediate Affliction Damage Hit and the wiki's
  "exponential" faction/Status Damage scaling (itself flagged "probably a
  bug") are not modeled — a conservative omission.
- **Toxin DoT bypasses shields, not armor** (wiki Toxin Damage; corrected
  from an earlier draft of this sim). Gas ticks are likewise armor
  mitigated; only Slash bleeds ignore armor. Armor DR uses the
  repository's sqrt convention, `0.9 × sqrt(armor/2700)` (40.25% DR at the
  Corrosive cap of 540 armor).
- **Gas** (Heat + Toxin): clouds tick 6 times over 6 s, 10 instances cap;
  cloud ticks are armor-mitigated and their modded base **ignores elemental
  mods** — only base-damage, faction and Status Damage bonuses count.
- Vulcan Blitz death explosions and Galvanized stack *gains* cannot happen
  before the single dummy dies; the room sim models both (Vulcan: 300 Blast
  + 60% max health, 6 m, assumed 50% average radial falloff, LoS assumed).

## Gas tick vs Toxin tick, worked math

Both statuses come from the same slam modded base. With only Primed
Pressure Point in the damage bracket, `MBD = 600 × (1 + 1.65) = 1,590`, and
Galvanized Elementalist gives +80% Status Damage (`×1.8`). One non-critical
proc, no faction mod:

```
Gas tick   = (MBD + 1 accumulator) × 0.5 coefficient × 1.8 Status Damage
           = 1,591 × 0.5 × 1.8                                   = 1,431.9 raw
Toxin tick = 1,591 × 0.5 × (1 + 1.65 Fever Strike) × 1.8
           = 1,591 × 0.5 × 2.65 × 1.8                            = 3,794.5 raw
```

The Toxin mod's +165% is an **elemental term that exists on the Toxin tick
formula but not the Gas tick formula** — Gas's Heat/Toxin mods enlarge the
direct hit but never the cloud. Both ticks then eat the same armor DR:

| Armor state | DR (repo sqrt) | Gas → health | Toxin → health |
| --- | ---: | ---: | ---: |
| 2,700 (full) | 90.00% | 143.2 | 379.5 |
| 540 (Corrosive cap) | 40.25% | 855.6 | 2,267.2 |
| 0 (fully stripped) | 0% | 1,431.9 | 3,794.5 |

The raw ratio is exactly **2.65× = the Fever Strike factor**, and armor
shrinks both by the same divisor, so the ratio never improves for Gas.
Additional mechanics, all modeled:

- A critical slam snapshots its crit multiplier into every proc's seed
  (baseline 4.4× under full Galv Steel stacks), doubling-plus the ticks.
- Each proc deals 6 ticks; up to 10 instances coexist. One Melee
  Afflictions trigger injects six extra stacks — at full armor that is
  **+859 health/s from Gas vs +2,277 health/s from Toxin** per trigger.
- Direct hits cut the other way: the Gas build's slam carries 5,644
  elemental+physical type damage vs 4,214 for Toxin at 7× non-crit
  (11,853 vs 8,848 after 90% DR), because Molten Impact adds to the direct
  Gas portion. Gas therefore front-loads slightly harder per hit but loses
  the sustained-DoT war decisively, has no armor strip of its own, and
  combines away the Heat strip.

## Single-target results vs the SP150 dummy

> The matrices in this section hold the combo tier fixed per trial (the
> 5× Initial Combo floor), as labeled. Stateful combo recovery — spend,
> efficiency retention, 40 points/s regen — is introduced in the
> three-way plain-Gunner table further down; read that section for any
> build whose slam cadence is faster than 1.0 s (e.g. Attack Speed Rivens).

### Full Galvanized stacks, 5× Reflex combo floor (500 trials, median TTK s)

Melee Afflictions follows the wiki as of 2026-10-27: a Lifted trigger
(heavy slams force Lifted) injects **12 stacks, not 6** (documented bug
on both wiki mirrors), and the arcane only fires while a damaging DoT —
Gas or Toxin here — is live, so the Corrosive- and Viral-only builds
show zero triggers.

| 8th slot | Median | Mean | p90 | Affl. triggers (med) |
| --- | ---: | ---: | ---: | ---: |
| **Riven CC + CD + Attack Speed (3-positive)** | **7.42** | 7.29 | 7.42 | 11 |
| Riven MD + Attack Speed | 8.26 | 8.69 | 11.02 | 11 |
| Riven Crit Chance + Crit Dmg | 10.00 | 9.39 | 10.00 | 10 |
| Riven MD + Crit Damage | 11.00 | 11.38 | 17.00 | 7 |
| Corrosive (Shocking Touch) | 14.00 | 13.79 | 17.00 | 0 |
| Riven MD + Status Chance | 14.00 | 13.91 | 18.00 | 10 |
| Riven MD + Initial Combo | 14.00 | 14.69 | 20.00 | 10 |
| Corrosive (Focus Energy) | 15.00 | 15.04 | 18.00 | 0 |
| Primed Smite Grineer | 17.00 | 17.30 | 23.00 | 12 |
| Killing Blow | 18.00 | 18.19 | 25.00 | 12 |
| Organ Shatter | 19.00 | 19.53 | 27.00 | 13 |
| 60/60 Toxin (Virulent Scourge) | 20.00 | 20.12 | 26.00 | 15 |
| Viral (North Wind) | 24.00 | 24.28 | 29.00 | 0 |
| Riven MD + Heat (Gas) | 33.00 | 33.11 | 38.00 | 28 |
| Riven CD + Heat (Gas) | 42.00 | 42.72 | 49.00 | 34 |
| Gas (Molten Impact) | 68.00 | 68.42 | 76.00 | 60 |
| 60/60 Heat (Volcanic Edge, Gas) | 74.00 | 73.76 | 81.00 | 69 |

The corrected 12-stack injection roughly halves TTK on every Toxin-DoT
build compared with the old 6-stack model, and the DoT gate removes the
arcane entirely from Corrosive/Viral builds (they previously received
free stack acceleration). Gas-family builds barely move because their
clouds are pinned at the 10-instance cap and ticks eat armor DR.

Reference runs at other combo tiers (300 trials, medians): with **zero**
Galv stacks at 7×, the 3-positive Riven leads at 9.89 s, then Riven
AtkSpd/CC+CD around 12–13 s; Corrosive/Shocking sits at 23 s now that
Afflictions no longer accelerates its strip, and Gas remains 90 s. At
the **12× ceiling**, Shocking Touch lands 7.0 s vs Focus Energy 8.0 s of
pure slam time.

### Melee Afflictions contribution (full stacks, 5×, same seed)

| Build | With arcane | Without arcane |
| --- | ---: | ---: |
| Primed Smite Grineer (Toxin DoT) | 15.00 s (14 triggers) | 47.00 s |
| 60/60 Toxin (Virulent Scourge) | 20.00 s (19 triggers) | 56.00 s |
| Riven MD + Attack Speed | 8.26 s (14 triggers) | 19.28 s |
| Riven CC + CD | 9.00 s (8 triggers) | 22.00 s |
| Corrosive (Shocking Touch) | 11.00 s (**0 triggers**) | 11.00 s |

On Toxin-DoT builds the 12-stack Lifted injection is a ~2–3× TTK effect;
Corrosive-only builds are completely unaffected because they carry no
damaging DoT that can satisfy the trigger gate.

## Focus Energy vs Shocking Touch (Corrosive last slot)

Focus Energy gives +60% Electricity (vs Shocking Touch's +90%) plus +40%
Heavy Attack Efficiency, which with Galv Reflex's static +50% reaches the
**90% efficiency cap**.

| Metric | Shocking Touch | Focus Energy |
| --- | ---: | ---: |
| Corrosive type bonus (with Fever 1.65) | 2.55 | 2.25 |
| Heavy Attack Efficiency | 50% | 90% (capped) |
| Median TTK, 5× floor / full stacks | 14.00 s | 15.00 s |
| Median TTK, fixed 12× tier | 7.00 s | 8.00 s |
| Rebuild to 12× after a slam (wiki) | 2.75 s | 0.55 s |
| Rotation if you force 12× on every slam (7 vs 8 slams) | **23.5 s** | **11.9 s** |

(Both Corrosive builds show 0 Afflictions triggers — no damaging DoT is
present, so the arcane never fires; the 5×/12× rows above are pure
direct-hit plus natural Corrosive strip.)

At the free 5× Initial Combo floor under a *fixed-tier* model (and the
native 1.0 s cadence, where 50% efficiency plus 40 points/s regen does
hold 5×), efficiency does nothing, so Shocking Touch's bigger Corrosive
portion simply wins. Focus Energy earns its slot in two playstyles: the
light-attack rotation below, and **fast-cadence Riven floor spam**, where
the 0.618 s slam interval outruns regen at 50% efficiency but not at 90%
— see the three-way table in the next-but-one section. In the
light-attack rotation, slam at high combo, retain 90% of the points and
rebuild in 0.55 s instead of 2.75 s: the end-to-end kill is more than
twice as fast despite weaker individual slams.

## Plain SP150 Heavy Gunner (no Overguard): 60/60 Toxin vs 60/60 Heat vs Focus Energy

The requested three-way comparison uses a **plain, non-Eximus Heavy Gunner
at SP level 150** (`steel_path_heavy_gunner(150)`): **286,139.57 HP, 2,700
armor (90% DR), zero Overguard** — so Melee Afflictions can trigger from
the second slam. The Riven is a **3-positive god roll with a curse**
(`PlayerMeleeWeaponRandomModRare`, 3-pos/1-neg CSV averages):
**+202.5% Crit Chance / +101.3% Crit Damage / +61.8% Attack Speed**. With
four Galvanized stacks that gives 108.75% modded heavy crit chance
(guaranteed crits), a 6.426× crit multiplier and a **0.618 s slam
cadence**. The contested 8th slot is one of:

| 8th slot | Combined element (with Fever 1.65) | Status rolls/slam | Heavy efficiency |
| --- | --- | ---: | ---: |
| 60/60 Toxin — Virulent Scourge | standalone Toxin, bonus **2.25** | 2.8 | 50% |
| 60/60 Heat — Volcanic Edge | **Gas** (Heat 0.60 + Toxin 1.65), bonus 2.25 | 2.8 | 50% |
| Focus Energy | **Corrosive** (Elec 0.60 + Toxin 1.65), bonus 2.25 | 2.2 | **90% cap** |

All three produce the same 2.25× elemental type damage; only the proc
family, status roll count and efficiency differ. Combo is run through the
stateful `combo_recovery=True` model (spend → retain → 40 points/s regen
to the 81.4 floor), 1,000 trials per row.

| 8th slot | TTK median | mean | p90 | Fixed 5× ref | Fixed 3× ref | Slams (med) | Avg combo tier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Corrosive (Focus Energy)** | **1.85 s** | 1.80 | 1.85 | 1.85 | 2.47 | 3 | **5.00** |
| 60/60 Toxin (Virulent Scourge) | 2.47 s | 2.47 | 2.47 | 2.47 | 2.47 | 4 | 3.75 |
| 60/60 Heat (Volcanic Edge, Gas) | 4.94 s | 4.56 | 4.94 | 3.71 | 4.94 | 8 | 3.41 |

**Why Focus Energy wins this loadout (a reversal of the fixed-floor
Eximus table above):**

1. **The Attack Speed Riven outruns combo regen.** At 0.618 s per slam
   with 50% efficiency, each slam retains 40.7 points but only 24.7
   regenerate before the next: tier sequence **5 → 4 → 3 → 3…**, a steady
   3× floor. Focus Energy's 90% retention keeps 73.3 + 24.7 = 98.0 points
   — always above the 80-point 5× threshold, so it never loses a tier.
   The Toxin build's recovery TTK now equals both its fixed-5× and
   fixed-3× references: the tier collapse is real, but the 12-stack
   Afflictions injections compensate exactly at this fight length.
2. **Corrosive strip starts on slam one.** With no Overguard, procs land
   immediately; the median Focus kill leaves ~1,350 armor (50% stripped
   from natural Corrosive procs — Afflictions cannot accelerate it, as
   the build has no damaging DoT), so later slams bite through ~64% DR
   instead of 90%.
3. **Toxin beats Gas on the same element budget.** The Toxin tick carries
   the 2.25 Toxin elemental term; Gas cloud seeds ignore elemental mods
   and eat the full 90% armor DR. Volcanic Edge also converts *all* Heat
   into Gas, so this build has no Heat armor strip either — armor stays
   at 2,700 for the whole fight.
4. **Afflictions (median triggers: 3 / 7 / 0).** The wiki's Lifted bug
   injects 12 stacks per trigger, cutting the Toxin TTK from 4.33 s to
   2.47 s; Gas is already at its 10-cloud cap so 7 triggers change
   nothing (4.94 s either way); Focus never triggers at all — a
   Corrosive-only status profile has no damaging DoT to satisfy the
   gate, and its three-slam kill is purely direct damage.

*Reference, same three mods without the Riven (native 1.0 s cadence, 500
trials):* the 50%-efficiency builds hold 5× (40.7 retained + 40
regen ≥ 80), and the ordering is unchanged — **Focus 5.00 s < Toxin
6.00 s < Gas 13.00 s**. Focus is one slam slower than under the old
6-stack model because Afflictions no longer accelerates Corrosive
stacks, while Toxin is one slam faster thanks to the 12-stack
injections. Attack speed is what makes the efficiency difference
decisive; the Corrosive-vs-Toxin-vs-Gas ordering holds
regardless.

## Should the Riven roll Initial Combo?

No — not as a sought stat. Galvanized Reflex already supplies 81.4 Initial
Combo at four stacks (5× floor). An average Initial Combo Riven adds
+36.4, taking the floor from 81.4 to 117.8 points — a move from the 5×
tier to 6×, worth **+20% damage on floor slams**, while consuming a Riven
positive that could instead be +244.6% Melee Damage (bracket ×2.65 →
×5.096, a **+92.3% damage** gain) or +81.5% Attack Speed. It is also
completely inert once you maintain any tier above 6× with light attacks.
Take Initial Combo only as a free third stat; never roll for it. The
Heavy Attack Efficiency Riven stat (+109.1% average) is even worse here:
Reflex alone reaches 50% and Focus Energy already caps 90%, so most of it
is wasted against the hard cap.

## Room clears (5× floor, full Galv stacks, Melee Afflictions modeled, 20 seeded runs, median s)

| 8th slot | n=5 | n=10 | n=20 | Affl. triggers (n=10, med) |
| --- | ---: | ---: | ---: | ---: |
| Riven Crit Chance + Crit Dmg | **7.50** | **7.00** | **6.00** | 57 |
| Riven MD + Attack Speed | 9.37 | 10.47 | 8.26 | 120 |
| Riven MD + Crit Damage | 11.00 | 13.00 | 11.00 | 64 |
| Corrosive (Shocking Touch) | 12.00 | 10.50 | 10.00 | 0 |
| Corrosive (Focus Energy) | 13.00 | 11.00 | 11.00 | 0 |
| Primed Smite Grineer | 19.00 | 20.00 | 15.00 | 131 |
| Riven MD + Heat (Gas) | 34.00 | 30.50 | 28.00 | 276 |
| Gas (Molten Impact) | 66.50 | 62.00 | 60.00 | 590 |

The room loop runs the same Melee Afflictions model as the single-target
sim: 12 injected stacks per Lifted trigger, gated behind a live damaging
DoT, with nothing firing during a target's Overguard phase. Proc lists
are pruned first so a cloud/DoT that aged out between integer-second
ticks can never be resurrected. The DoT gate means the two Corrosive
builds now show **zero** triggers and regress to their un-buffed
baselines, while every Toxin-DoT build improves over the old 6-stack
model — Riven CC+CD takes the top outright and Primed Smite roughly
halves again (25/24.5/19 → 19/20/15 s). Pure Gas barely moves because
its clouds sit at the 10-instance cap and eat armor DR anyway; it
remains dead last in every column. Vulcan Blitz explosions (one per
kill, 60% max health before falloff) keep clear times nearly flat as
the room grows. Pass `afflictions=False` to `simulate_room` for the
un-buffed baseline.

## Recommendation

- **Single-target / assassination Riven: the 3-positive +Crit Chance /
  +Crit Damage / +Attack Speed god roll** (7.42 s median at the 5× floor;
  guaranteed crits and a 0.618 s slam cadence that feeds Melee
  Afflictions every other slam). Among two-positive rolls, **+Melee
  Damage / +Attack Speed** leads at 8.26 s, with **+Crit Chance / +Crit
  Damage** (10.0 s, guaranteed crits) the safer cold-open choice. All
  three rely on the standalone Fever Strike Toxin DoT, which is what
  Afflictions multiplies.
- **No Riven: Corrosive via Shocking Touch** remains the best mod slot
  (14 s single target; 10–12 s room clears) on the strength of direct
  hits and the ×1.5 Grineer Corrosive type modifier — but note Melee
  Afflictions never fires for it, because a Corrosive-only profile has no
  damaging DoT. Swap to **Focus Energy** for a light-attack rotation
  rebuilding toward 12× between slams, or with a fast Riven in floor
  spam (below).
- **With a +Attack Speed Riven (e.g. the 3-positive CC/CD/AS god roll):
  Focus Energy becomes the best 8th slot even in floor spam.** The Riven's
  0.618 s cadence outruns the 40 points/s combo regen at 50% efficiency
  (steady 3×); Focus's 90% retention holds 5× permanently, and its
  Corrosive strip works from slam one on non-Eximus targets. On the plain
  SP150 Heavy Gunner it kills in **1.85 s median vs 2.47 s (Virulent
  Scourge Toxin) and 4.94 s (Volcanic Edge Gas)**. Virulent Scourge is the
  runner-up if you want extra Toxin DoT pressure; never take Volcanic Edge
  against armored Grineer.
- **Do not run Gas on SP Grineer** (68 s vs 7.42 s for the winner):
  armor-mitigated clouds, elemental-mod-immune seeds, no strip. Keep
  Primed Fever Strike standalone — its Toxin ticks are 2.65× the Gas
  ticks and are what Melee Afflictions multiplies (12 stacks per Lifted
  trigger).
- **Do not roll Initial Combo or Heavy Attack Efficiency on the Riven.**

## Assumptions and scope

- Four Galvanized on-kill stacks are assumed active at t=0 per request;
  `galv_stacks=0` runs reproduce the un-stacked numbers. On a real single
  dummy those stacks cannot exist before the target dies, so un-stacked
  figures are the honest cold-open estimate and full-stack figures the
  sustained-fight estimate.
- Combo runs two ways: the fixed-tier reference path (`combo_multiplier=`)
  and the stateful path (`combo_recovery=True`), which spends the counter,
  applies Heavy Attack Efficiency retention and regenerates Initial Combo
  at 40 points/s. Light-attack rebuild above the Initial Combo floor is not
  scheduled inside `simulate` — the Focus Energy 12× rotation table applies
  the wiki's published rebuild seconds separately. Heavy slams build no
  combo and have no wind-up.
- Center-target slams only (no radial falloff), no Tennokai, focus school,
  Warframe buffs, headshots or stance-combo slams.
- Melee Afflictions adds stacks per trigger using the average seed of
  the *live* procs of each type (expired entries are pruned first, so no
  status can be resurrected between integer-second DoT ticks). Per the
  wiki (retrieved 2026-10-27), Lifted triggers inject 12 stacks rather
  than the rank-5 value of 6, the arcane requires a live damaging DoT
  (Gas/Toxin here) to fire, and statuses from the triggering slam itself
  are eligible. Its immediate Affliction Damage Hit and the wiki's
  "exponential" faction/Status Damage scaling are omitted
  (conservative); it never fires during Overguard, needs an
  already-Lifted target, and never adds status types not already present
  (regression-tested). The same model runs in `simulate` and
  `simulate_room`; toggle with `afflictions=`.
- Room runs assume a dense pack inside the slam radius, Vulcan explosions
  at 50% average falloff with line of sight. Riven values are normalized
  1.20× disposition averages from
  `source/riven_stats_average_1_2.csv` with a non-combat curse.
- Wiki mechanics retrieved 2026-10-27 (Jat Kittag, Melee, Melee Combo,
  Seismic Wave, Galvanized Steel/Reflex/Elementalist, Killing Blow,
  Organ Shatter, Melee Afflictions, Vulcan Blitz, Focus Energy, Primed
  Smite Grineer, Gas Damage, Toxin Damage). Standard-library `unittest`
  only, no external packages.

## Usage

```python
from modules.jat_kittag_sim import (
    run_trials, simulate_room, combo_tier, build_loadout,
    simulate, plain_heavy_gunner_factory,
)

# Full Galvanized stacks, fixed 5x Initial Combo floor (81.4 points)
print(combo_tier(4 * 20.35))
print(run_trials("Riven MD+AtkSpd", trials=500,
                  combo_multiplier=5.0, galv_stacks=4))

# 3-positive Riven + last-slot mod, stateful 40 points/s combo regen,
# plain non-Eximus SP150 Heavy Gunner (no Overguard)
print(run_trials("Corrosive (Focus Energy)", trials=1000, galv_stacks=4,
                 combo_recovery=True, riven_option="Riven CC+CD+AS",
                 factory=plain_heavy_gunner_factory))
b = build_loadout("60/60 Toxin (Virulent Scourge)", "Riven CC+CD+AS", 4)
trial = simulate(b, plain_heavy_gunner_factory(), seed=1,
                 combo_recovery=True)
print(trial.ttk, trial.combo_tiers)      # e.g. [5, 4, 3, 3, ...]

# Dense room with kill stacks and Vulcan Blitz explosions
result = simulate_room("Corrosive (Shocking Touch)", n_enemies=10,
                       combo_multiplier=5.0, galv_stacks=4, seed=1)
print(result.clear_time, result.vulcan_explosions)
```
