"""Real Qt widget/SQLite integration tests; no display or network required."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox, QTableWidget
except (ImportError, OSError) as exc:
    # CI sets this so a missing Qt installation cannot silently skip the suite.
    if os.environ.get("WDC_REQUIRE_GUI_TESTS") == "1":
        raise
    raise unittest.SkipTest(
        f"Qt integration tests need PyQt6 and native Qt libraries: {exc}") from exc

import main as startup
from gui.app import CompareBuildDialog, DamageCalculatorWindow, SettingsDialog
from modules.app_paths import ensure_app_dirs, seed_source_files
from modules.database import ModRepository, WeaponRepository
from modules.database_revision import CURRENT_DATABASE_REVISION

ROOT = Path(__file__).resolve().parents[1]


class GuiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {"APPDATA": self.temp.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.paths = ensure_app_dirs()
        shutil.copy2(ROOT / "data" / "weapons.db", self.paths["db"])
        self.information = patch.object(QMessageBox, "information").start()
        self.warning = patch.object(QMessageBox, "warning").start()
        self.critical = patch.object(QMessageBox, "critical").start()
        self.addCleanup(patch.stopall)
        self.window = DamageCalculatorWindow(WeaponRepository(self.paths["db"]),
                                             ModRepository(self.paths["db"]), ROOT)
        self.window.show()
        self.app.processEvents()

    def wait_for_pipeline(self, timeout=20):
        deadline = time.monotonic() + timeout
        while self.window.data_pipeline_running and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertFalse(self.window.data_pipeline_running, "the data pipeline did not finish in time")

    def tearDown(self):
        if self.window.data_pipeline_running:
            self.wait_for_pipeline()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.assertFalse(self.critical.called, f"Unexpected GUI error: {self.critical.call_args}")

    def test_data_pipeline_runs_off_gui_thread_and_delivers_results_on_gui_thread(self):
        gui_thread = threading.get_ident()
        worker_threads = []
        online_options = []
        progress_threads = []
        completion_threads = []
        outputs = {
            "db_path": self.paths["db"], "source_mode": "saved local exports",
            "lzma_method": "Not applicable", "backup_path": None, "refresh_error": None,
        }

        def run_pipeline(prefer_online, log_callback):
            worker_threads.append(threading.get_ident())
            online_options.append(prefer_online)
            log_callback("worker progress")
            return outputs

        with patch.object(self.window, "run_data_pipeline", side_effect=run_pipeline), \
             patch.object(self.window, "refresh_after_data_pipeline"):
            started = self.window.start_data_pipeline(
                prefer_online=False,
                on_progress=lambda _message: progress_threads.append(threading.get_ident()),
                on_succeeded=lambda _result: completion_threads.append(threading.get_ident()),
            )
            self.assertTrue(started)
            self.wait_for_pipeline()

        self.assertEqual(len(worker_threads), 1)
        self.assertNotEqual(worker_threads[0], gui_thread)
        self.assertEqual(online_options, [False])
        self.assertEqual(progress_threads, [gui_thread])
        self.assertEqual(completion_threads, [gui_thread])

    def select_weapon(self, name: str):
        self.window.search_edit.setText(name)
        items = self.window.weapon_list.findItems(name, Qt.MatchFlag.MatchExactly)
        self.assertEqual(len(items), 1)
        self.window.weapon_list.setCurrentItem(items[0])
        self.assertEqual(self.window.selected_weapon.weapon, name)

    def equip(self, slot_number: int, name: str, rank: int = 5):
        slot = self.window.mod_slots[slot_number]
        mod = next(m for m in self.window.available_mods
                   if m.name == name and m.fusion_limit == 5)
        index = slot.mod_combo.findData(mod.unique_name)
        self.assertGreaterEqual(index, 0, f"{name} not available in slot")
        slot.mod_combo.setCurrentIndex(index)
        slot.rank_spin.setValue(rank)
        self.assertEqual(slot.current_mod.unique_name, mod.unique_name)

    @staticmethod
    def table_values(table):
        return {table.item(i, 0).text(): float(table.item(i, 1).text())
                for i in range(table.rowCount())}

    def test_first_run_with_uninitialised_database_still_opens_an_empty_catalog(self):
        empty_db = self.paths["db"].parent / "uninitialised.db"
        window = DamageCalculatorWindow(WeaponRepository(empty_db), ModRepository(empty_db), ROOT)
        try:
            self.assertEqual(window.weapon_list.count(), 0)
            self.assertIsNone(window.selected_weapon)
            self.assertIsNone(window.current_results)
            self.assertFalse(self.critical.called)
        finally:
            window.close()
            window.deleteLater()

    def test_weapon_sidebar_lists_the_whole_catalogue(self):
        # The sidebar is a browser, not a capped search result: every row of
        # the database must be reachable without typing a name.
        with closing(sqlite3.connect(self.paths["db"])) as connection:
            total = connection.execute("SELECT COUNT(*) FROM weapons").fetchone()[0]
        self.assertEqual(self.window.weapon_list.count(), total)
        self.assertGreater(total, 250)
        self.window.search_edit.setText("Zymos")
        self.app.processEvents()
        self.assertEqual(len(self.window.weapon_list.findItems(
            "Zymos", Qt.MatchFlag.MatchExactly)), 1)

    def test_weapon_filter_does_not_switch_or_clear_an_unsaved_build(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        before = self.window.current_results
        with patch.object(self.window, "recalculate", wraps=self.window.recalculate) as recalculate:
            # A real search passes through multiple intermediate queries. The
            # selected weapon can disappear and later reappear without a click.
            for query in ("Z", "Zy", "Zymos", "no such weapon", ""):
                self.window.search_edit.setText(query)
                self.assertEqual(self.window.selected_weapon.weapon, "Braton")
                self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
                self.assertEqual(self.window.mod_slots[0].rank_spin.value(), 5)
            recalculate.assert_not_called()
        self.assertIs(self.window.current_results, before)
        self.assertEqual(self.window.weapon_list.currentItem().text(), "Braton")

        # Selecting another match intentionally still switches weapons and
        # clears mods which are not compatible with the new weapon.
        self.window.search_edit.setText("Zymos")
        self.window.weapon_list.setCurrentItem(self.window.weapon_list.item(0))
        self.assertEqual(self.window.selected_weapon.weapon, "Zymos")
        self.assertIsNone(self.window.mod_slots[0].current_mod)

    def test_unmodeled_base_damage_warning_follows_the_selected_weapon(self):
        self.select_weapon("Shadow Clones")
        self.assertTrue(self.window.current_results.warnings)
        self.assertFalse(self.window.damage_warning.isHidden())
        self.assertIn("750", self.window.damage_warning.text())
        self.assertIn("incomplete", self.window.damage_warning.text().lower())
        self.select_weapon("Braton")
        self.assertEqual(self.window.current_results.warnings, [])
        self.assertTrue(self.window.damage_warning.isHidden())

    def test_damage_scope_is_visible_for_combined_export_rows(self):
        self.select_weapon("Grimoire")
        self.assertIn("separate direct and radial hits", self.window.damage_scope_notice.text())
        self.assertAlmostEqual(self.window.current_results.hud_total, 150)
        self.assertAlmostEqual(self.window.current_results.hud_damage_by_type["ELEC"], 150)

    def test_wiki_element_order_reaches_result_widgets(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        self.equip(1, "Infected Clip")
        self.equip(2, "Hellfire")
        result = self.window.current_results
        # Wiki elemental ordering: Cold+Toxin, then Heat+innate Electricity.
        self.assertAlmostEqual(result.hud_damage_by_type["VIRAL"], 135)
        self.assertAlmostEqual(result.hud_damage_by_type["RAD"], 142.5)
        self.assertAlmostEqual(float(self.window.cards["hud_total"].value_label.text()), 277.5)
        values = self.table_values(self.window.hud_table)
        self.assertAlmostEqual(values["Viral"], 135)
        self.assertAlmostEqual(values["Radiation"], 142.5)

        self.equip(0, "Hellfire")
        self.equip(2, "Cryo Rounds")
        result = self.window.current_results
        self.assertAlmostEqual(result.hud_damage_by_type["GAS"], 135)
        self.assertAlmostEqual(result.hud_damage_by_type["MAG"], 142.5)
        self.assertEqual(result.hud_damage_by_type["VIRAL"], 0)

    def test_equipped_effects_batch_keeps_duplicate_slots_and_distinct_ranks(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds", 5)
        self.equip(1, "Cryo Rounds", 5)
        self.equip(2, "Cryo Rounds", 4)
        repository = self.window.mod_repository
        with patch.object(repository, "connect", wraps=repository.connect) as connect:
            equipped = self.window._build_equipped_mods()
        self.assertEqual(connect.call_count, 1)
        self.assertEqual([slot.rank for slot in equipped[:3]], [5, 5, 4])
        self.assertEqual(equipped[0].effects, equipped[1].effects)
        self.assertNotEqual(equipped[0].effects, equipped[2].effects)
        self.assertEqual(equipped[0].effects, repository.fetch_ranked_effects(
            equipped[0].mod.unique_name, 5))
        self.assertEqual(len(equipped), len(self.window.mod_slots))

    def test_database_error_does_not_show_a_result_without_equipped_mods(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        def short_connect():
            connection = sqlite3.connect(self.paths["db"], timeout=0.01)
            connection.row_factory = sqlite3.Row
            return connection

        with closing(sqlite3.connect(self.paths["db"])) as locker, \
             patch.object(self.window.mod_repository, "connect", side_effect=short_connect):
            locker.execute("BEGIN EXCLUSIVE")
            self.window.recalculate()
            locker.rollback()
        self.assertIsNone(self.window.current_results)
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertEqual(self.window.cards["hud_total"].value_label.text(), "—")
        self.assertIn("unavailable", self.window.damage_warning.text().lower())
        self.assertTrue(self.critical.called)
        self.critical.reset_mock()
        # Recalculation succeeds after the transient database error ends.
        self.window.recalculate()
        self.assertIsNotNone(self.window.current_results)
        self.assertFalse(self.window.damage_warning.isVisible())

    def test_failed_mod_catalog_read_does_not_switch_weapon_or_clear_slots(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        before = self.window.current_results
        self.window.search_edit.clear()
        other = self.window.weapon_list.findItems("Zymos", Qt.MatchFlag.MatchExactly)[0]
        with patch.object(self.window.mod_repository, "connect",
                          side_effect=sqlite3.OperationalError("database is locked")):
            self.window.weapon_list.setCurrentItem(other)
        self.assertEqual(self.window.selected_weapon.weapon, "Braton")
        self.assertEqual(self.window.weapon_list.currentItem().text(), "Braton")
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertIs(self.window.current_results, before)
        self.assertTrue(self.warning.called)

    def test_weapon_switch_calculates_only_after_all_mod_options_are_applied(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        self.equip(1, "Infected Clip")
        excluded = self.window.mod_slots[1].current_mod.unique_name
        options = [mod for mod in self.window.available_mods if mod.unique_name != excluded]
        self.window.search_edit.clear()
        other = self.window.weapon_list.findItems("Alternox Prime", Qt.MatchFlag.MatchExactly)[0]
        with patch.object(self.window, "_compatible_mod_options", return_value=options), \
             patch.object(self.window.mod_repository, "fetch_ranked_effects_many",
                          side_effect=sqlite3.OperationalError("database is locked")) as effects:
            self.window.weapon_list.setCurrentItem(other)
        effects.assert_called_once()
        self.assertEqual(self.critical.call_count, 1)
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertIsNone(self.window.mod_slots[1].current_mod)
        self.assertIsNone(self.window.current_results)
        self.critical.reset_mock()

    def test_catalog_search_error_preserves_the_visible_list_and_selection(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        before = self.window.weapon_list.count()
        with patch.object(self.window.weapon_repository, "connect",
                          side_effect=sqlite3.OperationalError("database is locked")):
            self.window.refresh_weapon_list()
        self.assertEqual(self.window.weapon_list.count(), before)
        self.assertEqual(self.window.weapon_list.currentItem().text(), "Braton")
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertIn("unavailable", self.window.statusBar().currentMessage().lower())

    def test_failed_post_rebuild_refresh_invalidates_and_then_reloads_results(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        old_rate = self.window.selected_weapon.firerate
        with closing(sqlite3.connect(self.paths["db"])) as connection:
            connection.execute("UPDATE weapons SET firerate = firerate + 1 WHERE weapon = 'Braton'")
            connection.commit()
        outputs = {"db_path": self.paths["db"], "source_mode": "local", "lzma_method": "N/A",
                   "backup_path": None, "refresh_error": None}
        with patch.object(self.window.mod_repository, "list_mods_for_slot",
                          side_effect=sqlite3.OperationalError("database is locked")):
            self.window._on_data_pipeline_completed(outputs, None)
        self.assertIsNone(self.window.current_results)
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertTrue(self.window._needs_catalog_refresh)
        self.assertIn("unavailable", self.window.damage_warning.text().lower())
        self.window.recalculate()
        self.assertAlmostEqual(self.window.selected_weapon.firerate, old_rate + 1)
        self.assertFalse(self.window._needs_catalog_refresh)
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertIsNotNone(self.window.current_results)

    def test_failed_post_rebuild_weapon_search_is_not_reported_as_success(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        outputs = {"db_path": self.paths["db"], "source_mode": "local", "lzma_method": "N/A",
                   "backup_path": None, "refresh_error": None}
        with patch.object(self.window.weapon_repository, "search_weapons",
                          side_effect=sqlite3.OperationalError("database is locked")):
            self.window._on_data_pipeline_completed(outputs, None)
        self.assertIsNone(self.window.current_results)
        self.assertTrue(self.window._needs_catalog_refresh)
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertIn("could not refresh", self.window.statusBar().currentMessage().lower())
        self.window.recalculate()
        self.assertFalse(self.window._needs_catalog_refresh)
        self.assertIsNotNone(self.window.current_results)

    def test_weapon_specific_and_primary_family_options_use_the_real_widgets(self):
        self.select_weapon("Braton")
        names = {m.name for m in self.window.available_mods}
        self.assertIn("Serration", names)
        self.assertNotIn("Point Blank", names)
        self.assertNotIn("Higasa Serration", names)
        self.assertNotIn("Firestorm", names)
        self.select_weapon("Hek")
        names = {m.name for m in self.window.available_mods}
        self.assertIn("Point Blank", names)
        self.assertNotIn("Serration", names)
        self.select_weapon("Coda Bubonico")
        names = {m.name for m in self.window.available_mods}
        self.assertIn("Point Blank", names)  # WFCD's Rifle label is overridden by the Wiki.
        self.assertNotIn("Serration", names)
        self.select_weapon("Higasa")
        self.assertIn("Higasa Serration", {m.name for m in self.window.available_mods})
        self.select_weapon("Ocucor")
        self.assertNotIn("Damzav-Vati", {m.name for m in self.window.available_mods})
        self.select_weapon("Akbronco Prime")
        self.assertIn("Damzav-Vati", {m.name for m in self.window.available_mods})
        self.assertIn("Compatibility is partial", self.window.compatibility_notice.text())

    def test_primed_pressure_point_changes_jat_direct_damage_and_bad_mods_are_hidden(self):
        self.select_weapon("Jat Kittag")
        names = {m.name for m in self.window.available_mods}
        self.assertIn("Primed Pressure Point", names)
        self.assertNotIn("Amar's Contempt", names)
        self.assertNotIn("Brute Conditioning", names)
        self.assertNotIn("Cutting Edge", names)
        baseline = self.window.current_results.hud_total
        slot = self.window.mod_slots[0]
        index = slot.mod_combo.findData("/Lotus/Upgrades/Mods/Melee/Expert/WeaponMeleeDamageModExpert")
        self.assertGreaterEqual(index, 0)
        slot.mod_combo.setCurrentIndex(index)
        slot.rank_spin.setValue(10)
        self.assertAlmostEqual(self.window.current_results.hud_total, baseline * 2.65)
        self.select_weapon("Fang Prime")
        self.assertIn("Amar's Contempt", {m.name for m in self.window.available_mods})

    def test_custom_mod_is_not_collapsed_into_an_identical_official_mod(self):
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            row = connection.execute("SELECT effect_summary FROM mods WHERE unique_name=?",
                ("/Lotus/Upgrades/Mods/Rifle/WeaponDamageAmountMod",)).fetchone()
            connection.execute("INSERT INTO mods(unique_name,name,slot_group,supported,fusion_limit,effect_summary) "
                               "VALUES('/custom/serration','Serration','PRIMARY',1,10,?)", (row[0],))
            connection.execute("INSERT INTO mod_effects VALUES('/custom/serration',10,1,'TRUE',.5,'custom')")
        self.select_weapon("Braton")
        ids = {m.unique_name for m in self.window.available_mods}
        self.assertIn("/custom/serration", ids)
        self.assertIn("/Lotus/Upgrades/Mods/Rifle/WeaponDamageAmountMod", ids)
        self.assertEqual(self.window.mod_repository.fetch_ranked_effects('/custom/serration', 10)[0].value, .5)
        slot = self.window.mod_slots[0]
        slot.mod_combo.setCurrentIndex(slot.mod_combo.findData("/custom/serration"))
        slot.rank_spin.setValue(10)
        path = self.paths["builds"] / "custom-mod.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "JSON")):
            self.window.save_build()
        slot.clear_selection()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
            self.window.load_build()
        self.assertEqual(slot.current_mod.unique_name, "/custom/serration")
        self.assertEqual(slot.rank_spin.value(), 10)

    def test_filtering_does_not_unequip_other_mods(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        self.equip(1, "Infected Clip")
        before = self.window.current_results.hud_total
        self.window.mod_search_edit.setText("Hellfire")
        self.assertEqual([s.current_mod.name if s.current_mod else None
                          for s in self.window.mod_slots[:2]], ["Cryo Rounds", "Infected Clip"])
        self.assertAlmostEqual(self.window.current_results.hud_total, before)
        self.window.mod_search_edit.clear()
        self.window.mod_category_combo.setCurrentText("Faction")
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertEqual(self.window.mod_slots[1].rank_spin.value(), 5)

    def test_mod_categories_include_all_factions_without_mislabeling_elements(self):
        self.select_weapon("Braton")
        self.window.mod_category_combo.setCurrentText("Faction")
        faction = {mod.name for mod in self.window.mod_slots[0].current_options}
        self.assertIn("Primed Bane of Orokin", faction)
        self.assertIn("Primed Bane of The Murmur", faction)
        self.assertIn("Bane of Grineer", faction)
        self.assertNotIn("Hellfire", faction)
        self.assertNotIn("Serration", faction)

        self.window.mod_category_combo.setCurrentText("Base Damage")
        base = {mod.name for mod in self.window.mod_slots[0].current_options}
        self.assertIn("Serration", base)
        self.assertNotIn("Hellfire", base)
        self.assertNotIn("Primed Bane of Orokin", base)
        self.assertNotIn("Primed Bane of The Murmur", base)

        self.window.mod_category_combo.setCurrentText("Elemental")
        elemental = {mod.name for mod in self.window.mod_slots[0].current_options}
        self.assertIn("Hellfire", elemental)
        self.assertNotIn("Serration", elemental)

        # A mod with multiple effects belongs to each applicable category.
        mixed = replace(self.window.available_mods[0], description="",
                        effect_summary="+20% Damage, +40% Heat, X1.3 Damage to Murmur")
        for category in ("Base Damage", "Elemental", "Faction"):
            self.assertTrue(self.window._mod_matches_category(mixed, category))
        self.assertFalse(self.window._mod_matches_category(mixed, "Other"))

    def test_filtering_reuses_current_results_without_recalculating_each_slot(self):
        self.select_weapon("Alternox Prime")
        for i in range(8):
            self.equip(i, "Cryo Rounds")
        before = self.window.current_results
        with patch.object(self.window, "recalculate", wraps=self.window.recalculate) as recalculate:
            self.window.mod_search_edit.setText("Hellfire")
            self.window.mod_search_edit.clear()
            self.window.mod_category_combo.setCurrentText("Faction")
            self.window.apply_mod_filters()  # repeated refresh of identical options
        recalculate.assert_not_called()
        self.assertIs(self.window.current_results, before)
        for slot in self.window.mod_slots:
            self.assertEqual(slot.current_mod.name, "Cryo Rounds")
            self.assertEqual(slot.rank_spin.value(), 5)

    def test_weapon_with_no_compatible_mods_clears_old_slots(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        self.equip(1, "Infected Clip")
        before = self.window.current_results.hud_total
        with patch.object(self.window.mod_repository, "list_mods_for_slot", return_value=[]), \
             patch.object(self.window, "recalculate", wraps=self.window.recalculate) as recalculate:
            self.window._load_mod_options_for_weapon(self.window.selected_weapon)
        self.assertIsNone(self.window.mod_slots[0].current_mod)
        self.assertIsNone(self.window.mod_slots[1].current_mod)
        self.assertEqual(self.window.mod_slots[0].mod_combo.count(), 1)
        self.assertEqual(recalculate.call_count, 1)
        self.assertNotEqual(self.window.current_results.hud_total, before)
        self.assertAlmostEqual(self.window.current_results.hud_total, 75)

    def test_clear_all_mods_recalculates_once_after_all_slots_are_empty(self):
        self.select_weapon("Alternox Prime")
        for i in range(8):
            self.equip(i, "Cryo Rounds")
        with patch.object(self.window, "recalculate", wraps=self.window.recalculate) as recalculate:
            self.window.clear_all_mods()
        self.assertEqual(recalculate.call_count, 1)
        self.assertTrue(all(slot.current_mod is None and slot.rank_spin.value() == 0
                            for slot in self.window.mod_slots))
        self.assertAlmostEqual(self.window.current_results.hud_total, 75)

    def test_option_refresh_clamps_rank_and_recalculates_once(self):
        from dataclasses import replace

        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        old = self.window.current_results.hud_total
        current = self.window.mod_slots[0].current_mod
        self.window.available_mods = [replace(current, fusion_limit=2)]
        with patch.object(self.window, "recalculate", wraps=self.window.recalculate) as recalculate:
            self.window.apply_mod_filters()
        self.assertEqual(self.window.mod_slots[0].rank_spin.value(), 2)
        self.assertEqual(recalculate.call_count, 1)
        self.assertNotEqual(self.window.current_results.hud_total, old)
        self.assertAlmostEqual(self.window.current_results.hud_total, 75 * 1.45)

    def test_save_load_and_compare_a_real_build(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds", 4)
        self.equip(1, "Infected Clip")
        self.window.faction_combo.setCurrentText("Infested")
        self.window.armor_edit.setText("100")
        expected = self.window.current_results.final_total
        build = self.paths["builds"] / "my-build.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(build), "JSON")):
            self.window.save_build_button.click()
        payload = json.loads(build.read_text(encoding="utf-8"))
        self.assertEqual(payload["weapon"], "Alternox Prime")
        self.assertEqual(payload["mods"][0]["rank"], 4)

        self.window.clear_mods_button.click()
        self.window.faction_combo.setCurrentText("Grineer")
        self.window.mod_search_edit.setText("Hellfire")  # load must not hide saved mods
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(build), "JSON")):
            self.window.load_build_button.click()
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertEqual(self.window.mod_slots[0].rank_spin.value(), 4)
        self.assertEqual(self.window.mod_slots[1].current_mod.name, "Infected Clip")
        self.assertEqual(self.window.faction_combo.currentText(), "Infested")
        self.assertAlmostEqual(self.window.current_results.final_total, expected)

        compared = {}
        class InspectingCompareDialog(CompareBuildDialog):
            def exec(self):
                table = self.findChild(QTableWidget)
                for row in range(table.rowCount()):
                    compared[table.item(row, 0).text()] = (table.item(row, 1).text(),
                                                            table.item(row, 2).text())
                return 0
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(build), "JSON")), \
             patch("gui.app.CompareBuildDialog", InspectingCompareDialog):
            self.window.compare_build_button.click()
        self.assertEqual(compared["Weapon"], ("Alternox Prime", "Alternox Prime"))
        self.assertEqual(compared["Final Total"][0], compared["Final Total"][1])

    def test_build_actions_handle_catalog_and_effect_read_failures_without_mutation(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        slot = self.window.mod_slots[0]
        original = self.window.current_results
        path = self.paths["builds"] / "saved.json"
        path.write_text(json.dumps({"weapon": "Braton", "mods": [
            {"unique_name": slot.current_mod.unique_name, "rank": slot.rank_spin.value()},
        ]}), encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
             patch.object(self.window.mod_repository, "list_mods_for_slot",
                          side_effect=sqlite3.OperationalError("database is locked")):
            self.window.load_build()
            self.window.compare_build()
        self.assertEqual(self.window.selected_weapon.weapon, "Braton")
        self.assertEqual(slot.current_mod.name, "Cryo Rounds")
        self.assertIs(self.window.current_results, original)
        self.assertGreaterEqual(self.warning.call_count, 2)

        self.warning.reset_mock()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
             patch.object(self.window.mod_repository, "fetch_ranked_effects_many",
                          side_effect=sqlite3.OperationalError("database is locked")), \
             patch("gui.app.CompareBuildDialog") as dialog:
            self.window.compare_build()
        dialog.assert_not_called()
        self.assertIn("locked", str(self.warning.call_args).lower())
        self.assertIs(self.window.current_results, original)

    def test_load_build_preflights_effects_once_and_preserves_build_on_read_failure(self):
        self.select_weapon("Braton")
        self.equip(3, "Hellfire")
        original = self.window.current_results
        cold = next(mod for mod in self.window.available_mods
                    if mod.name == "Cryo Rounds" and mod.fusion_limit == 5)
        toxin = next(mod for mod in self.window.available_mods
                     if mod.name == "Infected Clip" and mod.fusion_limit == 5)
        path = self.paths["builds"] / "two-mods.json"
        path.write_text(json.dumps({"weapon": "Braton", "inputs": {"faction": "Corpus", "armor": "100"},
                                    "mods": [{"unique_name": cold.unique_name, "rank": 5},
                                             {"unique_name": toxin.unique_name, "rank": 4}]}),
                        encoding="utf-8")
        self.information.reset_mock()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
             patch.object(self.window.mod_repository, "fetch_ranked_effects_many",
                          side_effect=sqlite3.OperationalError("database is locked")) as effects:
            self.window.load_build()
        effects.assert_called_once()
        self.assertIsNone(self.window.mod_slots[0].current_mod)
        self.assertIsNone(self.window.mod_slots[1].current_mod)
        self.assertEqual(self.window.mod_slots[3].current_mod.name, "Hellfire")
        self.assertIs(self.window.current_results, original)
        self.assertIn("locked", str(self.warning.call_args).lower())
        self.assertFalse(self.critical.called)
        self.information.assert_not_called()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
             patch.object(self.window.mod_repository, "fetch_ranked_effects_many",
                          wraps=self.window.mod_repository.fetch_ranked_effects_many) as effects:
            self.window.load_build()
        effects.assert_called_once()
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertEqual(self.window.mod_slots[1].current_mod.name, "Infected Clip")
        self.assertEqual(self.window.mod_slots[1].rank_spin.value(), 4)
        self.assertIsNone(self.window.mod_slots[3].current_mod)
        self.assertIsNotNone(self.window.current_results)

    def test_comparison_shows_incomplete_damage_warnings_for_both_builds(self):
        path = self.paths["builds"] / "comparison.json"
        compared = {}

        class InspectingCompareDialog(CompareBuildDialog):
            def exec(self):
                table = self.findChild(QTableWidget)
                for row in range(table.rowCount()):
                    compared[table.item(row, 0).text()] = (table.item(row, 1).text(),
                                                            table.item(row, 2).text())
                return 0

        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
             patch("gui.app.CompareBuildDialog", InspectingCompareDialog):
            self.select_weapon("Braton")
            path.write_text(json.dumps({"weapon": "Shadow Clones", "mods": []}), encoding="utf-8")
            self.window.compare_build()
            self.assertEqual(compared["Warnings"][0], "None")
            self.assertIn("750", compared["Warnings"][1])
            self.assertIn("incomplete", compared["Warnings"][1].lower())

            self.select_weapon("Shadow Clones")
            path.write_text(json.dumps({"weapon": "Braton", "mods": []}), encoding="utf-8")
            self.window.compare_build()
            self.assertIn("750", compared["Warnings"][0])
            self.assertEqual(compared["Warnings"][1], "None")

    def test_load_rejects_unknown_weapon_without_changing_current_build(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        before = self.window.current_results.hud_total
        path = self.paths["builds"] / "unknown.json"
        path.write_text(json.dumps({"weapon": "No Such Weapon", "inputs": {"faction": "Infested"}, "mods": []}), encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
            self.window.load_build()
        self.assertTrue(self.warning.called)
        self.assertEqual(self.window.selected_weapon.weapon, "Alternox Prime")
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertAlmostEqual(self.window.current_results.hud_total, before)

    def test_short_saved_build_clears_slots_not_present_in_file(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        self.equip(1, "Infected Clip")
        selected = self.window.mod_slots[0].current_mod.unique_name
        path = self.paths["builds"] / "short.json"
        path.write_text(json.dumps({"weapon": "Alternox Prime", "mods": [{"unique_name": selected, "rank": 5}]}), encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
            self.window.load_build()
        self.assertEqual(self.window.mod_slots[0].current_mod.unique_name, selected)
        self.assertIsNone(self.window.mod_slots[1].current_mod)

    def test_load_rejects_unavailable_mod_without_leaving_a_misleading_build(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        before = self.window.current_results.hud_total
        path = self.paths["builds"] / "missing-mod.json"
        path.write_text(json.dumps({"weapon": "Alternox Prime", "mods": [{"unique_name": "/missing/mod", "rank": 5}]}), encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
            self.window.load_build()
        self.assertTrue(self.warning.called)
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertAlmostEqual(self.window.current_results.hud_total, before)

    def test_incompatible_saved_build_is_rejected_without_changing_ui_or_file(self):
        self.select_weapon("Alternox Prime")
        self.equip(0, "Cryo Rounds")
        before = self.window.current_results.hud_total
        path = self.paths["builds"] / "old-incompatible.json"
        content = json.dumps({"weapon": "Hek", "mods": [{
            "unique_name": "/Lotus/Upgrades/Mods/Rifle/WeaponDamageAmountMod", "rank": 10}]})
        path.write_text(content, encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
            self.window.load_build()
            self.window.compare_build()
        self.assertEqual(self.warning.call_count, 2)
        self.assertIn("incompatible", str(self.warning.call_args))
        self.assertEqual(self.window.selected_weapon.weapon, "Alternox Prime")
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertAlmostEqual(self.window.current_results.hud_total, before)
        self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_failed_save_preserves_the_previous_file(self):
        self.select_weapon("Alternox Prime")
        path = self.paths["builds"] / "existing.json"
        path.write_text("previous contents", encoding="utf-8")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "JSON")), \
             patch("gui.app.os.replace", side_effect=OSError("disk error")):
            self.window.save_build()
        self.assertEqual(path.read_text(encoding="utf-8"), "previous contents")
        self.assertTrue(self.warning.called)
        self.assertFalse(list(path.parent.glob(".existing.json.*.tmp")))

    def test_oversized_build_is_not_saved_over_an_existing_file(self):
        self.select_weapon("Braton")
        path = self.paths["builds"] / "existing.json"
        path.write_text("previous contents", encoding="utf-8")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "JSON")), \
             patch("gui.app.MAX_BUILD_JSON_BYTES", 32):
            self.window.save_build()
        self.assertEqual(path.read_text(encoding="utf-8"), "previous contents")
        self.assertIn("safety limit", str(self.warning.call_args))
        self.assertFalse(list(path.parent.glob(".existing.json.*.tmp")))

    def test_malformed_build_files_are_reported_for_load_and_compare(self):
        self.select_weapon("Alternox Prime")
        path = self.paths["builds"] / "bad.json"
        for content in ('{broken', '[]', '{"weapon":"Alternox Prime", "mods": [null]}',
                        '{"weapon":"Alternox Prime", "inputs": []}',
                        '{"weapon":"Alternox Prime", "mods": {}}',
                        '{"weapon":"Alternox Prime", "inputs": {"armor": "inf"}}'):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                self.warning.reset_mock()
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
                    self.window.load_build()
                    self.window.compare_build()
                self.assertEqual(self.warning.call_count, 2)
                self.assertEqual(self.window.selected_weapon.weapon, "Alternox Prime")

    def test_invalid_numeric_inputs_clear_results_and_recover_without_modal_errors(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        for field, label in ((self.window.armor_edit, "Armor"),
                             (self.window.valence_edit, "Valence")):
            for value in ("not a number", "nan", "inf", "-1", "1e309", "-1e-9999", "1e-9999", "."):
                with self.subTest(field=label, value=value):
                    field.setText(value)
                    self.assertIsNone(self.window.current_results)
                    self.assertEqual(self.window.cards["hud_total"].value_label.text(), "—")
                    self.assertIn(label.lower(), self.window.input_warning.text().lower())
                    self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
                    self.assertFalse(self.critical.called)
                    field.setText("0")
                    self.assertIsNotNone(self.window.current_results)
                    self.assertFalse(self.window.input_warning.isVisible())

    def test_empty_numeric_fields_mean_zero_and_valid_decimals_are_accepted(self):
        self.select_weapon("Braton")
        self.window.armor_edit.setText("")
        self.window.valence_edit.setText("   ")
        self.assertIsNotNone(self.window.current_results)
        self.assertFalse(self.window.input_warning.isVisible())
        path = self.paths["builds"] / "blank-values.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "JSON")):
            self.window.save_build()
        self.window.armor_edit.setText("10")
        self.window.valence_edit.setText("10")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
             patch.object(CompareBuildDialog, "exec", return_value=0):
            self.window.load_build()
            self.window.compare_build()
        self.assertEqual(self.window.armor_edit.text(), "")
        self.assertEqual(self.window.valence_edit.text(), "   ")
        self.assertIsNotNone(self.window.current_results)
        self.assertFalse(self.warning.called)
        self.window.lich_combo.setCurrentText("HEAT")
        self.window.armor_edit.setText("500.5")
        self.window.valence_edit.setText(" 2.5e1 ")
        self.assertIsNotNone(self.window.current_results)
        self.assertAlmostEqual(self.window.current_results.weapon_total_damage,
                               self.window.selected_weapon.dmg + 25)

    def test_overflowing_calculation_is_inline_and_cannot_be_saved_or_compared(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        self.window.lich_combo.setCurrentText("HEAT")
        self.window.valence_edit.setText("1e308")
        self.assertIsNone(self.window.current_results)
        self.assertIn("finite", self.window.input_warning.text().lower())
        self.assertFalse(self.critical.called)
        target = self.paths["builds"] / "keep.json"
        target.write_text("existing build", encoding="utf-8")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "JSON")) as save, \
             patch.object(QFileDialog, "getOpenFileName") as compare:
            self.window.save_build()
            self.window.compare_build()
        save.assert_not_called()
        compare.assert_not_called()
        self.assertEqual(target.read_text(encoding="utf-8"), "existing build")
        self.assertIn("finite", str(self.warning.call_args).lower())
        self.window.valence_edit.setText("25")
        self.assertIsNotNone(self.window.current_results)
        self.assertFalse(self.window.input_warning.isVisible())

    def test_invalid_numeric_inputs_cannot_overwrite_a_saved_build(self):
        self.select_weapon("Braton")
        target = self.paths["builds"] / "keep.json"
        original = '{"weapon":"existing"}'
        target.write_text(original, encoding="utf-8")
        self.window.armor_edit.setText("bad armor")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "JSON")) as dialog:
            self.window.save_build()
        dialog.assert_not_called()
        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertIn("armor", str(self.warning.call_args).lower())

    def test_overflowing_saved_build_is_rejected_without_changing_the_current_build(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        original = self.window.current_results
        path = self.paths["builds"] / "overflow.json"
        content = json.dumps({"weapon": "Hek", "inputs": {
            "lich_element": "HEAT", "valence_base": "1e308"}})
        path.write_text(content, encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
             patch.object(CompareBuildDialog, "exec", return_value=0):
            self.window.load_build()
            self.window.compare_build()
        self.assertEqual(self.warning.call_count, 2)
        self.assertEqual(self.window.selected_weapon.weapon, "Braton")
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertIs(self.window.current_results, original)
        self.assertEqual(path.read_text(encoding="utf-8"), content)
        self.assertFalse(self.critical.called)

    def test_saved_json_numeric_decimals_remain_supported(self):
        self.select_weapon("Braton")
        path = self.paths["builds"] / "numeric.json"
        path.write_text(json.dumps({"weapon": "Braton", "inputs": {
            "armor": 12.5, "valence_base": 2.5, "lich_element": "HEAT"}}), encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")):
            self.window.load_build()
        self.assertEqual(self.window.armor_edit.text(), "12.5")
        self.assertEqual(self.window.valence_edit.text(), "2.5")
        self.assertAlmostEqual(self.window.current_results.weapon_total_damage,
                               self.window.selected_weapon.dmg + 2.5)
        self.assertFalse(self.warning.called)

    def test_saved_json_numeric_underflow_is_not_silently_converted_to_zero(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        original = self.window.current_results
        path = self.paths["builds"] / "underflow.json"
        for value in ("-1e-9999", "1e-9999", "1e" + "9" * 100):
            content = '{"weapon":"Hek", "inputs":{"armor":' + value + '}}'
            path.write_text(content, encoding="utf-8")
            self.warning.reset_mock()
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
                 patch.object(CompareBuildDialog, "exec", return_value=0):
                self.window.load_build()
                self.window.compare_build()
            self.assertEqual(self.warning.call_count, 2)
            self.assertEqual(self.window.selected_weapon.weapon, "Braton")
            self.assertIs(self.window.current_results, original)
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_negative_or_invalid_numeric_build_inputs_are_rejected_before_mutation(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        original = self.window.current_results
        path = self.paths["builds"] / "bad-numbers.json"
        for key, value in (("armor", -100), ("valence_base", "-1"),
                           ("armor", False), ("valence_base", "nan"),
                           ("armor", "not a number"), ("armor", None),
                           ("valence_base", None)):
            with self.subTest(key=key, value=value):
                path.write_text(json.dumps({"weapon": "Alternox Prime", "inputs": {key: value}}),
                                encoding="utf-8")
                self.warning.reset_mock()
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
                     patch.object(CompareBuildDialog, "exec", return_value=0):
                    self.window.load_build()
                    self.window.compare_build()
                self.assertEqual(self.warning.call_count, 2)
                self.assertEqual(self.window.selected_weapon.weapon, "Braton")
                self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
                self.assertIs(self.window.current_results, original)

    def test_oversized_or_deeply_nested_build_is_rejected_without_mutation(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        original = self.window.current_results
        path = self.paths["builds"] / "large-or-deep.json"
        oversized = json.dumps({"weapon": "Hek", "extra": "x" * 1000})
        nested = '{"weapon":"Hek", "extra":' + '[' * 2000 + '0' + ']' * 2000 + '}'
        for content, limit in ((oversized, 256), (nested, 1024 * 1024)):
            with self.subTest(limit=limit):
                path.write_text(content, encoding="utf-8")
                self.warning.reset_mock()
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
                     patch("gui.app.MAX_BUILD_JSON_BYTES", limit), \
                     patch.object(CompareBuildDialog, "exec", return_value=0):
                    self.window.load_build()
                    self.window.compare_build()
                self.assertEqual(self.warning.call_count, 2)
                self.assertEqual(self.window.selected_weapon.weapon, "Braton")
                self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
                self.assertIs(self.window.current_results, original)
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_build_depth_limit_is_explicit_and_ignores_brackets_in_strings(self):
        from gui.app import MAX_BUILD_JSON_DEPTH

        self.select_weapon("Braton")
        original = self.window.current_results
        path = self.paths["builds"] / "depth-boundary.json"
        # The outer object is one level; brackets in the quoted value do not
        # count, including after escaped quotes and backslashes.
        value = json.dumps('[{"quoted": "brackets"}] \\')
        for nesting, accepted in ((MAX_BUILD_JSON_DEPTH - 1, True), (MAX_BUILD_JSON_DEPTH, False)):
            with self.subTest(nesting=nesting):
                content = '{"weapon":"Braton", "extra":' + '[' * nesting + value + ']' * nesting + '}'
                path.write_text(content, encoding="utf-8")
                self.warning.reset_mock()
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
                     patch.object(CompareBuildDialog, "exec", return_value=0) as dialog:
                    self.window.compare_build()
                self.assertEqual(self.warning.call_count, 0 if accepted else 1)
                self.assertEqual(dialog.call_count, 1 if accepted else 0)
                self.assertIs(self.window.current_results, original)
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_duplicate_build_keys_are_rejected_without_changing_the_build(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        original = self.window.current_results
        path = self.paths["builds"] / "ambiguous.json"
        for content in (
            '{"weapon":"Braton", "weapon":"Hek"}',
            '{"weapon":"Hek", "inputs":{"armor":"0", "armor":"100"}}',
        ):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                self.warning.reset_mock()
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON")), \
                     patch.object(CompareBuildDialog, "exec", return_value=0):
                    self.window.load_build()
                    self.window.compare_build()
                self.assertEqual(self.warning.call_count, 2)
                self.assertEqual(self.window.selected_weapon.weapon, "Braton")
                self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
                self.assertIs(self.window.current_results, original)
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_saved_data_rebuild_does_not_call_the_network_and_shows_backup(self):
        seed_source_files(ROOT)
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            connection.execute("INSERT INTO mods(unique_name, name) VALUES('/custom/mod', 'Custom Mod')")
        dialog = SettingsDialog(self.window)
        try:
            with patch("modules.updater.WarframeDataUpdater.refresh",
                       side_effect=AssertionError("network must not be called")) as refresh, \
                 patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as confirm:
                dialog.use_backup_button.click()
                self.wait_for_pipeline()
            refresh.assert_not_called()
            self.assertIn("backed up", confirm.call_args.args[2])
            self.assertIn("weapon", confirm.call_args.args[2].lower())
            self.assertIn("rebuilt", dialog.status.toPlainText().lower())
            self.assertTrue(self.information.called)
            backups = list((self.paths["data"] / "backups").glob("*-pre-rebuild-*.sqlite3"))
            self.assertEqual(len(backups), 1)
            self.assertIn(str(backups[0]), dialog.status.toPlainText())
            self.assertIn(str(backups[0]), self.information.call_args.args[2])
            with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],
                                 CURRENT_DATABASE_REVISION)
                self.assertEqual(connection.execute("SELECT count(*) FROM mods WHERE unique_name='/custom/mod'").fetchone()[0], 0)
            with closing(sqlite3.connect(backups[0])) as connection, connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM mods WHERE unique_name='/custom/mod'").fetchone()[0], 1)
        finally:
            dialog.close()

    def test_rebuild_schema_guard_reports_trigger_and_preserves_other_user_tables(self):
        seed_source_files(ROOT)
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            connection.execute("CREATE TABLE personal_notes (note TEXT)")
            connection.execute("INSERT INTO personal_notes VALUES ('keep me')")
            connection.execute("CREATE TRIGGER user_mod_trigger AFTER DELETE ON MODS BEGIN "
                               "DELETE FROM personal_notes; END")
        dialog = SettingsDialog(self.window)
        try:
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                dialog.use_backup_button.click()
                self.wait_for_pipeline()
            self.assertIn("user_mod_trigger", dialog.status.toPlainText())
            self.assertTrue(self.critical.called)
            with closing(sqlite3.connect(self.paths["db"])) as connection:
                self.assertEqual(connection.execute("SELECT note FROM personal_notes").fetchone()[0], "keep me")
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],
                                 CURRENT_DATABASE_REVISION)
        finally:
            self.critical.reset_mock()
            dialog.close()

    def test_backup_failure_is_reported_without_erasing_custom_mods(self):
        seed_source_files(ROOT)
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            connection.execute("INSERT INTO mods(unique_name, name) VALUES('/custom/mod', 'Custom Mod')")
        dialog = SettingsDialog(self.window)
        try:
            with patch("modules.importer.create_database_backup", side_effect=OSError("disk full")), \
                 patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                dialog.use_backup_button.click()
                self.wait_for_pipeline()
            self.assertIn("disk full", dialog.status.toPlainText())
            self.assertTrue(self.critical.called)
            with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM mods WHERE unique_name='/custom/mod'").fetchone()[0], 1)
        finally:
            self.critical.reset_mock()
            dialog.close()

    def test_cancel_rebuild_leaves_database_and_sources_alone(self):
        dialog = SettingsDialog(self.window)
        try:
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), \
                 patch.object(self.window, "start_data_pipeline") as pipeline:
                dialog.use_backup_button.click()
                dialog.update_and_rebuild_button.click()
            pipeline.assert_not_called()
        finally:
            dialog.close()

    def test_locked_catalog_does_not_trigger_an_initial_rebuild_prompt(self):
        self.select_weapon("Braton")
        self.equip(0, "Cryo Rounds")
        original = self.window.current_results
        real_connect = sqlite3.connect

        def fast_connect(*args, **kwargs):
            kwargs["timeout"] = 0.05
            return real_connect(*args, **kwargs)

        with closing(real_connect(self.paths["db"], timeout=0.05)) as locker:
            locker.execute("BEGIN EXCLUSIVE")
            try:
                with patch.object(startup.sqlite3, "connect", side_effect=fast_connect), \
                     patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes) as prompt, \
                     patch.object(self.window, "start_data_pipeline") as pipeline:
                    startup.maybe_bootstrap_database(self.window)
            finally:
                locker.rollback()
        prompt.assert_not_called()
        pipeline.assert_not_called()
        self.assertIn("locked", str(self.warning.call_args).lower())
        self.assertEqual(self.window.selected_weapon.weapon, "Braton")
        self.assertEqual(self.window.mod_slots[0].current_mod.name, "Cryo Rounds")
        self.assertIs(self.window.current_results, original)

    def test_first_run_declined_does_not_start_a_download(self):
        shown = []
        def inspect_prompt(dialog):
            shown.append(dialog.text())
            return QMessageBox.StandardButton.No
        with patch.object(startup, "database_is_ready", return_value=False), \
             patch.object(QMessageBox, "exec", inspect_prompt), \
             patch.object(self.window, "start_data_pipeline") as pipeline:
            startup.maybe_bootstrap_database(self.window)
        pipeline.assert_not_called()
        self.assertIn("backed up", shown[0].lower())
        self.assertIn("replaced", shown[0].lower())

    def test_startup_upgrades_before_window_construction(self):
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            connection.execute("PRAGMA user_version=0")
            connection.execute("UPDATE weapons SET heat=75, elec=0 WHERE weapon='Alternox Prime'")
        observed = []
        real_window = DamageCalculatorWindow
        created = []
        def make_window(*args, **kwargs):
            with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
                observed.append((connection.execute("PRAGMA user_version").fetchone()[0],
                                 connection.execute("SELECT heat,elec FROM weapons "
                                                    "WHERE weapon='Alternox Prime'").fetchone()))
            window = real_window(*args, **kwargs)
            created.append(window)
            return window
        with patch.object(startup, "build_application", return_value=self.app), \
             patch.object(startup, "DamageCalculatorWindow", side_effect=make_window), \
             patch.object(QApplication, "exec", return_value=0), \
             patch("modules.updater.WarframeDataUpdater.refresh") as refresh:
            startup.main()
        refresh.assert_not_called()
        for window in created:
            window.close()
            window.deleteLater()
        self.assertEqual(observed, [(CURRENT_DATABASE_REVISION, (0.0, 75.0))])
        self.assertTrue(any("Database Upgraded" in str(call) for call in self.information.call_args_list))
        self.assertFalse(self.warning.called)
        self.assertEqual(len(list((self.paths["data"] / "backups").glob("*.sqlite3"))), 1)

    def test_startup_source_seed_failure_is_visible_and_does_not_open_window(self):
        with patch.object(startup, "build_application", return_value=self.app), \
             patch.object(startup, "seed_source_files", side_effect=OSError("disk full")), \
             patch.object(startup, "DamageCalculatorWindow") as window_factory, \
             patch.object(QApplication, "exec", return_value=0) as app_exec, \
             patch.object(QMessageBox, "critical") as error:
            status = startup.main()
        self.assertEqual(status, 1)
        window_factory.assert_not_called()
        app_exec.assert_not_called()
        self.assertIn("disk full", error.call_args.args[2])
        with closing(sqlite3.connect(self.paths["db"])) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],
                             CURRENT_DATABASE_REVISION)

    def test_startup_preserves_orphaned_database_sidecar_before_opening_window(self):
        database = self.paths["db"]
        database.unlink()
        sidecar = Path(str(database) + "-wal")
        sidecar.write_bytes(b"potentially recoverable WAL")
        with patch.object(startup, "build_application", return_value=self.app), \
             patch.object(startup, "seed_source_files"), \
             patch.object(startup, "DamageCalculatorWindow") as window_factory, \
             patch.object(startup, "maybe_bootstrap_database") as bootstrap, \
             patch.object(QApplication, "exec", return_value=0):
            status = startup.main()
        self.assertEqual(status, 1)
        window_factory.assert_not_called()
        bootstrap.assert_not_called()
        self.assertIn("sidecar", str(self.critical.call_args).lower())
        self.assertFalse(database.exists())
        self.assertEqual(sidecar.read_bytes(), b"potentially recoverable WAL")
        self.critical.reset_mock()

    def test_startup_failure_blocks_window_and_reports_the_error(self):
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            connection.execute("PRAGMA user_version=0")
        # Seeding deliberately does not overwrite existing files.
        (self.paths["source"] / "ExportWeapons_en_Cleaned.zip").write_bytes(b"invalid")
        with patch.object(startup, "build_application", return_value=self.app), \
             patch.object(startup, "DamageCalculatorWindow") as window_factory, \
             patch.object(QApplication, "exec", return_value=0) as app_exec, \
             patch.object(QMessageBox, "critical") as error:
            status = startup.main()
        self.assertEqual(status, 1)
        window_factory.assert_not_called()
        app_exec.assert_not_called()
        error.assert_called_once()
        self.assertIn("No migration changes", error.call_args.args[2])
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_startup_rejects_newer_revisions_before_building_a_window(self):
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            connection.execute(f"PRAGMA user_version={CURRENT_DATABASE_REVISION + 1}")
        with patch.object(startup, "build_application", return_value=self.app), \
             patch.object(startup, "DamageCalculatorWindow") as window_factory, \
             patch.object(QMessageBox, "critical") as error:
            startup.main()
        window_factory.assert_not_called()
        self.assertIn("newer", error.call_args.args[2])
        with closing(sqlite3.connect(self.paths["db"])) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],
                             CURRENT_DATABASE_REVISION + 1)


if __name__ == "__main__":
    unittest.main()
