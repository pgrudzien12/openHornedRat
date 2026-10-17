"""Windowed macOS app with the launcher and engine in one onedir bundle."""

from pathlib import Path

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
    hiddenimports=["_zengl", "whshr._build_version"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ohr-engine",
    console=False,
    strip=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ohr-engine",
    strip=False,
    upx=False,
)
app = BUNDLE(
    coll,
    name="Open Horned Rat.app",
    icon=str(REPO_ROOT / "whshr" / "icons" / "ohr.icns"),
    bundle_identifier="org.openhornedrat.launcher",
    info_plist={"CFBundleDisplayName": "Open Horned Rat", "NSPrincipalClass": "NSApplication"},
)
