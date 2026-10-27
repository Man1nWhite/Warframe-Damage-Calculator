# Kuva Nukor Test Build — Last Mod Choice vs Eximus Heavy Gunner L150 (Steel Path)

Tick-by-tick Monte Carlo simulation for the requested build against dummy A
([target dummy model](target_dummy_models.md): 1,716,837.41 health, 2,700
armor / 90% DR, 269,918.97 Overguard). Code:
[`modules/kuva_nukor_sim.py`](../modules/kuva_nukor_sim.py), tests:
[`tests/test_kuva_nukor_sim.py`](../tests/test_kuva_nukor_sim.py).

Weapon-specific facts used (Kuva Nukor wiki page): the beam ramps **30% →
100%** over 0.6 s (not the generic 20% start), consumes **0.5 ammo per
beam tick**, and chains to up to **2 extra enemies within 9 m at 50% beam
damage**.

## TL;DR

| 8th mod | Median TTK (single dummy) | Mean | p90 | Worst case | Overguard broken |
| --- | --- | --- | --- | --- | --- |
| **Scorch** (+60% Heat/+60% Status) | **2.000 s** | 2.000 s | 2.000 s | **2.000 s** | 0.625 s |
| **Hornet Strike** (+220% Damage) | **2.000 s** | 2.002 s | 2.000 s | 2.250 s | **0.500 s** |
| Anemic Agility | 2.000 s | 2.001 s | 2.000 s | 2.160 s | 0.520 s |
| Hollow Point | 2.250 s | 2.296 s | 2.625 s | 3.000 s | 0.688 s |
| Primed Pistol Gambit | 2.375 s | 2.363 s | 2.688 s | 3.000 s | 0.688 s |
| No 8th mod (reference) | 2.438 s | 2.449 s | 2.750 s | 3.000 s | 0.688 s |
| **Frostbite (Blast AoE build)** | **11.688 s** | 10.892 s | 11.938 s | 12.188 s | 0.562 s |

500 seeded trials per candidate. For a **single target, Frostbite is the
worst pick by far** — Cold combines with Heat into Blast, deleting the Heat
armor strip, and Blast's single-target proc is only 30% of modded base per
stack. Its value is exclusively **room clear**, where it beats every Heat
build once the pack is larger than the beam's 3-target chain (see below).

## The fixed build and the modded stats

| Slot | Mod | Effect used |
| --- | --- | --- |
| Progenitor | Magnetic 60% | +12.6 Magnetic base (21 × 0.6) |
| Arcane | Secondary Enervate | averaged via the wiki AFCC formula |
| 1 | Galvanized Diffusion (4 stacks) | +230% Multishot |
| 2 | Galvanized Shot (3 stacks) | +80% Status, +120% direct Damage |
| 3 | Lethal Torrent | +60% Fire Rate, +60% Multishot |
| 4 | Primed Heated Charge | +165% Heat |
| 5 | Primed Target Cracker | +120% Critical Damage |
| 6 | Pistol Elementalist | +90% Status Duration |
| 7 | Riven (avg, 3 pos + 1 curse) | +101.3% Viral, +101.3% Crit Dmg, +112.5% Status Duration, −72.1% Zoom |
| 8 | candidate | see tables |

Shared modded stats: 3.90 merged beams per tick, 16.0 ticks/s (62.5 ms),
AFCC **105.95%** final crit chance at 7% modded (112.5% with Primed Pistol
Gambit), crit multiplier **16.065×**, status-duration multiplier **3.025**
(all procs 18.15 s), Heat armor-strip ramp interval 1.5125 s.

Riven averages come from `source/riven_stats_average_1_2.csv` (Pistol,
3 positives + 1 curse, average grade, 1.20 disposition). The repository's
Riven tables intentionally omit combined-element tags; the Viral roll uses
the same 101.3% average as single-element pistol stats, matching how the
wiki lists combined-element Riven attributes.

### Element-combining constraints on the last slot

The only free base element is Heat (Radiation is innate, Viral is already
combined). A second base element recombines:

- Frostbite (Cold) → Heat + Cold = **Blast**: no Heat procs, no armor strip.
- Pistol Pestilence (Toxin) → Heat + Toxin = **Gas**: no armor strip.
- Jolt / Convulsion (Electricity) → Heat + Electricity = **Radiation**: no
  Heat procs at all.
- Scorch (Heat) stacks additively and keeps the Heat mechanic; damage mods
  (Hornet Strike, Hollow Point, Anemic Agility) never touch elements.

---

## Frostbite: the Blast AoE option

### What changes in the build

Frostbite adds +60% Cold and +60% Status Chance. Cold combines with the
165% Heat into a **225% Blast element**; the damage distribution per beam
becomes Radiation 46.20, Magnetic 27.72, **Blast 166.32**, Viral 74.88 —
identical magnitudes to the Scorch build with Heat relabeled Blast. Blast
proc weight is 52.78%; merged status is 4.68 procs/tick, i.e.
**~39.5 Blast procs per second** on the primary target.

### Blast proc mechanics (wiki Blast_Damage, current rules)

- Each stack has its own fuse: 1.5 s × status-duration multiplier =
  **4.54 s** here. Normal expiry hits only the proc target for
  **30% of modded base** per stack.
- At **10 stacks, or when the target dies**, all stacks detonate early:
  the proc target takes 10 × 30% (300%), and every other enemy within
  **5 m** (no falloff, fixed radius) takes **300% of modded base per stack**
  — up to 3000% at 10 stacks — combined into one radial damage instance.
- Crit/headshot multipliers snapshot per stack and sum into the radial.
- Elemental mods do **not** buff Blast proc damage, only its proc weight;
  Pistol Elementalist's +90% status-damage does apply. Blast is neutral to
  Grineer flesh and armor.

Per-stack damage with this build (merged seed 288.29, average crit factor
16.96):

| Quantity | Pre-armor | After 90% DR and Viral ×4.25 |
| --- | --- | --- |
| Single-target 30% stack | 2,787 | ~1,185 |
| Radial 300% stack (per neighbor) | 27,872 | ~11,845 |
| Full 10-stack radial event (per neighbor) | 278,717 | **~118,454** |

### Single target: 5.8× slower than Scorch

With no Heat procs, armor stays at 2,700 / 90% DR for the entire fight, and
Blast's 30%/stack fuses are explicitly the weakest single-target status in
the game. The representative Frostbite trial takes **11.75 s** (one reload):
direct beam 1.30M health damage, Blast single-target procs 0.43M, no DoT
contribution at all — compare Scorch's 2.00 s where consolidated Heat DoT
supplies ~80% of health damage after the strip. On the Icebind L1000 dummy
Frostbite is effectively unusable solo (~160 s) for the same reason.

### Room clear: Blast wins once the pack outgrows the chain

The room simulator (`simulate_room`) models a dense pack where every enemy
is within the 9 m chain range and the 5 m Blast radius: the beam hits a
primary target plus 2 chains at 50%, every target rolls its own procs, and
Blast 10-stack/death detonations hit every other target in the room.
Median clear time, 30–40 seeded trials per cell:

| Pack size | Frostbite (Blast) | Scorch (Heat) | Hornet Strike |
| --- | --- | --- | --- |
| 3 (chains cover all) | 2.09 s | **2.00 s** | **2.00 s** |
| 5 | 4.38 s | **4.00 s** | **4.00 s** |
| 10 | **6.19 s** | 8.00 s | 8.00 s |
| 15 | **5.16 s** | 11.63 s | 11.63 s |
| 20 | **5.38 s** | 16.00 s | 16.00 s |

The crossover sits around **6–7 enemies**. Heat builds scale almost linearly
with pack size because the beam only ever touches 3 targets at once;
Frostbite's clear time barely grows from 5 to 20 enemies (5 m radials hit
the whole room, 63–74 radial events per fight, radial damage ~9× the direct
beam damage in the 10-target room). In the room of 20 Frostbite is roughly
**3× faster** than Scorch.

### Verdict on Frostbite

- **Keep Scorch or Hornet Strike as the default 8th mod** for Eximus
  killing, boss damage and anything resembling a single target (2.0 s vs
  11.7 s).
- **Carry Frostbite as a swappable room-clear config** for dense Eximus
  packs / survival camps: it pays off from ~7 enemies up and is ~3× faster
  at 20 targets. It is a playstyle switch, not an upgrade.
- Practical note: the build's huge Status Duration (×3.025) lengthens the
  Blast fuse to 4.54 s — harmless in a sustained beam (10 stacks arrive
  every ~0.25 s and detonate early anyway), but procs applied to enemies
  you then stop beaming will take a long time to pop.

## Why Scorch and Hornet Strike tie on the single dummy

Both feed the same Heat-DoT kill from opposite directions. Hornet Strike
stacks additively with Galvanized Shot (+120% → +340% total), doubling the
modded base seed: per-proc Heat ticks are ~1.63× bigger, but status stays at
3.51 procs/tick with Heat weight 45.1%, so only ~45 Heat procs accumulate by
t = 2 s. Scorch keeps the smaller seed but raises the Heat mod multiplier to
2.25× and merged status to 4.68 procs/tick, accumulating ~76 procs — roughly
1.7× as many. `1.63 × per-proc` vs `1.7 × procs` is an almost exact wash, so
both kill on the same consolidated DoT tick. Hornet's doubled direct damage
wins the Overguard phase (0.50 s vs 0.63 s) and has zero RNG dependence;
Scorch has the tighter worst-case tail and deeper strip (~105 vs ~384 armor
at kill).

### Icebind L1000 Eximus Heavy Gunner stress test (60 trials, 6-player squad)

| 8th mod | Median TTK | Worst case |
| --- | --- | --- |
| **Hornet Strike** | **5.00 s** | 5.94 s |
| **Scorch** | 6.00 s | 6.00 s |
| Anemic Agility | 6.00 s | 6.00 s |
| Primed Pistol Gambit | 7.00 s | 8.00 s |
| Frostbite | ~160 s | — |

With the corrected 0.5 ammo/tick cost the 77-round magazine covers ~9.6 s of
beam at 16 ticks/s, so no reload occurs in these fights for the Heat builds.

## Sensitivity checks

- **Without Secondary Enervate** (ordinary 7% crit): median TTK rises to
  4–7 s — the arcane roughly halves kill time.
- **If Heat stripped instantly** (no Status-Duration ramp slowdown): the
  Heat builds kill in ~1.0 s. The Riven's +112.5% Status Duration is a real
  trade-off: longer DoT/proc uptime versus a slower armor strip.
- Overguard damage-over-time behavior is moot: no DoT/Blast fuse tick occurs
  before the buffer breaks (~0.5–0.7 s).

## Modeled mechanics and assumptions

Beam ticks at `1/fire rate` with the 30%→100% 0.6 s ramp; multishot beams
merge (summed damage and status chance, single crit roll); per-tick proc
rolls weighted by damage distribution with guaranteed procs above 100%
status; Heat consolidation with the `(Σseeds + 1)·0.5·(1+Heat)·crit` tick
formula and per-proc multiplicative armor strip; Blast fuses, 10-stack and
on-death radials; Viral/Magnetic 10-stack multipliers; Overguard Magnetic
amplification and break damage; 1/32 direct-hit quantization; magazine/
reload behavior; Galvanized mods and Enervate at full/averaged effect as
requested.

Deliberate scope: body shots (×1; headshots would be ×3 and also multiply
Blast radials), no faction mod, no Warframe buffs, one fixed average Riven
roll, no votable Icebind restrictions, room model assumes a dense pack with
every target inside both radii. RNG uses fixed seeds so every result is
reproducible (`python3 -m unittest tests.test_kuva_nukor_sim`).

## Usage

```python
from modules.kuva_nukor_sim import (
    build_nukor, simulate, run_trials, simulate_room,
    steel_path_dummy_factory,
)

# Single target
result = simulate(build_nukor("Scorch"), steel_path_dummy_factory(),
                  seed=20261027, trace=True, trace_interval_s=0.25)
print(result.ttk, result.trace)

# Room clear (dense pack of 10 Eximus dummies)
room = simulate_room(build_nukor("Frostbite"), 10, seed=7000, trace=True)
print(room.clear_time, room.radial_events, room.kill_times)
```
