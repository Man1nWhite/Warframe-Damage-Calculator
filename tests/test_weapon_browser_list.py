"""The GUI weapon sidebar must browse the whole catalogue.

``SEARCH_LIMIT`` bounds a typed search, but the sidebar also lists every
weapon when the search box is empty. Applying the cap there sorted first and
truncated after, so everything past the first 250 names (Kuva/Tenet weapons,
most Primes, Ocucor, Zymos, ...) was absent from the list and only reachable by
typing its name.
"""
from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from modules.constants import SEARCH_LIMIT
from modules.database import WeaponRepository

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "weapons.db"
# Sorts after the default cap in the bundled database; see the test below.
BEYOND_THE_CAP = "Zymos"


class WeaponBrowserListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = WeaponRepository(DATABASE)
        with closing(sqlite3.connect(DATABASE)) as connection:
            self.total = connection.execute("SELECT COUNT(*) FROM weapons").fetchone()[0]

    def test_browsing_without_a_limit_lists_every_weapon(self) -> None:
        names = self.repository.search_weapons("", limit=None)
        self.assertEqual(len(names), self.total)
        self.assertEqual(len(set(names)), self.total)

    def test_the_default_cap_would_hide_part_of_the_catalogue(self) -> None:
        # Guards the fixture as much as the code: if the bundled database ever
        # shrinks below the cap this test no longer proves anything.
        self.assertGreater(self.total, SEARCH_LIMIT)
        capped = self.repository.search_weapons("")
        self.assertEqual(len(capped), SEARCH_LIMIT)
        self.assertNotIn(BEYOND_THE_CAP, capped)
        self.assertIn(BEYOND_THE_CAP, self.repository.search_weapons("", limit=None))

    def test_a_query_still_filters_when_no_limit_is_given(self) -> None:
        names = self.repository.search_weapons("Nukor", limit=None)
        self.assertIn("Kuva Nukor", names)
        self.assertTrue(names)
        self.assertTrue(all("nukor" in name.casefold() for name in names), names)

    def test_an_explicit_limit_is_still_honoured(self) -> None:
        self.assertEqual(len(self.repository.search_weapons("", limit=10)), 10)


if __name__ == "__main__":
    unittest.main()
