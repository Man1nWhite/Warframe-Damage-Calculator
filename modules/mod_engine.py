from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Dict, Iterable

from .constants import BASE_ELEMENT_TYPES, BANE_CODE_MAP, ELEMENT_COMBINATIONS, MOD_STAT_ORDER
from .models import EquippedMod


def _bane_bonus(value: float) -> float:
    """Normalize a bane/faction mod value to an additive damage bonus.

    The DE export data (and the reference spreadsheet) express bane mods as full
    multipliers, e.g. "X1.30 damage to Grineer" stored as 1.30. Every other mod
    stat is stored as a fractional bonus (0.30 for +30%), so convert here.
    Percent-style entries are already fractional and pass through unchanged.
    """
    return value - 1.0 if value > 1.0 else value


class ModAggregator:
    """Aggregates equipped mod effects into the per-stat values the calculator uses.

    Base elemental effects follow Warframe's slot-order combination rules:

    - mods are read in equipped slot order (left to right, top to bottom);
    - repeated contributions of the same element stack into one group whose
      hierarchy position is fixed by its first occurrence;
    - when a different base element appears, it combines with the earliest
      uncombined element group into a secondary element;
    - an element that has already combined into a secondary element keeps
      feeding that secondary element when it appears again later.
    """

    def aggregate(self, equipped_mods: Iterable[EquippedMod], faction: str) -> Dict[str, float]:
        totals = defaultdict(float)
        # Uncombined base element groups, keyed by element in first-occurrence order.
        pending: "OrderedDict[str, float]" = OrderedDict()
        # Base element -> secondary element code it was combined into.
        combo_of: dict[str, str] = {}

        bane_codes = BANE_CODE_MAP.get(faction, set())

        for equipped in equipped_mods:
            if equipped.mod is None:
                continue

            for effect in equipped.effects:
                code = effect.code
                if code in bane_codes:
                    totals["BANE"] += _bane_bonus(effect.value)
                    continue

                if code in BASE_ELEMENT_TYPES:
                    if code in pending:
                        # Same element stacks into its existing uncombined group.
                        pending[code] += effect.value
                    elif code in combo_of:
                        # The element already combined earlier; later copies
                        # add to that secondary element instead of standing alone.
                        totals[combo_of[code]] += effect.value
                    elif pending:
                        # Combine with the earliest uncombined element group.
                        partner = next(iter(pending))
                        combo_code = ELEMENT_COMBINATIONS.get(frozenset((partner, code)))
                        if combo_code is None:
                            # Defensive fallback: no valid pairing, keep both uncombined.
                            pending[code] = effect.value
                            continue
                        totals[combo_code] += pending.pop(partner) + effect.value
                        combo_of[partner] = combo_code
                        combo_of[code] = combo_code
                    else:
                        pending[code] = effect.value
                    continue

                totals[code] += effect.value

        for element, value in pending.items():
            totals[element] += value

        return {code: float(totals.get(code, 0.0)) for code in MOD_STAT_ORDER}
