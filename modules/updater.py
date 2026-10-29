from __future__ import annotations

import hashlib
import json
import lzma
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

import requests

from .app_paths import ensure_app_dirs
from .database_revision import database_has_contents, require_supported_revision
from .export_safety import (
    UnfinishedExportPublication,
    _require_complete_exports_unlocked,
    export_lock,
    locked_exports,
    require_complete_exports,
)
from .json_safety import reject_duplicate_keys

KEY_URL = "https://origin.warframe.com/PublicExport/index_en.txt.lzma"
DATA_URL = "https://content.warframe.com/PublicExport/Manifest/"
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_DECOMPRESSED_BYTES = 32 * 1024 * 1024

ExportFingerprint = tuple[int, int, int, int, str] | None


class DataRefreshError(RuntimeError):
    pass


class DataRefreshRecoveryError(DataRefreshError):
    """Export publication needs manual recovery before the pair can be used.

    Do not fall back to the potentially mixed pair; the exception identifies
    retained staging copies. This includes interrupted first-run seeding,
    where an externally created destination must not be deleted automatically.
    """


class WarframeDataUpdater:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout
        self.paths = ensure_app_dirs()

    def refresh(self) -> dict[str, str | Path]:
        source = self.paths["source"]
        weapons_zip = source / "ExportWeapons_en_Cleaned.zip"
        upgrades_zip = source / "ExportKeys_en_Cleaned.zip"
        with locked_exports(weapons_zip, upgrades_zip):
            starting_exports = {
                path: self._export_fingerprint(path) for path in (weapons_zip, upgrades_zip)
            }
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
                                       (staged_upgrades, upgrades_zip)), stage,
                                      expected=starting_exports)
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
    def _export_fingerprint(path: Path) -> ExportFingerprint:
        """Identify the exact existing export contents without following symlinks."""
        try:
            before = path.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(before.st_mode):
            raise DataRefreshError(f"Cannot refresh a symbolic-link export: {path}. Preserve and review it first.")
        if not stat.S_ISREG(before.st_mode):
            raise DataRefreshError(f"The saved export is not a regular file: {path}.")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            opened = os.fstat(source.fileno())
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise DataRefreshRecoveryError(f"The saved export changed while it was being inspected: {path}.")
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(source.fileno())
        current = path.lstat()
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        identity_path = (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
        if identity_before != identity_after or identity_after != identity_path:
            raise DataRefreshRecoveryError(f"The saved export changed while it was being inspected: {path}.")
        return (*identity_after, digest.hexdigest())

    @staticmethod
    def _publish_exports(archives: tuple[tuple[Path, Path], ...], stage: Path,
                         *, expected: dict[Path, ExportFingerprint] | None = None) -> None:
        """Publish a validated pair under the shared process-level export lock.

        Two filesystem entries cannot be replaced as one atomic operation, so
        readers and every publisher cooperate through a lock spanning the full
        publication. Previous copies and a marker allow a later process to
        detect and manually recover a failure or crash mid-publication.
        """
        targets = tuple(target for _, target in archives)
        with export_lock(*targets):
            _require_complete_exports_unlocked(*targets)
            if expected is not None:
                for target in targets:
                    if WarframeDataUpdater._export_fingerprint(target) != expected.get(target):
                        raise DataRefreshRecoveryError(
                            f"Saved export {target} changed while fresh data was downloading. "
                            "No exports were published and no rebuild was started. Preserve the "
                            "current files, verify the pair, and retry if appropriate."
                        )
            WarframeDataUpdater._publish_exports_locked(archives, stage, expected=expected)

    @staticmethod
    def _publish_seed_exports_locked(archives: tuple[tuple[Path, Path], ...], stage: Path) -> None:
        """Publish a first-run pair without overwriting a concurrently created file.

        A hard link is an atomic, no-clobber publication of each complete staged
        file. If publication stops after any link was made, leave the marker and
        staged copies for manual recovery rather than deleting a file another
        program might already have modified.
        """
        marker = stage / "PUBLISHING.json"
        with marker.open("x", encoding="utf-8") as handle:
            json.dump({"mode": "seed-no-clobber", "archives": [
                {"destination": target.name, "previous_copy": None, "staged_copy": staged.name}
                for staged, target in archives
            ]}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        attempted: list[tuple[Path, Path]] = []
        try:
            for staged, target in archives:
                # Record intent before linking: an interrupt may arrive after
                # the OS call succeeds but before Python regains control.
                attempted.append((staged, target))
                os.link(staged, target)
        except BaseException as exc:
            needs_recovery = False
            for staged, target in attempted:
                try:
                    needs_recovery = needs_recovery or os.path.samefile(staged, target)
                except FileNotFoundError:
                    # If a target exists but its staged copy disappeared, do
                    # not guess who owns the target or remove the marker.
                    needs_recovery = needs_recovery or os.path.lexists(target)
                except OSError:
                    needs_recovery = True
            if needs_recovery:
                if not isinstance(exc, Exception):
                    raise
                raise DataRefreshRecoveryError(
                    "First-run export seeding stopped after publication began. "
                    f"Inspect and recover the saved pair using {stage}; no destination "
                    f"was overwritten or automatically deleted. Publication error: {exc}"
                ) from exc
            marker.unlink()
            if not isinstance(exc, Exception) or isinstance(exc, FileExistsError):
                raise
            raise DataRefreshError(f"Could not safely seed saved exports: {exc}") from exc
        marker.unlink()

    @staticmethod
    def _publish_exports_locked(archives: tuple[tuple[Path, Path], ...], stage: Path,
                                *, expected: dict[Path, ExportFingerprint] | None = None) -> None:
        """Publish under the export lock, preserving uncertain destinations on failure."""
        backups: dict[Path, Path | None] = {}
        for _, target in archives:
            try:
                info = target.lstat()
            except FileNotFoundError:
                backups[target] = None
                continue
            # os.replace would replace a symlink itself, not the file it points
            # to. Do not silently destroy a user's linked-source configuration.
            if stat.S_ISLNK(info.st_mode):
                raise DataRefreshError(f"Cannot refresh a symbolic-link export: {target}. Preserve and review it first.")
            if not stat.S_ISREG(info.st_mode):
                raise DataRefreshError(f"The saved export is not a regular file: {target}.")
            backup = stage / ("previous-" + target.name)
            shutil.copy2(target, backup)
            if expected is not None:
                prior = expected.get(target)
                snapshot = WarframeDataUpdater._export_fingerprint(backup)
                if prior is None or snapshot is None or snapshot[2] != prior[2] or snapshot[4] != prior[4]:
                    raise DataRefreshRecoveryError(
                        f"Saved export {target} changed while its recovery copy was made. "
                        "No exports were published; preserve the current files and retry after review."
                    )
            backups[target] = backup

        marker = stage / "PUBLISHING.json"
        with marker.open("x", encoding="utf-8") as handle:
            json.dump({"archives": [
                {"destination": target.name,
                 "previous_copy": (backup_path.name if (backup_path := backups[target]) else None)}
                for _, target in archives
            ]}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            for staged, target in archives:
                if expected is not None and backups[target] is not None:
                    if WarframeDataUpdater._export_fingerprint(target) != expected.get(target):
                        raise DataRefreshRecoveryError(
                            f"Saved export {target} changed immediately before publication. "
                            f"No further files were published; inspect the recovery copies in {stage}."
                        )
                if backups[target] is None:
                    # A file created after the backup check belongs to its
                    # creator; publish only if this entry is still absent.
                    os.link(staged, target)
                else:
                    os.replace(staged, target)
        except BaseException as exc:
            # A signal can arrive after a filesystem operation succeeds, and
            # another program may have changed a destination. Automatically
            # restoring or deleting it could destroy that newer data. Keep the
            # marker, prior copies and current destinations for manual review.
            if not isinstance(exc, Exception):
                raise
            raise DataRefreshRecoveryError(
                "Export publication stopped; do not rebuild from the current pair. "
                f"Preserve the destinations and review the previous copies in {stage}. "
                f"No automatic rollback was attempted. Publication error: {exc}"
            ) from exc
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
        if database_has_contents(target):
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
                    # Requests transparently decodes Content-Encoding (e.g.
                    # gzip) in iter_content, so Content-Length describes a
                    # different byte count and must not be compared here.
                    with open(target_path, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=8192):
                            if not chunk:
                                continue
                            if total_bytes + len(chunk) > MAX_DOWNLOAD_BYTES:
                                raise DataRefreshError(
                                    f"Downloaded file exceeds the {MAX_DOWNLOAD_BYTES}-byte safety limit: {url}"
                                )
                            handle.write(chunk)
                            total_bytes += len(chunk)

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

    def _decompress_lzma_streams(self, data: bytes, *,
                                 max_output_bytes: int = MAX_MANIFEST_DECOMPRESSED_BYTES) -> bytes:
        """Read complete streams with a decoded-size cap; reject truncation/junk."""
        if not data:
            raise lzma.LZMAError("Empty compressed data")
        if max_output_bytes < 0:
            raise ValueError("max_output_bytes must be non-negative")
        results: list[bytes] = []
        total = 0
        while data:
            decomp = lzma.LZMADecompressor(lzma.FORMAT_AUTO)
            pending = data
            chunks: list[bytes] = []
            while not decomp.eof:
                # Permit one byte beyond the limit so expansion is detected
                # before an unbounded result can be materialized.
                result = decomp.decompress(pending, max_length=max_output_bytes - total + 1)
                pending = b""
                total += len(result)
                if total > max_output_bytes:
                    raise lzma.LZMAError(
                        f"Decompressed manifest exceeds the {max_output_bytes}-byte safety limit"
                    )
                chunks.append(result)
                if decomp.needs_input:
                    if not decomp.eof:
                        raise lzma.LZMAError(
                            "Compressed data ended before the end-of-stream marker was reached"
                        )
                # needs_input=False means the decoder has buffered output; call
                # it again with empty input and the remaining bounded capacity.
            results.append(b"".join(chunks))
            data = decomp.unused_data
        return b"".join(results)

    def _clean_json(self, json_path: Path) -> dict:
        # Refuse ambiguous duplicate keys instead of silently accepting the
        # last occurrence. Do not strip whitespace around escaped newlines:
        # it changes string contents.
        data = json.loads(json_path.read_text(encoding="utf-8"),
                          object_pairs_hook=reject_duplicate_keys)
        if not isinstance(data, dict):
            raise ValueError(f"Export root must be a JSON object: {json_path}")
        return data

    def _write_zip(self, zip_path: Path, member_name: str, data: dict) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(member_name, json.dumps(data, indent=4))
