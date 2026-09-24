"""Validates a candidate installation path before the launcher lets the user proceed.

Two layers, reusing existing logic rather than re-deriving it:

- ``quick_validate`` (:func:`whshr.launcher.discovery.looks_like_installation`) is cheap enough to
  run on every launcher start, to catch a previously-recognized path that no longer exists (moved
  or uninstalled) without a noticeable delay.
- ``full_check`` runs the existing ``whshr check`` structural regression report (RNC/audio/
  cutscene/behaviour-script checks) once, when the user adopts a *new* path, and returns its
  per-group pass/fail lines instead of just a final bool.
"""

import contextlib
import io

from whshr.launcher.discovery import looks_like_installation as quick_validate


def full_check(path):
    """Runs ``whshr check`` against ``path``, returning (passed, per-group report lines).

    Imports ``whshr.__main__`` lazily: it pulls in the whole tool suite (engine, viewers, ...),
    which ``quick_validate`` - run on every launcher start - has no reason to pay for.
    """
    from whshr.__main__ import check as run_check

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        passed = run_check(path)
    lines = [line for line in output.getvalue().splitlines() if line.strip()]
    return passed, lines
