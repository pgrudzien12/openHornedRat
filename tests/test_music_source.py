"""The Steam edition's MP3 music can replace the MIDI tracks, chosen in Options (whshr.music_source)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from whshr.glue_content import GlueContent
from whshr.music_source import CD, MIDI, MP3, MusicSourceSetting, has_mp3_music, music_source_setting, music_track
from whshr.options_scene import OptionsScene
from whshr.audio_settings import audio_settings
from whshr.difficulty import difficulty_setting
from whshr.paths import Installation
from whshr.scenes import Scene, SceneMachine


def touch(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def steam_installation(root: Path) -> Installation:
    touch(root, "FILE/BINARY/MUSIC/MIDI/GEN/BATTLE.MID")
    touch(root, "FILE/BINARY/MUSIC/MIDI/GEN/SIGHTED.MID")
    touch(root, "FILE/BINARY/MUSIC/BATTLE.MP3")
    touch(root, "FILE/BINARY/MUSIC/BATTLECD.MP3")
    touch(root, "FILE/BINARY/MUSIC/SIGHTED.MP3")  # no SIGHTEDCD.MP3: the CD choice falls back to MIDI
    return Installation(root)


def gog_installation(root: Path) -> Installation:
    touch(root, "FILE/BINARY/MUSIC/BATTLE.MID")
    touch(root, "FILE/BINARY/MUSIC/BATTLEFM.MID")
    return Installation(root)


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "game"
        self.save_dir = Path(self.directory.name) / "saves"

    def tearDown(self) -> None:
        music_source_setting.configure(None)
        audio_settings.configure(None)
        difficulty_setting.configure(None)
        self.directory.cleanup()


class TrackResolutionTests(Case):
    def test_given_steam_music_then_each_source_plays_its_own_recording(self) -> None:
        game = steam_installation(self.root)
        self.assertEqual(music_track(game, "BATTLE", MIDI).name, "BATTLE.MID")
        self.assertEqual(music_track(game, "BATTLE", MP3).name, "BATTLE.MP3")
        self.assertEqual(music_track(game, "BATTLE", CD).name, "BATTLECD.MP3")

    def test_given_a_glue_track_name_in_lower_case_then_its_recording_is_found(self) -> None:
        self.assertEqual(music_track(steam_installation(self.root), "sighted", MP3).name, "SIGHTED.MP3")

    def test_given_a_missing_recording_then_the_midi_file_plays(self) -> None:
        self.assertEqual(music_track(steam_installation(self.root), "SIGHTED", CD).name, "SIGHTED.MID")

    def test_given_gog_music_then_an_mp3_choice_still_plays_midi(self) -> None:
        self.assertEqual(music_track(gog_installation(self.root), "BATTLE", MP3).name, "BATTLE.MID")

    def test_given_no_source_then_the_saved_choice_is_used(self) -> None:
        game = steam_installation(self.root)
        music_source_setting.source = CD
        self.assertEqual(music_track(game, "BATTLE").name, "BATTLECD.MP3")

    def test_only_an_installation_with_mp3_music_offers_it(self) -> None:
        self.assertTrue(has_mp3_music(steam_installation(self.root / "steam")))
        self.assertFalse(has_mp3_music(gog_installation(self.root / "gog")))
        self.assertFalse(has_mp3_music(None))


class SettingTests(Case):
    def test_given_a_new_player_or_no_save_directory_then_midi_plays(self) -> None:
        setting = MusicSourceSetting()
        setting.configure(self.save_dir)
        self.assertIs(setting.source, MIDI)
        setting.configure(None)
        self.assertIs(setting.source, MIDI)

    def test_given_a_saved_choice_then_it_survives_reloading_and_an_invalid_one_is_midi(self) -> None:
        setting = MusicSourceSetting()
        setting.configure(self.save_dir)
        setting.save(CD)
        reloaded = MusicSourceSetting()
        reloaded.configure(self.save_dir)
        self.assertIs(reloaded.source, CD)
        (self.save_dir / "music.json").write_text('{"source": "cassette"}')
        reloaded.configure(self.save_dir)
        self.assertIs(reloaded.source, MIDI)


class Context:
    def __init__(self, save_dir: Path, installation: Installation | None) -> None:
        self.save_dir = save_dir
        self.content = GlueContent.from_data(resources={"STARTCARAVAN": "[WINDOW]\n[END]"})
        self.content.installation = installation

    def glue_content(self) -> GlueContent:
        return self.content


class OptionsTests(Case):
    def test_given_steam_music_then_options_cycle_midi_mp3_cd_and_ok_saves(self) -> None:
        machine = SceneMachine(OptionsScene(Scene()), Context(self.save_dir, steam_installation(self.root)))
        scene = machine.active
        assert isinstance(scene, OptionsScene)
        self.assertTrue(scene.mp3_music)
        seen = []
        for _ in range(3):
            machine.handle(("options:cycle", "music_source"))
            seen.append(scene.music_source)
        self.assertEqual(seen, [MP3, CD, MIDI])
        machine.handle(("options:cycle", "music_source"))
        machine.handle("options:ok")
        self.assertEqual(json.loads((self.save_dir / "music.json").read_text()), {"source": "mp3"})
        self.assertIs(music_source_setting.source, MP3)

    def test_given_steam_music_when_cancelled_then_the_choice_is_discarded(self) -> None:
        machine = SceneMachine(OptionsScene(Scene()), Context(self.save_dir, steam_installation(self.root)))
        machine.handle(("options:cycle", "music_source"))
        machine.handle("options:cancel")
        self.assertIs(music_source_setting.source, MIDI)
        self.assertFalse((self.save_dir / "music.json").exists())

    def test_given_no_mp3_music_then_the_control_is_absent_and_nothing_is_saved(self) -> None:
        machine = SceneMachine(OptionsScene(Scene()), Context(self.save_dir, gog_installation(self.root)))
        scene = machine.active
        assert isinstance(scene, OptionsScene)
        self.assertFalse(scene.mp3_music)
        machine.handle(("options:cycle", "music_source"))
        self.assertIs(scene.music_source, MIDI)
        machine.handle("options:ok")
        self.assertFalse((self.save_dir / "music.json").exists())


@unittest.skipUnless(importlib.util.find_spec("pygame"), "Pygame is not installed")
class LoopingTuneTests(Case):
    def test_given_a_looping_tune_when_the_source_changes_then_it_restarts_from_the_new_recording(self) -> None:
        from whshr.frontend import music_player

        game = steam_installation(self.root)
        with mock.patch.object(music_player.pygame.mixer, "get_init", return_value=(22050, -16, 2)), \
                mock.patch.object(music_player.pygame.mixer, "music") as channel:
            music_player.play_looping(game, "BATTLE")
            music_player.follow_source_change()  # unchanged: no restart
            self.assertEqual([Path(call.args[0]).name for call in channel.load.call_args_list], ["BATTLE.MID"])
            music_source_setting.source = MP3
            music_player.follow_source_change()
            self.assertEqual(Path(channel.load.call_args.args[0]).name, "BATTLE.MP3")
            channel.play.assert_called_with(loops=-1)
            music_player.forget()
            music_source_setting.source = CD
            music_player.follow_source_change()  # nothing loops: nothing starts
            self.assertEqual(channel.load.call_count, 2)


if __name__ == "__main__":
    unittest.main()
