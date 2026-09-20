import unittest

from whshr.glue_content import GlueContent
from whshr.glue_render import build_render_model
from whshr.glue_runtime import WindowInstance


class GlueRenderModelTests(unittest.TestCase):
    def test_window_projection_expands_includes_preserves_draw_order_and_keeps_hotspot_hint_separate_from_target(self):
        content = GlueContent.from_data(resources={
            "BASE": """[WINDOW]
[POSITION]
set:x=2
set:y=3
set:vx=640
set:vy=480
[BITMAP]
setbitmap:Base
[INCLUDE]
script:DECOR
[HOTSPOT]
set:x=4
set:y=5
set:vx=6
set:vy=7
set:res=99
res:Next
[END]""",
            "DECOR": """[WINDOW]
[BITMAP]
set:x=8
set:y=9
setbitmap:Decoration
[TEXT]
set:x=10
set:y=11
set:res=12
font:4
[END]""",
            "OBJECT": """[WINDOW]
[BITMAP]
setbitmap:Late
[END]""",
        })

        model = build_render_model(content, WindowInstance("BASE", None, 2, ["OBJECT"]))

        self.assertEqual((model.x, model.y, model.width, model.height, model.palette_id), (2, 3, 640, 480, 2))
        self.assertEqual([bitmap.name for bitmap in model.bitmaps], ["Base", "Decoration", "Late"])
        self.assertEqual((model.texts[0].string_id, model.texts[0].font), (12, "4"))
        self.assertEqual((model.hotspots[0].hint_id, model.hotspots[0].target), (99, "Next"))

    def test_cyclic_include_is_a_diagnostic_error_not_an_unbounded_projection(self):
        content = GlueContent.from_data(resources={
            "A": "[WINDOW]\n[INCLUDE]\nscript:B\n[END]",
            "B": "[WINDOW]\n[INCLUDE]\nscript:A\n[END]",
        })

        with self.assertRaisesRegex(ValueError, "cyclic glue include"):
            build_render_model(content, WindowInstance("A", None, 0))

    def test_mission_window_exposes_its_geometry_and_stable_mission_references(self):
        content = GlueContent.from_data(resources={
            "MISSIONS": """[WINDOW]
[MISSIONWINDOW]
set:x=30
set:y=15
[END]
[MISSION]
set:res=601
[END]
[MISSION]
set:res=602
[END]""",
        })

        model = build_render_model(content, WindowInstance("MISSIONS", None, 0))

        self.assertEqual((model.mission_lists[0].x, model.mission_lists[0].y), (30, 15))
        self.assertEqual([reference.key for reference in model.mission_lists[0].missions], ["missions.0", "missions.1"])


if __name__ == "__main__":
    unittest.main()
