# MAJOR NOTE!!

## A Note on Development: This app's UI and structure were generated entirely using ChatGPT, but the underlying math is the result of countless hours of manual testing and coding.

Ages ago, I started the TenZero.GG project to make a better site to create and share Warframe builds. While I handled the bulk of the overarching project, my collaborator Xadreus and I teamed up heavily on the incredibly complex damage calculations and the underlying math. Together, we worked our tails off to accurately recreate the game's systems, matching not just the HUD stats, but the real-world values you actually see when using weapons in a mission. We honestly had the most accurate calculations of any model we could find online.

Unfortunately, life loves to get in the way of passion projects. Between college for Xadreus and it being over a decade and a half since I last touched webdev, the site itself suffered. But our math and our testing spreadsheets were rock solid.

Instead of letting all the work Xadreus and I put into those accurate damage calculations go to waste, I figured: why not throw our spreadsheet at ChatGPT and see if I could vibe code out a Python app? I wanted to give something back to the amazing Warframe community so our work actually means something, even if the original site never gets built. I absolutely plan to get my hands dirty in the code later to add features and make it look better, but with real life pulling me away, using AI was the best way to get this tool into your hands now. I hope you understand, and I hope you enjoy it!

# Warframe Damage Calculator by TenZeroGG v1.0.1

Desktop Warframe damage calculator built around the calculator engine and packaged as a PyQt6 desktop app.

## Current Features

- PyQt6 dark mode UI
- SQLite database for weapons and mods
- Real mod selection with rank support
- Slot-order elemental combining
- Accurate HUD and final damage calculation flow with Warframe-style rounding
- Built-in FAQ dialog that explains the calculator logic
- Settings dialog for:
  - refreshing Warframe data from DE
  - rebuilding the SQLite database in-app
  - showing where the app stores its AppData-backed files
- App data stored in the user's AppData-backed calculator folder for easier packaging later
- Save and load build files as JSON

## App Data Layout

The app stores its working files in:

- Windows: `%APPDATA%\WDC`
- Fallback on non-Windows systems: `~/.local/share/WDC`

Inside that folder the app keeps:

- `data/weapons.db`
- `source/ExportWeapons_en_Cleaned.zip`
- `source/ExportKeys_en_Cleaned.zip`
- `source/Warframe-Damage-Calculator_v2.xlsx`
- `builds/*.json`
- `settings.json`

## Running

```bash
pip install -r requirements.txt
python main.py
```

If the app does not detect a ready database on startup, it prompts to build initial data from DE and falls back to bundled backup export files when needed.

## Rebuilding The Database Manually

```bash
python build_database.py
```

## Riven Stat Tables

Riven stat data is not present in the cleaned DE export (the Riven
`upgradeEntries` tables are stripped), so WDC vendors a community-verified
Riven stat table and ports the in-game value formula in `modules/riven.py`.
The vendored base values are byte-identical to the current official DE export
(`warframe-public-export-plus`), and every generated range matches the
[WARFRAME Wiki Riven Mods page](https://wiki.warframe.com/w/Riven_Mods)
("Attribute Value Formula" and rank-8 base value tables; see
`tests/test_riven_wiki.py`).

- `source/riven_tags.json` - per-tag base values for all seven Riven types
  (Rifle, Shotgun, Pistol, Kitgun, Melee, Zaw, Archgun), derived from DE's
  Riven `upgradeEntries` via [warframe-riven-info](https://github.com/calamity-inc/warframe-riven-info)
- `source/riven_stats_average_1_2.json` / `.csv` - generated average-grade
  tables at **1.2 disposition**, max rank (rank 8, x9 steps), covering the
  combined-stat layouts 2 positives, 3 positives, 2 positives + 1 negative and
  3 positives + 1 negative (plus negative-stat columns for each). These are the
  only four rollable layouts: a Riven has 2-3 positive stats and at most one
  negative, per the wiki
- The wiki's weighted layout table (0.99 / 1.2375 / 0.75 / 0.9375 bonus and
  -0.495 / -0.75 malus) equals the engine's layout factors multiplied by the
  1.5 specific-fit constant; the two are numerically equivalent
- Average grade means the midpoint random roll (grade factor 1.0); the full
  per-stat roll band is 0.9x-1.1x and is available through `modules/riven.py`
- Stats that map onto the damage engine carry a `wdc_code` (e.g. `HEAT`,
  `TRUE`, `BANE_GRINEER`); utility stats such as critical chance or fire rate
  are labeled but not yet consumed by the calculator
- Riven Disposition was retired in Hotfix 44.1.3 (2026-10-22): all weapons are
  now normalized to the 1.2x these tables use
- Splicing-system attributes (weakpoint damage, combined elemental damage,
  ammo efficiency, etc.) are not part of the Riven upgrade tables and are not
  included

Regenerate the tables (any disposition works):

```bash
python build_riven_tables.py                    # 1.2 disposition
python build_riven_tables.py --disposition 1.0
```

## Condition Overload (GunCO) Stacking Tables

CO-type bonuses (the melee Condition Overload mod, Galvanized
Aptitude/Shot/Savvy, Secondary Shiver, the Cedo's innate alt-fire, Shattering
Frost and Incarnon Genesis perks) are intended to stack **additively** with
ordinary +% damage mods, but many projectile attacks instead apply them
**multiplicatively** - a long-standing, wiki-documented engine quirk. The
catalog of every discrepant attack is vendored from the
[Condition Overload (Mechanic) wiki page](https://wiki.warframe.com/w/Condition_Overload_(Mechanic))
(last edited 2026-10-05, retrieved 2026-10-27) and cross-checked against the
community GunCO rule table in `source/conditionOverload.ts` (wiki pull Oct
2026 plus rainy's GunCO sheet 38.0.12; sheet-only rows are flagged
`gunco_sheet`).

- `source/gunco_mechanic.json` / `.csv` - 118 attack rules across primaries,
  secondaries, melees, exalted weapons, archguns, robotic weapons and amps:
  77 multiplicative, 25 additive with a non-1.0 scale, 16 where no bonus
  applies. The CSV is one row per weapon x attack. Kitgun chamber names that
  exist in both slots (Sporelacer, Tombfinger) carry a section field; pass
  `section=` to the resolver to disambiguate
- `modules/condition_overload.py` - `resolve_co_behavior(weapon, attack)`
  resolver plus `apply_co(...)` implementing both damage formulas
- `tests/test_condition_overload.py` - wiki-pinned rule and formula tests

The two stacking modes (`B` = base, `M` = pooled ordinary damage multiplier
such as Serration, `c` = total CO-type bonus fraction, `s` = per-attack scale):

| Mode | Formula | Wiki behavior |
| --- | --- | --- |
| Multiplying | `B x M x (1 + c) x other` | #1, mostly projectiles, not intended |
| Adding | `B x (M x other + c x s)` | #2-#4, intended, most hitscan weapons |
| Does not apply | CO contribution is 0 | #5, explosion radii and known bugs |

The wiki catalog lists only discrepant attacks; the resolver defaults to
additive +100% for unlisted attacks, additive direct-hit-only for unlisted
hitscan AoE, and "does not apply" for unlisted projectile explosion radii.
Example: with Serration (x2.65) and a +100% CO bonus on a base-100 hit, an
additive attack deals 365 while a multiplicative one deals 530.

Regenerate the tables after updating the vendored TS source:

```bash
python build_gunco_tables.py
```

## Damage Formula And Status Damage Reference

`docs/damage_formula_reference.md` is a wiki-sourced (retrieved 2026-10-27)
reference covering the full damage pipeline and every weapon delivery type:

- direct damage: Arsenal total, 1/32 quantization, armor modifier
  (`1 - 0.9*AR/(AR+2700)`), crit average shots, AoE/direct-hit split, weak
  points and burst/sustained DPS by trigger type
- hitscan vs projectile vs beam (continuous weapon) differences: trace
  registration, per-pellet proc rolls, beam ticking at `1/fire rate`, the
  0.6 s damage ramp, and multishot merging where a beam tick's damage and
  status chance are the sum of the merged beams (DoTs double dip multishot)
- status chance: per-pellet rolls, >100% unique procs, damage-distribution
  proc weighting (the 0.25x elemental weight was removed in Update 27.2),
  average procs per shot/second
- the five damaging procs (Slash, Heat, Toxin, Electricity, Gas): tick
  timing, the exact `(sum(S_i)+1) x C x M` tick formula, the simplified
  per-type formulas, modded-base seeds, faction double dipping and which
  mods can buff each proc
- a Gas status change log: the mechanical rework was Update 27.2
  (2020-03-05, cloud deals Gas DoT instead of forcing Toxin procs); Update
  36.0 (2024) only changed VFX and faction resistances, not damage numbers

The formulas are ported into `modules/status_damage.py` (pure functions, no
data files) and pinned against the wiki's worked examples in
`tests/test_status_damage.py`.

## Target Dummy Models (Eximus Heavy Gunner)

`docs/target_dummy_models.md` documents the full level-scaling model for the
two benchmark dummies — an Eximus Heavy Gunner at level 150 on The Steel
Path and at level 1000 in The Icebind (all 1–6 player squad sizes):

- Grineer health/armor S-curves with the 70–80 smoothstep, Eximus base-health
  scaler, armor floor/cap of 200/2700 and the current square-root armor DR
  formula `0.9*sqrt(armor/2700)` (90% at the cap)
- Steel Path x2.5 health/shields and Icebind Empowered Enemies x4–x9
  (health/shields/armor) mission multipliers, applied in the exact order used
  by the wiki's live infobox calculator
- Eximus Overguard scaling from base 12 on its own curve (unarmored,
  mission-multiplier independent), plus combined EHP for both dummies

The model lives in `modules/enemy_scaling.py` (pure functions, no data
files) and is pinned in `tests/test_enemy_scaling.py`, including the live
Heavy Gunner infobox anchor (500 armor -> 38.73% DR, EHP 489.64).

## Kuva Nukor Build Simulation (Last Mod Choice)

`docs/kuva_nukor_build_sim.md` covers a tick-by-tick Monte Carlo simulation of
the requested Kuva Nukor build (Magnetic progenitor, Secondary Enervate,
Galvanized Diffusion/Shot, Lethal Torrent, Primed Heated Charge, Primed
Target Cracker, Pistol Elementalist, Viral/Crit Damage/Status Duration Riven)
against the Steel Path level 150 Eximus Heavy Gunner dummy:

- full beam mechanics: 0.6 s damage ramp, merged multishot ticks (summed
  damage/status, single crit roll), per-tick proc rolls weighted by damage
  distribution, Secondary Enervate averaged with the wiki's AFCC formula
- live status state: Heat consolidation and its 15/30/40/50% per-proc armor
  strip (ramp intervals slowed by Status Duration), Viral/Magnetic 10-stack
  multipliers, Overguard Magnetic amplification and break damage, Heat/Toxin
  DoTs, magazine reloads, 1/32 direct-hit quantization
- ranks six last-slot candidates over 500 seeded trials: Scorch, Hornet
  Strike and Anemic Agility all hit a 2.000 s median TTK (Scorch/Hornet
  recommended), beating Hollow Point (2.25 s) and Primed Pistol Gambit
  (2.38 s); Frostbite (Heat+Cold -> Blast) is intentionally weak single
  target (11.7 s) but a room-clear option
- room-clear simulation with beam chaining (2 extra targets at 50%) and
  Blast 5 m radials: Heat builds win packs up to ~5 enemies, Frostbite wins
  from ~7 enemies up and is ~3x faster in a room of 20 (5.4 s vs 16.0 s)

Code: `modules/kuva_nukor_sim.py`; pinned in `tests/test_kuva_nukor_sim.py`.

## Akarius Prime Riven Simulation (Viral vs Corrosive)

`docs/akarius_prime_riven_sim.md` covers a tick-by-tick simulation of an
Akarius Prime (dual burst-fire rocket launchers: 68 Impact Rocket Impact +
509 Blast Rocket Detonation, separate crit/status rolls per instance) with
Secondary Enervate, Galvanized Diffusion/Shot, Hornet Strike, Lethal Torrent,
Primed Heated Charge, Primed Target Cracker, Pistol Elementalist and a
Crit Damage/-Zoom Riven whose third stat is either Viral or Corrosive:

- confirms via the repository's own GunCO tables that Galvanized Shot's CO
  bonus **multiplies** against Hornet Strike on the Rocket Impact
  (bracket ×7.04) while the detonation radius gets no CO (bracket ×3.2)
- models Corrosive's 26%+6%/stack current-armor strip (80% cap) alongside
  the Heat strip, Viral's 4.25x health multiplier, 8-round magazines with
  2.4 s reloads, burst timing and Blast fuses
- Viral wins: mean TTK 3.69 s vs 4.33 s on the SP150 dummy (20% of runs
  kill in the first magazine at 1.50 s; Corrosive never does) and 9.53 s
  vs 25.46 s on the Icebind L1000 stress dummy — Corrosive's strip is
  redundant once Heat is in the build

Code: `modules/akarius_sim.py`; pinned in `tests/test_akarius_sim.py`.

## Ocucor Arcane and Riven Simulation (Enervate vs Cascadia Flare)

`docs/ocucor_riven_sim.md` covers a tick-by-tick simulation of an Ocucor
continuous beam (11 base Radiation/Puncture, 19.2 ticks/s, 20%→100% ramp,
magazine 60 / 1.6 s reload) with Galvanized Diffusion/Shot, Lethal Torrent,
Primed Heated Charge, Primed Target Cracker, Pistol Elementalist, Sentient
Surge and a fixed +Viral/−Zoom Riven whose second positive is chosen from
six candidates, run under both Secondary Enervate and Cascadia Flare:

- Ocucor is absent from the GunCO exception table, so Galvanized Shot's CO
  bonus **adds** to the ordinary damage bracket — the same bracket Flare
  and a Damage Riven feed, which drives the Riven-stat ranking
- Enervate is averaged through the AFCC formula; Flare's +12%/Heat-proc
  stacks (one per beam tick, +480% cap, 10 s) are simulated with their
  real ~3 s ramp, alongside Heat armor strip, Viral stacks, Overguard and
  merged-multishot Heat DoT seeds
- single-target winner: **Enervate + Damage Riven**, median TTK 6.04 s on
  the SP150 dummy vs 9.05 s for the best Flare roll; in dense rooms the
  ordering flips — Flare + Multishot clears 10/20 enemies in 25.0/33.0 s
  vs 34.2/45.0 s for Enervate + Damage, because Flare stays capped and
  feeds the Tendril beams spawned after kills (Sentient Surge is inert
  until a kill, so it contributes nothing on a single dummy)

Code: `modules/ocucor_sim.py`; pinned in `tests/test_ocucor_sim.py`.

## Jat Kittag Heavy-Slam Simulation (Last Slot and Riven)

`docs/jat_kittag_heavy_slam_sim.md` covers a slam-by-slam simulation of a
Jat Kittag heavy-slam build (600 Blast heavy slam, 100% status, forced
Lifted, 1/s, no wind-up) with Primed Pressure Point, Seismic Wave,
Galvanized Elementalist/Reflex/Steel, Vulcan Blitz, Primed Fever Strike
and Melee Afflictions, comparing nine normal mods (incl. Focus Energy and
the 60/60 Virulent Scourge/Volcanic Edge) and eight average-grade Riven
rolls for the open 8th slot. Full
Galvanized stacks are assumed active: Reflex's 81.4 Initial Combo gives a
free 5x combo floor, Steel adds +120% crit damage and Elementalist +120%
status chance:

- models the full heavy-slam damage chain (Seismic Wave's separate x3.0
  bracket, Killing Blow additive with Pressure Point, Galvanized Steel and
  Riven crit chance doubled on heavy attacks), Corrosive armor strip,
  Toxin DoTs (shield-bypass only, armor-mitigated), Gas clouds, Viral
  stacks, Overguard and Melee Afflictions' post-Overguard stack
  injections (12 per Lifted trigger per the wiki bug, gated behind a
  live Gas/Toxin DoT), plus a worked Gas-vs-Toxin tick calculation
- stateful combo model (`combo_recovery=True`): after each slam, Heavy
  Attack Efficiency retains its fraction of the counter and Initial Combo
  regenerates at 40 points/s (heavy slams add no points); a 3-positive
  CC/CD/AS Riven's 0.618 s cadence collapses the 50%-efficiency floor
  5x -> 4x -> a steady 3x, while 90%-efficiency Focus Energy holds 5x
- **Gas is the worst option on armored SP Grineer** (68 s median TTK at
  the 5x floor vs 7.4 s for the winner): Gas ticks are armor-mitigated,
  their seed ignores Heat/Toxin mods, and combining away Heat removes the
  only armor strip — a Toxin tick is exactly 2.65x a Gas tick before
  armor; Gas only makes sense vs unarmored Infested or external strip
- winners: the **3-positive Riven Crit Chance + Crit Damage + Attack
  Speed** (7.4 s single target), then **Riven Melee Damage + Attack
  Speed** (8.3 s) and **Riven Crit Chance + Crit Damage** (10 s,
  guaranteed crits); without a Riven, **Corrosive/Shocking Touch** is the
  best mod slot (14 s; 10-12 s room clears) but never triggers Melee
  Afflictions because it has no damaging DoT; Focus Energy (90%
  efficiency cap) beats it in light-attack rotations rebuilding toward
  12x (11.9 s vs 23.5 s end-to-end); Initial Combo Rivens only lift the
  Reflex floor from 5x to 6x and are not worth rolling
- **three-way table on a plain SP150 Heavy Gunner** (286,140 HP, 2,700
  armor, no Overguard) with the 3-positive +202.5% CC / +101.3% CD /
  +61.8% AS Riven: **Focus Energy (Corrosive) wins at 1.85 s median TTK**
  vs Virulent Scourge 60/60 Toxin 2.47 s and Volcanic Edge 60/60 Heat
  (Gas) 4.94 s — Focus holds the 5x combo floor where the 50%-efficiency
  builds fall to 3x, and Corrosive strips armor from the first slam;
  without the Riven the same ordering holds at 5.0 / 6.0 / 13.0 s

Code: `modules/jat_kittag_sim.py`; pinned in `tests/test_jat_kittag_sim.py`.

## Alternox Prime Riven Simulation (Blast Roll, Two Open Positives)

`docs/alternox_prime_riven_sim.md` covers an analytic expected-DPS ranking and
a hit-by-hit Monte Carlo of an Alternox Prime normal-fire build (75 pure
Electricity projectile, 5.33/s, 3.3 multishot) with Serration, Galvanized
Aptitude/Chamber, Rifle Elementalist, Primed Cryo Rounds, Vital Sense,
Critical Delay and a 3-positive Riven whose Blast trait (a Riven Splicer
combined element since Update 44.1) is fixed:

- reads Rifle Riven averages from `source/riven_stats_average_1_2.csv` and
  resolves combined-element names (Blast/Viral/Magnetic/...) to the
  identical wiki base-element range; a specific rolled value can be passed
  via `blast_value`
- resolves Galvanized Aptitude through the GunCO catalog: the Alternox
  Prime Normal Attack is an explicit `multiply` rule (×3.4 at 2 stacks /
  3 status types), and Electric/Blast proc seeds snapshot the multiplied
  modded base while radials and alt-fire get no GunCO
- ranks all 20 candidate pairs: every Viral (Riven Toxin + Cryo Cold) build
  beats every non-Viral build; **Damage + Toxin leads on sustained DPS**
  (1,128,031 burst / 953,742 sustained) while Fire Rate + Toxin wins the
  in-magazine stochastic TTK (3.08 s vs 3.28 s median, 200 trials) on the
  plain SP150 Heavy Gunner dummy
- checks cold-open (zero kill stacks), single-Viral-stack and
  single-positive marginals; Heat and Electricity Riven positives are
  flagged as traps (Blast merge loses a GunCO type; Magnetic does nothing
  to Grineer health), and −Punch Through is the free curse

Code: `modules/alternox_prime_sim.py`; pinned in
`tests/test_alternox_prime_sim.py`.

## Notes

- The updater now uses streamed downloads with file-size validation before it runs Python LZMA decoding on Warframe's manifest index.
- Truncated downloads are caught early with a clearer error message.
- 7-Zip is no longer required for normal refreshes.
- The current focus is the core damage path, not every secondary combat system in Warframe yet.


## Building A Windows EXE And Installer

This project includes:

- `WDC.spec` for PyInstaller
- `build_exe.bat` to build the app into `dist\WDC`
- `installer\WDC.iss` for Inno Setup
- `build_installer.bat` to compile the installer into `installer_output`
- `installer\BUILDING.md` with quick build steps

Typical build flow:

```bat
build_exe.bat
build_installer.bat
```

## License

Distributed under the GNU GPL-3.0 license; please check the `LICENSE` file in the GitHub repository for more information.

## Disclaimer

The following is the disclaimer that applies to all scripts, functions, one-liners, etc. This disclaimer supersedes any disclaimer included in any script, function, one-liner, etc.

You running this script/function means you will not blame the author(s) if this breaks your stuff. This script/function is provided **AS IS** without warranty of any kind. Author(s) disclaim all implied warranties including, without limitation, any implied warranties of merchantability or of fitness for a particular purpose.

The entire risk arising out of the use or performance of the sample scripts and documentation remains with you.

In no event shall author(s) be held liable for any damages whatsoever (including, without limitation, damages for loss of business profits, business interruption, loss of business information, or other pecuniary loss) arising out of the use of or inability to use the script or documentation.

Neither this script/function, nor any part of it other than those parts that are explicitly copied from others, may be republished without author(s) express written permission.

The author(s) retain the right to alter this disclaimer at any time.

For the most up to date version of the disclaimer, see:  
https://ucunleashed.com/code-disclaimer
