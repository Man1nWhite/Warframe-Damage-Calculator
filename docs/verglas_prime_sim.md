# Verglas Prime: Crit Pair vs Heat Slots Against Dummy A

**Experimental simulation, not an in-game measurement or a definitive build ranking.**
Reviewed against the English WARFRAME Wiki on 28 October 2026.

Code: [`modules/verglas_prime_sim.py`](../modules/verglas_prime_sim.py),
tests: [`tests/test_verglas_prime_sim.py`](../tests/test_verglas_prime_sim.py).

This report answers one question from the build consultation: the user's
current two-slot crit pair (**Critical Delay + Vital Sense**) versus Heat and
rate alternatives on a Nautilus Verglas Prime, fired at the repository's
level-150 Steel Path **Eximus Heavy Gunner** dummy (1,716,837 HP, 2,700 armor,
269,919 Overguard). It replaces the earlier slot-by-slot damage-index
arithmetic with a tick-by-tick Monte Carlo that shares one engine with the rest
of the repository.

## Short answer

- **The crit pair is the slowest option tested.** Median time to kill is
  **6.15 s** with Critical Delay + Vital Sense versus **5.08 s** with Hellfire +
  Thermite Rounds, a **17%** difference. Every Heat loadout in the table beats
  every crit loadout.
- **Critical Delay alone is the worst build of all (6.88 s).** It buys a 42%
  crit chance on a 2.20x base multiplier while paying 20% fire rate, and it
  also delays the Overguard break — the opposite of what a two-slot crit
  package is supposed to do here.
- **The Overguard-break Electricity burst, not the gun, decides most of these
  kills.** About 0.9-1.2 million of the dummy's 1.72 million health comes from
  the Magnetic break proc; that component is nearly build-independent, which
  *compresses* the TTK spread. On self-generated health damage alone
  (direct + Heat DoT) Hellfire + Thermite is **+29%** over the crit pair, and
  the Viral/Heat loadout is **+194%**.
- **Magnetic is worth keeping — for the break, not for damage.** Magnetic does
  nothing to Grineer health, but ten stacks convert the Overguard break into a
  burst worth roughly 0.9-1.1 million health damage. The loadout that drops
  Magnetic (Cold + Toxin under Heat) produces the largest gun damage and still
  takes 6.00 s, because it has to shoot the whole Overguard bar down itself
  (3.00 s versus 1.56 s).
- **Do not read the ordering below as validated in-game.** See
  [Limits](#limits) and the [formula audit](formula_audit.md) first.

The resulting build is listed under [Final build](#final-build).

## The fixed context

Requested assumptions, all applied to every row:

| Item | Value |
| --- | --- |
| Target | `enemy_scaling.steel_path_eximus_heavy_gunner(150)` |
| Health / armor / Overguard | 1,716,837.41 / 2,700 (capped) / 269,918.97 |
| Weapon | Verglas Prime: 32 Cold, 14% crit at 2.20x, 36% status, 12.0/s, mag 80, 1.60 s reload, 0.0 m innate punch-through |
| Fired Up | Max rank, +5% Heat per hit, +100% at 20 hits, 5 s reset |
| Summoner's Wrath | +75% Companion damage, additive with faction, double-dipped on DoT |
| Rifle Elementalist | +90% Status Damage, +0.6 m punch-through |
| Riven | Average 1.2-disposition Rifle roll from [`source/riven_stats_average_1_2.csv`](../source/riven_stats_average_1_2.csv) |

The Riven is the one the consultation started from: **spliced +Viral,
+Multishot, +Critical Damage** (+0.81 multi, +1.08 crit damage, spliced Viral
at the base-element roll). Combined traits are absent from the vendored table,
so they take the base-element value, as the Splicer workbench gives them the
same range. The final Viral/Heat row uses the same Riven with **+Heat** instead
of +Viral.

## The loadouts

All eight rows carry **Serration, Split Chamber, Rime Rounds, High Voltage,
Rifle Elementalist, the Riven and Fired Up**; the two columns below are what
changes. Rime Rounds + High Voltage make **Magnetic** from the innate Cold,
which is the only reason the Overguard break burst exists.

| Key | Two changing slots |
| --- | --- |
| `user_list_crit_pair` | Critical Delay + Vital Sense (the current build) |
| `critical_delay_only` | Critical Delay |
| `vital_sense_only` | Vital Sense |
| `heat_pair` | Hellfire + Thermite Rounds |
| `heat_vital_sense` | Hellfire + Vital Sense |
| `heat_vile_acceleration` | Hellfire + Vile Acceleration |
| `heat_primed_shred` | Hellfire + Primed Shred |
| `viral_heat` | Cold + Toxin Riven, Hellfire + Thermite Rounds, **no Magnetic** |
| `final_recommended` | Hellfire + Primed Shred, the same +Viral Riven (see [Final build](#final-build)) |

Resolved stats for the current build: **2.71x multishot** (Split Chamber 0.90 +
Riven 0.81), **42% crit** at **7.228x** (2.20x quantized, +120% Vital Sense,
+108% Riven), **79.2% status per beam**, **9.60 attacks/s**, **0.6 m**
punch-through. Fired Up adds a standalone **Heat** group that ramps from 0 to
84.8 per beam.

## Results (200 trials per row, seed 20261028)

| Build | TTK median | p10 | p90 | Overguard break | Heat procs | Reloads |
| --- | --- | --- | --- | --- | --- | --- |
| `heat_vile_acceleration` | **5.05 s** | 5.00 | 5.32 | 1.14 | 65 | 1 |
| `heat_pair` | **5.08 s** | 5.00 | 6.00 | 1.92 | 76 | 0 |
| `heat_primed_shred` | 5.13 s | 5.00 | 5.61 | 1.34 | 64 | 1 |
| `final_recommended` | 5.13 s | 5.00 | 5.61 | 1.34 | 64 | 1 |
| `heat_vital_sense` | 5.75 s | 5.08 | 6.08 | 1.75 | 55 | 0 |
| `viral_heat` (no Magnetic) | 6.00 s | 6.00 | 7.00 | 3.00 | 121 | 0 |
| `user_list_crit_pair` | 6.15 s | 5.56 | 6.67 | 1.56 | 27 | 0 |
| `vital_sense_only` | 6.75 s | 6.25 | 7.50 | 2.00 | 38 | 1 |
| `critical_delay_only` | 6.88 s | 6.42 | 7.29 | 1.98 | 31 | 0 |

No trial timed out at the 600 s cap, and every row ends with the target at
**1,350 armor** — the 50% cap of the Heat strip ramp, reached well before the
kill. Heat proc counts separate cleanly by element mix: 27 with the crit pair
against 65-76 for the Hellfire rows.

Health-damage attribution (medians of the killed trials):

| Build | Direct | Heat DoT | Overguard-break Electricity | Gun only |
| --- | --- | --- | --- | --- |
| `heat_pair` | 210,847 | 700,959 | 883,766 | **911,806** |
| `heat_vile_acceleration` | 216,412 | 679,477 | 979,019 | 895,889 |
| `heat_primed_shred` | 236,006 | 637,323 | 975,844 | 873,329 |
| `heat_vital_sense` | 268,261 | 515,787 | 1,057,881 | 784,047 |
| `user_list_crit_pair` | 364,141 | 342,915 | 1,069,702 | 707,056 |
| `critical_delay_only` | 278,754 | 322,479 | 1,219,115 | 601,233 |
| `vital_sense_only` | 248,330 | 317,825 | 1,281,845 | 566,154 |
| `viral_heat` | 199,813 | 1,879,711 | 0 | 2,079,524 |

Two things fall out of that table:

1. **The crit pair wins the direct-damage column and loses the fight.** 364k of
   direct damage is the highest of any Magnetic build, but Heat DoT is 2.0x
   higher on the Hellfire rows, and the DoT keeps ticking while the gun reloads
   or the target is at range.
2. **A burst can hide a lot.** The break Electricity is 0.9-1.3 million in every
   Magnetic row; because it is shared, the TTK table understates how much worse
   the crit pair is at generating its own damage. `viral_heat` shows the reverse
   distortion: it must shoot the whole Overguard bar and its own Heat DoT
   overkills the dummy by ~20% before the kill lands, so its 6.00 s median hides
   the largest self-generated output of the set.

## Why the crit pair loses

Verglas Prime's 2.20x base multiplier is the problem, not the crit mods.
Critical Delay on a 14% base gives **42% at 2.20x** — an average factor of
1.51x for a 20% fire-rate loss and one of eight slots. Vital Sense only pays on
top of Critical Delay (7.228x, an average factor of 2.62x) and spends a second
slot. Meanwhile a single Hellfire adds **+90% Heat** to a group that Fired Up
already ramps, and Heat is the only proc in this mix that keeps compounding:
each proc becomes a 0.5x-coefficient tick with the Heat bracket applied once,
the faction bonus twice (3.06x with Summoner's Wrath) and Status Damage at
+90%. That is the mechanism behind 700k of Heat DoT from two slots versus 343k
from the crit pair.

Punch-through is deliberately *not* simulated: the dummy is a single body, and
0.6 m of Rifle Elementalist pierces nothing (the wiki's rule of thumb is ~1.2 m
per enemy). Primed Shred's 2.2 m reaches two bodies, which is a Cordon
multiplier and not a single-target one — see the earlier consultation for that
argument.

## Final build

Eight weapon slots, plus Fired Up on the Sentinel itself:

| Slot | Mod | Why |
| --- | --- | --- |
| 1 | Serration | +165% base damage |
| 2 | Split Chamber | +90% multishot; every extra beam is damage *and* status |
| 3 | Rime Rounds | Cold half of Magnetic |
| 4 | High Voltage | Electricity half of Magnetic, +60% status |
| 5 | Hellfire | +90% Heat, the only uncapped compounding proc |
| 6 | Primed Shred | +55% fire rate, +2.2 m punch-through (2.8 m with Elementalist) |
| 7 | Rifle Elementalist | +90% Status Damage, +0.6 m punch-through |
| 8 | Riven | keep the current **+Viral, +Multishot, +Critical Damage** roll |
| — | Fired Up (Sentinel mod, max rank) | +100% Heat after 20 hits |

Resolved: 2.71x multishot, **18.60 attacks/s**, 14% crit at 4.58x, 79% status
per beam, **2.8 m punch-through (2 bodies)**; per-beam Heat ramps 76.3 -> 161.1.
Median time to kill **5.13 s** (p10 5.00, p90 5.61) versus **6.15 s** for the
current Critical Delay + Vital Sense pair.

Swap the eighth slot, not the Riven:

| Eighth slot | Single-dummy TTK | Punch-through | Take it when |
| --- | --- | --- | --- |
| Vile Acceleration | 5.05 s | 0.6 m, 1 body | Pure single-target; no Cordon clumps |
| Thermite Rounds | 5.08 s | 0.6 m, 1 body | You want more Heat procs (76) and no fire-rate mod |
| **Primed Shred** | 5.13 s | **2.8 m, 2 bodies** | Nautilus Cordon: every beam hits two clumped bodies for +100% damage |
| Riven +Punch Through instead of +CD | 5.40 s (with Vile Acceleration) | 3.0 m, 2 bodies | You would rather reroll than spend slot 6 on Primed Shred |

Two traps the simulation confirms:

- **Do not trade the +Viral Riven for a +Heat Riven while keeping Rime
  Rounds + High Voltage.** With no Toxin source the build has no Viral at all;
  measured TTK jumps to 11.0-13.0 s even though Heat proc counts triple.
- **Do not drop Magnetic to add Heat.** The Cold + Toxin + double Hellfire
  build generates the most damage but must shoot the Overguard bar down itself
  (3.00 s versus 1.34-1.92 s) and forfeits the ~1 million break burst: 6.00 s.

## Limits

- **The Overguard-break burst is the largest single lever in the model and the
  least verified one.** The repository implements the wiki's Magnetic page as
  3% of maximum Overguard per stack per second over the six-second Electricity
  duration, with Status Damage and faction each applied twice. On a 269,919
  Overguard dummy that is a ~1 million damage event, and it dominates the
  attribution above. If that interaction is weaker in game than the page
  suggests, the TTK spread widens in favour of the Heat rows but the ordering
  does not change; if it is stronger, all Magnetic rows converge.
- **Monte Carlo spread is narrow, not absent.** Kills often land on a
  consolidated Heat tick, which is why several p10/median pairs coincide and
  why medians cluster on round values. The p10-p90 band, not the median alone,
  is the honest summary; the Heat rows' bands are tighter than the crit rows'.
- **Magnetic and Viral are capped per enemy.** Viral saturates at ten stacks
  (~1.67 procs/s needed against 4.2/s generated) and Magnetic does nothing to
  Grineer health, so proc generation beyond those caps is wasted — the point the
  consultation raised. Only Heat converts proc rate into damage without a cap.
- **Out of scope:** shields, weak points and body parts, punch-through geometry,
  Heat's first-proc inherit lock (irrelevant with a single Heat source), status
  duration beyond the six-second base, and any target that is not this dummy.
  See the [formula audit](formula_audit.md) for the shared assumptions.

## Reproducing

```bash
python -m unittest tests.test_verglas_prime_sim          # 24 tests
python -m modules.verglas_prime_sim --trials 200          # all eight rows
python -m modules.verglas_prime_sim --trials 200 --build heat_pair
```

`--seed` (default `20261028`) seeds trial *i* with `seed + i`, so a run is
reproducible but not a rerun of one sample. A single `--build` run also prints
the resolved element mix, stat line, and the health-damage attribution.
