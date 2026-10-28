"""Test-only PyInstaller runtime hook to exercise the packaged application.

This hook is injected by packaging_smoke.spec, never by the production spec.
The runner supplies isolated app data and reads the resulting JSON file.
"""
from __future__ import annotations

import json
import os
import sqlite3
import traceback
from contextlib import closing
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

_original_exec = QApplication.exec


def _exercise_packaged_app() -> None:
    result_path = Path(os.environ["WDC_PACKAGING_SMOKE_RESULT"])
    result: dict[str, object] = {"ok": False}
    try:
        from modules.importer import build_database

        windows = [window for window in QApplication.topLevelWidgets() if window.isVisible()]
        window = next(item for item in windows if type(item).__name__ == "DamageCalculatorWindow")
        assert not any(isinstance(item, QMessageBox) for item in windows), "unexpected startup dialog"
        window.search_edit.setText("Alternox Prime")
        matches = window.weapon_list.findItems("Alternox Prime", Qt.MatchFlag.MatchExactly)
        assert len(matches) == 1, "packaged database did not expose Alternox Prime"
        window.weapon_list.setCurrentItem(matches[0])
        for index, name in enumerate(("Cryo Rounds", "Infected Clip", "Hellfire")):
            mod = next(mod for mod in window.available_mods if mod.name == name and mod.fusion_limit == 5)
            slot = window.mod_slots[index]
            selection = slot.mod_combo.findData(mod.unique_name)
            assert selection >= 0, f"{name} was not in the mod picker"
            slot.mod_combo.setCurrentIndex(selection)
            slot.rank_spin.setValue(5)
        assert abs(window.current_results.hud_damage_by_type["VIRAL"] - 135) < 1e-9
        assert abs(window.current_results.hud_damage_by_type["RAD"] - 142.5) < 1e-9
        expected_total = window.current_results.final_total

        # Avoid native file dialogs while testing packaged save/load behavior.
        build_file = window.paths["builds"] / "packaged-smoke.json"
        QFileDialog.getSaveFileName = staticmethod(lambda *args: (str(build_file), "JSON"))
        QFileDialog.getOpenFileName = staticmethod(lambda *args: (str(build_file), "JSON"))
        QMessageBox.information = staticmethod(lambda *args: QMessageBox.StandardButton.Ok)

        def reject_warning(*args):
            raise AssertionError(f"Unexpected warning: {args}")
        QMessageBox.warning = staticmethod(reject_warning)
        window.save_build()
        assert build_file.is_file(), "packaged save did not produce a file"
        window.clear_all_mods()
        window.load_build()
        assert [slot.current_mod.name for slot in window.mod_slots[:3]] == [
            "Cryo Rounds", "Infected Clip", "Hellfire"]
        assert abs(window.current_results.final_total - expected_total) < 1e-9

        # Verify that the separately bundled compatibility snapshot is loaded,
        # including the Wiki override, and that melee base damage survived the
        # import/parser changes. Restore the saved build afterwards.
        window.search_edit.setText("Coda Bubonico")
        window.weapon_list.setCurrentItem(window.weapon_list.findItems(
            "Coda Bubonico", Qt.MatchFlag.MatchExactly)[0])
        names = {mod.name for mod in window.available_mods}
        assert "Point Blank" in names and "Serration" not in names, "packaged primary family filter failed"
        window.search_edit.setText("Jat Kittag")
        window.weapon_list.setCurrentItem(window.weapon_list.findItems(
            "Jat Kittag", Qt.MatchFlag.MatchExactly)[0])
        baseline = window.current_results.hud_total
        slot = window.mod_slots[0]
        index = slot.mod_combo.findData("/Lotus/Upgrades/Mods/Melee/Expert/WeaponMeleeDamageModExpert")
        assert index >= 0, "Primed Pressure Point is unavailable"
        slot.mod_combo.setCurrentIndex(index)
        slot.rank_spin.setValue(10)
        assert abs(window.current_results.hud_total - baseline * 2.65) < 1e-6
        window.load_build()
        assert window.selected_weapon.weapon == "Alternox Prime"

        # Check bundled exports, spreadsheet, openpyxl and SQLite without
        # modifying the active database or contacting DE.
        rebuilt = window.paths["temp"] / "packaged-rebuild.db"
        source = window.paths["source"]
        initial_backup = build_database(rebuilt, source / "ExportWeapons_en_Cleaned.zip",
                                        source / "ExportKeys_en_Cleaned.zip",
                                        source / "Warframe-Damage-Calculator_v2.xlsx")
        assert initial_backup is None, "a new database should not create a backup"
        with closing(sqlite3.connect(rebuilt)) as connection, connection:
            connection.execute("INSERT INTO mods(unique_name, name) VALUES('/test/custom', 'Custom Mod')")
        backup = build_database(rebuilt, source / "ExportWeapons_en_Cleaned.zip",
                                source / "ExportKeys_en_Cleaned.zip",
                                source / "Warframe-Damage-Calculator_v2.xlsx")
        assert backup is not None and backup.is_file(), "rebuild did not retain a backup"
        with closing(sqlite3.connect(backup)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("SELECT count(*) FROM mods WHERE unique_name='/test/custom'").fetchone()[0] == 1
        with closing(sqlite3.connect(rebuilt)) as connection:
            count = connection.execute("SELECT count(*) FROM weapons").fetchone()[0]
            assert count > 0 and connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("SELECT count(*) FROM mods WHERE unique_name='/test/custom'").fetchone()[0] == 0
            grimoire = connection.execute(
                "SELECT unique_name,dmg,elec FROM weapons WHERE weapon='Grimoire'").fetchone()
            assert grimoire == ("/Lotus/Weapons/Tenno/Grimoire/TnGrimoire", 150, 150), \
                "packaged import selected the wrong Grimoire"
        result = {"ok": True, "weapon": window.selected_weapon.weapon,
                  "mod_slots": 3, "viral": window.current_results.hud_damage_by_type["VIRAL"],
                  "radiation": window.current_results.hud_damage_by_type["RAD"],
                  "primary_family_and_melee_base_verified": True,
                  "grimoire_export_collision_verified": True,
                  "rebuilt_weapon_rows": count, "rebuild_backup_verified": True}
    except BaseException:
        result["error"] = traceback.format_exc()
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    QApplication.instance().exit(0 if result["ok"] else 7)


def _instrumented_exec() -> int:
    QTimer.singleShot(250, _exercise_packaged_app)
    return _original_exec()


QApplication.exec = staticmethod(_instrumented_exec)
