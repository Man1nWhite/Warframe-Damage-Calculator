# Ocucor: Arcane Choice and Riven Stat Simulation

> **Historical report — results invalidated by the 2026-10-27 formula audit.**
> The archived TTKs, rankings, recommendations and some formulas below use
> superseded mechanics. For the requested Multishot/Viral Riven and arcane
> comparison, see the newer [experimental report](ocucor_enervate_flare_comparison.md).
> Simulation output still has important limitations; see the
> [formula audit](formula_audit.md) before use.

<details>
<summary>Show archived, unvalidated report</summary>

Tick-by-tick Monte Carlo simulation for an Ocucor against the Steel Path
level 150 Eximus Heavy Gunner dummy (1,716,837.41 health, 2,700 armor / 90%
DR, 269,918.97 Overguard). Code:
[`modules/ocucor_sim.py`](../modules/ocucor_sim.py), tests:
[`tests/test_ocucor_sim.py`](../tests/test_ocucor_sim.py).

Two coupled decisions:

1. **Arcane:** Secondary Enervate (averaged through the wiki AFCC formula)
   vs **Cascadia Flare** (+12% damage per Heat status, stack ramp simulated
   tick by tick, 40 stacks / +480% cap, 10 s refreshable).
2. **Riven stat:** the Riven is fixed at **+Viral, −Zoom** with one more
   positive to choose — Critical Damage, Critical Chance, Damage, Fire Rate,
   Status Chance, or Multishot (average-grade Pistol Riven, 2 positives +
   1 curse, values from `source/riven_stats_average_1_2.csv`).

## Galvanized Shot treatment

Ocucor has no entry in the repository's GunCO exception table
(`source/gunco_mechanic.json` / `.csv`; grep for `ocucor` returns nothing),
so the default hitscan rule applies: Galvanized Shot's +120% Condition
Overload bonus **adds into the ordinary +damage pool**. That means Galv
Shot, a Damage Riven and Cascadia Flare all compete in the *same*
multiplicative bracket — the key reason a Damage Riven gets diluted while
Flare is active, while Multishot stays an independent multiplier.

## The build

| Slot | Mod / item | Effect modeled |
| --- | --- | --- |
| Arcane | Secondary Enervate **or** Cascadia Flare | AFCC average **or** simulated +12%/Heat-proc stacks |
| 1 | Galvanized Diffusion (all stacks) | +230% Multishot |
| 2 | Galvanized Shot (all stacks) | +80% Status, +120% CO damage (additive bracket) |
| 3 | Lethal Torrent | +60% Fire Rate, +60% Multishot |
| 4 | Primed Heated Charge | +165% Heat |
| 5 | Primed Target Cracker | +120% Critical Damage |
| 6 | Pistol Elementalist | +90% Status Duration (×1.9) |
| 7 | Sentient Surge | +60% Crit / +60% Status per Tendril, 20% mag refill per kill |
| 8 | Riven (avg, 2 pos + 1 curse) | +133.7% Viral, selectable second positive, −47.6% Zoom |

Shared modded stats (Critical-Damage Riven shown): **3.90 multishot**,
**19.2 beam ticks/s** (0.0521 s/tick), **43.2% status per beam → 1.685
merged status rolls per tick**, modded crit 16% → **AFCC 110.45%** with
Enervate (every tick crits, ~10% orange), crit multiplier **6.367×** with
a CD Riven (3.96× without), damage bracket **×2.20** before Flare,
status-duration ×1.9 (Heat/Viral 11.4 s, Heat strip ramp 0.95 s/step).
Magazine 60 at 0.5 ammo/tick = 120 ticks (6.25 s of continuous fire),
1.6 s reload. Beam damage ramps 20% → 100% over the first 0.6 s of held
fire. Multishot beams merge, so each tick is one damage instance: summed
damage and status, one crit roll, and **at most one Cascadia Flare stack
per tick**.

Damage mix per single beam (bracket ×2.20): 22.0 Radiation, 2.2 Puncture,
39.93 Heat, 32.36 Viral — proc weights **Heat 41.4%, Viral 33.5%,
Radiation 22.8%, Puncture 2.3%**. The innate Radiation (a pre-combined
Fire+Electric element) coexists with standalone Heat and the Riven's
Viral; nothing combines unexpectedly. Heat's expected application rate is
~13.4 procs/s, so Flare reaches its 40-stack cap in roughly 3 s (the sim
hits the cap in every trial).

## Results vs the SP150 Eximus Heavy Gunner (1,000 seeded trials each)

Median time-to-kill in seconds. Flare peak is the median highest stack
count reached during the fight (40 = cap).

| Riven stat | Enervate median | Enervate mean (p90 / min–max) | Flare median | Flare mean (p90 / min–max) |
| --- | ---: | ---: | ---: | ---: |
| **Damage** | **6.042** | 6.325 (7.850 / 5.990–8.006) | 10.038 | 9.720 (10.038 / 8.006–11.860) |
| Multishot | 8.006 | 8.231 (8.788 / 7.850–9.048) | **9.048** | **8.971** (9.829 / 7.850–10.819) |
| Critical Damage | 8.162 | 8.294 (8.892 / 7.850–9.308) | 10.142 | 10.459 (11.340 / 8.162–13.006) |
| Fire Rate | 9.011 | 9.014 (9.011 / 8.021–11.397) | 9.011 | 9.392 (11.397 / 8.021–11.670) |
| Status Chance | 9.048 | 8.932 (9.517 / 8.006–10.038) | 9.152 | 9.386 (10.038 / 8.006–11.027) |
| Critical Chance | 10.767 | 10.663 (11.027 / 9.360–12.017) | 9.777 | 9.619 (10.038 / 8.006–11.235) |

Overguard (269,919) breaks at 3.07 s median for the winning Enervate +
Damage build, after which Heat strips the 2,700 armor to effectively zero
and Viral stacks (up to 10, 4.25× health multiplier) amplify both direct
beam damage and Heat DoT. A magazine holds 120 ticks (6.25 s of fire), so
the 6.04 s winning build finishes inside its first magazine in 90% of
trials; every other configuration (8–11 s TTKs) burns through one reload,
with Fire Rate occasionally needing two.

## Room clears: Tendrils, Sentient Surge and Flare uptime

Against a single dummy, Sentient Surge is inert until the target dies —
Tendrils only spawn from kills, so its +240%/+240% four-Tendril bonus and
20% magazine refill never activate before the fight is over. In a dense
room (`simulate_room`), each kill spawns a Tendril (max 4) that fires a
full-damage beam with independent crit/status rolls at another target;
Surge's bonuses are added **additively** with mods, and Tendrils reset on
reload per the wiki. Median clear times, 30 seeded runs:

| Room | Enervate + Damage | Flare + Damage | Flare + Multishot |
| --- | ---: | ---: | ---: |
| 5 enemies | 23.04 s | 23.04 s | — |
| 10 enemies | 34.23 s | 27.00 s | **25.02 s** |
| 20 enemies | 45.01 s | 35.02 s | **33.04 s** |

The ordering flips in sustained content. Flare's ~3-second ramp is paid
once and then stays capped for the whole room because Heat procs on every
target refresh it, while its +480% bracket applies to every Tendril beam.
Enervate's averaged crit advantage is tuned for one short duel, not twenty
consecutive ones.

## Why these numbers come out this way

- **Enervate wins single-target (6.04 s vs 9.05 s best Flare).** The AFCC
  formula puts every beam tick over 100% crit chance; with a 3.96–6.37×
  multiplier that is roughly a ×4.3 average crit factor from the first
  tick. Flare needs ~3 s of Heat procs before its bracket catches up, and
  a 6-second duel ends right around the break-even point.
- **Flare wins rooms (33.0 s vs 45.0 s at n=20).** The ramp amortizes over
  many targets, stacks never drop, and the bonus feeds Tendril beams too.
- **Damage is the best Riven under Enervate.** Bracket ×2.20 → ×4.671 more
  than doubles every damage type *and* every Heat DoT seed, and DoT is a
  large share of late-fight damage. No other stat comes close (+33% over
  the next-best Multishot roll).
- **Multishot is the best Riven under Flare.** Flare already inflates the
  shared damage bracket to ×7.0; a +247.1% Damage Riven only grows that to
  ×9.47 (+35%), whereas +134.7% Multishot is a separate ×1.35 multiplier
  on damage that also raises merged status (faster Heat procs, faster Flare
  ramp, more Viral) and enlarges Heat DoT seeds via the merged base.
- **Critical Chance is the worst Enervate roll.** Enervate already
  guarantees crits through AFCC, so base crit chance above 16% buys almost
  nothing; it only redeems itself under Flare, where no AFCC exists.
- **Fire Rate starves the magazine.** It adds zero damage per magazine and
  pushes the 120-tick mag dry faster: room runs average 11–12 reloads
  instead of 2–3, making it the worst room-clear stat by a wide margin.

## Recommendation

- **Primary pick for the SP150 dummy / single-target assassination:
  Secondary Enervate with a +Damage second positive.** Median TTK 6.04 s —
  the best of all 12 configurations, ~33% faster than the best Flare roll.
- **If the weapon is for sustained room clearing: Cascadia Flare with
  +Multishot** (25.0 s / 33.0 s median for 10 / 20 enemies), with +Damage
  a close second.
- **One Riven to cover both uses: +Damage.** It is the clear Enervate
  winner and remains competitive on Flare (10.04 s single, 35.0 s rooms),
  avoiding the Fire Rate and Critical Chance trap stats entirely.

## Assumptions and scope

- Galvanized Diffusion and Galvanized Shot are at full stacks from t=0, as
  requested. Secondary Enervate uses the wiki AFCC regression as a
  constant average (repository convention); the real arcane ramps per hit,
  so its true early-fight output is slightly lower than modeled while
  Flare's ramp is modeled exactly — the live Enervate-vs-Flare gap in
  short fights may be a little smaller than the table suggests.
- Single-target runs model no Tendrils and no Sentient Surge bonus, since
  neither can activate before the only target dies. Room runs model
  Tendrils as parallel full-damage beams on separate targets, reset on
  reload; line-of-sight, range and reticle-cone limits are ignored, and
  ammo reserves are assumed sufficient for the modeled magazine refills.
- Radiation (confusion) and Puncture procs have no single-target DPS effect
  and are counted but not acted on. Ocucor is a normal (non-Lich) weapon,
  so there is no Magnetic element; Overguard is broken by raw damage only.
- Wiki mechanics retrieved 2026-10-27 (Ocucor, Sentient Surge, Cascadia
  Flare pages). No external packages; standard-library `unittest` only.

## Usage

```python
from modules.ocucor_sim import run_trials, simulate_room

# 1,000-trial single-target matrix entry
print(run_trials("Secondary Enervate", "Damage", trials=1000))

# Dense room with Tendrils + Sentient Surge
result = simulate_room("Cascadia Flare", "Multishot", n_enemies=10, seed=1)
print(result.clear_time, result.tendril_peak, result.flare_peak)
```


</details>
