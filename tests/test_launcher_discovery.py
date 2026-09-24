import tempfile
import unittest
from pathlib import Path
from unittest import mock

from whshr.launcher import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative, content=b"data"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_given_directory_with_file_and_remote_binary_when_checked_then_it_looks_like_an_installation(self):
        self._write("FILE/BINARY/STANDARD.PAL")
        self._write("REMOTE/BINARY/ANIM/Intro.SI")

        self.assertTrue(discovery.looks_like_installation(self.root))

    def test_given_directory_missing_remote_binary_when_checked_then_it_does_not_look_like_an_installation(self):
        self._write("FILE/BINARY/STANDARD.PAL")

        self.assertFalse(discovery.looks_like_installation(self.root))

    def test_given_nonexistent_directory_when_checked_then_it_does_not_look_like_an_installation(self):
        self.assertFalse(discovery.looks_like_installation(self.root / "missing"))

    def test_given_a_valid_installation_among_plain_folders_when_discovering_then_only_it_is_found(self):
        valid = self.root / "GOG Games" / "Warhammer Shadow of the Horned Rat"
        (valid / "FILE" / "BINARY").mkdir(parents=True)
        (valid / "REMOTE" / "BINARY").mkdir(parents=True)
        (self.root / "GOG Games" / "Some Other Game").mkdir(parents=True)

        with mock.patch.object(discovery, "candidate_parents", return_value=[self.root / "GOG Games"]):
            found = discovery.discover_installations()

        self.assertEqual(found, [valid])

    def test_given_libraryfolders_vdf_when_parsed_then_every_configured_library_path_is_returned(self):
        steam_root = self.root / "Steam"
        self._write(
            "Steam/steamapps/libraryfolders.vdf",
            b'"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"D:\\\\SteamLibrary"\n\t}\n}\n',
        )

        roots = discovery._steam_library_roots(steam_root)

        self.assertIn(steam_root, roots)
        self.assertIn(Path("D:\\SteamLibrary"), roots)
