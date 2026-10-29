"""Direct-hit calculation for the selected weapon and mod layout.

The wiki's damage calculation page describes quantization in units of 1/32
of modded base damage.  Display rounding is deliberately not part of the
health-damage calculation. This model treats the exported damage row as one
non-critical hit against health (not shields or Overguard). Some rows already
combine separate direct and radial attacks; those are not modeled per hit.
Weapon-specific mechanics, crits, status effects and additional multishot are
outside this screen's scope.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from .constants import (
    BASE_ELEMENT_TYPES,
    COMBINED_ELEMENT_TYPES,
    DAMAGE_TYPES,
    ELEMENT_COMBINATIONS,
    FACTION_MULTIPLIERS,
    PHYSICAL_DAMAGE_TYPES,
    faction_key,
)
from .enemy_scaling import enemy_armor_damage_reduction
from .mod_engine import ModAggregator, ordered_mod_effects
from .models import CalculationInputs, CalculationResults, Weapon
from .status_damage import wiki_quantized_damage

# Innate primary elements follow equipped mods in this order.
INNATE_ELEMENT_ORDER = ("HEAT", "COLD", "ELEC", "TOXIN")


class NumericRangeError(ValueError):
    """The data or an intermediate calculation is not a finite number."""


def _require_finite(description: str, *values: float) -> None:
    if not all(math.isfinite(value) for value in values):
        raise NumericRangeError(f"{description} must be finite; check the numeric values and range.")


def parse_nonnegative_number(value: object, label: str, *, blank_zero: bool = False) -> float:
    """Parse a representable non-negative value without silent underflow.

    Text is accepted for callers reading a build file; a blank can mean zero
    when explicitly requested by the UI. Negative mod effects are unrelated
    to this validation and remain supported.
    """
    suffix = " (blank means zero)" if blank_zero else ""
    message = f"{label} must be a representable, finite, non-negative number{suffix}."
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise ValueError(message)
        if isinstance(value, str):
            value = value.strip()
            if not value and blank_zero:
                return 0.0
        parsed = float(value)
        if not math.isfinite(parsed) or parsed < 0:
            raise ValueError(message)
        # A nonzero decimal can underflow to signed zero, concealing a
        # negative or a value that the calculator cannot represent.
        if parsed == 0.0:
            underflowed = not Decimal(value).is_zero() if isinstance(value, str) else value != 0
            if underflowed:
                raise ValueError(message)
        return parsed
    except (TypeError, ValueError, OverflowError, InvalidOperation):
        raise ValueError(message) from None


class DamageCalculator:
    def calculate(self, weapon: Weapon, inputs: CalculationInputs) -> CalculationResults:
        base_weapon_damage = float(weapon.dmg)
        _require_finite("Weapon damage and multishot", base_weapon_damage, weapon.multi,
                        *(weapon.damage_for(kind) for kind in DAMAGE_TYPES))
        armor_value = parse_nonnegative_number(inputs.armor_value, "Armor")
        valence_input = parse_nonnegative_number(inputs.valence_base, "Valence")

        faction = faction_key(inputs.faction)
        element = (inputs.lich_element or "").strip().upper()
        if element and element not in DAMAGE_TYPES:
            raise ValueError(f"Unknown progenitor damage type: {element}")
        # A value without a selected type is not a damage component.
        valence_damage = valence_input if element else 0.0
        valence_multiplier = valence_damage / base_weapon_damage if base_weapon_damage > 0 else 0.0
        weapon_total_damage = base_weapon_damage + valence_damage
        mod_totals = self._mod_totals(inputs, faction)
        _require_finite("Mod effects", *mod_totals.values())
        base_multiplier = max(0.0, 1.0 + mod_totals.get("TRUE", 0.0))
        modded_base = weapon_total_damage * base_multiplier
        quanta = modded_base / 32.0
        _require_finite("Calculated base damage", valence_multiplier, weapon_total_damage,
                        base_multiplier, modded_base, quanta)

        base_by_type, lich_damage, resolved_mods = self._resolve_elements(
            weapon, inputs, mod_totals, element, valence_damage
        )
        _require_finite("Calculated damage components", *base_by_type.values(),
                        *lich_damage.values(), *resolved_mods.values())
        faction_modifiers = self._build_faction_modifiers(faction)
        armor_modifiers = self._build_armor_modifiers(armor_value, faction_modifiers)
        bane_multiplier = max(0.0, 1.0 + mod_totals.get("BANE", 0.0))

        hud_damage_by_type: dict[str, float] = {}
        final_damage_by_type: dict[str, float] = {}
        bane_final_by_type: dict[str, float] = {}
        for damage_type in DAMAGE_TYPES:
            base_value = base_by_type[damage_type] + lich_damage[damage_type]
            mod_value = resolved_mods.get(damage_type, 0.0)
            if damage_type in PHYSICAL_DAMAGE_TYPES:
                raw = base_value * (1.0 + mod_value)
            else:
                raw = base_value + weapon_total_damage * mod_value
            hud_damage_by_type[damage_type] = raw * base_multiplier
            _require_finite("Calculated damage", raw, hud_damage_by_type[damage_type])
            try:
                quantized = (
                    wiki_quantized_damage(hud_damage_by_type[damage_type], modded_base)
                    if modded_base > 0 else 0.0
                )
            except (OverflowError, ValueError) as exc:
                raise NumericRangeError("Quantized damage must be finite; check the numeric range.") from exc
            dealt = quantized * armor_modifiers[damage_type]
            bane_dealt = dealt * bane_multiplier
            _require_finite("Calculated damage", quantized, dealt, bane_dealt)
            # The wiki's armor article states a minimum of 1 per positive
            # damage type reduced by armor.  Zero-quantized types stay zero.
            if armor_value > 0:
                if dealt > 0:
                    dealt = max(1.0, dealt)
                if bane_dealt > 0:
                    bane_dealt = max(1.0, bane_dealt)
            final_damage_by_type[damage_type] = dealt
            bane_final_by_type[damage_type] = bane_dealt

        # Arsenal-style totals include innate multishot, whereas final totals
        # treat the exported row as one damage instance. Some export rows
        # combine distinct hit components. Additional multishot is not modeled.
        hud_total = sum(hud_damage_by_type.values()) * (weapon.multi if weapon.multi > 0 else 1.0)
        hud_total_with_bane = hud_total * bane_multiplier
        final_total = sum(final_damage_by_type.values())
        final_total_with_bane = sum(bane_final_by_type.values())
        accounted_base = sum(weapon.damage_for(kind) for kind in DAMAGE_TYPES)
        _require_finite("Damage totals", hud_total, hud_total_with_bane, final_total,
                        final_total_with_bane, accounted_base)
        missing_base = max(0.0, base_weapon_damage - accounted_base)
        _require_finite("Unmodeled base damage", missing_base)
        warnings = []
        if missing_base > max(1e-6, abs(base_weapon_damage) * 1e-6):
            warnings.append(
                f"{missing_base:g} base damage is not assigned to a modeled damage type; "
                "HUD and final totals are incomplete."
            )
        return CalculationResults(
            base_weapon_damage=base_weapon_damage,
            quanta=quanta,
            valence_multiplier=valence_multiplier,
            weapon_total_damage=weapon_total_damage,
            lich_damage=lich_damage,
            faction_modifiers=faction_modifiers,
            armor_modifiers=armor_modifiers,
            hud_damage_by_type=hud_damage_by_type,
            final_damage_by_type=final_damage_by_type,
            aggregated_mods=resolved_mods,
            hud_total=hud_total,
            hud_total_with_bane=hud_total_with_bane,
            final_total=final_total,
            final_total_with_bane=final_total_with_bane,
            warnings=warnings,
        )

    @staticmethod
    def _mod_totals(inputs: CalculationInputs, faction: str) -> dict[str, float]:
        """Per-stat bonuses in effect for this build.

        The equipped slots are authoritative: when ``equipped_mods`` is
        supplied, the totals are aggregated from them and ``inputs.mods`` is
        ignored, so a build cannot produce different numbers depending on
        whether the caller also passed the totals it pre-computed, and a stale
        or hand-edited dictionary cannot smuggle in a bonus the slots do not
        justify. The pre-aggregated dictionary stays supported -- and is the
        only source -- for callers that do not supply the slot list at all.
        """
        if inputs.equipped_mods is None:
            return {code: float(value) for code, value in inputs.mods.items()}
        return ModAggregator().aggregate(inputs.equipped_mods, faction)

    @staticmethod
    def _resolve_elements(weapon: Weapon, inputs: CalculationInputs,
                          mod_totals: dict[str, float], lich_element: str,
                          valence_damage: float
                          ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        """Combine ordered primary mods, then innate and progenitor primaries.

        Already-combined elemental mods and innate secondary elements remain
        independent. For callers without equipped_mods, the mod dictionary is
        considered already resolved; primary values have the deterministic
        HEAT/COLD/ELEC/TOXIN order, since a plain dictionary cannot express the
        origin of a pre-combined bonus.
        """
        base = {kind: weapon.damage_for(kind) for kind in DAMAGE_TYPES}
        lich = {kind: 0.0 for kind in DAMAGE_TYPES}
        mods = dict(mod_totals)
        # Each first occurrence establishes a group's hierarchy.  Values are
        # [mod percentage, innate damage, progenitor damage].
        groups: OrderedDict[str, list[float]] = OrderedDict()
        if inputs.equipped_mods is not None:
            for kind in BASE_ELEMENT_TYPES:
                mods[kind] = 0.0
            # Aggregator totals already include paired primary mods; rebuild
            # elemental values from source effects to retain their provenance.
            for kind in COMBINED_ELEMENT_TYPES:
                mods[kind] = 0.0
            for equipped in inputs.equipped_mods:
                for effect in ordered_mod_effects(equipped):
                    if effect.code in BASE_ELEMENT_TYPES:
                        groups.setdefault(effect.code, [0.0, 0.0, 0.0])[0] += effect.value
                    elif effect.code in COMBINED_ELEMENT_TYPES:
                        mods[effect.code] = mods.get(effect.code, 0.0) + effect.value
        else:
            for kind in INNATE_ELEMENT_ORDER:
                value = mods.get(kind, 0.0)
                if value:
                    groups.setdefault(kind, [0.0, 0.0, 0.0])[0] += value
                mods[kind] = 0.0

        for kind in INNATE_ELEMENT_ORDER:
            innate = base[kind]
            progenitor = valence_damage if lich_element == kind else 0.0
            if innate or progenitor:
                group = groups.setdefault(kind, [0.0, 0.0, 0.0])
                group[1] += innate
                group[2] += progenitor
            base[kind] = 0.0
        if lich_element and lich_element not in BASE_ELEMENT_TYPES:
            lich[lich_element] = valence_damage

        ordered = list(groups.items())
        for i in range(0, len(ordered), 2):
            kind, values = ordered[i]
            if i + 1 < len(ordered):
                other, other_values = ordered[i + 1]
                destination = ELEMENT_COMBINATIONS[frozenset((kind, other))]
                values = [a + b for a, b in zip(values, other_values, strict=True)]
            else:
                destination = kind
            mods[destination] = mods.get(destination, 0.0) + values[0]
            base[destination] += values[1]
            lich[destination] += values[2]
        return base, lich, mods

    @staticmethod
    def _build_faction_modifiers(faction: str) -> dict[str, float]:
        try:
            modifiers = FACTION_MULTIPLIERS[faction_key(faction)]
        except KeyError:
            raise ValueError(f"Unknown faction: {faction!r}") from None
        return {kind: float(modifiers[kind]) for kind in DAMAGE_TYPES}

    @staticmethod
    def _build_armor_modifiers(armor_value: float, faction_modifiers: dict[str, float]) -> dict[str, float]:
        armor_term = 1.0 - enemy_armor_damage_reduction(armor_value)
        return {kind: armor_term * faction_modifiers[kind] for kind in DAMAGE_TYPES}
