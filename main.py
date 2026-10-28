from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox

from gui.app import DamageCalculatorWindow, build_application
from modules.app_paths import ensure_app_dirs, seed_source_files
from modules.database import ModRepository, WeaponRepository
from modules.database_migration import DatabaseMigrationError, MigrationResult, migrate_database
from modules.database_revision import UnsupportedDatabaseRevision


def database_is_ready(db_path: Path) -> bool:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False
    try:
        with closing(sqlite3.connect(db_path)) as connection:
            row = connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='weapons'").fetchone()
            if not row or int(row[0]) == 0:
                return False
            count_row = connection.execute("SELECT COUNT(*) FROM weapons").fetchone()
            return bool(count_row and int(count_row[0]) > 0)
    except Exception:
        return False


def maybe_bootstrap_database(window: DamageCalculatorWindow) -> None:
    if database_is_ready(window.paths["db"]):
        return

    message = QMessageBox(window)
    message.setWindowTitle("Build Initial Data")
    message.setIcon(QMessageBox.Icon.Question)
    message.setText(
        "WDC needs its initial data before weapon calculations can be used. "
        "Build it now using fresh DE data when available, with saved local exports as a fallback?"
    )
    message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    message.setDefaultButton(QMessageBox.StandardButton.Yes)

    if message.exec() != QMessageBox.StandardButton.Yes:
        return

    try:
        outputs = window.run_data_pipeline(prefer_online=True)
        details = [
            f"Data source: {outputs['source_mode']}",
            f"Manifest decode path: {outputs['lzma_method']}",
            f"Database: {outputs['db_path']}",
        ]
        if outputs.get("backup_path"):
            details.append(f"Previous database backup: {outputs['backup_path']}")
        if outputs.get("refresh_error"):
            details.append(f"Fresh download failed, so WDC used saved local exports: {outputs['refresh_error']}")
        QMessageBox.information(window, "Initial Data Ready", "\n".join(details))
    except Exception as exc:
        QMessageBox.critical(
            window,
            "Initial Data Failed",
            "WDC could not build its initial data. Open Settings later to retry with fresh data or saved local exports.\n\n" + str(exc),
        )


def migrate_existing_database(paths: dict[str, Path]) -> MigrationResult:
    """Inspect/upgrade any existing database before repositories read it."""
    return migrate_database(
        paths["db"],
        paths["source"] / "ExportWeapons_en_Cleaned.zip",
        paths["source"] / "ExportKeys_en_Cleaned.zip",
        paths["source"] / "Warframe-Damage-Calculator_v2.xlsx",
    )


def main() -> int:
    project_root = Path(__file__).resolve().parent
    seed_source_files(project_root)
    paths = ensure_app_dirs()

    app = build_application(paths["db"])
    try:
        migration_result = migrate_existing_database(paths)
    except (DatabaseMigrationError, UnsupportedDatabaseRevision) as exc:
        # Do not construct repositories or show calculations based on stale,
        # corrupt, or newer-incompatible data.
        QMessageBox.critical(
            None, "Database Upgrade Not Completed",
            "WDC could not safely open or upgrade the existing database. No migration changes "
            "were committed. Check the saved source files, restore a backup, or use a compatible "
            "app version before retrying.\n\n"
            f"Database: {paths['db']}\nSaved sources: {paths['source']}\n\n{exc}",
        )
        return 1

    weapon_repository = WeaponRepository(paths["db"])
    mod_repository = ModRepository(paths["db"])
    window = DamageCalculatorWindow(weapon_repository, mod_repository, project_root=project_root)
    window.show()
    if migration_result.status == "migrated":
        QMessageBox.information(
            window, "Database Upgraded",
            "WDC updated the existing database from your saved export files without a download. "
            "A backup of the previous database is available at:\n\n"
            + str(migration_result.backup_path),
        )
    maybe_bootstrap_database(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
