"""Unpacks the game from a GOG offline installer (``setup_*.exe``) on systems that cannot run it.

GOG sells the game as a DRM-free Windows installer built with Inno Setup. Linux and macOS cannot run it
directly, but the open-source ``innoextract`` tool reads that format; this module runs it to unpack only
the game's ``WARFB`` folder into a directory of the user's choosing (by default the engine's own data
directory, :func:`whshr.user_dirs.default_game_dir`). ``innoextract`` is found next to a frozen launcher
first (packages may bundle it), then on ``PATH``.
"""

import shutil
import subprocess
import sys
from collections import deque
from collections.abc import Callable
from os import PathLike
from pathlib import Path

from whshr.launcher.discovery import looks_like_installation
from whshr.launcher.external import external_environment

INNOEXTRACT = "innoextract"
GAME_FOLDER = "WARFB"
FILE_LINE_PREFIX = ' - "'  # innoextract prints one such line per listed or extracted file or folder

Progress = Callable[[int, int], None]  # (files done, files in total)


def _is_file_line(line: str) -> bool:
    """True for innoextract's line about one file (folders are listed too, ending in a slash)."""
    return line.startswith(FILE_LINE_PREFIX) and '/"' not in line


class ExtractionFailed(Exception):
    """innoextract failed, or the unpacked files are not a usable installation."""


def find_innoextract(search_path: str | None = None, executable: str | None = None) -> str | None:
    """The innoextract program to run: the one bundled beside a frozen launcher, else the one on PATH.

    ``search_path`` replaces ``PATH`` and ``executable`` replaces ``sys.executable`` (for tests).
    """
    if getattr(sys, "frozen", False) or executable is not None:
        name = INNOEXTRACT + (".exe" if sys.platform == "win32" else "")
        bundled = Path(executable or sys.executable).parent / name
        if bundled.is_file():
            return str(bundled)
    return shutil.which(INNOEXTRACT, path=search_path)


def install_hint(platform: str | None = None) -> str:
    """How to get innoextract on this platform, for a message shown when it is missing."""
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        return "Install it with Homebrew: brew install innoextract"
    if platform == "win32":
        return "On Windows you can simply run the GOG installer instead."
    return ("Install it with your package manager, for example: sudo apt install innoextract "
            "(Debian/Ubuntu) or sudo dnf install innoextract (Fedora).")


def _run(command: list[str], on_line: Callable[[str], None] | None = None) -> list[str]:
    """Runs ``command``; returns the last output lines, raising ExtractionFailed on a non-zero exit."""
    tail: deque[str] = deque(maxlen=12)
    # A system innoextract must not load the packaged launcher's bundled libraries (whshr.launcher.external).
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=external_environment(),
                          encoding="utf-8", errors="replace") as process:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            tail.append(line)
            if on_line is not None:
                on_line(line)
    if process.returncode != 0:
        raise ExtractionFailed("innoextract failed:\n" + "\n".join(tail))
    return list(tail)


def count_game_files(innoextract: str, installer: str | PathLike[str]) -> int:
    """How many game files the installer holds (innoextract's listing, without unpacking)."""
    count = 0

    def on_line(line: str) -> None:
        nonlocal count
        if _is_file_line(line):
            count += 1

    _run([innoextract, "--list", "--include", GAME_FOLDER, "--color=0", "--progress=0", str(installer)], on_line)
    return count


def find_game(target: Path) -> Path | None:
    """The unpacked installation under ``target``: its WARFB folder, searched a few levels deep."""
    for depth in range(4):
        for candidate in sorted(target.glob("/".join(["*"] * depth + [GAME_FOLDER]))):
            if candidate.is_dir() and looks_like_installation(candidate):
                return candidate
    return None


def _remove_empty_tree(path: Path) -> None:
    """Deletes ``path`` if it holds only (nested) empty directories."""
    if path.is_dir() and not any(child.is_file() for child in path.rglob("*")):
        shutil.rmtree(path, ignore_errors=True)


def extract(innoextract: str, installer: str | PathLike[str], target: str | PathLike[str],
            progress: Progress | None = None) -> Path:
    """Unpacks the installer's game folder into ``target``; returns the installation directory.

    Existing files in ``target`` are overwritten. Raises :class:`ExtractionFailed` if innoextract fails
    or the result does not look like an installation.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    total = count_game_files(innoextract, installer)
    if total == 0:
        raise ExtractionFailed(f"{installer} does not contain the game's {GAME_FOLDER} folder.")
    done = 0

    def on_line(line: str) -> None:
        nonlocal done
        if _is_file_line(line):
            done += 1
            if progress is not None:
                progress(min(done, total), total)

    _run([innoextract, "--gog", "--include", GAME_FOLDER, "--output-dir", str(target), "--color=0",
          "--progress=0", str(installer)], on_line)
    # innoextract also recreates the installer's empty folders under a separate "app" directory.
    _remove_empty_tree(target / "app")
    game = find_game(target)
    if game is None:
        raise ExtractionFailed(f"The unpacked files in {target} are not a usable installation.")
    return game
