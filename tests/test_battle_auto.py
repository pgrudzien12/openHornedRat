"""Automated battle protocol: valid player orders and an explicit roster source."""

from types import SimpleNamespace
import unittest

from whshr.battle_auto import describe, parse_order


class BattleAutoTests(unittest.TestCase):
    def test_given_order_command_when_parsed_then_only_supported_scene_events_are_forwarded(self):
        self.assertEqual(parse_order({"event": ["select", "Player"]}), ("select", "Player"))
        self.assertEqual(parse_order({"event": ["move_to", 12.5, 20]}), ("move_to", 12.5, 20))
        for event in (["win_battle"], ["move_to", "west", 20], ["attack"], ["select", 1]):
            with self.subTest(event=event), self.assertRaises(ValueError):
                parse_order({"event": event})

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


if __name__ == "__main__":
    unittest.main()
