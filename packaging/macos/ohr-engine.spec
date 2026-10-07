"""Windowed macOS app with the launcher and engine in one onedir bundle."""

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parents[1]
datas = [
    (str(path), str(Path("scripts") / path.relative_to(REPO_ROOT / "scripts").parent))
    for path in (REPO_ROOT / "scripts").rglob("*.py")
    if "__pycache__" not in path.parts
]

a = Analysis(
    [str(REPO_ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["_zengl"],
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
    bundle_identifier="org.openhornedrat.launcher",
    info_plist={"CFBundleDisplayName": "Open Horned Rat", "NSPrincipalClass": "NSApplication"},
)
