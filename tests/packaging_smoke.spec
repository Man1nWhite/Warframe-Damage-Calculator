# Test-only wrapper around the production PyInstaller specification.
# The runtime hook below is NOT included in the shipping WDC.spec bundle.
from pathlib import Path

project_root = Path(SPECPATH).parent
smoke_hook = project_root / "tests" / "packaging_smoke_hook.py"
_original_analysis = Analysis


def _instrumented_analysis(scripts, *args, **kwargs):
    # Analysis resolves relative script paths against this test spec's folder.
    scripts = [str(project_root / script) if not Path(script).is_absolute() else script
               for script in scripts]
    kwargs["runtime_hooks"] = [*kwargs.get("runtime_hooks", []), str(smoke_hook)]
    return _original_analysis(scripts, *args, **kwargs)


Analysis = _instrumented_analysis
SPECPATH = str(project_root)
production_spec = project_root / "WDC.spec"
exec(compile(production_spec.read_bytes(), str(production_spec), "exec"))
