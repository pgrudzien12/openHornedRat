from types import SimpleNamespace
import importlib.util
import unittest



@unittest.skipUnless(importlib.util.find_spec("pygame"), "Pygame is not installed in the headless test environment")
class CaravanViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from whshr.frontend.caravan_view import CaravanView
        cls.view_type = CaravanView

    def setUp(self):
        self.view = self.view_type.__new__(self.view_type)
        self.view._native_point = lambda point: point
        self.view.scene = SimpleNamespace(
            campaign=SimpleNamespace(hotspots=()), can_select_mission=True, missions=(object(),), gold=500,
        )

    def test_resource_target_and_rect_are_read_from_the_hotspot_record(self):
        self.view.scene.campaign.hotspots = ({
            "x": 20, "y": 30, "vx": 40, "vy": 50, "res": 151,
            "target": "ArmyBook", "target_kind": "res",
        },)

        self.assertEqual(self.view._hub_action_at((25, 35)), "browse_book:troop roster")
        self.assertIsNone(self.view._hub_action_at((1, 1)))

    def test_flow_resource_opens_the_mission_map_only_when_a_mission_is_available(self):
        self.view.scene.campaign.hotspots = ({
            "x": 0, "y": 0, "vx": 20, "vy": 20, "res": 150,
            "target": "FlowScriptBP01", "target_kind": "res",
        },)

        self.assertEqual(self.view._hub_action_at((1, 1)), "open_mission_map")
        self.view.scene.missions = ()
        self.assertIsNone(self.view._hub_action_at((1, 1)))

    def test_an_ordinary_brtxt_hint_is_not_given_the_gold_format_argument(self):
        self.view.scene.campaign.hotspots = ({"x": 0, "y": 0, "vx": 20, "vy": 20, "res": 151},)
        self.view.scene.campaign.hint = lambda hint_id, *args: f"{hint_id}:{args}"
        self.view.hint = SimpleNamespace(set_lines=lambda _lines: None)

        self.view._set_hover((1, 1))

        self.assertEqual(self.view.hover, "151:()")


if __name__ == "__main__":
    unittest.main()
