"""Unpacking the game from a GOG installer with innoextract (faked here by a small script)."""

import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from whshr.launcher import gog_installer

FAKE_INNOEXTRACT = textwrap.dedent('''\
    #!{python}
    """Stands in for innoextract: lists or "unpacks" a three-file game, or fails on request."""
    import os, sys
    from pathlib import Path
    args = sys.argv[1:]
    if os.environ.get("FAKE_INNOEXTRACT_FAIL"):
        print("Not a supported Inno Setup installer!")
        sys.exit(1)
    files = [] if os.environ.get("FAKE_INNOEXTRACT_EMPTY") else [
        "WARFB/FILE/BINARY/STANDARD.PAL", "WARFB/REMOTE/BINARY/INTRO.SI", "WARFB/GAMEF.DLL"]
    if "--list" in args:
        for name in files:
            print(f' - "{{name}}" [en-US]')
        sys.exit(0)
    target = Path(args[args.index("--output-dir") + 1])
    print('Extracting "Game" - setup data version 5.6.2 (unicode)')
    (target / "app" / "WARFB" / "FILE" / "MESH" / "SCENERY").mkdir(parents=True, exist_ok=True)
    print(' - "app/WARFB/FILE/MESH/SCENERY/"')
    for name in files:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(b"data")
        print(f' - "{{name}}" [en-US]')
    print("Done.")
''')


def write_fake_innoextract(folder: Path) -> Path:
    script = folder / "innoextract"
    script.write_text(FAKE_INNOEXTRACT.format(python=sys.executable), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@unittest.skipIf(sys.platform == "win32", "the fake innoextract is a script run through its #! line")
class GogInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "bin").mkdir()
        self.innoextract = str(write_fake_innoextract(self.root / "bin"))
        self.installer = self.root / "setup_game.exe"
        self.installer.write_bytes(b"MZ")
        self.environ = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.environ)
        self.temporary.cleanup()

    def test_given_a_gog_installer_when_unpacked_then_the_installation_is_returned_with_full_progress(self):
        progress = []

        game = gog_installer.extract(self.innoextract, self.installer, self.root / "game",
                                     lambda done, total: progress.append((done, total)))

        self.assertEqual(game, self.root / "game" / "WARFB")
        self.assertEqual(progress, [(1, 3), (2, 3), (3, 3)])
        self.assertFalse((self.root / "game" / "app").exists(), "the empty folder copy is cleaned up")

    def test_given_innoextract_fails_when_unpacking_then_the_error_carries_its_output(self):
        os.environ["FAKE_INNOEXTRACT_FAIL"] = "1"

        with self.assertRaises(gog_installer.ExtractionFailed) as raised:
            gog_installer.extract(self.innoextract, self.installer, self.root / "game")

        self.assertIn("Not a supported Inno Setup installer!", str(raised.exception))

    def test_given_an_installer_without_the_game_folder_when_unpacking_then_nothing_is_extracted(self):
        os.environ["FAKE_INNOEXTRACT_EMPTY"] = "1"

        with self.assertRaises(gog_installer.ExtractionFailed):
            gog_installer.extract(self.innoextract, self.installer, self.root / "game")

        self.assertEqual(list((self.root / "game").iterdir()), [])

    def test_given_innoextract_on_the_search_path_when_looking_for_it_then_it_is_found(self):
        self.assertEqual(gog_installer.find_innoextract(search_path=str(self.root / "bin")), self.innoextract)
        self.assertIsNone(gog_installer.find_innoextract(search_path=str(self.root / "missing")))

    def test_given_innoextract_bundled_beside_the_launcher_when_looking_for_it_then_the_bundled_one_wins(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        bundled = write_fake_innoextract(bundle)

        found = gog_installer.find_innoextract(search_path=str(self.root / "bin"),
                                               executable=str(bundle / "ohr-engine"))

        self.assertEqual(found, str(bundled))


class InstallHintTests(unittest.TestCase):
    def test_given_each_platform_when_innoextract_is_missing_then_the_hint_names_a_way_to_get_it(self):
        self.assertIn("brew install innoextract", gog_installer.install_hint("darwin"))
        self.assertIn("apt install innoextract", gog_installer.install_hint("linux"))


if __name__ == "__main__":
    unittest.main()
