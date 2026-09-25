# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Persistent launcher settings: the recognized installation path.

One JSON file, stdlib-only. Location follows each platform's own convention:

- Windows: ``%APPDATA%\\ohr\\config.json``.
- macOS/Linux: ``$XDG_CONFIG_HOME/ohr/config.json`` if ``XDG_CONFIG_HOME`` is set, else
  ``~/.ohr/config.json``.
"""

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from os import PathLike
from typing import Any, Optional


@dataclass
class LauncherConfig:
    installation_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LauncherConfig":
        return cls(installation_path=data.get("installation_path"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def config_path() -> Path:
    """Where the config file lives on the current platform."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "ohr" / "config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "ohr" / "config.json"
    return Path.home() / ".ohr" / "config.json"


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
