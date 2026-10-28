# Jat Kittag heavy-slam spam: efficiency, Gas and Rivens

**Reference date: 2026-10-28.** This is an analytical comparison, **not an
in-game-validated damage-per-second or time-to-kill ranking**. The old
[Jat simulation report](jat_kittag_heavy_slam_sim.md) is invalid for choosing
between these builds: it omits important Blast, area damage and Melee
Afflictions interactions. The calculations here deliberately restrict their
numerical claims to combo recovery, idealized status rolls and direct slam
damage before defenses. They do **not** use that simulator's TTKs.

## Recommendations

1. **No Riven, fast all-round spam: keep Primed Fever Strike and add Focus
   Energy.** With full Galvanized Reflex stacks it caps Heavy Attack Efficiency
   at 90%; the modded damage types are **Blast + Corrosive**, not Toxin. It is
   a particularly reasonable choice against armored Grineer. Corrosive's armor
   reduction and faction bonus are useful, but it does not bypass shields. Its
   Afflictions replication is less certain than a build with a damaging DoT:
   sources disagree about whether Blast alone is sufficient.
2. **Shield-heavy enemies: Primed Fever Strike + Focus Radon** also caps
   efficiency. It gives **Blast + Toxin + Radiation**; [Toxin](https://wiki.warframe.com/w/Damage/Toxin_Damage)
   bypasses shields, though not armor or Overguard. It retains a damaging Toxin
   status for Afflictions. It is not automatically better against armored targets.
3. **For Gas without a Riven, Primed Fever Strike + Volcanic Edge** gives
   Blast + Gas and abundant status, but only 50% efficiency. This is a real
   tradeoff for rapid spam. For an ordinary, non-spliced Riven there are two
   90%-efficiency options: keep Fever Strike and roll **Heat / Heavy Attack
   Efficiency / Critical Chance**, or replace Fever Strike with Volcanic Edge
   and roll **Toxin / Heavy Attack Efficiency / Critical Chance**. The latter
   trades direct damage for more normal status rolls and substantially more
   frequent first-hit Gas + Blast coexistence. Both are Blast + Gas with no
   separate Toxin or armor strip; their full area damage is not modeled.
   Another option is to replace Fever Strike with a **Heat / Toxin / Critical
   Chance** Riven *placed before Focus Energy*: Heat + Toxin form Gas, while
   Focus Energy leaves Electricity separate, yielding **Blast + Gas +
   Electricity** at 90% efficiency. Gas and Electricity both have damaging
   area statuses. Changing the slot order can change the combinations.
4. **For Gas with splicing, choose the other damage type you actually want:**
   * Keep Fever Strike and use **spliced Gas / Heavy Attack Efficiency /
     Critical Chance**: Blast + Toxin + Gas, 90% efficiency. Toxin can bypass
     shields and is a second damaging status type.
   * **Replace Fever Strike with Focus Energy** and use **spliced Gas / Toxin /
     Critical Chance**: Blast + Corrosive + Gas, 90% efficiency. Electricity
     from Focus Energy combines with the Riven's separate Toxin into Corrosive;
     the already-combined Gas remains independent. This is the more natural
     Gas/armor-strip choice, but it has **no separate Toxin shield bypass**.

   Each of those is **exactly eight mods**, not Fever Strike + Focus Energy +
   Riven. Their Gas status competes with the other damage types, so neither
   guarantees a Gas proc on each slam. Neither is proven the best crowd clear.
5. **No splicing and no Gas required:** Fever Strike + a regular Riven with
   **Heavy Attack Efficiency / Critical Chance / Melee Damage** is a strong
   direct-hit/Toxin candidate. Alternatively, replace Fever Strike with Focus
   Energy and use **Toxin / Critical Chance / Melee Damage** on the Riven to
   retain Corrosive and the efficiency cap. Both are ordinary rollable
   attributes, but their relative real-world TTKs are unvalidated.

All choices retain the requested six fixed mods: **Primed Pressure Point,
Seismic Wave, Galvanized Elementalist, Galvanized Reflex, Vulcan Blitz and
Galvanized Steel**, plus rank-5 Melee Afflictions. The three Galvanized kill
buffs are assumed fully stacked *from the start*. Warming them up in a mission
will be weaker. Only the final two weapon mod slots vary in those comparisons.
A later user-specified build deliberately **drops Primed Pressure Point** to fit
Fever + Focus + a Gas / Cold / Damage Riven; its exact eight-slot analysis is
[here](jat_kittag_gas_cold_damage_build.md). An independent, experimental
[slam-count sensitivity comparison](jat_kittag_expected_slams.md) contrasts
that build with a Gas / Crit Damage / Crit Chance Riven plus Primed Pressure
Point; it is not a validated gameplay TTK.

## Follow-up: Fever + spliced Gas / Cold / Crit Chance

**With those six fixed mods, Primed Fever Strike and the Riven fill all eight
weapon slots.** Jat Kittag has innate Blast, not Electricity, so without an
external source there is no Electricity for the Riven's Cold to combine with.
Instead, **Cold + Fever Strike's Toxin form Viral**, while the *spliced* Gas
remains a separate combined element. The result is **Blast + Gas + Viral**,
with no separate Toxin, Magnetic or Corrosive. A normal Heat/Toxin-generated
Gas is not the same as the literal spliced +Gas trait used here.

For the same midpoint **3-positive/1-negative Riven** assumptions as the rest
of this report (+101.25% Gas, +101.25% Cold, +202.5% Critical Chance):

- Heavy-attack efficiency is **50%**, and heavy-slam crit chance is **108.75%**.
  Fully stacked Galvanized Elementalist gives 2 guaranteed normal status rolls
  and a 20% chance of a third.
- Before engine rounding and enemy-specific effects, damage-type weights are
  about **21.4% Blast, 21.7% Gas and 57.0% Viral**. The modeled first-slam
  normal-proc chances are **41.3% Gas**, **83.6% Viral**, and **28.7% both**.
  These assume independent rolls, no prior statuses, immunity or external
  procs; they do not include Afflictions replication.
- A literal +101.25% Gas trait gives a **2.0125× normal Gas-tick factor**
  versus no +Gas, holding seed inputs fixed. Do not assume the same factor
  necessarily applies to Afflictions-created/re-seeded stacks.

**Viral + Gas is a legitimate alternative**, especially when enemy health is
exposed and the enemies can receive Viral. The first Viral stack doubles damage
to health for six seconds; 10 stacks give 4.25× health damage. Viral does not
strip armor or amplify damage to shields or Overguard. Its own triggering
*direct hit* is not amplified, but the [Viral Wiki](https://wiki.warframe.com/w/Damage/Viral_Damage)
states that Gas procs applied at the same time as Viral do get their immediate
first Gas tick amplified. A Gas cloud damages nearby enemies, but that damage
is amplified by Viral only on **each enemy that is itself Virally affected**.
Some enemies are immune to Viral status, including several Deimos units.
Melee Afflictions can replicate eligible statuses on a Lifted target, but
Overguard blocks that trigger and current reports disagree about some Jat and
Blast interactions. Do not assume an automatic full stack of Viral or Gas on
every slam.

The main cost for the original rapid-spam goal is the missing efficiency.
Compared with **Fever + spliced Gas / Efficiency / Crit**, this proposed build
has **1.274×** the neutral average direct damage at the same 5× combo, but
only **0.860×** over the first eight modeled slams at the illustrative 0.65 s
interval because its combo tiers fall. Both figures exclude Viral amplification,
Gas/Blast statuses, Afflictions, Vulcan Blitz and defenses, so they **do not
rank total damage or clear speed**. At slower cadence or with other combo
sources, this tradeoff can change.

### If Magnetic was the goal

[Focus Energy](https://wiki.warframe.com/w/Focus_Energy) supplies Electricity
and 40% efficiency, but adding it while retaining the six fixed mods, Fever
and the Riven would be a **ninth mod**. Legal alternatives include:

| Two flexible slots | Result and tradeoff |
| --- | --- |
| **Focus Energy + spliced Gas / Cold / Crit Riven** | Replace Fever: Blast + Gas + Magnetic; 90% efficiency, 108.75% crit, literal +Gas tick bonus. No separate Toxin. |
| **Fever + spliced Gas / Cold / Electricity Riven** | Keep Fever; put the Riven **before** Fever: Blast + Gas + Magnetic + Toxin; literal +Gas, but only 50% efficiency and 48% crit without a Crit roll. |
| **Fever + spliced Magnetic / Heat / Efficiency Riven** | Keep Fever: Blast + Magnetic + Gas (Heat + Fever's Toxin); 90% efficiency, but 48% crit, no separate Toxin, and no literal +Gas tick bonus. |
| **Fever + spliced Magnetic / Heat / Crit Riven** | Same damage types as the previous row; 108.75% crit but only 50% efficiency, still no separate Toxin or literal +Gas tick bonus. |

The Riven can have only one spliced trait: **spliced Gas and spliced Magnetic
cannot both be on the same Riven**. The first Magnetic alternative retains the
exact proposed Gas/Cold/Crit Riven but drops Fever; the other rows change its
traits. An external source is another possibility, but its rules matter:
[Shock Trooper](https://wiki.warframe.com/w/Shock_Trooper), for example, adds
separate Electricity rather than combining it with Cold, and would also change
the proc weights above. The Electricity option on a
[Violet Archon Shard](https://wiki.warframe.com/w/Violet_Archon_Shard) applies
to **primary** weapons, not Jat Kittag.

If one of the original six fixed mods were deliberately removed, Fever + Focus
Energy + the proposed Riven would fit in eight slots. To get **Blast + Gas +
Magnetic + separate Toxin**, place both the Riven's Cold and Focus Energy
**before** Fever Strike: the first pair forms Magnetic, leaving Fever's Toxin
uncombined. Placing Fever before the Riven can instead create Viral + separate
Electricity; placing Fever before Focus can create Corrosive + separate Cold.
This is a conditional slot swap, **not** part of the six-fixed-mod comparison;
for example, removing Vulcan Blitz would sacrifice its death explosion.

## Why Focus Energy helps with spam

[Galvanized Reflex](https://wiki.warframe.com/w/Galvanized_Reflex) provides
+50% efficiency and, at four stacks, **81.4 Initial Combo**. Initial Combo
recharges at **40 points per second** after being spent; 80 points is the 5×
threshold. Heavy Attack Efficiency is capped at **90%**. Focus Energy adds
+40% efficiency and +60% Electricity; Focus Radon adds the same efficiency
and +60% Radiation. See the Wiki's
[combo](https://wiki.warframe.com/w/Melee_Combo),
[Focus Energy](https://wiki.warframe.com/w/Focus_Energy) and
[Focus Radon](https://wiki.warframe.com/w/Focus_Radon) pages.

| Setup | Efficiency | Combo retained from 81.4 | First recovery to 80 | First full recovery to 81.4 | Minimum interval to sustain 5× indefinitely |
| --- | ---: | ---: | ---: | ---: | ---: |
| Reflex alone | 50% | 40.7 | 0.983 s | 1.018 s | **1.00 s** |
| Reflex + Focus Energy or Radon | 90% | 73.26 | 0.169 s | 0.204 s | **0.20 s** |

The last column is important: *the first return to a threshold is not the same
as repeatedly sustaining it*. If a slam is made right at 80 points, retaining
90% leaves 72, so it takes 8/40 = 0.20 s to get back to 80 on every following
slam. These are continuous-time idealizations; exact game rounding and frame
timing may shift boundaries.

For an illustrative **0.65-second** landing-to-landing interval, beginning at
81.4, assuming no combo gained from hits or external effects:

| Setup | Combo tiers on eight consecutive slams | Mean tier |
| --- | --- | ---: |
| 50% efficiency | 5, 4, 3, 3, 3, 3, 3, 3 | 3.375× |
| 90% efficiency | 5, 5, 5, 5, 5, 5, 5, 5 | 5× |

At illustrative 0.75 s, 50% gives 5,4,4,4,4,4,4,4; at 1.00 s it sustains
5× in this model. **These intervals are examples, not measured Jat slam
cadences.** Height, animation cancellation, player inputs and effects change
the real rhythm and coverage. The Wiki says regular slams gain combo per enemy
hit and regular heavy attacks do not generate combo; the exact heavy-slam
radial behavior is not settled here, so zero added combo is an explicit
scenario, not a universal claim. Existing combo above the Initial Combo floor,
blocking, other attacks or team buffs can change the result.

**Optional Warframe aura, no weapon slot:**
[Ready Steel](https://wiki.warframe.com/w/Ready_Steel) adds +24 Initial Combo.
With the assumed Reflex stacks this gives 105.4 points and a **6×** starting
tier while keeping Focus Energy. At 90% efficiency, the model's first return
to 100 is 0.129 s and the interval needed to sustain 6× is 0.25 s. It costs an
aura slot and is *not* included in the comparison tables below.

Likewise a midpoint +27.6 Initial Combo Riven gives 109 points and starts at
6×. With 90% efficiency, its first return to 100 is about 0.048 s but sustained
6× still requires at least 0.25 s. A Riven Initial Combo roll can therefore be
useful if preserving the higher tier matters more than the positive it replaces.

## Gas, Corrosive and the arcane

- Jat Kittag's [heavy slam](https://wiki.warframe.com/w/Jat_Kittag) is
  listed at 600 innate Blast damage, 100% status, 15% crit chance and 2× crit
  multiplier; the forced effect is **Lifted**, not a guaranteed Blast proc.
  Slam radius depends on travel distance and direct damage falls off toward
  the edge. A short low-height spam is not necessarily the listed 10 m radius.
- [Gas](https://wiki.warframe.com/w/Damage/Gas_Damage) creates a six-second
  area cloud, growing from 3 to 6 m with stacks, that persists after the host
  dies. It is attractive in dense groups, especially with enemies grouped near
  a cloud. Gas damage is reduced by armor and does not bypass shields.
- **Heat + Toxin mods form Gas direct damage but do not themselves multiply a
  normal Gas tick.** The Wiki's normal Gas formula does accept a literal
  **+Gas Damage** bonus, including a spliced Gas Riven: +101.25% Gas is a
  2.0125× normal-Gas tick factor *holding all other seed inputs fixed*.
  Whether and how this bonus applies to stacks created/re-seeded by Melee
  Afflictions is not independently established here; do not extrapolate that
  factor to all arcane damage.
- [Corrosive](https://wiki.warframe.com/w/Damage/Corrosive_Damage) removes
  26% armor on its first proc and up to 80% at 10 stacks, and has a 1.5×
  direct type bonus against Grineer/Kuva Grineer. For illustration only, on an
  ordinary target starting at 2,700 armor/90% DR, the Wiki armor formula gives
  roughly **2.26×** damage after one Corrosive proc and **5.98×** after ten,
  relative to no strip. This is not an Overguard multiplier or a TTK forecast.
- [Melee Afflictions](https://wiki.warframe.com/w/Melee_Afflictions) can
  affect statuses already present, including statuses inflicted by the
  triggering hit; an eligible target need not already be Lifted. Rank 5 says
  +6 stacks, but the Wiki currently identifies **+12 from Lifted as a bug**,
  so don't build a permanent guarantee around it. It describes complicated
  damage re-seeding across status types; this analysis does not calculate it.
  Existing combined elemental mods may also influence Afflictions-created
  Toxin/Electricity according to that page: do not treat elemental pairing as
  proof that all source bonuses vanish from arcane-created procs.
- The Wiki's Afflictions page is marked for update and tentatively records a
  Blast-only fix; a [June 2026 forum test](https://forums.warframe.com/topic/1512645-melee-afflictions-the-dot-requirement-and-blast-status/)
  reports that most non-DoT statuses, including Corrosive and Blast, required a
  damaging DoT to be replicated, with exceptions. These reports are not
  conclusively reconciled. Jat-specific [bug reports](https://forums.warframe.com/topic/1515280-jat-kittag-melee-afflictions/)
  also disagree on Blast behavior. Consequently a pure Blast + Corrosive
  build's **arcane replication is a less certain part of the recommendation**;
  direct Corrosive damage and ordinary armor strip do not depend on that claim.
- Enemy [Overguard](https://wiki.warframe.com/w/Overguard) can receive status
  effects and armor can be stripped while it remains, but it blocks the
  Lifted/knockdown trigger for Afflictions. Toxin does not bypass it. The user
  has raised an overflow-discard correction; the Wiki distinguishes the
  player's depletion gate from enemy Overguard and says enemies lack an
  invulnerability gate. Exact overflow allocation is not settled here, and
  **no Overguard or shield break is modeled in the tables**. When Magnetic is
  present, its [dedicated Wiki page](https://wiki.warframe.com/w/Damage/Magnetic_Damage)
  describes a forced Electricity proc on depletion: 3% of maximum defense
  per Magnetic stack, up to 30%, as a base total over six seconds before
  applicable modifiers—not 3% per tick. That effect is also not modeled here.
- [Blast](https://wiki.warframe.com/w/Damage/Blast_Damage) has a 1.5 s fuse
  and can detonate in an area at the stack cap or on death; its exact
  Afflictions interaction is disputed. [Vulcan Blitz](https://wiki.warframe.com/w/Vulcan_Blitz)
  creates a separate 6 m, line-of-sight death explosion based partly on the
  killed enemy's maximum health. Hotfix 44.1.3 fixed a specific Elemental
  Ammo-induced recursive explosion interaction; this is not evidence that
  every possible ordinary death chain is gone. Neither contribution is in the
  direct-hit table. **Do not infer crowd TTK from the direct numbers.**

## Idealized status probabilities

With the requested [Galvanized Elementalist](https://wiki.warframe.com/w/Galvanized_Elementalist)
fully stacked, the 100%-base-status heavy slam makes **2 guaranteed normal
status rolls plus a 20% chance of a third**; Volcanic Edge adds 60 percentage
points, giving 2 + 80% of a third. For a type with unquantized damage share
`p` and fractional extra-roll probability `f`, the approximation is
`P(at least one) = 1 - (1-p)^2(1-f*p)`. Joint probabilities use inclusion–exclusion.

| Two flexible slots | Normal damage types | Eff. | P(Gas) | P(other named type) | P(both) |
| --- | --- | ---: | ---: | ---: | ---: |
| Fever + Focus Energy | Blast, Corrosive | 90% | — | Corrosive **91.8%** | — |
| Fever + Focus Radon | Blast, Toxin, Radiation | 90% | — | Toxin **78.2%** | — |
| Fever + Volcanic Edge | Blast, Gas | 50% | **95.8%** | Blast 63.9% | Gas + Blast 59.6% |
| Fever + Molten Impact | Blast, Gas | 50% | **93.2%** | Blast 51.3% | Gas + Blast 44.5% |
| Fever + regular Heat / Efficiency / Crit Riven | Blast, Gas | 90% | **93.6%** | Blast 50.0% | Gas + Blast 43.7% |
| Volcanic Edge + regular Toxin / Efficiency / Crit Riven | Blast, Gas | 90% | **92.6%** | Blast 73.6% | Gas + Blast 66.2% |
| regular Heat / Toxin / Crit Riven **before** Focus Energy | Blast, Gas, Electricity | 90% | **82.7%** | Electricity 32.7% | Gas + Electricity 21.9% |
| Fever + spliced Gas / Efficiency / Crit Riven | Blast, Toxin, Gas | 90% | **50.5%** | Toxin **72.5%** | Gas + Toxin **29.4%** |
| Focus Energy + spliced Gas / Toxin / Crit Riven | Blast, Corrosive, Gas | 90% | **51.0%** | Corrosive **71.9%** | Gas + Corrosive **29.4%** |
| Fever + spliced Gas / Cold / Crit Riven | Blast, Gas, Viral | 50% | **41.3%** | Viral **83.6%** | Gas + Viral **28.7%** |
| Focus Energy + spliced Gas / Cold / Crit Riven | Blast, Gas, Magnetic | 90% | **51.0%** | Magnetic **71.9%** | Gas + Magnetic **29.4%** |
| Fever + spliced Gas / Cold / Electricity Riven, **before** Fever | Blast, Gas, Magnetic, Toxin | 50% | **34.8%** | Magnetic **61.5%** | Gas + Magnetic **15.7%** |
| Fever + spliced Magnetic / Heat / Efficiency or Crit Riven | Blast, Gas, Magnetic | 90% or 50% | **83.6%** | Magnetic **41.3%** | Gas + Magnetic **28.7%** |

These are **first-hit, normal status-roll probabilities**, not chances that
the arcane succeeds or an enemy dies. They assume independent rolls, no
pre-existing statuses, no status immunity and no other procs. The forced Lifted
is not counted. Even a [bullet jump](https://wiki.warframe.com/w/Maneuvers)
can apply a separate guaranteed Blast proc near its start, so the player's
actual rotation may depart substantially from this first-hit calculation.
[Faction weakness](https://wiki.warframe.com/w/Status_Effect) changes damage,
not these type weights; status immunities can change the available choices.
Exact distribution quantization is uncertain, so these use raw modded damage
shares rather than asserting engine-exact proc probabilities.

The table shows the trade clearly: split Gas + another useful type gives much
less reliable *first-slam* Gas than pure Blast + Gas. The two ordinary Riven
variants also differ: Volcanic Edge + Toxin Riven averages approximately
**1.73 Gas and 1.07 Blast normal procs per slam**, compared with **1.60 Gas
and 0.60 Blast** for Fever Strike + Heat Riven, under these assumptions. Both
lack a literal +Gas tick multiplier, and their different proc counts do not
establish a total-damage ranking. Repeated hits, previously applied procs,
crowd density, armor strip, the Gas tick bonus, Afflictions and explosions can
all alter the final outcome. The 29.4% joint probabilities do **not** include
such later effects or claim guaranteed 10-stack replication.

## Direct-hit-only benchmark

The following is **not TTK, not total DPS, and not room damage**. It includes
only the expected center of eight direct slams at the same illustrative
0.65 s interval, using the modeled combo tier for each hit. The reference is
Fever + Focus Energy. It excludes armor/strip, shields/Overguard, statuses, Gas
clouds, Blast detonations, Afflictions, Vulcan Blitz and any extra combo gains.
The neutral column assumes no type weaknesses; the Grineer column includes
only the **1.5× Corrosive type weakness**, still before armor.

| Two flexible slots | Neutral direct / reference | Grineer-type direct / reference |
| --- | ---: | ---: |
| Fever + Focus Energy | 1.000× | 1.000× |
| Fever + Focus Radon | 1.000× | 0.743× |
| Fever + Volcanic Edge | 0.675× | 0.501× |
| Fever + Molten Impact | 0.740× | 0.550× |
| Fever + Shocking Touch | 0.740× | 0.747× |
| Fever + regular Efficiency / Crit / Damage Riven | 2.479× | 1.841× |
| Fever + regular Efficiency / Crit / Crit Damage Riven | 2.143× | 1.592× |
| Fever + regular Efficiency / Crit / Initial Combo Riven | 1.750× | 1.300× |
| Fever + spliced Slam / Efficiency / Crit Riven | 2.113× | 1.570× |
| Fever + spliced Heavy Damage / Efficiency / Crit Riven | 2.200× | 1.634× |
| Fever + regular Heat / Efficiency / Crit Riven | 2.008× | 1.492× |
| Volcanic Edge + regular Toxin / Efficiency / Crit Riven | 1.442× | 1.071× |
| regular Heat / Toxin / Crit Riven **before** Focus Energy | 1.991× | 1.479× |
| Fever + spliced Gas / Efficiency / Crit Riven | 2.008× | 1.492× |
| Focus Energy + spliced Gas / Toxin / Crit Riven | 1.991× | 1.810× |
| Fever + spliced Gas / Cold / Crit Riven | 1.726× | 1.282× |
| Focus Energy + spliced Gas / Cold / Crit Riven | 1.991× | 1.479× |
| spliced Gas / Cold / Electricity Riven **before** Fever | 1.181× | 0.877× |
| Fever + spliced Magnetic / Heat / Efficiency Riven | 1.433× | 1.064× |
| Fever + spliced Magnetic / Heat / Crit Riven | 1.726× | 1.282× |
| Focus Energy + regular Toxin / Crit / Damage Riven | 2.450× | 2.383× |
| Focus Energy + regular Toxin / Crit / Crit Damage Riven | 2.117× | 2.060× |

The equal neutral direct results for ordinary Heat and spliced Gas do not make
their statuses equal: the former is Blast + Gas; the latter is Blast + Toxin +
Gas and has a literal +Gas bonus. Volcanic Edge + Toxin Riven produces more
ordinary procs in this scenario but approximately **28% less neutral direct
hit damage** than Fever Strike + Heat Riven. In the 50%-efficiency rows the lower combo
sequence matters: at the same 5× on the *first* hit, Volcanic Edge and Focus
Energy have the same neutral direct expectation. At slower actual cadence,
Volcanic Edge retains more of that direct damage; at faster cadence it can
lose more. DoT/arcane/area outcomes may reverse any ordering.

Direct damage uses the Wiki's approximate [**1/32 damage-type quantization**](https://wiki.warframe.com/w/Damage/Calculation),
with unquantized shares used only for proc selection. The Wiki's description
of the quantization base has ambiguities; exact game binary32 and crit
rounding are not emulated. At full stacks, Galvanized Steel yields **48% crit
chance, 4.4× crit multiplier**, mean factor **2.632**. With the midpoint
+202.5% Critical Chance Riven the heavy-attack crit chance is **108.75%**,
mean factor **4.6975** under ideal tier averaging. These are not verified
against a full fight or damage attenuation.

## Riven values and alternative rolls

For rank 8, the post-44.1.3 universal 1.2 multiplier and a midpoint
**3-positive/1-negative** layout, example attributes are approximately:

| Attribute | Midpoint | What it buys here |
| --- | ---: | --- |
| Critical Chance | +202.5% | Doubled on heavy attacks; strong direct and proc seed candidate. |
| Melee Damage | +185.3% | Additive with Primed Pressure Point; a solid ordinary third positive. |
| Critical Damage | +101.3% | Additive with fully stacked Galvanized Steel's +120% crit damage. |
| Heavy Attack Efficiency | +82.6% | With Reflex reaches 90% cap; excess is wasted. Focus Energy/Radon already cap it. |
| Initial Combo | +27.6 | 81.4 → 109.0 and 5× → 6×, subject to stacks/timing. |
| Heat or Toxin | +101.3% | A regular element; it combines with the other primary as usual. |
| **Spliced** Gas or Status Damage | +101.25% | Literal Gas increases ordinary Gas ticks; Status Damage competes with an existing +80% and may affect Afflictions differently. |
| **Spliced** Slam or Heavy Attack Damage | +134.7% | Slam shares Seismic Wave's bracket; Heavy Damage is additive with Melee Damage. Each consumes the single spliced-trait choice. |
| Finisher Damage negative | about −107.7% | Example curse for someone not using finishers; it can make ground/prompted finishers ineffective. |

Real rolls vary. The exact 2-positive layout yields larger individual stats,
but cannot contain the three listed positives. Avoid a severe negative Status
Duration or Heavy Attack Efficiency on a build depending on statuses and combo.
Splicing Gas requires Heat + Toxin on **one** Riven; the consumed traits are
replaced by Gas and a random trait, and normal traits can be rerolled/locked
afterwards. Only **one spliced trait** is available at a time. It is not a
free second Riven or an ordinary Gas roll: the Splicer comes from The Icebind,
with a three-per-week reward limit. Details and acquisition are on the
[Wiki](https://wiki.warframe.com/w/Riven_Splicer) and in [DE's workshop](https://forums.warframe.com/topic/1523869-riven-expansion-trait-locking-riven-splicing/).
For an ordinary multi-element Riven, the [Wiki](https://wiki.warframe.com/w/Damage)
states its last-listed element has first priority within the Riven, while mod
slots combine left-to-right, top-to-bottom. Place a Heat/Toxin Riven before
Focus Energy to produce Gas + Electricity; reversing the slots can change the
pairing.
The current Riven value system is documented on the
[Riven Mods page](https://wiki.warframe.com/w/Riven_Mods) and its
[patch history](https://wiki.warframe.com/w/Riven_Mods/Patch_History).

A spliced **Status Damage / Efficiency / Crit** Riven with Fever gives
Blast + Toxin at 90% efficiency, with a normal status-damage factor of
`1 + 0.80 + 1.0125 = 2.8125` versus 1.8 without it. It cannot also have
spliced Gas. Similarly spliced Slam/Heavy Damage are alternatives, not extra
attributes. Under this particular direct-only setup, regular +Melee Damage
outperforms either spliced direct-damage trait in the table, but their
DoT-seeding interactions and total performance remain unvalidated.

**Optional external damage:** one [Nira set](https://wiki.warframe.com/w/Nira's_Set)
Warframe mod contributes +150% Slam Damage, additive to Seismic Wave. With
Seismic Wave and no other Slam Damage bonuses this raises the direct slam
bracket from 3.0 to 4.5, a **1.5× direct-hit** factor without consuming a
weapon slot. Nira's Anguish also gives parkour velocity. This costs a
Warframe mod slot, is not included in the tables, and its interaction with
Afflictions-created damage is not quantified here.

## Reproduction and limits

From the repository root:

```sh
.venv/bin/python -m modules.jat_kittag_slam_analysis
.venv/bin/python -m unittest -v tests.test_jat_kittag_slam_analysis
```

The module prints all candidate values and tier sequences; tests check slot
counts, element composition, status probabilities, Riven/crit brackets,
quantization-based direct ratios and combo recurrences. The recurrence from
an Initial Combo floor `F` is `next = min(F, efficiency * current + 40 * dt)`
when beginning at or below `F`; the implementation does not incorrectly
clamp already-earned combo above that floor. Actual slam speed and combo gain,
Afflictions trigger/reseeding and +Gas behavior, Gas cloud overlap and
replacement, Seismic Wave's DoT seeding, defenses and gate transitions,
status immunity, enemy movement, line of sight, death chains, warm-up and
special targets remain outside the model. Tests establish the calculation's
internal consistency, **not in-game validation**.
