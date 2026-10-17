"""The application icon: the skull pendant made for this project (not taken from the game).

``whshr/icons/`` holds it as PNGs in every size the desktops use, plus ``ohr.ico`` (Windows) and ``ohr.icns``
(macOS) for the packages; ``tools/launcher_art/build_art.py`` builds them all from the source artwork. The
launcher (Tk) and the engine window (pygame) set it at runtime; a missing file just leaves the default icon.
Stdlib only.
"""

from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
WINDOW_ICON_SIZES = (16, 32, 48, 64, 128, 256)  # what a window offers its desktop to pick from
ENGINE_WINDOW_ICON_SIZE = 64  # pygame/SDL takes one image
# The windows' class (X11 WM_CLASS, Wayland app id): it matches the Linux desktop file's name and its
# StartupWMClass, so docks and task switchers group the launcher and game windows under that entry and its icon.
WINDOW_CLASS = "ohr-engine"


def icon_path(size: int) -> Path:
    """The PNG of the icon at ``size`` pixels (one of :data:`ICON_SIZES`)."""
    return ICON_DIR / f"ohr-{size}.png"
