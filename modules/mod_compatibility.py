"""Conservative, incomplete GUI mod-compatibility checks.

DE's weapon export does not include primary mod families or all melee
subclasses. Broad primary classes are a pinned, attributed WFCD snapshot;
explicit Wiki-reviewed exceptions and a few melee lists are maintained here.
This is not a comprehensive legality checker. Custom mods are left untouched.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .mod_effect_policy import is_supported_export_mod
from .models import Mod, Weapon

_PRIMARY_CLASSES = {"Rifle", "Shotgun", "Bow", "Sniper", "Launcher"}
_PLAYER_CATEGORIES = {"LongGuns", "Pistols", "Melee"}

# The source export has no reliable Incarnon/multi-mode trigger compatibility;
# equipping Cannonade on all rifles or pistols would be wrong. Hide these
# entries until their exact weapon/mode eligibility can be represented.
# https://wiki.warframe.com/w/Semi-Rifle_Cannonade
_CANNONADE_IDS = frozenset({
    "/Lotus/Upgrades/Mods/Rifle/RifleSemiAutoFantasyMod",
    "/Lotus/Upgrades/Mods/Shotgun/ShotgunSemiAutoFantasyMod",
    "/Lotus/Upgrades/Mods/Pistol/PistolSemiAutoFantasyMod",
})

# Exact English category members, excluding stances, skins and Conclave pages.
# These bounded lists may omit weapons added after the cited Wiki revisions.
# https://wiki.warframe.com/w/Category:Dual_Daggers?oldid=2669242
# https://wiki.warframe.com/w/Category:Polearm?oldid=2669197
# https://wiki.warframe.com/w/Category:Whip?oldid=2669131
_MELEE_SUBCLASSES = {
    "dual daggers": frozenset(name.casefold() for name in (
        "Ether Daggers", "Fang", "Fang Prime", "Nepheri", "Okina", "Okina Prime",
    )),
    "polearms": frozenset(name.casefold() for name in (
        "Amanata", "Cassowar", "Edun", "Guandao", "Guandao Prime", "Kesheg",
        "Korumm", "Lesion", "Orthos", "Orthos Prime", "Pupacyst", "Serro",
        "Sydon", "Tonbo", "Vaykor Sydon",
    )),
    "whips": frozenset(name.casefold() for name in (
        "Atterax", "Galvacord", "Lecta", "Scoliac", "Secura Lecta", "Spinnerex", "Verdilac",
    )),
}

# Variants documented by these augment pages. Do not infer arbitrary variants
# from similar names: some augments explicitly exclude seemingly related ones.
# https://wiki.warframe.com/w/Toxic_Blight
# https://wiki.warframe.com/w/Bright_Purity
# https://wiki.warframe.com/w/Justice_Blades
_AUGMENT_VARIANTS = {
    "mire": frozenset({"mire", "coda mire"}),
    "skana": frozenset({"skana", "skana prime", "prisma skana"}),
    "dual cleavers": frozenset({"dual cleavers", "prisma dual cleavers"}),
}


@dataclass(frozen=True)
class ModCompatibility:
    primary_classes: Mapping[str, str]

    @classmethod
    def from_file(cls, path: str | Path) -> ModCompatibility:
        """Load the bundled data; a missing/corrupt file means unknown classes."""
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            classes = payload["classes"]
            if (payload.get("schema") != 1 or not isinstance(classes, dict)
                    or not all(isinstance(key, str) and key.startswith("/Lotus/")
                               and value in _PRIMARY_CLASSES for key, value in classes.items())):
                raise ValueError("invalid class snapshot")
            return cls(dict(classes))
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            return cls({})

    def allows(self, weapon: Weapon, mod: Mod) -> bool:
        # A user's non-DE custom mod is never reinterpreted by this policy.
        if not mod.unique_name.startswith("/Lotus/"):
            return True
        if (not is_supported_export_mod(mod.unique_name) or mod.unique_name in _CANNONADE_IDS
                or "/Sentinel/" in mod.unique_name or "/Pets/" in mod.unique_name):
            return False

        # The desktop engine only models normal player weapon slots. Do not
        # present rifle/melee mods for a companion, Archwing or exalted weapon
        # merely because the importer defaulted an unknown category to primary.
        if (weapon.unique_name.startswith("/Lotus/")
                and weapon.product_category not in _PLAYER_CATEGORIES):
            return False

        compat = mod.compat_name.strip().casefold()
        name = weapon.weapon.strip().casefold()
        if compat in {"rifle", "shotgun", "bow", "sniper"}:
            if weapon.slot_group != "PRIMARY":
                return False
            family = self.primary_classes.get(weapon.unique_name)
            if family is None:
                # Unknown official weapons are not guessed; user-created
                # weapons retain access to generic mods with an explicit note.
                return not weapon.unique_name.startswith("/Lotus/")
            if compat == "shotgun":
                return family == "Shotgun"
            if compat == "rifle":
                return family != "Shotgun"
            return family.casefold() == compat
        if compat in {"primary", "pistol", "secondary", "melee", "any"}:
            slots = {"primary": "PRIMARY", "pistol": "SECONDARY", "secondary": "SECONDARY",
                     "melee": "MELEE"}
            return compat == "any" or slots[compat] == weapon.slot_group
        if compat in _MELEE_SUBCLASSES:
            return weapon.slot_group == "MELEE" and name in _MELEE_SUBCLASSES[compat]
        if compat in _AUGMENT_VARIANTS:
            return name in _AUGMENT_VARIANTS[compat]
        # Known weapon-specific IDs in the export name their exact weapon in
        # compatName (e.g. Higasa, Amanata, Akbronco Prime). Unknown categories
        # or unlisted variants are excluded rather than guessed.
        return bool(compat and compat == name)

    def notice(self, weapon: Weapon) -> str:
        general = ("Some mods, including Cannonade, are hidden when their rules are unmodeled. Compatibility is partial: "
                   "conflicts, duplicates, mod capacity and other restrictions are not checked. "
                   "Verify the build separately.")
        if (weapon.unique_name.startswith("/Lotus/")
                and weapon.product_category not in _PLAYER_CATEGORIES):
            return "This weapon category is not modeled; only custom mods are available. " + general
        if weapon.slot_group == "PRIMARY" and weapon.unique_name not in self.primary_classes:
            if weapon.unique_name.startswith("/Lotus/"):
                return "Unknown primary mod family; official rifle/shotgun mods are hidden. " + general
            return "Custom weapon family is unknown; generic rifle/shotgun mods are not filtered. " + general
        return general
