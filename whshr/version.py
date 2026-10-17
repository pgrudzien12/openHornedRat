"""The engine's version: one string shared by the launcher, ``--version``, the logs and the packages.

A release is tagged ``vX.Y.Z`` and its builds carry ``X.Y.Z``. A build between releases carries
``X.Y.Z+gitN.SHA``: the last release tag, the number of commits since it and the commit. Such versions sort
after that release and after each other in apt, dnf and macOS package receipts (N only grows on the main
branch). Before the first tag the base is ``0.0.0`` and N counts every commit.

Where the version comes from, in order:

1. ``whshr/_build_version.py``, written by the PyInstaller specs when a package is built (the package
   workflows pass the version in ``OHR_VERSION``; a local build asks git); it is not tracked;
2. ``git describe`` in a source checkout;
3. :data:`UNKNOWN`.

Stdlib only. Run as a script (``python3 whshr/version.py``) it prints the git-derived version; the package
workflows use that for builds between releases.
"""

import re
import subprocess
import sys
from functools import lru_cache
from os import PathLike
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UNKNOWN = "0.0.0+unknown"
TAG_GLOB = "v[0-9]*"
_NUMBERS = re.compile(r"^v?(\d+(?:\.\d+)*)")


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def from_git(root: str | PathLike[str] = REPOSITORY_ROOT) -> str | None:
    """The version of the commit checked out at ``root``, or None outside a git checkout."""
    root = Path(root)
    described = _git(root, "describe", "--tags", "--long", "--abbrev=8", "--match", TAG_GLOB)
    if described:
        tag, count, commit = described.rsplit("-", 2)
        base = tag[1:]
        return base if count == "0" else f"{base}+git{count}.{commit.removeprefix('g')}"
    count = _git(root, "rev-list", "--count", "HEAD")
    commit = _git(root, "rev-parse", "--short=8", "HEAD")
    if count is None or commit is None:
        return None
    return f"0.0.0+git{count}.{commit}"


@lru_cache(maxsize=1)
def version() -> str:
    """This engine's version (see the module docstring for where it comes from)."""
    try:
        from whshr._build_version import VERSION  # pyright: ignore[reportMissingImports]
    except ImportError:
        pass
    else:
        return str(VERSION)
    return from_git() or UNKNOWN


def release_numbers(text: str) -> tuple[int, ...] | None:
    """The numeric release part of a version or tag (``v1.2.0`` and ``1.2.0+git3.abc`` give (1, 2, 0))."""
    match = _NUMBERS.match(text.strip())
    if match is None:
        return None
    numbers = [int(part) for part in match.group(1).split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()  # 1.2 and 1.2.0 are the same release
    return tuple(numbers)


def is_prerelease(text: str) -> bool:
    """True for a prerelease such as ``1.2.0-rc1`` (a suffix after the numbers, before any ``+``)."""
    match = _NUMBERS.match(text.strip())
    return match is not None and text.strip()[match.end():].split("+", 1)[0] != ""


def is_newer_release(tag: str, current: str) -> bool:
    """Whether release ``tag`` (e.g. ``v1.2.0``) is newer than the running version ``current``.

    A build between releases (``1.2.0+git5.abc``) counts as its base release; a prerelease of a release is
    older than the release itself. An unreadable version is never reported as outdated.
    """
    if current.strip().endswith("+unknown"):
        return False  # a build that does not know its version cannot tell
    latest, running = release_numbers(tag), release_numbers(current)
    if latest is None or running is None or is_prerelease(tag):
        return False
    if latest != running:
        return latest > running
    return is_prerelease(current)


if __name__ == "__main__":
    print(from_git(Path.cwd()) or UNKNOWN)
    sys.exit(0)
