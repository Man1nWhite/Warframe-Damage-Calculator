# Kuva Nukor: Hornet Strike vs Scorch vs Frostbite

**Experimental model comparison, 2026-10-28.** These numbers are not verified
in-game times to kill. The model has material approximations, including Heat
stack timing, Blast behavior, and Overguard routing; see the
[formula audit](formula_audit.md). The older
[Kuva Nukor report](kuva_nukor_build_sim.md) remains an invalid historical
archive and was not used for these results.

## Build and assumptions

- **Kuva Nukor:** 60% Magnetic progenitor. The seven fixed mods are Galvanized
  Diffusion, Galvanized Shot, Lethal Torrent, Primed Heated Charge, Primed
  Target Cracker, Pistol Elementalist, and the specified Riven. All mods and
  Secondary Enervate are max rank.
- The exact Riven percentages were not supplied. This is a **hypothetical
  midpoint-grade**, 3-positive/1-negative Pistol Riven: **+101.3% spliced
  Viral, +101.3% Critical Damage, +112.5% Status Duration, −72.1% Zoom**.
  Viral is treated as an already-combined element. The 90% base value of a
  spliced Viral trait and the current normalized 1.2 Riven multiplier are
  documented on the Wiki [3](https://wiki.warframe.com/w/Riven_Mods); see also
  the Hotfix 44.1.3 notes [6](https://www.warframe.com/en/patch-notes/pc/44-1-3).
  This midpoint is an input, not an assertion about the user's actual Riven
  or the statistical mean of all possible splicing outcomes.
- Both Galvanized mods start at maximum **kill** stacks. The target starts
  without status effects; Galvanized Shot uses status types actually applied
  during the simulation, including Microwave after the first hit. At full
  kill stacks its bonus is +120% per distinct status type and normally adds
  to ordinary damage bonuses [19](https://wiki.warframe.com/w/Galvanized_Shot).
- Secondary Enervate is represented by the Wiki's steady-state average final
  critical chance: `102.45 + 0.5 × 7 = 105.95%` [4](https://wiki.warframe.com/w/Secondary_Enervate).
  The simulator samples crit tiers from that averaged chance; it does not
  simulate the arcane's actual ramp, reset cycle, or full tier distribution.
- Max-rank Primed Target Cracker is **+110%**, not +120% [1](https://wiki.warframe.com/w/Primed_Target_Cracker).
  With the assumed Riven, the first-tier critical multiplier is
  `5 × (1 + 1.10 + 1.013) = 15.565×`. This value was corrected in the Nukor,
  Ocucor, and Akarius simulations before the runs below. Pistol Elementalist
  gives **+90% status damage and +60% reload speed**, not duration [2](https://wiki.warframe.com/w/Pistol_Elementalist).
- Single target, body shots, uninterrupted beam until death, no faction mod,
  external buffs, companion, primer, headshots, or beam chains. Targets have
  no shields. Each starts at the Nukor's 30% beam ramp. Only the 8th mod
  changes; seeds are `20261028 + trial_index`. The simulation timeout is
  600 seconds; none of the reported runs timed out or reloaded.

## Modded status profile

| Last mod | Damage types present | Modded status per beam | Expected merged status rolls per tick |
| --- | --- | ---: | ---: |
| Hornet Strike | Radiation, Magnetic, Viral, Heat | 90% | 3.51 |
| Scorch | Radiation, Magnetic, Viral, Heat | 120% | 4.68 |
| Frostbite | Radiation, Magnetic, Viral, Blast | 120% | 4.68 |

The expected 3.9 beams result from full Galvanized Diffusion and Lethal
Torrent; actual ticks roll three or four beams. Same-target beam instances
merge for damage and status chance [8](https://wiki.warframe.com/w/Multishot).

Scorch adds +60% Heat and +60% status chance. Frostbite adds +60% Cold and
+60% status chance; here Cold and Primed Heated Charge's Heat combine into
Blast, so the weapon has **no separate Heat damage or Heat procs**
[5](https://wiki.warframe.com/w/Damage). The Riven's pre-combined Viral remains
separate in this model. Heat armor strip takes longer with positive status
duration [21](https://wiki.warframe.com/w/Damage/Heat_Damage): this Riven
changes each strip step from 0.5 to 1.0625 seconds, making the full four-step
ramp 4.25 seconds rather than 2 seconds.

## Results

The targets are calculated with the repository's Steel Path Heavy Gunner
model. The Eximus uses **1,716,837 health, 2,700 armor and 269,919
Overguard**; the ordinary Heavy Gunner uses **286,140 health, 2,700 armor
and no Overguard**. Overguard scaling follows the Wiki infobox gadget, which
differs from the scaling article; see the audit. The following numbers are
seconds from the first modeled hit to death. Mean and percentiles summarize
successful runs only; all runs succeeded. Extra decimal places identify the
simulated beam-tick boundaries, not real-world accuracy.

### Steel Path level 150 Eximus, 5,000 trials per mod

| Last mod | Mean | Median | p90 | Median Overguard break |
| --- | ---: | ---: | ---: | ---: |
| Hornet Strike | 2.0095 | 2.0000 | 2.0625 | 0.3125 |
| Scorch | 2.0024 | 2.0000 | 2.0000 | 0.3125 |
| Frostbite | 2.9567 | 2.9375 | 3.1250 | 0.2500 |

**Interpretation:** in this particular model Scorch and Hornet are effectively
close; their medians coincide at the same Heat-tick boundary. Scorch has a
slightly lower sample mean, but it is not defensible to treat the difference
as a validated gameplay win. Frostbite breaks Overguard slightly earlier in
the model but is slower to finish this armored, durable single target.

### Steel Path level 150 ordinary Heavy Gunner, 2,500 trials per mod

| Last mod | Mean | Median | p90 |
| --- | ---: | ---: | ---: |
| Hornet Strike | 0.9212 | 0.9375 | 1.0000 |
| Scorch | 0.9757 | 1.0000 | 1.0625 |
| Frostbite | 0.8108 | 0.8125 | 0.8750 |

Here Frostbite wins **in the model**: the target is frailer and Blast can
detonate before the first Heat damage tick. These are not predictions for
other factions, shields, levels, squad buffs, or enemy packs. Blast can damage
nearby enemies, but no crowd-clear times were measured here.

## Sensitivity and limits

- **Heat clock:** the default model makes each Heat stack wait at least one
  second before contributing to the shared tick. As a hypothetical alternative,
  allowing all already-applied stacks to contribute at the next group tick
  changes the Eximus mean to **1.8952 s for Hornet** and **1.7215 s for
  Scorch** (2,500 trials each, same seeds). This is a sensitivity experiment,
  not independent evidence of which implementation matches the game.
- **Blast on Eximus:** the default uses 10 stacks and the dedicated Blast
  page's single-target settlement. The Wiki's general calculation page instead
  describes a four-stack cap on bosses/Eximus and different settlement
  [13](https://wiki.warframe.com/w/Damage/Calculation). A four-stack
  sensitivity run **retaining the default's single-target settlement** gives
  Frostbite an Eximus mean of **3.0082 s** (2,500 trials); it is a hybrid
  assumption, not a resolution of the conflicting sources.
- **Ramp and status seed:** the default applies the beam ramp to direct hits,
  but does not apply it to status seeds. A sensitivity experiment applying
  the initial ramp to Heat/Blast seeds gave the same median ordering on both
  targets; the ordinary target's Frostbite mean changed from 0.8108 to
  0.8452 s. How the game treats this interaction is not established here.
- The model approximates mixed-hit overflow from Overguard, faction modifiers
  on Overguard, Magnetic-break Electricity, Heat eligibility, Blast settlement,
  and crit/DoT quantization. It does not establish shield-gate behavior or
  in-game accuracy. Average Enervate also suppresses the true cold-start and
  crit-tier variation. Different Riven rolls or outside armor strip can
  materially change the ordering.
- As community context, players discuss the benefit of multiple statuses for
  Galvanized Shot on the forums
  [28](https://forums.warframe.com/topic/1335866-kuva-nukor-questions/),
  and explain status-damage scaling on Reddit
  [16](https://www.reddit.com/r/Warframe/comments/1pfa5yp/elementalist_mods_status_damage/).
  Old Riven-disposition advice in community builds predates normalization.

## Reproduce the primary tables

Run from the repository root with Python 3:

```python
from modules.enemy_scaling import steel_path_heavy_gunner
from modules.kuva_nukor_sim import DummyTarget, run_trials, steel_path_dummy_factory

plain = steel_path_heavy_gunner(150)
def plain_factory():
    return DummyTarget(plain.health, plain.armor, plain.overguard)

mods = ("Hornet Strike", "Scorch", "Frostbite")
for label, factory, count in (
    ("Eximus", steel_path_dummy_factory, 5000),
    ("Ordinary", plain_factory, 2500),
):
    for mod in mods:
        result = run_trials(mod, factory, trials=count, base_seed=20261028)
        print(label, mod, result["ttk_mean"], result["ttk_median"],
              result["ttk_p90"], result["overguard_median"],
              result["trials_attempted"], result["timed_out"])
```

To reproduce the alternative Heat-clock sensitivity, start a fresh Python
interpreter and use the same seed and `run_trials`:

```python
from modules.enemy_scaling import steel_path_eximus_heavy_gunner
from modules.kuva_nukor_sim import DummyTarget, run_trials

class AllAppliedHeatAtGroupTick(DummyTarget):
    def consume_heat_tick(self, when, duration):
        if self.next_heat_tick(duration) != when:
            return []
        self.prune(when, duration)
        self._next_heat_tick = when + 1.0
        return list(self.heat_procs)

eximus = steel_path_eximus_heavy_gunner(150)
def factory():
    return AllAppliedHeatAtGroupTick(eximus.health, eximus.armor, eximus.overguard)

for mod in ("Hornet Strike", "Scorch"):
    result = run_trials(mod, factory, trials=2500, base_seed=20261028)
    print(mod, result["ttk_mean"], result["ttk_median"], result["timed_out"])
```

For the four-stack hybrid Blast sensitivity, in a fresh interpreter set
`modules.kuva_nukor_sim.BLAST_MAX_STACKS = 4` before calling `run_trials` for
Frostbite with 2,500 trials and seed 20261028. This deliberately changes the
simulation globally for that process; it does not establish the correct game
mechanic.
