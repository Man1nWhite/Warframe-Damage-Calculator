# Akarius Prime Riven Choice: Viral vs Corrosive

Tick-by-tick Monte Carlo simulation for an Akarius Prime against the Steel
Path level 150 Eximus Heavy Gunner dummy (1,716,837.41 health, 2,700 armor /
90% DR, 269,918.97 Overguard). Code:
[`modules/akarius_sim.py`](../modules/akarius_sim.py), tests:
[`tests/test_akarius_sim.py`](../tests/test_akarius_sim.py).

The Riven is fixed at **+Critical Damage, −Zoom**, and the third positive
stat is the decision: **+Viral or +Corrosive** (average-grade Pistol Riven,
2 positives + 1 curse).

## Your Galvanized Shot question first

Yes — but only on half the weapon. This repository's own GunCO tables
(`source/gunco_mechanic.json`, 118 wiki-verified rules) list the Akarius
Prime `Rocket Impact` as a **`multiply`** attack:

| Damage instance | Hornet Strike | Galvanized Shot CO (3 stacks) | Combined bracket |
| --- | --- | --- | --- |
| Rocket Impact (68 Impact, projectile) | ×3.2 | **multiplies: ×2.2** | **×7.04** |
| Rocket Detonation (509 Blast, 7.8 m AoE) | ×3.2 | **does not apply** | ×3.2 |

The intended "additive" rule would give 1 + 2.2 + 1.2 = ×4.4; the projectile
bug/quirk instead gives 3.2 × 2.2 = **×7.04** on the direct hit. Projectile
explosion radii never receive Condition-Overload-type bonuses (the universal
`none` rule), which matters here because the detonation is 7.5× the base
damage of the impact.

## The build

| Slot | Mod / item | Effect modeled |
| --- | --- | --- |
| Arcane | Secondary Enervate | averaged via the wiki AFCC formula |
| 1 | Galvanized Diffusion (4 stacks) | +230% Multishot |
| 2 | Galvanized Shot (3 stacks) | +80% Status, +120% CO direct damage |
| 3 | Hornet Strike | +220% Damage |
| 4 | Lethal Torrent | +60% Fire Rate, +60% Multishot |
| 5 | Primed Heated Charge | +165% Heat |
| 6 | Primed Target Cracker | +120% Critical Damage |
| 7 | Pistol Elementalist | +90% Status Duration |
| 8 | Riven (avg, 2 pos + 1 curse) | +133.7% Crit Damage, +133.7% Viral **or** Corrosive, −47.6% Zoom |

Shared modded stats: **3.9 multishot** (3 rockets + 90% fourth),
**5.867 rockets/s** in 2-round bursts (0.12 s intra-burst, 0.341 s cycle),
magazine 8 with 2.4 s reloads, status **61.2% per damage instance**,
modded crit 18% → **AFCC 111.45%** (every hit critts; 88.55% orange),
crit multiplier **7.074×**, status-duration multiplier ×1.9 (Heat/Viral
11.4 s, Corrosive 15.2 s, Heat strip ramp 0.95 s/step, Blast fuse 2.85 s).

Each rocket produces two independent damage instances with separate crit and
status rolls (wiki: "Initial hit and explosion apply status separately").
Point-blank hits are assumed, so the detonation takes no falloff (100% →
30% linear falloff only starts beyond 0 m out to 7.8 m). Rocket travel time
(80 m/s) is ignored at close range.

Damage distribution is identical in shape for both Rivens — Heat is the
dominant proc weight (41.4%), then the Riven element (33.5%), then the innate
type (25.1%) — so status application rates match; only the *effect* of the
Riven procs differs.

## Results vs the SP150 Eximus Heavy Gunner (1,000 seeded trials)

| Riven element | Mean TTK | Median | Best case | Worst case | Kills inside first magazine |
| --- | --- | --- | --- | --- | --- |
| **Viral** | **3.69 s** | 4.244 s | **1.503 s** | 4.244 s | **20.1%** |
| Corrosive | 4.33 s | 4.244 s | 4.244 s | 4.824 s | 0.0% |

The Viral distribution is bimodal. When Heat strips armor fast enough inside
the 8-round first magazine (~1 in 5 runs), Viral's 4.25× health multiplier
finishes the Eximus at **1.50 s**; otherwise both builds empty the magazine
and kill on the first burst after the 2.4 s reload (4.24 s). Corrosive never
kills in magazine one: its armor strip ramps quickly (2,700 → ~240 armor by
t ≈ 1.5 s) but, lacking any health multiplier, it is always a few hits short.

### Icebind L1000 Eximus Heavy Gunner stress test (120 trials, 6-player squad)

| Riven element | Median TTK | Mean | Reloads |
| --- | --- | --- | --- |
| **Viral** | **9.53 s** | 9.88 s | 2–3 |
| Corrosive | 25.46 s | 25.76 s | 5–7 |

On a long fight the gap opens to ~2.7×. Heat alone reaches its 50% strip and
the many Heat procs compound multiplicatively (armor approaches zero), so
Corrosive's strip becomes redundant — while Viral's 4.25× health multiplier
keeps compounding on every direct hit and Heat tick for the whole fight.

## Why Viral wins this build

1. **Corrosive duplicates a job Heat already does.** Both reduce current
   armor multiplicatively; Heat alone caps at 50% and, with ~15+ procs,
   overshoots it via stacking factors. Viral does something nothing else in
   the build does: multiply damage to health by up to 4.25×.
2. **The 90% DR phase punishes the no-amplifier build.** Until armor falls,
   every Corrosive-build hit loses 90%; Viral's ×4.25 (up within ~0.5 s,
   10 stacks last 11.4 s) partially offsets that from the first second.
3. **Type modifiers are a wash.** Corrosive's own damage gets the Grineer
   ×1.5 type modifier (modeled), but it applies to one ~33%-weight proc
   family; Viral's multiplier applies to *all* health damage including the
   Heat DoT and the 509-Blast detonations.
4. Corrosive's advantages — instant per-stack strip, 15.2 s duration — only
   matter if Heat is missing or slow. This build always has 165% Heat and
   high status, so they never decide the fight.

### When Corrosive would be the better roll

- A no-Heat version of the weapon (different element layout), where nothing
  else strips armor.
- Targets with armor that Heat alone cannot keep down in the available beam
  time, or content where Viral procs are cleansed/immune.
- Corrosive also strips armor for *teammates'* weapons; Viral is a purely
  personal damage multiplier.

## Assumptions and scope

Galvanized Shot is held at its 3-stack cap (four status types — Impact,
Blast, Heat, Riven element — are available, so the cap is reached within the
first bursts); Galvanized Diffusion at four stacks; Enervate via the closed-
form AFCC average. Single target, body shots (headshots ×3 would also
multiply Blast proc radials), no faction mod, no Warframe buffs, average Riven
values, no votable Icebind restrictions, point-blank detonations. RNG uses
fixed seeds; reproduce with `python3 -m unittest tests.test_akarius_sim`.

## Usage

```python
from modules.akarius_sim import (
    build_akarius, simulate, run_trials, akarius_dummy_factory, RIVEN_VIRAL,
)

build = build_akarius(RIVEN_VIRAL)
trial = simulate(build, akarius_dummy_factory(), seed=20261027, trace=True)
print(trial.ttk, trial.final_armor, trial.trace)

summary = run_trials("Corrosive", trials=500)
```
