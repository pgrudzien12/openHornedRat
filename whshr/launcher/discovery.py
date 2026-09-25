# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Finds a Warhammer: Shadow of the Horned Rat installation without asking the user first.

Rather than guessing the exact install folder name (fragile across releases/languages), this
scans a short list of platform-typical parent directories - GOG Galaxy's default location,
every configured Steam library folder (including a Steam/Proton compatibility prefix, the
layout this project's own Linux development environment uses), and the user's home directory -
and structurally validates each immediate subdirectory as a candidate installation.
"""

import os
import re
import sys
from pathlib import Path

from whshr.paths import Installation


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


def _steam_roots() -> list[Path]:
    if sys.platform == "win32":
        candidates = [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    else:
        candidates = [Path.home() / ".local/share/Steam", Path.home() / ".steam/steam"]
    return [c for c in candidates if c.is_dir()]


def candidate_parents() -> list[Path]:
    """Parent directories whose immediate subdirectories are worth checking for an installation."""
    parents: list[Path] = []
    if sys.platform == "win32":
        parents.append(Path("C:/GOG Games"))
        parents.append(Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "GOG Galaxy/Games")
    else:
        parents.append(Path.home() / "GOG Games")

    for steam_root in _steam_roots():
        for library in _steam_library_roots(steam_root):
            parents.append(library / "steamapps" / "common")
            compatdata = library / "steamapps" / "compatdata"
            if compatdata.is_dir():
                for prefix in compatdata.iterdir():
                    parents.append(prefix / "pfx" / "drive_c" / "GOG Games")

    return [p for p in parents if p.is_dir()]


def discover_installations() -> list[Path]:
    """Returns every structurally valid installation found under the candidate parents."""
    found: list[Path] = []
    for parent in candidate_parents():
        try:
            children = list(parent.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and looks_like_installation(child):
                found.append(child)
    return found
