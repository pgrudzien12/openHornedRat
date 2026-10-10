"""Automated battle protocol: valid player orders and an explicit roster source."""

from types import SimpleNamespace
import importlib.util
import unittest
from unittest import mock

from whshr.battle_auto import camera_values, describe, parse_order, target_values


class BattleAutoTests(unittest.TestCase):
    def test_given_order_command_when_parsed_then_only_supported_scene_events_are_forwarded(self):
        self.assertEqual(parse_order({"event": ["select", "Player"]}), ("select", "Player"))
        self.assertEqual(parse_order({"event": ["move_to", 12.5, 20]}), ("move_to", 12.5, 20))
        for event in (["win_battle"], ["move_to", "west", 20], ["attack"], ["select", 1]):
            with self.subTest(event=event), self.assertRaises(ValueError):
                parse_order({"event": event})

    def test_given_camera_and_world_coordinates_when_nonfinite_or_out_of_range_then_rejected(self):
        self.assertEqual(camera_values([450, 45, 120]), (90, 45, 120))
        self.assertEqual(target_values([10, 20.5]), (10, 20.5))
        for values in ([0, 0, 120], [0, 45, 0], [float("nan"), 45, 120],
                       [0, float("inf"), 120], [0, 45, float("nan")]):
            with self.subTest(camera=values), self.assertRaises(ValueError):
                camera_values(values)
        with self.assertRaises(ValueError):
            target_values([float("nan"), 20])
        with self.assertRaises(ValueError):
            parse_order({"event": ["move_to", float("inf"), 20]})

    def test_given_direct_entry_battle_when_described_then_roster_and_figure_counts_are_visible(self):
        player = SimpleNamespace(name="Infantry", side=SimpleNamespace(value="player"))
        battle = SimpleNamespace(tick_count=0, update_count=0, phase="deployment", paused=False, result=None,
                                 regiments={"Infantry": player},
                                 snapshot=lambda: {"Infantry": {"models": 16, "ranks": 4, "x": 10, "y": 20}})
        scene = SimpleNamespace(battle=battle, battle_id=SimpleNamespace(name="bf001"), selected_id=None,
                                player_army=None, field=SimpleNamespace(script={"merc": {
                                    "file": "START.MRC", "armies": [{"units": [{"id": "Infantry"}]}]}}))
        state = describe(scene)
        self.assertEqual(state["player_army"], {"source": "battle_loadmerc", "file": "START.MRC",
                                                  "units": ["Infantry"]})
        self.assertEqual(state["regiments"]["Infantry"]["models"], 16)

    @unittest.skipUnless(importlib.util.find_spec("pygame") and importlib.util.find_spec("zengl"),
                         "frontend packages not installed")
    def test_given_png_write_failure_when_capturing_then_frame_is_ended(self):
        from whshr.frontend.battle_auto import BattleSession

        session = BattleSession.__new__(BattleSession)
        ctx = mock.Mock()
        target = mock.Mock()
        target.save_png.side_effect = OSError("disk full")
        session.gpu = SimpleNamespace(ctx=ctx, target=target)
        session.view = mock.Mock()
        with self.assertRaises(OSError):
            session.command({"op": "capture", "path": "samples/test-failed-capture.png"})
        ctx.new_frame.assert_called_once()
        ctx.end_frame.assert_called_once()


if __name__ == "__main__":
    unittest.main()
