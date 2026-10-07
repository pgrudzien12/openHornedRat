# Installer / packaging pipeline

Tracked by GitHub epic #96 (Windows: #97, Ubuntu/Linux: #98, CI + license audit: #99).

## Goal and scope

Produce packages that bundle this project's own engine code and a Python interpreter,
so a user doesn't need Python or Python dependencies pre-installed. The Windows installer
is per-user; Debian and RPM packages use system package managers. These packages provide a
menu entry, while AppImage is a portable executable.
The original game's files/assets are never bundled — see `CLAUDE.md`.

## Entry point: frozen launcher integration is pending

The standalone GUI launcher (epic #88: install discovery, settings, battle picker) is not
yet integrated with frozen builds. The installers freeze `python -m whshr engine` as-is
(`windows/entrypoint.py`): it forwards any arguments and otherwise falls back to the `WARFB`
environment variable, exactly like running `whshr engine` from source. This means the first
launch after install needs `WARFB` set, or the exe run with the installation path as an
argument (e.g. from a shortcut's "Target" field) — there is no install-path picker yet.
The source launcher now exists, but its subprocess logic still assumes a source checkout
and local virtual environment. Integrating it into frozen packages needs a separate change.

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

`.github/workflows/windows-installer.yml` checks once a day for package source changes and
builds the Windows installer on a `windows-latest` runner when needed (PyInstaller and Inno
Setup both run natively there — no Wine/cross-compilation). A pending `v*` tag takes priority
and its installer is attached to the matching GitHub Release. Use **Run workflow** to force
a build on a selected branch or tag at any time. Not yet run on GitHub's infrastructure as
of this writing — verify the first run before relying on it.

The scheduled run checks the tracked files used by each package against a marker saved
after a successful build and release upload. If those files are unchanged, the build job
is skipped. A manual run always builds. A tag with a missing release asset is built even if
its source was built before. Only one pending tag is processed per daily run.

Successful builds of the default branch are also published under **Releases** as a dated
prerelease, `daily-YYYYMMDD` (UTC). All formats built that day attach to that one prerelease.
If no package source changed, no new daily prerelease or package is created. A manual run
on the default branch also publishes there; a manual run on another branch remains a
workflow artifact.
Version-tag builds continue to attach to their matching `v*` release. Daily assets include
the source commit in their filenames, since formats may be built from different commits
on a busy day.

## Debian package (#98)

`.github/workflows/debian-package.yml` checks once a day for package source changes and
builds an amd64 `.deb` inside a Debian 12 (bookworm) container when needed. A pending `v*`
tag takes priority and its package is attached to the matching GitHub Release; daily builds
appear in a dated prerelease and workflow artifacts. **Run workflow** forces a build on a
selected branch or tag at any time.
PyInstaller bundles the engine and its Python dependencies under `/opt/ohr-engine`.
The package provides `ohr-engine` on `PATH` and an application-menu entry. The menu
entry opens a terminal and asks for the user's original `WARFB` directory; the command
line entry accepts that path as its first argument or via `WARFB`. No original game files
are included. Save files and logs stay in the user's home directory.

To build locally on Debian 12 amd64 with Python 3.11, `python3-venv`, `binutils`,
`libgl1`, `libx11-6`, and `dpkg` installed:

```sh
python3 -m venv /tmp/ohr-build-venv
/tmp/ohr-build-venv/bin/pip install --only-binary=:all: -r requirements-engine.txt pyinstaller
/tmp/ohr-build-venv/bin/pyinstaller packaging/linux/ohr-engine.spec --distpath dist --workpath build/pyinstaller --noconfirm
sh packaging/linux/build-deb.sh 0.0.0~dev1
```

The package is written to `dist/debian/`. Install with
`sudo apt install ./dist/debian/ohr-engine_*.deb`, then run
`ohr-engine /path/to/WARFB` or use the menu entry.
The bookworm build targets Debian 12 and newer systems with compatible libraries; it has
not been tested against an actual game installation in CI.

## AppImage

`.github/workflows/appimage.yml` builds an x86_64 AppImage in a Debian 12 container. Its
AppDir contains the frozen engine, a relative `AppRun`, a desktop file, a PNG icon, and
license notices. The workflow uses versioned upstream appimagetool and type 2 runtime
releases. Run the resulting file with `./ohr-engine-<version>-x86_64.AppImage
/path/to/WARFB`, or set `WARFB`. The AppImage still needs a compatible host graphics
stack and a glibc at least as new as Debian 12's. See the
[AppDir specification](https://docs.appimage.org/reference/appdir.html) for its layout.
If FUSE is unavailable, set `APPIMAGE_EXTRACT_AND_RUN=1` when launching it; see the
[AppImage FUSE guide](https://docs.appimage.org/user-guide/troubleshooting/fuse.html).

For a local build on Debian 12, first create `dist/ohr-engine` with the PyInstaller command
above. Install `librsvg2-bin` for the icon, and provide the pinned upstream
`appimagetool-x86_64.AppImage` and `runtime-x86_64` files. Make appimagetool executable:

```sh
chmod +x /path/to/appimagetool-x86_64.AppImage
APPIMAGETOOL=/path/to/appimagetool-x86_64.AppImage \
APPIMAGE_RUNTIME_FILE=/path/to/runtime-x86_64 \
sh packaging/linux/build-appimage.sh 0.0.0~dev1
```

The output is in `dist/appimage/`.

## RPM

`.github/workflows/rpm-package.yml` freezes the engine in a Rocky Linux 9 container and
builds an x86_64 RPM with `rpmbuild`. It installs under `/opt/ohr-engine`, with the same
command and terminal menu entry as the Debian package. The RPM includes the frozen Python
runtime and notices, and targets systems with glibc 2.34 or newer and compatible OpenGL/X11
libraries. Prerelease hyphens in tags become RPM tilde operators, so `v1.2.3-rc1` becomes
`1.2.3~rc1`.

For a local build on Rocky Linux 9:

```sh
sudo dnf install python3.11 python3.11-pip rpm-build binutils libglvnd-glx libX11 cpio
python3.11 -m venv /tmp/ohr-build-venv
/tmp/ohr-build-venv/bin/pip install --only-binary=:all: -r requirements-engine.txt pyinstaller
/tmp/ohr-build-venv/bin/pyinstaller packaging/linux/ohr-engine.spec --distpath dist --workpath build/pyinstaller --noconfirm
sh packaging/linux/build-rpm.sh 0.0.0~dev1
```

The output is in `dist/rpm/`; install it with `sudo dnf install ./dist/rpm/*.rpm`.
Both new workflows use the same daily source check and manual **Run workflow** option as
the Debian and Windows workflows. Pending release tags are processed one per day per format.
