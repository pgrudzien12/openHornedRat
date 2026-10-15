import unittest

from whshr.cutscene import (
    FilmFades, SpeechSubtitles, movie_number, narration_caption_ids, narration_text, speech_tracks, subtitle_color,
    teleprompter_lines,
)


def _media(rows, fields=5):
    return {"objects": {7: {"evt": {"fields": fields, "rows": rows}}}}


def _track(text_id, speaker, first, last, hold=15, start_ms=0, fields=5, extra=0):
    """Records every 125 ms: current_tick from first to last-1, held `hold` more records, then last."""
    ticks = list(range(first, last)) + [last - 1] * hold + [last]
    rows = []
    for index, tick in enumerate(ticks):
        row = [start_ms + 125 * index, text_id, speaker, first, tick, last]
        if fields == 6:
            row.append(extra)
        rows.append(row)
    return {"evt": {"fields": fields, "rows": rows}}


def _fits_chars(limit):
    return lambda line: len(line) < limit


WIZARD = "Wizard: Prepare to die, sewer fiend!"


class SpeechSubtitleTests(unittest.TestCase):
    """notes/cutscene_subtitles.md: two blocks, typed by current_tick, stacked, scrolling."""

    def test_given_a_speaker_slot_then_it_only_picks_the_colour(self):
        self.assertEqual([subtitle_color(code) for code in (2, 3, 4)], [(255, 0, 0), (0, 255, 0), (0, 0, 255)])

    def test_given_the_a1_1010_vector_then_characters_follow_current_tick(self):
        # first 230, last 251, 36 characters, denominator 20; the first record is at 28.625 s
        subtitles = SpeechSubtitles({"objects": {1: _track(1010, 2, 230, 251, start_ms=28625)}}, {1010: WIZARD})
        fits = _fits_chars(100)

        self.assertEqual(subtitles.at(28.6, fits), (None, None))
        self.assertEqual(subtitles.at(28.625, fits)[0].bottom, "")  # shown, empty
        self.assertEqual(subtitles.at(28.75, fits)[0].bottom, "W")
        self.assertEqual(subtitles.at(30.0, fits)[0].bottom, "Wizard: Prepare to ")  # c = 241: 19 characters
        self.assertEqual(subtitles.at(31.125, fits)[0].bottom, WIZARD)
        self.assertEqual(subtitles.at(33.0, fits)[0].bottom, WIZARD)  # the hold
        self.assertEqual(subtitles.at(33.125, fits), (None, None))  # the clearing record
        self.assertEqual(subtitles.at(28.75, fits)[0].color, (255, 0, 0))

    def test_given_overlapping_tracks_then_they_stack_and_a_later_line_reuses_the_upper_block(self):
        media = {"objects": {
            1: _track(1020, 3, 306, 312, hold=4, start_ms=0),      # 0 .. 1.25 s
            2: _track(1030, 4, 315, 330, hold=2, start_ms=500),    # 0.5 .. 2.75 s
            3: _track(1040, 2, 375, 380, start_ms=3000),           # after both
        }}
        subtitles = SpeechSubtitles(media, {1020: "a", 1030: "b", 1040: "c"})

        self.assertEqual([subtitles.blocks[i] for i in range(3)], [0, 1, 0])
        upper, lower = subtitles.at(0.6, _fits_chars(100))
        self.assertIsNotNone(upper)
        self.assertEqual(lower.color, (0, 0, 255))

    def test_given_a_word_that_does_not_fit_then_it_starts_a_new_bottom_line_before_its_first_letter(self):
        text = "one two three"
        fits = _fits_chars(8)  # "one two" (7) fits, "one two three" does not
        self.assertEqual(teleprompter_lines(text, 8, fits), ("", "one two "))
        self.assertEqual(teleprompter_lines(text, 9, fits), ("one two", "t"))

    def test_given_a_long_speech_then_only_its_last_two_lines_are_visible(self):
        text = "aaa bbb ccc ddd"
        self.assertEqual(teleprompter_lines(text, len(text), _fits_chars(5)), ("ccc", "ddd"))

    def test_given_the_a13_six_field_vector_then_the_joined_text_is_typed_as_one(self):
        first, last = 125, 467
        media = {"objects": {1: _track(13030, 2, first, last, fields=6, extra=1)}}
        strings = {13030: "x" * 456 + " ", 13031: "y" * 112}
        (track,) = speech_tracks(media, strings)
        self.assertEqual(len(track.text), 569)
        self.assertEqual(track.visible_count((200 - first) * 0.125), 125)  # trunc(569 * 75 / 341)


class NarrationCaptionTests(unittest.TestCase):
    """The page before a film, from its name alone (notes/cutscene_narration.md 2, test vectors 5)."""

    def test_given_film_names_then_their_numbers_ignore_trailing_letters(self):
        self.assertEqual([movie_number(name) for name in ("A1", "A12b", "a16A", "A18B", "DEATH01")],
                         [1, 12, 16, 18, 0])

    def test_given_the_report_vectors_then_each_film_gets_its_row(self):
        expected = {
            "A1": (1100, 1101, 1102), "A12b": (12100,), "A12": (12100,), "A13": (13200,),
            "A16a": (16100,), "A16b": (16600, 16601), "A18B": (18100, 18101), "A20": (20100,),
            "A27": (27100, 27101, 27102, 27103), "A9": (), "A14": (), "DEATH01": (), "DEATH02": (),
        }
        for film, ids in expected.items():
            with self.subTest(film=film):
                self.assertEqual(narration_caption_ids(film), ids)

    def test_given_captions_then_the_page_joins_them_with_no_separator(self):
        strings = {3100: "In the Badlands, ", 3101: "a warlord stirs ", 3102: "again..."}
        self.assertEqual(narration_text("A3", strings), "In the Badlands, a warlord stirs again...")
        self.assertEqual(narration_text("A9", strings), "")


class FilmFadeTests(unittest.TestCase):
    """The film's own fades (notes/cutscene_narration.md 4.3)."""

    MEDIA = {"objects": {
        7: {"evt": {"fields": 1, "rows": [[12500, 98], [12625, 96], [18625, 0]]}},
        8: {"evt": {"fields": 2, "rows": [[4000, 10, 10]]}},
    }}

    def test_given_anim_done_then_each_record_sets_the_volume_and_darkens_by_five(self):
        fades = FilmFades(self.MEDIA)
        times = (0.0, 12.499, 12.5, 12.7, 20.0)
        self.assertEqual([fades.volume(t) for t in times], [100, 100, 98, 96, 0])
        self.assertEqual([fades.darken(t) for t in times], [0, 0, 5, 10, 15])

    def test_given_the_fade_marker_then_only_a_skip_after_it_and_before_the_end_fade_fades(self):
        fades = FilmFades(self.MEDIA)
        self.assertFalse(fades.skip_fades(3.9))
        self.assertTrue(fades.skip_fades(4.0))
        self.assertTrue(fades.skip_fades(12.499))
        self.assertFalse(fades.skip_fades(12.5))  # the first AnimDone record removes the mark
        self.assertFalse(FilmFades({}).skip_fades(10.0))

    def test_given_the_skip_fade_then_each_step_darkens_by_16_and_then_lowers_the_volume(self):
        steps = [FilmFades.skip_step(k) for k in range(1, 11)]
        self.assertEqual([volume for _, volume in steps], [100, 90, 80, 70, 60, 50, 40, 30, 20, 10])
        colour = (200, 120, 40)  # the report's vector
        dimmed = [tuple(max(0, c - darken) for c in colour) for darken, _ in steps]
        self.assertEqual(dimmed[:3], [(184, 104, 24), (168, 88, 8), (152, 72, 0)])
        self.assertEqual(dimmed[-1], (40, 0, 0))

if __name__ == "__main__":
    unittest.main()
