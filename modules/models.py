from __future__ import annotations

from dataclasses import dataclass, field

from .constants import DAMAGE_TYPES, MOD_STAT_ORDER


@dataclass(slots=True)
class Weapon:
    weapon: str
    unique_name: str
    product_category: str
    slot_group: str
    dmg: float
    critchan: float
    critmult: float
    statchan: float
    firerate: float
    multi: float
    damage: dict[str, float] = field(default_factory=dict)

    def damage_for(self, damage_type: str) -> float:
        return float(self.damage.get(damage_type, 0.0))


@dataclass(slots=True)
class ModEffect:
    code: str
    value: float
    text: str
    position: int = 0


@dataclass(slots=True)
class Mod:
    unique_name: str
    name: str
    mod_type: str
    compat_name: str
    polarity: str
    rarity: str
    fusion_limit: int
    base_drain: int
    description: str
    effect_summary: str
    supported: bool


@dataclass(slots=True)
class EquippedMod:
    mod: Mod | None = None
    rank: int = 0
    effects: list[ModEffect] = field(default_factory=list)


@dataclass(slots=True)
class CalculationInputs:
    weapon_name: str
    faction: str
    armor_value: float
    lich_element: str = ""
    valence_base: float = 0.0
    # Pre-aggregated per-stat bonuses, used only when `equipped_mods` is None.
    # When the slots are also given the calculator aggregates them itself and
    # ignores this dictionary, so a build cannot depend on whether the caller
    # remembered to pre-compute `mods`.
    mods: dict[str, float] = field(default_factory=dict)
    # Original slot order preserves which primary elements formed a pair.
    equipped_mods: list[EquippedMod] | None = None


@dataclass(slots=True)
class CalculationResults:
    base_weapon_damage: float
    quanta: float
    valence_multiplier: float
    weapon_total_damage: float
    lich_damage: dict[str, float]
    faction_modifiers: dict[str, float]
    armor_modifiers: dict[str, float]
    hud_damage_by_type: dict[str, float]
    final_damage_by_type: dict[str, float]
    aggregated_mods: dict[str, float]
    hud_total: float
    hud_total_with_bane: float
    final_total: float
    final_total_with_bane: float
    warnings: list[str] = field(default_factory=list)

    def rows_for_hud(self) -> list[tuple[str, float]]:
        return [(damage_type, self.hud_damage_by_type[damage_type]) for damage_type in DAMAGE_TYPES]

    def rows_for_final(self) -> list[tuple[str, float]]:
        return [(damage_type, self.final_damage_by_type[damage_type]) for damage_type in DAMAGE_TYPES]

    def rows_for_mods(self) -> list[tuple[str, float]]:
        return [(code, self.aggregated_mods.get(code, 0.0)) for code in MOD_STAT_ORDER]
