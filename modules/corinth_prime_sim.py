"""Corinth Prime Riven choice simulation (primary fire, semi-auto trigger).

WARNING: experimental simulation, not a validated in-game TTK model. It reuses
the audited core (element hierarchy, 1/32 quantization, critical tiers, Viral /
Corrosive / Puncture stack rules, armor scaling) and the routing assumptions
documented in ``docs/formula_audit.md``. Read that file before quoting a number.

The request fixes eight weapon slots, one Primary arcane and the Riven in the
slot that Galvanized Acceleration would occupy (that mod adds projectile speed
only, so it is the natural cut):

    Semi-Shotgun Cannonade, Galvanized Hell, Primed Ravage, Blunderbuss,
    Primed Chilling Grasp, Toxic Barrage, Primed Charged Shell,
    Shotgun Riven   (+ Primary Overcharge arcane)

Weapon model (``source/ExportWeapons_en_Cleaned.zip``, "Corinth Prime",
retrieved 2026-11-12): 25.2 Impact / 37.8 Puncture / 27.0 Slash per pellet
(90 total), **six pellets** per trigger pull, 30% critical chance, 2.8x
critical multiplier, 9% status chance per pellet, 1.4167 attacks/s, magazine
20, reload 3.0 s, semi-auto trigger. The alt-fire airburst round is not
modelled; the target is one Heavy Gunner at point-blank full damage (the
export carries no falloff data, so range falloff is out of scope).

Mod values (``source/ExportKeys_en_Cleaned.zip`` rank tables, max rank):

* Semi-Shotgun Cannonade: +240% damage, +1.5 m punch-through, "Fire Rate
  cannot be modified" -- the model therefore holds fire rate at the 1.4167
  base value and ignores Fire Rate rolls and curses (see the caveat below).
* Galvanized Hell: +110% multishot, plus +30% per kill stack, 4 stacks
  -> +230% with every stack held (as requested).
* Primed Ravage +110% critical damage; Blunderbuss +90% critical chance;
  Primed Chilling Grasp +165% Cold; Toxic Barrage +60% Toxin and +60% status
  chance; Primed Charged Shell +165% Electricity.
* Galvanized Acceleration (+30% projectile speed, +30% per kill stack) is the
  mod the Riven replaces; projectile speed does not enter the damage model.
* Primary Overcharge (``ExportRelicArcane``:
  ``/Lotus/Upgrades/CosmeticEnhancers/Offensive/MultishotForMaxEnergy``)
  grants "35% of Max Energy as Multishot, capped at 250%" while at or above
  90% energy. The request says to assume the cap, so it contributes **+250%
  multishot** (additive with Galvanized Hell).

That gives 6 x (1 + 2.30 + 2.50) = **34.8 pellets per trigger pull**, 57%
critical chance, 5.875x critical damage (2.7976 after 12-bit quantization,
times 2.10 from Primed Ravage) and 14.4% status chance per pellet before any
Riven.

Riven values come from ``source/riven_stats_average_1_2.csv``: the shotgun
rows (``LotusShotgunRandomModRare``), average (midpoint) grade, after Hotfix
44.1.3 normalized every disposition to 1.20. The 3-positive/1-curse column
reads Damage +185.3%, Critical Chance / Critical Damage / Status Chance /
element +101.3%, Multishot +134.7%, Status Duration +112.5%, Damage to
Grineer +51%; the 2-positive/1-curse column is larger (Damage +244.6%,
crit / element +133.7%, Multishot +177.8%, Bane +67%).

Spliced traits: since Update 44.1 two traits on one Riven can be merged into a
combined element (Heat + Toxin -> Gas, ...). The merge preserves the layout --
the consumed pair becomes the combined trait and a re-rollable trait -- so a
spliced Riven still shows the normal number of positive lines
(``docs/jat_kittag_slam_spam_comparison.md``), and the combined trait inherits
the higher consumed value, which at average grade is the ordinary element
value (``COMBINED_ELEMENT_STATS``). A spliced trait is pre-combined: it never
joins the Cold/Toxin/Electricity groups of the fixed mods.

Targets: two Steel Path level-150 Heavy Gunners, both faction Grineer. The
plain one is 286,139.57 HP at 2,700 armor; the Eximus one
(:data:`TARGET_EXIMUS`, the CLI default, and the target of the 2026-11-12
follow-up request) is 1,716,837.41 HP at 2,700 armor behind 269,918.97
Overguard. The plain target stays the factory default so the benchmark digest
in ``tools/bench_models.py`` keeps its reference value.

Overguard routing follows ``modules/damage_routing.py``: the layer is neutral to
every damage type except Void, so the Grineer type table (Corrosive x1.5,
Impact x1.5, Heat x0.5) applies to the health layer only, while a Bane-style
faction *damage* bonus is applied to the hit before routing and therefore
reaches both layers. Status effects are still applied while Overguard stands,
which matches the Overguard page's "immunity to most crowd control effects"
wording; the only consequence here is the damage those procs deal to the
Overguard layer, and Cold's four-stack cap while the layer holds.

Element pairing: the three fixed elemental mods are the same in both layouts,
but Warframe combines primary elements in mod-slot order, so
``element_layout`` decides the result. :data:`ELEMENT_LAYOUT_VIRAL_ELEC`
(Cold + Toxin -> Viral, Electricity single) is the original build;
:data:`ELEMENT_LAYOUT_CORROSIVE_COLD` (Toxin + Electricity -> Corrosive,
Cold single) is the variant that pairs the base into Corrosive and leaves Cold
as its own damage type. The magnitudes are identical -- only the pairing
changes.

Status model (shared with the other simulators):

* Viral: 2 + 0.25 x (stacks - 1) health damage, 10 stacks / 4.25x, 6 s.
* Corrosive: 26% of current armor on the first stack and +6% per further
  stack, 10 stacks / 80%, 8 s (``docs/damage_formula_reference.md``).
* Puncture: +5 absolute critical-chance points per stack, 5 stacks, 10 s.
* Electricity: six ticks over 6 s at 0.5x modded base, first tick on
  application, buffed by the Electricity elemental bonus and reduced by armor.
* Slash: six ticks over 6 s at 0.35x modded base, first tick after 1 s,
  bypasses armor.
* Cold: +0.10x Critical Damage on the first stack, +0.05x per further stack,
  +1.0x while Frozen; capped at four stacks (+0.25x) while Overguard stands,
  freezing at ten for half the status duration and leaving three stacks. The
  target owns that state machine; this module only has to apply the proc.
* Magnetic: amplifies Overguard damage by 2.0 + 0.25 x (stacks - 1) to 4.25x
  and, when the layer breaks, releases Electricity worth 3% of maximum
  Overguard per stack over the proc duration. Both are delegated to the shared
  target: the amplification happens inside ``route_enemy_hit`` because the
  target now carries Magnetic stacks, and the break tick is settled from
  ``next_magnetic_electric_tick`` alongside the other DoTs.
* Impact stagger and Radiation confusion have no single-target damage effect
  and are recorded as inert statuses.
* Bane-style faction damage is one multiplier on direct hits and double dips
  the DoT seeds, exactly as in the Verglas and Kuva Nukor models.

Proc selection weights each damage type by its share of the modded hit
(``docs/damage_formula_reference.md`` section 3). Heat, Toxin, Blast and Gas are
not modelled; a Heat Riven pairs with the fixed Electricity into Radiation, so
:func:`build_corinth` builds such layouts but :func:`simulate` rejects them
instead of silently dropping a proc.

Caveats worth repeating in the report:

* Cannonade's "Fire Rate cannot be modified" is read as locking out both
  bonuses and penalties. A -Fire Rate curse is therefore free; a +Fire Rate
  positive is worthless. If the game applies negative fire rate anyway, that
  curse becomes the worst possible roll.
* The vendored shotgun table has no Zoom trait (the rifle and pistol tables
  do), so the usual free -Zoom curse is not available here.
* One target, no headshots, no punch-through geometry, no falloff, no
  companion/aura, and the arcane is assumed held at its 250% cap.
* The analytic table is a health-only steady-state number: it has no Overguard
  layer, no armor strip ramp and no ramp-up, so it is a ranking aid. The Monte
  Carlo TTK is the number to quote against either target.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from .calculator import DamageCalculator
from .constants import FACTION_MULTIPLIERS
from .crit import crit_multiplier_for_tier, quantize_crit_multiplier
from .enemy_scaling import (
    enemy_armor_damage_multiplier,
    steel_path_eximus_heavy_gunner,
    steel_path_heavy_gunner,
)
from .kuva_nukor_sim import DummyTarget, MagneticSource, roll_multishot
from .models import CalculationInputs, EquippedMod, Mod, ModEffect, Weapon
from .status_damage import electricity_tick, slash_tick
from .trial_statistics import sample_percentile

# --- Weapon (source/ExportWeapons_en_Cleaned.zip, "Corinth Prime") ----------

WEAPON_NAME = "Corinth Prime"
WEAPON_UNIQUE_NAME = "/Lotus/Weapons/Tenno/LongGuns/PrimeCorinth/PrimeCorinth"
PELLETS = 6.0                 # base multishot = pellet count
PELLET_DAMAGE = 90.0
BASE_DAMAGE_BY_TYPE = {"IMPACT": 25.2, "PUNC": 37.8, "SLASH": 27.0}
BASE_CRIT_CHANCE = 0.30
BASE_CRIT_MULTIPLIER = 2.80
BASE_STATUS_CHANCE = 0.09     # per pellet
BASE_FIRE_RATE = 1.4166667    # attacks per second
MAGAZINE = 20
RELOAD_TIME = 3.0

# --- Fixed mods (max rank) ---------------------------------------------------

CANNONADE_DAMAGE = 2.40
CANNONADE_PUNCH_THROUGH = 1.50
GALVANIZED_HELL_MULTISHOT = 2.30    # +110% base, +30% x 4 kill stacks
PRIMED_RAVAGE_CRIT_DAMAGE = 1.10
BLUNDERBUSS_CRIT_CHANCE = 0.90
PRIMED_CHILLING_GRASP_COLD = 1.65
TOXIC_BARRAGE_TOXIN = 0.60
TOXIC_BARRAGE_STATUS = 0.60
PRIMED_CHARGED_SHELL_ELEC = 1.65
PRIMARY_OVERCHARGE_MULTISHOT = 2.50

# --- Status constants (modules/status_damage.py, modules/kuva_nukor_sim.py) --

PROC_DURATION = 6.0
VIRAL_CAP = 10
VIRAL_HEALTH_MULTIPLIER_MAX = 4.25
CORROSIVE_FIRST_STACK = 0.26
CORROSIVE_PER_STACK = 0.06
CORROSIVE_CAP = 10
CORROSIVE_DURATION = 8.0
PUNCTURE_CRIT_PER_STACK = 0.05
PUNCTURE_CAP = 5
PUNCTURE_DURATION = 10.0
HEAT_RAMP_INTERVAL = 0.5      # unused (no Heat source), kept for the target API

# --- Targets -----------------------------------------------------------------

TARGET_PLAIN = "plain"
TARGET_EXIMUS = "eximus"
TARGETS = (TARGET_PLAIN, TARGET_EXIMUS)
TARGET_LABELS = {
    TARGET_PLAIN: "SP150 Heavy Gunner",
    TARGET_EXIMUS: "SP150 Eximus Heavy Gunner (with Overguard)",
}

# Element pairing of the three fixed elemental mods. Warframe combines primary
# elements in mod-slot order: the first two form a combined element and the
# third stays single. The user's first build pairs Cold + Toxin (Viral) and
# leaves Electricity single; the alternative pairs Toxin + Electricity
# (Corrosive) and leaves Cold single.
ELEMENT_LAYOUT_VIRAL_ELEC = "viral_electric"
ELEMENT_LAYOUT_CORROSIVE_COLD = "corrosive_cold"
ELEMENT_LAYOUTS = (ELEMENT_LAYOUT_VIRAL_ELEC, ELEMENT_LAYOUT_CORROSIVE_COLD)
ELEMENT_LAYOUT_LABELS = {
    ELEMENT_LAYOUT_VIRAL_ELEC: "Viral + Electricity",
    ELEMENT_LAYOUT_CORROSIVE_COLD: "Corrosive + Cold",
}

# Statuses this module can apply. Blast and Gas need cloud/detonation models
# this build cannot reach, so a layout producing them is rejected.
SUPPORTED_PROC_TYPES = frozenset(
    {"VIRAL", "CORR", "ELEC", "SLASH", "IMPACT", "PUNC", "RAD", "MAG", "COLD"})

# --- Riven tables ------------------------------------------------------------

_RIVEN_CSV = "riven_stats_average_1_2.csv"
_RIVEN_TYPE = "LotusShotgunRandomModRare"

# ``stat_name`` column -> calculator effect code. Codes the calculator does not
# consume (magazine, reload, fire rate) still count for the stat summary.
RIVEN_CODES: dict[str, str] = {
    "Damage": "TRUE",
    "Multishot": "MULTISHOT",
    "Critical Chance": "CRIT_CHANCE",
    "Critical Damage": "CRIT_DAMAGE",
    "Status Chance": "STATUS_CHANCE",
    "Status Duration": "STATUS_DURATION",
    "Damage to Grineer": "BANE_GRINEER",
    "Damage to Corpus": "BANE_CORPUS",
    "Damage to Infested": "BANE_INFESTED",
    "Magazine Capacity": "MAGAZINE_CAPACITY",
    "Reload Speed": "RELOAD_SPEED",
    "Fire Rate / Attack Speed": "FIRE_RATE",
    "Projectile Speed": "PROJECTILE_SPEED",
    "Punch Through": "PUNCTHROUGH",
    "Ammo Maximum": "AMMO_MAXIMUM",
    "Weapon Recoil": "RECOIL",
    "Heat": "HEAT",
    "Cold": "COLD",
    "Electricity": "ELEC",
    "Toxin": "TOXIN",
    "Impact": "IMPACT",
    "Puncture": "PUNC",
    "Slash": "SLASH",
    "Viral": "VIRAL",
    "Blast": "BLAST",
    "Magnetic": "MAG",
    "Corrosive": "CORR",
    "Gas": "GAS",
    "Radiation": "RAD",
}

# Already-combined (spliced) traits. The vendored CSV only lists base
# attributes; the wiki gives Combined Elemental Damage the same range as
# Elemental Damage, so the element value is used.
COMBINED_ELEMENT_STATS = frozenset(
    {"Viral", "Blast", "Magnetic", "Corrosive", "Gas", "Radiation"})

# Traits that can change the damage model. Everything else (punch-through,
# projectile speed, ammo, recoil, fire rate under Cannonade) is a "free" line
# or curse for a single-target DPS question.
DAMAGE_STATS = (
    "Damage",
    "Multishot",
    "Critical Chance",
    "Critical Damage",
    "Status Chance",
    "Status Duration",
    "Damage to Grineer",
    "Magazine Capacity",
    "Reload Speed",
    "Heat",
    "Cold",
    "Electricity",
    "Toxin",
)

LAYOUT_COLUMNS = {
    (2, False): "buff_2_pos",
    (3, False): "buff_3_pos",
    (2, True): "buff_2_pos_1_neg",
    (3, True): "buff_3_pos_1_neg",
}
CURSE_COLUMNS = {2: "curse_with_2_pos", 3: "curse_with_3_pos"}

# Curses ranked from harmless to fatal for *this* model. Fire Rate is free only
# because Cannonade locks fire rate (see the module docstring caveat).
FREE_CURSES = ("Ammo Maximum", "Projectile Speed", "Fire Rate / Attack Speed",
               "Weapon Recoil", "Punch Through")
DEFAULT_CURSE = "Ammo Maximum"


def _source_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "source"


@cache
def _load_column(column: str, csv_path: str | None) -> tuple[tuple[str, float], ...]:
    """Read one layout column once; callers get a fresh dict copy."""
    path = Path(csv_path) if csv_path else _source_dir() / _RIVEN_CSV
    out: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["riven_type"] != _RIVEN_TYPE:
                continue
            value = row[column]
            if not value:
                continue
            unit = row["unit"]
            if unit not in {"percent", "plain", "faction_bonus"}:
                raise ValueError(f"unknown Riven table unit {unit!r}")
            out[row["stat_name"]] = float(value) / 100.0 if unit == "percent" else float(value)
    if not out:
        raise ValueError(f"no {_RIVEN_TYPE} rows found in {path}")
    return tuple(out.items())


def load_shotgun_riven_averages(
    column: str = "buff_3_pos_1_neg",
    csv_path: str | Path | None = None,
) -> dict[str, float]:
    """Average Shotgun Riven values from a vendored layout column.

    Percent values are fractions (1.853 == +185.3%), faction values are bonus
    multipliers (+0.51) and plain values keep their units (3.0 m punch-through).
    Traits unavailable in that column (a curse-only sign, or a stat the
    shotgun table does not carry, such as Zoom) are omitted. The parsed table
    is cached; each call returns a fresh dictionary.
    """
    return dict(_load_column(column, str(csv_path) if csv_path else None))


# --- Riven roll --------------------------------------------------------------

@dataclass(frozen=True)
class RivenRoll:
    """One Shotgun Riven roll: its positive traits and optional curse.

    ``positives`` names come from the CSV ``stat_name`` column; a combined
    element (Viral, Corrosive, ...) is a SPLICED trait and counts as one of
    the positive lines. The layout -- and therefore the value column -- is
    inferred from the number of positives and whether a curse is present.
    """

    positives: tuple[str, ...]
    curse: str | None = None

    def __post_init__(self) -> None:
        if not 2 <= len(self.positives) <= 3:
            raise ValueError("a Riven roll needs two or three positive traits, "
                             f"got {self.positives!r}")
        unknown = [name for name in self.positives if name not in RIVEN_CODES]
        if unknown:
            raise ValueError(f"unknown Riven stat names: {unknown}")
        if len(set(self.positives)) != len(self.positives):
            raise ValueError("Riven positive traits must be distinct")
        spliced = [name for name in self.positives if name in COMBINED_ELEMENT_STATS]
        if len(spliced) > 1:
            raise ValueError("only one spliced trait can be on a Riven, "
                             f"got {spliced}")
        if self.curse is not None:
            if self.curse in self.positives:
                raise ValueError("the curse cannot repeat a positive trait")
            curse_column = CURSE_COLUMNS[len(self.positives)]
            if self.curse not in load_shotgun_riven_averages(curse_column):
                raise ValueError(f"{self.curse!r} is not a Shotgun Riven curse "
                                 f"in {curse_column!r}")

    @property
    def has_curse(self) -> bool:
        return self.curse is not None

    @property
    def value_column(self) -> str:
        return LAYOUT_COLUMNS[(len(self.positives), self.has_curse)]

    @property
    def spliced(self) -> bool:
        return any(name in COMBINED_ELEMENT_STATS for name in self.positives)

    def label(self) -> str:
        positives = " / ".join(self.positives)
        return f"+{positives}" + (f", -{self.curse}" if self.curse else "")


def riven_effects(roll: RivenRoll,
                  averages: dict[str, float] | None = None,
                  curse_averages: dict[str, float] | None = None) -> dict[str, float]:
    """The roll as ``{calculator code: value}`` at average grade.

    A spliced combined trait takes the element value from the same column.
    The curse is added as a negative value of its own stat (the CSV stores
    curses as negative percentages, and a Recoil curse as positive recoil).
    """
    values = averages or load_shotgun_riven_averages(roll.value_column)
    effects: dict[str, float] = {}
    for stat in roll.positives:
        key = "Toxin" if stat in COMBINED_ELEMENT_STATS else stat
        if key not in values:
            raise KeyError(f"no shotgun Riven value for {stat!r}")
        code = RIVEN_CODES[stat]
        effects[code] = effects.get(code, 0.0) + values[key]
    if roll.curse is not None:
        curses = curse_averages or load_shotgun_riven_averages(
            CURSE_COLUMNS[len(roll.positives)])
        effects[RIVEN_CODES[roll.curse]] = (
            effects.get(RIVEN_CODES[roll.curse], 0.0) + curses[roll.curse])
    return effects


def fixed_effects() -> dict[str, float]:
    """Max-rank effects of the seven fixed weapon mods."""
    return {
        "TRUE": CANNONADE_DAMAGE,
        "PUNCTHROUGH": CANNONADE_PUNCH_THROUGH,
        "MULTISHOT": GALVANIZED_HELL_MULTISHOT,
        "CRIT_DAMAGE": PRIMED_RAVAGE_CRIT_DAMAGE,
        "CRIT_CHANCE": BLUNDERBUSS_CRIT_CHANCE,
        "COLD": PRIMED_CHILLING_GRASP_COLD,
        "TOXIN": TOXIC_BARRAGE_TOXIN,
        "STATUS_CHANCE": TOXIC_BARRAGE_STATUS,
        "ELEC": PRIMED_CHARGED_SHELL_ELEC,
    }


# --- Build -------------------------------------------------------------------

def corinth_prime_weapon() -> Weapon:
    """The wiki/export stat block as a :class:`Weapon` for the calculator."""
    damage = {kind: 0.0 for kind in (
        "IMPACT", "PUNC", "SLASH", "HEAT", "COLD", "ELEC", "TOXIN", "BLAST",
        "RAD", "GAS", "MAG", "VIRAL", "CORR", "VOID")}
    damage.update(BASE_DAMAGE_BY_TYPE)
    return Weapon(
        weapon=WEAPON_NAME,
        unique_name=WEAPON_UNIQUE_NAME,
        product_category="LongGuns",
        slot_group="PRIMARY",
        dmg=PELLET_DAMAGE,
        critchan=BASE_CRIT_CHANCE,
        critmult=BASE_CRIT_MULTIPLIER,
        statchan=BASE_STATUS_CHANCE,
        firerate=BASE_FIRE_RATE,
        multi=PELLETS,
        damage=damage,
    )


def _mod(name: str, effects: dict[str, float]) -> EquippedMod:
    mod = Mod(
        unique_name=f"/sim/{name}",
        name=name,
        mod_type="",
        compat_name="Shotgun",
        polarity="",
        rarity="",
        fusion_limit=0,
        base_drain=0,
        description="",
        effect_summary="",
        supported=True,
    )
    return EquippedMod(mod=mod, rank=0, effects=[
        ModEffect(code=code, value=value, text="")
        for code, value in effects.items() if value])


def _element_mods(element_layout: str) -> list[EquippedMod]:
    """The three elemental mods in the slot order that fixes their pairing."""
    cold = _mod("Primed Chilling Grasp", {"COLD": PRIMED_CHILLING_GRASP_COLD})
    toxin = _mod("Toxic Barrage", {"TOXIN": TOXIC_BARRAGE_TOXIN,
                                   "STATUS_CHANCE": TOXIC_BARRAGE_STATUS})
    elec = _mod("Primed Charged Shell", {"ELEC": PRIMED_CHARGED_SHELL_ELEC})
    if element_layout == ELEMENT_LAYOUT_VIRAL_ELEC:
        return [cold, toxin, elec]
    if element_layout == ELEMENT_LAYOUT_CORROSIVE_COLD:
        return [toxin, elec, cold]
    raise ValueError(f"unknown element layout {element_layout!r}")


def _equipped(roll: RivenRoll | None,
              effects: dict[str, float],
              element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC) -> list[EquippedMod]:
    """Eight slots in the request's order, with the Riven in slot eight."""
    slots = [
        _mod("Semi-Shotgun Cannonade",
             {"TRUE": CANNONADE_DAMAGE, "PUNCTHROUGH": CANNONADE_PUNCH_THROUGH}),
        _mod("Galvanized Hell", {"MULTISHOT": GALVANIZED_HELL_MULTISHOT}),
        _mod("Primed Ravage", {"CRIT_DAMAGE": PRIMED_RAVAGE_CRIT_DAMAGE}),
        _mod("Blunderbuss", {"CRIT_CHANCE": BLUNDERBUSS_CRIT_CHANCE}),
        *_element_mods(element_layout),
    ]
    if roll is not None:
        slots.append(_mod("Riven", effects))
    else:
        # The un-rivend baseline: the utility mod the Riven would replace.
        slots.append(_mod("Galvanized Acceleration", {"PROJECTILE_SPEED": 0.30}))
    return slots


@dataclass
class CorinthBuild:
    """Resolved stats, element mix and proc weights for one Riven roll."""

    roll: RivenRoll | None
    effects: dict[str, float]
    element_layout: str
    hud_by_type: dict[str, float]      # per pellet, 1/32-quantized
    modded_base: float                 # 90 x (1 + base-damage bonuses)
    crit_chance: float
    crit_multiplier: float
    status_chance: float               # per pellet
    multishot: float                   # pellets per trigger pull
    fire_rate: float
    magazine: int
    reload_time: float
    faction_bonus: float
    status_duration_multiplier: float
    electricity_bonus: float

    @property
    def pellets_per_second(self) -> float:
        return self.multishot * self.fire_rate

    @property
    def proc_weights(self) -> dict[str, float]:
        total = sum(self.hud_by_type.values())
        if total <= 0:
            raise ValueError("this build deals no damage")
        return {kind: value / total for kind, value in self.hud_by_type.items()}

    @property
    def magazine_dps_factor(self) -> float:
        """Magazine uptime: firing time / (firing time + reload)."""
        firing = self.magazine / self.fire_rate
        return firing / (firing + self.reload_time)


def supports_simulation(build: CorinthBuild) -> bool:
    """Whether every proc type this element mix can roll is modelled."""
    return set(build.hud_by_type) <= SUPPORTED_PROC_TYPES


def build_corinth(roll: RivenRoll | None = None, *,
                  riven_values: dict[str, float] | None = None,
                  element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC) -> CorinthBuild:
    """Resolve one Riven roll on top of the seven fixed mods.

    ``element_layout`` selects how the three fixed elemental mods pair:
    ``viral_electric`` (Cold + Toxin -> Viral, Electricity single) or
    ``corrosive_cold`` (Toxin + Electricity -> Corrosive, Cold single).

    ``roll=None`` returns the eight-mod baseline with Galvanized Acceleration
    in place of the Riven. Builds are constructed even when their element mix
    produces a proc this module cannot apply (Blast, Gas, Heat, Cold, Toxin);
    :func:`simulate` refuses those instead, so the analytic ranking still
    covers them (with their proc damage unmodelled).
    """
    effects = fixed_effects()
    riven_fx: dict[str, float] = {}
    if roll is not None:
        curse_column = CURSE_COLUMNS[len(roll.positives)] if roll.has_curse else None
        riven_fx = riven_effects(
            roll,
            riven_values,
            load_shotgun_riven_averages(curse_column) if curse_column else None,
        )
        for code, value in riven_fx.items():
            effects[code] = effects.get(code, 0.0) + value

    results = DamageCalculator().calculate(
        corinth_prime_weapon(),
        CalculationInputs(weapon_name=WEAPON_NAME, faction="Grineer",
                          armor_value=0.0,
                          equipped_mods=_equipped(roll, riven_fx, element_layout)),
    )
    hud = {kind: value for kind, value in results.hud_damage_by_type.items()
           if value > 0}

    multishot = PELLETS * (1.0 + effects.get("MULTISHOT", 0.0)
                           + PRIMARY_OVERCHARGE_MULTISHOT)
    duration_multiplier = 1.0 + effects.get("STATUS_DURATION", 0.0)
    reload_bonus = effects.get("RELOAD_SPEED", 0.0)
    magazine_bonus = effects.get("MAGAZINE_CAPACITY", 0.0)
    return CorinthBuild(
        roll=roll,
        effects=effects,
        element_layout=element_layout,
        hud_by_type=hud,
        modded_base=PELLET_DAMAGE * (1.0 + effects.get("TRUE", 0.0)),
        crit_chance=BASE_CRIT_CHANCE * (1.0 + effects.get("CRIT_CHANCE", 0.0)),
        crit_multiplier=(quantize_crit_multiplier(BASE_CRIT_MULTIPLIER)
                         * (1.0 + effects.get("CRIT_DAMAGE", 0.0))),
        status_chance=BASE_STATUS_CHANCE * (1.0 + effects.get("STATUS_CHANCE", 0.0)),
        multishot=multishot,
        # Cannonade: "Fire Rate cannot be modified" -- the base rate is used
        # even when a Riven carries a Fire Rate trait.
        fire_rate=BASE_FIRE_RATE,
        magazine=max(1, int(math.floor(MAGAZINE * (1.0 + magazine_bonus)))),
        reload_time=RELOAD_TIME / (1.0 + reload_bonus) if reload_bonus > -1 else RELOAD_TIME,
        faction_bonus=effects.get("BANE_GRINEER", 0.0),
        status_duration_multiplier=duration_multiplier,
        electricity_bonus=effects.get("ELEC", 0.0),
    )


# --- Analytic steady-state DPS ----------------------------------------------

@dataclass(frozen=True)
class DpsReport:
    """Steady-state expected DPS split by source."""

    roll: RivenRoll | None
    direct_dps: float
    slash_dps: float
    electric_dps: float
    viral_multiplier: float
    total_dps: float
    sustained_dps: float
    status_types: tuple[str, ...]
    armour: float

    @property
    def label(self) -> str:
        return self.roll.label() if self.roll else "no Riven (Galvanized Acceleration)"


def corrosive_armor_factor(stacks: int) -> float:
    """Multiplier on current armor from Corrosive stacks (26% then +6%)."""
    n = min(max(stacks, 0), CORROSIVE_CAP)
    if n == 0:
        return 1.0
    return 1.0 - (CORROSIVE_FIRST_STACK + CORROSIVE_PER_STACK * (n - 1))


def viral_health_multiplier(stacks: int) -> float:
    """Viral's health-damage multiplier, capped at 10 stacks (4.25x)."""
    if stacks <= 0:
        return 1.0
    return 2.0 + 0.25 * (min(stacks, VIRAL_CAP) - 1)


def _crit_expectation(build: CorinthBuild) -> float:
    """Average critical multiplier: 1 + chance x (CDM - 1)."""
    chance = max(build.crit_chance, 0.0)
    return 1.0 + chance * (build.crit_multiplier - 1.0)


def steady_state_dps(build: CorinthBuild, *,
                     viral_stacks: int | None = None,
                     corrosive_stacks: int = 0,
                     faction: str = "Grineer") -> DpsReport:
    """Expected DPS with Viral (and, if any, Corrosive) already saturated.

    This is a ranking aid, not a time-to-kill: it assumes the status ramp is
    already complete and that every pellet hits one target at full damage.
    Direct hits use the audited per-type armor and faction modifiers; DoT
    ticks use their own coefficients and the same faction modifier once more
    (the deliberate Bane double dip). ``viral_stacks=None`` saturates Viral
    only when the build actually deals Viral damage, so a Corrosive + Cold
    layout is not credited with a Viral amplifier it cannot apply.
    """
    types = FACTION_MULTIPLIERS[faction]
    armor = steel_path_heavy_gunner(150).armor * corrosive_armor_factor(corrosive_stacks)
    armor_multiplier = enemy_armor_damage_multiplier(armor)
    crit = _crit_expectation(build)
    bane = 1.0 + build.faction_bonus
    if viral_stacks is None:
        viral_stacks = VIRAL_CAP if "VIRAL" in build.hud_by_type else 0
    viral = viral_health_multiplier(viral_stacks)
    pellets_per_second = build.pellets_per_second

    direct = sum(value * armor_multiplier * types[kind] for kind, value
                 in build.hud_by_type.items()) * crit * bane * viral
    direct_dps = direct * pellets_per_second

    weights = build.proc_weights
    procs_per_second = pellets_per_second * build.status_chance
    seed = build.modded_base * bane * crit
    # Six ticks per proc, one accumulator per tick group; the per-proc "+1"
    # of the wiki formula is omitted here because it is negligible at these
    # seed sizes and this is a steady-state estimate.
    slash_dps = (procs_per_second * weights.get("SLASH", 0.0) * 6.0 * 0.35
                 * seed * bane * viral)
    electric_dps = (procs_per_second * weights.get("ELEC", 0.0) * 6.0 * 0.5
                    * seed * bane
                    * (1.0 + build.electricity_bonus)
                    * armor_multiplier * types.get("ELEC", 1.0) * viral)
    total = direct_dps + slash_dps + electric_dps
    return DpsReport(
        roll=build.roll,
        direct_dps=direct_dps,
        slash_dps=slash_dps,
        electric_dps=electric_dps,
        viral_multiplier=viral,
        total_dps=total,
        sustained_dps=total * build.magazine_dps_factor,
        status_types=tuple(sorted(build.hud_by_type)),
        armour=armor,
    )


# --- Target ------------------------------------------------------------------

ARMOR_CURVE_AUDITED = "audited"
ARMOR_CURVE_LINEAR = "linear"
ARMOR_CURVES = (ARMOR_CURVE_AUDITED, ARMOR_CURVE_LINEAR)


def equivalent_armor(armor: float) -> float:
    """Armor whose audited DR equals ``armor / (armor + 300)``.

    ``docs/formula_audit.md`` records that the Armor page gives the square-root
    formula at or below 2,700 and ``armor / (armor + 300)`` above it; the two
    branches agree only at 2,700. :data:`ARMOR_CURVE_LINEAR` is a sensitivity
    switch, not a second model: it maps the live armor value onto the audited
    curve so that the *fraction of damage that survives* matches the linear
    reading, which isolates how much a conclusion depends on that branch.
    """
    if armor <= 0:
        return 0.0
    remaining = 300.0 / (armor + 300.0)
    return min(2700.0, max(0.0, 2700.0 * ((1.0 - remaining) / 0.9) ** 2))


class CorinthTarget(DummyTarget):
    """Plain SP150 Heavy Gunner plus Corrosive, Electricity and Bleed state."""

    def __init__(self, health: float, armor: float, overguard: float = 0.0,
                 *, boss: bool = False, armor_curve: str = ARMOR_CURVE_AUDITED):
        if armor_curve not in ARMOR_CURVES:
            raise ValueError(f"unknown armor curve {armor_curve!r}")
        super().__init__(health, armor, overguard, boss=boss)
        self.armor_curve = armor_curve
        self.corrosive_expiries: list[float] = []
        self.electric_procs: list[DoTProc] = []
        self.bleed_procs: list[DoTProc] = []

    def corrosive_stacks(self, now: float) -> int:
        self.corrosive_expiries = [t for t in self.corrosive_expiries if t > now]
        return len(self.corrosive_expiries)

    def add_corrosive(self, when: float, duration: float) -> None:
        if duration <= 0:
            return
        self.corrosive_stacks(when)
        self.corrosive_expiries.append(when + duration)
        self.corrosive_expiries = self.corrosive_expiries[-CORROSIVE_CAP:]
        self.record_status("CORR", when, duration)

    def current_armor(self, now: float, ramp_interval: float) -> float:
        """Heat's strip (none here) times Corrosive's multiplicative strip."""
        heat_armor = super().current_armor(now, ramp_interval)
        armor = heat_armor * corrosive_armor_factor(self.corrosive_stacks(now))
        return equivalent_armor(armor) if self.armor_curve == ARMOR_CURVE_LINEAR else armor


@dataclass
class DoTProc:
    """One damaging status effect with its own tick clock.

    ``first_tick`` is the delay before the first tick (0 s for Electricity,
    1 s for Slash), and ``ticks`` is the number of damaging pulses.
    """

    start: float
    seed: float
    crit_factor: float
    first_tick: float = 0.0
    ticks: int = 6
    next_tick: float = field(init=False)

    def __post_init__(self) -> None:
        self.next_tick = self.start + self.first_tick

    def last_tick(self, duration: float) -> float:
        return self.start + self.first_tick + (self.ticks - 1) * 1.0

    def live(self, now: float, duration: float) -> bool:
        return self.next_tick <= min(self.last_tick(duration), now)


@dataclass
class CorinthTrial:
    ttk: float
    shots: int
    pellets: int
    reloads: int
    viral_procs: int
    corrosive_procs: int
    electric_procs: int
    bleed_procs: int
    final_viral_stacks: int
    final_corrosive_stacks: int
    final_armor: float
    overguard_max: float = 0.0
    overguard_break: float = math.inf
    cold_procs: int = 0
    magnetic_procs: int = 0
    final_cold_stacks: int = 0
    final_magnetic_stacks: int = 0
    trace: list[str] = field(default_factory=list)


def corinth_dummy_factory(armor_curve: str = ARMOR_CURVE_AUDITED,
                          target: str = TARGET_PLAIN) -> CorinthTarget:
    """Fresh SP150 Heavy Gunner for one trial.

    ``TARGET_PLAIN`` (the default, so the benchmark digest stays stable) is
    286,139.57 HP / 2,700 armor with no Overguard. ``TARGET_EXIMUS`` is the
    Eximus variant: 1,716,837.41 HP / 2,700 armor behind 269,918.97 Overguard.
    The CLI defaults to the Eximus target; see :data:`TARGETS`.
    """
    if target not in TARGETS:
        raise ValueError(f"unknown target {target!r}")
    enemy = (steel_path_eximus_heavy_gunner(150) if target == TARGET_EXIMUS
             else steel_path_heavy_gunner(150))
    return CorinthTarget(enemy.health, enemy.armor, enemy.overguard,
                         armor_curve=armor_curve)


# --- Trial -------------------------------------------------------------------

def _crit_factor(rng: random.Random, build: CorinthBuild,
                 target: CorinthTarget, when: float) -> float:
    """Critical-damage factor for one pellet, with live Puncture stacks."""
    chance = max(build.crit_chance + PUNCTURE_CRIT_PER_STACK
                 * target.puncture_stacks(when), 0.0)
    tiers = int(math.floor(chance))
    tier = tiers + (1 if rng.random() < chance - tiers else 0)
    return crit_multiplier_for_tier(
        target.crit_damage_multiplier(build.crit_multiplier, when), tier)


def simulate(build: CorinthBuild,
             target: CorinthTarget,
             *,
             seed: int = 1,
             max_time: float = 120.0,
             trace: bool = False) -> CorinthTrial:
    """Fire until the dummy dies or ``max_time`` elapses.

    Every pellet rolls its own critical tier and status chance; status types
    are drawn from the pellet's damage distribution. DoT ticks are settled at
    their own application-relative times, before the next shot.
    """
    if not supports_simulation(build):
        unsupported = sorted(set(build.hud_by_type) - SUPPORTED_PROC_TYPES)
        raise ValueError(
            f"{build.roll.label() if build.roll else 'baseline'}: proc type(s) "
            f"{unsupported} are not modelled by this simulator")
    rng = random.Random(seed)
    gunner_types = FACTION_MULTIPLIERS["Grineer"]
    proc_duration = PROC_DURATION * build.status_duration_multiplier
    corrosive_duration = CORROSIVE_DURATION * build.status_duration_multiplier
    puncture_duration = PUNCTURE_DURATION * build.status_duration_multiplier
    faction = 1.0 + build.faction_bonus
    magnetic_source = MagneticSource(
        faction_bonus=build.faction_bonus,
        electricity_bonus=build.electricity_bonus,
        duration_multiplier=build.status_duration_multiplier,
    )
    proc_types = list(build.proc_weights)
    proc_weights = list(build.proc_weights.values())

    now = 0.0
    ammo = build.magazine
    shots = pellets_fired = reloads = 0
    counts = {"VIRAL": 0, "CORR": 0, "ELEC": 0, "SLASH": 0, "COLD": 0, "MAG": 0}
    log: list[str] = []

    def route(damage: dict[str, float], when: float, *, bypass: bool = False) -> None:
        target.prune(when, proc_duration)
        target.absorb(damage, when, HEAT_RAMP_INTERVAL,
                      faction_type_modifiers=gunner_types,
                      armor_bypass=bypass)

    def settle_dots(until: float) -> float | None:
        """Apply every DoT tick due at or before ``until``, in time order."""
        while target.health > 0:
            # The Electricity released by an Overguard break has its own clock
            # and is applied inside the target, so it is settled first.
            magnetic_due = target.next_magnetic_electric_tick()
            due_time = magnetic_due
            for procs, duration in ((target.electric_procs, proc_duration),
                                    (target.bleed_procs, proc_duration)):
                for proc in procs:
                    if proc.next_tick <= proc.last_tick(duration):
                        due_time = min(due_time, proc.next_tick)
            if due_time > until:
                return None
            if magnetic_due == due_time:
                target.process_magnetic_electric_until(
                    due_time, HEAT_RAMP_INTERVAL,
                    faction_type_modifiers=gunner_types)
                if target.health <= 0:
                    return due_time
                continue
            for procs, duration, kind, bypass in (
                    (target.electric_procs, proc_duration, "ELEC", False),
                    (target.bleed_procs, proc_duration, "SLASH", True)):
                due = [p for p in procs
                       if p.next_tick == due_time and p.next_tick <= p.last_tick(duration)]
                if not due:
                    continue
                seeds = sum(p.seed * p.crit_factor for p in due)
                for proc in due:
                    proc.next_tick += 1.0
                procs[:] = [p for p in procs
                            if p.next_tick <= p.last_tick(duration)]
                if kind == "ELEC":
                    tick = electricity_tick(
                        seeds,
                        elemental_bonus=build.electricity_bonus,
                        faction_bonus=build.faction_bonus,
                        accumulator=True)
                else:
                    tick = slash_tick(seeds,
                                      faction_bonus=build.faction_bonus,
                                      accumulator=True)
                route({kind: tick}, due_time, bypass=bypass)
                if target.health <= 0:
                    return due_time
        return None

    while now < max_time and target.health > 0:
        if ammo <= 0:
            reloads += 1
            reload_end = now + build.reload_time
            death = settle_dots(min(reload_end, max_time))
            if death is not None:
                now = death
                break
            if reload_end >= max_time:
                now = max_time
                break
            now = reload_end
            ammo = build.magazine
            continue

        death = settle_dots(now)
        if death is not None:
            now = death
            break

        shots += 1
        ammo -= 1
        for _ in range(roll_multishot(rng, build.multishot)):
            pellets_fired += 1
            crit = _crit_factor(rng, build, target, now)
            route({kind: value * crit * faction
                   for kind, value in build.hud_by_type.items()}, now)
            if target.health <= 0:
                break

            chance = build.status_chance
            guaranteed = int(math.floor(chance))
            rolls = guaranteed + (1 if rng.random() < chance - guaranteed else 0)
            for ptype in rng.choices(proc_types, weights=proc_weights, k=rolls):
                counts[ptype] = counts.get(ptype, 0) + 1
                if ptype == "VIRAL":
                    target.record_status("VIRAL", now, proc_duration)
                    target.viral_expiries.append(now + proc_duration)
                    target.viral_expiries = target.viral_expiries[-VIRAL_CAP:]
                elif ptype == "CORR":
                    target.add_corrosive(now, corrosive_duration)
                elif ptype == "PUNC":
                    target.add_puncture(now, puncture_duration,
                                        max_stacks=PUNCTURE_CAP)
                elif ptype == "COLD":
                    # Cold raises Critical Damage per stack and caps at four
                    # while Overguard stands; the target owns that state.
                    target.record_status(ptype, now, proc_duration)
                elif ptype == "MAG":
                    target.add_magnetic(now, proc_duration, magnetic_source)
                elif ptype in {"IMPACT", "RAD"}:
                    # No single-target damage effect: Impact staggers and
                    # Radiation only confuses other enemies.
                    target.record_status(ptype, now, proc_duration)
                else:
                    # Seed without the crit factor: ``DoTProc`` carries the
                    # pellet's crit multiplier separately and every tick
                    # applies it once (``seed * crit_factor``), as the other
                    # simulators do.
                    proc_seed = build.modded_base * faction
                    if ptype == "ELEC":
                        target.record_status(ptype, now, proc_duration)
                        target.electric_procs.append(
                            DoTProc(now, proc_seed, crit, first_tick=0.0))
                    elif ptype == "SLASH":
                        target.record_status(ptype, now, proc_duration)
                        target.bleed_procs.append(
                            DoTProc(now, proc_seed, crit, first_tick=1.0))
                if target.health <= 0:
                    break
            if target.health <= 0:
                break
            settle_dots(now)

        if target.health <= 0:
            break
        now += 1.0 / build.fire_rate
        if trace and shots % 5 == 0:
            log.append(
                f"t={now:6.2f}s hp={max(target.health, 0):10.0f} "
                f"viral={target.viral_stacks(now):2d} "
                f"corr={target.corrosive_stacks(now):2d} "
                f"armor={target.current_armor(now, HEAT_RAMP_INTERVAL):6.0f}")

    if target.health > 0 and now >= max_time:
        death = settle_dots(max_time)
        now = death if death is not None else max_time
    ttk = now if target.health <= 0 else math.inf
    if target.overguard_max <= 0:
        break_time = 0.0
    elif target.overguard_broken_at is not None:
        break_time = target.overguard_broken_at
    else:
        break_time = math.inf
    return CorinthTrial(
        ttk=ttk,
        shots=shots,
        pellets=pellets_fired,
        reloads=reloads,
        viral_procs=counts["VIRAL"],
        corrosive_procs=counts["CORR"],
        electric_procs=counts["ELEC"],
        bleed_procs=counts["SLASH"],
        final_viral_stacks=target.viral_stacks(ttk if math.isfinite(ttk) else now),
        final_corrosive_stacks=target.corrosive_stacks(
            ttk if math.isfinite(ttk) else now),
        final_armor=target.current_armor(ttk if math.isfinite(ttk) else now,
                                         HEAT_RAMP_INTERVAL),
        overguard_max=target.overguard_max,
        overguard_break=break_time,
        cold_procs=counts["COLD"],
        magnetic_procs=counts["MAG"],
        final_cold_stacks=target.cold_stacks(
            ttk if math.isfinite(ttk) else now),
        final_magnetic_stacks=target.mag_stacks(
            ttk if math.isfinite(ttk) else now),
        trace=log,
    )


def run_trials(roll: RivenRoll | None,
               trials: int = 200,
               *,
               base_seed: int = 20261112,
               armor_curve: str = ARMOR_CURVE_AUDITED,
               target: str = TARGET_PLAIN,
               element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC,
               factory=None) -> dict:
    """Run ``trials`` seeded fights for one roll and summarize the TTKs.

    ``target`` selects the plain or Eximus Heavy Gunner; a custom ``factory``
    overrides it. Overguard break times are summarized only when the target
    has Overguard, and fights that never break it report ``inf``.
    """
    if trials < 1:
        raise ValueError("trials must be positive")
    build = build_corinth(roll, element_layout=element_layout)
    spawn = factory or (lambda: corinth_dummy_factory(armor_curve, target))
    ttks: list[float] = []
    reloads: list[float] = []
    viral: list[float] = []
    corrosive: list[float] = []
    breaks: list[float] = []
    cold: list[float] = []
    magnetic: list[float] = []
    overguard_max = 0.0
    for index in range(trials):
        foe = spawn()
        overguard_max = max(overguard_max, foe.overguard_max)
        result = simulate(build, foe, seed=base_seed + index)
        if math.isfinite(result.ttk):
            ttks.append(result.ttk)
            reloads.append(result.reloads)
            viral.append(result.final_viral_stacks)
            corrosive.append(result.final_corrosive_stacks)
            cold.append(result.final_cold_stacks)
            magnetic.append(result.final_magnetic_stacks)
            if math.isfinite(result.overguard_break):
                breaks.append(result.overguard_break)
    return {
        "roll": roll,
        "build": build,
        "target": target,
        "element_layout": element_layout,
        "overguard_max": overguard_max,
        "trials": len(ttks),
        "trials_attempted": trials,
        "timed_out": trials - len(ttks),
        "ttk_median": sample_percentile(ttks, 0.5, empty=math.inf),
        "ttk_mean": (sum(ttks) / len(ttks)) if ttks else math.inf,
        "ttk_p90": sample_percentile(ttks, 0.9, empty=math.inf),
        "reloads_median": sample_percentile(reloads, 0.5),
        "viral_median": sample_percentile(viral, 0.5),
        "corrosive_median": sample_percentile(corrosive, 0.5),
        "cold_median": sample_percentile(cold, 0.5),
        "magnetic_median": sample_percentile(magnetic, 0.5),
        "overguard_break_median": (sample_percentile(breaks, 0.5, empty=math.inf)
                                   if overguard_max > 0 else 0.0),
        "overguard_break_mean": ((sum(breaks) / len(breaks)) if breaks
                                 else math.inf if overguard_max > 0 else 0.0),
    }


# --- Candidate sweeps --------------------------------------------------------

def candidate_rolls(positives: int = 3,
                    curse: str | None = DEFAULT_CURSE,
                    *, include_spliced: bool = True,
                    stats: tuple[str, ...] = DAMAGE_STATS) -> list[RivenRoll]:
    """Every roll worth ranking for a this-many-positive layout.

    Non-spliced rolls draw ``positives`` traits from ``stats``; spliced rolls
    replace one line with a combined element, keeping the same layout size.
    """
    import itertools

    rolls: list[RivenRoll] = []
    for combo in itertools.combinations(stats, positives):
        try:
            rolls.append(RivenRoll(combo, curse))
        except ValueError:
            continue
    if include_spliced:
        for spliced in sorted(COMBINED_ELEMENT_STATS):
            for combo in itertools.combinations(stats, positives - 1):
                # Splicing preserves the layout: the consumed pair becomes the
                # combined trait plus a re-rollable line, so the roll still
                # has ``positives`` lines and the others may be anything.
                rolls.append(RivenRoll((spliced, *combo), curse))
    return rolls


def rank_rolls(rolls: list[RivenRoll], *,
               viral_stacks: int | None = None,
               corrosive_stacks: int = 0,
               element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC
               ) -> list[DpsReport]:
    """Rank rolls by steady-state DPS under the given saturation."""
    reports = []
    for roll in rolls:
        build = build_corinth(roll, element_layout=element_layout)
        reports.append(steady_state_dps(build, viral_stacks=viral_stacks,
                                        corrosive_stacks=corrosive_stacks))
    reports.sort(key=lambda report: -report.total_dps)
    return reports


def rank_by_ttk(rolls: list[RivenRoll | None], trials: int = 200, *,
                base_seed: int = 20261112,
                armor_curve: str = ARMOR_CURVE_AUDITED,
                target: str = TARGET_PLAIN,
                element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC) -> list[dict]:
    """Rank rolls by simulated mean TTK against the SP150 Heavy Gunner.

    Rolls whose element mix can proc a status this module does not model are
    skipped. Mean TTK is the sort key because the trigger clock quantizes
    every kill to a shot time, which makes the median jump a whole pull.
    """
    results = [run_trials(roll, trials, base_seed=base_seed,
                          armor_curve=armor_curve, target=target,
                          element_layout=element_layout)
               for roll in rolls
               if supports_simulation(build_corinth(
                   roll, element_layout=element_layout))]
    results.sort(key=lambda result: (result["ttk_mean"], result["ttk_median"]))
    return results


# --- CLI ---------------------------------------------------------------------

def _format_row(cells: list[str], widths: list[int]) -> str:
    return "  ".join(cell.rjust(width) for cell, width in zip(cells, widths, strict=True))


def _print_target_summary(target: str) -> None:
    enemy = (steel_path_eximus_heavy_gunner(150) if target == TARGET_EXIMUS
             else steel_path_heavy_gunner(150))
    print(f"Target: {TARGET_LABELS[target]}")
    print(f"  {enemy.health:,.0f} HP at {enemy.armor:,.0f} armor "
          f"({enemy.armor_dr:.0%} reduction), "
          f"{enemy.overguard:,.0f} Overguard, faction Grineer")
    print()


def _print_build_summary(
        element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC) -> CorinthBuild:
    baseline = build_corinth(None, element_layout=element_layout)
    print(f"Build: {WEAPON_NAME}, {PELLETS:g} pellets x "
          f"{1.0 + GALVANIZED_HELL_MULTISHOT + PRIMARY_OVERCHARGE_MULTISHOT:.2f} "
          f"multishot = {baseline.multishot:.1f} pellets per trigger pull")
    print(f"  fire rate {baseline.fire_rate:.4f}/s (Cannonade lock), "
          f"magazine {baseline.magazine}, reload {baseline.reload_time:.2f} s")
    print(f"  crit {baseline.crit_chance:.1%} at {baseline.crit_multiplier:.3f}x, "
          f"status {baseline.status_chance:.1%}/pellet, "
          f"modded base {baseline.modded_base:.1f}, "
          f"per-pellet {sum(baseline.hud_by_type.values()):.1f}")
    print(f"  elements: {ELEMENT_LAYOUT_LABELS[element_layout]} "
          f"({', '.join(sorted(baseline.hud_by_type))})")
    print(f"  un-rivend steady-state DPS (Viral saturated, no Corrosive): "
          f"{steady_state_dps(baseline).total_dps:,.0f}")
    print()
    return baseline


def _print_analytic(top: int, element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC
                    ) -> list[RivenRoll]:
    winners: list[RivenRoll] = []
    for positives in (3, 2):
        rolls = candidate_rolls(positives)
        ranked = rank_rolls(rolls, element_layout=element_layout)
        print(f"== Analytic steady-state DPS: {positives} positives + 1 curse "
              f"({len(rolls)} rolls)")
        widths = [74, 12, 14, 12]
        print(_format_row(["roll", "DPS", "DPS at 10 Corr", "sustained"], widths))
        for report in ranked[:top]:
            strip = steady_state_dps(
                build_corinth(report.roll, element_layout=element_layout),
                corrosive_stacks=CORROSIVE_CAP)
            print(_format_row([report.label, f"{report.total_dps:,.0f}",
                               f"{strip.total_dps:,.0f}",
                               f"{report.sustained_dps:,.0f}"], widths))
        # Keep the leading spliced trait in the Monte Carlo set even when it
        # does not crack the analytic top rows: it is the question the
        # Splicer raises, and armor stripping only shows up from a cold start.
        leading_spliced = next((report for report in ranked
                                if report.roll is not None and report.roll.spliced),
                               None)
        top_labels = {report.label for report in ranked[:top]}
        if leading_spliced is not None and leading_spliced.label not in top_labels:
            strip = steady_state_dps(
                build_corinth(leading_spliced.roll,
                              element_layout=element_layout),
                corrosive_stacks=CORROSIVE_CAP)
            print(_format_row([leading_spliced.label + "   [leading spliced]",
                               f"{leading_spliced.total_dps:,.0f}",
                               f"{strip.total_dps:,.0f}",
                               f"{leading_spliced.sustained_dps:,.0f}"], widths))
            if leading_spliced.roll is not None:
                winners.append(leading_spliced.roll)
        winners.extend(report.roll for report in ranked[:top]
                       if report.roll is not None)
        print()
    return winners


def _print_trials(rolls: list[RivenRoll | None], trials: int, seed: int,
                  armor_curve: str, title: str,
                  target: str = TARGET_PLAIN,
                  element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC) -> list[dict]:
    results = rank_by_ttk(rolls, trials, base_seed=seed,
                          armor_curve=armor_curve, target=target,
                          element_layout=element_layout)
    print(f"== {title} ({trials} seeded trials per roll)")
    overguarded = any(result["overguard_max"] > 0 for result in results)
    header = ["roll", "mean", "median", "p90"]
    widths = [68, 9, 9, 9]
    if overguarded:
        header.append("OG break")
        widths.append(10)
    header += ["viral", "corr", "cold", "mag"]
    widths += [6, 6, 6, 6]
    print(_format_row(header, widths))
    for result in results:
        cells = [
            result["roll"].label() if result["roll"] else "no Riven",
            f"{result['ttk_mean']:.2f} s",
            f"{result['ttk_median']:.2f} s",
            f"{result['ttk_p90']:.2f} s",
        ]
        if overguarded:
            cells.append(f"{result['overguard_break_median']:.2f} s")
        cells.extend([f"{result['viral_median']:.0f}",
                      f"{result['corrosive_median']:.0f}",
                      f"{result['cold_median']:.0f}",
                      f"{result['magnetic_median']:.0f}"])
        print(_format_row(cells, widths))
    print()
    return results


def _print_curses(roll: RivenRoll, trials: int, seed: int,
                  target: str = TARGET_PLAIN,
                  element_layout: str = ELEMENT_LAYOUT_VIRAL_ELEC) -> None:
    print(f"== Curse ranking for +{' / '.join(roll.positives)} "
          f"({trials} seeded trials each)")
    rows: list[tuple[float, str, float]] = []
    curse_column = CURSE_COLUMNS[len(roll.positives)]
    for curse in load_shotgun_riven_averages(curse_column):
        if curse in roll.positives:
            continue
        candidate = RivenRoll(roll.positives, curse)
        build = build_corinth(candidate, element_layout=element_layout)
        if not supports_simulation(build):
            continue
        report = steady_state_dps(build)
        result = run_trials(candidate, trials, base_seed=seed, target=target,
                            element_layout=element_layout)
        rows.append((result["ttk_mean"], curse, report.total_dps))
    rows.sort()
    widths = [24, 10, 12]
    print(_format_row(["curse", "mean TTK", "analytic DPS"], widths))
    for mean, curse, dps in rows:
        print(_format_row([f"-{curse}", f"{mean:.2f} s", f"{dps:,.0f}"], widths))
    print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=400,
                        help="seeded trials per roll in the Monte Carlo tables")
    parser.add_argument("--top", type=int, default=8,
                        help="rows kept from each analytic table")
    parser.add_argument("--seed", type=int, default=20261112,
                        help="base seed for the Monte Carlo trials")
    parser.add_argument("--sensitivity", action="store_true",
                        help="also run the linear armor-curve sensitivity table")
    parser.add_argument("--curses", action="store_true",
                        help="also rank the curses for the leading roll")
    parser.add_argument("--target", choices=TARGETS, default=TARGET_EXIMUS,
                        help="enemy variant: the Eximus Heavy Gunner with "
                             "Overguard (default) or the plain one")
    parser.add_argument("--elements", choices=ELEMENT_LAYOUTS,
                        default=ELEMENT_LAYOUT_VIRAL_ELEC,
                        help="pairing of the three elemental mods: Viral + "
                             "Electricity (default) or Corrosive + Cold")
    args = parser.parse_args(argv)
    label = TARGET_LABELS[args.target]
    _print_target_summary(args.target)
    _print_build_summary(args.elements)
    winners = _print_analytic(args.top, args.elements)
    rolls: list[RivenRoll | None] = list(dict.fromkeys(winners))
    if None not in rolls:
        rolls.insert(0, None)
    results = _print_trials(
        rolls, args.trials, args.seed, ARMOR_CURVE_AUDITED,
        f"Monte Carlo TTK, {label}, audited armor curve", args.target,
        args.elements)
    if args.sensitivity:
        _print_trials(rolls, args.trials, args.seed, ARMOR_CURVE_LINEAR,
                      "Sensitivity: same rolls on the linear armor reading",
                      args.target, args.elements)
    if args.curses:
        _print_curses(results[0]["roll"], args.trials, args.seed, args.target,
                      args.elements)


if __name__ == "__main__":
    main()
