"""HUD geometry/input tests without requiring the optional pygame/zengl frontend stack."""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


pygame = types.ModuleType("pygame")
pygame.font = SimpleNamespace(Font=lambda *args, **kwargs: None)
pygame.MOUSEWHEEL = 1
pygame.MOUSEMOTION = 2
pygame.KEYDOWN = 3
pygame.MOUSEBUTTONDOWN = 4
pygame.MOUSEBUTTONUP = 5
pygame.K_HOME = 6
pygame.K_ESCAPE = 7
sys.modules.setdefault("pygame", pygame)
sys.modules.setdefault("zengl", types.ModuleType("zengl"))

from whshr.engine import Battle, Regiment
from whshr.frontend.battle_view import BattleView
from whshr.frontend.hud import Hud


class HudTests(unittest.TestCase):
    def setUp(self):
        player = Regiment("player", "Player", 100, 100, 0, True, models=10, ranks=2)
        enemy = Regiment("enemy", "Enemy", 700, 600, 0, False, models=10, ranks=2)
        self.hud = Hud.__new__(Hud)
        self.hud.field = SimpleNamespace(width=1000, height=800)
        self.hud.battle = Battle(1000, 800, [player, enemy])
        self.hud.selected = "player"
        self.hud._draw_size = (1280, 720)
        self.hud.pressed_action = None

    def test_given_hud_chrome_when_hit_tested_then_all_drawn_regions_are_occupied(self):
        self.assertTrue(self.hud.occupies((1030, 30)))  # minimap
        self.assertTrue(self.hud.occupies((20, 600)))   # selected-unit panel
        self.assertTrue(self.hud.occupies((1170, 550)))  # command panel
        self.assertFalse(self.hud.occupies((500, 300)))

    def test_given_a_minimap_pixel_when_converted_then_it_maps_to_the_battlefield_axes(self):
        self.assertEqual(self.hud.minimap_position((1024, 16)), (0.0, 800.0))
        self.assertEqual(self.hud.minimap_position((1263, 299)), (1000.0, 0.0))
        self.assertIsNone(self.hud.minimap_position((500, 300)))

    def test_given_a_selected_regiment_when_commands_are_checked_then_only_valid_orders_enable(self):
        player = self.hud.battle.regiments["player"]
        self.assertEqual(self.hud.hit_test((1161, 549)), "move")
        self.assertTrue(self.hud._button_enabled("attack", player))
        self.assertFalse(self.hud._button_enabled("halt", player))
        self.assertFalse(self.hud._button_enabled("shoot", player))
        player.target_x, player.target_y = 500, 500
        self.assertTrue(self.hud._button_enabled("halt", player))
        player.routing = True
        self.assertFalse(self.hud._button_enabled("move", player))

    def test_given_a_pressed_command_when_released_then_its_visual_state_is_cleared(self):
        self.hud.set_pressed("move")
        self.assertEqual(self.hud.pressed_action, "move")
        self.hud.set_pressed(None)
        self.assertIsNone(self.hud.pressed_action)


class BattleViewHudInputTests(unittest.TestCase):
    def _view(self, hud, selected_id="player"):
        view = BattleView.__new__(BattleView)
        view.hud = hud
        view.scene = SimpleNamespace(selected_id=selected_id)
        view.camera = SimpleNamespace()
        view.order_mode = None
        view._ground_click = Mock(return_value=(("ground",),))
        return view

    def test_given_a_non_actionable_hud_click_when_handled_then_it_never_reaches_ground_picking(self):
        hud = SimpleNamespace(minimap_position=lambda pos: None, hit_test=lambda pos: None,
                              occupies=lambda pos: True, set_pressed=Mock())
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        view._ground_click.assert_not_called()

    def test_given_a_selected_unit_when_the_minimap_is_clicked_then_it_emits_a_move_order(self):
        hud = SimpleNamespace(minimap_position=lambda pos: (123.0, 456.0), hit_test=lambda pos: None,
                              occupies=lambda pos: True, set_pressed=Mock())
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("move_to", 123.0, 456.0),))
        view._ground_click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
