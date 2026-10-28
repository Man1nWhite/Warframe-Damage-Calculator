"""Build and exercise an instrumented PyInstaller bundle with isolated data.

Run manually (not as part of unittest discovery):
    python -m pip install -r requirements-build.txt
    python tests/run_packaging_smoke.py

The test-only runtime hook performs real offscreen widget calculations,
save/load and an offline database rebuild, then exits. It is not shipped by
WDC.spec. No existing app-data files are touched and no network is used by
the bundled app. Building still requires a shared-library Python and the Qt
native libraries needed on the host.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="wdc-packaging-smoke-") as temporary:
        temporary_path = Path(temporary)
        work = temporary_path / "work"
        dist = temporary_path / "dist"
        appdata = temporary_path / "appdata"
        result_path = temporary_path / "result.json"
        db_dir = appdata / "WDC" / "data"
        db_dir.mkdir(parents=True)
        shutil.copy2(ROOT / "data" / "weapons.db", db_dir / "weapons.db")

        command = [sys.executable, "-m", "PyInstaller", "--noconfirm",
                   "--workpath", str(work), "--distpath", str(dist),
                   str(ROOT / "tests" / "packaging_smoke.spec")]
        try:
            build = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors="replace",
                                   timeout=600, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Could not complete the PyInstaller build: {exc}", file=sys.stderr)
            return 1
        if build.returncode:
            print(build.stdout[-15000:], file=sys.stderr)
            return build.returncode

        executable = dist / "WDC" / ("WDC.exe" if sys.platform == "win32" else "WDC")
        env = os.environ.copy()
        env.update({"APPDATA": str(appdata), "QT_QPA_PLATFORM": "offscreen",
                    "WDC_PACKAGING_SMOKE_RESULT": str(result_path)})
        env.pop("PYTHONPATH", None)
        try:
            run = subprocess.run([str(executable)], cwd=temporary_path, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, errors="replace", timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Packaged app did not complete its smoke test: {exc}", file=sys.stderr)
            return 1
        if run.returncode or not result_path.is_file():
            print(f"Packaged app exited {run.returncode}; output:\n{run.stdout}", file=sys.stderr)
            if result_path.is_file():
                print(result_path.read_text(encoding="utf-8"), file=sys.stderr)
            return 1
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"Cannot read the packaged-app result: {exc}", file=sys.stderr)
            return 1
        if not result.get("ok"):
            print(json.dumps(result, indent=2), file=sys.stderr)
            return 1
        print("Packaged offscreen smoke test passed:")
        print(json.dumps(result, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
