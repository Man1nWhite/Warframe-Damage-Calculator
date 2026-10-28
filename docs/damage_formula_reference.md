# Warframe Damage & Status Formula Reference

Compiled from the WARFRAME Wiki on **2026-10-27** and re-verified page by page
on **2026-10-28**. Several source pages carry an "actively being worked on"
banner and disagree on some details. This is a reference, not a claim that the
calculator or simulators implement every formula here. See
[the formula audit](formula_audit.md) for tested scope, source conflicts and
known simulation errors, and
[the wiki verification report](wiki_formula_verification.md) for the per-formula
verdicts and the pages each one was read from.

## Sources

| Topic | Wiki page |
| --- | --- |
| Full calculation chain, quantization, DPS, DoT | https://wiki.warframe.com/w/Damage/Calculation |
| DoT timing, stacking, scaling, detonation | https://wiki.warframe.com/w/Damage_over_Time |
| Status chance, proc weighting, multishot, beams | https://wiki.warframe.com/w/Status_Effect |
| Beam (continuous weapon) mechanics | https://wiki.warframe.com/w/Continuous_Weapon and https://wiki.warframe.com/w/Multishot |
| Hit registration | https://wiki.warframe.com/w/Hitscan |
| Per-type proc formulas | https://wiki.warframe.com/w/Damage/Slash_Damage, /Heat_Damage, /Toxin_Damage, /Electricity_Damage, /Gas_Damage, /Blast_Damage, /Corrosive_Damage, /Cold_Damage, /Viral_Damage, /Magnetic_Damage, /Puncture_Damage |
| Critical hits, tiers, base-multiplier quantization | https://wiki.warframe.com/w/Critical_Hit |

---

## 1. Direct damage (the hit itself)

### 1.1 Modded stats and Arsenal total

```
Modded Stat   = Base Stat x (1 + Stat Bonuses)
Modded Time   = Base Time / (1 + Speed Bonuses)          # reload, charge
```

Arsenal total damage (average non-crit damage per shot, no faction bonus):

```
Arsenal Total = Base Damage
              x [ 1 + Elemental Bonuses
                  + unmodded Impact share    x Impact Bonuses
                  + unmodded Puncture share x Puncture Bonuses
                  + unmodded Slash share     x Slash Bonuses ]
              x (1 + Damage Bonuses)
              x [ Base Multishot x (1 + Multishot Bonuses) ]
```

Melee weapons have no multishot term and no stance multiplier in this number.
The desktop currently uses innate multishot only. It applies this generic
calculation to the public-export row, which may combine separate impact and
radial events rather than describing one hit; see the
[Grimoire example and limitations](formula_audit.md#2026-10-28-follow-up-weapon-export-collisions-and-hit-components).

### 1.2 Quantization

Each physical/elemental damage type is rounded to the nearest 1/32 of the
attack's modded base damage **before** any further multiplier:

```
Scale = Modded Base Damage / 32
x     = Damage Type Value / Modded Base Damage
Quantized(x) = sign(x) x floor(|x| x 32 + 0.5) / 32
Quantized Damage Type Value = Quantized(x) x Modded Base Damage
```

DoT ticks are **not** quantized this way (see section 4). After all applicable
multipliers and defenses, the damage pop-up is rounded to a whole number;
this display rounding is not applied to the underlying health damage.

### 1.3 Health-type and armor modifiers

```
Unarmored / True (Cinematic) damage:  Inflicted = Starting x (1 + Health Modifier)
Enemy armor <= 2700:  DR = 0.9 x sqrt(Armor / 2700)
Enemy armor > 2700:   DR = Armor / (Armor + 300)    # exceptional case
Health damage = Starting x faction/type modifier x (1 - DR)
```

Armor is the value after all debuffs (Corrosive procs, Corrosive Projection,
Terrify, ...). Positive damage reduced by armor has a minimum of 1 per damage
type. Shield damage is not reduced by armor; Toxin generally bypasses shields
straight to health (Treasurer/Hounds excepted). The desktop calculator models
health, not shields or Overguard.

### 1.4 Total, crit, AoE and weak points

```
Total Inflicted = SD_1 x DM_1 + ... + SD_n x DM_n                 # per type, summed
Average Shot    = Total x (1 + Modded Crit Chance x (Modded Crit Multiplier - 1))
Normal Shot     = Total x [1 + floor(Crit Chance) x (Crit Mult - 1)]
Critical Shot   = Total x [1 + ceil(Crit Chance)  x (Crit Mult - 1)]
AoE attack      = Average Shot(direct hit) + Average Shot(AoE hit)   # separate instances
Weak Point      = Average Shot x (Weak Point Multiplier + Weak Point Damage Bonus)
```

Direct-hit and AoE instances have independent stats; some bonuses (e.g.
Condition Overload-type damage, see `source/gunco_mechanic.json`) affect only
the direct instance. AoE cannot headshot; some weapons (e.g. Arca Plasmor) have
no headshot multiplier at all.

Critical chance and critical damage are built from relative and absolute
bonuses, and the **base** critical multiplier is stored as a 12-bit code:

```
Modded Crit Chance     = Base Crit Chance x (1 + Relative Bonus) + Absolute Bonus
Modded Crit Multiplier = Quantized Base x (1 + Relative Bonus) + Absolute Bonus
Code(x)                = floor(clamp(x, 0, 32) x 4095 / 32 + 0.5)
Quantized Base         = Code(x) x 32 / 4095
```

Relative bonuses (Point Strike, Riven Critical Damage, Vital Sense) scale the
base; absolute bonuses (Arcane Avenger, Puncture's Weakened, Cold's Freeze
bonus, Secondary Enervate) are added afterwards. Critical tiers follow
`1 + tier x (Crit Multiplier - 1)`; above 100% the floor tier is the lowest
guaranteed hit and the ceiling tier the next possible one (250% -> tiers 2 and
3). A critical headshot doubles the critical term before the location
multiplier:
`Headshot Crit Tier = Headshot Multi x (1 + tier x (2 x Crit Multiplier - 1))`
(not implemented: every bundled simulator assumes body shots). Example (Critical Hit page): `Code(1.6 + 0.4) = 256`, so the decoded base
is `256 x 32/4095 = 2.0004884`.

Cold is the only status that changes critical damage: **+0.10x** on the first
Freeze stack, **+0.05x** per subsequent stack, and **+1.0x** while frozen at 10
stacks (bosses and Overguard-carrying enemies cap at 4 stacks, +0.25x). It is
additive with Critical Damage mods, applies before the tier is chosen, and does
not apply to AoE damage. Kunai with Primed Target Cracker at 9 Cold stacks:
`1.6 x (1 + 110%) + 0.50 = 3.86`.

Implemented in `modules/crit.py` (`modded_crit_chance`,
`quantize_crit_multiplier`, `modded_crit_multiplier`,
`cold_crit_damage_bonus`, `crit_tiers`, `normal_shot`, `critical_shot`,
`average_shot`, `direct_aoe_shot`, `weak_point_shot`). The simulators reach the
Freeze bonus through `DummyTarget.crit_damage_multiplier`, which adds it for
that target's live Cold stacks before the tier; it is zero unless the target
actually carries Freeze stacks, and the Akarius radial Blast instance opts out
because the bonus does not apply to AoE damage.

### 1.5 DPS

```
Average Burst DPS    = Average Shot x Effective Fire Rate
Shots per Magazine   = Modded Mag Size / Ammo Cost Per Shot
Sustained DPS        = Burst DPS x ShotsPerMag / (EffFireRate x Reload + ShotsPerMag)
Effective Fire Rate:
  Auto / Semi / Duplex / Held = Modded Fire Rate
  Charge   = 1 / (Modded Charge Time + 1 / Modded Fire Rate)
  Burst    = Burst Count / (1/Modded Fire Rate + (Burst Count - 1) x Modded Burst Delay)
```

---

## 2. Hitscan, projectile and beam attacks

The **damage formula is identical** for all three; the differences are hit
registration, proc rolls and multishot behavior.

### 2.1 Hitscan (internally `DHT_TRACE`, "trace fire")

- Instant line trace from reticle to hitbox; limited by the Range stat
  (300 m normal weapons, 1000 m snipers). Accuracy below 100 deviates the
  trace; Punch Through lets the trace penetrate geometry/enemies.
- Every pellet/projectile rolls crit and status independently.
- Damage falloff is a final multiplier based on distance.
- Continuous (beam) weapons are a subclass of hitscan.

### 2.2 Projectile

- A traveling object with projectile speed (moddable), flight time and, for
  launchers, an impact instance plus an explosion-radius instance.
- Same per-projectile proc/crit rolls as hitscan.
- Projectile **explosion radii never receive Condition Overload-type bonuses**;
  hitscan/beam AoE applies them only to the directly hit enemy (see the GunCO
  tables).

### 2.3 Beams / continuous weapons (Held trigger)

- Hitscan ticks, not traveling projectiles. Tick interval =
  **1 / modded fire rate**; ammo cost 0.5 per tick (flamethrowers excepted).
- Damage ramps from ~20% to 100% over **0.6 s** on target; 0.8 s after losing
  the target it decays back over 2 s. Reloading resets the ramp.
- Multishot beams hitting the same target **merge into one damage instance**:
  damage **and status chance are the sum** of the individual beams, while crit
  chance stays that of a single beam.
- Consequence: damaging status effects from beams are affected **twice** by
  multishot (more proc chance *and* a bigger merged damage seed feeding the
  proc). Forced procs (Hunter Munitions, Seeking Talons) are applied after the
  merge, so they are not double dipped — one proc per interval.
- Chaining beams (Amprex, Atomos, Kuva Nukor, ...) hit secondary targets for
  reduced damage; Firestorm extends chain range, Punch Through spreads rather
  than increases damage.
- Multishot does not enlarge the spherical blast of flamethrower-type beams
  (Ignis, Glaxion, Gaze, Embolist, Catabolyst, ...).

---

## 3. Status chance and proc selection

- Arsenal status chance is the probability **per pellet/projectile/tick**.
  Multishot adds rolls, it never changes the per-projectile chance.
- Above 100%, each whole 100% guarantees one proc, and the fractional remainder
  rolls one more. Each type is drawn independently with replacement, so the
  same type can occur multiple times on one hit.
- Proc type weighting equals the damage distribution (enemy status immunities
  remove that type and renormalize):

```
Proc Type Chance = Damage of Type / Total Damage
```

- Since **Update 27.2 (2020-03-05)** there is no longer a 0.25x multiplier on
  elemental status weights — the old 4:1 physical-to-elemental weighting is
  gone, every damage point weighs equally.
- One attack hitting multiple enemies gives each enemy its own roll.
- Forced procs ignore status chance and damage distribution and can occur
  alongside a normal proc.

```
Average Procs Per Shot   = Multishot x (Forced Procs + Status Chance per Projectile)
Average Procs Per Second = Average Procs Per Shot x Fire Rate
Beam merged tick chance  = Status Chance per Beam x Multishot
```

---

## 4. Status damage over time

Five damage types deal DoT: **Slash, Heat, Toxin, Electricity, Gas** (Blast is
a delayed 1.5 s detonation, not a true DoT).

### 4.1 Tick timing (base 6 s duration, 1 tick/s)

| Proc | Delay | Tick times (s) | Damaging ticks | AoE? | Stack cap |
| --- | --- | --- | --- | --- | --- |
| Slash (Bleed) | 1 s | 1, 2, 3, 4, 5, 6 | 6 | no | none |
| Heat (Ignite) | 1 s | 1, 2, 3, 4, 5, 6 | 6 | no | none (refreshing stack mechanic) |
| Toxin (Poison) | 1 s | 1, 2, 3, 4, 5, 6 | 6 | no | none |
| Electricity (Tesla Chain) | none | 0, 1, 2, 3, 4, 5 (tick at 6 s empty) | 6 | 3 m chain | none |
| Gas (Gas Cloud) | none | 0, 1, 2, 3, 4, 5 (tick at 6 s empty) | 6 | 3 m cloud | 10 |

```
Total Ticks = floor(Tick Rate x (Duration - Delay)) + 1
Total DoT   = Damage per Tick x Total Ticks
```

Status Duration mods (Lingering Torment, Perpetual Agony, Continuous Misery,
...) extend duration and therefore add ticks. DoT Detonation effects
(Expedite Suffering, Final Verse Tragedy, Divine Retribution, Harmony heavy)
pay out all remaining ticks in one damage instance.

### 4.2 The tick formula

The wiki describes this tick-group form with binary32 intermediates:

```
Unrounded Tick Damage = (sum(S_i) + 1) x C x M
```

- `S_i`: full-precision damage seeds consolidated into this tick group
- `+1`: the group's accumulator starts at 1; counted **once per tick group**,
  not per stack and not as a flat end bonus
- `C`: **0.35 Slash**, **0.50 Heat / Toxin / Electricity / Gas**
- `M`: product of remaining applicable modifiers (elemental, faction and
  status damage). Crit/body-part factors can be part of the stored seed;
  avoid multiplying them twice.

The Python helpers use binary64 and do not implement exact binary32 or critical
multiplier quantization, so their results can differ slightly in game.

The per-type wiki pages present the simplified form without the accumulator:

```
Tick = C x Modded Base x (1 + Elemental) x (1 + Faction) x (1 + Status Damage) x Additional
Modded Base = Base Damage x (1 + Base Damage Bonuses) x (1 + Faction Bonuses)
```

"Modded Base" deliberately excludes physical and elemental +damage mods.
Faction bonuses appear twice (once in the seed, once as an explicit factor) —
the wiki's "double dip".

### 4.3 Per-type details

| Type | C | Special rules |
| --- | --- | --- |
| **Slash** | 0.35 | Cinematic damage — ignores armor. No elemental term at all; physical mods (Buzz Kill, Sawtooth Clip) don't buff it. Enemy-inflicted Bleed uses 0.10 instead of 0.35. |
| **Heat** | 0.50 | Buffed by literal Heat mods (Hellfire, Thermite Rounds); panic + armor strip ramping to 50%; proc instance refreshes. |
| **Toxin** | 0.50 | Bypasses shields to health; buffed by Toxin mods; does not affect the embedded DoT on Stinger-type weapons. |
| **Electricity** | 0.50 | 3 m Tesla Chain, stuns; buffed by Electricity mods; headshot/body-part rolls per chained enemy. |
| **Gas** | 0.50 | 3 m cloud, +0.3 m per stack up to 6 m at 10 stacks; **only literal Gas mods** (Leaded Gas, Valence Formation) buff it — Heat and Toxin component mods do not. Cloud can headshot (1x base, moddable via Target Acquired/Deadhead). 11th stack replaces the oldest. |

What a proc inherits from the inducing hit: base damage buffs (Serration, Vex
Armor, Eclipse, ...), the matching elemental mod, faction mods (twice), crit
multiplier and stealth/body-part multipliers, status-damage bonuses
(Elementalist mods, Emerald Shard, Galvanized Elementalist), melee/sniper
combo counters. Sonar/Detect Vulnerability weak spots buff the hit only, not
the proc. Critical DoTs use the inducing hit's effective crit multiplier.

Wiki worked examples (pinned in tests):

- Heat, 40 seed +60% Heat: `(40+1) x 0.5 x 1.6 = 32.8` (pop-up 33)
- Electricity, 40 seed +150%: `(40+1) x 0.5 x 2.5 = 51.25` (pop-up 51)
- Gas, 40 seed, no bonuses: `(40+1) x 0.5 = 20.5` (pop-up 21)
- Toxin, 40 seed +225% Toxin, +55% faction: `(40x1.55+1) x 0.5 x 3.25 x 1.55 = 158.68125`
- Slash, 100 base + Serration + Bane of Grineer + Rifle Elementalist:
  `100 x 2.65 x 0.35 x 1.3^2 x 1.9 = 297.8202` per tick
- Toxin page example: modded base 344.5, DoT multiplier 4.693 →
  `0.5 x 344.5 x 4.693 = 808.3692` per tick

Update 43.0 (2026-06-17) added the health-bar **DoT Preview** showing exactly
how much a status DoT will deal across health/shields/Overguard (abilities such
as Saryn Spores excluded).

---

### 4.4 Non-damaging status effects (numbers used by the simulators)

| Proc | Duration / stacks | Effect |
| --- | --- | --- |
| Impact (Stagger) | 1 s, 5 stacks | +8% Parazon Mercy threshold per proc |
| Puncture (Weakened) | 10 s, 5 stacks | enemy damage -40%, then -10% per stack (max -80%); incoming weapon damage +5% flat critical chance per stack (max +25%), not on AoE |
| Cold (Freeze) | 6 s, 10 stacks (4 under Overguard) | slow 50% -> 90%; +0.10x critical damage, +0.05x per stack, +1.0x frozen |
| Corrosive (Corrosion) | 8 s, 10 stacks | armor `1 - (0.20 + 0.06 x stacks)`, i.e. 26% then +6% to 80% |
| Viral (Virus) | 6 s, 10 stacks | health damage `2 + 0.25 x (stacks - 1)`, max 325%; not double-dipped on DoTs |
| Magnetic (Disrupt) | 6 s, 10 stacks | shields/Overguard damage `2 + 0.25 x (stacks - 1)`; on break a forced Electricity proc worth 3% of max defense per stack over 6 s |
| Radiation (Confusion) | 12 s, 10 stacks | friendly fire, +100% and +50% per stack to 550% |
| Blast (Detonate) | 1.5 s fuse, 10 stacks (4 for bosses and some Eximus) | 30% of modded base per stack, or `max(1, 0.3 x H)` if the fuse expires unnoticed; at the cap or on death all stacks detonate for 300% per stack within 5 m to *other* enemies (the proc target keeps only the 30%-per-stack single-target damage) |

Heat's armor strip is 15/30/40/50% at 0.5 s intervals after the first proc and
restores 50/40/30/15/0% every 1.5 s after it ends; armor reductions from Heat,
Corrosive and Corrosive Projection are multiplicative with one another
(`(1 - heat) x (1 - corrosive) x (1 - 0.18 x projections)`).

## 5. Gas status — change history

Current mechanics (2026): a Gas proc spawns a 3 m cloud dealing 50% of modded
base as Gas damage each second for 6 s, no first-tick delay, stacking up to 10
times (radius +0.3 m per stack, cap 6 m); each stack has its own timer and the
cloud persists for its duration even if the host dies.

| Update | Date | Gas change |
| --- | --- | --- |
| 11.0 | 2013-11-20 | Gas damage/status introduced. |
| 26.0 (Old Blood) | 2019-10-31 | Status 2.0 rework establishes the modern stacking DoT framework; Gas keeps the 50%-of-base cloud tick and per-instance stack cap. |
| **27.2** | **2020-03-05** | **Mechanical rework:** the cloud no longer applies a forced Poison (Toxin) proc to enemies in its radius; it now deals direct **Gas DoT** in the AoE. Base duration set to 6 s to match Slash. Same patch removed the 0.25x elemental status weight, making all elemental procs 4x more likely (this is the patch that reshaped proc weighting, not 36.0). |
| 27.3 | 2020-03-24 | Cloud keeps ticking for the average remaining duration after the host dies; AoE radius now explicitly grows per stack to the 10-stack max; Toxic Ancient auras no longer resist Gas. |
| 33.5 | 2023-06-21 | Crash fix only (Enemy Radar + Gas weapons). |
| **36.0 (Jade Shadows)** | **2024-06-18** | **No damage numbers changed.** Readability/VFX rework (volume, particles, per-target VFX, radius outline, reduced self-obscuration). Deimos Infested become Gas-vulnerable under the simplified faction-resistance/health-type rework. The wider status rework (duplicate stacking rules, Blast rework, players limited to one stack) applies to Gas too. |
| 37.0 | 2024-10-02 | Fixed the radial bubble VFX vanishing at 10 stacks; it now disappears only after all stacks expire. |
| 38.5 | 2025-03-19 | Fixed Gas Status Effect VFX not showing. |

Practical takeaways:

1. The big behavioral break is **27.2**, not 36.0 — pre-27.2 Gas spread
   Toxin procs; post-27.2 Gas is its own Gas-typed AoE DoT and cannot be
   buffed by Heat/Toxin mods, only by literal Gas bonuses (Leaded Gas,
   Valence Formation).
2. Update 36.0 was visuals plus the faction/health simplification; any guide
   claiming a 36.0 Gas damage rework is conflating it with 27.2.
3. As of the Oct 2026 wiki revision there have been no further Gas mechanics
   changes after 38.5.

---

## 6. Code reference

`modules/status_damage.py` implements these formulas without any game-data
dependency:

- `modded_base_damage()` — proc seed (base/faction only)
- `proc_tick_damage()` plus `slash_tick/heat_tick/toxin_tick/electricity_tick/gas_tick`
  — `(sum(S)+1) x C x M` form in Python binary64, with `accumulator=False`
  for the simplified per-type-page form
- `total_ticks()` / `damaging_ticks()` — tick counting including the empty
  final AoE tick
- `proc_type_chances()`, `average_procs_per_shot()`,
  `average_procs_per_second()`, `beam_merged_status_chance()`
- `wiki_quantized_damage()` — the 1/32 direct-hit quantization
- `modules/crit.py` — critical chance/damage formulas: relative and absolute
  bonuses, the 12-bit base critical-multiplier quantization, Cold's
  critical-damage bonus, critical tiers, normal/critical/average shot,
  direct + AoE sum and the weak-point form
- `STATUS_PROCS` — coefficient/timing/stack reference table
