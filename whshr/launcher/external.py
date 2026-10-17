"""The environment for programs the launcher starts that are not part of it (innoextract, the web browser).

A packaged (PyInstaller) launcher runs with the library search path pointing at its own bundled libraries
(``LD_LIBRARY_PATH`` on Linux, ``LIBPATH`` on AIX, ``DYLD_LIBRARY_PATH`` where set on macOS). A child process
inherits it, so a system program such as ``/usr/bin/innoextract`` would load the bundle's older ``libstdc++``
and fail ("version `GLIBCXX_...' not found"). PyInstaller keeps each variable's value from before the launch
in ``<NAME>_ORIG``; external programs get that back, or no value at all if there was none.

The engine itself is not affected: a packaged launcher starts its own bundled executable, which sets the
variables again. Stdlib only.
"""

import os
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager

LIBRARY_PATH_VARIABLES = ("LD_LIBRARY_PATH", "LIBPATH", "DYLD_LIBRARY_PATH")


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def external_environment(base: Mapping[str, str] | None = None, frozen: bool | None = None) -> dict[str, str]:
    """``base`` (this process's environment by default) with the library search paths from before the launch."""
    environment = dict(os.environ if base is None else base)
    if not (_frozen() if frozen is None else frozen):
        return environment
    for name in LIBRARY_PATH_VARIABLES:
        original = environment.pop(f"{name}_ORIG", None)
        if original is not None:
            environment[name] = original
        else:
            environment.pop(name, None)
    return environment


@contextmanager
def external_process_environment() -> Generator[None]:
    """Within the block, this process's own environment is the external one (for APIs that take no ``env``,
    such as :func:`webbrowser.open`); the bundled values are restored afterwards."""
    if not _frozen():
        yield
        return
    saved = {name: os.environ.get(name) for name in LIBRARY_PATH_VARIABLES}
    cleaned = external_environment(frozen=True)
    for name in LIBRARY_PATH_VARIABLES:
        if name in cleaned:
            os.environ[name] = cleaned[name]
        else:
            os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
