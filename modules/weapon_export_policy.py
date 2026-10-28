"""Guard name-keyed weapon imports against ambiguous official export rows.

The export contains both a player Grimoire and a differently statted
Doppelganger entry under the same name. The database is keyed by displayed
name, so blindly applying rows in source order can replace the player weapon.
This is an explicit ID-based exception, not a generic guess at player IDs.
"""
from __future__ import annotations

from collections import defaultdict

GRIMOIRE_NAME = "Grimoire"
GRIMOIRE_PLAYER_ID = "/Lotus/Weapons/Tenno/Grimoire/TnGrimoire"
GRIMOIRE_DOPPELGANGER_ID = "/Lotus/Weapons/Tenno/Grimoire/TnDoppelgangerGrimoire"


def order_export_weapons(rows: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    """Check collisions, then give the known player entry last-write priority.

    Keep the Doppelganger row in the payload: legacy-coverage checks and the
    guarded data migration need its original identifier and values. Unknown
    same-name rows with different modeled fields fail closed rather than
    silently selecting whichever happened to be exported last. Rows differing
    only in ID are retained; identity-dependent compatibility remains bounded.
    """
    by_name: dict[str, list[dict[str, float | str]]] = defaultdict(list)
    for row in rows:
        by_name[str(row["weapon"])].append(row)
    preferred: list[dict[str, float | str]] = []
    for name, group in by_name.items():
        if name == GRIMOIRE_NAME:
            preferred = [row for row in group if row["unique_name"] == GRIMOIRE_PLAYER_ID]
            has_doppelganger = any(row["unique_name"] == GRIMOIRE_DOPPELGANGER_ID for row in group)
            if has_doppelganger and not preferred:
                raise ValueError("Grimoire export contains the Doppelganger but no player entry.")
            if preferred:
                group = [row for row in group if row["unique_name"] != GRIMOIRE_DOPPELGANGER_ID]
        if len(group) > 1:
            first = {key: value for key, value in group[0].items() if key != "unique_name"}
            if any({key: value for key, value in row.items() if key != "unique_name"} != first
                   for row in group[1:]):
                raise ValueError(f"{name}: conflicting same-name weapon export entries; review their IDs.")
    if not preferred:
        return rows
    # Other entries retain their source order; the preferred entry wins even
    # if future exports reverse the order of the two Grimoire records.
    return [row for row in rows if not (
        row["weapon"] == GRIMOIRE_NAME and row["unique_name"] == GRIMOIRE_PLAYER_ID
    )] + preferred
