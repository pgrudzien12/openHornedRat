"""Glue speech recordings are found, repaired and played when a line is spoken (notes/briefing_dialogue.md §3.2)."""
import io
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput, GlueRuntime, HotspotSpeech, PlaySpeech, StopSpeech
from whshr.paths import Installation
from whshr.speech import canonical_wav, load_speech, speech_path

PCM = struct.pack("<8h", 1, -2, 3, -4, 5, -6, 7, -8)


def original_style_wav(pcm=PCM, riff_size=999999):
    """A clip as shipped: the RIFF size field is wrong, the data chunk length is right."""
    fmt = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, 22050, 44100, 2, 16)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm


class SpeechFileTests(unittest.TestCase):
    def test_given_a_clip_with_a_wrong_riff_size_when_repaired_then_it_reads_back_with_all_its_samples(self):
        for riff_size in (0, 999999):
            with self.subTest(riff_size=riff_size):
                fixed = canonical_wav(original_style_wav(riff_size=riff_size))

                with wave.open(io.BytesIO(fixed)) as reader:
                    self.assertEqual((reader.getnchannels(), reader.getsampwidth(), reader.getframerate()), (1, 2, 22050))
                    self.assertEqual(reader.readframes(reader.getnframes()), PCM)

    def test_given_a_data_chunk_longer_than_the_file_then_the_available_samples_are_kept(self):
        data = original_style_wav()[:-3]  # cut in the middle of the last sample

        with wave.open(io.BytesIO(canonical_wav(data))) as reader:
            self.assertEqual(reader.getnframes(), 6)  # 13 bytes left: six whole samples

    def test_given_something_that_is_not_a_pcm_wav_then_it_is_refused(self):
        self.assertIsNone(canonical_wav(b"not a wave file at all"))
        compressed = original_style_wav().replace(struct.pack("<H", 1) + struct.pack("<H", 1), struct.pack("<H", 2) + struct.pack("<H", 1), 1)
        self.assertIsNone(canonical_wav(compressed))

    def test_given_an_installation_then_a_line_is_found_case_insensitively_and_missing_lines_give_none(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "REMOTE" / "BINARY" / "GLUE" / "SPEECH"
            folder.mkdir(parents=True)
            (folder / "B931.WAV").write_bytes(original_style_wav())
            game = Installation(directory)

            self.assertEqual(speech_path(game, 931).name, "B931.WAV")
            self.assertIsNotNone(load_speech(game, 931))
            self.assertIsNone(speech_path(game, 932))
            self.assertIsNone(load_speech(game, 932))

    def test_given_an_installation_without_speech_then_nothing_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(speech_path(Installation(directory), 931))


RESOURCES = {
    "CARAVAN": "[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n[END]",
    "SCRIPT": "[RUN]\n[START]\nopenwindow:res=CARAVAN\nwaitforresume:\n[END]",
}


class SpokenLineEffectTests(unittest.TestCase):
    def _runtime(self, speech_enabled=True):
        content = GlueContent.from_data(resources=RESOURCES, strings={"BRTXT": {931: "one", 932: "two", 933: "three"}})
        runtime = GlueRuntime(content, speech_enabled=speech_enabled)
        runtime.start("SCRIPT")
        return runtime

    def test_given_a_click_speech_when_it_starts_then_the_first_recording_is_played(self):
        effects = self._runtime().handle(GlueInput("hotspot-speech", "931:3"))

        self.assertEqual(effects, (HotspotSpeech(931, 3), PlaySpeech(931)))

    def test_given_a_click_speech_when_each_line_finishes_then_the_next_recording_starts(self):
        runtime = self._runtime()
        runtime.handle(GlueInput("hotspot-speech", "931:3"))
        played = []

        for _ in range(400):
            played += [effect.string_id for effect in runtime.tick(100) if isinstance(effect, PlaySpeech)]

        self.assertEqual(played, [932, 933])

    def test_given_speech_is_off_then_the_text_is_shown_but_no_recording_is_played(self):
        runtime = self._runtime(speech_enabled=False)

        effects = runtime.handle(GlueInput("hotspot-speech", "931:2"))

        self.assertFalse(any(isinstance(effect, PlaySpeech) for effect in effects))
        self.assertEqual(runtime.state.dialogue_text, "one")


class PacedByRecordingTests(unittest.TestCase):
    """A spoken line lasts as long as its recording, so the next line never cuts it off."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name) / "REMOTE" / "BINARY" / "GLUE" / "SPEECH"
        folder.mkdir(parents=True)
        for string_id, seconds in ((931, 2), (932, 3)):  # mono 16-bit 22 050 Hz
            (folder / f"B{string_id}.WAV").write_bytes(original_style_wav(bytes(2 * 22050 * seconds)))
        content = GlueContent(temporary.name, resources=RESOURCES, strings={"BRTXT": {931: "one two", 932: "three", 933: "x"}})
        self.runtime = GlueRuntime(content)
        self.runtime.start("SCRIPT")

    def _played_at(self, milliseconds_per_tick=50, total=8000):
        """{string id: time of the PlaySpeech effect} while the click speech 931:3 runs."""
        times = {}
        effects = self.runtime.handle(GlueInput("hotspot-speech", "931:3"))
        elapsed = 0
        for effect in effects:
            if isinstance(effect, PlaySpeech):
                times[effect.string_id] = elapsed
        while elapsed < total:
            elapsed += milliseconds_per_tick
            for effect in self.runtime.tick(milliseconds_per_tick):
                if isinstance(effect, PlaySpeech):
                    times[effect.string_id] = elapsed
        return times

    def test_given_recordings_then_each_line_starts_only_after_the_previous_clip_and_its_short_hold(self):
        times = self._played_at()

        self.assertEqual(times[931], 0)
        self.assertGreaterEqual(times[932], 2000 + 200)  # the 2 s clip plus the 8-tick hold
        self.assertLess(times[932], 2000 + 200 + 100)
        self.assertGreaterEqual(times[933] - times[932], 3000 + 200)

    def test_given_a_recording_then_the_text_is_typed_along_with_it(self):
        self.runtime.handle(GlueInput("hotspot-speech", "931:1"))

        self.runtime.tick(1000)  # half of the 2 s clip
        half = self.runtime.state.dialogue_typed
        self.runtime.tick(1000)
        full = self.runtime.state.dialogue_typed

        self.assertEqual(half, len("one two") // 2)
        self.assertEqual(full, len("one two"))

    def test_given_a_line_without_a_recording_then_the_text_sets_the_pace_as_before(self):
        self.runtime.handle(GlueInput("hotspot-speech", "933:1"))

        self.assertEqual(self.runtime.state.dialogue_clip_ms, 0)
        self.runtime.tick(50)
        self.assertEqual(self.runtime.state.dialogue_typed, 1)


class ClickThroughTests(unittest.TestCase):
    """A click while a hotspot speech plays skips to the next line: new sound, new text."""

    def _runtime(self):
        content = GlueContent.from_data(resources=RESOURCES, strings={"BRTXT": {931: "one", 932: "two", 933: "three"}})
        runtime = GlueRuntime(content)
        runtime.start("SCRIPT")
        return runtime

    def test_given_a_line_in_progress_when_the_player_clicks_then_the_next_line_plays_and_is_shown(self):
        runtime = self._runtime()
        runtime.handle(GlueInput("hotspot-speech", "931:3"))
        runtime.tick(50)

        effects = runtime.handle(GlueInput("dialogue-drain"))  # a click on the empty window; another click on Dietrich is ignored

        self.assertEqual(effects, (PlaySpeech(932),))
        self.assertEqual(runtime.state.dialogue_text, "two")
        self.assertEqual(runtime.state.dialogue_typed, 0)  # the new line types from its start
        self.assertTrue(runtime.state.speech_active)

    def test_given_the_last_line_when_the_player_clicks_then_the_speech_stops_and_the_box_clears(self):
        runtime = self._runtime()
        runtime.handle(GlueInput("hotspot-speech", "932:1"))

        effects = runtime.handle(GlueInput("dialogue-drain"))

        self.assertEqual(effects, (StopSpeech(),))
        self.assertFalse(runtime.state.speech_active)
        self.assertEqual(runtime.state.dialogue_text, "")

    def test_given_repeated_clicks_then_every_line_is_reached_in_order_and_then_it_ends(self):
        runtime = self._runtime()
        runtime.handle(GlueInput("hotspot-speech", "931:3"))
        heard = []

        while runtime.state.speech_active:
            heard += [effect.string_id for effect in runtime.handle(GlueInput("dialogue-drain")) if isinstance(effect, PlaySpeech)]

        self.assertEqual(heard, [932, 933])

    def test_given_speech_still_running_when_it_is_cut_off_then_clip_and_text_stop(self):
        runtime = self._runtime()
        runtime.handle(GlueInput("hotspot-speech", "931:3"))

        self.assertEqual(runtime.stop_speech(), (StopSpeech(),))
        self.assertEqual((runtime.state.speech_active, runtime.state.speech_lines, runtime.state.dialogue_text), (False, (), ""))
        self.assertEqual(runtime.stop_speech(), ())  # nothing running: nothing to stop

    def test_given_a_skip_then_the_timing_of_the_new_line_starts_from_zero(self):
        runtime = self._runtime()
        runtime.handle(GlueInput("hotspot-speech", "931:2"))
        runtime.tick(300)

        runtime.handle(GlueInput("dialogue-drain"))

        self.assertEqual(runtime.state.dialogue_ms, 0)


if __name__ == "__main__":
    unittest.main()
