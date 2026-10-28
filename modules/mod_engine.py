from __future__ import annotations

from collections import OrderedDict, defaultdict
from collections.abc import Iterable

from .constants import BANE_CODE_MAP, BASE_ELEMENT_TYPES, ELEMENT_COMBINATIONS, MOD_STAT_ORDER
from .models import EquippedMod, ModEffect


def ordered_mod_effects(equipped: EquippedMod) -> Iterable[ModEffect]:
    """Return effect order for elemental hierarchy without mutating the mod.

    The Wiki gives the last displayed primary elemental stat of a Riven
    priority. Recognition currently uses the existing name-based convention;
    arbitrary named Rivens are not automatically identified as Rivens.
    Non-primary effects keep their positions and are otherwise unaffected.
    """
    if equipped.mod is None:
        return ()
    effects = equipped.effects
    if "riven" not in equipped.mod.name.lower():
        return effects
    primary = [effect for effect in effects if effect.code in BASE_ELEMENT_TYPES]
    if len(primary) < 2:
        return effects
    reversed_primary = iter(reversed(primary))
    return tuple(next(reversed_primary) if effect.code in BASE_ELEMENT_TYPES else effect
                 for effect in effects)


def _bane_bonus(value: float, text: str = "") -> float:
    """Normalize a bane/faction mod value to an additive damage bonus.

    The DE export data (and the reference spreadsheet) express bane mods as full
    multipliers, e.g. "X1.30 damage to Grineer" stored as 1.30. Every other mod
    stat is stored as a fractional bonus (0.30 for +30%), so convert here.
    Percent-style entries are already fractional and pass through unchanged.
    """
    if text.strip().lower().startswith("x"):
        return value - 1.0
    if "%" in text:
        return value
    # Compatibility for older callers without a stat label.
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

    def aggregate(self, equipped_mods: Iterable[EquippedMod], faction: str) -> dict[str, float]:
        totals = defaultdict(float)
        # Uncombined base element groups, keyed by element in first-occurrence order.
        pending: OrderedDict[str, float] = OrderedDict()
        # Base element -> secondary element code it was combined into.
        combo_of: dict[str, str] = {}

        bane_codes = BANE_CODE_MAP.get(faction, set())

        for equipped in equipped_mods:
            if equipped.mod is None:
                continue

            for effect in ordered_mod_effects(equipped):
                code = effect.code
                if code in bane_codes:
                    totals["BANE"] += _bane_bonus(effect.value, effect.text)
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
