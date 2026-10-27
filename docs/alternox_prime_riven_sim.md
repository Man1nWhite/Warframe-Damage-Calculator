# Alternox Prime Riven Choice: Blast Is Fixed — Which Two Other Positives?

Analytic expected-DPS ranking plus a tick-by-tick Monte Carlo simulation for
an Alternox Prime normal-fire build against the plain Steel Path level 150
Heavy Gunner dummy (286,139.57 health, 2,700 armor / 90% DR, no Overguard).
Code: [`modules/alternox_prime_sim.py`](../modules/alternox_prime_sim.py),
tests: [`tests/test_alternox_prime_sim.py`](../tests/test_alternox_prime_sim.py)
(40 tests).

**Short answer.** With Blast locked as one Riven positive, the second
positive should be **Toxin** (it combines with Primed Cryo Rounds into
**Viral**, worth roughly +423% on the baseline), and the third should be
**Damage or Fire Rate** — a statistical tie on burst, Damage wins
reload-adjusted sustained DPS, Fire Rate kills the standard dummy a fraction
of a second faster because it ramps Viral quicker. Curse: **−Punch Through**,
which is free on a weapon with innate infinite body punch-through.

## The build

Eight fixed mods plus the Riven (the user's loadout):

| Slot | Mod | Effect modeled |
| --- | --- | --- |
| 1 | Serration | +165% base damage |
| 2 | Galvanized Aptitude (2 kill stacks) | +80% status chance; +40% **direct** damage per status type per stack, +80%/type cap |
| 3 | Galvanized Chamber (5 kill stacks) | +80% multishot + 5 × +30% → 3.3 projectiles per trigger pull |
| 4 | Rifle Elementalist | ×1.9 Status Damage (the separate status-damage multiplier) |
| 5 | Primed Cryo Rounds | +165% Cold |
| 6 | Vital Sense | +120% critical damage |
| 7 | Critical Delay | +200% critical chance, −20% fire rate |
| 8 | Riven (3 positives + 1 curse, avg grade) | **Blast fixed**, two candidates ranked below |

Shared weapon stats (wiki Alternox Prime, Normal Attack, retrieved
2026-10-27): 75 pure Electricity per projectile, 5.33 shots/s, 20% crit
chance, 2.2× crit multiplier, 40% status chance, magazine 42, 1.8 s reload,
projectile with infinite body punch-through. With the fixed mods the build
runs 0.72 status chance per pellet (40% × 1.8), 3.3 multishot, 4.264 shots/s
before any Fire Rate Riven, 60% crit chance and 4.84× crit multiplier before
crit Rivens.

### What "Blast on the Riven" means now

The vendored Riven table
([`source/riven_stats_average_1_2.csv`](../source/riven_stats_average_1_2.csv))
only carries base attributes (its WDC codes are Heat/Cold/Elec/Toxin etc.);
combined elements are not normal cycling rolls. Since **Update 44.1
(2026-10-07)** the Mod Workbench supports **Riven Splicing** (wiki Riven
Splicer, retrieved 2026-10-27): two base-element traits merge into one
combined trait — Heat + Cold → Blast — with one spliced trait per Riven, and
the spliced trait inherits the higher consumed value. The wiki Riven Mods
Base Values table lists "Combined Elemental Damage" with the **identical
value range** to ordinary Elemental Damage, so at average grade every
elemental trait is worth the same 101.3% (the 1.20 disposition that all
weapons were normalized to when dispositions were retired in 44.1.3,
2026-10-22). The module therefore resolves combined-element Riven names to
the base-element average (`COMBINED_ELEMENT_STATS`) and lets a real roll be
passed explicitly via `blast_value=` (the earlier chat analysis used a fixed
+60% Blast trait; both scenarios are tabled below).

Because the spliced Blast is already a combined element it never participates
in further Arsenal combines, leaving the Primed Cryo Cold free to pair with a
Riven Toxin positive. There is only one Cold source: a Riven carrying two of
Toxin/Heat/Electricity could only combine one of them, and `combine_elements`
rejects that layout rather than model it silently — such rolls are outside
the candidate grid.

### GunCO is a separate multiplicative tier on this weapon

Galvanized Aptitude is a Condition-Overload-type ("GunCO") bonus. This
repository's curated catalog
([`source/gunco_mechanic.json`](../source/gunco_mechanic.json), resolved via
[`modules/condition_overload.py`](../modules/condition_overload.py)) carries
an explicit wiki-verified rule for the **Alternox Prime Normal Attack**:
projectile behavior **`multiply`**, scale 1.0. At two kill stacks with three
live status types the bonus is 3 × 80% = +240%, i.e. a standalone ×3.4
multiplier outside the Serration bracket (the intended "additive" behavior
would give ×4.4 total instead of ×4.506 × 3.4; the module keeps both modes
reachable because the wiki flags the projectile rule as community-documented
and partly unintended). Radial/AoE hits and the alt-fire sphere never receive
GunCO, and the +80% status-chance term affects proc frequency only.

Electricity and Blast procs snapshot the **GunCO-multiplied Modded Base
Damage** of the creating hit (wiki Condition Overload Mechanic, retrieved
2026-10-27), so Aptitude stacks raise proc/DoT damage by the same factor as
direct hits; Rifle Elementalist's ×1.9 then multiplies the ticks as the
separate Status Damage term.

### Status model

* **Viral** (Toxin + Cryo Cold): 2 + 0.25·(n−1) health damage, capped at 10
  stacks / ×4.25, 6 s duration.
* **Electricity** (innate): Tesla proc, 6 ticks over 6 s at 0.5× modded base
  per tick.
* **Blast** (spliced Riven trait): stacks on the target; each stack fuses for
  1.5 s and detonates for 0.3× modded base per stack; ten stacks detonate
  immediately for 3.0× modded base. The 5 m radial is excluded (single dummy;
  radii never receive GunCO).
* **Magnetic** (Riven Electricity + Cryo Cold) and standalone **Cold** only
  matter for shield disruption / slow and as GunCO status types; neither adds
  single-target health damage.

## Analytic results: all 20 candidate pairs

Steady-state expected DPS, full Galvanized stacks, Viral saturated at ×4.25,
average-grade Blast (101.3%). These are **pre-armor damage numbers** (the
90% DR of the 2,700-armor dummy is applied in the Monte Carlo, not here),
which is valid for ranking because every build faces the same armor curve.
"Sustained" applies the magazine-uptime discount
`mag_life / (mag_life + 1.8 s)`.

| # | Two positives (besides Blast) | Burst DPS | Sustained DPS | Status types | GunCO |
| --- | --- | --- | --- | --- | --- |
| 1 | **Damage + Toxin** | **1,128,031** | **953,742** | 3 | ×3.4 |
| 2 | Fire Rate + Toxin | 1,111,196 | 850,778 | 3 | ×3.4 |
| 3 | Critical Damage + Toxin | 1,000,135 | 845,607 | 3 | ×3.4 |
| 4 | Critical Chance + Toxin | 908,226 | 767,898 | 3 | ×3.4 |
| 5 | Multishot + Toxin | 867,044 | 733,079 | 3 | ×3.4 |
| 6 | Status Chance + Toxin | 702,969 | 594,355 | 3 | ×3.4 |
| 7 | Damage + Fire Rate | 361,175 | 276,530 | 3 | ×3.4 |
| 8 | Damage + Critical Damage | 321,164 | 271,542 | 3 | ×3.4 |
| 9 | Critical Damage + Fire Rate | 316,371 | 242,227 | 3 | ×3.4 |
| 10 | Damage + Critical Chance | 292,359 | 247,187 | 3 | ×3.4 |
| 11 | Critical Chance + Fire Rate | 287,995 | 220,501 | 3 | ×3.4 |
| 12 | Damage + Multishot | 281,818 | 238,275 | 3 | ×3.4 |
| 13 | Multishot + Fire Rate | 277,612 | 212,551 | 3 | ×3.4 |
| 14 | Critical Chance + Critical Damage | 268,907 | 227,359 | 3 | ×3.4 |
| 15 | Damage + Status Chance | 235,836 | 199,397 | 3 | ×3.4 |
| 16 | Fire Rate + Status Chance | 232,316 | 177,871 | 3 | ×3.4 |
| 17 | Critical Chance + Multishot | 224,717 | 189,997 | 3 | ×3.4 |
| 18 | Critical Damage + Status Chance | 200,763 | 169,744 | 3 | ×3.4 |
| 19 | Critical Chance + Status Chance | 183,823 | 155,421 | 3 | ×3.4 |
| 20 | Multishot + Status Chance | 181,272 | 153,264 | 3 | ×3.4 |

Every Viral build outranks every non-Viral build by roughly 2–3×. Within the
Viral bracket, Damage and Fire Rate are effectively tied on burst; Damage
takes sustained because the Fire Rate roll shortens magazine life from
9.85 s to 5.88 s, so reloads cost a larger fraction of the cycle. The
analytic engine was cross-validated to machine epsilon against an
independent reimplementation of the same formula for every pair and both
Blast values; the anchored outputs are pinned in
`tests/test_alternox_prime_sim.py`.

### The earlier chat scenario: fixed +60% Blast roll

Top of the table with the weaker, explicitly rolled Blast trait (the two
ranked positives stay average-grade):

| Two positives | Burst DPS | Sustained DPS |
| --- | --- | --- |
| Damage + Toxin | 1,037,968 | 877,594 |
| Fire Rate + Toxin | 1,022,477 | 782,851 |
| Critical Damage + Toxin | 917,428 | 775,678 |
| Critical Chance + Toxin | 833,636 | 704,833 |
| Multishot + Toxin | 797,819 | 674,550 |
| Status Chance + Toxin | 652,209 | 551,438 |
| Damage + Fire Rate (no Viral) | 327,054 | 250,406 |

The 327,054 figure matches the number quoted in the original chat analysis
exactly; the Viral-row figures there were understated because the scratch
model dropped the Primed Cryo +165% from the Viral combine (it counted only
the Riven Toxin 101.3% instead of the full 266.3% Viral factor). The
correction changes magnitudes, not ordering — the shopping conclusion below
is unchanged.

## Stochastic TTK vs the SP150 Heavy Gunner (200 seeded trials each)

Hit-by-hit simulation with 90% armor reduction, per-pellet status rolls,
sequential multishot, GunCO recomputed per hit from the statuses actually
live, Electric ticks and Blast fuses on the 1-second clock, Viral ramp, and
reloads.

| Riven positives | Median TTK | Mean | p90 | Reloads |
| --- | --- | --- | --- | --- |
| Fire Rate + Toxin | **3.080 s** | 3.112 s | 3.360 s | 0 |
| Damage + Toxin | 3.283 s | 3.379 s | 3.752 s | 0 |
| Critical Damage + Toxin | 3.518 s | 3.642 s | 3.987 s | 0 |
| Damage + Fire Rate (no Viral) | 9.081 s | 9.144 s | 9.781 s | 1 |
| Heat + Damage (no Viral, Blast merge) | 14.933 s | 14.830 s | 15.871 s | 1 |

All dummy fights end inside the first magazine, so the reload discount never
bites and the Fire Rate roll edges out Damage: more pellets per second
saturates the ten Viral stacks and seeds Electric/Blast procs faster. Treat
the two as interchangeable for ordinary missions — pick **Damage** for
long magazines / sustained fire and boss-style uptime, **Fire Rate** for
burst kills and faster status ramp. The no-Viral builds need roughly 3× the
time, and the Heat layout is worst because merging Heat into Blast removes a
status type and collapses GunCO from ×3.4 to ×2.6.

### Robustness checks (analytic)

* **Cold open, zero Galvanized kill stacks** (no ×3.4): Damage + Toxin still
  leads at 331,774, then Fire Rate + Toxin 326,822 — the ordering is
  identical before any kill stacks exist.
* **Single Viral stack (×2.0 instead of ×4.25)**: Damage + Toxin 530,838 vs
  Fire Rate + Toxin 522,916; even un-saturated Viral beats the best
  no-Viral roll (361,175).
* **Single-positive marginals over a Blast-only Riven** (full stacks):
  Toxin **+423.1%**, Damage +70.0%, Fire Rate +67.5%, Critical Damage
  +48.9%, Critical Chance +35.6%, Multishot +30.7%, Electricity → Magnetic
  +23.1%, Status Chance +9.4%, Heat (Blast merge) **−4.5%**.

## Shopping guidance

1. **Toxin is non-negotiable as one of the two open positives.** It is the
   only route to Viral in this loadout and no other positive is remotely
   close in value. Avoid re-rolling it away.
2. **Take Damage or Fire Rate as the third positive.** Critical Damage is a
   respectable third choice (~11% behind the leaders); crit chance,
   multishot and status chance trail further.
3. **Avoid Heat and Electricity positives.** Heat merges into the existing
   Blast and costs a GunCO status type; Electricity becomes Magnetic, which
   does nothing to health/armor on Grineer. (A four-type Magnetic GunCO build
   is impossible here anyway: one Cold source can only feed one combine.)
4. **Curse: −Punch Through.** The Alternox Prime's infinite innate body
   punch-through makes the penalty mechanically free; −Zoom is the harmless
   runner-up. Avoid −Fire Rate, −Damage and −Multishot curses.

## Assumptions and scope

Full Galvanized kill stacks (Aptitude 2, Chamber 5) are the steady-state
convention, with a documented zero-stack cold-open check; Viral is saturated
in the analytic model and ramped honestly in the Monte Carlo. Single target,
body shots, no faction mod, no Warframe/arcane buffs, average-grade Riven
values unless an explicit `blast_value` is passed, projectile travel time
ignored at close range, Blast radials and alt-fire excluded. RNG uses fixed
seeds; reproduce with `python3 -m unittest tests.test_alternox_prime_sim`.

Simulation mechanics follow the shared conventions in the kuva_nukor/akarius
sims: wiki 1/32 per-type quantization is applied to **pre-crit** direct
damage (crit multiplier lands afterwards), while DoT ticks and Blast
detonations use full-precision binary seeds; DoT ticks and Blast fuses are
evaluated on the integer-second clock, so a 1.5 s fuse resolves at the next
integer second (timing only — total proc damage is unaffected); a status
chance above 100% (Status Chance Riven builds reach ~145–153% per pellet)
grants `floor(sc)` guaranteed procs plus one fractional roll. Rifle
Elementalist's ×1.9 multiplies status damage only — wiki-verified
(2026-10-27) that it does **not** extend proc duration, which stays at the
6 s base. Galvanized Aptitude's 20-second stack timeout and Chamber stack
decay are not timed out; maintained stacks are an explicit input
(`galv_kill_stacks`, `chamber_stacks`).

## Usage

```python
from modules.alternox_prime_sim import (
    R_BLAST, R_DAMAGE, R_TOXIN, alternox_dummy_factory, build_alternox,
    expected_dps, rank_riven_pairs, run_trials, simulate,
)

# Analytic steady-state ranking (average-grade Riven values).
for report in rank_riven_pairs()[:5]:
    print(report.positions, report.total_dps, report.sustained_dps)

# A specific rolled Riven: fixed +60% Blast trait plus average candidates.
build = build_alternox((R_BLAST, R_DAMAGE, R_TOXIN), blast_value=0.60)
print(expected_dps(build))

# Stochastic TTK against the SP150 Heavy Gunner.
summary = run_trials((R_BLAST, R_DAMAGE, R_TOXIN), trials=200)
trial = simulate(build, alternox_dummy_factory(),
                 seed=20261027, trace=True)
print(summary["ttk_median"], trial.trace)
```

## Sources

* Wiki.warframe.com — Alternox Prime (Normal Attack stats), retrieved
  2026-10-27.
* Wiki.warframe.com — Riven Mods (Base/Spliced Values, disposition
  retirement) and Riven Splicer (Update 44.1 mechanics, 2026-10-07),
  retrieved 2026-10-27.
* Wiki.warframe.com — Galvanized Aptitude, Condition Overload (Mechanic),
  Status Effect / Blast / Electricity / Viral pages, retrieved 2026-10-27.
* [`source/riven_stats_average_1_2.csv`](../source/riven_stats_average_1_2.csv)
  — normalized 1.20-disposition Rifle Riven averages (`LotusRifleRandomModRare`).
* [`source/gunco_mechanic.json`](../source/gunco_mechanic.json) — curated
  GunCO behavior catalog; Alternox Prime Normal Attack `multiply` rule.
