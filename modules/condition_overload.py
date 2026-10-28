"""Condition Overload-type ("GunCO") stacking behavior.

Implements the rules documented on the WARFRAME wiki page
``Condition_Overload_(Mechanic)`` (last edited 2026-10-05, retrieved
2026-10-27). The curated dataset lives in ``source/gunco_mechanic.json``;
its TS cross-reference is vendored at ``source/conditionOverload.ts``.

Two stacking modes exist for CO-type bonuses (Condition Overload,
Galvanized Aptitude/Shot/Savvy, Secondary Shiver, ...):

* ``multiply`` (wiki behavior #1, mostly projectiles, not the intended design)::

      damage = base * most_damage_bonuses * (1 + co_bonus * scale) * other_multipliers

* ``add`` (wiki behaviors #2-#4, intended, most hitscan weapons)::

      damage = base * (most_damage_bonuses * other_multipliers + co_bonus * scale)

* ``none`` (wiki behavior #5): the attack (almost always an explosion radius)
  receives no CO-type bonus at all.

``scale`` mirrors the wiki's "CO bonus relative to base damage" column:
charged shots that only count the uncharged base (bows 0.5, Ballistica 0.25),
child projectiles that count the parent's damage (Kulstar 2.67), and so on.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

GUNCO_FILE = "gunco_mechanic.json"

MODE_MULTIPLY = "multiply"
MODE_ADD = "add"
MODE_NONE = "none"
VALID_MODES = frozenset({MODE_MULTIPLY, MODE_ADD, MODE_NONE})

SOURCE_WIKI = "wiki"
SOURCE_SHEET = "gunco_sheet"
SOURCE_DEFAULT = "default"

_DIRECT_ONLY_NOTE = (
    "Only on the enemy the hitscan shot hits directly, "
    "and scales off the hitscan damage"
)
_PROJECTILE_AOE_NOTE = "Projectile explosion radius doesn't get CO"


@dataclass(frozen=True)
class CoBehavior:
    """How a CO-type bonus applies to one weapon attack."""

    mode: str
    scale: float
    source: str
    note: Optional[str]
    matched: bool  # True = explicit catalog rule, False = default resolution

    @property
    def is_multiplicative(self) -> bool:
        return self.mode == MODE_MULTIPLY


def _default_path() -> Path:
    candidates = [Path(__file__).resolve().parent.parent / "source" / GUNCO_FILE]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "source" / GUNCO_FILE)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_gunco_dataset(path: Optional[str | Path] = None) -> dict:
    """Load the full GunCO dataset (meta, formulas, CO sources, rules)."""
    dataset_path = Path(path) if path else _default_path()
    with dataset_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or "rules" not in data or not data["rules"]:
        raise ValueError(f"GunCO data at {dataset_path} is empty or malformed")
    return data


def resolve_co_behavior(
    weapon_name: str,
    attack_name: str,
    *,
    is_aoe: bool = False,
    hitscan_aoe: bool = False,
    section: Optional[str] = None,
    dataset: Optional[dict] = None,
) -> CoBehavior:
    """Resolve how CO-type bonuses apply to a weapon attack.

    Mirrors the wiki Attack Catalog and the cross-referenced TS resolver:

    1. An explicit catalog rule (weapon name + attack-name regex) wins.
    2. Otherwise, an unlisted hitscan/beam AoE is additive on the directly
       hit enemy only.
    3. An unlisted projectile explosion radius gets nothing.
    4. Every other unlisted attack is the intended additive +100% behavior.

    ``section`` optionally restricts the catalog lookup (``"primary"``,
    ``"secondary"``, ``"melee"``, ``"exalted"``, ``"archgun"``, ``"robotic"``
    or ``"amp"``); needed for kitgun chamber names that exist in both weapon
    slots (Sporelacer, Tombfinger). Without it, the first catalog match wins,
    which is the primary-section row.
    """
    data = dataset if dataset is not None else load_gunco_dataset()
    for rule in data["rules"]:
        if section is not None and rule["section"] != section:
            continue
        if weapon_name not in rule["weapons"]:
            continue
        if re.search(rule["attack_pattern"], attack_name):
            return CoBehavior(
                mode=rule["mode"],
                scale=float(rule["scale"]),
                source=rule["source"],
                note=rule["note"],
                matched=True,
            )
    if hitscan_aoe:
        return CoBehavior(MODE_ADD, 1.0, SOURCE_DEFAULT, _DIRECT_ONLY_NOTE, False)
    if is_aoe:
        return CoBehavior(MODE_NONE, 1.0, SOURCE_DEFAULT, _PROJECTILE_AOE_NOTE, False)
    return CoBehavior(MODE_ADD, 1.0, SOURCE_DEFAULT, None, False)


def co_bonus_for_statuses(per_status: float, status_count: int,
                          cap: Optional[float] = None) -> float:
    """Total CO-type damage fraction from one CO source.

    ``per_status`` e.g. 0.4 for Galvanized Aptitude, 0.8 for Condition
    Overload. ``cap`` is the maximum bonus *per status type* (e.g. 0.8
    for Galvanized Aptitude at two kill stacks), not a cap on the total.
    Returns 0.0 for zero statuses.
    """
    if status_count < 0:
        raise ValueError("status_count must be non-negative")
    if cap is not None:
        per_status = min(per_status, cap)
    return per_status * status_count


def apply_co(
    base_damage: float,
    co_bonus: float,
    damage_bonus_mult: float,
    other_multipliers: float = 1.0,
    *,
    mode: str = MODE_ADD,
    scale: float = 1.0,
) -> float:
    """Final damage of one attack given its resolved CO behavior.

    ``co_bonus`` is the summed CO-type bonus fraction (e.g. 0.8 for one
    status under Condition Overload). ``damage_bonus_mult`` is the pooled
    ordinary +% damage multiplier including base (Serration 1.65 -> 2.65).
    In additive mode ``other_multipliers`` applies only to the ordinary term,
    for effects the wiki says that CO ignores; apply shared final multipliers
    to the returned result. ``scale`` applies to the CO term in both modes.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"unknown CO mode {mode!r}; expected one of {sorted(VALID_MODES)}")
    if mode == MODE_NONE:
        return base_damage * damage_bonus_mult * other_multipliers
    if mode == MODE_MULTIPLY:
        return (
            base_damage
            * damage_bonus_mult
            * (1.0 + co_bonus * scale)
            * other_multipliers
        )
    # additive: CO joins the ordinary damage-bonus pool, scaled per attack
    return (
        base_damage
        * (damage_bonus_mult * other_multipliers + co_bonus * scale)
    )


def multiplicative_rules(section: Optional[str] = None,
                         dataset: Optional[dict] = None) -> list[dict]:
    """All catalog rules that stack CO multiplicatively (the user's tables)."""
    data = dataset if dataset is not None else load_gunco_dataset()
    return [
        rule for rule in data["rules"]
        if rule["mode"] == MODE_MULTIPLY and (section is None or rule["section"] == section)
    ]
