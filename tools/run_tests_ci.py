"""Run the full unittest suite and surface failures as GitHub annotations.

The runner keeps unittest's normal discovery, verbosity and failure exit code.
Annotations make tracebacks available through the Checks API even when the
Actions log-download host is inaccessible. No tests are skipped or retried.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]


def _escape_command_text(text: str) -> str:
    """Escape data in a GitHub Actions workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def run_suite(suite: unittest.TestSuite, *, stream: TextIO | None = None) -> unittest.TestResult:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for test, traceback in [*result.failures, *result.errors]:
            message = f"{test}\n{traceback}"
            # Keep an individual annotation bounded while retaining the test
            # identifier and its traceback; unittest still prints the full log.
            print("::error title=Unittest failure::" + _escape_command_text(message[:50000]))
        if result.testsRun == 0:
            print("::error title=Unittest discovery::No tests were executed.")
    return result


def main() -> int:
    # The CLI unittest discover command exposes both the repository and test
    # directories to imports. Preserve that behavior on Linux and Windows.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test*.py")
    result = run_suite(suite)
    return 0 if result.testsRun and result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
