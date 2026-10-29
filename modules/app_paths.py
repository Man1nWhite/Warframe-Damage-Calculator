from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from modules.constants import APP_NAME
from modules.export_safety import UnfinishedExportPublication, locked_exports

DB_NAME = "weapons.db"
EXPORT_FILES = ("ExportWeapons_en_Cleaned.zip", "ExportKeys_en_Cleaned.zip")
SOURCE_FILES = [
    *EXPORT_FILES,
    "Warframe-Damage-Calculator_v2.xlsx",
    "riven_tags.json",
    "riven_stats_average_1_2.json",
    "riven_stats_average_1_2.csv",
    "gunco_mechanic.json",
    "gunco_mechanic.csv",
    "conditionOverload.ts",
]


def get_appdata_root() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def ensure_app_dirs() -> dict[str, Path]:
    root = get_appdata_root()
    data = root / "data"
    source = root / "source"
    temp = root / "temp"
    builds = root / "builds"
    for folder in (root, data, source, temp, builds):
        folder.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "data": data,
        "source": source,
        "temp": temp,
        "builds": builds,
        "db": data / DB_NAME,
    }


def seed_source_files(project_root: Path) -> None:
    """Seed an absent export pair, never fill one half from another snapshot.

    Stage both files before publication and reuse the refresh recovery marker;
    a process interruption cannot make a partially seeded pair look complete.
    Other independent reference files may still be seeded individually.
    """
    paths = ensure_app_dirs()
    bundled_source = project_root / "source"
    source = paths["source"]
    bundled_pair = [bundled_source / name for name in EXPORT_FILES]
    targets = [source / name for name in EXPORT_FILES]
    try:
        # Serialize the existence check with refresh publication. Seeded files
        # must never fill one half of a pair being installed by another process.
        with locked_exports(*targets):
            if (not any(target.exists() for target in targets)
                    and all(path.is_file() for path in bundled_pair)):
                # Imported lazily to avoid a module-level app_paths/updater cycle.
                from .updater import WarframeDataUpdater

                stage = Path(tempfile.mkdtemp(prefix=".wdc-refresh-seed-", dir=source))
                try:
                    staged = [stage / name for name in EXPORT_FILES]
                    for original, copy in zip(bundled_pair, staged, strict=True):
                        shutil.copy2(original, copy)
                    WarframeDataUpdater._publish_exports_locked(
                        tuple(zip(staged, targets, strict=True)), stage)
                finally:
                    if not (stage / "PUBLISHING.json").exists():
                        shutil.rmtree(stage, ignore_errors=True)
    except UnfinishedExportPublication:
        # Do not touch a pair that requires manual refresh recovery.
        pass

    for file_name in SOURCE_FILES:
        if file_name in EXPORT_FILES:
            continue
        source_file = bundled_source / file_name
        target_file = source / file_name
        if source_file.exists() and not target_file.exists():
            shutil.copy2(source_file, target_file)

