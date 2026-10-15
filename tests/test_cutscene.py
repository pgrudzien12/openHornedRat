import unittest

from whshr.cutscene import SubtitleTimeline, movie_number, narration_caption_ids, narration_text, subtitle_color


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
    """The text page before a film: its M100... captions (notes/pe_resources.md "ANTXT")."""

    STRINGS = {3010: "Urgat: speech", 3100: "In the Badlands ", 3101: "a warlord stirs. ", 3510: "alt speech",
               13100: "timed caption", 13200: "Meanwhile... ", 4100: "Elsewhere. ", 30000: "You were killed."}

    def test_given_movie_names_then_their_numbers_ignore_the_version_letter(self):
        self.assertEqual([movie_number(name) for name in ("a1", "A12b", "a16A", "DEATH01", "")],
                         [1, 12, 16, None, None])

    def test_given_a_film_then_its_captions_are_its_hundreds_not_its_speech_or_alternative_lines(self):
        self.assertEqual(narration_caption_ids("A3", self.STRINGS, {}), (3100, 3101))
        self.assertEqual(narration_text("A3", self.STRINGS, {}), "In the Badlands a warlord stirs.")

    def test_given_a_caption_the_film_already_times_then_only_the_rest_go_on_the_page(self):
        media = _media([[0, 13100, 2, 0, 0, 4]])
        self.assertEqual(narration_caption_ids("A13", self.STRINGS, media), (13200,))

    def test_given_a_film_without_captions_or_number_then_there_is_no_page(self):
        self.assertEqual(narration_text("A14", self.STRINGS, {}), "")
        self.assertEqual(narration_text("DEATH01", self.STRINGS, {}), "")


if __name__ == "__main__":
    unittest.main()
