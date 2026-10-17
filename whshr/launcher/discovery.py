# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Finds a Warhammer: Shadow of the Horned Rat installation without asking the user first.

Rather than guessing the exact install folder name (fragile across releases/languages), this
scans a list of platform-typical parent directories and structurally validates what is inside:

- the engine's own data directory, where the launcher's **Unpack...** (and the README's manual
  ``innoextract`` command) puts a game unpacked from GOG's installer: ``.../ohr/game/WARFB``
  (:func:`whshr.user_dirs.default_game_dir`);
- GOG: ``C:/GOG Games`` and GOG Galaxy's ``Games`` folder on Windows, ``~/GOG Games`` elsewhere,
  ``/Applications`` on macOS;
- Steam: every library of every Steam installation found (native, snap and Flatpak on Linux,
  ``~/Library/Application Support/Steam`` on macOS), its ``steamapps/common`` and the GOG folders
  inside each Proton prefix under ``steamapps/compatdata`` (a GOG copy installed through Proton);
- Wine-style prefixes on Linux and macOS: ``~/.wine``, Bottles' bottles and Lutris' ``~/Games/*``;
- Heroic's default ``~/Games/Heroic``.

Each immediate subdirectory of a parent is accepted if it is an installation itself, or if it holds
one in a ``WARFB`` subdirectory (GOG installs to ``Warhammer - Shadow of the Horned Rat/WARFB``).
"""

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from whshr.paths import Installation
from whshr.user_dirs import data_dir


def looks_like_installation(path: str | os.PathLike[str]) -> bool:
    """True if ``path`` has the FILE/BINARY and REMOTE/BINARY layout a WARFB directory needs."""
    try:
        game = Installation(path)
    except FileNotFoundError:
        return False
    return game.find("FILE", "BINARY") is not None and game.find("REMOTE", "BINARY") is not None


def _steam_library_roots(steam_root: Path) -> list[Path]:
    """Parses ``steamapps/libraryfolders.vdf`` for every configured library's ``steamapps`` dir."""
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    roots = [steam_root]
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return roots
    for match in re.finditer(r'"path"\s*"([^"]+)"', text):
        roots.append(Path(match.group(1).replace("\\\\", "\\")))
    return roots


def _steam_roots(home: Path, platform: str) -> list[Path]:
    if platform == "win32":
        candidates = [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    elif platform == "darwin":
        candidates = [home / "Library/Application Support/Steam"]
    else:
        candidates = [
            home / ".local/share/Steam",
            home / ".steam/steam",
            home / "snap/steam/common/.local/share/Steam",
            home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
            home / ".var/app/com.valvesoftware.Steam/data/Steam",
        ]
    return [c for c in candidates if c.is_dir()]


def _windows_game_folders(drive_c: Path) -> list[Path]:
    """GOG's install folders inside a Windows drive or a Wine/Proton prefix's ``drive_c``."""
    return [drive_c / "GOG Games", drive_c / "Program Files (x86)/GOG Galaxy/Games"]


def _subdirectories(path: Path) -> list[Path]:
    try:
        return sorted(child for child in path.iterdir() if child.is_dir())
    except OSError:
        return []


def candidate_parents(home: Path | None = None, platform: str | None = None,
                      environ: Mapping[str, str] | None = None) -> list[Path]:
    """Parent directories whose immediate subdirectories are worth checking for an installation.

    ``home``, ``platform`` and ``environ`` default to the current user's home directory, ``sys.platform``
    and ``os.environ``.
    """
    home = Path.home() if home is None else home
    platform = sys.platform if platform is None else platform
    # First, so a copy unpacked by the launcher is the one preselected.
    parents: list[Path] = [data_dir(environ, platform, home)]
    if platform == "win32":
        parents.append(Path("C:/GOG Games"))
        parents.append(Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "GOG Galaxy/Games")
    else:
        parents.append(home / "GOG Games")
        if platform == "darwin":
            parents.append(Path("/Applications"))
        prefixes = [home / ".wine", *_subdirectories(home / ".local/share/bottles/bottles"),
                    *_subdirectories(home / "Games")]
        for prefix in prefixes:
            parents.extend(_windows_game_folders(prefix / "drive_c"))
        parents.append(home / "Games/Heroic")

    for steam_root in _steam_roots(home, platform):
        for library in _steam_library_roots(steam_root):
            parents.append(library / "steamapps" / "common")
            for prefix in _subdirectories(library / "steamapps" / "compatdata"):
                parents.extend(_windows_game_folders(prefix / "pfx" / "drive_c"))

    return [p for p in parents if p.is_dir()]


def discover_installations(home: Path | None = None, platform: str | None = None,
                           environ: Mapping[str, str] | None = None) -> list[Path]:
    """Returns every structurally valid installation found under the candidate parents, once each."""
    found: list[Path] = []
    seen: set[Path] = set()
    for parent in candidate_parents(home, platform, environ):
        for child in _subdirectories(parent):
            inner = [grandchild for grandchild in _subdirectories(child) if grandchild.name.upper() == "WARFB"]
            for candidate in (child, *inner):
                if not looks_like_installation(candidate):
                    continue
                resolved = candidate.resolve()  # the same library is often reachable through a symlink
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(candidate)
    return found
