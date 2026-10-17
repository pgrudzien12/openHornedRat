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

    def test_given_the_steam_editions_merged_layout_when_checked_then_it_looks_like_an_installation(self):
        self._write("FILE/BINARY/STANDARD.PAL")
        self._write("FILE/BINARY/ANIM/Intro.SI")

        self.assertTrue(discovery.looks_like_installation(self.root))

    def test_given_the_steam_edition_in_its_library_when_discovering_from_home_then_its_game_root_is_found(self):
        game = self.root / ".local/share/Steam/steamapps/common/Warhammer Shadow of the Horned Rat"
        self._write(f"{game.relative_to(self.root)}/FILE/BINARY/STANDARD.PAL")
        self._write(f"{game.relative_to(self.root)}/FILE/BINARY/ANIM/Intro.SI")

        found = discovery.discover_installations(home=self.root, platform="linux", environ={})

        self.assertEqual(found, [game])

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

    def _install_game(self, relative: str) -> Path:
        game = self.root / relative
        (game / "FILE" / "BINARY").mkdir(parents=True)
        (game / "REMOTE" / "BINARY").mkdir(parents=True)
        return game

    def test_given_a_game_in_a_typical_location_when_discovering_from_home_then_it_is_found(self):
        gog_folder = "Warhammer - Shadow of the Horned Rat/WARFB"
        layouts = {
            "GOG folder in home": ("linux", f"GOG Games/{gog_folder}"),
            "Proton prefix of snap Steam": (
                "linux", f"snap/steam/common/.local/share/Steam/steamapps/compatdata/123/pfx/drive_c/GOG Games/{gog_folder}"),
            "Proton prefix with GOG Galaxy": (
                "linux", f".local/share/Steam/steamapps/compatdata/9/pfx/drive_c/Program Files (x86)/GOG Galaxy/Games/{gog_folder}"),
            "Flatpak Steam library": (
                "linux", ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Horned Rat"),
            "default Wine prefix": ("linux", f".wine/drive_c/GOG Games/{gog_folder}"),
            "Lutris prefix": ("linux", f"Games/warhammer-horned-rat/drive_c/GOG Games/{gog_folder}"),
            "Bottles bottle": ("linux", f".local/share/bottles/bottles/Games/drive_c/GOG Games/{gog_folder}"),
            "Heroic install": ("linux", f"Games/Heroic/{gog_folder}"),
            "macOS Steam library": ("darwin", "Library/Application Support/Steam/steamapps/common/Horned Rat"),
            "unpacked by the launcher on Linux": ("linux", ".local/share/ohr/game/WARFB"),
            "unpacked by the launcher on macOS": ("darwin", "Library/Application Support/ohr/game/WARFB"),
        }
        for name, (platform, relative) in layouts.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as home:
                self.root = Path(home)
                game = self._install_game(relative)

                found = discovery.discover_installations(home=self.root, platform=platform, environ={})

                self.assertEqual(found, [game])

    def test_given_xdg_data_home_when_discovering_then_the_game_unpacked_there_is_found_first(self):
        unpacked = self._install_game("data/ohr/game/WARFB")
        gog = self._install_game("GOG Games/Warhammer - Shadow of the Horned Rat/WARFB")

        found = discovery.discover_installations(home=self.root, platform="linux",
                                                 environ={"XDG_DATA_HOME": str(self.root / "data")})

        self.assertEqual(found, [unpacked, gog])

    def test_given_a_steam_root_reachable_through_a_symlink_when_discovering_then_the_game_is_listed_once(self):
        game = self._install_game(".local/share/Steam/steamapps/common/Horned Rat")
        (self.root / ".steam").mkdir()
        (self.root / ".steam" / "steam").symlink_to(self.root / ".local/share/Steam")

        found = discovery.discover_installations(home=self.root, platform="linux", environ={})

        self.assertEqual(found, [game])

    def test_given_a_game_folder_without_the_game_data_when_discovering_then_nothing_is_found(self):
        (self.root / "GOG Games" / "Warhammer - Shadow of the Horned Rat" / "WARFB" / "FILE").mkdir(parents=True)

        self.assertEqual(discovery.discover_installations(home=self.root, platform="linux", environ={}), [])
