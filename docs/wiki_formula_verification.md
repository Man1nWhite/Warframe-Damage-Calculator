# Wiki verification of every formula family

Checked against the English **WARFRAME Wiki** on **2026-10-28** by reading the
pages' raw wikitext through the wiki's own API
(`https://wiki.warframe.com/api.php?action=parse&page=<PAGE>&prop=wikitext`),
so the text below the rendered article was reviewed as well. This file records
*what* the wiki says, *where* the repository implements it, and whether the two
agree. It is an audit trail, not a claim that the models match the game:
nothing here was measured in-game, and several wiki pages carry "actively being
worked on" banners.

Companion documents:

- [`formula_audit.md`](formula_audit.md) — scope limits, source conflicts and
  the history of earlier corrections.
- [`damage_formula_reference.md`](damage_formula_reference.md) — the formulas
  themselves in reference form.

Pages read directly in this pass (retrieved 2026-10-28):

`Damage/Calculation` · `Damage/Overview_Table` · `Damage_over_Time` ·
`Status_Effect` · `Critical_Hit` · `Armor` · `Enemy_Level_Scaling` ·
`Overguard` · `Multishot` · `Damage/Heat_Damage` · `Damage/Puncture_Damage` ·
`Damage/Cold_Damage` · `Damage/Blast_Damage` · `Damage/Corrosive_Damage` ·
`Damage/Gas_Damage` · `Damage/Magnetic_Damage` · `Damage/Viral_Damage` ·
`Damage/Impact_Damage` · `Damage/Slash_Damage` · `Damage/Toxin_Damage` ·
`Damage/Electricity_Damage` · `Damage/Radiation_Damage` ·
`Condition_Overload_(Mechanic)` · `Secondary_Enervate` · `Cascadia_Flare` ·
`Sentient_Surge` · `Kuva_Nukor` · `Ocucor` · `Akarius_Prime` ·
`MediaWiki:Gadget-enemyinfoboxslider.js`.

A second pass on the same day re-read `Damage/Calculation`, `Armor`,
`Enemy_Level_Scaling`, `Critical_Hit`, `Multishot`, `Cascadia_Flare` and the
lead ("DAMAGE EFFICACY") quote of all thirteen damage-type pages. The
fourteen-faction matrix in `modules/constants.py` was rebuilt cell by cell from
those per-type quotes and matches every non-neutral entry; the wiki's own
overview table is malformed wikitext (its resistance markers fall on row-
separator lines), which is why the per-type quotes are the reference here.

Pages carried over from the 2026-10-27 audit and the existing pinned tests,
not re-read here: `Riven_Mods`, `Damage/Grineer`, `Alternox_Prime`, `Melee`,
`Seismic_Wave`, `Melee_Afflictions`, `Primed_Target_Cracker`. Their rows below
say "match" because the tests cited in section 5 pin the numbers, not because
the page was re-read today.

---

## 1. Formula inventory

Verdicts: **match** — the code reproduces the documented expression;
**match (documented deviation)** — the code states and documents a deliberate
difference; **fixed this pass** — the code was changed to follow the wiki;
**not implemented** — documented gap.

### 1.1 Direct hit

| Formula | Wiki | Code | Verdict |
| --- | --- | --- | --- |
| `Modded Stat = Base × (1 + bonuses)` | Damage/Calculation | `modules/calculator.py` | match |
| `Modded Time = Base Time / (1 + speed bonuses)` | Damage/Calculation | docs only | not implemented (no time stats in the UI) |
| Arsenal total damage incl. physical shares and innate multishot, excluding faction bonus | Damage/Calculation | `DamageCalculator.calculate`, `hud_total` | match (only innate multishot is supported) |
| Quantization `sign(x)·⌊abs(x)·32+0.5⌋/32` on modded base damage | Damage/Calculation | `status_damage.wiki_quantized_damage` | match |
| Faction/type table after quantization, no display rounding | Damage/Calculation | `_build_armor_modifiers`, `final_damage_by_type` | match |
| Unarmored `Inflicted = Starting × (1 + health modifier)` | Damage/Calculation | `route_enemy_hit` / `calculator` | match |
| Armor DR: `0.9·√(armor/2700)` at ≤2700, `armor/(armor+300)` above | Armor | `enemy_scaling.enemy_armor_damage_reduction` | match |
| Minimum 1 damage per type reduced by armor | Armor | `calculator.calculate`, `damage_routing.route_enemy_hit` | match (Jat slam-count scalar model keeps the documented exception) |
| Toxin bypasses shields; Treasurer/Hounds excepted | Damage/Calculation | n/a (shields not modeled) | not implemented |
| Average/normal/critical shot, AoE direct+radial sum, weak point | Damage/Calculation | `modules/crit.py` | fixed this pass (new module) |
| Critical tiers `1 + tier × (CDM − 1)`; `floor`/`ceil` split above 100% | Damage/Calculation | `modules/crit.py`, simulators | match |
| 12-bit base critical-damage quantization | Critical_Hit | `modules/crit.py`, six simulators | fixed this pass |
| Relative vs absolute critical-chance bonuses | Critical_Hit | `modules/crit.py` | fixed this pass (documented; sims use the formulas) |
| Burst/sustained/charge/burst-trigger DPS and lifetime damage | Damage/Calculation | docs only | not implemented |

### 1.2 Status chance and proc selection

| Formula | Wiki | Code | Verdict |
| --- | --- | --- | --- |
| `Proc Type Chance = Type damage / Total damage` | Status_Effect | `status_damage.proc_type_chances` | match |
| No separate physical/elemental weighting (since 27.2) | Status_Effect | same | match |
| >100% status: whole numbers guaranteed, fraction rolls once, independently drawn | Status_Effect | simulators (`floor` + fractional roll) | match |
| Multishot adds rolls, never changes per-projectile chance | Multishot | `average_procs_per_shot` | match |
| Fired projectiles: `floor(multishot)` + fractional extra roll | Multishot | `kuva_nukor_sim.roll_multishot` | match |
| Beams merging on one target: damage **and** status chance sum, crit chance stays single | Multishot | `beam_merged_status_chance`, all beam sims | match |
| Forced procs applied after the merge, not multiplied by multishot | Multishot | docs (`status_damage` docstring) | match (no forced-proc source in the bundled builds) |
| Status immunities remove a type and renormalize | Status_Effect | docs only | not implemented |

### 1.3 Damage over time

| Formula | Wiki | Code | Verdict |
| --- | --- | --- | --- |
| Tick = `(Σ Sᵢ + 1) × C × M`, single shared accumulator per tick group | Damage/Calculation | `status_damage.proc_tick_damage` | match |
| `C = 0.35` Slash, `0.5` Heat/Toxin/Electricity/Gas | Damage_over_Time, per-type pages | `status_damage` constants | match |
| 6 s duration, 1 tick/s, 1 s delay for Slash/Heat/Toxin, none for Electricity/Gas | Damage_over_Time | `STATUS_PROCS` | match (pinned in tests) |
| Electricity/Gas final pulse at 6 s deals no damage | Damage_over_Time | `damaging_ticks(last_tick_empty=True)` | match |
| `Total Ticks = ⌊rate × (duration − delay)⌋ + 1` | Damage_over_Time | `total_ticks` | match |
| DoT ticks bypass 1/32 quantization | Damage/Calculation | docstring + usage | match |
| Faction bonus inside the seed **and** again as a multiplier | Damage/Calculation, per-type pages | `modded_base_damage` + `proc_tick_damage(faction_bonus=…)` | match |
| Literal-element bonus only (Heat for Ignite, Gas for Gas Cloud, none for Slash) | per-type pages | `slash_tick`, `heat_tick`, `gas_tick` | match |
| Blast is a 1.5 s fuse, 30% single-target, 300% per stack radial at 10 stacks/death, target excluded from the radial | Damage/Blast_Damage | `kuva_nukor_sim` (`BLAST_*`), `alternox_prime_sim` | match |
| Blast detonations are "Status Damage" (Elementalist applies) | Status_Effect | sims pass `status_damage_bonus` | match |
| Bosses and some Eximus detonate Blast at 4 stacks, everyone else at 10 | Damage/Blast_Damage | `status_damage.BLAST_MAX_STACKS_BOSS`, `DummyTarget.blast_cap_reached` | match (opt-in per target: `boss=True`) |
| A dying target detonates every Blast stack, and a killing blow that inflicts at least one Blast proc still explodes | Damage/Blast_Damage | `kuva_nukor_sim.simulate_room` (`record_deaths`, `record_killing_blow_blast`) | match (room model; the single-target models have no other target to hit) |
| A Blast stack that expires on its own (1.5 s) deals `max(1, 0.3 × H)`; detonation at the cap settles every stack instead | Damage/Calculation, Damage/Blast_Damage | `detonate_expired_blasts` in the three Blast simulators | fixed this pass (floor added) |
| Gas cloud 3 m, +0.3 m per stack to 6 m at 10 stacks, 10-instance cap | Damage/Gas_Damage | constants only (`GAS_MAX_STACKS`) | partly implemented (radius growth is not simulated) |
| Heat consolidates stacks into one pulse, refreshes all durations, strip does not accelerate | Damage/Heat_Damage | `DummyTarget.add_heat`, `consume_heat_tick` | match |
| Heat strip 15/30/40/50% every 0.5 s, restore 50/40/30/15/0% every 1.5 s | Damage/Heat_Damage | `_heat_strip_fraction`, `current_armor` | match |
| Corrosive `1 − (0.20 + 0.06·stacks)`, 8 s, capped at 10 stacks | Damage/Corrosive_Damage | `akarius_sim.corrosive_armor_factor` | match |
| Corrosive strip is **multiplicative** with Heat strip and Corrosive Projection: `(1 − 50%)·[1 − (20% + 6%·n)]·(1 − 18%·projections)` | Damage/Corrosive_Damage | `JatTarget.current_armor` (heat ramp × `corrosive_armor_factor`); Corrosive Projection is in no bundled build | match |
| Puncture 10 s, 5 stacks, +5 flat critical chance per stack (max +25%), not on AoE | Damage/Puncture_Damage | `DummyTarget.add_puncture` | match |
| Puncture's flat critical chance only matters where a build actually deals Puncture: the Jat Kittag slam build is Blast + Gas + Toxin and rolls no Puncture procs, so `jat_kittag_sim` needs no term for it | Damage/Puncture_Damage | `ocucor_sim`, `kuva_nukor_sim` (`add_puncture`) | match (n/a for the slam build) |
| Cold +0.10x critical damage, +0.05x per stack, +1.0x frozen, 4-stack cap under Overguard | Damage/Cold_Damage | `crit.cold_crit_damage_bonus`, `DummyTarget.add_cold` / `crit_damage_multiplier` | match (every simulator now reads the target's Cold stacks when it builds a crit factor) |
| Viral/Magnetic `2 + 0.25·(stacks − 1)`, 10-stack cap | Damage/Viral_Damage, /Magnetic_Damage | `damage_routing.status_vulnerability` | match |
| Magnetic break: 3% of max defense per stack over 6 s; Status Damage and faction twice, Electricity once | Damage/Magnetic_Damage | `status_damage.magnetic_break_electric_tick` | match |
| DoT ticks are amplified by live Viral, not double-dipped | Damage/Viral_Damage | `damage_routing` (applies Viral once to health) | match |

### 1.4 Enemies

| Formula | Wiki | Code | Verdict |
| --- | --- | --- | --- |
| Health curves `1 + C·q^E` with smoothstep between `q = 70…80` | Enemy_Level_Scaling | `enemy_scaling` curves | match |
| Grineer health 0.015/2.12 → 10.7332/0.72 | Enemy_Level_Scaling | `GRINEER_HEALTH` | match |
| Armor 0.005/1.75 → 0.4/0.75, floor 200, cap 2700 | Enemy_Level_Scaling, Armor | `GRINEER_ARMOR`, `scale_enemy` | match |
| Shield curves per faction (Corpus/Amalgam, Orokin/Anarchs, Grineer/Sentient, Techrot) | Enemy_Level_Scaling | `SHIELD_CURVES` | match |
| Eximus base-health piecewise scaler (0.25 armored / 0.375 flesh) and `max(base·1.1, …)` | Enemy_Level_Scaling | `eximus_base_health` | match |
| Eximus base shield scaler | Enemy_Level_Scaling | `eximus_base_shields` | match |
| Steel Path ×2.5 health/shields, Empowered `2 + 0.5·players`, Icebind `3 + players` | Enemy_Level_Scaling | `scale_enemy` | match |
| Grineer/Techrot/Corpus damage curve with ×2 faction factor | Enemy_Level_Scaling | `GRINEER_DAMAGE` | match |
| `EHP = health/(1 − DR) + shields (+ Overguard)` | Armor | `ScaledEnemy.ehp` | match |
| Overguard `q = level − 1` | Enemy_Level_Scaling | `enemy_scaling` uses `level − base_level` | match (documented deviation: the infobox gadget uses `level − base_level`, and that gadget is the chosen reference) |
| Overguard neutral to every type except Void ×1.5, no armor DR, no enemy invulnerability gate | Overguard | `damage_routing` | match (faction type modifiers now skip the Overguard layer) |
| `f32` intermediate arithmetic for scaled stats | Enemy_Level_Scaling | Python binary64 + 2-decimal rounding | documented deviation |

### 1.5 Mods, Rivens, arcanes

| Formula | Wiki | Code | Verdict |
| --- | --- | --- | --- |
| Slot-order elemental combination, repeated elements keep their first position | Damage (elemental modding) | `mod_engine.ModAggregator`, `calculator._resolve_elements` | match (verified by the wiki's Nagantaka Prime example) |
| Riven primary-element ordering uses the last listed primary stat | Riven_Mods | `mod_engine.ordered_mod_effects` | match |
| Riven value `tag × (1.5·dispo·10) × 1.25^neg × grade × layout × (rank+1)` | Riven_Mods | `riven.py` | match (pinned by `tests/test_riven_wiki.py`) |
| Riven rank-8 layout weights 0.99 / 1.2375 / 0.75 / 0.9375 and malus columns | Riven_Mods | `riven.NUM_BUFFS_ATTEN`, `NUM_BUFFS_CURSE_ATTEN` | match |
| Positive-only / negative-only traits | Riven_Mods, Melee_Combo | `riven._POSITIVE_ONLY_TAGS`, `_NEGATIVE_ONLY_TAGS` | match |
| Condition Overload additive/multiplicative/no-effect behaviors and per-status values | Condition_Overload_(Mechanic) | `condition_overload.apply_co`, `source/gunco_mechanic.json` | match |
| Galvanized Shot +40% per status up to +120% per type | Condition_Overload_(Mechanic) | sims (`GALV_SHOT_*`) | match |
| Secondary Enervate +10% absolute crit per stack, 6-big-crit reset, closed-form AFCC | Secondary_Enervate | `kuva_nukor_sim.enervate_afcc` | match (pinned) |
| Cascadia Flare +12% per stack, 40 stacks (+480%), additive with base-damage mods | Cascadia_Flare | `ocucor_sim.FLARE_*`, `_scaled_type_damage` bracket | match |
| Flare: **one stack per damage instance** (multishot / Archon Vitality procs do not multiply it), fatal Heat instances still stack, one expiry wipes all stacks | Cascadia_Flare | `ocucor_sim` `heat_this_tick` flag, `flare_expiries` | match (pinned by `tests/test_ocucor_sim.py::test_one_flare_stack_per_damage_instance`) |
| Sentient Surge +60% crit/status per tendril, 4 tendrils | Sentient_Surge | `ocucor_sim.SURGE_*` | match |
| Primed Target Cracker +110% | Primed_Target_Cracker | simulators | match (corrected earlier) |

### 1.6 Weapon mechanics baked into the simulators

| Mechanic | Wiki | Code | Verdict |
| --- | --- | --- | --- |
| Continuous weapons: tick = 1/fire rate, 0.5 ammo/tick, ramp then decay | Kuva_Nukor, Ocucor, Continuous_Weapon | sims | match |
| Nukor ramp 30%→100% over 0.6 s, decay after 0.8 s over 2 s | Kuva_Nukor | `RAMP_START`, `RAMP_TIME` | match |
| Ocucor ramp 20%→100% over 0.6 s; 4 tendrils; reset on reload/empty mag | Ocucor | `ocucor_sim` | match |
| Nukor chains 2 enemies within 9 m at 50% | Kuva_Nukor | room simulation | match |
| Akarius Prime: 68 Impact + 509 Blast, 7.8 m radial, 100→30% falloff, separate status for impact/explosion, 2-round burst | Akarius_Prime | `akarius_sim` | match (falloff/headshot modeling is simplified) |
| Alternox Prime: 75 Electricity, 5.33 fire rate, 20% crit, 2.2x, 40% status | Alternox_Prime | `alternox_prime_sim` | match |

---

## 2. Worked examples re-checked numerically

1. **Quantization** — `Damage/Calculation` gives Nagantaka Prime: 173 base,
   Puncture 15.57 with +120%, Slash 155.7, Viral 259.5 (90% + 60% of 173),
   Heat 156.78125, Gas 346, total 951.5. `tests/test_damage_formulas.py`
   reproduces every type value, and `tests/test_status_damage.py` pins the
   1/32 rule directly.
2. **DoT ticks** — `(40 + 1) × 0.5 × 1.6 = 32.8`, `(40 + 1) × 0.5 × 2.5 = 51.25`,
   `(40 × 1.55 + 1) × 0.5 × 3.25 × 1.55 = 158.68125` and the nine-seed
   consolidated example are pinned in `tests/test_status_damage.py`.
3. **Critical damage quantization** — `Code(1.6 + 0.4) = 256`, decoded
   `256 × 32/4095 = 2.0004884`. Pinned in `tests/test_crit_wiki.py`.
   Consequence for the bundled builds: Kuva Nukor 5.0 → 5.001221, Ocucor
   1.8 → 1.797314, Akarius 2.0 → 2.000488, Alternox 2.2 → 2.203663,
   Jat Kittag 2.0 → 2.000488.
4. **Cold** — Kunai with Primed Target Cracker at 9 Cold stacks:
   `1.6 × (1 + 110%) + 0.50 = 3.86`; Paris Prime at 112.5% crit:
   tier 1 → 2.5x, tier 2 → 4x.
5. **Faction table** — every non-neutral cell of `Damage/Overview_Table`
   matches `modules/constants.py` (14 factions; `+` = ×1.5, `−` = ×0.5).
6. **Armor** — `0.9·√(2700/2700) = 90%` at the cap; `2700/(2700+300) = 90%`
   only coincides at the cap, so the exceptional branch is exercised with
   larger armour in `tests/test_enemy_scaling.py`.
7. **Enemy scaling** — the infobox gadget's `trans()` helper and Overguard
   curve (`1 + 0.0015·q⁴` / `1 + 260·q^0.9`) were read from the live
   `MediaWiki:Gadget-enemyinfoboxslider.js`; `enemy_scaling` ports them
   term-for-term.
8. **Secondary Enervate** — `AFCC(x)` piecewise branches and the
   30-triggers-per-second caveat are pinned in `tests/test_wiki_cross_checks.py`.
9. **Quantization end to end** — the Nagantaka Prime example now runs through
   `DamageCalculator` itself (Cryo Rounds, Malignant Force, Hellfire, Piercing
   Caliber, 200% Gas Valence Formation): Puncture 32.4375, Slash 156.78125,
   Viral 259.5, Heat 156.78125, Gas 346, total **951.5**, with the 1.73
   Impact quantized to 0. Pinned in `tests/test_crit_wiki.py`.
10. **Critical tiers** — the `Critical_Hit` table (0/100/200/300/400/500%)
    is reproduced by `crit_tiers`, the tier multiplier by
    `crit_multiplier_for_tier` (`1 + tier × (CDM − 1)`), the Lenz/Vital Sense
    orange crit as `1 + 2 × (4.4 − 1) = 7.8`, and the Paris average multiplier
    as `1 + 0.75 × (4.4 − 1) = 3.55`.

---

## 3. Changed in this pass

1. **New `modules/crit.py`** implementing the `Critical_Hit` expressions that
   the repository previously only described in prose: modded critical chance
   (relative + absolute), the 12-bit base critical-damage quantization,
   cold's critical-damage bonus, critical tiers, normal/critical/average shot,
   direct + AoE sum and the weak-point form.
2. **Base critical multiplier is now quantized** in all six damage models
   (`kuva_nukor_sim`, `ocucor_sim`, `akarius_sim`, `alternox_prime_sim`,
   `jat_kittag_sim`, `jat_kittag_slam_analysis`). Changes are small
   (≤0.2%) but the wiki's quantization section is explicit that the stored
   base value is the decoded 12-bit code.
3. **New tests** — `tests/test_crit_wiki.py` (26 tests covering the
   critical-hit page) and `tests/test_wiki_cross_checks.py` (24 tests
   pinning the proc-timing, Blast, Corrosive, Heat-strip, Magnetic-break,
   Viral/Magnetic, multishot and Enervate constants to the pages cited above).
4. **Pinned expectations updated** where they encoded an unquantized base
   critical multiplier; the assertions now read
   `quantize_crit_multiplier(…) × bonus` so the derivation stays visible.
5. **One new test, no code change:** `tests/test_ocucor_sim.py`
   `test_one_flare_stack_per_damage_instance` pins Cascadia Flare's
   one-stack-per-hit rule with a forced multi-Heat roll. `ocucor_sim` already
   enforced it (`heat_this_tick`), so only the regression guard is new.
6. **Blast stack expiry floor.** An expiring stack now deals the wiki's
   `max(1, 0.3 × H)` in `kuva_nukor_sim`, `akarius_sim` and
   `alternox_prime_sim`. The floor is unreachable for the bundled builds
   (seeds are hundreds of damage) but it is part of the published formula.
7. **`tests/test_crit_wiki.py`** grew from 22 to 26 tests: the Nagantaka
   Prime example now runs through `DamageCalculator` itself (per-type values,
   the 951.5 total and the unquantized arsenal display) and an extra test pins
   the `32/4095` spacing between adjacent codes.
8. **Docstring correction.** `modules/crit.py` said the decoded code-256
   multiplier was `2.0002442`; it is `2.0004884` (`8192 / 4095`).

No other formula changed: every other checked item already agreed with the
wiki, or differs in a way that is recorded in the next section.

---

## 4. Deviations and unresolved source conflicts

These are deliberate, documented choices rather than silent errors. Each one is
a place where "follow the wiki" is not a single instruction.

1. **Overguard level input.** `Enemy_Level_Scaling` says Overguard uses
   `q = current level − 1`; the infobox gadget (re-read 2026-10-28) uses
   `current level − base level` like every other stat. `enemy_scaling` follows
   the gadget, so Eximus Overguard differs from the article's formula.
2. **DoT "Modded Damage" and multishot.** `Damage/Calculation` writes the DoT
   seed as `Modded Base × Modded Multishot × (1 + faction)`. The helpers expose
   the per-instance seed (`modded_base_damage`) and the beam simulators build
   their seeds from the merged tick, which already contains multishot; the
   scalar helpers therefore do not multiply multishot a second time.
3. **Faction type modifiers on Overguard (resolved).** `Overguard` says the
   layer is "neutral to all damage types except for a 50% vulnerability from
   Void damage". `route_enemy_hit` therefore applies the faction *type* table
   to the health layer only; the faction *damage* bonus of Bane-style mods is a
   separate multiplier that the simulators apply before routing and still
   reaches both layers. Earlier numbers in the comparison reports that assumed
   otherwise are marked as such where they are quoted.
4. **Overguard overflow split.** No reviewed page specifies what happens to a
   mixed damage instance that breaks Overguard. The model keeps the same
   fraction of every component for health and discards the Magnetic multiplier
   beyond the break.
5. **Blast stack caps for bosses/Eximus (modelled).** `DummyTarget` takes
   `boss=True`, which lowers the early-detonation threshold to four stacks
   (`BLAST_MAX_STACKS_BOSS`); every simulator asks the target for its cap. The
   wiki says *some* Eximus share the boss rule and does not say which, so the
   bundled reference targets stay at ten and the Akarius sensitivity runs the
   four-stack variant explicitly. A death detonates that target's Blast stacks,
   including a stack whose proc came from the killing blow itself; the radial
   damages the other targets, since Damage/Blast_Damage excludes the proc
   target from its own explosion.
6. **Cold critical damage (modelled).** `DummyTarget.crit_damage_multiplier`
   adds `crit.cold_crit_damage_bonus` to the build's Critical Damage before the
   tier, and every simulator builds its crit factor from it. No bundled build
   leaves Cold as a standalone proc (cold always merges into
   Viral/Blast/Magnetic), so the term is zero unless a target is primed with
   Cold, which the `COLD` branch in `alternox_prime_sim` and the Cold tests
   exercise. Freeze's bonus is deliberately not applied to the Akarius radial
   Blast instance, matching the wiki's AoE exclusion.
7. **Blast and Cold are excluded from AoE damage.** Cold's Freeze bonus is
   opted out of the Akarius radial Blast instance, but the simulators still
   apply weapon-wide multipliers to radial Blast damage. That is the same thing
   for a single-target radial and not for the penalty/benefit rules on AoE
   critical additions, which remain unmodelled.
8. **Heat inherit across sources** (first-proc Heat percentage and faction
   modifiers applying to later stacks) is only partially modeled: each
   simulator uses one weapon, so cross-source inheritance cannot occur.
9. **Binary32.** `Damage/Calculation`, `Enemy_Level_Scaling`, `Critical_Hit`
   and the Eximus tables specify binary32 ordering. Python uses binary64; the
   infobox parity is achieved by rounding health/shields to two decimals and
   flooring armour.
10. **Not implemented at all:** shields, enemy status immunities, stance
    multipliers, Follow Through, Melee Afflictions' immediate damage,
    Seismic Wave/Vulcan Blitz interactions, Gas radius growth, weapon
    alternate fires, radial falloff, hit registration/accuracy, and the
    Arsenal burst/sustained/lifetime DPS family. The desktop calculator still
    treats one export row as one non-critical hit.

---

## 5. Test map

| Area | File |
| --- | --- |
| Direct hit, quantization, elemental order, faction table | `tests/test_damage_formulas.py` |
| DoT tick formula, timing, proc weighting, beam merge | `tests/test_status_damage.py` |
| Critical hits, tiers, CDM quantization, Cold | `tests/test_crit_wiki.py` |
| Damage quantization reproduced end to end (Nagantaka Prime) | `tests/test_crit_wiki.py` |
| Proc timing, Blast (incl. the 4-stack boss cap), Cold/Freeze, Corrosive, Heat strip, Magnetic break, AFCC | `tests/test_wiki_cross_checks.py` |
| Enemy scaling and target dummies | `tests/test_enemy_scaling.py` |
| Riven value formula | `tests/test_riven_wiki.py`, `tests/test_riven.py` |
| Condition Overload behaviors | `tests/test_condition_overload.py` |
| Cascadia Flare stacking (one stack per hit, cap, expiry) | `tests/test_ocucor_sim.py`, `tests/test_ocucor_comparison.py` |
| Overguard/health routing, incl. faction type modifiers skipping Overguard | `tests/test_damage_routing.py` |
| Simulator invariants (crit, multishot, status, cutoffs) | `tests/test_*_sim*.py` |

Run everything offline with:

```bash
python -m unittest discover -s tests -q
```

Re-run the wiki side of this audit with `tools/wiki_audit.py`; it reads the
pages it names, extracts the numbers next to each claim's keyword and compares
them with the code value, and `--save-snapshot` / `--baseline` turn two runs
into a diff. README documents the modes and exit codes.

CI runs `python -m ruff check .` (the rule set in `ruff.toml`) and
`python -m mypy` (the `modules/` gate in `mypy.ini`) before the suite. All three
were run by hand for this pass and are clean.

---

## 6. Third pass, 2026-10-28 (evening): live re-read of the core pages

The pages below were fetched again from `wiki.warframe.com`
(`?action=raw`) **today** and compared expression by expression with the code.
This is a re-check of the audit above, not a new audit: where a page was read
only in part, the section says so, and everything not listed here still rests
on the 2026-10-27/28 passes or on the pins in `tests/`.

| Page (read today) | What was compared | Code | Verdict |
| --- | --- | --- | --- |
| `Critical_Hit` §Critical Chance | `Base × (1 + Relative) + Absolute` (Point Strike 150% + Argon Scope 135%; Avenger 45%) | `crit.modded_crit_chance` | match |
| `Critical_Hit` §Critical Damage | `Base × (1 + Relative) + Absolute`; Freeze and Tenacious Bond listed under *absolute* increases | `crit.modded_crit_multiplier` | match |
| `Critical_Hit` §Quantization | `Code(x) = ⌊clamp(x,0,32) × 4095/32 + 0.5⌋`, decoded `× 32/4095`, spacing `32/4095`, `Code(1.6+0.4)=256` | `crit.quantize_crit_multiplier`, all six models | match |
| `Critical_Hit` §Critical Tiers | 0/100/200/300/400/500% table; `1 + Tier × (Total CDM − 1)`; Lenz/Vital Sense orange = 7.8 | `crit.crit_tiers`, `crit.crit_multiplier_for_tier` | match |
| `Critical_Hit` §Critical Headshots | `Headshot Multi × (1 + Tier × (2 × Total CDM − 1))`; Lanka/Vital Sense example; heads only; 1.0x-headshot weapons excluded | `crit.headshot_crit_multiplier` | **added this pass** (was missing; no model yet calls it) |
| `Critical_Hit` §Average Damage | `1 + CC × (CDM − 1)`; Paris 30%/2.0 = 1.3, with Point Strike + Vital Sense = 3.55 | `crit.average_shot` | match |
| `Armor` §Enemy Damage Reduction | `90% × √(Net Armor / 2700)` at ≤2,700; `Net Armor / (Net Armor + 300)` above; minimum 1 damage per type | `enemy_scaling.enemy_armor_damage_reduction`, `calculator`, `route_enemy_hit` | match |
| `Damage/Calculation` §Quantization | scale, `Quantized(x) = sign(x)·⌊|x|·32+0.5⌋/32`, physical/elemental rules, "damage mods only multiply final quantized values" | `status_damage.wiki_quantized_damage`, `calculator` | match |
| `Damage/Calculation` §Adding Mods | Nagantaka Prime example: Puncture 32.4375, Slash 156.78125, Viral 259.5, Heat 156.78125, Gas 346, total 951.5, Impact 1.73 → 0 | pinned end to end in `tests/test_crit_wiki.py` | match |
| `Damage/Calculation` §Unarmored / §Armored | `ID = SD × (1 + HM)`; `DM = 1 − 0.9·√(AR/2700)`; shields unaffected by armor; Toxin bypasses shields except Treasurers/Hounds | `calculator`, `route_enemy_hit`; shields not modelled | match (shield cases documented as not implemented) |
| `Damage/Calculation` §Total Damage | Arsenal total = base × (1 + elemental + physical shares) × (1 + damage bonuses) × innate multishot; excludes faction damage | `DamageCalculator.calculate` / `hud_total` | match (only innate multishot supported) |
| `Damage/Calculation` §Average Shot | normal/critical/average shot forms | `crit.normal_shot`, `crit.critical_shot`, `crit.average_shot` | match |
| `Damage_over_Time` §Status Effects | 6 s for Slash/Heat/Toxin/Electricity/Gas; 1 s delay for Slash/Heat/Toxin; Electricity/Gas last tick empty; Blast 1.5 s fuse with a damaging tick; Blast cap 10 | `status_damage.STATUS_PROCS`, `total_ticks`, `damaging_ticks`, `BLAST_*` | match |
| `Damage_over_Time` §Calculating | `Total Ticks = ⌊rate × (duration − delay)⌋ + 1`; `Total = per-tick × ticks` | `status_damage.total_ticks` | match |
| `Multishot` §Continuous Weapons | beams merging on one target sum **damage and status chance**, crit chance stays single-beam; forced procs after the merge; fractional projectile = chance of one more | `beam_merged_status_chance`, `kuva_nukor_sim.roll_multishot`, `status_damage.average_procs_per_shot` | match |
| `Status_Effect` §Status Chance | >100% applies independent extra procs, the same type may roll twice; each target rolls its own proc | simulators (`floor` + one fractional roll) | match |
| `Status_Effect` §Damage Distribution | `Proc Type Chance = Damage ÷ Total Damage`, no separate physical/elemental weighting | `status_damage.proc_type_chances` | match |
| `Status_Effect` §Status Immunity | an immune proc type is removed and the rest renormalise | not implemented (no bundled immune target) | documented gap |
| `Condition_Overload_(Mechanic)` §Sources | CO +80%/status (melee), Galvanized Aptitude +40% ×2, Galvanized Shot +40% ×3, Savvy +40% ×2; sources stack additively | `condition_overload`, `GALV_SHOT_DAMAGE = 1.20`, `GALV_SHOT_STATUS = 0.80` | match |
| `Condition_Overload_(Mechanic)` §Application | multiplicative ("excellent") vs additive ("intended") vs none, per attack; radial AoE generally excluded | `condition_overload.MODE_MULTIPLY / MODE_ADD / MODE_NONE`, `source/gunco_mechanic.json` | match |

Deliberately **not** re-read today, so their rows in §1 still rest on the
earlier passes or on pinned tests: `Damage/Overview_Table` and the thirteen
damage-type pages (faction matrix and per-type coefficients),
`Riven_Mods` (only its challenges table was fetched — the attribute formula
was **not** re-verified in this pass), `Enemy_Level_Scaling`, `Overguard`,
`Secondary_Enervate`, `Cascadia_Flare`, `Sentient_Surge` and
`MediaWiki:Gadget-enemyinfoboxslider.js`.

Two things came out of this pass:

1. **One formula was missing rather than wrong.** `Critical_Hit`'s
   headshot-critical expression had no implementation; `Damage/Calculation`'s
   weak-point average (already implemented) is a different expression. It is
   now in `modules/crit.py` with the page's own worked example pinned, and it
   is documented as unused until a model actually fires at heads.
2. **No drift.** Every expression that was re-read still matches the code, so
   nothing in the pinned numbers changed. The accompanying optimisation pass
   is behaviour-neutral by construction and was verified with
   `tools/bench_models.py`: the complete trial records hash identically before
   and after (see [`optimization_review.md`](optimization_review.md)).
