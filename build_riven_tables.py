"""Generate average-grade Riven stat tables at a fixed disposition.

Outputs (next to the vendored ``source/riven_tags.json``):

- ``source/riven_stats_average_<disp>.json`` - full structured table
- ``source/riven_stats_average_<disp>.csv``  - flat, spreadsheet-friendly table

Every Riven is evaluated at the same disposition (default 1.2), average random
roll (grade factor 1.0) and max rank (rank 8, x9 steps). Combined-stat layouts
cover 2 or 3 positive stats with and without a negative stat.

Usage::

    python build_riven_tables.py                 # disposition 1.2
    python build_riven_tables.py --disposition 1.0
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from modules.riven import (
    BUFF_LAYOUTS,
    CURSE_LAYOUTS,
    DEFAULT_DISPOSITION,
    RIVEN_TYPE_NAMES,
    build_average_tables,
)

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_DIR = PROJECT_ROOT / "source"


def write_json(tables: dict, disposition: float) -> Path:
    tag = f"{disposition:g}".replace(".", "_")
    path = SOURCE_DIR / f"riven_stats_average_{tag}.json"
    path.write_text(json.dumps(tables, indent=2), encoding="utf-8")
    return path


def write_csv(tables: dict, disposition: float) -> Path:
    tag = f"{disposition:g}".replace(".", "_")
    path = SOURCE_DIR / f"riven_stats_average_{tag}.csv"
    buff_columns = [f"buff_{key}" for key, _, _ in BUFF_LAYOUTS]
    curse_columns = [f"curse_{key}" for key, _, _ in CURSE_LAYOUTS]
    fieldnames = (
        ["riven_type", "riven_name", "tag", "stat_name", "unit", "wdc_code"]
        + buff_columns
        + curse_columns
    )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for riven_type, payload in tables["riven_types"].items():
            for stat in payload["stats"]:
                row = {
                    "riven_type": riven_type,
                    "riven_name": RIVEN_TYPE_NAMES.get(riven_type, riven_type),
                    "tag": stat["tag"],
                    "stat_name": stat["name"],
                    "unit": stat["unit"],
                    "wdc_code": stat["wdc_code"] or "",
                }
                for key, _, _ in BUFF_LAYOUTS:
                    value = stat["buffs"][key]
                    row[f"buff_{key}"] = value["display"] if value is not None else ""
                for key, _, _ in CURSE_LAYOUTS:
                    value = stat["curses"][key]
                    row[f"curse_{key}"] = value["display"] if value is not None else ""
                writer.writerow(row)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build average-grade Riven stat tables.")
    parser.add_argument(
        "--disposition",
        type=float,
        default=DEFAULT_DISPOSITION,
        help="Riven disposition applied to every table (default: 1.2).",
    )
    args = parser.parse_args()

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    tables = build_average_tables(disposition=args.disposition)
    json_path = write_json(tables, args.disposition)
    csv_path = write_csv(tables, args.disposition)

    stat_count = sum(len(payload["stats"]) for payload in tables["riven_types"].values())
    print(f"Wrote {json_path.relative_to(PROJECT_ROOT)} ({len(tables['riven_types'])} Riven types, {stat_count} stats)")
    print(f"Wrote {csv_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
