from __future__ import annotations

import re

from .models import ModEffect

TOKEN_PATTERN = re.compile(r'([+-]?\d+(?:\.\d+)?%|x\d+(?:\.\d+)?)', re.IGNORECASE)
TAG_PATTERN = re.compile(r'<[^>]+>')
WHITESPACE_PATTERN = re.compile(r'\s+')
CONDITIONAL_PATTERN = re.compile(r'\b(?:for|per|while|when|after|on)\b', re.IGNORECASE)

PHRASE_MAP = {
    "impact": "IMPACT",
    "puncture": "PUNC",
    "slash": "SLASH",
    "heat": "HEAT",
    "cold": "COLD",
    "electricity": "ELEC",
    "electric": "ELEC",
    "toxin": "TOXIN",
    "blast": "BLAST",
    "radiation": "RAD",
    "gas": "GAS",
    "magnetic": "MAG",
    "viral": "VIRAL",
    "corrosive": "CORR",
    "void": "VOID",
}

IGNORE_TERMS = {
    "status chance",
    "critical chance",
    "critical damage",
    "reload speed",
    "fire rate",
    "attack speed",
    "magazine capacity",
    "ammo maximum",
    "recoil",
    "zoom",
    "punch through",
    "combo count chance",
    "finisher damage",
    "slam attack",
    "heavy attack",
    "status duration",
    "projectile speed",
    "flight speed",
    "accuracy",
    "holster rate",
    "initial combo",
    "combo duration",
    "chance to gain",
    "ammo mutation",
    "maximum ammo",
    "beam length",
    "weapon recoil",
    "spread",
}


def parse_effects(stat_line: str) -> list[ModEffect]:
    cleaned_line = clean_stat_line(stat_line)
    matches = list(TOKEN_PATTERN.finditer(cleaned_line))
    effects: list[ModEffect] = []
    # Conditions may precede, follow, or span multiple numeric bonuses. The
    # desktop calculator has no activation state, so reject the whole line
    # instead of accidentally making one of its bonuses permanent.
    if CONDITIONAL_PATTERN.search(cleaned_line):
        return effects
    if matches and cleaned_line[:matches[0].start()].strip():
        return effects

    for index, match in enumerate(matches, start=1):
        raw_value = match.group(1).strip().lower()
        start = match.end()
        end = matches[index].start() if index < len(matches) else len(cleaned_line)
        label = cleaned_line[start:end].strip().lower()
        code = map_label_to_code(label)
        if not code:
            continue

        if raw_value.startswith('x'):
            value = float(raw_value[1:])
        else:
            value = float(raw_value.rstrip('%')) / 100.0

        text = f"{raw_value.upper() if raw_value.startswith('x') else raw_value} {label}".strip()
        effects.append(ModEffect(code=code, value=value, text=text, position=index))

    return effects


def source_effect_fragments(stat_line: str) -> list[str]:
    """Reconstruct old stored token text for migration coverage checks.

    This intentionally does not decide whether a token is supported damage.
    It lets migration distinguish a still-present but now rejected source
    phrase from a missing or changed source rank.
    """
    cleaned = clean_stat_line(stat_line)
    matches = list(TOKEN_PATTERN.finditer(cleaned))
    fragments = []
    for index, match in enumerate(matches):
        raw = match.group(1).strip().lower()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        label = cleaned[match.end():end].strip().lower()
        fragments.append(f"{raw.upper() if raw.startswith('x') else raw} {label}".strip())
    return fragments


def clean_stat_line(stat_line: str) -> str:
    cleaned = TAG_PATTERN.sub('', stat_line or '')
    cleaned = cleaned.replace('×', 'x')
    cleaned = WHITESPACE_PATTERN.sub(' ', cleaned).strip()
    return cleaned


def map_label_to_code(label: str) -> str | None:
    normalized = WHITESPACE_PATTERN.sub(' ', label.strip().lower())

    if any(term == normalized or term in normalized for term in IGNORE_TERMS):
        return None

    factions = {
        'damage to grineer': 'BANE_GRINEER',
        'damage to corpus': 'BANE_CORPUS',
        'damage to infested': 'BANE_INFESTED',
        'damage to corrupted': 'BANE_CORRUPTED',
        'damage to orokin': 'BANE_CORRUPTED',
        'damage to the murmur': 'BANE_MURMUR',
        'damage to murmur': 'BANE_MURMUR',
        'damage to sentient': 'BANE_SENTIENT',
        'damage to sentients': 'BANE_SENTIENT',
        'damage to scaldra': 'BANE_SCALDRA',
        'damage to techrot': 'BANE_TECHROT',
    }
    if normalized in factions:
        return factions[normalized]
    if normalized in {'damage', 'melee damage'}:
        return 'TRUE'

    # Recognize only an actual damage-type label, optionally followed by the
    # word "damage". A substring/prefix match misreads "Blast Range", "Void
    # Sling" and "of Damage converted into Impact" as direct damage bonuses.
    return PHRASE_MAP.get(normalized.removesuffix(' damage').strip())
