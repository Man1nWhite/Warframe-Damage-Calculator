# Jat Kittag: spliced Gas / Cold / Damage with Fever and Focus

**Reference date: 2026-10-28.** This is a Wiki-based analytical assessment,
not an in-game-validated time-to-kill or room-clear simulation. The requested
build drops **Primed Pressure Point**, not Vulcan Blitz. All three Galvanized
kill effects are assumed fully stacked, with no outside buffs, extra combo or
prior statuses. Melee Afflictions is rank 5 and occupies the separate arcane
slot. Real Riven rolls and negatives can change the results. A subsequent
[experimental slam-count comparison](jat_kittag_expected_slams.md) compares
this build with the user's Gas / Crit Damage / Crit Chance Riven plus Primed
Pressure Point, under explicitly uncertain Afflictions scenarios.

## Exact build and element order

This is **eight weapon mods** plus the arcane. One valid top-left-to-bottom-right
weapon-slot order is:

| Slot | Mod |
| ---: | --- |
| 1 | Seismic Wave |
| 2 | Galvanized Elementalist |
| 3 | Galvanized Reflex |
| 4 | Vulcan Blitz |
| 5 | Galvanized Steel |
| 6 | Focus Energy |
| 7 | Riven: **spliced Gas / Cold / Melee Damage** |
| 8 | Primed Fever Strike |

Slots 1–5 contain no primary elemental mods and can be reordered. Focus Energy
and the Riven can swap places, but **both must be before Fever** for this
particular combination. Their Electricity and Cold combine into Magnetic;
Fever's Toxin remains separate. Spliced Gas and Jat Kittag's innate heavy-slam
Blast stay independent. The result is:

> **Blast + Gas + Magnetic + Toxin.**

There is **no Viral, Corrosive or separate Electricity** in the modded hit.
A Magnetic shield/Overguard break can later create an Electricity status proc.
If Fever is first, different layouts produce different types: Fever → Riven →
Focus gives Blast + Gas + Viral + Electricity, while Fever → Focus → Riven
gives Blast + Gas + Corrosive + Cold. See the Wiki's
[element-order rules](https://wiki.warframe.com/w/Damage) and
[Riven Splicer](https://wiki.warframe.com/w/Riven_Splicer).

## What the build does

- **Spam:** Reflex + Focus Energy reaches the 90% Heavy Attack Efficiency
  cap. At full Reflex stacks, the model starts at 81.4 combo points (5×),
  retaining 73.26 after a heavy. With initial combo regenerating at 40/s, the
  first return to 80 takes 0.169 s; sustaining 5× repeatedly takes at least
  **0.20 s between slams**. This is an idealized continuous-time calculation,
  not a measurement of slam cadence, frame timing or combo gained from hits.
- **Crit:** 15% heavy-slam base crit and Galvanized Steel's doubled +110%
  give **48% crit chance**. With Steel fully stacked, crit multiplier is 4.4×
  and the ideal mean crit factor is 2.632×. There is no Crit Chance on this
  Riven and no hidden Primed Pressure Point in the calculation.
- **Riven Damage:** for a midpoint, rank-8 3-positive/1-negative Riven at the
  Wiki's normalized 1.20 multiplier, use **+185.3% Melee Damage**, +101.25%
  Cold, and +101.25% spliced Gas as examples. Its base damage bracket is
  2.853× without Primed Pressure Point, compared with 2.65× for Primed
  Pressure Point alone: about **7.7% higher**, before crit or other effects.
  This does not mean the entire build is 7.7% stronger than a different
  Crit-Riven build.
- **Gas + Toxin:** each can seed a damaging status. Literal +101.25% Gas gives
  a **2.0125× ordinary Gas-tick factor** with other inputs fixed; Fever's
  +165% Toxin gives a **2.65× ordinary Toxin-tick factor** with other inputs
  fixed. Gas hits an area, while Toxin damage and procs bypass shields but
  **not** Overguard or armor. See the Wiki's
  [Gas](https://wiki.warframe.com/w/Damage/Gas_Damage) and
  [Toxin](https://wiki.warframe.com/w/Damage/Toxin_Damage) formulas.
- **Vulcan Blitz:** a Jat kill can cause a separate death explosion; at max
  rank the Wiki lists 300 Blast plus 60% of the killed enemy's max health,
  with a 6 m radius, line-of-sight requirement and linear falloff. It is not
  included in any direct-hit or proc probability number below.
  [Source](https://wiki.warframe.com/w/Vulcan_Blitz).

## Status dilution on the first slam

With the example Riven, before quantization the relative damage weights are
Blast 1.000, Gas 1.0125, Magnetic 1.6125 and Toxin 1.650. Fully stacked
Galvanized Elementalist gives 220% status chance: two normal rolls guaranteed
and a 20% chance of a third. Using independent, unquantized damage-weighted
rolls, against a target with no prior statuses or immunity:

| Type | Share per normal roll | Chance of at least one on first slam |
| --- | ---: | ---: |
| Blast | 19.0% | 36.8% |
| Gas | 19.2% | **37.2%** |
| Magnetic | 30.6% | **54.7%** |
| Toxin | 31.3% | **55.7%** |

The chance of **both Gas and Toxin** among those normal rolls is about 15.0%;
Gas and Magnetic is 14.7%. The chance of Gas, Toxin **and** Magnetic together
is about 2.2%, since all three require the optional third normal roll. These
are not probabilities of an Afflictions trigger or a kill: prior statuses,
additional procs, immunity, engine rounding, the forced Lifted effect, the
Magnetic break proc and the arcane are excluded. Repeated hits and enemies
inside other Gas clouds change the situation.

## Magnetic and Melee Afflictions

A Magnetic status doubles subsequent damage to Shields/Overguard at its first
stack, increasing to 4.25× at ten. When a defense breaks **with Magnetic
stacks present**, the dedicated [Magnetic Wiki](https://wiki.warframe.com/w/Damage/Magnetic_Damage)
describes an Electricity proc based on **3% of maximum defense per stack**, up
to a 30% base total, over six seconds—not 3% per tick. Its first Electricity
tick is immediate. The first-slam Magnetic probability above is not the chance
that a defense break already has Magnetic stacks.

The same Wiki page says that the source's Status Damage bonus applies twice
and its Electricity mod bonus applies once even if combined. If **this Jat**
applied the Magnetic, following that page gives the conditional nominal total:

`3% × stacks × (1 + 0.80)^2 × (1 + 0.60) = 15.552% × stacks`

That is **15.55% of maximum defense over six seconds for one stack**, or
**155.52% at ten**, before target mitigation and other effects. The +80% is
Galvanized Elementalist and +60% is Focus Energy. The Wiki says ordinary base
damage mods do not affect this special max-defense-based proc, so the Riven's
+Damage is **not** a multiplier on this particular effect. The example is a
Wiki-derived approximation, not guaranteed health damage or an instant hit;
stack source, break timing, gates, armor, faction effects and other statuses
matter. The special proc's full mechanics are not independently validated.

Enemy Overguard can receive damage statuses but prevents the Lifted trigger
while it remains; once a target is eligible, the Wiki says the triggering hit's
statuses can be replicated by [Melee Afflictions](https://wiki.warframe.com/w/Melee_Afflictions).
Gas and Toxin together offer two damaging types for its re-seeding mechanic,
and a Magnetic-break Electricity proc may supply another for a later eligible
trigger. The Wiki page is marked for update and Jat/Blast reports conflict, so
neither a particular stack count nor the exact resulting damage is guaranteed.
The +Gas factor above is for an **ordinary** proc, not a proven multiplier for
all Afflictions-created stacks.

For the user's asserted gate behavior, do not assume excess damage from a
breaking hit reaches health. The Wiki explicitly distinguishes the player's
Overguard invulnerability gate from enemy Overguard, and mixed-hit overflow is
not settled here. Neither gate routing nor the Electric proc's damage to nearby
enemies is simulated by the direct comparison.

## Comparing choices, without claiming a TTK

### Riven +Damage versus +Crit Chance in these same eight slots

Keep all other stats and mods as requested; do **not** secretly put Primed
Pressure Point back into either variant. With the midpoint example values and
no external buffs:

| Third Riven positive | Base-damage bracket | Heavy crit | Mean crit factor | Neutral direct hit |
| --- | ---: | ---: | ---: | ---: |
| **+Melee Damage** | 2.853× | 48% | 2.632× | **1.599×** |
| +Crit Chance | 1.000× | 108.75% | 4.6975× | 1.000× |

Thus **+Damage is a strong choice when it replaces the missing Pressure Point**:
in this simplified no-buff comparison it gives about **60% more mean direct
hit**, and the normal Gas/Toxin proc-seed comparison follows the same factors
before rounding. Proc type shares are unchanged. This is not a prediction of
Afflictions damage, Magnetic-break Electricity, Vulcan Blitz or total TTK.
Additional melee-damage buffs and flat critical bonuses can change the result.

### Versus the prior Gas / Efficiency / Crit Riven with Fever

The earlier build kept Primed Pressure Point and used Fever + a spliced
Gas / Heavy Attack Efficiency / Crit Chance Riven; it had Blast + Gas +
Toxin, **no Magnetic**, and also reached 90% efficiency. For one unprimed
first slam at equal 5× combo and midpoint Riven rolls:

| Metric | Earlier Gas / Efficiency / Crit | Requested Gas / Cold / Damage |
| --- | ---: | ---: |
| P(Gas) | 50.5% | 37.2% |
| P(Toxin) | 72.5% | 55.7% |
| P(Gas and Toxin) | 29.4% | 15.0% |
| P(Magnetic) | 0% | 54.7% |
| Mean neutral direct-hit damage | 1.000× | 0.871× |

The requested build trades some normal Gas/Toxin probability and neutral
crit-driven direct damage for **Magnetic**, an Electricity proc on eligible
defense breaks, and retained Toxin shield bypass. It can be attractive against
shielded and Overguarded crowds; against unshielded non-Eximus targets,
Magnetic status itself offers no shield/Overguard benefit. This build also has
**no inherent Viral or armor strip**. An external primer can supply those, but
is not assumed or calculated here. Neither the direct table nor the status
rolls establish which build clears a room faster.

## Reproduction and limits

```sh
.venv/bin/python -m modules.jat_kittag_slam_analysis
.venv/bin/python -m unittest discover -s tests -p 'test_jat_kittag_slam_analysis.py'
```

The requested candidate is `focus_fever_gas_cold_damage`; its same-slot Crit
comparison is `focus_fever_gas_cold_cc`. Tests check all eight slots, the
absence of Pressure Point, element order through the project's calculator,
status probability inclusion–exclusion, combo recovery and the conditional
Wiki-based Magnetic-break formula. Neither tests nor these estimates model
full Afflictions re-seeding, Blast detonations, Gas-cloud overlap, Vulcan Blitz,
enemy defenses, exact gates, target movement or measured player cadence.
See the [broader Jat comparison](jat_kittag_slam_spam_comparison.md) and
[formula audit](formula_audit.md) for additional caveats and sources.
