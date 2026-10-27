# Target Dummy Models: Eximus Heavy Gunner (Steel Path L150 / Icebind L1000)

Mathematical model for the two requested target dummies, implemented in
[`modules/enemy_scaling.py`](../modules/enemy_scaling.py) and pinned by
[`tests/test_enemy_scaling.py`](../tests/test_enemy_scaling.py) (24 tests).

The implementation is a faithful Python port of the WARFRAME wiki's live
enemy-infobox calculator `MediaWiki:Gadget-enemyinfoboxslider.js` (oldid
2816353, retrieved 2026-10-27) — the same gadget that renders the
[Heavy Gunner](https://wiki.warframe.com/w/Heavy_Gunner) infobox with its
Eximus / Steel Path / Icebind / player-count checkboxes. Cross-checked
against [Enemy Level Scaling](https://wiki.warframe.com/w/Enemy_Level_Scaling),
[Armor](https://wiki.warframe.com/w/Armor),
[Eximus](https://wiki.warframe.com/w/Eximus),
[Overguard](https://wiki.warframe.com/w/Overguard),
[The Steel Path](https://wiki.warframe.com/w/The_Steel_Path),
[Empowered Enemies](https://wiki.warframe.com/w/Empowered_Enemies) and
[The Icebind](https://wiki.warframe.com/w/The_Icebind).

## Base enemy: Heavy Gunner (Grineer)

| Stat | Value |
| --- | --- |
| Base level | 8 |
| Base Health | 300 |
| Base Armor (Alloy Armor) | 500 |
| Shields | 0 |
| Eximus base health override | 300 (then Eximus scaler applies) |
| Headshot multiplier | 3.0x |
| Faction modifiers | Impact 1.5x, Corrosive 1.5x (vs Grineer) |

At base level the live infobox shows **38.73% damage reduction** and
**EHP 489.64**; the model reproduces both exactly.

## Scaling pipeline (order matters)

For level difference `q = current_level - 8`, every stat uses two power
curves blended by a smoothstep over a transition window:

```
s(q; lo, hi) =
    0                              q < lo
    1                              q > hi
    3T^2 - 2T^3, T = (q-lo)/(hi-lo)  otherwise

multiplier = 1 + f1(q) + (f2(q) - f1(q)) * s(q; lo, hi)
```

| Stat | f1(q) | f2(q) | Window |
| --- | --- | --- | --- |
| Health (Grineer) | `1 + 0.015 q^2.12` | `1 + 10.7332 q^0.72` | 70–80 |
| Armor | `1 + 0.005 q^1.75` | `1 + 0.4 q^0.75` | 70–80 |
| Overguard | `1 + 0.0015 q^4` | `1 + 260 q^0.9` | 45–50 |
| Outgoing damage (Grineer, then x2) | `1 + 0.015 q^1.75` | `1 + 0.0075 q^1.55` | 1–25 |

Stat assembly, in the exact order the wiki gadget applies it:

1. **Eximus conversion** — base Overguard becomes 12; base stats are swapped
   to Eximus variants when defined.
2. **Eximus base-health scaler** (armored coefficient 0.25), driven by `q`:
   - `q <= 15`: `max(1.1 * HP, 0.25 * (HP + 900))`
   - `15 < q <= 25`: factor `1 + 0.025(q-15)`
   - `25 < q <= 35`: factor `1.25 + 0.125(q-25)`
   - `35 < q <= 50`: factor `2.5 + (2/15)(q-35)`
   - `50 < q <= 100`: factor `4.5 + 0.03(q-50)`
   - `q > 100`: factor `6` -> for the Heavy Gunner this is
     `max(330, 0.25 * 1200 * 6) = 1800`.
3. **Mission multiplier on base stats** (before level scaling):
   - Steel Path: health/shields **x2.5** (armor is *not* multiplied);
   - Empowered (Archon Hunt/Netracell/Archimedea): health/shields
     `x(2.0 + 0.5 * players)` = 2.5x/3.0x/3.5x/4.0x;
   - The Icebind: health/shields/**armor** `x(3.0 + players)` =
     4.0x … 9.0x for 1–6 players. Steel Path and Empowered never stack.
4. **Level multiplication** — health and Overguard round to 2 decimals;
   armor is floored and then clamped to **[200, 2700]**.
5. **Armor damage reduction** (current in-game formula since Update 36,
   Jade Shadows):

   ```
   DR = round(sqrt(3 * armor) * 100) / 10000
      = 0.9 * sqrt(armor / 2700)   (4-decimal rounding; 90% at the 2700 cap)
   ```

   > **Wiki inconsistency:** the prose on wiki.warframe.com/w/Armor and
   > /w/Damage/Calculation still prints the pre-U36 *linear* formula
   > `0.9 * armor / 2700` (both pages carry work-in-progress banners). The
   > maintained infobox gadget, the Fandom mirror and current community
   > testing all use the square-root form above — which is also what this
   > repository's `modules/calculator.py` already implements.
6. **Overguard** scales on its own curve from base 12 and is **not**
   affected by Steel Path/Empowered/Icebind multipliers. It ignores armor
   DR and damage-type resistances (Void is the only weakness, x1.5).
7. **EHP** = `round2(health / (1 - DR) + shields) + overguard`. Overguard
   is added as a raw, unarmored buffer.

## Dummy A — Eximus Heavy Gunner, level 150, The Steel Path

Steel Path adds 100 levels to the node; "level 150" here is the resulting
enemy level. `q = 150 - 8 = 142`, well past every transition window, so all
curves sit on their upper endpoint `f2`.

| Build step | Value |
| --- | --- |
| Eximus base health (`q > 100` branch) | 1,800 |
| Steel Path x2.5 | base 4,500 (armor untouched) |
| Health multiplier `f2(142)` | 381.519423x |
| **Health** | **1,716,837.41** |
| Armor multiplier `f2(142)` | 17.454180x |
| Raw scaled armor `floor(500 x 17.4542)` | 8,727 -> capped |
| **Armor / damage reduction** | **2,700 / 90.00%** |
| Overguard multiplier `f2(142)` | 22,493.247716x |
| **Overguard** (12 base; SP does not multiply it) | **269,918.97** |
| Armored-health EHP `health / 0.1` | 17,168,374.10 |
| **Total EHP** | **17,438,293.07** |
| Reference: enemy outgoing damage multiplier | x34.52 (Grineer x2 included) |

## Dummy B — Eximus Heavy Gunner, level 1000, The Icebind

Icebind enemies are native level 999+ (no Steel Path level shift). The
Empowered Enemies restriction multiplies health, shields **and armor** by
`3 + players`. `q = 1000 - 8 = 992`; health multiplier `f2(992)` =
1543.473196x, armor multiplier 71.703961x, Overguard multiplier
129,371.081847x.

| Players | Icebind multiplier | Base health (1800 x mult) | Health | Armor (pre-cap raw) | DR | Overguard | Total EHP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4.0x | 7,200 | 11,113,007.01 | 143,407 -> 2700 | 90% | 1,552,452.98 | 112,682,523.08 |
| 2 | 5.0x | 9,000 | 13,891,258.76 | 179,259 -> 2700 | 90% | 1,552,452.98 | 140,465,040.58 |
| 3 | 6.0x | 10,800 | 16,669,510.52 | 215,111 -> 2700 | 90% | 1,552,452.98 | 168,247,558.18 |
| 4 | 7.0x | 12,600 | 19,447,762.27 | 250,963 -> 2700 | 90% | 1,552,452.98 | 196,030,075.68 |
| 5 | 8.0x | 14,400 | 22,226,014.02 | 286,815 -> 2700 | 90% | 1,552,452.98 | 223,812,593.18 |
| 6 (default) | 9.0x | 16,200 | **25,004,265.78** | 322,667 -> 2700 | 90% | **1,552,452.98** | **251,595,110.78** |

Full-squad dummy B compared with dummy A: ~14.56x the health and ~14.43x
the total EHP. Armor is identical in practice — both dummies sit on the
2700 / 90% cap, so the Icebind armor multiplier only matters below the
levels where level scaling alone reaches the cap. Overguard is identical
for every squad size (it ignores Empowered multipliers) and is a small
fraction of total EHP here (~1.55% of dummy A, ~0.62% of dummy B).

## Practical implications for weapon testing

- **Both dummies cap at 90% armor DR**, so every point of health is worth
  10 EHP until armor is stripped. A 28%+ armor strip at the cap (540 armor
  remaining) is the break-even where Viral out-scales raw Corrosive.
- **Overguard must be burned first** and is unarmored: it takes full
  damage from every type except it only *resists* nothing — Void deals
  x1.5 to it, and Magnetic procs amplify Overguard damage. Secondary
  Fortifier (up to x8) is the dedicated Overguard lever.
- Grineer faction modifiers apply on the health bar: **Impact and
  Corrosive x1.5**; headshots multiply health-bar damage by x3.
- Scope note: the model covers the standard **Empowered Enemies**
  restriction. Icebind's separate votable restrictions are *not* included:
  **Archaic Armor** (unstrip-able armor that loses 1% max per hit) and
  **Bolstered Belligerents** (Overguard equal to 50% of max health) would
  change these numbers substantially.

## Usage

```python
from modules.enemy_scaling import (
    steel_path_eximus_heavy_gunner,
    icebind_eximus_heavy_gunner,
    scale_enemy, HEAVY_GUNNER, MODE_ICEBIND,
)

dummy_a = steel_path_eximus_heavy_gunner(150)
dummy_b = icebind_eximus_heavy_gunner(1000, players=6)

# Any enemy/level/mode combination:
custom = scale_enemy(HEAVY_GUNNER, 200, eximus=True,
                     mode=MODE_ICEBIND, players=4)
```

Run the tests with:

```
python3 -m unittest tests.test_enemy_scaling -v
```
