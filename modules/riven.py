"""Riven mod stat engine.

The per-tag base values in ``source/riven_tags.json`` and the formula below are
a Python port of the community-verified RivenParser.js
(https://github.com/calamity-inc/warframe-riven-info), which reproduces the
in-game values of Digital Extremes' Riven ``upgradeEntries`` tables. The port is
verified against real unveiled Rivens (see ``tests/test_riven.py`` and the
upstream ``test.js`` fingerprints) and against the WARFRAME Wiki's rank-8 range
tables and "Attribute Value Formula" (see ``tests/test_riven_wiki.py``;
https://wiki.warframe.com/w/Riven_Mods).

Value model (all factors multiplied together):

    raw = tag_base_value
          * (1.5 * disposition * 10)        # SPECIFIC_FIT_ATTENUATION x RIVEN_BASE_DRAIN
          * 1.25 ** num_negative_stats      # a curse makes the positive stats bigger
          * grade_factor                    # lerp(0.9, 1.1, roll), average roll = 1.0
          * num_buffs_atten[num_positive]   # more combined stats -> smaller each stat
          * (rank + 1)                      # Riven ranks 0..8 -> x1 .. x9

The wiki presents the same layout weights with the 1.5 specific-fit factor
folded in: 2/0 = 0.99, 2/1 = 1.2375, 3/0 = 0.75, 3/1 = 0.9375 bonus, and
-0.495 / -0.75 for the malus columns (i.e. 1.5 x the layout factors here,
within float32 rounding). The negative ("curse") stat uses its own attenuation
arrays; see :func:`curse_layout_factor`.

Since Hotfix 44.1.3 (2026-10-22) Riven Disposition is retired and every weapon
is normalized to 1.2x, matching :data:`DEFAULT_DISPOSITION`. The Splicing
system's spliced attributes (weakpoint damage, combined elemental damage,
etc.) are not part of the Riven upgrade tables and are intentionally excluded.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# --- Game constants (from RivenParser.js) -----------------------------------

SPECIFIC_FIT_ATTENUATION = 1.5
RIVEN_BASE_DRAIN = 10
MAX_RIVEN_ROLL_INT = 0x3FFFFFFF  # 1_073_741_823

# Per-stat random roll band. ``average`` grade sits at the midpoint (factor 1.0).
GRADE_MIN_FACTOR = 0.9
GRADE_MAX_FACTOR = 1.1
AVERAGE_GRADE_T = 0.5

# A Riven mod reaches rank 8 in game; each rank contributes one step.
MAX_RIVEN_RANK = 8
RANK_STEPS = MAX_RIVEN_RANK + 1  # lvl + 1 = 9 at max rank

# Attenuation by number of positive stats (index 0 unused, indexes 1..5).
NUM_BUFFS_ATTEN = [0.0, 1.0, 0.66000003, 0.5, 0.40000001, 0.34999999]
# Curse attenuation indexed by the number of POSITIVE stats.
NUM_BUFFS_CURSE_ATTEN = [0.0, 1.0, 0.33000001, 0.5, 1.25, 1.5]
# Each negative stat boosts the positives by 1.25x.
CURSE_BOOST_PER_NEGATIVE = 1.25

DEFAULT_DISPOSITION = 1.2

RIVEN_TAGS_FILE = "riven_tags.json"

RIVEN_TYPE_NAMES = {
    "LotusRifleRandomModRare": "Rifle Riven Mod",
    "LotusShotgunRandomModRare": "Shotgun Riven Mod",
    "LotusPistolRandomModRare": "Pistol Riven Mod",
    "LotusModularPistolRandomModRare": "Kitgun Riven Mod",
    "PlayerMeleeWeaponRandomModRare": "Melee Riven Mod",
    "LotusModularMeleeRandomModRare": "Zaw Riven Mod",
    "LotusArchgunRandomModRare": "Archgun Riven Mod",
}

# (layout key, number of positives, number of negatives)
BUFF_LAYOUTS = (
    ("2_pos", 2, 0),
    ("3_pos", 3, 0),
    ("2_pos_1_neg", 2, 1),
    ("3_pos_1_neg", 3, 1),
)
# (layout key, number of positives, number of negatives) for the curse column.
CURSE_LAYOUTS = (
    ("with_2_pos", 2, 1),
    ("with_3_pos", 3, 1),
)

UNIT_PERCENT = "percent"
UNIT_FACTION_BONUS = "faction_bonus"
UNIT_PLAIN = "plain"

_FACTION_TAGS = {
    "WeaponFactionDamageGrineer",
    "WeaponFactionDamageCorpus",
    "WeaponFactionDamageInfested",
    "WeaponMeleeFactionDamageGrineer",
    "WeaponMeleeFactionDamageCorpus",
    "WeaponMeleeFactionDamageInfested",
}
_PLAIN_UNIT_TAGS = {
    "WeaponMeleeComboInitialBonusMod",
    "ComboDurationMod",
    "WeaponMeleeRangeIncMod",
    "WeaponPunctureDepthMod",
}

# Wiki ordinary traits marked positive-only or negative-only. The Riven Mods
# rank-8 range table contradicts its coefficient legend for Initial Combo; the
# dedicated Melee Combo page explicitly confirms Initial Combo is positive-only.
_POSITIVE_ONLY_TAGS = frozenset({
    "WeaponFireDamageMod", "WeaponFreezeDamageMod", "WeaponElectricityDamageMod",
    "WeaponToxinDamageMod", "WeaponPunctureDepthMod", "WeaponMeleeDamageMod",
    "WeaponMeleeComboInitialBonusMod", "WeaponMeleeComboBonusOnHitMod",
})
_NEGATIVE_ONLY_TAGS = frozenset({"WeaponMeleeComboPointsOnHitMod"})

# tag -> (human-readable label, unit kind, WDC damage/mod code when applicable)
TAG_METADATA: dict[str, tuple[str, str, str | None]] = {
    "WeaponDamageAmountMod": ("Damage", UNIT_PERCENT, "TRUE"),
    "WeaponMeleeDamageMod": ("Melee Damage", UNIT_PERCENT, "TRUE"),
    "WeaponImpactDamageMod": ("Impact", UNIT_PERCENT, "IMPACT"),
    "WeaponArmorPiercingDamageMod": ("Puncture", UNIT_PERCENT, "PUNC"),
    "WeaponSlashDamageMod": ("Slash", UNIT_PERCENT, "SLASH"),
    "WeaponFireDamageMod": ("Heat", UNIT_PERCENT, "HEAT"),
    "WeaponFreezeDamageMod": ("Cold", UNIT_PERCENT, "COLD"),
    "WeaponElectricityDamageMod": ("Electricity", UNIT_PERCENT, "ELEC"),
    "WeaponToxinDamageMod": ("Toxin", UNIT_PERCENT, "TOXIN"),
    "WeaponFactionDamageGrineer": ("Damage to Grineer", UNIT_FACTION_BONUS, "BANE_GRINEER"),
    "WeaponFactionDamageCorpus": ("Damage to Corpus", UNIT_FACTION_BONUS, "BANE_CORPUS"),
    "WeaponFactionDamageInfested": ("Damage to Infested", UNIT_FACTION_BONUS, "BANE_INFESTED"),
    "WeaponMeleeFactionDamageGrineer": ("Damage to Grineer", UNIT_FACTION_BONUS, "BANE_GRINEER"),
    "WeaponMeleeFactionDamageCorpus": ("Damage to Corpus", UNIT_FACTION_BONUS, "BANE_CORPUS"),
    "WeaponMeleeFactionDamageInfested": ("Damage to Infested", UNIT_FACTION_BONUS, "BANE_INFESTED"),
    "WeaponCritChanceMod": ("Critical Chance", UNIT_PERCENT, None),
    "WeaponCritDamageMod": ("Critical Damage", UNIT_PERCENT, None),
    "WeaponStunChanceMod": ("Status Chance", UNIT_PERCENT, None),
    "WeaponProcTimeMod": ("Status Duration", UNIT_PERCENT, None),
    "WeaponFireRateMod": ("Fire Rate / Attack Speed", UNIT_PERCENT, None),
    "WeaponFireIterationsMod": ("Multishot", UNIT_PERCENT, None),
    "WeaponReloadSpeedMod": ("Reload Speed", UNIT_PERCENT, None),
    "WeaponClipMaxMod": ("Magazine Capacity", UNIT_PERCENT, None),
    "WeaponAmmoMaxMod": ("Ammo Maximum", UNIT_PERCENT, None),
    "WeaponPunctureDepthMod": ("Punch Through", UNIT_PLAIN, None),
    "WeaponRecoilReductionMod": ("Weapon Recoil", UNIT_PERCENT, None),
    "WeaponZoomFovMod": ("Zoom", UNIT_PERCENT, None),
    "WeaponProjectileSpeedMod": ("Projectile Speed", UNIT_PERCENT, None),
    "WeaponMeleeRangeIncMod": ("Range", UNIT_PLAIN, None),
    "WeaponMeleeFinisherDamageMod": ("Finisher Damage", UNIT_PERCENT, None),
    "WeaponMeleeComboEfficiencyMod": ("Heavy Attack Efficiency", UNIT_PERCENT, None),
    "WeaponMeleeComboInitialBonusMod": ("Initial Combo", UNIT_PLAIN, None),
    "ComboDurationMod": ("Combo Duration", UNIT_PLAIN, None),
    "WeaponMeleeComboPointsOnHitMod": ("Chance to Gain Combo Count", UNIT_PERCENT, None),
    "WeaponMeleeComboBonusOnHitMod": ("Additional Combo Count Chance", UNIT_PERCENT, None),
    "SlideAttackCritChanceMod": ("Slide Attack", UNIT_PERCENT, None),
}


def _default_tags_path() -> Path:
    candidates = [Path(__file__).resolve().parent.parent / "source" / RIVEN_TAGS_FILE]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "source" / RIVEN_TAGS_FILE)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_riven_tags(path: str | Path | None = None) -> dict[str, list[dict]]:
    """Load the per-type Riven stat tables (``{riven_type: [{tag, value, ...}]}``)."""
    tags_path = Path(path) if path else _default_tags_path()
    with tags_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not data:
        raise ValueError(f"Riven tag data at {tags_path} is empty or malformed")
    return data


def riven_int_to_float(roll: int) -> float:
    """Map a Riven fingerprint roll integer to the 0..1 grade position."""
    fraction = roll / MAX_RIVEN_ROLL_INT
    return fraction if 0.0 <= fraction <= 1.0 else 0.0


def lerp(low: float, high: float, t: float) -> float:
    return low + (high - low) * t


def grade_factor(t: float = AVERAGE_GRADE_T) -> float:
    """Random-roll grade multiplier. Average grade (t=0.5) is exactly 1.0."""
    return lerp(GRADE_MIN_FACTOR, GRADE_MAX_FACTOR, t)


def _js_round(value: float) -> float:
    """JavaScript ``Math.round``: halves round toward positive infinity."""
    return float(math.floor(value + 0.5))


def display_value(tag: str, raw: float) -> float:
    """Round a raw stat for the table (faction entries remain bonus-only)."""
    if tag in _FACTION_TAGS:
        return _js_round(raw * 100) / 100
    if tag in _PLAIN_UNIT_TAGS:
        return _js_round(raw * 10) / 10
    if tag == "WeaponMeleeComboPointsOnHitMod":
        # This negative-only trait is displayed as -100*v, not +100*v.
        raw = -raw
    return _js_round(raw * 1000) / 10


def stat_unit(tag: str) -> str:
    if tag in _FACTION_TAGS:
        return UNIT_FACTION_BONUS
    if tag in _PLAIN_UNIT_TAGS:
        return UNIT_PLAIN
    return UNIT_PERCENT


def base_attenuation(disposition: float = DEFAULT_DISPOSITION) -> float:
    return SPECIFIC_FIT_ATTENUATION * disposition * RIVEN_BASE_DRAIN


def buff_layout_factor(num_buffs: int, num_curses: int) -> float:
    """Combined-stat attenuation for a positive stat in a given layout."""
    buff_index = min(num_buffs, len(NUM_BUFFS_ATTEN) - 1)
    return NUM_BUFFS_ATTEN[buff_index] * (CURSE_BOOST_PER_NEGATIVE ** num_curses)


def curse_layout_factor(num_buffs: int, num_curses: int) -> float:
    """Combined-stat attenuation for a negative stat in a given layout."""
    curse_index = min(num_buffs, len(NUM_BUFFS_CURSE_ATTEN) - 1)
    buff_index = min(num_curses, len(NUM_BUFFS_ATTEN) - 1)
    return NUM_BUFFS_CURSE_ATTEN[curse_index] * NUM_BUFFS_ATTEN[buff_index]


def _tag_value(tables: dict[str, list[dict]], riven_type: str, tag: str) -> float:
    for entry in tables[riven_type]:
        if entry["tag"] == tag:
            return float(entry["value"])
    raise KeyError(f"Tag {tag!r} cannot roll on {riven_type!r}")


def average_buff(
    riven_type: str,
    tag: str,
    disposition: float = DEFAULT_DISPOSITION,
    rank: int = MAX_RIVEN_RANK,
    num_buffs: int = 2,
    num_curses: int = 0,
    grade_t: float = AVERAGE_GRADE_T,
    tables: dict[str, list[dict]] | None = None,
) -> float:
    """Raw average-grade value of a rollable positive trait for a given layout."""
    tables = tables or load_riven_tags()
    if tag in _NEGATIVE_ONLY_TAGS:
        raise ValueError(f"{tag} cannot roll as a positive Riven trait")
    return (
        _tag_value(tables, riven_type, tag)
        * base_attenuation(disposition)
        * grade_factor(grade_t)
        * buff_layout_factor(num_buffs, num_curses)
        * (rank + 1)
    )


def average_curse(
    riven_type: str,
    tag: str,
    disposition: float = DEFAULT_DISPOSITION,
    rank: int = MAX_RIVEN_RANK,
    num_buffs: int = 3,
    num_curses: int = 1,
    grade_t: float = AVERAGE_GRADE_T,
    tables: dict[str, list[dict]] | None = None,
) -> float:
    """Raw average-grade modifier for a rollable negative trait.

    Some raw coefficients have inverted display conventions, so the sign of
    the raw modifier is not always the sign shown to the player.
    """
    tables = tables or load_riven_tags()
    if tag in _POSITIVE_ONLY_TAGS:
        raise ValueError(f"{tag} cannot roll as a negative Riven trait")
    return (
        _tag_value(tables, riven_type, tag)
        * -1.0
        * base_attenuation(disposition)
        * grade_factor(grade_t)
        * curse_layout_factor(num_buffs, num_curses)
        * (rank + 1)
    )


def parse_riven(riven_type: str, fingerprint: dict, disposition: float) -> list[dict]:
    """Parse a full Riven fingerprint (as stored on an unveiled mod).

    Mirrors RivenParser.js ``parseRiven`` so arbitrary rolls, including
    non-average grades and repeated tags, can be evaluated exactly.
    """
    tables = load_riven_tags()
    tag_values = {entry["tag"]: float(entry["value"]) for entry in tables[riven_type]}
    buffs = fingerprint.get("buffs", [])
    curses = fingerprint.get("curses", [])
    num_buffs, num_curses = len(buffs), len(curses)
    attenuation = base_attenuation(disposition)
    curse_boost = CURSE_BOOST_PER_NEGATIVE ** num_curses
    rank_steps = int(fingerprint.get("lvl", MAX_RIVEN_RANK)) + 1

    stats: list[dict] = []
    for buff in buffs:
        raw = (
            tag_values[buff["Tag"]]
            * attenuation
            * curse_boost
            * grade_factor(riven_int_to_float(int(buff["Value"])))
            * NUM_BUFFS_ATTEN[min(num_buffs, len(NUM_BUFFS_ATTEN) - 1)]
            * rank_steps
        )
        stats.append({"tag": buff["Tag"], "raw": raw, "display": display_value(buff["Tag"], raw)})

    for curse in curses:
        raw = (
            tag_values[curse["Tag"]]
            * -1.0
            * attenuation
            * grade_factor(riven_int_to_float(int(curse["Value"])))
            * curse_layout_factor(num_buffs, num_curses)
            * rank_steps
        )
        stats.append({"tag": curse["Tag"], "raw": raw, "display": display_value(curse["Tag"], raw)})

    return stats


def _stat_entry(
    tables: dict[str, list[dict]],
    riven_type: str,
    entry: dict,
    disposition: float,
    rank: int,
) -> dict:
    tag = entry["tag"]
    name, unit, wdc_code = TAG_METADATA.get(tag, (tag, stat_unit(tag), None))
    buffs: dict[str, dict | None] = {}
    for layout_key, num_buffs, num_curses in BUFF_LAYOUTS:
        if tag in _NEGATIVE_ONLY_TAGS:
            buffs[layout_key] = None
        else:
            raw = average_buff(
                riven_type, tag, disposition, rank, num_buffs, num_curses, tables=tables
            )
            buffs[layout_key] = {"raw": raw, "display": display_value(tag, raw)}
    curses: dict[str, dict | None] = {}
    for layout_key, num_buffs, num_curses in CURSE_LAYOUTS:
        if tag in _POSITIVE_ONLY_TAGS:
            curses[layout_key] = None
        else:
            raw = average_curse(
                riven_type, tag, disposition, rank, num_buffs, num_curses, tables=tables
            )
            curses[layout_key] = {"raw": raw, "display": display_value(tag, raw)}
    return {
        "tag": tag,
        "name": name,
        "unit": unit,
        "wdc_code": wdc_code,
        "buffs": buffs,
        "curses": curses,
    }


def build_average_tables(
    disposition: float = DEFAULT_DISPOSITION,
    rank: int = MAX_RIVEN_RANK,
    tags_path: str | Path | None = None,
) -> dict:
    """Build average-grade stat tables for every Riven type at one disposition."""
    tables = load_riven_tags(tags_path)
    riven_types = {}
    for riven_type, entries in tables.items():
        riven_types[riven_type] = {
            "display_name": RIVEN_TYPE_NAMES.get(riven_type, riven_type),
            "stats": [
                _stat_entry(tables, riven_type, entry, disposition, rank) for entry in entries
            ],
        }

    return {
        "meta": {
            "disposition": disposition,
            "grade": "average",
            "grade_roll_t": AVERAGE_GRADE_T,
            "grade_factor": grade_factor(AVERAGE_GRADE_T),
            "grade_band": [GRADE_MIN_FACTOR, GRADE_MAX_FACTOR],
            "max_rank": rank,
            "rank_steps": rank + 1,
            "specific_fit_attenuation": SPECIFIC_FIT_ATTENUATION,
            "riven_base_drain": RIVEN_BASE_DRAIN,
            "buff_layouts": [
                {
                    "key": key,
                    "positive_stats": num_buffs,
                    "negative_stats": num_curses,
                    "factor": buff_layout_factor(num_buffs, num_curses),
                }
                for key, num_buffs, num_curses in BUFF_LAYOUTS
            ],
            "curse_layouts": [
                {
                    "key": key,
                    "positive_stats": num_buffs,
                    "negative_stats": num_curses,
                    "factor": curse_layout_factor(num_buffs, num_curses),
                }
                for key, num_buffs, num_curses in CURSE_LAYOUTS
            ],
            "stat_source": "github.com/calamity-inc/warframe-riven-info (riven_tags.json; derived from DE ExportUpgrades Riven buffData)",
        },
        "riven_types": riven_types,
    }
