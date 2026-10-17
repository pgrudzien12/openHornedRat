"""Files resolve in both the GOG layout and the Steam "Classic" edition's merged layout (notes/steam_edition.md)."""
import tempfile
import unittest
from pathlib import Path

from whshr.paths import Installation


def touch(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


class LayoutCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class GogLayoutTests(LayoutCase):
    def setUp(self) -> None:
        super().setUp()
        self.gm = touch(self.root, "FILE/BINARY/MUSIC/BATTLE.MID")
        self.fm = touch(self.root, "FILE/BINARY/MUSIC/BATTLEFM.MID")
        self.film = touch(self.root, "REMOTE/BINARY/ANIM/INTRO.SI")
        touch(self.root, "FILE/BINARY/ANIM/OTHER.SI")

    def test_given_gog_music_then_both_families_resolve_in_music(self) -> None:
        game = Installation(self.root)
        self.assertEqual(game.binary_file("MUSIC", "BATTLE.MID"), self.gm)
        self.assertEqual(game.binary_file("MUSIC", "BATTLEFM.MID"), self.fm)
        self.assertEqual(game.music_dir(), self.gm.parent)

    def test_given_a_remote_folder_then_remote_lookups_use_it(self) -> None:
        self.assertEqual(Installation(self.root).remote_dir("BINARY", "ANIM"), self.film.parent)


class SteamLayoutTests(LayoutCase):
    def setUp(self) -> None:
        super().setUp()
        self.gm = touch(self.root, "FILE/BINARY/MUSIC/MIDI/GEN/BATTLE.MID")
        self.fm = touch(self.root, "FILE/BINARY/MUSIC/MIDI/BATTLEFM.MID")
        touch(self.root, "FILE/BINARY/MUSIC/BATTLE.MP3")
        self.film = touch(self.root, "FILE/BINARY/ANIM/INTRO.SI")

    def test_given_steam_music_then_general_midi_tracks_resolve_in_gen(self) -> None:
        self.assertEqual(Installation(self.root).binary_file("MUSIC", "battle.mid"), self.gm)

    def test_given_steam_music_then_fm_tracks_resolve_in_midi(self) -> None:
        self.assertEqual(Installation(self.root).binary_file("MUSIC", "BATTLEFM.MID"), self.fm)

    def test_given_steam_music_then_the_music_folder_is_the_general_midi_one(self) -> None:
        self.assertEqual(Installation(self.root).music_dir(), self.gm.parent)

    def test_given_no_remote_folder_then_remote_lookups_fall_back_to_file(self) -> None:
        game = Installation(self.root)
        self.assertEqual(game.remote_dir("BINARY", "ANIM"), self.film.parent)
        self.assertEqual(game.remote_find("BINARY", "ANIM"), self.film.parent)

    def test_given_a_missing_track_then_lookup_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            Installation(self.root).binary_file("MUSIC", "NOSUCH.MID")


if __name__ == "__main__":
    unittest.main()
