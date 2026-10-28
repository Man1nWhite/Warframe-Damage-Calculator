"""Keep legacy imported effects within the desktop direct-hit model's scope.

Old databases may contain false positives from the earlier permissive parser.
Apply the current parser to saved official effect text before use, without
rewriting the database or changing user-defined rows. Some old rows discarded
their activation condition entirely; these known identifiers need an explicit
exception until the data is reimported. This is not an exhaustive condition or
weapon-compatibility catalogue.
"""
from __future__ import annotations

import math

from .mod_parser import parse_effects
from .models import ModEffect

# Proton Snap's source line says to Wall Latch before gaining Toxin, but older
# databases retained only "+100% toxin damage". The Wiki describes the trigger:
# https://wiki.warframe.com/w/Proton_Snap
_LEGACY_CONDITIONAL_MODS = frozenset({
    "/Lotus/Upgrades/Mods/Sets/Spider/SpiderModC",
})

# This DE export row is named "Pressure Point" but advertises +200% damage at
# rank 10 and a heavy-kill identifier. It does not match the Wiki's normal,
# flawed, primed or sacrificial variants. Exclude until independently mapped.
# https://wiki.warframe.com/w/Pressure_Point
_UNVERIFIED_EXPORT_MODS = frozenset({
    "/Lotus/Upgrades/Mods/Melee/WeaponMeleeDamageOnHeavyKillMod",
})


def is_pve_mod(unique_name: str) -> bool:
    """The public export's PvPMods namespace is not usable in normal PvE."""
    return not (unique_name.startswith("/Lotus/") and "/PvPMods/" in unique_name)


def is_supported_export_mod(unique_name: str) -> bool:
    """Reject known unsupported or unverified official identifiers."""
    return is_pve_mod(unique_name) and unique_name not in _UNVERIFIED_EXPORT_MODS


def usable_direct_effect(unique_name: str, effect: ModEffect) -> bool:
    """Whether an imported effect can be used as unconditional direct damage.

    Identifiers outside DE's reserved /Lotus/ namespace are user data; do not
    reinterpret their custom labels or values. Conclave-only items are outside
    this PvE-oriented calculator, even if an individual line resembles a
    normal PvE effect.
    """
    if not unique_name.startswith("/Lotus/"):
        return True
    if unique_name in _LEGACY_CONDITIONAL_MODS or not is_supported_export_mod(unique_name):
        return False
    parsed = parse_effects(effect.text)
    return (len(parsed) == 1 and parsed[0].code == effect.code
            and math.isclose(parsed[0].value, effect.value, rel_tol=1e-9, abs_tol=1e-12))
