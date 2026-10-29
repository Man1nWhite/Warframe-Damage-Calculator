# Verglas Prime: Crit Pair vs Heat Slots Against Dummy A

**Experimental simulation, not an in-game measurement or a definitive build ranking.**
The weapon and mechanic references were reviewed against the English WARFRAME
Wiki on 28–29 October 2026. Results below were regenerated after the Magnetic
Electricity and Fired Up corrections; they replace the earlier figures.

Code: [`modules/verglas_prime_sim.py`](../modules/verglas_prime_sim.py), tests:
[`tests/test_verglas_prime_sim.py`](../tests/test_verglas_prime_sim.py).

## Short answer

For the specific level-150 Steel Path Eximus Heavy Gunner and assumptions
below, the current **Critical Delay + Vital Sense** pair has a 5.10 s median
TTK. **Hellfire + Thermite Rounds** has a 4.83 s median, and **Hellfire + Vile
Acceleration** has a 4.14 s median. The tested Heat/Viral build without
Magnetic takes 6.00 s. These are *model comparisons*, not measured in-game
results; the Magnetic-break approximation has a particularly large effect.

Earlier versions omitted High Voltage's +60% Electricity bonus from the
Magnetic-break Electricity proc. The simulator now includes it even though the
Electricity combines into Magnetic. It also counts eligible Heat and
Magnetic-break Electricity ticks from Verglas toward Fired Up. Custom loadouts
now receive Status Damage only when they actually equip it.

## Setup and loadouts

| Item | Assumption |
| --- | --- |
| Target | `steel_path_eximus_heavy_gunner(150)`: 1,716,837.41 health, 2,700 armor, 269,918.97 Overguard |
| Verglas Prime | 32 Cold, 14% crit at 2.20x, 36% status, 12.0 attacks/s, magazine 80, 1.60 s reload |
| Fired Up | Max rank, +5% Heat per hit, 20-stack cap, 5 s reset; eligible DoT ticks also count |
| Summoner's Wrath | +75% Companion damage, treated as faction-additive |
| Rifle Elementalist | +90% Status Damage and +0.6 m punch-through in the listed builds |
| Riven | Average 1.2-disposition Rifle values from [`source/riven_stats_average_1_2.csv`](../source/riven_stats_average_1_2.csv); uncursed |

The standard Riven is spliced **+Viral, +Multishot, +Critical Damage**.
Combined traits are absent from the vendored table and use the base-element
average as an approximation. A cursed Riven is rejected because the simulator
does not currently represent its negative trait. The `viral_heat` row instead
uses a +Heat, +Multishot, +Critical Damage Riven and Malignant Force in place
of High Voltage, producing Viral and Heat rather than Magnetic.

The common mods are Serration, Split Chamber, Rime Rounds, Rifle Elementalist
and the Riven. All but `viral_heat` also have High Voltage. Fired Up is on the
Sentinel, not a weapon slot. The `critical_delay_only` and `vital_sense_only`
rows deliberately leave a weapon slot empty for comparison; `final_recommended`
is the same loadout as `heat_primed_shred`.

| Key | Other weapon mods |
| --- | --- |
| `user_list_crit_pair` | Critical Delay + Vital Sense |
| `critical_delay_only` | Critical Delay |
| `vital_sense_only` | Vital Sense |
| `heat_pair` | Hellfire + Thermite Rounds |
| `heat_vital_sense` | Hellfire + Vital Sense |
| `heat_vile_acceleration` | Hellfire + Vile Acceleration |
| `heat_primed_shred` / `final_recommended` | Hellfire + Primed Shred |
| `viral_heat` | Malignant Force + Hellfire + Thermite Rounds; Heat Riven, no High Voltage |

The crit-pair build resolves to 2.71x multishot, 42% crit at about 7.228x,
79.2% status per beam, 9.60 attacks/s and 0.6 m punch-through. Fired Up adds a
standalone Heat group that ramps from 0 to 84.8 damage per beam.

## Results: 200 trials per row, seed 20261028

Times are seconds. Percentiles and damage components are calculated over
successful kills; there were no timeouts at the 600 s cap. Heat proc and
reload counts are medians. All final-armor medians were 1,350.

| Build | TTK median | p10 | p90 | Overguard break median | Heat procs | Reloads |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `heat_vile_acceleration` | 4.14 | 4.00 | 4.36 | 1.14 | 64 | 1 |
| `heat_primed_shred` | 4.34 | 4.08 | 4.61 | 1.34 | 63 | 1 |
| `final_recommended` | 4.34 | 4.08 | 4.61 | 1.34 | 63 | 1 |
| `heat_pair` | 4.83 | 4.25 | 5.00 | 1.92 | 68 | 0 |
| `heat_vital_sense` | 4.83 | 4.41 | 5.08 | 1.75 | 45 | 0 |
| `user_list_crit_pair` | 5.10 | 4.56 | 5.56 | 1.56 | 22 | 0 |
| `vital_sense_only` | 5.42 | 4.92 | 5.84 | 2.00 | 31 | 0 |
| `critical_delay_only` | 5.52 | 5.08 | 6.05 | 1.98 | 24 | 0 |
| `viral_heat` (no Magnetic) | 6.00 | 6.00 | 7.00 | 3.00 | 121 | 0 |

Health-damage attribution, **medians of the separate components**, rounded to
whole damage. The "direct + Heat" column is the sum of those medians, not the
median of their per-trial sum. Components can exceed remaining health because
the model records the full killing hit.

| Build | Direct | Heat DoT | Break Electricity | Direct + Heat |
| --- | ---: | ---: | ---: | ---: |
| `user_list_crit_pair` | 274,707 | 187,738 | 1,357,352 | 462,446 |
| `critical_delay_only` | 199,502 | 180,258 | 1,395,949 | 379,760 |
| `vital_sense_only` | 187,684 | 170,268 | 1,414,025 | 357,952 |
| `heat_pair` | 175,735 | 402,638 | 1,377,874 | 578,373 |
| `heat_vital_sense` | 200,272 | 301,425 | 1,357,352 | 501,697 |
| `heat_vile_acceleration` | 206,923 | 425,625 | 1,320,497 | 632,547 |
| `heat_primed_shred` / `final_recommended` | 231,608 | 368,487 | 1,342,610 | 600,095 |
| `viral_heat` | 199,813 | 1,883,364 | 0 | 2,083,177 |

The crit pair has the highest median direct damage among the Magnetic builds,
but the Heat builds generally accrue more Heat damage and/or break Overguard
sooner. The computed break Electricity contributes roughly 1.32–1.41 million
health damage in these Magnetic runs. It is a large **modeled** effect, not a
measurement of the game's behavior.

## Example build and alternatives

The earlier proposed eight-slot loadout remains a useful *candidate* to test:
Serration, Split Chamber, Rime Rounds, High Voltage, Hellfire, Primed Shred,
Rifle Elementalist, and the +Viral/+Multishot/+Critical Damage Riven, with
Fired Up on the Sentinel. It resolves to 18.60 attacks/s and 2.8 m
punch-through. Its median is 4.34 s (p10 4.08, p90 4.61) in this model.

Replacing Primed Shred with Vile Acceleration produces 4.14 s and 0.6 m
punch-through; replacing it with Thermite Rounds produces 4.83 s and 0.6 m.
A separate test replacing the Riven's Critical Damage with Punch Through in
the Vile Acceleration setup gives 4.40 s and 3.0 m (200 trials, same seeds).
These numbers do **not** include any extra targets: actual penetration depends
on target geometry and positioning, so neither a body count nor a Cordon damage
multiplier is guaranteed by this single-target simulation.

In a separate `heat_pair` test replacing the Viral Riven trait with Heat while
keeping Rime Rounds and High Voltage removes Viral from the resulting mix; the
median rises to 10.00 s (p10 9.00, p90 11.00). This is a model sensitivity, not
a universal recommendation.

## Limits

- The Magnetic page describes 3% of maximum defense **per stack over six
  seconds**, before modifiers. The model applies Status Damage and faction
  bonuses twice and Electricity bonuses once. Other sources describe break
  behavior differently, and mixed-hit Overguard overflow is an approximation.
  The large modeled burst makes the ordering especially sensitive to these
  assumptions; its magnitude and the ordering are not game-validated.
- Heat procs refresh together. The first-proc Heat-inheritance lock is not
  modeled; even with one weapon, Fired Up changes the Heat bonus over time, so
  whether that dynamic bonus should be inherited remains unverified here.
  Mixed-source Heat damage is not modeled accurately.
- Fired Up is assumed to add one stack before damage on each merged weapon
  hit, and one per eligible consolidated DoT pulse. The exact timing and
  grouping of those stacks have not been validated in game.
- Reloads, Heat and break-proc ticks are modeled; shields, accuracy, weak
  points, body parts, beam warm-up/decay, punch-through geometry and additional
  targets are not. `headroom_bodies` uses 1.2 m per body only as a rough
  heuristic; actual hitboxes vary.
- The listed builds have six-second base statuses. Custom Status Duration
  Riven positives scale Cold/Freeze, Viral, Magnetic, Heat duration and the
  Heat strip interval, as well as the break Electricity duration. Mixed-source
  Heat inheritance and durations are not modeled.
- Only Heat, Viral, Magnetic and Cold procs are supported. Unsupported proc
  mixes, impossible duplicate/incompatible weapon mods and cursed Rivens are
  rejected instead of silently yielding a complete-looking result. Other
  restrictions such as mod capacity are not checked.
- Cold's post-Freeze three stacks are given the freezing proc's remaining
  duration as an explicit approximation; the cited Wiki does not establish
  their precise individual expiry times.

## Reproducing

```bash
python -m unittest tests.test_verglas_prime_sim
python -m modules.verglas_prime_sim --trials 200 --seed 20261028
python -m modules.verglas_prime_sim --trials 200 --build heat_pair
```

Trial *i* uses `seed + i`. A single `--build` run also prints resolved elements,
stats and damage attribution. See the [formula audit](formula_audit.md) for
shared modeling assumptions.
