"""The third-party notices stay in step with what the packages bundle (GitHub issue #99): every native library the
installed pygame-ce ships is named in the notices, the pinned versions are the audited ones, and every package
installs the license texts the notices rely on."""

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
NOTICES = (PACKAGING / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
LICENSE_FILES = ("LGPL-2.1.txt", "Apache-2.0.txt")
INSTALL_STEPS = (
    PACKAGING / "linux" / "build-appimage.sh", PACKAGING / "linux" / "build-deb.sh",
    PACKAGING / "linux" / "ohr-engine.rpm.spec", PACKAGING / "macos" / "build-pkg.sh",
    PACKAGING / "windows" / "installer.iss",
)


def library_name(filename: str) -> str:
    """The library a wheel file belongs to: no 'lib' prefix, hash, version or extension ('libSDL2-2-50d19f93.0.so.0'
    and 'SDL2.dll' are 'sdl2'; zlib-ng's 'libz.1.3.1.zlib-ng.dylib' is 'zlib')."""
    stem = filename.lower().split(".")[0]
    stem = stem[3:] if stem.startswith("lib") else stem
    stem = re.sub(r"-[0-9a-f]{8}$", "", stem)
    stem = re.sub(r"-\d+$", "", stem)
    return "zlib" if stem == "z" else stem


def documented_libraries() -> set[str]:
    """The library identifiers named (in backticks) in the notices' native-library tables."""
    start = NOTICES.index("## Bundled native libraries")
    section = NOTICES[start:NOTICES.index("## Python, Tcl/Tk and PyInstaller")]
    names = re.findall(r"`([^`]+)`", section)
    return {library_name(name) for name in names if not name.startswith("LICENSE.")}


def bundled_libraries() -> list[str]:
    spec = importlib.util.find_spec("pygame")
    if spec is None or spec.origin is None:
        return []
    package = Path(spec.origin).parent
    files: list[Path] = []
    for folder in (package.parent / "pygame_ce.libs", package / ".dylibs"):
        if folder.is_dir():
            files.extend(folder.iterdir())
    files.extend(package.glob("*.dll"))
    return sorted(file.name for file in files)


class ThirdPartyNoticesTests(unittest.TestCase):
    def test_given_the_installed_pygame_ce_when_listing_its_native_libraries_then_each_is_named_in_the_notices(self):
        libraries = bundled_libraries()
        if not libraries:
            self.skipTest("pygame-ce is not installed here, or its wheel bundles no native libraries")
        documented = documented_libraries()
        missing = sorted({library_name(name) for name in libraries if library_name(name) not in documented})
        self.assertEqual(missing, [], "native libraries missing from packaging/THIRD_PARTY_NOTICES.md")

    def test_given_the_pinned_requirements_then_the_notices_name_the_audited_pygame_ce_version(self):
        pinned = re.search(r"^pygame-ce==([\w.]+)", (ROOT / "requirements-engine.txt").read_text(), re.M)
        self.assertIsNotNone(pinned)
        assert pinned is not None
        self.assertIn(pinned.group(1), NOTICES, "update the audit when pygame-ce is bumped")

    def test_given_each_package_recipe_then_it_installs_every_license_text_the_notices_rely_on(self):
        for recipe in INSTALL_STEPS:
            text = recipe.read_text(encoding="utf-8")
            for name in LICENSE_FILES:
                with self.subTest(recipe=recipe.name, license=name):
                    covered = name in text or (recipe.suffix == ".iss" and "licenses" in text)
                    self.assertTrue(covered)

    def test_given_the_license_texts_then_the_repository_carries_them(self):
        for name in LICENSE_FILES:
            with self.subTest(license=name):
                self.assertGreater((PACKAGING / "licenses" / name).stat().st_size, 5000)
        self.assertIn("Apache License", (PACKAGING / "licenses" / "Apache-2.0.txt").read_text()[:200])

    def test_given_an_undocumented_library_whose_name_is_part_of_a_documented_one_then_it_is_still_missing(self):
        documented = documented_libraries()
        self.assertIn("webp", documented)
        self.assertNotIn(library_name("libweb.so.1"), documented)
        self.assertNotIn(library_name("liblicense.so"), documented)

    def test_given_the_permissive_libraries_then_their_notice_texts_ship_and_every_package_installs_them(self):
        texts = sorted((PACKAGING / "licenses" / "third-party").glob("LICENSE.*.txt"))
        self.assertGreaterEqual(len(texts), 15)
        for text in texts:
            with self.subTest(text=text.name):
                self.assertGreater(text.stat().st_size, 500)
                self.assertIn(text.name, NOTICES)
        for recipe in INSTALL_STEPS:
            with self.subTest(recipe=recipe.name):
                content = recipe.read_text(encoding="utf-8")
                self.assertTrue("third-party" in content or (recipe.suffix == ".iss" and "recursesubdirs" in content))

    def test_given_portmidi_then_the_notices_say_apache_not_mit(self):
        row = next(line for line in NOTICES.splitlines() if "portmidi.dll" in line)
        self.assertIn("Apache", row)
        self.assertNotIn("MIT", row)


if __name__ == "__main__":
    unittest.main()
