import unittest

from whshr.cutscene import FilmFades, SubtitleTimeline, movie_number, narration_caption_ids, narration_text, subtitle_color


def _media(rows, fields=5):
    return {"objects": {7: {"evt": {"fields": fields, "rows": rows}}}}


class SubtitleTimelineTests(unittest.TestCase):
    def test_given_a_speaker_slot_when_its_color_is_requested_then_it_uses_a_primary_rgb_color(self):
        self.assertEqual(subtitle_color(2), (255, 0, 0))
        self.assertEqual(subtitle_color(3), (0, 255, 0))
        self.assertEqual(subtitle_color(4), (0, 0, 255))
        self.assertEqual(subtitle_color(99), (255, 255, 255))

    def test_given_a_speech_event_when_its_interval_is_active_then_text_is_revealed_over_its_ticks(self):
        timeline = SubtitleTimeline(
            _media([[1000, 1010, 2, 8, 8, 10], [1125, 1010, 2, 8, 9, 10],
                    [1250, 1010, 2, 8, 10, 10]]),
            {1010: "Wizard"},
        )

        self.assertEqual(timeline.cues[0].start_seconds, 1.0)
        self.assertEqual(timeline.cues[0].reveal_end_seconds, 1.3)
        self.assertEqual(timeline.cues[0].end_seconds, 2.375)
        self.assertEqual(timeline.text_at(0.999), "")
        self.assertEqual(timeline.text_at(1.0), "W")
        self.assertEqual(timeline.text_at(1.125), "Wiz")
        self.assertEqual(timeline.text_at(1.30), "Wizard")
        self.assertEqual(timeline.text_at(2.374), "Wizard")
        self.assertEqual(timeline.text_at(2.375), "")

    def test_given_overlapping_events_when_queried_then_the_newer_line_replaces_the_old_one(self):
        timeline = SubtitleTimeline(
            {"objects": {
                1: {"evt": {"fields": 5, "rows": [[1000, 1010, 2, 8, 8, 11], [1375, 1010, 2, 8, 11, 11]]}},
                2: {"evt": {"fields": 5, "rows": [[1125, 1020, 3, 9, 9, 10], [1250, 1020, 3, 9, 10, 10]]}},
            }}, {1010: "Older", 1020: "New"},
        )

        self.assertEqual(timeline.current(1.2).text_id, 1020)

    def test_given_a_non_subtitle_event_or_unknown_string_when_built_then_it_is_ignored(self):
        timeline = SubtitleTimeline(
            {"objects": {
                1: {"evt": {"fields": 2, "rows": [[1000, 10, 10]]}},
                2: {"evt": {"fields": 5, "rows": [[1000, 9999, 2, 8, 8, 8]]}},
            }}, {1010: "Known"},
        )

        self.assertEqual(timeline.cues, ())


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

    def test_given_a_six_field_speech_track_then_its_line_and_the_next_id_are_one_subtitle(self):
        timeline = SubtitleTimeline(_media([[0, 13030, 2, 0, 0, 4, 1]], fields=6),
                                    {13030: "Ungrunn: First part, ", 13031: "second part."})
        self.assertEqual(timeline.cues[0].text, "Ungrunn: First part, second part.")


class FilmFadeTests(unittest.TestCase):
    """The film's own fades (notes/cutscene_narration.md 4.3)."""

    MEDIA = {"objects": {
        7: {"evt": {"fields": 1, "rows": [[12500, 98], [12625, 96], [18625, 0]]}},
        8: {"evt": {"fields": 2, "rows": [[4000, 10, 10]]}},
    }}

    def test_given_anim_done_then_the_level_follows_its_records(self):
        fades = FilmFades(self.MEDIA)
        self.assertEqual([fades.level(t) for t in (0.0, 12.499, 12.5, 12.7, 20.0)], [100, 100, 98, 96, 0])

    def test_given_the_fade_marker_then_only_a_skip_after_it_fades(self):
        fades = FilmFades(self.MEDIA)
        self.assertFalse(fades.skip_fades(3.9))
        self.assertTrue(fades.skip_fades(4.0))
        self.assertFalse(FilmFades({}).skip_fades(10.0))


if __name__ == "__main__":
    unittest.main()
