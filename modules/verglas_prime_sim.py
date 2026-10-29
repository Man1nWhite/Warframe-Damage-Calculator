"""Verglas Prime trials against the repository's Eximus Heavy Gunner dummy.

This is an experimental model of one Sentinel rifle firing at Dummy A
(``enemy_scaling.steel_path_eximus_heavy_gunner(150)``: 1,716,837 HP,
2,700 armor and 269,919 Overguard), not a prediction of in-game time to kill.
It exists to compare mod loadouts with the same mechanics: the element
hierarchy, the 1/32 damage quantization, critical tiers, the Overguard ->
health routing and the timed status model all come from the repository's
audited core rather than being re-derived here.

Weapon model (WARFRAME Wiki, retrieved 2026-10-28):

* Verglas Prime: 32 Cold, 14% critical chance, 2.20x critical multiplier,
  36% status chance, 12.0 attacks/s, magazine 80, 1.6 s reload, hit-scan,
  0.0 m innate punch-through. Robotic weapons accept Rifle mods.
* Continuous weapon: the arsenal status chance is per damage instance, and
  multishot beam instances that hit the same target merge into one instance
  whose damage *and* status chance are the sums of the beams
  (``status_damage.beam_merged_status_chance``), while critical chance stays
  that of a single beam.
* Fired Up (Sentinel-only): +5% Heat damage per hit, capped at +100% after
  20 hits, reset after 5 s without a hit. Damage-over-time ticks from the
  Sentinel's own attacks also build stacks. Since Update 34 the bonus "applies
  the same way adding a Mod would", so it enters the Heat bracket and the
  Heat DoT's Heat multiplier; it also combines with the weapon's elements.
* Summoner's Wrath (aura): +75% Companion and Summon damage, additive with
  faction damage bonuses. Like a Bane mod it therefore applies to direct
  damage once, and to a Heat tick twice (``Damage/Heat_Damage``: faction
  enters both Modded Base Damage and the tick multiplier).
* Rifle Elementalist: +90% Status Damage, +0.6 m punch through. Status Damage
  is a final multiplicative term on every DoT tick.

Modelled statuses are Heat, Viral, Magnetic and Cold. A loadout whose element
mix produces any other damaging proc type (Blast, Corrosive, Gas, Toxin,
Radiation) is rejected by :func:`build_verglas` instead of being silently
mis-simulated.

Deviations, all conservative or documented in ``docs/formula_audit.md``:

* Punch-through is not simulated: the target is a single dummy, and piercing
  extra bodies only matters against a pack (``Cordon`` clumps). Extra bodies
  do not change this dummy's time to kill.
* Heat's first-proc "inherit" lock is not modelled. Verglas is the only Heat
  source, but Fired Up changes its Heat bonus during a fight, so the effect
  of inheritance on this changing bonus remains an unverified limitation.
* Punch-through, shields, weak points and body parts are out of scope.
"""
from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, field

from .alternox_prime_sim import load_rifle_riven_averages
from .calculator import DamageCalculator
from .constants import FACTION_MULTIPLIERS
from .crit import crit_multiplier_for_tier, quantize_crit_multiplier
from .damage_routing import RoutedDamage
from .enemy_scaling import steel_path_eximus_heavy_gunner, steel_path_heavy_gunner
from .kuva_nukor_sim import (
    DummyTarget,
    HeatProc,
    MagneticBreakProc,
    MagneticSource,
    roll_multishot,
)
from .models import CalculationInputs, EquippedMod, Mod, ModEffect, Weapon
from .status_damage import heat_tick, wiki_quantized_damage
from .trial_statistics import sample_percentile

# --- Weapon (wiki: Verglas_Prime, retrieved 2026-10-28) ---------------------

WEAPON_NAME = "Verglas Prime"
BASE_DAMAGE = 32.0
BASE_DAMAGE_TYPE = "COLD"
BASE_CRIT_CHANCE = 0.14
BASE_CRIT_MULTIPLIER = 2.20
BASE_STATUS_CHANCE = 0.36
BASE_FIRE_RATE = 12.0
MAGAZINE = 80
RELOAD_TIME = 1.60
PUNCH_THROUGH = 0.0

# --- Fixed mechanics -------------------------------------------------------

PROC_DURATION = 6.0
HEAT_STRIP_INTERVAL = 0.5     # 15/30/40/50% strip steps after the first proc
VIRAL_MAG_CAP = 10
# +0.10x Critical Damage for the first Freeze stack etc. is handled by
# ``DummyTarget.crit_damage_multiplier``; Verglas Cold is normally consumed
# into a combined element, so the term is usually zero.

FIRED_UP_STEP = 0.05          # +5% Heat damage per hit
FIRED_UP_MAX_STACKS = 20      # +100% at rank 5
FIRED_UP_RESET = 5.0          # seconds without a hit
SUMMONERS_WRATH = 0.75        # +75% Companion/Summon damage, faction-additive
RIFLE_ELEMENTALIST_SD = 0.90  # +90% Status Damage

# Supported damaging proc types; anything else must fail loudly.
SUPPORTED_PROCS = frozenset({"HEAT", "VIRAL", "MAG", "COLD"})

# --- Mod table ------------------------------------------------------------
#
# ``data/weapons.db`` keeps only effects that the calculator itself consumes
# (damage types, TRUE, BANE), and several critical/rate mods are not even
# listed as supported because the parser rejects their conditional rank text.
# The simulator therefore carries max-rank values, as the other simulators do.

MOD_TABLE: dict[str, dict[str, float]] = {
    # Base damage and multishot
    "Serration": {"TRUE": 1.65},
    "Split Chamber": {"MULTISHOT": 0.90},
    "Vigilante Armaments": {"MULTISHOT": 0.60},
    "Galvanized Chamber": {"MULTISHOT": 0.80},
    # Critical
    "Critical Delay": {"CRIT_CHANCE": 2.00, "FIRE_RATE": -0.20},
    "Point Strike": {"CRIT_CHANCE": 1.50},
    "Vital Sense": {"CRIT_DAMAGE": 1.20},
    "Hammer Shot": {"CRIT_DAMAGE": 0.60, "STATUS_CHANCE": 0.80},
    # Fire rate (and the punch-through that comes with Primed Shred)
    "Speed Trigger": {"FIRE_RATE": 0.60},
    "Vile Acceleration": {"FIRE_RATE": 0.90, "TRUE": -0.15},
    "Primed Shred": {"FIRE_RATE": 0.55, "PUNCTHROUGH": 2.20},
    # 60/60 and 90% elemental mods
    "Rime Rounds": {"COLD": 0.60, "STATUS_CHANCE": 0.60},
    "High Voltage": {"ELEC": 0.60, "STATUS_CHANCE": 0.60},
    "Malignant Force": {"TOXIN": 0.60, "STATUS_CHANCE": 0.60},
    "Thermite Rounds": {"HEAT": 0.60, "STATUS_CHANCE": 0.60},
    "Hellfire": {"HEAT": 0.90},
    "Primed Cryo Rounds": {"COLD": 1.65},
    # Utility
    "Rifle Elementalist": {"STATUS_DAMAGE": RIFLE_ELEMENTALIST_SD,
                           "PUNCTHROUGH": 0.60},
    "Primed Bane of Grineer": {"BANE_GRINEER": 0.55},
}

# Fired Up is a Sentinel mod, not a weapon slot: it is added to every build
# and ramped per hit, so it is deliberately absent from MOD_TABLE's static
# application (``_static_effects`` skips it) and from the eight weapon slots.
FIRED_UP = "Fired Up"

# Riven stat names are the ``stat_name`` column of
# ``source/riven_stats_average_1_2.csv``; a spliced combined element (Viral,
# Blast, ...) is not in that table and takes the base-element value, as the
# Splicer workbench gives combined traits the same range.
RIVEN_CODES: dict[str, str] = {
    "Damage": "TRUE",
    "Multishot": "MULTISHOT",
    "Critical Chance": "CRIT_CHANCE",
    "Critical Damage": "CRIT_DAMAGE",
    "Fire Rate / Attack Speed": "FIRE_RATE",
    "Status Chance": "STATUS_CHANCE",
    "Status Duration": "STATUS_DURATION",
    "Punch Through": "PUNCTHROUGH",
    "Heat": "HEAT",
    "Cold": "COLD",
    "Electricity": "ELEC",
    "Toxin": "TOXIN",
    "Viral": "VIRAL",
    "Blast": "BLAST",
    "Magnetic": "MAG",
    "Corrosive": "CORR",
    "Gas": "GAS",
    "Radiation": "RAD",
    "Damage to Grineer": "BANE_GRINEER",
}
# Combined traits reuse the base-element roll of the vendored table.
COMBINED_RIVEN_FALLBACK = ("Viral", "Blast", "Magnetic", "Corrosive", "Gas",
                           "Radiation")


def verglas_prime_weapon() -> Weapon:
    """The wiki stat block as a :class:`Weapon` the calculator can consume."""
    return Weapon(
        weapon=WEAPON_NAME,
        unique_name="/Lotus/Weapons/Tenno/Robotic/VerglasPrime",
        product_category="SentinelWeapons",
        slot_group="PRIMARY",
        dmg=BASE_DAMAGE,
        critchan=BASE_CRIT_CHANCE,
        critmult=BASE_CRIT_MULTIPLIER,
        statchan=BASE_STATUS_CHANCE,
        firerate=BASE_FIRE_RATE,
        multi=1.0,
        damage={kind: 0.0 for kind in ("IMPACT", "PUNC", "SLASH", "HEAT",
                                      "COLD", "ELEC", "TOXIN", "BLAST", "RAD",
                                      "GAS", "MAG", "VIRAL", "CORR", "VOID")}
        | {BASE_DAMAGE_TYPE: BASE_DAMAGE},
    )


# --- Loadouts -------------------------------------------------------------

@dataclass(frozen=True)
class RivenTraits:
    """Three Riven positives by ``stat_name``.

    ``cursed`` identifies a three-positive/one-negative Riven, but the curse
    itself is not represented. Such a build is rejected by ``build_verglas``
    rather than granting the larger positives while silently ignoring the malus.
    """

    positives: tuple[str, ...]
    cursed: bool = False

    def __post_init__(self) -> None:
        if len(self.positives) != 3:
            raise ValueError("a three-positive Riven needs exactly three "
                             f"positives, got {self.positives!r}")
        unknown = [name for name in self.positives
                   if name not in RIVEN_CODES and name not in COMBINED_RIVEN_FALLBACK]
        if unknown:
            raise ValueError(f"unknown Riven stat names: {unknown}")
        if len(set(self.positives)) != len(self.positives):
            raise ValueError("Riven positive traits must be distinct")
        if sum(stat in COMBINED_RIVEN_FALLBACK for stat in self.positives) > 1:
            raise ValueError("only one spliced trait can be on a Riven")


@dataclass(frozen=True)
class Loadout:
    """A named eight-mod weapon build plus its Riven."""

    key: str
    mods: tuple[str, ...]
    riven: RivenTraits


# The Riven the request starts from: spliced +Viral plus two positives. The
# last slot is the question the comparison answers, so the candidate builds
# differ only there (or in the element pair, where noted).
RIVEN_VIRAL_MS_CD = RivenTraits(("Viral", "Multishot", "Critical Damage"))
RIVEN_HEAT_MS_CD = RivenTraits(("Heat", "Multishot", "Critical Damage"))

_FIXED = ("Serration", "Split Chamber", "Rime Rounds", "High Voltage",
          "Rifle Elementalist")

BUILDS: tuple[Loadout, ...] = (
    Loadout("user_list_crit_pair", _FIXED + ("Critical Delay", "Vital Sense"),
            RIVEN_VIRAL_MS_CD),
    Loadout("critical_delay_only", _FIXED + ("Critical Delay",),
            RIVEN_VIRAL_MS_CD),
    Loadout("vital_sense_only", _FIXED + ("Vital Sense",), RIVEN_VIRAL_MS_CD),
    Loadout("heat_pair", _FIXED + ("Hellfire", "Thermite Rounds"),
            RIVEN_VIRAL_MS_CD),
    Loadout("heat_vital_sense", _FIXED + ("Hellfire", "Vital Sense"),
            RIVEN_VIRAL_MS_CD),
    Loadout("heat_vile_acceleration", _FIXED + ("Hellfire", "Vile Acceleration"),
            RIVEN_VIRAL_MS_CD),
    Loadout("heat_primed_shred", _FIXED + ("Hellfire", "Primed Shred"),
            RIVEN_VIRAL_MS_CD),
    Loadout("viral_heat", ("Serration", "Split Chamber", "Rime Rounds",
                           "Malignant Force", "Rifle Elementalist", "Hellfire",
                           "Thermite Rounds"), RIVEN_HEAT_MS_CD),
    # A candidate retaining the user's +Viral/+Multishot/+Critical Damage
    # Riven and adding punch-through. Actual Cordon geometry is not simulated.
    Loadout("final_recommended", _FIXED + ("Hellfire", "Primed Shred"),
            RIVEN_VIRAL_MS_CD),
)
BUILD_BY_KEY = {loadout.key: loadout for loadout in BUILDS}


# --- Build -----------------------------------------------------------------

def _riven_effects(loadout: Loadout) -> dict[str, float]:
    """Riven positives as ``{code: value}`` from the vendored average table."""
    averages = load_rifle_riven_averages(
        "buff_3_pos_1_neg" if loadout.riven.cursed else "buff_3_pos")
    effects: dict[str, float] = {}
    for stat in loadout.riven.positives:
        # Spliced combined traits are absent from the base-attribute table and
        # share the base-element range; the Toxin roll is representative.
        value = averages["Toxin" if stat in COMBINED_RIVEN_FALLBACK else stat]
        code = RIVEN_CODES[stat]
        effects[code] = effects.get(code, 0.0) + value
    return effects


def _static_effects(loadout: Loadout) -> dict[str, float]:
    """Summed max-rank effects of the weapon mods, without Fired Up."""
    effects: dict[str, float] = {}
    for name in loadout.mods:
        if name == FIRED_UP:
            raise ValueError("Fired Up is a Sentinel mod; it is added by the "
                             "simulator and must not occupy a weapon slot")
        try:
            table = MOD_TABLE[name]
        except KeyError:
            raise KeyError(f"no max-rank values for mod {name!r}") from None
        for code, value in table.items():
            effects[code] = effects.get(code, 0.0) + value
    for code, value in _riven_effects(loadout).items():
        effects[code] = effects.get(code, 0.0) + value
    return effects


def _mod(name: str, effects: tuple[tuple[str, float], ...],
         *, sentinel: bool = False) -> EquippedMod:
    mod = Mod(
        unique_name=f"/sim/{name}",
        name=name,
        mod_type="",
        compat_name="Sentinel" if sentinel else "Rifle",
        polarity="",
        rarity="",
        fusion_limit=0,
        base_drain=0,
        description="",
        effect_summary="",
        supported=True,
    )
    return EquippedMod(mod=mod, rank=0, effects=[
        ModEffect(code=code, value=value, text="") for code, value in effects])


def _equipped(loadout: Loadout, *, fired_up_heat: float | None) -> list[EquippedMod]:
    """Slots for the calculator; ``fired_up_heat=None`` omits Fired Up."""
    slots = [_mod(name, tuple(MOD_TABLE[name].items())) for name in loadout.mods]
    slots.append(_mod("Riven", tuple(_riven_effects(loadout).items())))
    if fired_up_heat is not None:
        # Appended last: Fired Up's Heat sits at the bottom of the element
        # hierarchy, behind the equipped mods and the innate Cold.
        slots.append(_mod(FIRED_UP, (("HEAT", fired_up_heat),), sentinel=True))
    return slots


def _hud_by_type(loadout: Loadout, *, fired_up_heat: float | None) -> dict[str, float]:
    results = DamageCalculator().calculate(
        verglas_prime_weapon(),
        CalculationInputs(weapon_name=WEAPON_NAME, faction="Grineer",
                          armor_value=0.0,
                          equipped_mods=_equipped(loadout, fired_up_heat=fired_up_heat)),
    )
    return {kind: value for kind, value in results.hud_damage_by_type.items() if value > 0}


@dataclass(frozen=True)
class VerglasBuild:
    """Resolved stats and element mix for one loadout."""

    key: str
    loadout: Loadout
    effects: dict[str, float]
    hud_by_type_full: dict[str, float]      # Fired Up at +100%, per beam
    hud_by_type_zero: dict[str, float]      # Fired Up at 0%
    multishot: float
    crit_chance: float
    crit_multiplier: float
    status_chance: float
    fire_rate: float
    punch_through: float
    damage_bonus: float
    faction_bonus: float
    heat_bonus_static: float
    modded_base: float

    @property
    def headroom_bodies(self) -> int:
        """Rough extra-body estimate using 1.2 m per body, not a guarantee.

        Enemy hitboxes vary; the simulated target is a single dummy, so no
        punch-through geometry or additional targets affect its time to kill.
        """
        return max(0, math.floor((self.punch_through + PUNCH_THROUGH) / 1.2))

    def heat_bonus(self, stacks: int) -> float:
        return self.heat_bonus_static + FIRED_UP_STEP * stacks

    def type_damage(self, stacks: int) -> dict[str, float]:
        """Per-beam type damage with the Heat bracket ramped by Fired Up."""
        ramp = stacks / FIRED_UP_MAX_STACKS if stacks else 0.0
        heat_zero = self.hud_by_type_zero.get("HEAT", 0.0)
        heat_full = self.hud_by_type_full.get("HEAT", 0.0)
        out: dict[str, float] = {}
        for kind, value in self.hud_by_type_full.items():
            if kind == "HEAT":
                value = heat_zero + ramp * (heat_full - heat_zero)
            if value > 0:
                out[kind] = value
        return out

    def multishot_beams(self, rng: random.Random) -> int:
        return roll_multishot(rng, self.multishot)

    def proc_weights(self, stacks: int) -> tuple[list[str], list[float]]:
        types = self.type_damage(stacks)
        total = sum(types.values())
        if total <= 0:
            raise ValueError(f"{self.key}: build deals no damage")
        kinds = sorted(types, key=lambda kind: -types[kind])
        return kinds, [types[kind] / total for kind in kinds]


def build_verglas(loadout: Loadout) -> VerglasBuild:
    """Resolve one loadout, rejecting unsupported or impossible inputs."""
    if loadout.riven.cursed:
        raise ValueError("cursed Riven negative effects are not modelled")
    if len(loadout.mods) > 7:  # the required Riven occupies one weapon slot
        raise ValueError("the Riven plus weapon mods must fit in eight slots")
    if len(set(loadout.mods)) != len(loadout.mods):
        raise ValueError("a weapon cannot equip the same mod more than once")
    for incompatible in ({"Critical Delay", "Point Strike"},
                         {"Split Chamber", "Galvanized Chamber"}):
        if incompatible <= set(loadout.mods):
            raise ValueError(f"incompatible weapon mods: {', '.join(sorted(incompatible))}")
    effects = _static_effects(loadout)
    hud_full = _hud_by_type(loadout, fired_up_heat=FIRED_UP_STEP * FIRED_UP_MAX_STACKS)
    hud_zero = _hud_by_type(loadout, fired_up_heat=0.0)
    # Fired Up may only scale an existing standalone Heat group. If it would
    # create or destroy a pairing, the interpolation in ``type_damage`` is
    # invalid, so fail instead of reporting a number.
    if set(hud_full) - {"HEAT"} != set(hud_zero) - {"HEAT"}:
        raise ValueError(f"{loadout.key}: Fired Up changes the element pairing "
                         f"({sorted(hud_zero)} -> {sorted(hud_full)}); the ramp "
                         "needs Heat to stay a standalone group")
    unsupported = set(hud_full) - SUPPORTED_PROCS
    if unsupported:
        raise ValueError(f"{loadout.key}: proc type(s) {sorted(unsupported)} are "
                         "not modelled by this simulator")
    heat_static = effects.get("HEAT", 0.0)
    return VerglasBuild(
        key=loadout.key,
        loadout=loadout,
        effects=effects,
        hud_by_type_full=hud_full,
        hud_by_type_zero=hud_zero,
        multishot=1.0 + effects.get("MULTISHOT", 0.0),
        crit_chance=BASE_CRIT_CHANCE * (1.0 + effects.get("CRIT_CHANCE", 0.0)),
        crit_multiplier=(quantize_crit_multiplier(BASE_CRIT_MULTIPLIER)
                         * (1.0 + effects.get("CRIT_DAMAGE", 0.0))),
        status_chance=BASE_STATUS_CHANCE * (1.0 + effects.get("STATUS_CHANCE", 0.0)),
        fire_rate=BASE_FIRE_RATE * (1.0 + effects.get("FIRE_RATE", 0.0)),
        punch_through=PUNCH_THROUGH + effects.get("PUNCTHROUGH", 0.0),
        damage_bonus=effects.get("TRUE", 0.0),
        faction_bonus=SUMMONERS_WRATH + effects.get("BANE_GRINEER", 0.0),
        heat_bonus_static=heat_static,
        modded_base=BASE_DAMAGE * (1.0 + effects.get("TRUE", 0.0)),
    )


# --- Trial -----------------------------------------------------------------

@dataclass
class Trial:
    ttk: float
    overguard_break_time: float
    attacks: int
    reloads: int
    heat_procs: int
    viral_procs: int
    magnetic_procs: int
    cold_procs: int
    fired_up_peak: int
    final_armor: float
    direct_to_overguard: float = 0.0
    direct_to_health: float = 0.0
    dot_to_overguard: float = 0.0
    dot_to_health: float = 0.0
    break_electric: float = 0.0
    trace: list[str] = field(default_factory=list)


def eximus_dummy_factory() -> DummyTarget:
    """Dummy A: level-150 Steel Path Eximus Heavy Gunner."""
    enemy = steel_path_eximus_heavy_gunner(150)
    return DummyTarget(enemy.health, enemy.armor, enemy.overguard)


def heavy_gunner_factory() -> DummyTarget:
    """The same Heavy Gunner without Eximus Overguard, for comparison."""
    enemy = steel_path_heavy_gunner(150)
    return DummyTarget(enemy.health, enemy.armor, enemy.overguard)


def _crit_factor(rng: random.Random, build: VerglasBuild,
                 target: DummyTarget, when: float) -> float:
    chance = max(build.crit_chance, 0.0)
    tiers = int(math.floor(chance))
    tier = tiers + (1 if rng.random() < chance - tiers else 0)
    # Cold stacks raise Critical Damage for this target; normally zero because
    # the Verglas element mix consumes Cold into Magnetic/Viral/Blast.
    return crit_multiplier_for_tier(
        target.crit_damage_multiplier(build.crit_multiplier, when), tier)


def simulate(build: VerglasBuild,
             target: DummyTarget,
             *,
             seed: int = 1,
             max_time: float = 600.0,
             trace: bool = False,
             trace_interval_s: float = 10.0) -> Trial:
    """One Monte Carlo trial: fire until the dummy dies or ``max_time``."""
    rng = random.Random(seed)
    dt = 1.0 / build.fire_rate
    gunner_types = FACTION_MULTIPLIERS["Grineer"]
    status_damage_bonus = build.effects.get("STATUS_DAMAGE", 0.0)
    duration_multiplier = 1.0 + build.effects.get("STATUS_DURATION", 0.0)
    proc_duration = PROC_DURATION * duration_multiplier
    heat_strip_interval = HEAT_STRIP_INTERVAL * duration_multiplier
    magnetic_source = MagneticSource(
        status_damage_bonus=status_damage_bonus,
        faction_bonus=build.faction_bonus,
        # Electricity bonuses still apply when combined into Magnetic.
        electricity_bonus=build.effects.get("ELEC", 0.0),
        duration_multiplier=duration_multiplier,
    )
    ammo = float(MAGAZINE)
    now = 0.0
    attacks = reloads = 0
    stacks = 0
    peak_stacks = 0
    last_hit: float | None = None
    counts = {"HEAT": 0, "VIRAL": 0, "MAG": 0, "COLD": 0}
    buckets = {"direct_og": 0.0, "direct_hp": 0.0, "dot_og": 0.0,
               "dot_hp": 0.0, "break": 0.0}
    log: list[str] = []
    # A supplied target can already carry someone else's statuses. Keep
    # references to our own procs so only our DoT ticks build Fired Up.
    own_heat: dict[int, HeatProc] = {}
    own_electric: dict[int, MagneticBreakProc] = {}

    def register_fired_up_hit(when: float) -> None:
        nonlocal stacks, peak_stacks, last_hit
        if last_hit is not None and when - last_hit >= FIRED_UP_RESET:
            stacks = 0
        previous = stacks
        stacks = min(FIRED_UP_MAX_STACKS, stacks + 1)
        peak_stacks = max(peak_stacks, stacks)
        last_hit = when
        if trace and previous < FIRED_UP_MAX_STACKS == stacks:
            log.append(f"  t={when:7.2f}s Fired Up capped (+100% Heat)")

    def process_magnetic(when: float) -> None:
        target.prune(when, proc_duration)
        while target.health > 0 and target.next_magnetic_electric_tick() <= when:
            tick_at = target.next_magnetic_electric_tick()
            own_tick = any(id(proc) in own_electric and proc.next_tick == tick_at
                           for proc in target.magnetic_break_procs)
            for _, result in target.process_magnetic_electric_until(
                    tick_at, heat_strip_interval, faction_type_modifiers=gunner_types):
                buckets["break"] += result.health
                if own_tick and (result.overguard > 0 or result.health > 0):
                    register_fired_up_hit(tick_at)

    def route(damage: dict[str, float], when: float, category: str) -> RoutedDamage:
        target.prune(when, proc_duration)
        previous_break_procs = len(target.magnetic_break_procs)
        result = target.absorb(damage, when, heat_strip_interval,
                               faction_type_modifiers=gunner_types)
        buckets[category + "_og"] += result.overguard
        buckets[category + "_hp"] += result.health
        if result.broke_overguard:
            if (target.magnetic_source is magnetic_source
                    and len(target.magnetic_break_procs) > previous_break_procs):
                proc = target.magnetic_break_procs[-1]
                own_electric[id(proc)] = proc
            if trace:
                log.append(f"  t={when:6.2f}s Overguard broke "
                           f"(magnetic x{target.mag_stacks(when)})")
            process_magnetic(when)
        return result

    def heat_tick_at(when: float) -> None:
        ready = target.consume_heat_tick(when, proc_duration)
        if not ready:
            return
        # Each proc folded its own (1 + Heat bonus) and critical multiplier
        # into its seed, so one consolidated tick uses the shared accumulator.
        weighted = sum(proc.seed * proc.crit_factor for proc in ready)
        result = route({"HEAT": heat_tick(weighted,
                                          faction_bonus=build.faction_bonus,
                                          status_damage_bonus=status_damage_bonus,
                                          accumulator=True)}, when, "dot")
        if (any(id(proc) in own_heat for proc in ready)
                and (result.overguard > 0 or result.health > 0)):
            register_fired_up_hit(when)

    def advance_events(until: float) -> float | None:
        while target.health > 0:
            next_heat = target.next_heat_tick(proc_duration)
            next_electric = target.next_magnetic_electric_tick()
            event = min(next_heat, next_electric)
            if event > until:
                break
            if next_electric <= next_heat:
                process_magnetic(event)
            else:
                heat_tick_at(event)
            if target.health <= 0:
                return event
        return None

    while now < max_time and target.health > 0:
        if ammo <= 0:
            reloads += 1
            reload_end = now + RELOAD_TIME
            death_time = advance_events(min(reload_end, max_time))
            if death_time is not None:
                now = death_time
                break
            if reload_end >= max_time:
                now = max_time
                break
            now = reload_end
            ammo = MAGAZINE
            continue

        death_time = advance_events(now)
        if death_time is not None:
            now = death_time
            break

        # Both weapon hits and the weapon's DoT ticks build Fired Up.
        register_fired_up_hit(now)

        beams = build.multishot_beams(rng)
        crit = _crit_factor(rng, build, target, now)
        faction = 1.0 + build.faction_bonus
        direct = {
            kind: wiki_quantized_damage(value, build.modded_base)
            * beams * crit * faction
            for kind, value in build.type_damage(stacks).items()
        }
        route(direct, now, "direct")
        attacks += 1
        ammo -= 1.0
        if target.health <= 0:
            break

        # Continuous weapon: merged beams add their status chances.
        merged_status = build.status_chance * beams
        guaranteed = int(math.floor(merged_status))
        n_procs = guaranteed + (1 if rng.random() < merged_status - guaranteed else 0)
        kinds, weights = build.proc_weights(stacks)
        # The Heat seed is Modded Base Damage (which already contains the
        # faction bonus) times the proc's own Heat bracket and crit factor.
        seed_damage = (build.modded_base * (1.0 + build.faction_bonus) * beams
                       * (1.0 + build.heat_bonus(stacks)))
        for ptype in rng.choices(kinds, weights=weights, k=n_procs):
            if target.health <= 0:
                break
            counts[ptype] += 1
            if ptype == "HEAT":
                target.record_status(ptype, now, proc_duration)
                target.add_heat(now, seed_damage, crit, proc_duration)
                if len(target.heat_procs) == 1:
                    own_heat.clear()  # a new group replaced expired procs
                proc = target.heat_procs[-1]
                own_heat[id(proc)] = proc
            elif ptype == "VIRAL":
                target.record_status(ptype, now, proc_duration)
                target.viral_expiries.append(now + proc_duration)
                target.viral_expiries = target.viral_expiries[-VIRAL_MAG_CAP:]
            elif ptype == "MAG":
                target.add_magnetic(now, proc_duration, magnetic_source)
            elif ptype == "COLD":
                # add_cold owns status bookkeeping and rejects applications
                # during Freeze; a generic refresh here would bypass it.
                target.add_cold(now, proc_duration)

        if trace and attacks % max(1, int(trace_interval_s * build.fire_rate)) == 0:
            log.append(
                f"  t={now:7.2f}s og={max(target.overguard, 0):9.0f} "
                f"hp={max(target.health, 0):10.0f} "
                f"armor={target.current_armor(now, heat_strip_interval):7.0f} "
                f"heat={len(target.heat_procs):3d} "
                f"viral={target.viral_stacks(now):2d} "
                f"mag={target.mag_stacks(now):2d} fired_up={stacks:2d}")

        if target.health <= 0:
            break
        now += dt

    if target.health > 0 and now >= max_time:
        death_time = advance_events(max_time)
        now = death_time if death_time is not None else max_time

    ttk = now if target.health <= 0 else math.inf
    return Trial(
        ttk=ttk,
        overguard_break_time=(target.overguard_broken_at
                              if target.overguard_broken_at is not None
                              else 0.0 if target.overguard_max <= 0 else math.inf),
        attacks=attacks,
        reloads=reloads,
        heat_procs=counts["HEAT"],
        viral_procs=counts["VIRAL"],
        magnetic_procs=counts["MAG"],
        cold_procs=counts["COLD"],
        fired_up_peak=peak_stacks,
        final_armor=target.current_armor(ttk if math.isfinite(ttk) else now,
                                         heat_strip_interval),
        direct_to_overguard=buckets["direct_og"],
        direct_to_health=buckets["direct_hp"],
        dot_to_overguard=buckets["dot_og"],
        dot_to_health=buckets["dot_hp"],
        break_electric=buckets["break"],
        trace=log,
    )


def run_trials(build: VerglasBuild,
               trials: int = 200,
               *,
               base_seed: int = 20261028,
               factory=eximus_dummy_factory,
               max_time: float = 600.0) -> dict:
    """Summarize Monte Carlo trials; timeouts are reported, not hidden."""
    if trials < 1:
        raise ValueError("trials must be positive")
    kills: list[float] = []
    breaks: list[float] = []
    reloads: list[int] = []
    heat: list[int] = []
    armors: list[float] = []
    direct: list[float] = []
    dot: list[float] = []
    breaks_dmg: list[float] = []
    for index in range(trials):
        result = simulate(build, factory(), seed=base_seed + index,
                          max_time=max_time)
        if not math.isfinite(result.ttk):
            continue
        kills.append(result.ttk)
        breaks.append(result.overguard_break_time)
        reloads.append(result.reloads)
        heat.append(result.heat_procs)
        armors.append(result.final_armor)
        direct.append(result.direct_to_health)
        dot.append(result.dot_to_health)
        breaks_dmg.append(result.break_electric)
    return {
        "build": build.key,
        "trials": trials,
        "kills": len(kills),
        "timeouts": trials - len(kills),
        "ttk_median": sample_percentile(kills, 0.5, empty=math.inf),
        "ttk_p10": sample_percentile(kills, 0.1, empty=math.inf),
        "ttk_p90": sample_percentile(kills, 0.9, empty=math.inf),
        "overguard_median": sample_percentile(breaks, 0.5),
        "heat_procs_median": sample_percentile(heat, 0.5),
        "reloads_median": sample_percentile(reloads, 0.5),
        "final_armor_median": sample_percentile(armors, 0.5),
        "direct_health_median": sample_percentile(direct, 0.5),
        "dot_health_median": sample_percentile(dot, 0.5),
        "break_electric_median": sample_percentile(breaks_dmg, 0.5),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verglas Prime vs Dummy A")
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261028)
    parser.add_argument("--max-time", type=float, default=600.0)
    parser.add_argument("--build", action="append", default=None,
                        help="limit to these build keys (repeatable)")
    args = parser.parse_args()
    keys = args.build or [loadout.key for loadout in BUILDS]
    dummy = eximus_dummy_factory()
    print(f"{WEAPON_NAME} vs level-150 Steel Path Eximus Heavy Gunner "
          f"({dummy.max_health:,.0f} HP / {dummy.max_armor:,.0f} armor / "
          f"{dummy.overguard_max:,.0f} Overguard)")
    print(f"Fired Up maxed, Summoner's Wrath +75%, {args.trials} trials each, "
          f"seed {args.seed}\n")
    header = (f"{'build':26s} {'TTK med':>8s} {'p10':>8s} {'p90':>8s} "
              f"{'OG break':>8s} {'heat':>5s} {'reloads':>7s} {'TO':>3s} {'armor':>6s}")
    print(header)
    built = {key: build_verglas(BUILD_BY_KEY[key]) for key in keys}
    summaries: dict[str, dict] = {}
    for key in keys:
        summary = run_trials(built[key], args.trials, base_seed=args.seed,
                             max_time=args.max_time)
        summaries[key] = summary
        print(f"{key:26s} {summary['ttk_median']:8.2f} {summary['ttk_p10']:8.2f} "
              f"{summary['ttk_p90']:8.2f} {summary['overguard_median']:8.2f} "
              f"{summary['heat_procs_median']:5.0f} "
              f"{summary['reloads_median']:7.0f} "
              f"{summary['timeouts']:3d} "
              f"{summary['final_armor_median']:6.0f}")
    if len(keys) > 1:
        print("\nhealth damage, medians of the killed trials "
              "(direct+Heat is the sum of component medians):")
        print(f"{'build':26s} {'direct':>10s} {'Heat DoT':>10s} "
              f"{'break':>11s} {'direct+Heat':>11s}")
        for key in keys:
            summary = summaries[key]
            gun = summary["direct_health_median"] + summary["dot_health_median"]
            print(f"{key:26s} {summary['direct_health_median']:10,.0f} "
                  f"{summary['dot_health_median']:10,.0f} "
                  f"{summary['break_electric_median']:11,.0f} {gun:11,.0f}")
    if len(keys) == 1:
        build = built[keys[0]]
        summary = summaries[keys[0]]
        cold = build.hud_by_type_zero
        hot = build.hud_by_type_full
        print("\nresolved build:")
        for kind in sorted(hot, key=lambda name: -hot[name]):
            print(f"  {kind:5s} {cold.get(kind, 0.0):7.2f} -> {hot[kind]:7.2f} "
                  "per beam (Fired Up 0 -> 20 hits)")
        print(f"  multishot {build.multishot:.2f} x {build.fire_rate:.2f}/s, "
              f"crit {build.crit_chance:.0%} of {build.crit_multiplier:.2f}x, "
              f"status {build.status_chance:.0%}/beam, "
              f"PT {build.punch_through:.1f} m "
              f"(~{build.headroom_bodies} extra bodies using 1.2 m/body; hitboxes vary)")
        print(f"\nhealth damage, component medians of {summary['kills']} kills: "
              f"direct {summary['direct_health_median']:,.0f} + Heat DoT "
              f"{summary['dot_health_median']:,.0f} + Overguard-break Electricity "
              f"{summary['break_electric_median']:,.0f}")


if __name__ == "__main__":
    main()
