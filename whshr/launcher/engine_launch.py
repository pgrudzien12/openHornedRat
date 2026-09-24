"""Resolves which Python interpreter runs the engine, and starts it as a decoupled subprocess.

The launcher stays dependency-light (stdlib only), but ``whshr engine`` needs the pygame-ce/zengl
packages from ``requirements-engine.txt``, normally installed into a local ``.venv`` next to this
checkout (see README.md). Launching the engine under the *launcher's own* interpreter would fail
with an import error whenever the launcher itself runs outside that ``.venv``, so this module
locates the ``.venv`` interpreter next to the repository root and falls back to the launcher's own
interpreter only if no ``.venv`` is found.
"""

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def find_engine_python(repository_root=REPOSITORY_ROOT):
    """The interpreter that should run ``whshr engine``: the local ``.venv`` if one exists."""
    repository_root = Path(repository_root)
    relative = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    venv_python = repository_root / ".venv" / relative
    return venv_python if venv_python.is_file() else Path(sys.executable)


def engine_dependencies_available(python_path, modules=("pygame", "zengl"), timeout=10):
    """Whether ``python_path`` can import the engine's frontend dependencies."""
    try:
        result = subprocess.run(
            [str(python_path), "-c", f"import {', '.join(modules)}"],
            capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def launch_battle(installation, battle_id, python_path=None):
    """Starts ``whshr engine <installation> --battle <battle_id>`` as an independent process."""
    python_path = python_path or find_engine_python()
    return subprocess.Popen(
        [str(python_path), "-m", "whshr", "engine", str(installation), "--battle", battle_id],
        cwd=str(REPOSITORY_ROOT),
    )
