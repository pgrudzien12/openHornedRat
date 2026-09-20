import importlib.util
import unittest

from whshr.glue_render import GlueRenderModel, RenderHotspot


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


if __name__ == "__main__":
    unittest.main()
