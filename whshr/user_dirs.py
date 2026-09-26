"""Where the engine keeps its own mutable player state (saves), per platform convention.

Resolution order for the save directory (``resolve_save_dir``):

1. an explicit ``--save-dir`` value,
2. the ``OSH_SAVE_DIR`` environment variable,
3. the platform's per-user data directory: ``$XDG_DATA_HOME/ohr`` (default ``~/.local/share/ohr``)
   on Linux, ``%APPDATA%\\ohr`` on Windows, ``~/Library/Application Support/ohr`` on macOS.

The directory is never inside the original installation (``CLAUDE.md``, "saves are the engine's own").
Stdlib only, so the launcher can share it.
"""

import os
import sys
from collections.abc import Mapping
from os import PathLike
from pathlib import Path

APP_NAME = "ohr"
SAVE_DIR_ENV = "OSH_SAVE_DIR"


def default_save_dir(environ: Mapping[str, str] | None = None, platform: str | None = None,
                     home: Path | None = None) -> Path:
    """The platform's per-user data directory for this engine's saves."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    if platform == "win32":
        return Path(environ.get("APPDATA") or (home / "AppData" / "Roaming")) / APP_NAME / "saves"
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME / "saves"
    data_home = environ.get("XDG_DATA_HOME")
    # The XDG spec ignores a relative XDG_DATA_HOME.
    base = Path(data_home) if data_home and Path(data_home).is_absolute() else home / ".local" / "share"
    return base / APP_NAME / "saves"


def resolve_save_dir(explicit: str | PathLike[str] | None = None, environ: Mapping[str, str] | None = None,
                     platform: str | None = None, home: Path | None = None) -> Path:
    """``explicit`` flag, else ``OSH_SAVE_DIR``, else the platform default."""
    if explicit is not None:
        return Path(explicit)
    environ = os.environ if environ is None else environ
    from_env = environ.get(SAVE_DIR_ENV)
    if from_env:
        return Path(from_env)
    return default_save_dir(environ, platform, home)
