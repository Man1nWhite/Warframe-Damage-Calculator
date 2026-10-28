"""Generated Riven snapshots must match the Wiki-aware table builder."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_riven_tables
from modules.riven import DEFAULT_DISPOSITION, build_average_tables


SOURCE = Path(__file__).resolve().parents[1] / "source"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class RivenSnapshotTests(unittest.TestCase):
    def test_json_and_csv_match_the_generator(self) -> None:
        generated = build_average_tables(DEFAULT_DISPOSITION)
        with (SOURCE / "riven_stats_average_1_2.json").open(encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), generated)
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(build_riven_tables, "SOURCE_DIR", Path(temporary)):
                generated_csv = build_riven_tables.write_csv(generated, DEFAULT_DISPOSITION)
            self.assertEqual(read_csv(SOURCE / "riven_stats_average_1_2.csv"),
                             read_csv(generated_csv))

    def test_csv_represents_unrollable_traits_with_empty_cells(self) -> None:
        rows = read_csv(SOURCE / "riven_stats_average_1_2.csv")
        by_type_tag = {(r["riven_type"], r["tag"]): r for r in rows}
        rifle = "LotusRifleRandomModRare"
        melee = "PlayerMeleeWeaponRandomModRare"
        heat = by_type_tag[(rifle, "WeaponFireDamageMod")]
        punch = by_type_tag[(rifle, "WeaponPunctureDepthMod")]
        chance = by_type_tag[(melee, "WeaponMeleeComboPointsOnHitMod")]
        self.assertEqual((heat["curse_with_2_pos"], heat["curse_with_3_pos"]), ("", ""))
        self.assertEqual((punch["unit"], punch["buff_3_pos_1_neg"]), ("plain", "3.0"))
        self.assertEqual(punch["curse_with_3_pos"], "")
        self.assertEqual(chance["buff_3_pos_1_neg"], "")
        self.assertEqual(chance["curse_with_3_pos"], "-94.4")


if __name__ == "__main__":
    unittest.main()
