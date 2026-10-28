from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.app_paths import ensure_app_dirs
from modules.calculator import DamageCalculator
from modules.constants import (
    APP_TITLE,
    APP_VERSION,
    DAMAGE_TYPES,
    DISPLAY_NAMES,
    FACTION_MULTIPLIERS,
    MOD_SLOT_COUNT,
    WINDOW_TITLE,
)
from modules.database import ModRepository, WeaponRepository
from modules.importer import build_database
from modules.mod_compatibility import ModCompatibility
from modules.models import CalculationInputs, EquippedMod, Mod, Weapon
from modules.updater import WarframeDataUpdater

DARK_STYLESHEET = """
QWidget {
    background-color: #11161f;
    color: #e6ecff;
    font-size: 12px;
}
QMainWindow, QScrollArea, QGroupBox, QFrame {
    background-color: #11161f;
}
QLineEdit, QComboBox, QSpinBox, QListWidget, QTableWidget, QTextEdit {
    background-color: #1a2230;
    color: #edf2ff;
    border: 1px solid #2b3850;
    border-radius: 8px;
    padding: 6px;
    selection-background-color: #2c6bed;
    selection-color: #ffffff;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView, QListWidget {
    background-color: #182131;
    alternate-background-color: #1d2738;
    color: #edf2ff;
    border: 1px solid #2b3850;
    selection-background-color: #2c6bed;
    selection-color: #ffffff;
}
QPushButton {
    background-color: #2c6bed;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #3d7af0;
}
QPushButton:pressed {
    background-color: #275dcb;
}
QGroupBox {
    border: 1px solid #283244;
    border-radius: 14px;
    margin-top: 14px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #9fb9ff;
}
QHeaderView::section {
    background-color: #20293a;
    color: #dce7ff;
    border: 0;
    border-right: 1px solid #33425d;
    padding: 6px;
}
QTableWidget {
    gridline-color: #2a3448;
    background-color: #182131;
    alternate-background-color: #1d2738;
    color: #edf2ff;
}
QTableWidget::item {
    padding: 6px;
    border: none;
    background: transparent;
}
QTableCornerButton::section {
    background-color: #20293a;
    border: 0;
}
QScrollBar:vertical {
    background-color: #141b27;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #33425d;
    min-height: 24px;
    border-radius: 6px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    background: none;
    border: none;
    height: 0;
}
QListWidget::item:selected {
    background-color: #2c6bed;
    border-radius: 6px;
}
"""

FAQ_TEXT = """
WDC FAQ - Warframe Damage Calculator by TenZeroGG
==============================

Why are there both HUD values and Final values?
-----------------------------------------------
The HUD / Mod Screen values show the damage buckets after the weapon, adversary bonus, and mod values have been built into each damage type. This view is useful for seeing what the build itself is doing before enemy modifiers are applied.

The Final values treat the exported damage row as one non-critical hit to health after faction damage-type modifiers and armor. Some export rows combine separate direct and radial hits; for those weapons this is not a per-hit estimate and does not model falloff or separate quantization. Shields, Overguard, critical hits, status effects, and special weapon mechanics are also outside this screen's scope.

What is the valence input doing?
--------------------------------
Enter the adversary bonus as an absolute damage value, not a percentage. For example, a 60% bonus on 100 base damage is 60. Select its element; without a selected element no bonus is added.

True Valence = Valence Base / Base Weapon Damage

The bonus is included in weapon base damage before mods and enemy calculations.

Why is Quanta shown?
--------------------
The wiki describes direct-hit damage quantization in units of one thirty-second of modded base damage:

Quanta = Weapon Total Damage x (1 + Base Damage Bonuses) / 32

Final damage types are quantized before faction and armor. Arsenal-style HUD values are not quantized. The displayed values are estimates and do not replicate every game rounding rule.

Why can the HUD total and Final total be very different?
--------------------------------------------------------
Because enemy health type and armor matter a lot. The HUD side shows the built damage on the weapon. The Final side shows what survives after enemy modifiers are applied to each damage bucket.

How are elemental mods combined?
--------------------------------
Primary elements are grouped by mod slot order, followed by innate and adversary primaries in Heat, Cold, Electricity, Toxin order. Pairs form Blast, Radiation, Gas, Magnetic, Viral, or Corrosive. Already-combined elements stay separate.

Why do faction mods show separately?
------------------------------------
Faction damage is tracked as its own multiplier so the calculator can show the pre-faction and post-faction totals separately.

How does WDC process the damage flow?
------------------------------------
WDC preserves the same layered logic used by the calculator engine:
- weapon lookup
- true valence reconstruction
- elemental combination by slot order
- HUD bucket calculation
- direct-hit quantization
- faction and armor application
- final total calculation

Why might a weapon estimate differ from gameplay?
------------------------------------------------
Exported stats can be stale, omit attack modes, or combine multiple hit components. The screen also omits falloff and many mechanics; hidden precision and game rounding can add differences. An adversary bonus must be entered as an absolute value for the selected element.

Where is the database saved?
----------------------------
The SQLite database and source data live in WDC's AppData-backed folder so the app can be packaged later without relying on files sitting beside the executable.

What happens when an older database is upgraded?
------------------------------------------------
WDC upgrades supported older databases from the saved local exports without downloading. It keeps a pre-upgrade backup in data/backups and stops if it cannot upgrade safely. Explicit rebuilds replace the mod catalog, but first back up an existing database in data/backups.

How does the data updater work?
-------------------------------
WDC can download fresh public export data from DE and rebuild the SQLite database in one step. If the download cannot be completed, WDC can fall back to saved local export files, initially seeded from the app.
""".strip()


class SummaryCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QFrame { background-color: #182131; border: 1px solid #2b3950; border-radius: 16px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        label = QLabel(title)
        label.setStyleSheet("color: #8ea9e6; font-size: 11px;")
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        layout.addWidget(label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class FAQDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_TITLE} FAQ")
        self.resize(880, 760)
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(FAQ_TEXT)
        layout.addWidget(text)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)




ENEMY_PRESETS = {
    "Custom": (None, None),
    "Grineer Heavy Armor": ("Grineer", 500),
    "Kuva Heavy Armor": ("Kuva", 600),
    "Corpus Tech": ("Corpus", 250),
    "Amalgam": ("Amalgam", 300),
    "Infested Heavy": ("Infested", 150),
    "Deimos Heavy": ("Deimos", 175),
    "Corrupted Heavy": ("Orokin", 400),
    "Sentient Durable": ("Sentient", 350),
    "Narmer Heavy": ("Narmer", 375),
    "Murmur Heavy": ("Murmur", 450),
    "Zariman Void": ("Zariman", 250),
}


class CompareBuildDialog(QDialog):
    def __init__(self, current_summary: list[tuple[str, str]], compare_summary: list[tuple[str, str]], compare_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare Builds")
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        intro = QLabel(f"Current build is shown against: {compare_name}")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        table = QTableWidget(len(current_summary), 3)
        table.setHorizontalHeaderLabels(["Metric", "Current Build", "Compared Build"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        compare_map = {name: value for name, value in compare_summary}
        for row_index, (metric, current_value) in enumerate(current_summary):
            table.setItem(row_index, 0, QTableWidgetItem(metric))
            table.setItem(row_index, 1, QTableWidgetItem(current_value))
            table.setItem(row_index, 2, QTableWidgetItem(compare_map.get(metric, "-")))

        layout.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class ModPickerDialog(QDialog):
    def __init__(self, mods: list[Mod], current_unique_name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Mod")
        self.resize(760, 560)
        self.mods = mods
        self.selected_unique_name = current_unique_name

        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search mods...")
        self.list_widget = QListWidget()
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(140)

        layout.addWidget(self.search_edit)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.detail_text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.search_edit.textChanged.connect(self.refresh_list)
        self.list_widget.currentItemChanged.connect(self.on_current_changed)
        self.list_widget.itemDoubleClicked.connect(lambda *_: self.accept())

        self.refresh_list()

    def refresh_list(self) -> None:
        query = self.search_edit.text().strip().lower()
        self.list_widget.clear()
        selected_row = 0
        for mod in self.mods:
            haystack = f"{mod.name} {mod.effect_summary} {mod.description}".lower()
            if query and query not in haystack:
                continue
            label = mod.name
            if mod.effect_summary:
                label += f"  |  {mod.effect_summary[:72]}"
            if mod.polarity:
                label += f"  |  Polarity: {mod.polarity}"
            label += f"  |  Drain: {mod.base_drain}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, mod.unique_name)
            self.list_widget.addItem(item)
            if mod.unique_name == self.selected_unique_name:
                selected_row = self.list_widget.count() - 1

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(selected_row)

    def on_current_changed(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self.detail_text.clear()
            return
        unique_name = current.data(Qt.ItemDataRole.UserRole)
        mod = next((entry for entry in self.mods if entry.unique_name == unique_name), None)
        if mod is None:
            self.detail_text.clear()
            return
        self.selected_unique_name = mod.unique_name
        lines = [mod.name]
        if mod.effect_summary:
            lines.append(mod.effect_summary)
        if mod.description and mod.description not in mod.effect_summary:
            lines.append(mod.description)
        lines.append(f"Polarity: {mod.polarity or 'None'}")
        lines.append(f"Base Drain: {mod.base_drain}")
        lines.append(f"Max Rank: {mod.fusion_limit}")
        lines.append(f"Compatibility: {mod.compat_name or mod.mod_type or 'General'}")
        self.detail_text.setPlainText("\n".join(lines))

    def chosen_unique_name(self) -> str | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)


class SettingsDialog(QDialog):
    def __init__(self, parent: DamageCalculatorWindow) -> None:
        super().__init__(parent)
        self.window = parent
        self.paths = ensure_app_dirs()
        self.setWindowTitle(f"{APP_TITLE} Settings")
        self.resize(900, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro_box = QGroupBox("Updater and Storage")
        intro_layout = QVBoxLayout(intro_box)
        intro_layout.setContentsMargins(14, 18, 14, 14)
        intro_layout.setSpacing(10)

        intro_text = QLabel(
            "Use this panel to download the latest public export data, rebuild the SQLite database, "
            "and manage where WDC stores its working files. The updater uses Python LZMA recovery for "
            "DE's manifest index and can fall back to the saved local export files when fresh data "
            "cannot be reached."
        )
        intro_text.setWordWrap(True)
        intro_text.setStyleSheet("color: #dce7ff;")
        intro_layout.addWidget(intro_text)

        path_box = QGroupBox("App Paths")
        path_layout = QFormLayout(path_box)
        path_layout.setContentsMargins(12, 16, 12, 12)
        path_layout.setHorizontalSpacing(16)
        path_layout.setVerticalSpacing(10)

        self.root_path_label = QLabel(str(self.paths["root"]))
        self.db_path_label = QLabel(str(self.paths["db"]))
        self.source_path_label = QLabel(str(self.paths["source"]))
        for label in (self.root_path_label, self.db_path_label, self.source_path_label):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setStyleSheet("color: #91a3c4;")

        path_layout.addRow("App Data Folder", self.root_path_label)
        path_layout.addRow("SQLite Database", self.db_path_label)
        path_layout.addRow("Source Folder", self.source_path_label)
        intro_layout.addWidget(path_box)
        layout.addWidget(intro_box)

        status_box = QGroupBox("Status")
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(12, 16, 12, 12)
        self.status = QTextEdit()
        self.status.setReadOnly(True)
        self.status.setMinimumHeight(220)
        self.status.setPlaceholderText("Updater and rebuild messages will show up here.")
        status_layout.addWidget(self.status)
        layout.addWidget(status_box, 1)

        button_box = QGroupBox("Actions")
        button_layout = QGridLayout(button_box)
        button_layout.setContentsMargins(12, 16, 12, 12)
        button_layout.setHorizontalSpacing(10)
        button_layout.setVerticalSpacing(10)
        self.update_and_rebuild_button = QPushButton("Download Fresh Data + Rebuild Database")
        self.use_backup_button = QPushButton("Use Saved Local Exports + Rebuild")
        self.open_folder_button = QPushButton("Open App Data Folder")
        self.close_button = QPushButton("Close")
        self.update_and_rebuild_button.setMinimumHeight(42)
        self.use_backup_button.setMinimumHeight(42)
        self.open_folder_button.setMinimumHeight(42)
        self.close_button.setMinimumHeight(42)
        button_layout.addWidget(self.update_and_rebuild_button, 0, 0, 1, 2)
        button_layout.addWidget(self.use_backup_button, 1, 0)
        button_layout.addWidget(self.open_folder_button, 1, 1)
        button_layout.addWidget(self.close_button, 2, 0, 1, 2)
        button_layout.setColumnStretch(0, 1)
        button_layout.setColumnStretch(1, 1)
        layout.addWidget(button_box)

        self.update_and_rebuild_button.clicked.connect(self.update_and_rebuild)
        self.use_backup_button.clicked.connect(self.rebuild_from_backup)
        self.open_folder_button.clicked.connect(self.open_appdata_folder)
        self.close_button.clicked.connect(self.accept)

    def set_status(self, message: str) -> None:
        self.status.append(message)
        QApplication.processEvents()

    def _confirm_catalog_rebuild(self) -> bool:
        choice = QMessageBox.question(
            self, "Rebuild Database",
            "This rebuild replaces the mod and effect catalog, including custom entries. "
            "An existing database will first be backed up in data/backups. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    def update_and_rebuild(self) -> None:
        if not self._confirm_catalog_rebuild():
            return
        try:
            self.set_status("Downloading fresh data from DE and rebuilding the SQLite database...")
            outputs = self.window.run_data_pipeline(prefer_online=True, log_callback=self.set_status)
            self.set_status(f"Database rebuilt at: {outputs['db_path']}")
            self.set_status(f"Data source: {outputs['source_mode']}")
            self.set_status(f"Manifest decode path: {outputs['lzma_method']}")
            if outputs.get("backup_path"):
                self.set_status(f"Previous database backup: {outputs['backup_path']}")
            if outputs.get("refresh_error"):
                self.set_status(f"Fresh download failed, so WDC used saved local exports: {outputs['refresh_error']}")
            backup_note = f"\n\nPrevious database backup: {outputs['backup_path']}" if outputs.get("backup_path") else ""
            QMessageBox.information(self, "Update Complete", "WDC finished rebuilding the database." + backup_note)
        except Exception as exc:
            self.set_status(f"Update failed: {exc}")
            QMessageBox.critical(self, "Update Failed", str(exc))

    def rebuild_from_backup(self) -> None:
        if not self._confirm_catalog_rebuild():
            return
        try:
            self.set_status("Rebuilding the database from saved local exports...")
            outputs = self.window.run_data_pipeline(prefer_online=False, log_callback=self.set_status)
            self.set_status(f"Database rebuilt at: {outputs['db_path']}")
            self.set_status("WDC used saved local exports for this rebuild.")
            if outputs.get("backup_path"):
                self.set_status(f"Previous database backup: {outputs['backup_path']}")
            backup_note = f"\n\nPrevious database backup: {outputs['backup_path']}" if outputs.get("backup_path") else ""
            QMessageBox.information(self, "Rebuild Complete", "The SQLite database was rebuilt from saved local exports." + backup_note)
        except Exception as exc:
            self.set_status(f"Rebuild failed: {exc}")
            QMessageBox.critical(self, "Rebuild Failed", str(exc))

    def open_appdata_folder(self) -> None:
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths["root"])))
        if not opened:
            QMessageBox.information(self, "App Data Folder", str(self.paths["root"]))


class ModSlotWidget(QGroupBox):
    def __init__(self, slot_number: int, parent: QWidget | None = None) -> None:
        super().__init__(f"Mod Slot {slot_number}", parent)
        self.current_mod: Mod | None = None
        self.mod_lookup: dict[str, Mod] = {}
        self.current_options: list[Mod] = []

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)

        self.mod_combo = QComboBox()
        self.mod_combo.setEditable(True)
        self.mod_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.mod_combo.setMaxVisibleItems(24)
        self.mod_combo.addItem("-- Empty --", None)
        self.mod_combo.setMinimumWidth(300)
        self.mod_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mod_combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.mod_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.mod_combo.view().setAlternatingRowColors(True)

        self.rank_spin = QSpinBox()
        self.rank_spin.setRange(0, 10)
        self.rank_spin.setValue(0)

        self.browse_button = QPushButton("Browse")
        self.clear_button = QPushButton("Clear")
        self.summary_label = QLabel("No mod selected")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #91a3c4;")

        layout.addWidget(QLabel("Mod"), 0, 0)
        layout.addWidget(self.mod_combo, 0, 1)
        layout.addWidget(self.browse_button, 0, 2)
        layout.addWidget(QLabel("Rank"), 0, 3)
        layout.addWidget(self.rank_spin, 0, 4)
        layout.addWidget(self.clear_button, 0, 5)
        layout.addWidget(self.summary_label, 1, 0, 1, 6)

        self.browse_button.clicked.connect(self.open_picker)

    def set_mod_options(self, mods: list[Mod]) -> bool:
        """Refresh the picker and report whether the selected build changed.

        Rebuilding the combo temporarily changes its index. Suppress those
        intermediate signals, including spinbox clamps, so the parent can
        recalculate once after *all* slots have been refreshed.
        """
        current_unique = self.current_mod.unique_name if self.current_mod else None
        old_rank = self.rank_spin.value()
        self.current_options = list(mods)
        self.mod_lookup = {mod.unique_name: mod for mod in mods}
        combo_blocked = self.mod_combo.blockSignals(True)
        rank_blocked = self.rank_spin.blockSignals(True)
        try:
            self.mod_combo.clear()
            self.mod_combo.addItem("-- Empty --", None)
            for mod in mods:
                summary = (mod.effect_summary or mod.description or "").strip()
                suffix = []
                if mod.rarity:
                    suffix.append(mod.rarity.title())
                if mod.polarity:
                    suffix.append(f"Polarity {mod.polarity}")
                suffix.append(f"Drain {mod.base_drain}")
                suffix.append(f"Max {mod.fusion_limit}")
                display_text = mod.name
                if summary:
                    display_text += f"  |  {summary[:64]}"
                display_text += f"  |  {' / '.join(suffix)}"
                self.mod_combo.addItem(display_text, mod.unique_name)
                self.mod_combo.setItemData(self.mod_combo.count() - 1, summary or mod.description, Qt.ItemDataRole.ToolTipRole)

            if current_unique and current_unique in self.mod_lookup:
                index = self.mod_combo.findData(current_unique)
                if index >= 0:
                    self.mod_combo.setCurrentIndex(index)
                    self.current_mod = self.mod_lookup[current_unique]
                    self.rank_spin.setMaximum(max(self.current_mod.fusion_limit, 0))
                    self.rank_spin.setValue(min(old_rank, self.rank_spin.maximum()))
                    self._refresh_summary()
                else:
                    self.clear_selection()
            else:
                self.clear_selection()
        finally:
            self.mod_combo.blockSignals(combo_blocked)
            self.rank_spin.blockSignals(rank_blocked)
        selected = self.current_mod.unique_name if self.current_mod else None
        return (selected, self.rank_spin.value()) != (current_unique, old_rank)

    def selected_unique_name(self) -> str | None:
        return self.mod_combo.currentData()

    def open_picker(self) -> None:
        if not self.current_options:
            return
        dialog = ModPickerDialog(self.current_options, self.selected_unique_name(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        unique_name = dialog.chosen_unique_name()
        if not unique_name:
            return
        index = self.mod_combo.findData(unique_name)
        if index >= 0:
            self.mod_combo.setCurrentIndex(index)

    def _refresh_summary(self) -> None:
        if self.current_mod is None:
            self.summary_label.setText("No mod selected")
            return
        parts = [self.current_mod.effect_summary or self.current_mod.description or "No supported effects found"]
        extra = []
        if self.current_mod.polarity:
            extra.append(f"Polarity: {self.current_mod.polarity}")
        extra.append(f"Drain: {self.current_mod.base_drain}")
        if extra:
            parts.append(" | ".join(extra))
        self.summary_label.setText("\n".join(parts))

    def clear_selection(self) -> None:
        self.current_mod = None
        self.mod_combo.setCurrentIndex(0)
        self.rank_spin.setMaximum(10)
        self.rank_spin.setValue(0)
        self.summary_label.setText("No mod selected")


class DamageCalculatorWindow(QMainWindow):
    def __init__(self, weapon_repository: WeaponRepository, mod_repository: ModRepository, project_root: Path) -> None:
        super().__init__()
        self.weapon_repository = weapon_repository
        self.mod_repository = mod_repository
        self.project_root = project_root
        self.mod_compatibility = ModCompatibility.from_file(project_root / "source" / "weapon_mod_classes.json")
        self.paths = ensure_app_dirs()
        self.calculator = DamageCalculator()
        self.selected_weapon: Weapon | None = None
        self.mod_slots: list[ModSlotWidget] = []
        self.available_mods: list[Mod] = []
        self.current_results = None

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1800, 1040)

        self._build_ui()
        self._connect_events()
        self.refresh_weapon_list()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([340, 1460])

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title = QLabel(f"{APP_TITLE} v{APP_VERSION}")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search weapon name...")

        self.weapon_list = QListWidget()
        self.weapon_summary = QTextEdit()
        self.weapon_summary.setReadOnly(True)
        self.weapon_summary.setMinimumHeight(260)

        subtitle = QLabel("Search for a weapon, build a loadout, and compare estimated damage.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #91a3c4;")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.weapon_list, 1)
        layout.addWidget(self.weapon_summary)

        bottom_buttons = QHBoxLayout()
        self.settings_button = QPushButton("Settings")
        self.faq_button = QPushButton("FAQ")
        bottom_buttons.addWidget(self.settings_button)
        bottom_buttons.addWidget(self.faq_button)
        layout.addLayout(bottom_buttons)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setSpacing(12)

        layout.addWidget(self._build_inputs_group())
        layout.addWidget(self._build_summary_cards())
        layout.addWidget(self._build_mod_section())
        layout.addWidget(self._build_tables_section())
        layout.addStretch(1)

        return panel

    def _build_inputs_group(self) -> QWidget:
        box = QGroupBox("Enemy / Weapon Inputs")
        form = QFormLayout(box)
        form.setContentsMargins(14, 18, 14, 14)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        self.enemy_preset_combo = QComboBox()
        self.enemy_preset_combo.addItems(list(ENEMY_PRESETS.keys()))

        self.lich_combo = QComboBox()
        self.lich_combo.addItems([""] + DAMAGE_TYPES)
        self.valence_edit = QLineEdit("0")
        self.valence_edit.setToolTip(
            "Absolute adversary bonus damage, not percent: e.g. 60 for a 60% bonus on 100 base damage."
        )
        self.faction_combo = QComboBox()
        self.faction_combo.addItems(list(FACTION_MULTIPLIERS.keys()))
        self.armor_edit = QLineEdit("0")

        form.addRow("Enemy Preset", self.enemy_preset_combo)
        form.addRow("Adversary Element", self.lich_combo)
        form.addRow("Valence Base", self.valence_edit)
        form.addRow("Faction", self.faction_combo)
        form.addRow("Armor Value", self.armor_edit)
        return box

    def _build_summary_cards(self) -> QWidget:
        wrapper = QWidget()
        grid = QGridLayout(wrapper)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self.cards = {
            "base_damage": SummaryCard("Base Damage"),
            "weapon_total_damage": SummaryCard("Weapon Damage"),
            "quanta": SummaryCard("Quanta"),
            "valence_multiplier": SummaryCard("True Valence"),
            "hud_total": SummaryCard("HUD Total"),
            "hud_total_with_bane": SummaryCard("HUD + Bane"),
            "final_total": SummaryCard("Final Total"),
            "final_total_with_bane": SummaryCard("Final + Bane"),
        }
        order = list(self.cards.values())
        for index, card in enumerate(order):
            grid.addWidget(card, index // 4, index % 4)
        return wrapper

    def _build_mod_section(self) -> QWidget:
        box = QGroupBox("Mods")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 18, 14, 14)

        self.damage_scope_notice = QLabel(
            "Estimates treat each exported damage row as one non-critical hit. Some rows combine "
            "separate direct and radial hits; falloff and separate quantization are not modeled. "
            "Only modeled damage effects are included."
        )
        self.damage_scope_notice.setWordWrap(True)
        self.damage_scope_notice.setStyleSheet("color: #91a3c4;")
        layout.addWidget(self.damage_scope_notice)
        self.compatibility_notice = QLabel(
            "Compatibility filtering is partial; verify conflicts, mod capacity and other restrictions."
        )
        self.compatibility_notice.setWordWrap(True)
        self.compatibility_notice.setStyleSheet("color: #e4bd78;")
        layout.addWidget(self.compatibility_notice)

        filter_row = QHBoxLayout()
        self.mod_search_edit = QLineEdit()
        self.mod_search_edit.setPlaceholderText("Filter mods by name or effect...")
        self.mod_category_combo = QComboBox()
        self.mod_category_combo.addItems([
            "All Mods",
            "Elemental",
            "Base Damage",
            "Physical",
            "Faction",
            "Other",
        ])
        filter_row.addWidget(QLabel("Filter"))
        filter_row.addWidget(self.mod_search_edit, 1)
        filter_row.addWidget(QLabel("Type"))
        filter_row.addWidget(self.mod_category_combo)
        layout.addLayout(filter_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for index in range(MOD_SLOT_COUNT):
            slot = ModSlotWidget(index + 1)
            self.mod_slots.append(slot)
            grid.addWidget(slot, index // 2, index % 2)
        layout.addLayout(grid)

        button_row = QHBoxLayout()
        self.save_build_button = QPushButton("Save Build")
        self.load_build_button = QPushButton("Load Build")
        self.compare_build_button = QPushButton("Compare Build")
        self.clear_mods_button = QPushButton("Clear All Mods")
        self.recalc_button = QPushButton("Recalculate")
        button_row.addWidget(self.save_build_button)
        button_row.addWidget(self.load_build_button)
        button_row.addWidget(self.compare_build_button)
        button_row.addStretch(1)
        button_row.addWidget(self.clear_mods_button)
        button_row.addWidget(self.recalc_button)
        layout.addLayout(button_row)
        return box

    def _build_tables_section(self) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.aggregated_table = self._create_table(["Stat", "Total Mod"])
        self.hud_table = self._create_table(["Damage Type", "HUD Value"])
        self.final_table = self._create_table(["Damage Type", "Final Value"])

        layout.addWidget(self._wrap_table("Aggregated Mod Totals", self.aggregated_table), 1)
        layout.addWidget(self._wrap_table("HUD / Mod Screen Damage", self.hud_table), 1)
        layout.addWidget(self._wrap_table("Final Damage", self.final_table), 1)
        return wrapper

    def _wrap_table(self, title: str, table: QTableWidget) -> QWidget:
        box = QGroupBox(title)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        inner = QVBoxLayout(box)
        inner.setContentsMargins(10, 16, 10, 10)
        inner.setSpacing(0)
        inner.addWidget(table, 0, Qt.AlignmentFlag.AlignTop)
        return box

    def _create_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setWordWrap(False)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setMinimumHeight(220)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return table

    def _connect_events(self) -> None:
        self.search_edit.textChanged.connect(self.refresh_weapon_list)
        self.weapon_list.currentItemChanged.connect(self.on_weapon_selected)
        self.enemy_preset_combo.currentTextChanged.connect(self.apply_enemy_preset)
        self.faction_combo.currentTextChanged.connect(self.recalculate)
        self.lich_combo.currentTextChanged.connect(self.recalculate)
        self.valence_edit.textChanged.connect(self.recalculate)
        self.armor_edit.textChanged.connect(self.recalculate)
        self.recalc_button.clicked.connect(self.recalculate)
        self.clear_mods_button.clicked.connect(self.clear_all_mods)
        self.mod_search_edit.textChanged.connect(self.apply_mod_filters)
        self.mod_category_combo.currentTextChanged.connect(self.apply_mod_filters)
        self.settings_button.clicked.connect(self.open_settings)
        self.faq_button.clicked.connect(self.open_faq)
        self.save_build_button.clicked.connect(self.save_build)
        self.load_build_button.clicked.connect(self.load_build)
        self.compare_build_button.clicked.connect(self.compare_build)

        for slot in self.mod_slots:
            slot.mod_combo.currentIndexChanged.connect(self.on_mod_changed)
            slot.rank_spin.valueChanged.connect(self.recalculate)
            slot.clear_button.clicked.connect(self._make_clear_slot_callback(slot))

    def open_settings(self) -> None:
        SettingsDialog(self).exec()

    def open_faq(self) -> None:
        FAQDialog(self).exec()

    def _make_clear_slot_callback(self, slot: ModSlotWidget):
        def callback() -> None:
            slot.clear_selection()
            self.recalculate()

        return callback

    def rebuild_database(self) -> None:
        build_database(
            db_path=self.paths["db"],
            cleaned_weapons_zip_path=self.paths["source"] / "ExportWeapons_en_Cleaned.zip",
            cleaned_upgrades_zip_path=self.paths["source"] / "ExportKeys_en_Cleaned.zip",
            spreadsheet_xlsx_path=(self.paths["source"] / "Warframe-Damage-Calculator_v2.xlsx"),
        )
        self.refresh_weapon_list()
        if self.selected_weapon is not None:
            refreshed = self.weapon_repository.get_weapon(self.selected_weapon.weapon)
            if refreshed is not None:
                self.selected_weapon = refreshed
                self._show_weapon_summary(refreshed)
                self._load_mod_options_for_weapon(refreshed)
                self.recalculate()

    def refresh_weapon_list(self) -> None:
        # The sidebar is the catalogue browser, so it asks for every weapon: the
        # default search cap would silently hide everything sorted after the
        # first 250 names (Kuva/Tenet weapons, most Primes, ...).
        weapons = self.weapon_repository.search_weapons(self.search_edit.text(), limit=None)
        current_name = self.weapon_list.currentItem().text() if self.weapon_list.currentItem() else None

        self.weapon_list.blockSignals(True)
        self.weapon_list.clear()
        for weapon_name in weapons:
            self.weapon_list.addItem(weapon_name)
        self.weapon_list.blockSignals(False)

        if current_name:
            matches = self.weapon_list.findItems(current_name, Qt.MatchFlag.MatchExactly)
            if matches:
                self.weapon_list.setCurrentItem(matches[0])
        elif self.weapon_list.count() > 0:
            self.weapon_list.setCurrentRow(0)

    def on_weapon_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return

        weapon = self.weapon_repository.get_weapon(current.text())
        if weapon is None:
            return

        self.selected_weapon = weapon
        self._show_weapon_summary(weapon)
        self._load_mod_options_for_weapon(weapon)
        self.recalculate()

    def _show_weapon_summary(self, weapon: Weapon) -> None:
        lines = [
            weapon.weapon,
            f"Category: {weapon.product_category or weapon.slot_group}",
            f"Weapon Family: {weapon.slot_group}",
            f"Base Damage: {weapon.dmg:.6f}",
            f"Fire Rate: {weapon.firerate:.6f}",
            f"Multishot: {weapon.multi:.6f}",
            f"Crit Chance: {weapon.critchan:.6f}",
            f"Crit Multiplier: {weapon.critmult:.6f}",
            f"Status Chance: {weapon.statchan:.6f}",
            "",
            "Base Damage Types:",
        ]
        for damage_type in DAMAGE_TYPES:
            value = weapon.damage_for(damage_type)
            if value:
                lines.append(f"  {self.display_name(damage_type)}: {value:.6f}")
        self.weapon_summary.setPlainText("\n".join(lines))

    def _compatible_mod_options(self, weapon: Weapon) -> list[Mod]:
        raw_mods = self.mod_repository.list_mods_for_slot(weapon.slot_group)
        deduped: dict[tuple[str, str], Mod] = {}
        for mod in raw_mods:
            if not self.mod_compatibility.allows(weapon, mod):
                continue
            # Do not collapse a user-defined mod into an official entry with
            # the same visible name/summary; saved builds use unique IDs.
            identity = ("official:" + mod.name.strip().lower() if mod.unique_name.startswith("/Lotus/")
                        else "custom:" + mod.unique_name)
            key = (identity, (mod.effect_summary or "").strip().lower())
            existing = deduped.get(key)
            if existing is None or mod.fusion_limit > existing.fusion_limit:
                deduped[key] = mod
        return sorted(deduped.values(), key=lambda mod: (mod.name.lower(), mod.fusion_limit))

    def _load_mod_options_for_weapon(self, weapon: Weapon) -> None:
        self.available_mods = self._compatible_mod_options(weapon)
        self.compatibility_notice.setText(self.mod_compatibility.notice(weapon))
        self.apply_mod_filters()

    def apply_mod_filters(self) -> None:
        if not self.available_mods:
            changed = False
            for slot in self.mod_slots:
                changed = slot.set_mod_options([]) or changed
            if changed:
                self.recalculate()
            return

        search_text = self.mod_search_edit.text().strip().lower()
        category = self.mod_category_combo.currentText()
        filtered = []
        for mod in self.available_mods:
            haystack = " ".join([mod.name, mod.effect_summary, mod.description]).lower()
            if search_text and search_text not in haystack:
                continue
            if not self._mod_matches_category(mod, category):
                continue
            filtered.append(mod)

        # Filtering the picker must not silently unequip mods that no longer
        # match the search. Keep each equipped mod in its own slot's options,
        # provided it is still compatible with the selected weapon.
        available_ids = {mod.unique_name for mod in self.available_mods}
        filtered_ids = {mod.unique_name for mod in filtered}
        changed = False
        for slot in self.mod_slots:
            selected = slot.current_mod
            options = filtered
            if selected and selected.unique_name in available_ids and selected.unique_name not in filtered_ids:
                options = [*filtered, selected]
            changed = slot.set_mod_options(options) or changed
        if changed:
            self.recalculate()

    def _mod_matches_category(self, mod: Mod, category: str) -> bool:
        summary = f"{mod.effect_summary} {mod.description}".lower()
        if category == "All Mods":
            return True
        if category == "Elemental":
            return any(term in summary for term in ("heat", "cold", "electric", "electricity", "toxin", "blast", "radiation", "gas", "magnetic", "viral", "corrosive"))
        if category == "Base Damage":
            return "damage" in summary and not any(term in summary for term in ("damage to grineer", "damage to corpus", "damage to infested", "damage to corrupted", "impact", "puncture", "slash"))
        if category == "Physical":
            return any(term in summary for term in ("impact", "puncture", "slash"))
        if category == "Faction":
            return any(term in summary for term in ("damage to grineer", "damage to corpus", "damage to infested", "damage to corrupted"))
        if category == "Other":
            return not self._mod_matches_category(mod, "Elemental") and not self._mod_matches_category(mod, "Base Damage") and not self._mod_matches_category(mod, "Physical") and not self._mod_matches_category(mod, "Faction")
        return True

    def on_mod_changed(self) -> None:
        for slot in self.mod_slots:
            unique_name = slot.selected_unique_name()
            if not unique_name:
                slot.current_mod = None
                slot.summary_label.setText("No mod selected")
                slot.rank_spin.setMaximum(10)
                continue

            mod = slot.mod_lookup.get(unique_name)
            if mod is None:
                mod = self.mod_repository.get_mod(unique_name)
            slot.current_mod = mod
            if mod is not None:
                slot.rank_spin.setMaximum(max(mod.fusion_limit, 0))
                if slot.rank_spin.value() > slot.rank_spin.maximum():
                    slot.rank_spin.setValue(slot.rank_spin.maximum())
                slot._refresh_summary()
        self.recalculate()

    def clear_all_mods(self) -> None:
        # Do not recalculate partial intermediate builds as each slot clears.
        states = [(slot.mod_combo.blockSignals(True), slot.rank_spin.blockSignals(True))
                  for slot in self.mod_slots]
        try:
            for slot in self.mod_slots:
                slot.clear_selection()
        finally:
            for slot, (combo_blocked, rank_blocked) in zip(
                    self.mod_slots, states, strict=True):
                slot.mod_combo.blockSignals(combo_blocked)
                slot.rank_spin.blockSignals(rank_blocked)
        self.recalculate()

    def recalculate(self) -> None:
        if self.selected_weapon is None:
            return

        try:
            equipped_mods = self._build_equipped_mods()
            inputs = CalculationInputs(
                weapon_name=self.selected_weapon.weapon,
                faction=self.faction_combo.currentText() or "Grineer",
                armor_value=self.safe_float(self.armor_edit.text()),
                lich_element=self.lich_combo.currentText(),
                valence_base=self.safe_float(self.valence_edit.text()),
                equipped_mods=equipped_mods,
            )
            results = self.calculator.calculate(self.selected_weapon, inputs)
            self.current_results = results
            self._update_results(results)
        except Exception as exc:
            QMessageBox.critical(self, "Calculation error", str(exc))

    def _build_equipped_mods(self) -> list[EquippedMod]:
        selections = [(slot.current_mod.unique_name, slot.rank_spin.value())
                      for slot in self.mod_slots if slot.current_mod is not None]
        effects_by_selection = self.mod_repository.fetch_ranked_effects_many(selections)
        equipped: list[EquippedMod] = []
        for slot in self.mod_slots:
            if slot.current_mod is None:
                equipped.append(EquippedMod())
                continue
            rank = slot.rank_spin.value()
            effects = effects_by_selection[(slot.current_mod.unique_name, rank)]
            equipped.append(EquippedMod(mod=slot.current_mod, rank=rank, effects=effects))
        return equipped

    def _update_results(self, results) -> None:
        self.cards["base_damage"].set_value(f"{results.base_weapon_damage:.6f}")
        self.cards["weapon_total_damage"].set_value(f"{results.weapon_total_damage:.6f}")
        self.cards["quanta"].set_value(f"{results.quanta:.6f}")
        self.cards["valence_multiplier"].set_value(f"{results.valence_multiplier:.10f}")
        self.cards["hud_total"].set_value(f"{results.hud_total:.6f}")
        self.cards["hud_total_with_bane"].set_value(f"{results.hud_total_with_bane:.6f}")
        self.cards["final_total"].set_value(f"{results.final_total:.6f}")
        self.cards["final_total_with_bane"].set_value(f"{results.final_total_with_bane:.6f}")

        self.fill_table(self.aggregated_table, results.rows_for_mods(), label_column=True)
        self.fill_table(self.hud_table, results.rows_for_hud(), label_column=True)
        self.fill_table(self.final_table, results.rows_for_final(), label_column=True)

    def fill_table(self, table: QTableWidget, rows: list[tuple[str, float]], label_column: bool = False) -> None:
        table.setRowCount(len(rows))
        for row_index, (name, value) in enumerate(rows):
            display = self.display_name(name) if label_column else name
            item_name = QTableWidgetItem(display)
            item_value = QTableWidgetItem(f"{value:.6f}")
            item_value.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_index, 0, item_name)
            table.setItem(row_index, 1, item_value)
        table.resizeRowsToContents()
        extra_height = table.horizontalHeader().height() + 8
        for row_index in range(table.rowCount()):
            extra_height += table.rowHeight(row_index)
        table.setFixedHeight(max(extra_height + 8, 220))

    def save_build(self) -> None:
        if self.selected_weapon is None:
            QMessageBox.information(self, "Save Build", "Pick a weapon first.")
            return
        default_path = self.paths["builds"] / f"{self.selected_weapon.weapon.replace('/', '-').replace(' ', '_')}.json"
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Build", str(default_path), "JSON Files (*.json)")
        if not file_name:
            return
        payload = {
            "weapon": self.selected_weapon.weapon,
            "inputs": {
                "lich_element": self.lich_combo.currentText(),
                "valence_base": self.valence_edit.text(),
                "faction": self.faction_combo.currentText(),
                "armor": self.armor_edit.text(),
            },
            "mods": [
                {
                    "unique_name": slot.current_mod.unique_name if slot.current_mod else None,
                    "rank": slot.rank_spin.value(),
                }
                for slot in self.mod_slots
            ],
        }
        target = Path(file_name)
        temporary: Path | None = None
        try:
            # Do not truncate an existing build before the new JSON is ready.
            descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(temporary, target)
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Save Build", f"Could not save the build: {exc}")
            return
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # Do not hide the original save error.
        QMessageBox.information(self, "Save Build", "Build saved.")

    def _read_build(self, file_name: str, action: str) -> tuple[Weapon, dict[str, str], list[tuple[Mod | None, int]]] | None:
        """Validate a saved build before mutating the UI or comparing results."""
        try:
            payload = json.loads(Path(file_name).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("The build must be a JSON object.")
            weapon_name = payload.get("weapon")
            if not isinstance(weapon_name, str) or not weapon_name.strip():
                raise ValueError("The build does not include a weapon name.")
            weapon = self.weapon_repository.get_weapon(weapon_name)
            if weapon is None:
                raise ValueError(f"Weapon not found in the database: {weapon_name}")

            raw_inputs = payload.get("inputs")
            if raw_inputs is None:
                raw_inputs = {}
            if not isinstance(raw_inputs, dict):
                raise ValueError("Build inputs must be a JSON object.")
            faction = str(raw_inputs.get("faction") or "Grineer")
            if faction == "Zairman":
                faction = "Zariman"  # Compatibility with older saved builds.
            if faction not in FACTION_MULTIPLIERS:
                raise ValueError(f"Unknown faction: {faction}")
            element = str(raw_inputs.get("lich_element") or "")
            if element and element not in DAMAGE_TYPES:
                raise ValueError(f"Unknown adversary element: {element}")
            inputs = {"faction": faction, "lich_element": element}
            for key in ("armor", "valence_base"):
                text = str(raw_inputs.get(key) or "0")
                if not math.isfinite(float(text)):
                    raise ValueError(f"{key} must be a finite number.")
                inputs[key] = text

            raw_mods = payload.get("mods")
            if raw_mods is None:
                raw_mods = []
            if not isinstance(raw_mods, list) or len(raw_mods) > len(self.mod_slots):
                raise ValueError(f"The build must contain at most {len(self.mod_slots)} mod slots.")
            compatible = {mod.unique_name: mod for mod in self._compatible_mod_options(weapon)}
            mods: list[tuple[Mod | None, int]] = []
            for row in raw_mods:
                if not isinstance(row, dict):
                    raise ValueError("Each mod slot must be a JSON object.")
                unique_name = row.get("unique_name")
                if unique_name is not None and not isinstance(unique_name, str):
                    raise ValueError("A mod identifier must be a string or null.")
                raw_rank = row.get("rank", 0)
                if isinstance(raw_rank, bool) or not isinstance(raw_rank, (int, str)):
                    raise ValueError("A mod rank must be an integer.")
                rank = int(raw_rank)
                mod = compatible.get(unique_name) if unique_name else None
                if unique_name and mod is None:
                    raise ValueError(f"Mod is unavailable or incompatible with {weapon_name}: {unique_name}")
                if rank < 0 or (mod is not None and rank > mod.fusion_limit):
                    raise ValueError(f"Invalid rank {rank} for {unique_name or 'empty slot'}.")
                mods.append((mod, rank))
            return weapon, inputs, mods
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, action, f"Could not read the build: {exc}")
            return None

    def load_build(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Build", str(self.paths["builds"]), "JSON Files (*.json)")
        if not file_name:
            return
        loaded = self._read_build(file_name, "Load Build")
        if loaded is None:
            return
        weapon, inputs, mod_rows = loaded

        # Reset filters before selecting saved mods, which may otherwise be
        # hidden. The exact weapon is known to exist from the preflight.
        self.mod_search_edit.clear()
        self.mod_category_combo.setCurrentText("All Mods")
        self.search_edit.setText(weapon.weapon)
        matches = self.weapon_list.findItems(weapon.weapon, Qt.MatchFlag.MatchExactly)
        if not matches:
            # An exact match can be outside a search result's limit.
            self.weapon_list.addItem(weapon.weapon)
            matches = self.weapon_list.findItems(weapon.weapon, Qt.MatchFlag.MatchExactly)
        self.weapon_list.setCurrentItem(matches[0])
        # Refresh even when the weapon was already selected: the database may
        # have been rebuilt since the current picker options were populated.
        self.selected_weapon = weapon
        self._show_weapon_summary(weapon)
        self._load_mod_options_for_weapon(weapon)

        self.lich_combo.setCurrentText(inputs["lich_element"])
        self.valence_edit.setText(inputs["valence_base"])
        self.faction_combo.setCurrentText(inputs["faction"])
        self.armor_edit.setText(inputs["armor"])

        # Older files may contain fewer than eight rows. Missing rows mean
        # empty slots, not "keep whatever the current build had equipped".
        for index, slot in enumerate(self.mod_slots):
            mod, rank = mod_rows[index] if index < len(mod_rows) else (None, 0)
            if mod is None:
                slot.clear_selection()
                continue
            slot.mod_combo.setCurrentIndex(slot.mod_combo.findData(mod.unique_name))
            slot.rank_spin.setValue(rank)
        self.on_mod_changed()
        QMessageBox.information(self, "Load Build", "Build loaded.")

    def apply_enemy_preset(self) -> None:
        preset_name = self.enemy_preset_combo.currentText()
        faction, armor = ENEMY_PRESETS.get(preset_name, (None, None))
        if faction:
            self.faction_combo.setCurrentText(faction)
        if armor is not None:
            self.armor_edit.setText(str(armor))
        if preset_name == "Custom":
            self.recalculate()

    def run_data_pipeline(self, prefer_online: bool, log_callback: Callable[[str], None] | None = None) -> dict[str, str | Path | None]:
        updater = WarframeDataUpdater()
        if log_callback:
            if prefer_online:
                log_callback("Trying to download fresh data from DE. If that fails, WDC will fall back to saved local exports.")
            else:
                log_callback("Using saved local export data (no download).")
        outputs = updater.update_and_build_database(
            db_path=self.paths["db"],
            cleaned_weapons_zip_path=self.paths["source"] / "ExportWeapons_en_Cleaned.zip",
            cleaned_upgrades_zip_path=self.paths["source"] / "ExportKeys_en_Cleaned.zip",
            spreadsheet_xlsx_path=(self.paths["source"] / "Warframe-Damage-Calculator_v2.xlsx"),
            allow_bundled_fallback=prefer_online,
        )
        self.refresh_weapon_list()
        if self.selected_weapon is not None:
            refreshed = self.weapon_repository.get_weapon(self.selected_weapon.weapon)
            if refreshed is not None:
                self.selected_weapon = refreshed
                self._show_weapon_summary(refreshed)
                self._load_mod_options_for_weapon(refreshed)
                self.recalculate()
        return outputs

    def compare_build(self) -> None:
        if self.selected_weapon is None or self.current_results is None:
            QMessageBox.information(self, "Compare Build", "Pick a weapon and calculate a build first.")
            return
        file_name, _ = QFileDialog.getOpenFileName(self, "Compare Build", str(self.paths["builds"]), "JSON Files (*.json)")
        if not file_name:
            return
        loaded = self._read_build(file_name, "Compare Build")
        if loaded is None:
            return
        weapon, inputs, mod_rows = loaded
        selections = [(mod.unique_name, rank) for mod, rank in mod_rows if mod is not None]
        effects_by_selection = self.mod_repository.fetch_ranked_effects_many(selections)
        equipped_mods: list[EquippedMod] = []
        for mod, rank in mod_rows:
            if mod is None:
                equipped_mods.append(EquippedMod())
                continue
            effects = effects_by_selection[(mod.unique_name, rank)]
            equipped_mods.append(EquippedMod(mod=mod, rank=rank, effects=effects))

        compare_inputs = CalculationInputs(
            weapon_name=weapon.weapon,
            faction=inputs["faction"],
            armor_value=self.safe_float(inputs["armor"]),
            lich_element=inputs["lich_element"],
            valence_base=self.safe_float(inputs["valence_base"]),
            equipped_mods=equipped_mods,
        )
        compare_results = self.calculator.calculate(weapon, compare_inputs)

        current_summary = [
            ("Weapon", self.selected_weapon.weapon),
            ("Faction", self.faction_combo.currentText()),
            ("Armor", self.armor_edit.text()),
            ("HUD Total", f"{self.current_results.hud_total:.6f}"),
            ("HUD + Faction", f"{self.current_results.hud_total_with_bane:.6f}"),
            ("Final Total", f"{self.current_results.final_total:.6f}"),
            ("Final + Faction", f"{self.current_results.final_total_with_bane:.6f}"),
            ("Quanta", f"{self.current_results.quanta:.6f}"),
            ("True Valence", f"{self.current_results.valence_multiplier:.10f}"),
        ]
        compare_summary = [
            ("Weapon", weapon.weapon),
            ("Faction", compare_inputs.faction),
            ("Armor", str(compare_inputs.armor_value)),
            ("HUD Total", f"{compare_results.hud_total:.6f}"),
            ("HUD + Faction", f"{compare_results.hud_total_with_bane:.6f}"),
            ("Final Total", f"{compare_results.final_total:.6f}"),
            ("Final + Faction", f"{compare_results.final_total_with_bane:.6f}"),
            ("Quanta", f"{compare_results.quanta:.6f}"),
            ("True Valence", f"{compare_results.valence_multiplier:.10f}"),
        ]

        CompareBuildDialog(current_summary, compare_summary, Path(file_name).name, self).exec()

    def display_name(self, code: str) -> str:
        return DISPLAY_NAMES.get(code, code.title())

    def safe_float(self, value: str) -> float:
        try:
            parsed = float(value.strip()) if value.strip() else 0.0
            return parsed if math.isfinite(parsed) else 0.0
        except ValueError:
            return 0.0


def build_application(db_path) -> QApplication:
    app = QApplication.instance() or QApplication([])
    icon_path = Path(__file__).resolve().parents[1] / "wdc.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(DARK_STYLESHEET)
    return app
