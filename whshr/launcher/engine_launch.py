# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Resolves which Python interpreter runs the engine, and starts it as a decoupled subprocess.

The launcher stays dependency-light (stdlib only), but ``whshr engine`` needs the pygame-ce/zengl
packages from ``requirements-engine.txt``, normally installed into a local ``.venv`` next to this
checkout (see README.md). Launching the engine under the *launcher's own* interpreter would fail
with an import error whenever the launcher itself runs outside that ``.venv``, so this module
locates the ``.venv`` interpreter next to the repository root and falls back to the launcher's own
interpreter only if no ``.venv`` is found.
"""

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

PathArg = str | PathLike[str]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def find_engine_python(repository_root: PathArg = REPOSITORY_ROOT) -> Path:
    """The interpreter that should run ``whshr engine``: the local ``.venv`` if one exists."""
    repository_root = Path(repository_root)
    relative = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    venv_python = repository_root / ".venv" / relative
    return venv_python if venv_python.is_file() else Path(sys.executable)


def engine_dependencies_available(python_path: PathArg, modules: Sequence[str] = ("pygame", "zengl"),
                                  timeout: float = 10) -> bool:
    """Whether ``python_path`` can import the engine's frontend dependencies."""
    try:
        result = subprocess.run(
            [str(python_path), "-c", f"import {', '.join(modules)}"],
            capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@dataclass(frozen=True)
class LaunchOptions:
    """Optional switches chosen on the launcher's options tab."""

    no_battles: bool = False
    trace: bool = False
    skip_intro: bool = False


def build_command(installation: PathArg, battle_id: str | None = None, options: LaunchOptions | None = None,
                  python_path: PathArg | None = None) -> list[str]:
    """The ``whshr engine`` command line: a normal start, or a direct battle when ``battle_id`` is given."""
    options = options or LaunchOptions()
    command = [str(python_path or find_engine_python()), "-m", "whshr", "engine", str(installation)]
    if battle_id:
        command += ["--battle", battle_id]
    if options.skip_intro:
        command.append("--skip-intro")
    if options.no_battles:
        command.append("--no-battle")
    return command


def build_environment(options: LaunchOptions | None = None, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The child's environment: the checkout on ``PYTHONPATH``, plus ``WHSHR_TRACE_SCRIPTS=1`` when tracing."""
    environment = dict(os.environ if base is None else base)
    # Put the checkout on the child's import path explicitly: a debugger-wrapped child does not
    # get the working directory on sys.path, and `-m whshr` then fails with "No module named whshr".
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join([str(REPOSITORY_ROOT)] + ([existing] if existing else []))
    if options and options.trace:
        environment["WHSHR_TRACE_SCRIPTS"] = "1"
    return environment


def launch_engine(installation: PathArg, battle_id: str | None = None, options: LaunchOptions | None = None,
                  python_path: PathArg | None = None) -> subprocess.Popen[bytes]:
    """Starts the engine as an independent process (a normal game, or one battle)."""
    return subprocess.Popen(
        build_command(installation, battle_id, options, python_path),
        cwd=str(REPOSITORY_ROOT),
        env=build_environment(options),
    )


def launch_battle(installation: PathArg, battle_id: str, python_path: PathArg | None = None,
                  options: LaunchOptions | None = None) -> subprocess.Popen[bytes]:
    """Starts ``whshr engine <installation> --battle <battle_id>`` as an independent process."""
    return launch_engine(installation, battle_id, options, python_path)
