from __future__ import annotations

import json
import lzma
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

import requests

from .app_paths import ensure_app_dirs
from .database_revision import require_supported_revision
from .export_safety import (
    UnfinishedExportPublication,
    _require_complete_exports_unlocked,
    export_lock,
    require_complete_exports,
)

KEY_URL = "https://origin.warframe.com/PublicExport/index_en.txt.lzma"
DATA_URL = "https://content.warframe.com/PublicExport/Manifest/"


class DataRefreshError(RuntimeError):
    pass


class DataRefreshRecoveryError(DataRefreshError):
    """Publication failed and an old export could not be restored.

    Do not fall back to the potentially mixed pair; the exception identifies
    a retained staging directory containing copies of the original files.
    """


class WarframeDataUpdater:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout
        self.paths = ensure_app_dirs()

    def refresh(self) -> dict[str, str | Path]:
        source = self.paths["source"]
        weapons_zip = source / "ExportWeapons_en_Cleaned.zip"
        upgrades_zip = source / "ExportKeys_en_Cleaned.zip"
        require_complete_exports(weapons_zip, upgrades_zip)
        # Never clean the entire shared temp directory: it can contain other
        # sessions' files. Each refresh owns and removes only its scratch dir.
        with tempfile.TemporaryDirectory(prefix="wdc-refresh-", dir=self.paths["temp"]) as scratch:
            temp = Path(scratch)
            lzma_path = temp / "index_en.txt.lzma"
            index_path = temp / "index_en.txt"
            self._download(KEY_URL, lzma_path)
            lzma_method = self._expand_lzma(lzma_path, temp)

            manifest_entries = index_path.read_text(encoding="utf-8").splitlines()
            needed: dict[str, str | None] = {
                "ExportWeapons_en.json": None,
                "ExportUpgrades_en.json": None,
            }
            for entry in manifest_entries:
                for target in needed:
                    if entry.startswith(target + "!"):
                        needed[target] = entry

            missing = [name for name, entry in needed.items() if not entry]
            if missing:
                raise DataRefreshError(f"Could not find these files in the manifest: {', '.join(missing)}")

            downloaded: dict[str, Path] = {}
            for logical_name, manifest_name in needed.items():
                target_path = temp / logical_name
                self._download(DATA_URL + str(manifest_name), target_path)
                downloaded[logical_name] = target_path

            weapons_clean = self._clean_json(downloaded["ExportWeapons_en.json"])
            upgrades_clean = self._clean_json(downloaded["ExportUpgrades_en.json"])

            # Stage on the destination filesystem so each os.replace is atomic.
            stage = Path(tempfile.mkdtemp(prefix=".wdc-refresh-", dir=source))
            try:
                staged_weapons = stage / weapons_zip.name
                staged_upgrades = stage / upgrades_zip.name
                self._write_zip(staged_weapons, "ExportWeapons_en_Cleaned.json", weapons_clean)
                self._write_zip(staged_upgrades, "ExportUpgrades_en_Cleaned.json", upgrades_clean)
                self._validate_exports(staged_weapons, staged_upgrades)
                self._publish_exports(((staged_weapons, weapons_zip),
                                       (staged_upgrades, upgrades_zip)), stage)
            finally:
                # An outstanding marker means publication may be incomplete;
                # preserve both it and the old copies, even after interruption.
                if not (stage / "PUBLISHING.json").exists():
                    shutil.rmtree(stage, ignore_errors=True)

        return {
            "weapons_zip": weapons_zip,
            "upgrades_zip": upgrades_zip,
            "lzma_method": lzma_method,
        }

    @staticmethod
    def _validate_exports(weapons_zip: Path, upgrades_zip: Path) -> None:
        """Check parsed data and SQLite constraints before touching saved exports."""
        from .importer import apply_import_payload, create_schema, load_import_payload

        payload = load_import_payload(weapons_zip, upgrades_zip)
        with closing(sqlite3.connect(":memory:")) as connection:
            create_schema(connection)
            apply_import_payload(connection, payload)

    @staticmethod
    def _publish_exports(archives: tuple[tuple[Path, Path], ...], stage: Path) -> None:
        """Publish a validated pair under the shared process-level export lock.

        Two filesystem entries cannot be replaced as one atomic operation, so
        readers and every publisher cooperate through a lock spanning the full
        publication and rollback. Copies and a publication marker still allow
        a later process to detect and manually recover a crash mid-publication.
        """
        targets = tuple(target for _, target in archives)
        with export_lock(*targets):
            _require_complete_exports_unlocked(*targets)
            WarframeDataUpdater._publish_exports_locked(archives, stage)

    @staticmethod
    def _publish_exports_locked(archives: tuple[tuple[Path, Path], ...], stage: Path) -> None:
        """Perform publication with the parent folder lock already held."""
        backups: dict[Path, Path | None] = {}
        for _, target in archives:
            if target.exists():
                backup = stage / ("previous-" + target.name)
                shutil.copy2(target, backup)
                backups[target] = backup
            else:
                backups[target] = None

        marker = stage / "PUBLISHING.json"
        with marker.open("x", encoding="utf-8") as handle:
            json.dump({"archives": [
                {"destination": target.name,
                 "previous_copy": (prior.name if (prior := backups[target]) else None)}
                for _, target in archives
            ]}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        published: list[Path] = []
        try:
            for staged, target in archives:
                # Record intent before the system call: an interrupt can arrive
                # after replace succeeds but before Python regains control.
                published.append(target)
                os.replace(staged, target)
        except BaseException as exc:
            failures = []
            for target in reversed(published):
                try:
                    prior = backups[target]
                    if prior is None:
                        target.unlink(missing_ok=True)
                    else:
                        # Copy to a new file and atomically restore it while
                        # retaining the original backup if restoration fails.
                        restore = stage / ("restore-" + target.name)
                        shutil.copy2(prior, restore)
                        os.replace(restore, target)
                except OSError as rollback_error:
                    failures.append(f"{target}: {rollback_error}")
            if failures:
                raise DataRefreshRecoveryError(
                    "Could not restore saved exports after a failed refresh. "
                    f"Do not rebuild from the current pair. Original copies are in {stage}. "
                    f"Publication error: {exc}. Restore errors: {'; '.join(failures)}"
                ) from exc
            marker.unlink()
            if not isinstance(exc, Exception):
                raise
            raise DataRefreshError(f"Could not publish fresh exports; previous files were restored: {exc}") from exc
        marker.unlink()

    def update_and_build_database(
        self,
        db_path: str | Path,
        cleaned_weapons_zip_path: str | Path,
        cleaned_upgrades_zip_path: str | Path,
        spreadsheet_xlsx_path: str | Path | None = None,
        allow_bundled_fallback: bool = True,
    ) -> dict[str, str | Path | None]:
        from .importer import build_database

        target = Path(db_path)
        if target.is_file() and target.stat().st_size:
            # Do this before refreshing the exports: an older app must not
            # overwrite either a future database or its saved source files.
            with closing(sqlite3.connect(target.resolve().as_uri() + "?mode=rw", uri=True)) as connection:
                require_supported_revision(connection)

        weapons_zip = Path(cleaned_weapons_zip_path)
        upgrades_zip = Path(cleaned_upgrades_zip_path)
        spreadsheet_path = Path(spreadsheet_xlsx_path) if spreadsheet_xlsx_path else None

        refresh_error: str | None = None
        source_mode = "saved local exports"
        lzma_method = "Not applicable (saved local exports)"

        if allow_bundled_fallback:
            try:
                refresh_outputs = self.refresh()
                weapons_zip = Path(refresh_outputs["weapons_zip"])
                upgrades_zip = Path(refresh_outputs["upgrades_zip"])
                lzma_method = str(refresh_outputs.get("lzma_method") or lzma_method)
                source_mode = "fresh DE data"
            except (DataRefreshRecoveryError, UnfinishedExportPublication):
                raise  # The saved pair may be mixed; falling back would be unsafe.
            except Exception as exc:
                # A failure while removing the marker is also an unsafe state.
                require_complete_exports(weapons_zip, upgrades_zip)
                refresh_error = str(exc)
                if not weapons_zip.exists() or not upgrades_zip.exists():
                    raise DataRefreshError(
                        "WDC could not download fresh data from DE, and saved local exports were not available."
                    ) from exc
        else:
            if not weapons_zip.exists() or not upgrades_zip.exists():
                raise DataRefreshError(
                    "Saved local exports were not found. WDC could not rebuild the database offline."
                )

        backup_path = build_database(
            db_path=db_path,
            cleaned_weapons_zip_path=weapons_zip,
            cleaned_upgrades_zip_path=upgrades_zip,
            spreadsheet_xlsx_path=spreadsheet_path,
        )

        return {
            "db_path": Path(db_path),
            "backup_path": backup_path,
            "weapons_zip": weapons_zip,
            "upgrades_zip": upgrades_zip,
            "source_mode": source_mode,
            "lzma_method": lzma_method,
            "refresh_error": refresh_error,
        }

    def _download(self, url: str, target_path: Path, min_expected_size: int = 0) -> int:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

        last_error: Exception | None = None
        for _ in range(3):
            try:
                total_bytes = 0
                with requests.get(url, headers=headers, stream=True, timeout=self.timeout) as response:
                    response.raise_for_status()
                    expected_length_header = response.headers.get("Content-Length")
                    expected_length = int(expected_length_header) if expected_length_header and expected_length_header.isdigit() else None

                    with open(target_path, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                handle.write(chunk)
                                total_bytes += len(chunk)

                if expected_length is not None and total_bytes != expected_length:
                    raise DataRefreshError(
                        f"Downloaded file size did not match Content-Length for {url}. "
                        f"Expected {expected_length} bytes, got {total_bytes}."
                    )

                if min_expected_size and total_bytes < min_expected_size:
                    raise DataRefreshError(
                        f"Downloaded file was too small for {url}. "
                        f"Expected at least {min_expected_size} bytes, got {total_bytes}."
                    )

                return total_bytes
            except Exception as exc:
                last_error = exc
                if target_path.exists():
                    target_path.unlink(missing_ok=True)

        raise DataRefreshError(f"Failed to download {url}: {last_error}") from last_error

    def _expand_lzma(self, input_path: Path, output_path: Path) -> str:
        compressed = input_path.read_bytes()
        try:
            decoded = self._decompress_lzma_streams(compressed)
            method = "Python LZMA"
        except lzma.LZMAError as first_error:
            # Some DE LZMA-Alone files have both a known-size header and an
            # end marker. Older liblzma builds (notably on Windows) reject
            # them. Mark the size unknown, require the end marker, and check
            # the decoded size against the original header before accepting.
            # See https://github.com/python/cpython/issues/124734.
            if (len(compressed) < 13 or compressed.startswith(b"\xfd7zXZ\x00")
                    or compressed[0] > 224):
                raise DataRefreshError(f"Could not decompress the manifest index: {first_error}") from first_error
            declared_size = int.from_bytes(compressed[5:13], "little")
            if declared_size == (1 << 64) - 1:
                raise DataRefreshError(f"Could not decompress the manifest index: {first_error}") from first_error
            repaired = compressed[:5] + b"\xff" * 8 + compressed[13:]
            try:
                decoded = self._decompress_lzma_streams(repaired)
                if len(decoded) != declared_size:
                    raise lzma.LZMAError("Decompressed size does not match the LZMA header")
            except lzma.LZMAError as exc:
                raise DataRefreshError(f"Could not decompress the manifest index: {exc}") from exc
            method = "Python LZMA with known-size header recovery"

        (output_path / "index_en.txt").write_bytes(decoded)
        return method

    def _decompress_lzma_streams(self, data: bytes) -> bytes:
        """Read complete concatenated streams; reject truncation and trailing junk."""
        if not data:
            raise lzma.LZMAError("Empty compressed data")
        results: list[bytes] = []
        while data:
            decomp = lzma.LZMADecompressor(lzma.FORMAT_AUTO)
            result = decomp.decompress(data)
            if not decomp.eof:
                raise lzma.LZMAError("Compressed data ended before the end-of-stream marker was reached")
            results.append(result)
            data = decomp.unused_data
        return b"".join(results)

    def _clean_json(self, json_path: Path) -> dict:
        # JSON's decoder already resolves duplicate object keys. Do not strip
        # whitespace around escaped newlines: it changes string contents.
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Export root must be a JSON object: {json_path}")
        return data

    def _write_zip(self, zip_path: Path, member_name: str, data: dict) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member_name, json.dumps(data, indent=4))
