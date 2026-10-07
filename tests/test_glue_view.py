import importlib.util
import unittest
from unittest.mock import patch

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

    def test_caravan_animation_keeps_the_unchanged_background_texture(self):
        from whshr.frontend.glue_view import GlueView
        from whshr.frontend.gpu import QuadCache
        from whshr.glue_palette import AppPalette
        import pygame

        view = GlueView.__new__(GlueView)
        view.scene = type("Scene", (), {"campaign": None, "require_runtime": lambda self: type("Runtime", (), {"content": None})()})()
        view.gpu = object()
        view._bitmap_models, view._bitmap_visibility = (), ()
        view.frames, view.palette = {}, None
        view.bitmap_quads, view.quads, view.text_labels = QuadCache(view.gpu), [], []
        palette = AppPalette.select(0, {})
        model = GlueRenderModel("STARTCARAVAN", 0, 0, 640, 480, 3,
                                (RenderBitmap("ReadBackgroundPic"), RenderBitmap("CarLampCell")),
                                (), (), (), ())

        with patch("whshr.frontend.gpu.ScreenQuad", _FakeQuad), patch(
                "whshr.frontend.glue_view.load_optional_bitmap", return_value=pygame.Surface((2, 2))):
            view._refresh_bitmaps((model,), {(model.name, 1): "CarLampCell5"}, palette)
            background, lamp = (quad for quad, _ in view.quads)
            view._refresh_bitmaps((model,), {(model.name, 1): "CarLampCell4"}, palette)
            view._refresh_bitmaps((model,), {(model.name, 1): "CarLampCell5"}, palette)

        self.assertIs(view.quads[0][0], background)
        self.assertFalse(background.released)
        self.assertIs(view.quads[1][0], lamp)
        self.assertFalse(lamp.released)
        view.bitmap_quads.release()
        self.assertTrue(background.released)
        self.assertTrue(lamp.released)

    def test_simultaneous_caravan_animations_advance_together(self):
        from whshr.frontend.glue_view import GlueView
        from whshr.glue_animation import GlueBitmapAnimator

        view = GlueView.__new__(GlueView)
        view.bitmap_animators = {
            ("STARTCARAVAN", 0): GlueBitmapAnimator({"bitmap": "CarLampCell", "animstartframe": 5, "animstopframe": -1}),
            ("STARTCARAVAN", 1): GlueBitmapAnimator({"bitmap": "CarCandleCell", "animstartframe": 5, "animstopframe": -1}),
        }
        view._overlay_frames = ()
        view.scene = type("Scene", (), {"require_runtime": lambda self: type(
            "Runtime", (), {"state": type("State", (), {"speech_overlays": {}})()})()})()
        view.refresh = lambda: None

        view.animate(50 / 1000)

        self.assertEqual([animator.display_name for animator in view.bitmap_animators.values()],
                         ["CarLampCell5", "CarCandleCell5"])

    def test_caravan_coffers_hint_receives_the_campaign_value(self):
        from whshr.frontend.glue_view import _caravan_hint
        campaign = type("Campaign", (), {"coffers": 500, "hint": lambda self, hint, *args: f"{hint}:{args}"})()
        model = GlueRenderModel("STARTCARAVAN", 0, 0, 640, 480, 0, (), (), (), (), ())
        hotspot = RenderHotspot(0, 0, 1, 1, -1, None, None, None, None)

        self.assertEqual(_caravan_hint(campaign, (model,), hotspot), "402:(500,)")

    def test_every_caravan_variant_shows_its_hotspot_hints_but_other_windows_do_not(self):
        from whshr.frontend.glue_view import _caravan_hint
        campaign = type("Campaign", (), {"coffers": 500, "hint": lambda self, hint, *args: f"hint{hint}"})()
        talk = RenderHotspot(0, 0, 1, 1, 160, "DietrichSpeech", None, None, None)
        for name, shown in (("STARTCARAVAN", True), ("CARAVANAFTERMISSION", True), ("CARAVANAFTERMISSIONWITHRECRUIT", True),
                            ("CARAVANAFTERENCOUNTERWITHRECRUIT", True), ("CARAVANRECRUITANDRESUME", True),
                            ("INFOCARAVANBPC", True), ("CARAVANSELECTMISSION", True), ("MAPWINDOW", False),
                            ("SCRIBE5WINDOWTL", False)):
            with self.subTest(window=name):
                model = GlueRenderModel(name, 0, 0, 640, 480, 0, (), (), (), (), ())

                self.assertEqual(_caravan_hint(campaign, (model,), talk), "hint160" if shown else None)

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


class _FakeQuad:
    def __init__(self, gpu, size):
        self.size = size
        self.released = False

    def write(self, data):
        pass

    def release(self):
        self.released = True


if __name__ == "__main__":
    unittest.main()
