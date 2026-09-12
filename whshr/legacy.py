"""Temporary compatibility loader for standalone tools during package migration."""

import importlib
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def module(name):
    """Load one existing script module while preserving its local sibling imports."""
    scripts = str(SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return importlib.import_module(name)

