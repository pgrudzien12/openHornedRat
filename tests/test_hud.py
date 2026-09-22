"""HUD geometry/panel-state/input tests without requiring the optional pygame/zengl frontend stack.

Layout source: notes/game_rules.md "Battle HUD layout". The HUD draws GPU quads directly (matching
the rest of the engine's rendering), so these tests exercise the pure logic that decides *what*
gets drawn (panel state, slot layout, hit testing, minimap marker selection) rather than pixel
output.
"""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

try:
    import pygame
except ModuleNotFoundError:
    pygame = types.ModuleType("pygame")
    pygame.font = SimpleNamespace(Font=lambda *args, **kwargs: None)
    pygame.MOUSEWHEEL = 1
    pygame.MOUSEMOTION = 2
    pygame.KEYDOWN = 3
    pygame.MOUSEBUTTONDOWN = 4
    pygame.MOUSEBUTTONUP = 5
    pygame.K_HOME = 6
    pygame.K_ESCAPE = 7

    class _Rect:
        def __init__(self, x, y, w, h):
            self.x, self.y, self.w, self.h = x, y, w, h

        def collidepoint(self, pos):
            x, y = pos
            return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h
    pygame.Rect = _Rect
    sys.modules["pygame"] = pygame

try:
    import zengl  # noqa: F401
except ModuleNotFoundError:
    sys.modules["zengl"] = types.ModuleType("zengl")

from whshr.engine import Battle, Regiment
from whshr.frontend.battle_view import BattleView
from whshr.frontend.hud import FIXED_BUTTONS, MINIMAP_RECT, PANEL_RECT, Hud


def _hud(selected="player", regiments=None, **overrides):
    if regiments is None:
        regiments = [
            Regiment("player", "Player", 100, 100, 0, True, models=10, ranks=2, hud_class="inf"),
            Regiment("enemy", "Enemy", 700, 600, 128, False, models=10, ranks=2, hud_class="inf"),
        ]
    instance = Hud.__new__(Hud)
    instance.field = SimpleNamespace(width=1000, height=800, palette=[(0, 0, 0)], ui_sheets={})
    instance.battle = Battle(1000, 800, regiments)
    instance.selected = selected
    instance._draw_size = (640, 480)
    instance.pressed = None
    instance.panel_set = "idle"
    instance.pending_order = None
    instance.marker_mode = 0
    instance._marker_order = []
    for key, value in overrides.items():
        setattr(instance, key, value)
    return instance


class PanelStateTests(unittest.TestCase):
    def test_given_nothing_selected_then_the_idle_no_selection_layout_is_used(self):
        hud = _hud(selected=None)

        self.assertEqual(hud.panel_state(), ("idle", None))
        self.assertEqual(hud.slots(), {"TL": "move", "TR": "attack", "BR": "independent"})

    def test_given_an_idle_infantry_regiment_then_it_has_move_attack_independent(self):
        hud = _hud()

        self.assertEqual(hud.panel_state(), ("idle", "inf"))
        self.assertEqual(hud.slots(), {"TL": "move", "TR": "attack", "BR": "independent"})

    def test_given_an_idle_artillery_regiment_then_it_has_no_move_slot(self):
        regiments = [Regiment("player", "Gun", 0, 0, 0, True, hud_class="art")]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.slots(), {"TR": "attack", "BR": "independent"})

    def test_given_an_idle_wizard_regiment_then_magic_and_back_are_present(self):
        regiments = [Regiment("player", "Wiz", 0, 0, 0, True, hud_class="wiz")]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.slots(),
                         {"TL": "move", "TR": "attack", "BR": "independent", "BL": "magic", "C": "back"})

    def test_given_a_regiment_in_melee_then_the_melee_noncaster_set_is_used(self):
        regiments = [Regiment("player", "P", 0, 0, 0, True, hud_class="inf", in_melee=True)]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.panel_state(), ("melee_noncaster", "inf"))
        self.assertEqual(hud.slots(), {"TR": "withdraw", "C": "fight_harder"})

    def test_given_a_routing_regiment_then_the_rally_set_is_used(self):
        regiments = [Regiment("player", "P", 0, 0, 0, True, hud_class="inf", routing=True)]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.panel_state(), ("rally", "inf"))
        self.assertEqual(hud.slots(), {"BR": "rally"})

    def test_given_a_regiment_with_an_attack_target_not_yet_in_melee_then_charging_has_no_buttons(self):
        regiments = [Regiment("player", "P", 0, 0, 0, True, hud_class="inf", attack_target="enemy")]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.panel_state(), ("charging", "inf"))
        self.assertEqual(hud.slots(), {})

    def test_given_a_class_with_no_buttons_then_no_slots_are_shown(self):
        regiments = [Regiment("player", "P", 0, 0, 0, True, hud_class=None)]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.panel_state(), (None, None))
        self.assertEqual(hud.slots(), {})

    def test_given_navigation_into_the_move_set_then_ranks_and_facing_subsets_are_offered(self):
        hud = _hud()

        hud.press("move")

        self.assertEqual(hud.panel_state(), ("move", "inf"))
        self.assertEqual(hud.slots(),
                         {"TL": "ranks_subset", "TR": "facing_subset", "BR": "halt", "BL": "face_point", "C": "back"})

    def test_given_the_attack_set_is_entered_then_the_noncaster_variant_is_used(self):
        # whshr.engine.Regiment has no spells/items list, so the caster variant is never selected
        # (a documented simplification, notes/glue_engine_integration... see Hud._caster).
        hud = _hud()

        hud.press("attack")

        self.assertEqual(hud.panel_state(), ("attack_noncaster", "inf"))

    def test_given_back_is_pressed_then_navigation_returns_to_idle(self):
        hud = _hud()
        hud.press("move")

        hud.press("back")

        self.assertEqual(hud.panel_state(), ("idle", "inf"))

    def test_given_a_new_selection_then_panel_navigation_and_pending_order_reset(self):
        hud = _hud()
        hud.press("move")
        self.assertEqual(hud.pending_order, "move")

        hud.set_selected("enemy")

        self.assertEqual(hud.panel_set, "idle")
        self.assertIsNone(hud.pending_order)


class PressAndOrderTests(unittest.TestCase):
    def test_given_move_pressed_then_it_arms_a_pending_order_and_issues_no_order_itself(self):
        hud = _hud()

        order = hud.press("move")

        self.assertIsNone(order)
        self.assertEqual(hud.pending_order, "move")

    def test_given_halt_pressed_then_it_is_returned_as_an_immediately_issuable_order(self):
        hud = _hud()

        order = hud.press("halt")

        self.assertEqual(order, "halt")

    def test_given_a_command_the_engine_does_not_support_then_pressing_it_issues_no_order(self):
        hud = _hud()

        self.assertIsNone(hud.press("charge"))
        self.assertIsNone(hud.press("withdraw"))
        self.assertIsNone(hud.press("rally"))

    def test_given_order_completed_then_pending_order_clears_and_navigation_returns_to_idle(self):
        hud = _hud()
        hud.press("move")

        hud.order_completed()

        self.assertIsNone(hud.pending_order)
        self.assertEqual(hud.panel_set, "idle")


class ButtonEnabledTests(unittest.TestCase):
    def test_given_an_unsupported_command_then_it_is_always_disabled(self):
        hud = _hud()
        player = hud.battle.regiments["player"]

        self.assertFalse(hud._button_enabled("charge", player))

    def test_given_back_then_it_is_always_enabled(self):
        hud = _hud()

        self.assertTrue(hud._button_enabled("back", None))

    def test_given_halt_then_it_is_enabled_only_while_moving(self):
        hud = _hud()
        player = hud.battle.regiments["player"]

        self.assertFalse(hud._button_enabled("halt", player))
        player.target_x, player.target_y = 500, 500
        self.assertTrue(hud._button_enabled("halt", player))

    def test_given_an_inactive_or_enemy_regiment_then_orders_are_disabled(self):
        hud = _hud()
        enemy = hud.battle.regiments["enemy"]

        self.assertFalse(hud._button_enabled("move", enemy))
        self.assertFalse(hud._button_enabled("move", None))


class HitTestAndOccupiesTests(unittest.TestCase):
    def test_given_a_point_on_the_minimap_or_panel_then_it_is_occupied(self):
        hud = _hud()

        self.assertTrue(hud.occupies((MINIMAP_RECT[0] + 5, MINIMAP_RECT[1] + 5)))
        self.assertTrue(hud.occupies((PANEL_RECT[0] + 5, PANEL_RECT[1] + 5)))
        self.assertFalse(hud.occupies((320, 100)))

    def test_given_a_fixed_button_position_then_hit_test_returns_its_name(self):
        hud = _hud()
        pos, _frames, _size = FIXED_BUTTONS["options"]

        self.assertEqual(hud.hit_test((PANEL_RECT[0] + pos[0] + 1, PANEL_RECT[1] + pos[1] + 1)), "options")

    def test_given_the_move_slot_position_then_hit_test_returns_move(self):
        hud = _hud()
        # TL slot: COMMAND_SUBWINDOW (492, 0) + (7, 11), inside the panel at PANEL_RECT's origin.
        pos = (PANEL_RECT[0] + 492 + 7 + 1, PANEL_RECT[1] + 0 + 11 + 1)

        self.assertEqual(hud.hit_test(pos), "move")

    def test_given_a_disabled_slot_command_then_hit_test_does_not_return_it(self):
        # Halt is only enabled while moving; the player regiment starts stationary.
        hud = _hud()
        hud.press("move")  # move set: BR = halt
        from whshr.frontend.hud import COMMAND_SUBWINDOW, SLOT_POSITIONS, SLOT_SIZE
        x, y = SLOT_POSITIONS["BR"]
        pos = (PANEL_RECT[0] + COMMAND_SUBWINDOW[0] + x + SLOT_SIZE[0] // 2,
              PANEL_RECT[1] + COMMAND_SUBWINDOW[1] + y + SLOT_SIZE[1] // 2)

        self.assertIsNone(hud.hit_test(pos))

    def test_given_a_window_larger_than_native_size_then_hit_test_still_scales_correctly(self):
        # BattleView renders at full window resolution; the HUD must letterbox its own native
        # 640x480 layout onto that window (matching NativeScreenView._layout()) for both drawing
        # and hit-testing, the same way every other screen already does.
        hud = _hud()
        hud._draw_size = (1280, 800)  # exact*scale: min(1280/640, 800/480)=1.666 -> integer scale 1
        left, top, scale = hud._layout()
        self.assertEqual(scale, 1)
        pos, _frames, _size = FIXED_BUTTONS["options"]
        window_pos = (left + (PANEL_RECT[0] + pos[0] + 1) * scale, top + (PANEL_RECT[1] + pos[1] + 1) * scale)

        self.assertEqual(hud.hit_test(window_pos), "options")

    def test_given_an_exact_multiple_window_then_hit_test_uses_the_integer_scale(self):
        hud = _hud()
        hud._draw_size = (1280, 960)  # exactly 2x native
        left, top, scale = hud._layout()
        self.assertEqual((left, top, scale), (0, 0, 2))
        pos, _frames, _size = FIXED_BUTTONS["options"]
        window_pos = ((PANEL_RECT[0] + pos[0] + 1) * scale, (PANEL_RECT[1] + pos[1] + 1) * scale)

        self.assertEqual(hud.hit_test(window_pos), "options")


class MinimapTests(unittest.TestCase):
    def test_given_a_minimap_pixel_when_converted_then_it_maps_to_the_battlefield_axes(self):
        hud = _hud()

        left, top, width, height = hud._map_scale()
        self.assertEqual(hud.minimap_position((left, top)), (0.0, 800.0))
        self.assertEqual(hud.minimap_position((left + width - 1, top + height - 1)), (1000.0, 0.0))
        self.assertIsNone(hud.minimap_position((0, 0)))

    def test_given_a_regiment_position_then_world_to_map_pixel_round_trips_through_minimap_position(self):
        hud = _hud()
        player = hud.battle.regiments["player"]

        pixel = hud._world_to_map_pixel(player.x, player.y)
        world = hud.minimap_position(pixel)

        self.assertAlmostEqual(world[0], player.x, delta=6.0)
        self.assertAlmostEqual(world[1], player.y, delta=6.0)

    def test_given_a_regiment_marker_then_minimap_regiment_at_finds_it_by_proximity(self):
        hud = _hud()
        player = hud.battle.regiments["player"]

        pixel = hud._world_to_map_pixel(player.x, player.y)

        self.assertEqual(hud.minimap_regiment_at(pixel), "player")
        self.assertIsNone(hud.minimap_regiment_at((0, 0)))

    def test_given_marker_mode_0_then_every_regiment_shows_its_banner(self):
        hud = _hud()
        player, enemy = hud.battle.regiments.values()

        self.assertTrue(hud._shows_banner(player))
        self.assertTrue(hud._shows_banner(enemy))

    def test_given_marker_mode_1_then_only_the_selected_regiment_shows_its_banner(self):
        hud = _hud()
        hud.marker_mode = 1
        player, enemy = hud.battle.regiments.values()

        self.assertTrue(hud._shows_banner(player))
        self.assertFalse(hud._shows_banner(enemy))

    def test_given_marker_mode_2_then_only_friendly_regiments_show_their_banner(self):
        hud = _hud()
        hud.marker_mode = 2
        player, enemy = hud.battle.regiments.values()

        self.assertTrue(hud._shows_banner(player))
        self.assertFalse(hud._shows_banner(enemy))

    def test_given_a_camera_at_north_yaw_then_its_eye_is_pulled_back_opposite_its_look_direction(self):
        # whshr.camera.BattleCamera.pan()'s look (eye-to-target) direction is
        # (-sin yaw, -cos yaw); the eye sits `distance` back along the opposite direction, so it
        # must never coincide with the target it looks at (the pre-fix behavior drew the marker
        # at the target itself).
        camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=180.0, distance=50.0)
        from whshr.battlefield import WORLD_PER_MESH

        eye_x, eye_y = Hud._camera_eye_position(camera)

        self.assertAlmostEqual(eye_x, 500.0, places=6)
        self.assertAlmostEqual(eye_y, 400.0 - 50.0 * WORLD_PER_MESH, places=6)

    def test_given_a_camera_at_east_yaw_then_its_eye_offsets_along_x(self):
        camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=90.0, distance=50.0)
        from whshr.battlefield import WORLD_PER_MESH

        eye_x, eye_y = Hud._camera_eye_position(camera)

        self.assertAlmostEqual(eye_x, 500.0 + 50.0 * WORLD_PER_MESH, places=6)
        self.assertAlmostEqual(eye_y, 400.0, places=6)

    def test_given_a_fighting_player_regiment_then_its_dot_frame_is_the_fighting_friendly_base_plus_facing(self):
        hud = _hud()
        player = hud.battle.regiments["player"]
        player.in_melee, player.direction = True, 0

        self.assertEqual(hud._regiment_dot_frame(player), 119)

    def test_given_a_routing_enemy_regiment_then_its_dot_frame_is_the_broken_enemy_base_plus_facing(self):
        hud = _hud()
        enemy = hud.battle.regiments["enemy"]
        enemy.routing, enemy.direction = True, 128  # 128/64 = 2 eighths

        self.assertEqual(hud._regiment_dot_frame(enemy), 143 + 2)

    def test_given_a_clicked_unit_when_selected_then_it_is_promoted_to_the_top_paint_order(self):
        hud = _hud()

        hud._promote_marker("enemy")

        self.assertEqual(list(hud._marker_order)[-1], "enemy")


class HudClassTests(unittest.TestCase):
    def test_given_a_unit_without_an_s_side_stat_then_hud_class_is_none(self):
        from whshr.engine import _decode_combat_profile

        decoded = _decode_combat_profile({})

        self.assertIsNone(decoded["hud_class"])

    def test_given_the_archer_race_type_then_hud_class_is_arch(self):
        from whshr.engine import _decode_combat_profile

        decoded = _decode_combat_profile({"stats": {"s_side": [3, 10, 10, 1]}})

        self.assertEqual(decoded["hud_class"], "arch")

    def test_given_the_wizard_race_type_then_hud_class_is_wiz(self):
        from whshr.engine import _decode_combat_profile

        decoded = _decode_combat_profile({"stats": {"s_side": [19, 1, 1, 1]}})

        self.assertEqual(decoded["hud_class"], "wiz")


class BattleViewHudInputTests(unittest.TestCase):
    def _view(self, hud, selected_id="player"):
        view = BattleView.__new__(BattleView)
        view.hud = hud
        view.scene = SimpleNamespace(selected_id=selected_id, battle=SimpleNamespace(
            regiments={"player": SimpleNamespace(player=True)}))
        view.camera = SimpleNamespace()
        view.order_mode = None
        view._ground_click = Mock(return_value=(("ground",),))
        return view

    def _hud_mock(self, **overrides):
        base = dict(
            click_minimap_tab=lambda pos: False, minimap_position=lambda pos: None,
            minimap_regiment_at=lambda pos: None, hit_test=lambda pos: None,
            occupies=lambda pos: True, set_pressed=Mock(), press=lambda name: None,
            order_completed=Mock(),
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_given_a_non_actionable_hud_click_when_handled_then_it_never_reaches_ground_picking(self):
        view = self._view(self._hud_mock())
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        view._ground_click.assert_not_called()

    def test_given_a_selected_unit_when_the_minimap_is_clicked_with_a_pending_move_then_it_moves(self):
        hud = self._hud_mock(minimap_position=lambda pos: (123.0, 456.0))
        view = self._view(hud)
        view.order_mode = "move"

        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("move_to", 123.0, 456.0),))
        view._ground_click.assert_not_called()
        hud.order_completed.assert_called_once()

    def test_given_no_pending_order_then_an_empty_minimap_click_issues_nothing(self):
        hud = self._hud_mock(minimap_position=lambda pos: (123.0, 456.0))
        view = self._view(hud)

        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        view._ground_click.assert_not_called()

    def test_given_a_move_button_when_pressed_then_order_mode_is_armed_and_no_order_fires_yet(self):
        hud = self._hud_mock(hit_test=lambda pos: "move", press=lambda name: None)
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(down), ())
        self.assertEqual(view.order_mode, "move")
        self.assertEqual(hud.set_pressed.call_args_list[-1].args, ("move",))

    def test_given_a_halt_button_when_pressed_then_it_issues_the_halt_order_immediately(self):
        hud = self._hud_mock(hit_test=lambda pos: "halt", press=lambda name: "halt")
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(down), (("halt",),))
        hud.order_completed.assert_called_once()

    def test_given_a_right_click_that_ends_on_hud_chrome_then_it_does_not_issue_a_ground_order(self):
        hud = self._hud_mock(occupies=lambda pos: pos == (20, 20))
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=3, pos=(10, 10))
        up = SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=3, pos=(20, 20))

        self.assertEqual(view.events(down), ())
        self.assertEqual(view.events(up), ())
        view._ground_click.assert_not_called()

    def test_given_a_unit_marker_when_clicked_on_the_minimap_then_that_unit_is_selected(self):
        hud = self._hud_mock(minimap_regiment_at=lambda pos: "player", minimap_position=lambda pos: (1.0, 2.0))
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("select", "player"),))
        view._ground_click.assert_not_called()

    def test_given_a_minimap_tab_click_then_it_is_consumed_without_a_ground_or_move_order(self):
        hud = self._hud_mock(click_minimap_tab=lambda pos: True)
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        view._ground_click.assert_not_called()


class BattleBannerVisibilityTests(unittest.TestCase):
    def _view_with_banner(self, active=True):
        from whshr.battlefield import SpriteFrame, SpriteSheet
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
        from whshr.frontend.battle_view import BANNER_MARKER_RAISE, INSTANCE
        instance = INSTANCE.unpack(self._view_with_banner()._instances())

        self.assertEqual(instance[:3], (12.5, 2.0 + BANNER_MARKER_RAISE, 25.0))
        self.assertEqual(instance[3:7], (0.0, 0.0, 32.0, 32.0))
        self.assertEqual(instance[7:], (16.0, 32.0, 1.0))

    def test_given_a_destroyed_bannered_regiment_when_the_battle_view_draws_then_no_banner_marker_is_visible(self):
        self.assertEqual(self._view_with_banner(active=False)._instances(), b"")

    def test_given_overlapping_regiment_banners_when_one_is_selected_then_its_marker_is_drawn_last(self):
        from whshr.battlefield import SpriteFrame, SpriteSheet
        from whshr.frontend.battle_view import INSTANCE
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
