"""Coordinate reads and publication of the saved multi-file export snapshot."""
from __future__ import annotations

import errno
import os
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path


class UnfinishedExportPublication(RuntimeError):
    """A prior refresh may have left the saved ZIP pair inconsistent."""


class ExportLockTimeout(TimeoutError):
    """A concurrent export reader or publisher did not release its lock."""


EXPORT_LOCK_TIMEOUT_SECONDS = 30.0
_LOCK_FILE_NAME = ".wdc-exports.lock"
_THREAD_LOCKS: dict[Path, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(path: Path) -> threading.RLock:
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(path)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[path] = lock
        return lock


def _windows_lock(handle, mode_name: str) -> None:
    """Apply a one-byte Windows lock without requiring platform stubs on POSIX."""
    import msvcrt

    locking_name = "locking"
    lock_file = getattr(msvcrt, locking_name)
    lock_mode = getattr(msvcrt, mode_name)
    lock_file(handle.fileno(), lock_mode, 1)


def _try_lock_file(handle) -> bool:
    """Try an exclusive one-byte lock using the platform's standard library."""
    if os.name == "nt":
        handle.seek(0)
        try:
            _windows_lock(handle, "LK_NBLCK")
            return True
        except OSError:
            return False

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise


def _unlock_file(handle) -> None:
    if os.name == "nt":
        handle.seek(0)
        _windows_lock(handle, "LK_UNLCK")
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _directory_lock(directory: Path, deadline: float) -> Iterator[None]:
    """Acquire a thread- and process-level exclusive lock for one export folder."""
    lock_path = directory / _LOCK_FILE_NAME
    local_lock = _thread_lock(lock_path)
    remaining = max(0.0, deadline - time.monotonic())
    if not local_lock.acquire(timeout=remaining):
        raise ExportLockTimeout(f"Timed out waiting for export lock: {lock_path}")

    handle = None
    locked = False
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # a+b creates the lock file without truncating it. Windows locks byte 0,
        # so ensure that byte exists before any process attempts to lock it.
        handle = lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        while not (locked := _try_lock_file(handle)):
            if time.monotonic() >= deadline:
                raise ExportLockTimeout(f"Timed out waiting for export lock: {lock_path}")
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        yield
    finally:
        if handle is not None:
            if locked:
                _unlock_file(handle)
            handle.close()
        local_lock.release()


@contextmanager
def export_lock(*paths: str | Path,
                timeout: float = EXPORT_LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """Lock the parent folder(s) for a complete read or publication operation.

    The locks are acquired in canonical path order to prevent deadlocks when
    callers pass files from more than one directory. The on-disk lock files are
    intentionally persistent; OS locks are released automatically if a process
    exits or crashes.
    """
    if timeout < 0:
        raise ValueError("timeout must be non-negative")
    parents = sorted({Path(path).resolve().parent for path in paths}, key=str)
    deadline = time.monotonic() + timeout
    with ExitStack() as stack:
        for parent in parents:
            stack.enter_context(_directory_lock(parent, deadline))
        yield


def _require_complete_exports_unlocked(*paths: str | Path) -> None:
    for parent in sorted({Path(path).parent.resolve() for path in paths}):
        for stage in sorted(parent.glob(".wdc-refresh-*")):
            if (stage / "PUBLISHING.json").is_file():
                raise UnfinishedExportPublication(
                    f"An unfinished data refresh may have left saved exports inconsistent: {stage}. "
                    "Do not rebuild from these files. Inspect PUBLISHING.json and restore the "
                    "previous-* copies (or remove a destination that previously did not exist), "
                    "then remove the staging directory and retry."
                )


@contextmanager
def locked_exports(*paths: str | Path,
                   timeout: float = EXPORT_LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    """Hold the export lock while verifying and reading a consistent snapshot."""
    with export_lock(*paths, timeout=timeout):
        _require_complete_exports_unlocked(*paths)
        yield


def require_complete_exports(*paths: str | Path) -> None:
    """Check that no interrupted publication currently needs manual recovery.

    Callers that will open/read the ZIPs must use :func:`locked_exports` for the
    entire read; this standalone check is only a point-in-time guard.
    """
    with export_lock(*paths):
        _require_complete_exports_unlocked(*paths)
