# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Persistent launcher settings: the recognized installation path.

One JSON file, stdlib-only. Location follows each platform's own convention:

- Windows: ``%APPDATA%\\ohr\\config.json``.
- macOS: ``~/Library/Application Support/ohr/config.json``, beside the saves and logs.
- Linux: ``$XDG_CONFIG_HOME/ohr/config.json``, by default ``~/.config/ohr/config.json``.

Older versions kept the file (and a packaged engine's logs) in ``~/.ohr`` on Linux and macOS;
:func:`migrate_legacy_files` moves them to their current places when the launcher starts.
"""

import json
import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from os import PathLike
from typing import Any, Optional

from whshr.user_dirs import data_dir

LEGACY_DIR_NAME = ".ohr"  # the old home-directory folder on Linux and macOS


@dataclass
class LauncherConfig:
    installation_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LauncherConfig":
        return cls(installation_path=data.get("installation_path"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def config_path(environ: Mapping[str, str] | None = None, platform: str | None = None,
                home: Path | None = None) -> Path:
    """Where the config file lives on the current platform (arguments default to this system's)."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    if platform in ("win32", "darwin"):
        return data_dir(environ, platform, home) / "config.json"
    xdg = environ.get("XDG_CONFIG_HOME")
    # The XDG spec ignores a relative XDG_CONFIG_HOME.
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else home / ".config"
    return base / "ohr" / "config.json"


def migrate_legacy_files(environ: Mapping[str, str] | None = None, platform: str | None = None,
                         home: Path | None = None) -> list[str]:
    """Moves what older versions left in ``~/.ohr`` (Linux and macOS) to the current locations.

    The config file goes to :func:`config_path` unless a config already exists there: then an identical
    old copy is deleted and a different one is left alone. Old logs go to ``logs/`` in the per-user data directory. ``~/.ohr`` is removed
    once empty. Returns one line per action taken; never raises (a failed move just stays behind).
    """
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    legacy = home / LEGACY_DIR_NAME
    if platform == "win32" or not legacy.is_dir():
        return []
    done: list[str] = []
    old_config = legacy / "config.json"
    new_config = config_path(environ, platform, home)
    try:
        if old_config.is_file() and not new_config.exists():
            new_config.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(old_config, new_config)
            done.append(f"Moved {old_config} to {new_config}")
        elif old_config.is_file() and new_config.is_file() and old_config.read_bytes() == new_config.read_bytes():
            old_config.unlink()
            done.append(f"Removed {old_config}, a copy of {new_config}")
        old_logs = legacy / "logs"
        if old_logs.is_dir():
            new_logs = data_dir(environ, platform, home) / "logs"
            new_logs.mkdir(parents=True, exist_ok=True)
            for log in sorted(old_logs.iterdir()):
                if log.is_file() and not (new_logs / log.name).exists():
                    shutil.move(log, new_logs / log.name)
                    done.append(f"Moved {log} to {new_logs}")
            if not any(old_logs.iterdir()):
                old_logs.rmdir()
        if not any(legacy.iterdir()):
            legacy.rmdir()
            done.append(f"Removed the empty {legacy}")
    except OSError:
        pass
    return done


def load_config(path: str | PathLike[str] | None = None) -> LauncherConfig:
    """Loads the config file, or a default (empty) config if it doesn't exist yet."""
    path = Path(path) if path is not None else config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return LauncherConfig()
    return LauncherConfig.from_dict(data)


def save_config(config: LauncherConfig, path: str | PathLike[str] | None = None) -> None:
    path = Path(path) if path is not None else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
