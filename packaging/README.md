# Installer / packaging pipeline

Tracked by GitHub epic #96 (Windows: #97, Ubuntu/Linux: #98, CI + license audit: #99).

## Goal and scope

Produce installers that bundle this project's own launcher/engine code and a Python
interpreter, so a user doesn't need Python or any dependencies pre-installed. Per-user
install (no admin/root), a shortcut/menu entry, and the option to launch immediately after
install. The original game's files/assets are never bundled — see `CLAUDE.md`.

Windows is implemented first (`windows/`); Ubuntu/Linux (#98) is a later follow-up and does
not exist yet.

## Entry point: a stopgap until the launcher (epic #88) exists

The standalone GUI launcher (epic #88: install discovery, settings, battle picker) hasn't
been built yet. Until it lands, the installer freezes `python -m whshr engine` as-is
(`windows/entrypoint.py`): it forwards any arguments and otherwise falls back to the `WARFB`
environment variable, exactly like running `whshr engine` from source. This means the first
launch after install needs `WARFB` set, or the exe run with the installation path as an
argument (e.g. from a shortcut's "Target" field) — there is no install-path picker yet.
**When epic #88 lands, point `windows/ohr-engine.spec`'s `Analysis` entry at the real
launcher entry point instead of `entrypoint.py`**; nothing else in the packaging changes.

## Windows (#97)

**Approach:** [PyInstaller](https://pyinstaller.org/) freezes the engine into a onedir
bundle, and [Inno Setup](https://jrsoftware.org/isinfo.php) wraps that bundle into a
per-user installer. Chosen over NSIS for its cleaner per-user (`PrivilegesRequired=lowest`)
install support and a scriptable CLI compiler (`ISCC.exe`) that works well in CI. Onedir
(not onefile) was chosen over PyInstaller's onefile mode for simpler LGPL 2.1 dynamic-linking
bookkeeping (see `THIRD_PARTY_NOTICES.md`) and faster startup (no self-extraction step).

Files:
- `windows/entrypoint.py` — the frozen entry point (see above).
- `windows/ohr-engine.spec` — PyInstaller spec. Bundles `scripts/` as data: `whshr/legacy.py`
  dynamically loads a handful of stdlib-only helper modules from there (e.g. `pe_resources`,
  `pe_missions`, `fon_parse`, used by the campaign-glue and cursor/portrait rendering code
  paths) that PyInstaller's static import analysis can't see on its own. Also lists `_zengl`
  as a hidden import: zengl's compiled extension imports that pure-Python module internally,
  which PyInstaller can't discover from a compiled binary and zengl ships no PyInstaller hook
  of its own (found by actually running the frozen build — see "Verified this session" below).
- `windows/installer.iss` — Inno Setup script: per-user install under
  `%LOCALAPPDATA%\Programs\openHornedRat Engine`, Start Menu shortcut (optional desktop
  shortcut), "launch now" checkbox on the finish page, registered uninstaller.

Two engine-side fixes were needed to freeze correctly, both frozen-build-only branches (the
non-frozen, run-from-source behaviour is unchanged):
- `whshr/legacy.py`'s `SCRIPTS` path now resolves under `sys._MEIPASS` when frozen (PyInstaller's
  documented, stable base path for bundled data in both onefile and onedir builds) instead of
  walking up from `__file__`, which would point into the frozen bundle's internal layout, not
  a real `scripts/` directory next to it.
- `whshr/__main__.py`'s default battle-log/save directories now resolve under the user's own
  per-app data folder (`%APPDATA%\ohr` on Windows, matching the location epic #88 plans for its
  config file) when frozen, instead of a `logs/`/`saves/` folder computed relative to the
  installed package — which would have put user save data inside the install directory, at risk
  of being swept up by the uninstaller.

Build locally (needs Python 3.10+ — the pinned `pygame-ce`/`zengl` versions in
`requirements-engine.txt` don't publish wheels for 3.9 — and Inno Setup's `ISCC.exe` on PATH):

```
python -m venv .venv
.venv\Scripts\pip install --only-binary=:all: -r requirements-engine.txt pyinstaller
.venv\Scripts\pyinstaller packaging\windows\ohr-engine.spec --distpath dist --workpath build --noconfirm
ISCC packaging\windows\installer.iss
```

The resulting installer lands in `dist\installer\ohr-engine-setup-<version>.exe`. Override
the version with `ISCC /DMyAppVersion=1.2.3 packaging\windows\installer.iss`.

**Verified this session:** running the frozen exe with `WARFB` pointed at an empty directory
(`--hidden --frames 1`, the same check the CI smoke-test step runs) reaches past argument
parsing into `whshr.frontend.app.run` — i.e. pygame-ce and zengl, the runtime frontend's own
third-party dependencies that are otherwise only imported lazily past the argument-parsing
gate, actually import and their native DLLs actually load in the frozen bundle — and fails
only on the (expected, correct) installation-completeness check, not on
`ModuleNotFoundError`/`ImportError`. `scripts/`-backed dynamic imports (`whshr.legacy.module`)
resolve correctly under `sys._MEIPASS`. A full Inno Setup install/uninstall cycle was also run
end to end (`/VERYSILENT`): per-user install with no admin prompt (`Administrative install
mode: No` in the Inno log), Start Menu shortcut created and removed, uninstaller registered
and working.

**Not verified this session** (no legally-owned game installation was available in this
environment, and none is ever available on a CI runner either — the game is never bundled,
see `CLAUDE.md`): the frozen exe was never run against a real `WARFB` installation, so the
`scripts/`-backed code paths (army records view, cursors, campaign scene font/string
loading) are statically correct (bundled, resolvable, unit-tested in isolation) but not
exercised end to end inside a frozen build. `whshr.frontend.app.run` validates the
installation (`whshr/assets.py`) before ever opening a window/GL context, so both this
session's local check and the CI smoke test point `WARFB` at an empty directory and only
need to reach that validation error — they don't need a real installation, and don't need
GPU-accelerated OpenGL either, to prove pygame-ce/zengl's native DLLs load correctly.
Confirm the `scripts/`-backed paths once a build runs against a real installation, e.g. a
manual test on a machine with the game installed.

## License audit (#99)

See `THIRD_PARTY_NOTICES.md` for the full conclusion. Summary: pygame-ce is LGPL 2.1 and
zengl is MIT; PyInstaller bundles pygame-ce's native libraries (SDL2 and friends, all
permissive-licensed) as separate DLL files loaded dynamically at runtime rather than
statically merged into the frozen executable, which satisfies LGPL 2.1 §6(b)'s
shared-library exception. `THIRD_PARTY_NOTICES.md` and `licenses/LGPL-2.1.txt` are installed
alongside the app (see `installer.iss`'s `[Files]` section).

## CI (#99)

`.github/workflows/windows-installer.yml` builds the Windows installer on a `windows-latest`
runner (PyInstaller and Inno Setup both run natively there — no Wine/cross-compilation,
PyInstaller does not support it) on pushes to `main` and pull requests touching the relevant
paths (unpublished smoke build, uploaded as a workflow artifact), and on `v*` tags, where the
installer is additionally attached to the matching GitHub Release. Not yet run on GitHub's
infrastructure as of this writing — verify the first run before relying on it.

The Ubuntu/Linux job (#98) is a follow-up; add it as a second job in the same workflow (or a
separate one) once that installer exists, rather than duplicating the trigger config.
