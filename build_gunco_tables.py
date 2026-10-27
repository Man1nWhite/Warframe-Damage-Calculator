#!/usr/bin/env python3
"""Build the GunCO (Condition Overload-type) mechanic tables.

Sources
-------
1. source/conditionOverload.ts
   Rule table transcribed from wiki.warframe.com/w/Condition_Overload_(Mechanic)
   (wiki pull Oct 2026); gaps in the secondary/melee coverage are filled from
   "rainy's GunCO sheet" (38.0.12, Feb 2025) and marked ``source == "gunco_sheet"``.
   Covers the Primary and Secondary catalogs.
2. WIKI_ONLY_RULES below
   Rows read directly from the wiki's Melee, Exalted/Pseudo-Exalted, Archgun,
   Robotic and Amp Attack Catalogs (retrieved 2026-10-27, page last edited
   2026-10-05). The wiki lists only *discrepant* attacks; everything not listed
   is intended additive +100%.

Outputs
-------
- source/gunco_mechanic.json  full structured dataset (meta, formulas, sources, rules)
- source/gunco_mechanic.csv   one row per weapon x rule, spreadsheet friendly
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TS_PATH = ROOT / "source" / "conditionOverload.ts"
JSON_OUT = ROOT / "source" / "gunco_mechanic.json"
CSV_OUT = ROOT / "source" / "gunco_mechanic.csv"

CONST = {
    "BOW_CHARGED": "CO only counts the uncharged base damage",
    "DIRECT_ONLY": "Only on the enemy the hitscan shot hits directly, "
    "and scales off the hitscan damage",
}

# section marker -> (weapon section, source)
SECTION_MARKERS = {
    "primaries (wiki)": ("primary", "wiki"),
    "primaries the wiki table doesn't have (sheet)": ("primary", "gunco_sheet"),
    "secondaries (wiki, down to Ballistica)": ("secondary", "wiki"),
    "the rest of the secondaries (sheet)": ("secondary", "gunco_sheet"),
}

# Rows transcribed directly from the wiki Attack Catalog (2026-10-27).
# attack_pattern uses the wiki's attack wording (kept in attack_name); the TS
# cross-reference instead uses warframe-items attack names. Tuple layout:
# (section, weapons, wiki attack name, mode, scale, note).
WIKI_ONLY_RULES = [
    # --- Primary rows the TS cross-reference misses ---
    ("primary", ["Sporelacer"], "Normal Attack", "multiply", 1.0,
     "Tremor grip; kitgun primary chamber"),
    ("primary", ["Tombfinger"], "Normal Attack", "multiply", 1.0,
     "Brash grip; kitgun primary chamber"),
    ("primary", ["Zenith"], "Alt-fire Disk Bonk", "multiply", 1.0, None),
    ("primary", ["Vadarya Prime"], "Primary Fire Lightning Strikes", "none", 1.0,
     "AoE does not apply"),
    # --- Secondary rows the TS cross-reference misses ---
    ("secondary", ["Ballistica Prime"], "Incarnon Mode", "multiply", 1.0, None),
    ("secondary", ["Catabolyst"], "Partial Reload Impact", "multiply", 1.0, None),
    ("secondary", ["Catabolyst"], "Reload From Empty Impact", "multiply", 1.0, None),
    ("secondary", ["Mk1-Kunai"], "Incarnon Mode", "multiply", 1.0,
     "CO uses the Evolution base damage too"),
    ("secondary", ["Tombfinger"], "Normal Attack", "multiply", 1.0,
     "Kitgun secondary chamber"),
    ("secondary", ["Sporelacer"], "Normal Attack", "add", 0.63,
     "CO uses a 57 damage value regardless of configuration"),
    ("secondary", ["Sporelacer"], "Bomblet Impact", "add", 6.33,
     "CO uses the parent projectile's 57 damage value"),
    ("secondary", ["Castanas"], "Normal Attack", "none", 1.0, "AoE does not apply"),
    ("secondary", ["Sancti Castanas"], "Mid-Flight Detonation", "none", 1.0,
     "AoE does not apply"),
    ("secondary", ["Sancti Castanas"], "Embedded Detonation", "none", 1.0,
     "AoE does not apply"),
    ("secondary", ["Kompressa Prime"], "Radial Attack", "none", 1.0,
     "AoE does not apply"),
    ("secondary", ["Scyotid"], "Alt-Fire Grab", "none", 1.0, "Does not apply"),
    # --- Melees (wiki: only discrepant attacks are listed) ---
    ("melee", ["Corufell"], "Heavy Attack Projectile", "multiply", 1.0, None),
    ("melee", ["Exodia Contagion"], "Aerial Projectile", "multiply", 1.0,
     "2x Zaw base; does not apply to embed damage or resultant AoE"),
    ("melee", ["Nepheri"], "Neutral Combo Fireball", "multiply", 1.0, None),
    ("melee", ["Syam"], "Heavy Attack Wave 1", "multiply", 1.0, None),
    ("melee", ["Syam"], "Heavy Attack Wave 2", "multiply", 1.0, None),
    ("melee", ["Tenet Agendus"], "Heavy Attack Wave 1", "multiply", 0.2, None),
    ("melee", ["Tenet Agendus"], "Heavy Attack Wave 2", "multiply", 0.2, None),
    ("melee", ["Tenet Grigori"], "Energy Disk", "multiply", 1.0,
     "Disk ignores melee base damage (Pressure Point, Arcane Fury); universal "
     "weapon bonuses (Arcane Arachne, Deathbringer) apply and are multiplied by CO"),
    ("melee", ["Verdilac"], "Energy Wave", "multiply", 1.0, None),
    # --- Exalted / pseudo-exalted ---
    ("exalted", ["Exalted Umbra Blade"], "Heavy Waves", "multiply", 1.0, None),
    # --- Archguns (CO reachable only via Secondary Shiver / Shattering Frost) ---
    ("archgun", ["Arbucep"], "Direct Hit", "multiply", 1.0,
     "All 6 projectiles; does not apply to the 228 damage AoE"),
    ("archgun", ["Kuva Ayanga"], "Direct Hit", "multiply", 1.0, None),
    ("archgun", ["Corvas Prime"], "Uncharged Attack", "multiply", 1.0, None),
    ("archgun", ["Corvas Prime"], "Charged Attack", "multiply", 1.0, None),
    ("archgun", ["Grattler"], "Normal Attack", "multiply", 1.0, None),
    ("archgun", ["Larkspur Prime"], "Alt-Fire", "multiply", 1.0, None),
    ("archgun", ["Mandonel"], "Uncharged Attack", "multiply", 1.0, None),
    ("archgun", ["Velocitus"], "Uncharged Attack", "multiply", 1.0, None),
    ("archgun", ["Velocitus"], "Charged Attack", "multiply", 1.0, None),
    # --- Robotic (sentinel / moa weapons) ---
    ("robotic", ["Burst Laser", "Prisma Burst Laser", "Burst Laser Prime"],
     "Normal Attack", "multiply", 1.0, None),
    ("robotic", ["Cryotra"], "Normal Attack", "multiply", 1.0,
     "Does not apply to the lingering cloud AoE"),
    ("robotic", ["Helstrum"], "Normal Attack", "multiply", 1.0, None),
    ("robotic", ["Laser Rifle"], "Normal Attack", "multiply", 1.0, None),
    ("robotic", ["Prime Laser Rifle"], "Normal Attack", "multiply", 1.0, None),
    ("robotic", ["Multron"], "Normal Attack", "multiply", 1.0, None),
    ("robotic", ["Vulklok"], "Normal Attack", "multiply", 1.0, None),
    # --- Amps ---
    ("amp", ["Shwaak Prism"], "Normal Attack", "multiply", 1.0, None),
    ("amp", ["Phahd Scaffold"], "Normal Attack", "multiply", 1.0, None),
    ("amp", ["Shraksun Scaffold"], "Normal Attack", "multiply", 1.0, None),
]

META = {
    "title": "Condition Overload (GunCO) multiplicative stacking tables",
    "wiki_url": "https://wiki.warframe.com/w/Condition_Overload_(Mechanic)",
    "wiki_page_status": "community/unofficial page, banner: actively being worked on",
    "wiki_page_last_edited": "2026-10-05",
    "data_retrieved": "2026-10-27",
    "cross_reference": (
        "dmerced05/verbose-spork-wf-calc src/calc/conditionOverload.ts - "
        "wiki pull Oct 2026 plus rainy's GunCO sheet 38.0.12 (Feb 2025); "
        "vendored at source/conditionOverload.ts"
    ),
    "catalog_scope": (
        "The wiki lists only discrepant attacks. Any attack not listed behaves "
        "as intended: additive +100% of the CO-type bonus."
    ),
    "default_resolution": {
        "unlisted_hitscan_aoe": "add, scale 1.0, direct-hit target only",
        "unlisted_projectile_aoe_radius": "none - projectile explosion radii never receive CO",
        "unlisted_regular_attack": "add, scale 1.0",
    },
}

STACKING_MODES = {
    "multiply": {
        "label": "Multiplying (wiki behavior #1, not intended; mostly projectiles)",
        "formula": "Base x MostDamageBonuses x (1 + CO_bonus) x OtherMultipliers",
        "description": (
            "The CO-type bonus stacks additively with other CO-type bonuses only, "
            "then multiplies against ordinary +% damage bonuses (Serration, Hornet "
            "Strike, Vex Armor, Arcane Fury, Pressure Point, ...)."
        ),
    },
    "add": {
        "label": "Adding (wiki behaviors #2-#4, intended; most hitscan weapons)",
        "formula": "Base x (MostDamageBonuses x OtherMultipliers + CO_bonus x scale)",
        "description": (
            "The CO-type bonus is added to the ordinary +% damage pool. 'scale' is "
            "the wiki's CO-bonus-relative-to-base column for attacks whose CO only "
            "counts part of the base (charged bows, child projectiles, AoE on the "
            "directly hit target). Final multipliers are ignored."
        ),
    },
    "none": {
        "label": "Does not apply (wiki behavior #5; AoE radii and known bugs)",
        "formula": "CO_bonus contribution = 0",
        "description": (
            "Explosion/radius damage of projectile weapons, plus a handful of "
            "documented bugged attacks (Azima turret, Balefire Charger, Glory, "
            "Sonicor, Stug, ...)."
        ),
    },
}

# Every buff that feeds the same CO-type stacking pool (wiki "CO-bonuses" list).
CO_SOURCES = [
    {"name": "Condition Overload", "slot": "melee", "per_status": 0.80,
     "stacks": "unique status types", "cap": None, "note": "+80% per status type"},
    {"name": "Galvanized Aptitude", "slot": "primary", "per_status": 0.40,
     "stacks": 2, "cap": 0.80, "note": "+40% per status type, 2 stacks"},
    {"name": "Galvanized Shot", "slot": "secondary", "per_status": 0.40,
     "stacks": 3, "cap": 1.20, "note": "+40% per status type, 3 stacks"},
    {"name": "Galvanized Savvy", "slot": "shotgun", "per_status": 0.40,
     "stacks": 2, "cap": 0.80, "note": "+40% per status type, 2 stacks"},
    {"name": "Secondary Shiver", "slot": "secondary", "per_status": 0.45,
     "stacks": "Freeze stacks", "cap": None,
     "note": "+45% per Freeze stack; also the only practical GunCO source for archguns"},
    {"name": "Cedo / Cedo Prime (innate alt-fire)", "slot": "secondary",
     "per_status": 0.60, "stacks": "status types", "cap": None,
     "note": "+60% per status type on alt-fire"},
    {"name": "Shattering Frost (Duviri decree, Koumei)", "slot": "decree",
     "per_status": 0.80, "stacks": 3, "cap": 2.40,
     "note": "+80% vs a Frozen target, up to +240%"},
    {"name": "Incarnon Genesis perks", "slot": "incarnon",
     "per_status": None, "stacks": None, "cap": None,
     "note": ("Dual Toxocyst +33%; Lato/Angstrum/Despair/Zylok/Soma +40%; "
              "Latron +30%; Kunai/Dread +100% while target under 50% HP")},
]

# Catalyze is explicitly excluded: radial, exponential scaling, not a CO-bonus.
EXCLUDED_SOURCES = ["Catalyze (radial exponential bonus, not a CO-type bonus)"]

# Effects the additive CO math deliberately ignores (wiki Math section).
IGNORED_FINAL_MULTIPLIERS = [
    "Extinguished Key", "range damage falloff", "Longbow Sharpshot",
    "Primary Compression (on projectiles)", "Duality", "Furious Javelin",
    "Garuda passive", "Eclipse", "Hall of Mirrors", "Parasitic Link",
    "Overdriver", "Incarnon Genesis base-damage evolutions",
    "some stance multipliers", "bow charge multiplier (uncharged base is used)",
]


def unescape(s: str) -> str:
    return s.replace("\\'", "'").replace("\\\\", "\\")


def parse_ts_rules() -> list[dict]:
    text = TS_PATH.read_text(encoding="utf-8")
    block = text[text.index("const CO_RULES"):text.index("]\n", text.index("const CO_RULES")) + 1]
    section, source = "primary", "wiki"
    rules: list[dict] = []
    obj_parts: list[str] = []
    depth = 0
    for line in block.splitlines():
        marker = next((m for m in SECTION_MARKERS if m in line), None)
        if marker:
            section, source = SECTION_MARKERS[marker]
            continue
        if depth == 0 and "{" not in line:
            continue
        obj_parts.append(line.strip())
        depth += line.count("{") - line.count("}")
        if depth > 0:
            continue
        obj = " ".join(obj_parts)  # full rule object, may span several lines
        obj_parts, depth = [], 0
        weapons = [unescape(w) for w in
                   re.findall(r"'((?:[^'\\]|\\.)*)'",
                              re.search(r"weapons:\s*\[([^\]]*)\]", obj).group(1))]
        pattern = re.search(r"attack:\s*/(.*?)/,", obj).group(1)
        mode = re.search(r"mode:\s*'(\w+)'", obj).group(1)
        sm = re.search(r"scale:\s*([\d.]+)", obj)
        scale = float(sm.group(1)) if sm else 1.0
        nm = re.search(r"note:\s*('(?:[^'\\]|\\.)*'|BOW_CHARGED|DIRECT_ONLY)", obj)
        note = None
        if nm:
            raw = nm.group(1)
            note = CONST.get(raw, unescape(raw.strip("'")))
        rule_source = "gunco_sheet" if "sheet: true" in obj else "wiki"
        rules.append({
            "section": section,
            "weapons": weapons,
            "attack_name": None,
            "attack_pattern": pattern,
            "mode": mode,
            "scale": scale,
            "source": rule_source,
            "note": note,
        })
    return rules


def build_wiki_only_rules() -> list[dict]:
    out = []
    for section, weapons, attack_name, mode, scale, note in WIKI_ONLY_RULES:
        out.append({
            "section": section,
            "weapons": weapons,
            "attack_name": attack_name,
            "attack_pattern": f"^{re.escape(attack_name)}$",
            "mode": mode,
            "scale": scale,
            "source": "wiki",
            "note": note,
        })
    return out


def main() -> None:
    rules = parse_ts_rules()
    rules += build_wiki_only_rules()
    # every regex must compile on Python
    for rule in rules:
        re.compile(rule["attack_pattern"])
    # sanity: unique weapon+pattern+section keys
    keys = [(tuple(rule["weapons"]), rule["attack_pattern"], rule["section"]) for rule in rules]
    assert len(keys) == len(set(keys)), "duplicate rules detected"

    dataset = {
        "meta": META,
        "stacking_modes": STACKING_MODES,
        "co_sources": CO_SOURCES,
        "excluded_sources": EXCLUDED_SOURCES,
        "ignored_final_multipliers": IGNORED_FINAL_MULTIPLIERS,
        "rules": rules,
    }
    JSON_OUT.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["section", "weapon", "attack_name", "attack_pattern",
                         "mode", "scale", "source", "note"])
        for rule in rules:
            for weapon in rule["weapons"]:
                writer.writerow([
                    rule["section"], weapon, rule["attack_name"] or "",
                    rule["attack_pattern"], rule["mode"], rule["scale"],
                    rule["source"], rule["note"] or "",
                ])

    from collections import Counter
    print(f"rules: {len(rules)} ({dict(Counter(r['mode'] for r in rules))})")
    print(f"sections: {dict(Counter(r['section'] for r in rules))}")
    print(f"sources: {dict(Counter(r['source'] for r in rules))}")
    print(f"wrote {JSON_OUT.relative_to(ROOT)} and {CSV_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
