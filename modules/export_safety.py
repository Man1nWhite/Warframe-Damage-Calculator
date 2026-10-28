"""Guard saved exports against an interrupted multi-file refresh."""
from __future__ import annotations

from pathlib import Path


class UnfinishedExportPublication(RuntimeError):
    """A prior refresh may have left its saved ZIP pair inconsistent."""


def require_complete_exports(*paths: str | Path) -> None:
    """Refuse saved exports until a retained publication is examined.

    Publication markers contain the destinations and backup filenames. This
    protects later rebuilds after an interrupted process or failed rollback;
    it does not provide locking against another process reading concurrently.
    """
    for parent in sorted({Path(path).parent.resolve() for path in paths}):
        for stage in sorted(parent.glob(".wdc-refresh-*")):
            if (stage / "PUBLISHING.json").is_file():
                raise UnfinishedExportPublication(
                    f"An unfinished data refresh may have left saved exports inconsistent: {stage}. "
                    "Do not rebuild from these files. Inspect PUBLISHING.json and restore the "
                    "previous-* copies (or remove a destination that previously did not exist), "
                    "then remove the staging directory and retry."
                )
