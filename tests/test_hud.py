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
from whshr.battlefield import SpriteFrame, SpriteSheet
from whshr.frontend.battle_view import BANNER_MARKER_RAISE, BattleView, INSTANCE
from whshr.frontend.hud import Hud, MINIMAP_SIZE


class HudTests(unittest.TestCase):
    def setUp(self):
        player = Regiment("player", "Player", 100, 100, 0, True, models=10, ranks=2)
        enemy = Regiment("enemy", "Enemy", 700, 600, 0, False, models=10, ranks=2)
        self.hud = Hud.__new__(Hud)
        self.hud.field = SimpleNamespace(width=1000, height=800, palette=[(0, 0, 0), (12, 34, 56)], ui_sheets={})
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

    def test_given_an_active_bannered_regiment_when_the_minimap_is_drawn_then_its_marker_is_bottom_centred(self):
        marker = SpriteFrame(3, 2, 0, 2, bytes((0, 0, 0, 0, 1, 0)))
        self.hud.field.ui_sheets["banner"] = SpriteSheet("BANNER", [marker, marker], [])
        self.hud.battle.regiments["player"].banner = "banner"
        self.hud._minimap_background = bytes((1, 2, 3, 255)) * (MINIMAP_SIZE[0] * MINIMAP_SIZE[1])

        rgba = self.hud._minimap_rgba()

        x = round(100 / 1000 * (MINIMAP_SIZE[0] - 1))
        y = round((1 - 100 / 800) * (MINIMAP_SIZE[1] - 1))
        offset = (y * MINIMAP_SIZE[0] + x) * 4
        self.assertEqual(rgba[offset:offset + 4], bytes((12, 34, 56, 255)))
        self.assertEqual(self.hud.minimap_regiment_at((1024 + x, 16 + y)), "player")
        selected_rim = rgba[(y * MINIMAP_SIZE[0] + x - 1) * 4:(y * MINIMAP_SIZE[0] + x) * 4]
        self.hud.selected = None
        deselected = self.hud._minimap_rgba()
        self.assertNotEqual(selected_rim, deselected[(y * MINIMAP_SIZE[0] + x - 1) * 4:(y * MINIMAP_SIZE[0] + x) * 4])

    def test_given_a_selected_marker_with_art_at_its_frame_edge_when_drawn_then_selection_is_visually_distinguished(self):
        marker = SpriteFrame(1, 1, 0, 1, bytes((1,)))
        self.hud.field.ui_sheets["banner"] = SpriteSheet("BANNER", [marker, marker], [])
        self.hud.battle.regiments["player"].banner = "banner"
        self.hud._minimap_background = bytes((1, 2, 3, 255)) * (MINIMAP_SIZE[0] * MINIMAP_SIZE[1])

        rgba = self.hud._minimap_rgba()

        x = round(100 / 1000 * (MINIMAP_SIZE[0] - 1))
        y = round((1 - 100 / 800) * (MINIMAP_SIZE[1] - 1))
        selected_rim = rgba[(y * MINIMAP_SIZE[0] + x - 1) * 4:(y * MINIMAP_SIZE[0] + x) * 4]
        self.hud.selected = None
        deselected = self.hud._minimap_rgba()
        self.assertNotEqual(selected_rim, deselected[(y * MINIMAP_SIZE[0] + x - 1) * 4:(y * MINIMAP_SIZE[0] + x) * 4])

    def test_given_overlapping_markers_when_one_is_selected_then_its_art_is_rendered_last(self):
        player, enemy = self.hud.battle.regiments.values()
        enemy.x, enemy.y = player.x, player.y
        player_marker = SpriteFrame(3, 2, 0, 2, bytes((0, 0, 0, 0, 1, 0)))
        enemy_marker = SpriteFrame(3, 2, 0, 2, bytes((0, 0, 0, 0, 2, 0)))
        self.hud.field.palette.append((90, 80, 70))
        self.hud.field.ui_sheets.update({
            "player-banner": SpriteSheet("PLAYER", [player_marker, player_marker], []),
            "enemy-banner": SpriteSheet("ENEMY", [enemy_marker, enemy_marker], []),
        })
        player.banner, enemy.banner = "player-banner", "enemy-banner"
        self.hud._promote_marker("player")
        self.hud._minimap_background = bytes((1, 2, 3, 255)) * (MINIMAP_SIZE[0] * MINIMAP_SIZE[1])

        rgba = self.hud._minimap_rgba()

        x = round(player.x / self.hud.field.width * (MINIMAP_SIZE[0] - 1))
        y = round((1 - player.y / self.hud.field.height) * (MINIMAP_SIZE[1] - 1))
        offset = (y * MINIMAP_SIZE[0] + x) * 4
        self.assertEqual(rgba[offset:offset + 4], bytes((12, 34, 56, 255)))
        self.hud.selected = None
        self.assertEqual(self.hud._minimap_rgba()[offset:offset + 4], bytes((12, 34, 56, 255)))

    def test_given_a_destroyed_bannered_regiment_when_the_minimap_is_drawn_then_its_marker_is_absent(self):
        marker = SpriteFrame(3, 2, 0, 2, bytes((0, 0, 0, 0, 1, 0)))
        self.hud.field.ui_sheets["banner"] = SpriteSheet("BANNER", [marker, marker], [])
        player = self.hud.battle.regiments["player"]
        player.banner, player.models = "banner", 0
        self.hud._minimap_background = bytes((1, 2, 3, 255)) * (MINIMAP_SIZE[0] * MINIMAP_SIZE[1])

        rgba = self.hud._minimap_rgba()

        x = round(100 / 1000 * (MINIMAP_SIZE[0] - 1))
        y = round((1 - 100 / 800) * (MINIMAP_SIZE[1] - 1))
        offset = (y * MINIMAP_SIZE[0] + x) * 4
        self.assertEqual(rgba[offset:offset + 4], bytes((1, 2, 3, 255)))

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
        hud = SimpleNamespace(minimap_regiment_at=lambda pos: None, minimap_position=lambda pos: None, hit_test=lambda pos: None,
                              occupies=lambda pos: True, set_pressed=Mock())
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        view._ground_click.assert_not_called()

    def test_given_a_selected_unit_when_the_minimap_is_clicked_then_it_emits_a_move_order(self):
        hud = SimpleNamespace(minimap_regiment_at=lambda pos: None, minimap_position=lambda pos: (123.0, 456.0), hit_test=lambda pos: None,
                              occupies=lambda pos: True, set_pressed=Mock())
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("move_to", 123.0, 456.0),))
        view._ground_click.assert_not_called()

    def test_given_no_selected_unit_when_the_minimap_is_clicked_then_it_does_not_issue_or_leak_an_order(self):
        hud = SimpleNamespace(minimap_regiment_at=lambda pos: None, minimap_position=lambda pos: (123.0, 456.0), hit_test=lambda pos: None,
                              occupies=lambda pos: True, set_pressed=Mock())
        view = self._view(hud, selected_id=None)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        view._ground_click.assert_not_called()

    def test_given_a_move_button_when_held_then_its_pressed_art_stays_visible_until_mouse_up(self):
        hud = SimpleNamespace(minimap_regiment_at=lambda pos: None, minimap_position=lambda pos: None, hit_test=lambda pos: "move",
                              occupies=lambda pos: True, set_pressed=Mock())
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))
        up = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(100, 100))

        self.assertEqual(view.events(down), ())
        self.assertEqual(view.order_mode, "move")
        self.assertEqual(hud.set_pressed.call_args_list[-1].args, ("move",))
        self.assertEqual(view.events(up), ())
        self.assertEqual(hud.set_pressed.call_args_list[-1].args, (None,))

    def test_given_a_right_click_that_ends_on_hud_chrome_then_it_does_not_issue_a_ground_order(self):
        hud = SimpleNamespace(minimap_regiment_at=lambda pos: None, minimap_position=lambda pos: None, hit_test=lambda pos: None,
                              occupies=lambda pos: pos == (20, 20), set_pressed=Mock())
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=3, pos=(10, 10))
        up = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=3, pos=(20, 20))

        self.assertEqual(view.events(down), ())
        self.assertEqual(view.events(up), ())
        view._ground_click.assert_not_called()

    def test_given_a_unit_marker_when_clicked_on_the_minimap_then_that_unit_is_selected(self):
        hud = SimpleNamespace(minimap_regiment_at=lambda pos: "player", minimap_position=lambda pos: (123.0, 456.0),
                              hit_test=lambda pos: None, occupies=lambda pos: True, set_pressed=Mock())
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("select", "player"),))
        view._ground_click.assert_not_called()


class BattleBannerVisibilityTests(unittest.TestCase):
    def _view_with_banner(self, active=True):
        regiment = Regiment("player", "Player", 100, 200, 0, True, models=1 if active else 0,
                            banner="banner")
        marker = SpriteFrame(32, 32, 0, 32, bytes(32 * 32))
        banner = SpriteSheet("BANNER", [marker, marker, marker], [],
                             rects=[(0, 0, 32, 32)] * 3)
        field = SimpleNamespace(
            ui_sheets={"banner": banner}, sprite_sheet=lambda resource: None,
            ground_height=lambda x, y: 2.0,
        )
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(field=field, battle=Battle(1000, 800, [regiment]), selected_id="player")
        view.camera = SimpleNamespace(yaw=180)
        view.capacity = 1
        return view

    def test_given_an_active_bannered_regiment_when_the_battle_view_draws_then_one_banner_marker_is_visible(self):
        instance = INSTANCE.unpack(self._view_with_banner()._instances())

        self.assertEqual(instance[:3], (12.5, 2.0 + BANNER_MARKER_RAISE, 25.0))
        self.assertEqual(instance[3:7], (0.0, 0.0, 32.0, 32.0))
        self.assertEqual(instance[7:], (16.0, 32.0, 1.0))

    def test_given_a_destroyed_bannered_regiment_when_the_battle_view_draws_then_no_banner_marker_is_visible(self):
        self.assertEqual(self._view_with_banner(active=False)._instances(), b"")

    def test_given_overlapping_regiment_banners_when_one_is_selected_then_its_marker_is_drawn_last(self):
        player = Regiment("player", "Player", 100, 200, 0, True, banner="player-banner")
        enemy = Regiment("enemy", "Enemy", 100, 200, 0, False, banner="enemy-banner")
        marker = SpriteFrame(32, 32, 0, 32, bytes(32 * 32))
        player_sheet = SpriteSheet("PLAYER", [marker, marker, marker], [], rects=[(10, 0, 32, 32)] * 3)
        enemy_sheet = SpriteSheet("ENEMY", [marker, marker, marker], [], rects=[(50, 0, 32, 32)] * 3)
        field = SimpleNamespace(
            ui_sheets={"player-banner": player_sheet, "enemy-banner": enemy_sheet},
            sprite_sheet=lambda resource: None, ground_height=lambda x, y: 2.0,
        )
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(field=field, battle=Battle(1000, 800, [player, enemy]), selected_id="player")
        view.camera, view.capacity = SimpleNamespace(yaw=180), 2

        instances = view._instances()

        first = INSTANCE.unpack_from(instances, 0)
        last = INSTANCE.unpack_from(instances, INSTANCE.size)
        self.assertEqual(first[3:7], (50.0, 0.0, 32.0, 32.0))
        self.assertEqual(last[3:7], (10.0, 0.0, 32.0, 32.0))
        view.scene.selected_id = None
        after_deselect = view._instances()
        self.assertEqual(INSTANCE.unpack_from(after_deselect, INSTANCE.size)[3:7], (10.0, 0.0, 32.0, 32.0))


if __name__ == "__main__":
    unittest.main()
