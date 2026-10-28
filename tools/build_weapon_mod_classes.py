"""Derive the small, offline primary-mod-family snapshot from pinned WFCD data.

Reproduction (requires gh; no network is needed by the app):
    gh api -H 'Accept: application/vnd.github.raw+json' \
      'repos/WFCD/warframe-items/contents/data/json/Primary.json?ref=01554db43218aebdf948006fe4b9b0b8042762d1' > /tmp/Primary.json
    python tools/build_weapon_mod_classes.py /tmp/Primary.json

The output contains identifiers and broad classes only. It is not a full mod
legality database. The Coda Bubonico override is sourced from the Wiki's
explicit "uses Shotgun Mods" note rather than WFCD's Rifle label.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

COMMIT = "01554db43218aebdf948006fe4b9b0b8042762d1"
SOURCE_SHA256 = "d531e96c474fecabe3f146dd0bb1e76367b2b5b1554152a4ad559646f358b1f7"
CODA_BUBONICO = "/Lotus/Weapons/Infested/InfestedLich/LongGuns/CodaBubonico/CodaBubonicoCannon"
VALID_CLASSES = {"Rifle", "Shotgun", "Bow", "Sniper", "Launcher"}
ROOT = Path(__file__).resolve().parents[1]


def build_snapshot(rows: list[dict]) -> dict:
    classes: dict[str, str] = {}
    for row in rows:
        unique = str(row.get("uniqueName") or "")
        category = str(row.get("type") or "")
        # The WFCD primary list also includes the pistol Sirocco.
        if category == "Pistol":
            continue
        if not unique.startswith("/Lotus/") or category not in VALID_CLASSES:
            raise ValueError(f"Unexpected primary entry: {unique!r}, {category!r}")
        if unique in classes:
            raise ValueError(f"Duplicate primary identifier: {unique}")
        classes[unique] = category
    if CODA_BUBONICO not in classes:
        raise ValueError("The pinned primary snapshot is missing Coda Bubonico")
    classes[CODA_BUBONICO] = "Shotgun"
    return {
        "schema": 1,
        "source": f"https://github.com/WFCD/warframe-items/blob/{COMMIT}/data/json/Primary.json",
        "source_sha256": SOURCE_SHA256,
        "license": "WFCD_LICENSE.txt",
        "overrides": {CODA_BUBONICO: "https://wiki.warframe.com/w/Coda_Bubonico"},
        "classes": dict(sorted(classes.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Pinned WFCD Primary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "source" / "weapon_mod_classes.json")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"Unexpected source SHA-256: {digest}; expected {SOURCE_SHA256}")
    snapshot = build_snapshot(json.loads(raw))
    args.output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
