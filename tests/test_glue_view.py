import importlib.util
import unittest

from whshr.glue_render import GlueRenderModel, RenderBitmap, RenderHotspot, RenderMissionList
from whshr.glue import MissionRef
from whshr.glue_render import RenderText
from whshr.glue_content import GlueContent


@unittest.skipUnless(importlib.util.find_spec("pygame"), "Pygame is not installed in the headless test environment")
class GlueViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from whshr.frontend.glue_view import GlueView
        cls.view_type = GlueView

    def test_hit_testing_uses_topmost_window_then_last_hotspot(self):
        bottom = GlueRenderModel("BOTTOM", 0, 0, 640, 480, 0, (), (), (
            RenderHotspot(0, 0, 20, 20, None, "bottom", None, None, None),
        ), (), ())
        top = GlueRenderModel("TOP", 5, 5, 100, 100, 0, (), (), (
            RenderHotspot(0, 0, 20, 20, None, "top-first", None, None, None),
            RenderHotspot(0, 0, 20, 20, None, "top-last", None, None, None),
        ), (), ())

        hit = self.view_type.hotspot_at((bottom, top), (8, 8))

        self.assertEqual(hit.target, "top-last")

    def test_text_resolution_uses_the_declared_table_or_brtext_by_default(self):
        from whshr.frontend.glue_view import resolve_text
        content = GlueContent.from_data(strings={"BRTXT": {7: "default"}, "BKTXT": {7: "book"}})

        self.assertEqual(resolve_text(content, RenderText(7, None)), "default")
        self.assertEqual(resolve_text(content, RenderText(7, "BKTXT")), "book")

    def test_mission_without_a_cash_record_has_no_payment_line(self):
        from whshr.frontend.glue_view import _mission_rows
        content = GlueContent.from_data(resources={
            "MISSIONS": "[WINDOW]\n[MISSION]\nset:res=601\n[END]",
        }, strings={"BRTXT": {601: "No payment"}})
        reference = MissionRef("MISSIONS", 0)
        model = GlueRenderModel("MISSIONS", 0, 0, 640, 480, 0, (), (), (), (), (),
                                (RenderMissionList(30, 15, (reference,)),))

        rows = _mission_rows(content, (model,), reference)

        self.assertEqual(rows[0][1:3], ("No payment", ""))

    def test_format_diagnostic_names_the_location_and_message(self):
        from whshr.frontend.glue_view import format_diagnostic
        from whshr.glue_runtime import Diagnostic

        line = format_diagnostic(Diagnostic("panel", "'open_book' is not yet implemented"))

        self.assertEqual(line, "glue: panel: 'open_book' is not yet implemented")

    def test_dynamic_animation_base_without_a_bitmap_resource_is_transparent(self):
        from whshr.frontend.glue_bitmap import load_optional_bitmap

        self.assertIsNone(load_optional_bitmap(GlueContent.from_data(), "Tent4"))

    def test_campaign_count_controls_dependent_caravan_bitmap_visibility(self):
        from whshr.frontend.glue_view import _bitmap_visible
        bitmap = RenderBitmap("CarScroll3", animation=(("depend", 2),))
        campaign = type("Campaign", (), {"missions": (object(),)})()

        self.assertFalse(_bitmap_visible(bitmap, campaign))
        campaign.missions = (object(), object())
        self.assertTrue(_bitmap_visible(bitmap, campaign))

    def test_only_caravan_scrolls_use_campaign_count_dependency(self):
        from whshr.frontend.glue_view import _bitmap_visible
        bitmap = RenderBitmap("OtherBitmap", animation=(("depend", 2),))
        campaign = type("Campaign", (), {"missions": ()})()

        self.assertTrue(_bitmap_visible(bitmap, campaign))

    def test_caravan_coffers_hint_receives_the_campaign_value(self):
        from whshr.frontend.glue_view import _caravan_hint
        campaign = type("Campaign", (), {"coffers": 500, "hint": lambda self, hint, *args: f"{hint}:{args}"})()
        model = GlueRenderModel("STARTCARAVAN", 0, 0, 640, 480, 0, (), (), (), (), ())
        hotspot = RenderHotspot(0, 0, 1, 1, -1, None, None, None, None)

        self.assertEqual(_caravan_hint(campaign, (model,), hotspot), "402:(500,)")

    def test_format_1_text_centres_in_vx_and_uses_vy_as_a_y_offset_not_a_box_height(self):
        from whshr.frontend.glue_view import _place_text

        gpu, font = _FakeGpu(), _FakeFont(12)
        model = GlueRenderModel("MAP", 0, 0, 640, 480, 0, (), (), (), (), ())
        text = RenderText(672, None, x=210, y=20, width=219, height=5, format=1)

        label, (x, y) = _place_text(gpu, font, "Decoy", text, model)

        self.assertEqual(gpu.last_size, (219, 12))
        self.assertEqual((label.align, label.fixed_width), ("center", True))
        self.assertEqual((x, y), (210, 25))

    def test_format_6_text_is_not_clipped_by_a_small_vx_it_does_not_use_as_a_width(self):
        from whshr.frontend.glue_view import _place_text

        gpu, font = _FakeGpu(), _FakeFont(12)
        model = GlueRenderModel("MAP", 0, 0, 640, 480, 0, (), (), (), (), ())
        text = RenderText(863, None, x=401, y=111, width=10, height=15, format=6)

        _place_text(gpu, font, "Karak-Hirn", text, model)

        self.assertEqual(gpu.last_size[0], 640)

    def test_format_8_text_centres_vertically_in_vy_without_clipping_the_label_to_it(self):
        from whshr.frontend.glue_view import _place_text

        gpu, font = _FakeGpu(), _FakeFont(12)
        model = GlueRenderModel("WIN", 0, 0, 640, 480, 0, (), (), (), (), ())
        text = RenderText(1, None, x=10, y=100, width=0, height=40, format=8)

        label, (x, y) = _place_text(gpu, font, "Option", text, model)

        self.assertEqual(gpu.last_size[1], 12)
        self.assertEqual((x, y), (10, 100 + (40 - label.text_size[1]) // 2))


class _FakeFont:
    def __init__(self, height):
        self.font = type("Font", (), {"height": height})()


class _FakeLabel:
    def __init__(self, size, align="left", fixed_width=False, **_options):
        self.size, self.align, self.fixed_width = size, align, fixed_width
        self.text_size = (len("Decoy") * 6, size[1])

    def set_lines(self, lines):
        pass


class _FakeGpu:
    def __init__(self):
        self.last_size = None

    def text(self, size, font, **options):
        self.last_size = size
        return _FakeLabel(size, **options)


if __name__ == "__main__":
    unittest.main()
