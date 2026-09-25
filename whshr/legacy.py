"""Temporary compatibility loader for standalone tools during package migration."""

import importlib
import sys
from pathlib import Path
from types import ModuleType


# sys._MEIPASS is PyInstaller's documented, stable base path for bundled data in both
# onefile and onedir builds (packaging/windows/ohr-engine.spec bundles scripts/ there).
SCRIPTS = (Path(str(getattr(sys, "_MEIPASS"))) if getattr(sys, "frozen", False)  # pyright: ignore[reportUnnecessaryComparison]
           else Path(__file__).resolve().parents[1]) / "scripts"


def module(name: str) -> ModuleType:
    """Load one existing script module while preserving its local sibling imports."""
    scripts = str(SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module(name)

