import unittest

from whshr.cutscene import SubtitleTimeline


def _media(rows, fields=5):
    return {"objects": {7: {"evt": {"fields": fields, "rows": rows}}}}


class SubtitleTimelineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
