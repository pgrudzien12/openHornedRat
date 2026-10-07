"""Shared frozen entry point for the launcher and its engine child process."""

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check-bundle"]:
        import tkinter
        import pygame
        import zengl
        from whshr.frontend import app  # noqa: F401

        assert tkinter.TkVersion > 0
        assert pygame.version.ver
        assert zengl.__version__
        return 0
    if args and args[0] != "--launcher":
        from whshr.__main__ import main as engine_main

        return engine_main(["engine", *(args[1:] if args[0] == "--engine" else args)]) or 0

    from whshr.launcher.gui import main as launcher_main

    launcher_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
