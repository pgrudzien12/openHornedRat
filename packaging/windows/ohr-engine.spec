# PyInstaller spec for the Windows build of the engine, wrapped by an Inno Setup
# installer (installer.iss). Build with:
#   .venv\Scripts\pyinstaller packaging\windows\ohr-engine.spec --distpath dist --workpath build
#
# Chosen approach and why: documented in packaging/README.md and
# packaging/THIRD_PARTY_NOTICES.md (license audit for the bundled pygame-ce/zengl
# dependencies, epic #96).
from pathlib import Path

block_cipher = None

# SPECPATH is injected by PyInstaller into the spec file's exec namespace.
REPO_ROOT = Path(SPECPATH).resolve().parents[1]

# The engine reports this version (whshr/_build_version.py is generated, untracked). Package workflows pass
# OHR_VERSION; a local build asks git. whshr/version.py is loaded by path so the whshr package is not imported.
import importlib.util
import os

_spec = importlib.util.spec_from_file_location("_ohr_version", REPO_ROOT / "whshr" / "version.py")
_version_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_version_module)
BUILD_VERSION = os.environ.get("OHR_VERSION") or _version_module.from_git(REPO_ROOT) or _version_module.UNKNOWN
(REPO_ROOT / "whshr" / "_build_version.py").write_text("VERSION = %r\n" % BUILD_VERSION, encoding="utf-8")

# whshr/legacy.py loads a handful of scripts/ modules (stdlib-only tools shared with
# the CLI, e.g. pe_resources/pe_missions/fon_parse) by name via importlib at runtime;
# PyInstaller's static import analysis cannot see those, so the whole scripts/
# directory is bundled as plain data at the bundle root, matching what
# whshr.legacy.SCRIPTS resolves to under sys._MEIPASS in a frozen build.
# __pycache__ is excluded: it is a local build/test byproduct, not part of scripts/ itself.
datas = [
    (str(path), str(Path("scripts") / path.relative_to(REPO_ROOT / "scripts").parent))
    for path in (REPO_ROOT / "scripts").rglob("*.py")
    if "__pycache__" not in path.parts
]
# The launcher's own art (whshr/launcher/theme.py loads it next to the module).
datas += [(str(path), "whshr/launcher/art") for path in (REPO_ROOT / "whshr" / "launcher" / "art").glob("*.png")]
# Application icon PNGs (loaded at runtime next to the whshr package).
datas += [(str(path), "whshr/icons") for path in (REPO_ROOT / "whshr" / "icons").glob("*.png")]

a = Analysis(
    [str(REPO_ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    # zengl's compiled extension (zengl.pyd) imports the pure-Python _zengl module
    # internally; PyInstaller can't see that from a compiled binary and zengl ships no
    # PyInstaller hook of its own, so it must be listed here explicitly (found by actually
    # running the frozen build and hitting ModuleNotFoundError: No module named '_zengl').
    hiddenimports=["_zengl", "whshr._build_version"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ohr-engine",
    icon=str(REPO_ROOT / "whshr" / "icons" / "ohr.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ohr-engine",
)
