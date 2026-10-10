"""HUD geometry/panel-state/input tests without requiring the optional pygame/zengl frontend stack.

Layout source: notes/game_rules.md "Battle HUD layout". The HUD draws GPU quads directly (matching
the rest of the engine's rendering), so these tests exercise the pure logic that decides *what*
gets drawn (panel state, slot layout, hit testing, minimap marker selection) rather than pixel
output.
"""
import struct
import sys
import types
import unittest
from array import array
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock, patch

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

from whshr.battle_scene import BattleScene
from whshr.battle_events import BattleEvent
from whshr.battlefield import WORLD_PER_MESH
from whshr.engine import Battle, Regiment
from whshr.frontend.battle_view import BattleView
from whshr.frontend.hud import FIXED_BUTTONS, MINIMAP_RECT, PANEL_RECT, Hud
from whshr.rules import Side


def _hud(selected="player", regiments=None, **overrides):
    if regiments is None:
        regiments = [
            Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10, ranks=2, hud_class="inf"),
            Regiment("enemy", "Enemy", 700, 600, 128, Side.ENEMY, models=10, ranks=2, hud_class="inf"),
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
    def test_item_popup_is_painted_after_the_unit_name(self):
        hud = _hud()
        order = []
        hud.panel_bg = object()
        hud._log_panel = None
        hud._unit_info_panel = object()
        hud._draw_panel = lambda quad, *args, **kwargs: order.append("unit_info") if quad is hud._unit_info_panel else None
        hud._draw_readout = lambda regiment: None
        hud._draw_fixed_buttons = lambda: None
        hud._draw_slots = lambda regiment: None
        hud._draw_minimap = lambda regiment, camera: None
        hud._draw_item_list = lambda regiment: order.append("items")

        hud.draw(640, 480)

        self.assertEqual(order, ["unit_info", "items"])

    def test_item_bearer_can_open_list_and_select_an_unused_item(self):
        bearer = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf",
                          items=("ItemGrudgeBringer", "ItemSwordOfMight"), has_leader=True)
        hud = _hud(regiments=[bearer])
        hud.press("attack")
        self.assertEqual(hud.slots()["BR"], "items")
        hud.press("items")
        self.assertEqual(hud.hit_test(_panel_pos(hud, 210, 75)), "item:ItemGrudgeBringer")
        self.assertIsNone(hud.hit_test(_panel_pos(hud, 210, 94)))  # passive item
        bearer.used_items.add("ItemGrudgeBringer")
        self.assertIsNone(hud.hit_test(_panel_pos(hud, 210, 75)))
        bearer.used_items.clear()
        self.assertEqual(hud.press("item:ItemGrudgeBringer"), "item:ItemGrudgeBringer")
        self.assertFalse(hud.item_list_open)

    def test_grudgebringer_row_reenables_after_the_next_wind(self):
        from whshr import spell_effects

        bearer = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf",
                          items=("ItemGrudgeBringer",), has_leader=True)
        hud = _hud(regiments=[bearer])
        hud.press("attack")
        hud.press("items")
        point = _panel_pos(hud, 210, 75)
        self.assertEqual(hud.hit_test(point), "item:ItemGrudgeBringer")
        hud.battle.arm_item("player", "ItemGrudgeBringer")
        self.assertIsNone(hud.hit_test(point))
        hud.battle.tick_count = spell_effects.WIND_TICKS
        hud.battle.tick()
        self.assertEqual(hud.hit_test(point), "item:ItemGrudgeBringer")

    def test_spent_grudgebringer_does_not_disable_the_items_menu(self):
        bearer = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf",
                          items=("ItemGrudgeBringer",), has_leader=True)
        hud = _hud(regiments=[bearer])
        hud.press("attack")
        bearer.used_items.add("ItemGrudgeBringer")

        self.assertTrue(hud._button_enabled("items", bearer))
        hud.press("items")
        self.assertTrue(hud.item_list_open)
        self.assertIsNone(hud.hit_test(_panel_pos(hud, 210, 75)))

    def test_used_item_has_a_check_on_the_right_until_rearmed(self):
        from whshr import spell_effects

        bearer = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf",
                          items=("ItemPotionOfStrength", "ItemGrudgeBringer", "ItemSwordOfMight"),
                          has_leader=True)
        hud = _hud(regiments=[bearer])
        hud.press("attack")
        hud.press("items")
        hud._item_labels = [Mock() for _ in bearer.items]
        hud._icon = Mock(return_value=object())
        check = object()
        hud._used_item_check_quad = Mock(return_value=check)
        draws = []
        hud._draw_panel = lambda quad, *args, **kwargs: draws.append((quad, args))

        hud._draw_item_list(bearer)
        self.assertEqual([args for quad, args in draws if quad is check], [])

        hud.battle.arm_item("player", "ItemPotionOfStrength")
        hud.battle.arm_item("player", "ItemGrudgeBringer")
        draws.clear()
        hud._draw_item_list(bearer)
        self.assertEqual([args for quad, args in draws if quad is check], [(420, 74), (420, 93)])

        hud.battle.tick_count = spell_effects.WIND_TICKS
        hud.battle.tick()
        draws.clear()
        hud._draw_item_list(bearer)
        self.assertEqual([args for quad, args in draws if quad is check], [(420, 74)])

    def test_item_menu_requires_a_living_leader(self):
        bearer = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf",
                          items=("ItemGrudgeBringer",), has_leader=False)
        hud = _hud(regiments=[bearer])
        hud.press("attack")

        self.assertEqual(hud.slots(), {"TL": "charge", "C": "back"})
        self.assertFalse(hud._button_enabled("items", bearer))

    def test_given_hidden_player_then_deployment_panel_and_friendly_markers_remain_available(self):
        hud = _hud()
        hud.battle.phase = "deployment"
        for regiment in hud.battle.regiments.values():
            regiment.hidden = True
        ally = Regiment("ally", "Ally", 200, 200, 0, Side.NEUTRAL, hidden=True)
        hud.battle.regiments["ally"] = ally
        self.assertEqual(hud.panel_state(), ("deployment", "inf"))
        self.assertEqual([r.identifier for r in hud._minimap_regiments()], ["player", "ally"])
        self.assertTrue(hud.battle.regiments["player"].hidden)

    def test_given_deployment_then_each_class_has_only_its_documented_controls(self):
        expected = {
            "inf": {"TL": "ranks_up", "TR": "move", "BR": "independent", "BL": "ranks_down", "C": "facing_subset"},
            "arch": {"TL": "ranks_up", "TR": "move", "BR": "independent", "BL": "ranks_down", "C": "facing_subset"},
            "wiz": {"TR": "move", "BR": "independent", "C": "facing_subset"},
            "mon": {"TR": "move", "BR": "independent", "C": "facing_subset"},
            "art": {"BR": "independent", "C": "facing_subset"}, None: {},
        }
        for unit_class, slots in expected.items():
            with self.subTest(unit_class=unit_class):
                hud = _hud()
                hud.battle.phase = "deployment"
                hud.battle.regiments["player"].hud_class = unit_class
                self.assertEqual(hud.slots(), slots)
                for name in ("attack", "halt", "charge", "fire", "magic", "items", "rally",
                             "withdraw", "fight_harder", "turn_left", "face_point", "ranks_subset"):
                    self.assertIsNone(hud.press(name))
                self.assertEqual(hud.slots(), slots)

    def test_given_deployment_facing_button_then_every_class_gets_the_turn_buttons_and_back_returns(self):
        facing = {"TL": "turn_left", "TR": "turn_right", "BL": "about_face", "BR": "face_point", "C": "back"}
        for unit_class in ("inf", "arch", "wiz", "mon", "art"):
            with self.subTest(unit_class=unit_class):
                hud = _hud()
                hud.battle.phase = "deployment"
                hud.battle.regiments["player"].hud_class = unit_class
                self.assertIsNone(hud.press("facing_subset"))
                self.assertEqual(hud.panel_state(), ("deployment_facing", unit_class))
                self.assertEqual(hud.slots(), facing)
                for name in ("turn_left", "turn_right", "about_face"):
                    self.assertEqual(hud.press(name), name)
                self.assertEqual(hud.slots(), facing)  # repeatable without reopening the sub-panel
                self.assertIsNone(hud.press("face_point"))
                self.assertEqual(hud.pending_order, "face_point")
                self.assertIsNone(hud.press("ranks_up"))  # not on this sub-panel
                hud.press("back")
                self.assertEqual(hud.panel_state(), ("deployment", unit_class))

    def test_given_deployment_facing_subpanel_when_battle_starts_then_the_idle_panel_is_shown(self):
        hud = _hud()
        hud.battle.phase = "deployment"
        hud.battle.regiments["player"].hud_class = "wiz"
        hud.press("facing_subset")
        self.assertEqual(hud.press("start_battle"), "start_battle")
        hud.battle.start_battle()
        self.assertEqual(hud.panel_state(), ("idle", "wiz"))

    def test_given_deployment_without_selection_then_start_is_available_and_no_unit_controls_are_shown(self):
        hud = _hud(selected=None)
        hud.battle.phase = "deployment"
        self.assertEqual(hud.slots(), {})
        self.assertEqual(hud.hit_test((25, 435)), "start_battle")
        self.assertEqual(hud.press("start_battle"), "start_battle")
        hud.battle.start_battle()
        self.assertEqual(hud.hit_test((25, 435)), "pause")

    def test_given_deployment_move_targeting_then_the_deployment_panel_does_not_open_battle_subpanels(self):
        hud = _hud()
        hud.battle.phase = "deployment"
        hud.press("move")
        self.assertEqual(hud.panel_state(), ("deployment", "inf"))
        self.assertEqual(hud.pending_order, "move")

    def test_given_nothing_selected_then_the_idle_no_selection_layout_is_used(self):
        hud = _hud(selected=None)

        self.assertEqual(hud.panel_state(), ("idle", None))
        self.assertEqual(hud.slots(), {"TL": "move", "TR": "attack", "BR": "independent"})

    def test_given_an_idle_infantry_regiment_then_it_has_move_attack_independent(self):
        hud = _hud()

        self.assertEqual(hud.panel_state(), ("idle", "inf"))
        self.assertEqual(hud.slots(), {"TL": "move", "TR": "attack", "BR": "independent"})

    def test_given_an_idle_artillery_regiment_then_it_has_no_move_slot(self):
        regiments = [Regiment("player", "Gun", 0, 0, 0, Side.PLAYER, hud_class="art")]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.slots(), {"TR": "attack", "BR": "independent"})

    def test_given_an_idle_wizard_regiment_then_magic_and_back_are_present(self):
        regiments = [Regiment("player", "Wiz", 0, 0, 0, Side.PLAYER, hud_class="wiz")]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.slots(),
                         {"TL": "move", "TR": "attack", "BR": "independent", "BL": "magic", "C": "back"})

    def test_given_a_regiment_in_melee_then_the_melee_noncaster_set_is_used(self):
        regiments = [Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf", in_melee=True)]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.panel_state(), ("melee_noncaster", "inf"))
        self.assertEqual(hud.slots(), {"TR": "withdraw", "C": "fight_harder"})
        self.assertTrue(hud._button_enabled("fight_harder", hud.battle.regiments["player"]))
        self.assertEqual(hud.press("fight_harder"), "fight_harder")

    def test_given_a_routing_regiment_then_the_rally_set_is_used(self):
        regiments = [Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf", routing=True)]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.panel_state(), ("rally", "inf"))
        self.assertEqual(hud.slots(), {"BR": "rally"})

    def test_attack_target_approaches_with_idle_buttons_then_charge_hides_them(self):
        regiments = [Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf", attack_target="enemy")]
        hud = _hud(regiments=regiments)

        self.assertEqual(hud.panel_state(), ("idle", "inf"))
        self.assertEqual(hud.slots(), {"TL": "move", "TR": "attack", "BR": "independent"})
        regiments[0].charge_started_target = "enemy"
        self.assertEqual(hud.panel_state(), ("charging", "inf"))
        self.assertEqual(hud.slots(), {})
        regiments[0].in_melee = True
        self.assertEqual(hud.slots(), {"TR": "withdraw", "C": "fight_harder"})

    def test_braced_unit_uses_melee_buttons_and_pursuer_uses_rally(self):
        regiment = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf", braced=True)
        hud = _hud(regiments=[regiment])
        self.assertEqual(hud.slots(), {"TR": "withdraw", "C": "fight_harder"})
        regiment.braced = False
        regiment.pursuing = True
        self.assertEqual(hud.slots(), {"BR": "rally"})

    def test_free_charge_hides_buttons_until_it_ends(self):
        regiment = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class="inf")
        hud = _hud(regiments=[regiment])
        hud.battle.order_charge_forward("player")
        self.assertTrue(regiment.free_charging)
        self.assertEqual(hud.slots(), {})
        hud.battle.order_halt("player")
        self.assertEqual(hud.slots(), {"TL": "move", "TR": "attack", "BR": "independent"})

    def test_attack_approach_charge_and_melee_panels_by_class(self):
        cases = {
            "inf": ({"TL": "move", "TR": "attack", "BR": "independent"},
                    {"TR": "withdraw", "BR": "items", "C": "fight_harder"}),
            "arch": ({"TL": "move", "TR": "attack", "BR": "independent"},
                     {"TR": "withdraw", "BR": "items", "C": "fight_harder"}),
            "art": ({"TR": "attack", "BR": "independent"},
                    {"TR": "withdraw", "BR": "items", "C": "fight_harder"}),
            "wiz": ({"TL": "move", "TR": "attack", "BR": "independent", "BL": "magic", "C": "back"},
                    {"TR": "withdraw", "BR": "items", "BL": "magic", "C": "fight_harder"}),
            "mon": ({"TL": "move", "TR": "attack", "BR": "independent"},
                    {"TR": "withdraw", "BR": "items", "C": "fight_harder"}),
        }
        for hud_class, (approach, melee) in cases.items():
            with self.subTest(hud_class=hud_class):
                bearer = Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class=hud_class,
                                  items=("ItemGrudgeBringer",), has_leader=True, attack_target="enemy")
                hud = _hud(regiments=[bearer])
                self.assertEqual(hud.slots(), approach)
                bearer.charge_started_target = "enemy"
                self.assertEqual(hud.slots(), {})
                bearer.in_melee = True
                self.assertEqual(hud.slots(), melee)
                bearer.has_leader = False
                bearer.leader_uid = -1
                self.assertNotIn("items", hud.slots().values())

    def test_attack_order_keeps_idle_panel_until_charge_reach(self):
        bearer = Regiment("player", "P", 100, 100, 0, Side.PLAYER, hud_class="inf")
        enemy = Regiment("enemy", "E", 100, 200, 256, Side.ENEMY, hud_class="inf")
        hud = _hud(regiments=[bearer, enemy])
        hud.battle.order_attack("player", "enemy")
        self.assertEqual(hud.panel_state(), ("idle", "inf"))

        hud.battle.tick()

        self.assertEqual(bearer.charge_started_target, "enemy")
        self.assertEqual(hud.panel_state(), ("charging", "inf"))

    def test_given_a_class_with_no_buttons_then_no_slots_are_shown(self):
        regiments = [Regiment("player", "P", 0, 0, 0, Side.PLAYER, hud_class=None)]
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

    def test_charge_and_rally_are_orders_while_unimplemented_commands_issue_none(self):
        hud = _hud()

        self.assertEqual(hud.press("charge"), "charge")
        self.assertIsNone(hud.press("withdraw"))
        self.assertEqual(hud.press("rally"), "rally")

    def test_given_order_completed_then_pending_order_clears_and_navigation_returns_to_idle(self):
        hud = _hud()
        hud.press("move")

        hud.order_completed()

        self.assertIsNone(hud.pending_order)
        self.assertEqual(hud.panel_set, "idle")


class ButtonEnabledTests(unittest.TestCase):
    def test_charge_is_enabled_for_a_player_regiment(self):
        hud = _hud()
        player = hud.battle.regiments["player"]

        self.assertTrue(hud._button_enabled("charge", player))

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


def _panel_pos(hud, x, y):
    """Convert command-panel-native (x, y) into a raw window pixel, given the panel's own
    bottom-pinned, horizontally-centered screen anchor."""
    left, top, scale = hud._panel_screen_origin()
    return (left + x * scale, top + y * scale)


def _map_pos(hud, x, y):
    """Convert minimap-native (x, y) into a raw window pixel, given the minimap's own
    top-right-pinned screen anchor."""
    left, top, scale = hud._minimap_screen_origin()
    return (left + x * scale, top + y * scale)


class HitTestAndOccupiesTests(unittest.TestCase):
    def test_given_a_point_on_the_minimap_or_panel_then_it_is_occupied(self):
        hud = _hud()

        self.assertTrue(hud.occupies(_map_pos(hud, 5, 5)))
        self.assertTrue(hud.occupies(_panel_pos(hud, 5, 5)))
        self.assertFalse(hud.occupies((0, 0)))

    def test_given_a_fixed_button_position_then_hit_test_returns_its_name(self):
        hud = _hud()
        pos, _frames, _size = FIXED_BUTTONS["options"]

        self.assertEqual(hud.hit_test(_panel_pos(hud, pos[0] + 1, pos[1] + 1)), "options")

    def test_given_the_move_slot_position_then_hit_test_returns_move(self):
        hud = _hud()
        # TL slot: COMMAND_SUBWINDOW (492, 0) + (7, 11), relative to the panel's own origin.
        pos = _panel_pos(hud, 492 + 7 + 1, 0 + 11 + 1)

        self.assertEqual(hud.hit_test(pos), "move")

    def test_given_a_disabled_slot_command_then_hit_test_does_not_return_it(self):
        # Halt is only enabled while moving; the player regiment starts stationary.
        hud = _hud()
        hud.press("move")  # move set: BR = halt
        from whshr.frontend.hud import COMMAND_SUBWINDOW, SLOT_POSITIONS, SLOT_SIZE
        x, y = SLOT_POSITIONS["BR"]
        pos = _panel_pos(hud, COMMAND_SUBWINDOW[0] + x + SLOT_SIZE[0] // 2,
                         COMMAND_SUBWINDOW[1] + y + SLOT_SIZE[1] // 2)

        self.assertIsNone(hud.hit_test(pos))

    def test_given_a_window_larger_than_native_size_then_hit_test_still_scales_correctly(self):
        # BattleView renders at full window resolution; the HUD must scale/anchor its own
        # native-space panel and minimap onto that window for both drawing and hit-testing.
        hud = _hud()
        hud._draw_size = (1280, 800)  # exact*scale: min(1280/640, 800/480)=1.666 -> integer scale 1
        self.assertEqual(hud._scale(), 1)
        pos, _frames, _size = FIXED_BUTTONS["options"]

        self.assertEqual(hud.hit_test(_panel_pos(hud, pos[0] + 1, pos[1] + 1)), "options")

    def test_given_an_exact_multiple_window_then_hit_test_uses_the_integer_scale(self):
        hud = _hud()
        hud._draw_size = (1280, 960)  # exactly 2x native
        self.assertEqual(hud._scale(), 2)
        pos, _frames, _size = FIXED_BUTTONS["options"]

        self.assertEqual(hud.hit_test(_panel_pos(hud, pos[0] + 1, pos[1] + 1)), "options")

    def test_given_a_window_larger_than_native_size_then_the_minimap_is_pinned_top_right(self):
        hud = _hud()
        hud._draw_size = (1280, 960)  # exactly 2x native, so the minimap has room to spare
        left, top, scale = hud._minimap_screen_origin()

        self.assertEqual(scale, 2)
        self.assertEqual(left, 1280 - MINIMAP_RECT[2] * scale)
        self.assertEqual(top, MINIMAP_RECT[1] * scale)

    def test_given_a_window_larger_than_native_size_then_the_panel_is_pinned_to_the_bottom(self):
        hud = _hud()
        hud._draw_size = (1280, 960)
        left, top, scale = hud._panel_screen_origin()

        self.assertEqual(top, 960 - PANEL_RECT[3] * scale)
        self.assertEqual(left, (1280 - PANEL_RECT[2] * scale) / 2)


class MinimapTests(unittest.TestCase):
    def test_given_a_minimap_pixel_when_converted_then_it_maps_to_the_battlefield_axes(self):
        hud = _hud()

        left, top, width, height = hud._map_scale()
        self.assertEqual(hud.minimap_position(_map_pos(hud, left, top)), (0.0, 800.0))
        self.assertEqual(hud.minimap_position(_map_pos(hud, left + width - 1, top + height - 1)), (1000.0, 0.0))
        self.assertIsNone(hud.minimap_position((0, 0)))

    def test_given_a_regiment_position_then_world_to_map_pixel_round_trips_through_minimap_position(self):
        hud = _hud()
        player = hud.battle.regiments["player"]

        native_pixel = hud._world_to_map_pixel(player.x, player.y)
        world = hud.minimap_position(_map_pos(hud, *native_pixel))

        self.assertAlmostEqual(world[0], player.x, delta=6.0)
        self.assertAlmostEqual(world[1], player.y, delta=6.0)

    def test_given_a_regiment_marker_then_minimap_regiment_at_finds_it_by_proximity(self):
        hud = _hud()
        player = hud.battle.regiments["player"]

        native_pixel = hud._world_to_map_pixel(player.x, player.y)

        self.assertEqual(hud.minimap_regiment_at(_map_pos(hud, *native_pixel)), "player")
        self.assertIsNone(hud.minimap_regiment_at((0, 0)))

    def test_given_a_regiment_with_a_visible_banner_then_clicking_the_banner_selects_it(self):
        # notes/game_rules.md: the banner is anchored 8px left, 24px above the regiment's dot; a
        # click anywhere on that larger, more visible banner rect should hit the regiment too, not
        # only the small 8x8 dot underneath it.
        hud = _hud()
        player = hud.battle.regiments["player"]
        marker_frame = SimpleNamespace(width=16, height=32)
        hud._minimap_marker = lambda regiment: marker_frame if regiment.identifier == "player" else None

        native_pixel = hud._world_to_map_pixel(player.x, player.y)
        banner_point = (native_pixel[0] - 8 + 2, native_pixel[1] - 24 + 2)  # inside the banner, off the dot

        self.assertEqual(hud.minimap_regiment_at(_map_pos(hud, *banner_point)), "player")

    def _stacked_hud(self, regiments):
        """3+ regiments at the exact same position, so every hit test finds all of them."""
        return _hud(regiments=regiments)

    def test_given_a_stack_of_markers_then_the_topmost_one_not_yet_selected_wins(self):
        regiments = [Regiment("enemy_a", "EnemyA", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf"),
                    Regiment("friendly_b", "FriendlyB", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf"),
                    Regiment("friendly_c", "FriendlyC", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf")]
        hud = self._stacked_hud(regiments)
        pixel = hud._world_to_map_pixel(500, 500)

        self.assertEqual(hud.minimap_regiment_at(_map_pos(hud, *pixel)), "friendly_c")

    def test_given_the_topmost_is_already_selected_then_the_bottom_most_friendly_is_picked_next(self):
        regiments = [Regiment("enemy_a", "EnemyA", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf"),
                    Regiment("friendly_b", "FriendlyB", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf"),
                    Regiment("friendly_c", "FriendlyC", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf")]
        hud = self._stacked_hud(regiments)
        hud.selected = "friendly_c"  # already on top
        pixel = hud._world_to_map_pixel(500, 500)

        self.assertEqual(hud.minimap_regiment_at(_map_pos(hud, *pixel)), "friendly_b")

    def test_given_repeated_clicks_on_the_same_stack_then_selection_cycles_through_every_friendly(self):
        regiments = [Regiment("enemy_a", "EnemyA", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf"),
                    Regiment("friendly_b", "FriendlyB", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf"),
                    Regiment("friendly_c", "FriendlyC", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf")]
        hud = self._stacked_hud(regiments)
        pixel = hud._world_to_map_pixel(500, 500)
        seen = []
        for _ in range(4):
            picked = hud.minimap_regiment_at(_map_pos(hud, *pixel))
            seen.append(picked)
            hud.set_selected(picked)  # promotes it to the top, as battle_view.py's real flow would

        self.assertEqual(seen, ["friendly_c", "friendly_b", "friendly_c", "friendly_b"])

    def test_given_no_friendly_unit_in_the_stack_then_it_cycles_through_any_side(self):
        regiments = [Regiment("enemy_a", "EnemyA", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf"),
                    Regiment("enemy_b", "EnemyB", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf")]
        hud = self._stacked_hud(regiments)
        hud.selected = "enemy_b"  # already on top
        pixel = hud._world_to_map_pixel(500, 500)

        self.assertEqual(hud.minimap_regiment_at(_map_pos(hud, *pixel)), "enemy_a")

    def test_given_a_single_unit_stack_already_selected_then_it_is_reselected(self):
        regiments = [Regiment("player", "Player", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf")]
        hud = self._stacked_hud(regiments)
        hud.selected = "player"
        pixel = hud._world_to_map_pixel(500, 500)

        self.assertEqual(hud.minimap_regiment_at(_map_pos(hud, *pixel)), "player")

    def test_given_the_selection_is_in_the_stack_but_not_on_top_then_the_top_still_wins(self):
        # Not one of the two rules the user described; treated the same as "not in the stack at
        # all" rather than a third special case - topmost wins whenever the exact previously
        # picked regiment isn't being re-clicked.
        regiments = [Regiment("enemy_a", "EnemyA", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf"),
                    Regiment("friendly_b", "FriendlyB", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf"),
                    Regiment("friendly_c", "FriendlyC", 500, 500, 0, Side.PLAYER, models=10, hud_class="inf")]
        hud = self._stacked_hud(regiments)
        hud.selected = "friendly_b"  # in the stack, but not on top
        pixel = hud._world_to_map_pixel(500, 500)

        self.assertEqual(hud.minimap_regiment_at(_map_pos(hud, *pixel)), "friendly_c")

    def test_given_an_order_target_lookup_then_the_topmost_wins_even_if_it_is_already_selected(self):
        # minimap_target_at() (order targeting, e.g. Attack) never cycles like minimap_regiment_at()
        # (plain-click selection) does: an order always hits whatever is visually on top.
        regiments = [Regiment("enemy_a", "EnemyA", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf"),
                    Regiment("enemy_b", "EnemyB", 500, 500, 0, Side.ENEMY, models=10, hud_class="inf")]
        hud = self._stacked_hud(regiments)
        hud.selected = "enemy_b"  # already selected/on top - must not trigger any cycling here
        pixel = hud._world_to_map_pixel(500, 500)

        self.assertEqual(hud.minimap_target_at(_map_pos(hud, *pixel)), "enemy_b")

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
    def test_given_hidden_player_then_minimap_drag_and_hud_cycle_select_it_without_revealing(self):
        view = self._deployment_view()
        regiment = view.scene.battle.regiments["player"]
        regiment.hidden = True
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100), mod=0)
        self.assertEqual(view.events(down), (("select", "player"), ("begin_drag", "player", 100.0, 100.0)))
        self.assertEqual(view._cycle_regiment(1), (("select", "player"),))
        self.assertTrue(regiment.hidden)

    def _deployment_view(self, marker="player"):
        from whshr.camera import BattleCamera

        hud = self._hud_mock(minimap_regiment_at=lambda pos: marker,
                             minimap_position=lambda pos: (float(pos[0]), float(pos[1])) if pos[0] >= 0 else None)
        view = self._view(hud)
        view.camera = BattleCamera(0, 0)
        view.scene.battle = Battle(1000, 1000, [Regiment("player", "P", 100, 100, 0, Side.PLAYER, hud_class="inf"),
                                              Regiment("enemy", "E", 800, 800, 0, Side.ENEMY)], deploy=True)
        return view

    def test_given_deployment_minimap_press_then_drag_ctrl_rotation_and_release_use_placement_intents(self):
        view = self._deployment_view()
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100), mod=pygame.KMOD_SHIFT)
        self.assertEqual(view.events(down), (("select", "player"), ("begin_drag", "player", 100.0, 100.0)))
        motion = SimpleNamespace(type=pygame.MOUSEMOTION, buttons=(1, 0, 0), pos=(200, 200), mod=pygame.KMOD_CTRL)
        self.assertEqual(view.events(motion), (("drag_to", 200.0, 200.0, True),))
        motion.mod = 0
        self.assertEqual(view.events(motion), (("drag_to", 200.0, 200.0, False),))
        self.assertEqual(view.events(SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1)), (("end_drag",),))

    def test_given_minimap_drag_when_pointer_leaves_then_drag_ends(self):
        view = self._deployment_view()
        view.events(SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100)))
        self.assertEqual(view.events(SimpleNamespace(type=pygame.MOUSEMOTION, buttons=(1, 0, 0), pos=(-1, 100))),
                         (("end_drag",),))

    def test_given_enemy_press_during_deployment_then_it_is_inspected_without_dragging(self):
        view = self._deployment_view("enemy")
        self.assertEqual(view.events(SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))),
                         (("select", "enemy"),))

    def test_given_move_targeting_then_ctrl_appends_and_plain_click_replaces_and_ends_targeting(self):
        view = self._deployment_view()
        view.order_mode = "move"
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(300, 300), mod=pygame.KMOD_CTRL)
        self.assertEqual(view.events(down), (("append_waypoint", 300.0, 300.0),))
        self.assertEqual(view.order_mode, "move")
        down.mod = 0
        self.assertEqual(view.events(down), (("move_to", 300.0, 300.0),))
        self.assertIsNone(view.order_mode)

    def test_given_deployment_then_right_click_enter_and_space_cannot_issue_orders_or_start(self):
        view = self._deployment_view()
        for key in (pygame.K_RETURN, pygame.K_SPACE):
            self.assertEqual(view.events(SimpleNamespace(type=pygame.KEYDOWN, key=key)), ())
        self.assertEqual(view.events(SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=3, pos=(100, 100))), ())
        self.assertEqual(view.events(SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=3, pos=(100, 100))), ())

    def _view(self, hud, selected_id="player"):
        view = BattleView.__new__(BattleView)
        view.hud = hud
        view.scene = SimpleNamespace(selected_id=selected_id, battle=SimpleNamespace(
            regiments={"player": SimpleNamespace(player=True), "enemy": SimpleNamespace(player=False)}))
        view.camera = SimpleNamespace()
        view.order_mode = None
        view.cursors, view._cursor_mode = None, None
        view.event_log = []
        view._ground_click = Mock(return_value=(("ground",),))
        return view

    def _hud_mock(self, **overrides):
        base = dict(
            click_minimap_tab=lambda pos: False, minimap_position=lambda pos: None,
            minimap_regiment_at=lambda pos: None, minimap_target_at=lambda pos: None,
            hit_test=lambda pos: None, occupies=lambda pos: True, set_pressed=Mock(),
            press=lambda name: None, order_completed=Mock(),
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_item_selection_arms_magic_cursor_and_minimap_target(self):
        world: list[tuple[float, float] | None] = [None]
        hud = self._hud_mock(hit_test=lambda pos: "item:ItemGrudgeBringer",
                             press=lambda name: name, minimap_position=lambda pos: world[0],
                             minimap_target_at=lambda pos: None)
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))
        hud.pressed = None
        hud.set_pressed = lambda name: setattr(hud, "pressed", name)

        self.assertEqual(view.events(down), ())
        self.assertEqual(hud.pressed, "item:ItemGrudgeBringer")
        self.assertEqual(view.events(SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=(100, 100))),
                         (("arm_item", "ItemGrudgeBringer"),))
        self.assertEqual(view.order_mode, "item:ItemGrudgeBringer")
        world[0] = (0.0, 400.0)
        self.assertEqual(view._minimap_click((100, 100)), (("item_target", "ItemGrudgeBringer", 0.0, 400.0),))
        self.assertIsNone(view.order_mode)

    def test_ctrl_item_targets_repeat_until_plain_click(self):
        world = (0.0, 400.0)
        hud = self._hud_mock(minimap_position=lambda pos: world)
        view = self._view(hud)
        view.scene.battle.event_bus = SimpleNamespace(power=SimpleNamespace(player=1))
        view.order_mode = "item:ItemGrudgeBringer"
        target = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100), mod=pygame.KMOD_CTRL)

        for _ in range(2):
            self.assertEqual(view.events(target),
                             (("item_target", "ItemGrudgeBringer", *world),))
            self.assertEqual(view.order_mode, "item:ItemGrudgeBringer")
        target.mod = 0
        self.assertEqual(view.events(target),
                         (("item_target", "ItemGrudgeBringer", *world),))
        self.assertIsNone(view.order_mode)

    def test_ctrl_item_target_ends_when_player_has_no_magic_power(self):
        hud = self._hud_mock(minimap_position=lambda pos: (0.0, 400.0))
        view = self._view(hud)
        view.scene.battle.event_bus = SimpleNamespace(power=SimpleNamespace(player=0))
        view.order_mode = "item:ItemGrudgeBringer"

        self.assertEqual(view._minimap_click((100, 100), repeat_item=True),
                         (("item_target", "ItemGrudgeBringer", 0.0, 400.0),))
        self.assertIsNone(view.order_mode)

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

    def test_given_no_player_selection_then_clicking_an_enemy_marker_selects_it_for_inspection(self):
        hud = self._hud_mock(minimap_regiment_at=lambda pos: "enemy", minimap_position=lambda pos: (1.0, 2.0))
        view = self._view(hud, selected_id=None)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("select", "enemy"),))
        view._ground_click.assert_not_called()

    def test_given_a_player_selection_but_no_pending_order_then_clicking_an_enemy_marker_still_selects_it(self):
        # notes/game_rules.md "Player orders and the command panel": every order needs its own
        # button pressed first ("Attack (crossed swords) + click"), so a plain click with no
        # pending order (self.order_mode is None) always just (re)selects whatever is under it,
        # regardless of what was already selected - there is no "click an enemy to charge"
        # shortcut without first arming Attack.
        hud = self._hud_mock(minimap_regiment_at=lambda pos: "enemy", minimap_position=lambda pos: (1.0, 2.0))
        view = self._view(hud, selected_id="player")
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("select", "enemy"),))
        view._ground_click.assert_not_called()

    def test_given_an_armed_attack_order_then_clicking_an_enemy_marker_fires_the_order_not_a_selection(self):
        hud = self._hud_mock(minimap_target_at=lambda pos: "enemy", minimap_position=lambda pos: (1.0, 2.0))
        view = self._view(hud, selected_id="player")
        view.order_mode = "attack"
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("attack", "enemy"),))
        view._ground_click.assert_not_called()

    def test_given_an_armed_attack_order_and_no_minimap_target_then_it_cancels_and_logs_cannot(self):
        hud = self._hud_mock(minimap_target_at=lambda pos: None, minimap_position=lambda pos: (1.0, 2.0))
        view = self._view(hud, selected_id="player")
        view.order_mode = "attack"
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        self.assertIsNone(view.order_mode)
        self.assertEqual(view.event_log[-1], "Cannot attack!")
        view._ground_click.assert_not_called()

    def test_given_a_banner_marker_outside_the_map_area_rect_then_it_still_selects_the_regiment(self):
        # A regiment's banner is anchored above and left of its dot (notes/game_rules.md) and can
        # hang outside the minimap's strict inner map-area rect near an edge - minimap_position()
        # alone (gated on that inner rect) would then miss the click entirely and it would fall
        # through to hit_test()/occupies() and be silently swallowed as plain HUD chrome. Routing
        # must also check minimap_regiment_at(), which has no such inner-rect restriction.
        hud = self._hud_mock(minimap_regiment_at=lambda pos: "enemy", minimap_position=lambda pos: None)
        view = self._view(hud, selected_id=None)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("select", "enemy"),))
        view._ground_click.assert_not_called()

    def test_given_a_minimap_book_click_then_it_opens_the_objectives_book(self):
        hud = self._hud_mock(click_minimap_tab=lambda pos: "book")
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), (("objectives_book",),))
        view._ground_click.assert_not_called()

    def test_given_a_minimap_tab_click_then_it_is_consumed_without_a_ground_or_move_order(self):
        hud = self._hud_mock(click_minimap_tab=lambda pos: True)
        view = self._view(hud)
        event = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        self.assertEqual(view.events(event), ())
        view._ground_click.assert_not_called()


class BattleCursorTests(unittest.TestCase):
    """notes/game_rules.md "Feedback": the cursor reflects the pending order mode - Attack gets
    its own cursor, an immediately-issued order (or no action at all) uses the default."""

    def _view(self, hud):
        view = BattleView.__new__(BattleView)
        view.hud = hud
        view.scene = SimpleNamespace(selected_id="player", battle=SimpleNamespace(
            regiments={"player": SimpleNamespace(player=True)}))
        view.camera = SimpleNamespace()
        view.order_mode = None
        view.cursors = Mock()
        view._cursor_mode = None
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

    def test_given_an_attack_button_when_pressed_then_the_attack_cursor_is_set(self):
        from whshr.frontend.battle_view import BATTLE_CURSOR_GROUPS
        hud = self._hud_mock(hit_test=lambda pos: "attack", press=lambda name: None)
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        view.events(down)

        view.cursors.set.assert_called_with(BATTLE_CURSOR_GROUPS["attack"])

    def test_given_an_immediately_issued_order_then_the_default_cursor_is_restored(self):
        from whshr.frontend.battle_view import BATTLE_CURSOR_GROUPS
        hud = self._hud_mock(hit_test=lambda pos: "halt", press=lambda name: "halt")
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))

        view.events(down)

        view.cursors.set.assert_called_with(BATTLE_CURSOR_GROUPS["default"])

    def test_given_escape_then_the_default_cursor_is_restored(self):
        from whshr.frontend.battle_view import BATTLE_CURSOR_GROUPS
        hud = self._hud_mock()
        view = self._view(hud)
        view.order_mode, view._cursor_mode = "attack", "attack"
        escape = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE)

        view.events(escape)

        view.cursors.set.assert_called_with(BATTLE_CURSOR_GROUPS["default"])

    def test_given_the_same_mode_again_then_the_cursor_is_not_reloaded(self):
        hud = self._hud_mock(hit_test=lambda pos: "attack", press=lambda name: None)
        view = self._view(hud)
        down = SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))
        view.events(down)
        view.cursors.set.reset_mock()
        view.hud.set_pressed(None)  # a second press of the same still-armed button

        view._set_cursor("attack")

        view.cursors.set.assert_not_called()


class EnemyInspectionSelectionTests(unittest.TestCase):
    """An enemy regiment can be selected for its HUD readout/banner/stats, but never given
    orders: whshr.battle_scene.BattleScene.handle() no longer restricts "select" to player
    regiments, and whshr.engine.Battle's order_move/order_attack/order_halt (and
    Hud._button_enabled()) already refuse commands for a non-player regiment regardless."""

    def _view(self, regiments, selected_id=None, order_mode=None):
        view = BattleView.__new__(BattleView)
        field = SimpleNamespace(width=1000, height=800, ground_height=lambda x, y: 0.0)
        view.scene = SimpleNamespace(field=field, battle=Battle(1000, 800, regiments), selected_id=selected_id)
        view.camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=180.0, pitch=45.0,
                                      distance=100.0, fov=45.0, projection=lambda *a, **k: None)
        view.gpu = SimpleNamespace(target=SimpleNamespace(size=(640, 480)))
        view.order_mode = order_mode
        view.cursors, view._cursor_mode = None, None
        view.event_log = []
        view.hud = SimpleNamespace(order_completed=Mock())
        view._figure_hits = lambda pixel, projection: []
        return view

    def _click_at(self, view, world_x, world_y):
        identifier = view.scene.battle.regiment_at(world_x, world_y, player_only=False)
        view._figure_hits = lambda pixel, projection: ([(view.scene.battle.regiments[identifier], (world_x, world_y))]
                                                        if identifier is not None else [])
        with patch("whshr.frontend.battle_view.picking.pick_ground",
                  return_value=(world_x / WORLD_PER_MESH, world_y / WORLD_PER_MESH)):
            return view._ground_click((0, 0))

    def test_given_no_player_selection_then_clicking_an_enemy_selects_it_for_inspection(self):
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10),
                    Regiment("enemy", "Enemy", 200, 200, 0, Side.ENEMY, models=10)]
        view = self._view(regiments, selected_id=None)

        events = self._click_at(view, 200, 200)

        self.assertEqual(events, (("select", "enemy"),))

    def test_given_a_player_selection_but_no_pending_order_then_clicking_an_enemy_still_selects_it(self):
        # notes/game_rules.md "Player orders and the command panel": there is no "just click an
        # enemy to charge" shortcut - Attack must be armed first, via the HUD button.
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10),
                    Regiment("enemy", "Enemy", 200, 200, 0, Side.ENEMY, models=10)]
        view = self._view(regiments, selected_id="player")

        events = self._click_at(view, 200, 200)

        self.assertEqual(events, (("select", "enemy"),))

    def test_given_an_armed_attack_order_then_clicking_an_enemy_charges_it(self):
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10),
                    Regiment("enemy", "Enemy", 200, 200, 0, Side.ENEMY, models=10)]
        view = self._view(regiments, selected_id="player", order_mode="attack")

        events = self._click_at(view, 200, 200)

        self.assertEqual(events, (("attack", "enemy"),))

    def test_given_an_armed_attack_order_and_empty_ground_then_it_cancels_and_logs_cannot(self):
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10)]
        view = self._view(regiments, selected_id="player", order_mode="attack")
        events = self._click_at(view, 900, 900)  # nothing there

        self.assertEqual(events, ())
        self.assertIsNone(view.order_mode)  # the order is cancelled, not left armed
        self.assertEqual(view.event_log[-1], "Cannot attack!")

    def test_given_an_armed_attack_order_and_a_target_then_nothing_is_logged(self):
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10),
                    Regiment("enemy", "Enemy", 200, 200, 0, Side.ENEMY, models=10)]
        view = self._view(regiments, selected_id="player", order_mode="attack")

        self._click_at(view, 200, 200)

        self.assertEqual(view.event_log, [])

    def test_given_a_right_click_direct_order_then_clicking_an_enemy_charges_it_without_arming_attack(self):
        # The right-click shortcut (direct=True) bypasses the Move/Attack HUD buttons entirely -
        # a pre-existing engine convenience, distinct from the documented button-driven flow.
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10),
                    Regiment("enemy", "Enemy", 200, 200, 0, Side.ENEMY, models=10)]
        view = self._view(regiments, selected_id="player")

        with patch("whshr.frontend.battle_view.picking.pick_ground",
                  return_value=(200.0 / WORLD_PER_MESH, 200.0 / WORLD_PER_MESH)):
            view._figure_hits = lambda pixel, projection: [(view.scene.battle.regiments["enemy"], (200.0, 200.0))]
            events = view._ground_click((0, 0), direct=True)

        self.assertEqual(events, (("attack", "enemy"),))

    def test_given_an_enemy_already_selected_for_inspection_then_it_cannot_be_ordered(self):
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10),
                    Regiment("enemy", "Enemy", 200, 200, 0, Side.ENEMY, models=10)]
        scene = BattleScene()
        scene.battle = Battle(1000, 800, regiments)
        scene.selected_id = None

        scene.handle(("select", "enemy"), context=None)
        self.assertEqual(scene.selected_id, "enemy")
        scene.handle(("move_to", 300.0, 300.0), context=None)

        self.assertIsNone(scene.battle.regiments["enemy"].target_x)

    def test_fight_harder_scene_order_applies_only_to_focused_player_in_melee(self):
        player = Regiment("player", "Player", 100, 100, 0, Side.PLAYER, in_melee=True)
        enemy = Regiment("enemy", "Enemy", 200, 200, 0, Side.ENEMY, in_melee=True)
        scene = BattleScene()
        scene.battle = Battle(1000, 800, [player, enemy])
        scene.selected_id = "player"

        scene.handle(("fight_harder",), context=None)
        self.assertTrue(player.fight_harder)
        self.assertFalse(enemy.fight_harder)
        scene.selected_id = "enemy"
        scene.handle(("fight_harder",), context=None)
        self.assertFalse(enemy.fight_harder)


class FigurePickTests(unittest.TestCase):
    """Battlefield clicks use the same visible figure frames and positions as rendering."""

    def _projection_factory(self):
        from whshr.battle3d import Projection

        def make_projection(w, h, fw, fh, th=0.0):
            return Projection(w, h, fw, fh, 180.0, 45.0, 1.0, 500.0 / WORLD_PER_MESH, 400.0 / WORLD_PER_MESH,
                              "perspective", 100.0, 45.0, th)

        return make_projection

    def _view(self, regiments, pixels=bytes([1] * 9)):
        from whshr.battlefield import SpriteFrame

        view = BattleView.__new__(BattleView)
        frame = SpriteFrame(3, 3, 1, 2, pixels)
        sheet = SimpleNamespace(frames=[frame], frame_index=lambda *args: 0)
        field = SimpleNamespace(width=1000, height=800, ground_height=lambda x, y: 0.0,
                                sprite_sheet=lambda resource: sheet, vertices=array("f"),
                                texture_layers=[], texture_size=(1, 1), effect_meshes={})
        battle = Battle(1000, 800, regiments)
        for regiment in regiments:
            regiment.model_positions()
        view.scene = SimpleNamespace(field=field, battle=battle, selected_id=None)
        view.camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=180.0, pitch=45.0,
                                      distance=100.0, fov=45.0, projection=self._projection_factory())
        view.gpu = SimpleNamespace(target=SimpleNamespace(size=(640, 480)))
        view.order_mode = None
        view.cursors = None
        view.hud = SimpleNamespace(order_completed=Mock())
        view.event_log = []
        return view

    def _pixel(self, view, x, y, column=1, row=1):
        from whshr.formation import SPRITE_PIXEL_WORLD_UNITS
        projection = view.camera.projection(640, 480, 1000, 800, 0.0)
        foot = projection.view(x / WORLD_PER_MESH, 0.0, y / WORLD_PER_MESH)
        px, py, _ = projection.project(foot)
        scale = SPRITE_PIXEL_WORLD_UNITS / WORLD_PER_MESH * projection.focal_length / foot[2]
        return (px + (column + 0.5 - 1) * scale - 0.5,
                py + (row + 0.5 - 2) * scale - 0.5)

    def test_a_figure_far_from_the_regiment_anchor_can_be_selected(self):
        regiment = Regiment("player", "Player", 500, 400, 0, Side.PLAYER, models=1)
        view = self._view([regiment])
        regiment.positions[0] = (700, 400)
        pixel = self._pixel(view, 700, 400)
        projection = view.camera.projection(640, 480, 1000, 800, 0.0)

        self.assertEqual([(r.identifier, point) for r, point in view._figure_hits(pixel, projection)],
                         [("player", (700, 400))])
        with patch("whshr.frontend.battle_view.picking.pick_ground", return_value=None):
            self.assertEqual(view._ground_click(pixel), (("select", "player"),))
        with patch("whshr.frontend.battle_view.picking.pick_ground",
                   return_value=(500 / WORLD_PER_MESH, 400 / WORLD_PER_MESH)):
            self.assertEqual(view._ground_click(pixel), (("select", "player"),))

    def test_empty_footprint_and_transparent_sprite_pixel_do_not_select(self):
        regiment = Regiment("player", "Player", 500, 400, 0, Side.PLAYER, models=1)
        view = self._view([regiment], pixels=bytes([1, 1, 1, 1, 0, 1, 1, 1, 1]))
        projection = view.camera.projection(640, 480, 1000, 800, 0.0)

        self.assertEqual(view._figure_hits(self._pixel(view, 500, 400), projection), [])
        with patch("whshr.frontend.battle_view.picking.pick_ground",
                   return_value=(500 / WORLD_PER_MESH, 400 / WORLD_PER_MESH)):
            self.assertEqual(view._ground_click(self._pixel(view, 500, 400)), ())

    def test_inactive_and_hidden_enemies_are_not_picked(self):
        destroyed = Regiment("destroyed", "Destroyed", 500, 400, 0, Side.PLAYER, models=0)
        hidden = Regiment("hidden", "Hidden", 500, 400, 0, Side.ENEMY, models=1, hidden=True)
        view = self._view([destroyed, hidden])
        projection = view.camera.projection(640, 480, 1000, 800, 0.0)

        self.assertEqual(view._figure_hits(self._pixel(view, *hidden.positions[0]), projection), [])

    def test_terrain_or_scenery_hides_a_figure_but_a_texture_hole_does_not(self):
        from whshr.frontend.battle_view import SPRITE_DEPTH_BIAS
        from whshr.picking import screen_ray

        regiment = Regiment("player", "Player", 500, 400, 0, Side.PLAYER, models=1)
        view = self._view([regiment])
        x, y = regiment.positions[0]
        pixel = self._pixel(view, x, y)
        projection = view.camera.projection(640, 480, 1000, 800, 0.0)
        self.assertEqual(len(view._figure_hits(pixel, projection)), 1)
        origin, direction = screen_ray(projection, *pixel)
        foot_depth = projection.view(x / WORLD_PER_MESH, 0.0, y / WORLD_PER_MESH)[2]
        forward = sum(direction[i] * projection.view_direction[i] for i in range(3))
        distance = (foot_depth - SPRITE_DEPTH_BIAS - 3.0) / forward
        centre = tuple(origin[i] + distance * direction[i] for i in range(3))
        for sx, sy in ((-10, -10), (10, -10), (0, 10)):
            view.scene.field.vertices.extend((*(centre[i] + sx * projection.right[i]
                                                  + sy * projection.up[i] for i in range(3)),
                                              0.25, 0.25, 0.0, 1.0))
        view.scene.field.texture_layers = [bytes((100, 100, 100, 255))]

        self.assertEqual(view._figure_hits(pixel, projection), [])
        occluder = array("f", view.scene.field.vertices)
        shift = (SPRITE_DEPTH_BIAS + 2.5) / forward
        for start in (0, 7, 14):
            for coordinate in range(3):
                view.scene.field.vertices[start + coordinate] += shift * direction[coordinate]
        self.assertEqual(len(view._figure_hits(pixel, projection)), 1)  # the renderer's depth bias keeps it visible
        view.scene.field.vertices = occluder
        view.scene.field.texture_layers = [bytes((0, 0, 0, 0))]
        self.assertEqual(len(view._figure_hits(pixel, projection)), 1)
        view.scene.field.texture_layers = [bytes((100, 100, 100, 255))]
        effect_vertices = view.scene.field.vertices
        view.scene.field.vertices = array("f")
        view.scene.field.effect_meshes = {"active": object()}
        view._effect_vertices = Mock(return_value=effect_vertices)
        self.assertEqual(view._figure_hits(pixel, projection), [])
        view._effect_vertices.assert_called_once_with()

    def test_overlap_cycles_selection_and_uses_topmost_figure_for_attack(self):
        regiments = [Regiment(name, name, 500, 400, 0, Side.PLAYER, models=1)
                     for name in ("first", "second", "third")]
        view = self._view(regiments)
        pixel = self._pixel(view, *regiments[0].positions[0])
        projection = view.camera.projection(640, 480, 1000, 800, 0.0)
        self.assertEqual([r.identifier for r, _ in view._figure_hits(pixel, projection)],
                         ["third", "second", "first"])
        with patch("whshr.frontend.battle_view.picking.pick_ground", return_value=None):
            selected = []
            for _ in range(3):
                identifier = view._ground_click(pixel)[0][1]
                selected.append(identifier)
                view.scene.selected_id = identifier
            self.assertEqual(selected, ["first", "third", "second"])
            view.order_mode = "attack"
            self.assertEqual(view._ground_click(pixel), (("attack", "first"),))

    def test_selection_elsewhere_in_an_overlap_does_not_replace_the_top_figure(self):
        regiments = [Regiment(name, name, 500, 400, 0, Side.PLAYER, models=1)
                     for name in ("first", "second", "third")]
        view = self._view(regiments)
        view.scene.selected_id = "second"  # selected through the minimap or keyboard
        pixel = self._pixel(view, *regiments[0].positions[0])
        with patch("whshr.frontend.battle_view.picking.pick_ground", return_value=None):
            self.assertEqual(view._ground_click(pixel), (("select", "first"),))
            view.scene.selected_id = "first"
            self.assertEqual(view._ground_click(pixel), (("select", "third"),))

    def test_move_click_on_a_figure_without_ground_keeps_the_order_armed(self):
        regiment = Regiment("target", "Target", 500, 400, 0, Side.PLAYER, models=1)
        view = self._view([regiment])
        view.order_mode = "move"
        pixel = self._pixel(view, *regiment.positions[0])
        with patch("whshr.frontend.battle_view.picking.pick_ground", return_value=None):
            self.assertEqual(view._ground_click(pixel), ())
        self.assertEqual(view.order_mode, "move")
        view.hud.order_completed.assert_not_called()

    def test_spell_point_uses_the_hit_figures_world_position(self):
        regiment = Regiment("target", "Target", 500, 400, 0, Side.ENEMY, models=1)
        view = self._view([regiment])
        regiment.positions[0] = (700, 400)
        view.order_mode = "item:spell"
        pixel = self._pixel(view, 700, 400)
        with patch("whshr.frontend.battle_view.picking.pick_ground", return_value=None):
            self.assertEqual(view._ground_click(pixel), (("item_target", "spell", 700, 400),))


def _seeded(battle):
    """A battle as a scene hands it to the view: every regiment's figures seeded (BattleScene.enter)."""
    for regiment in battle.regiments.values():
        regiment.model_positions()
    return battle


class BattleBannerVisibilityTests(unittest.TestCase):
    def test_given_hidden_player_or_ally_then_banner_is_drawn_without_revealing_it(self):
        for side in (Side.PLAYER, Side.NEUTRAL, Side.ENEMY):
            with self.subTest(side=side):
                view = self._view_with_banner()
                regiment = view.scene.battle.regiments["player"]
                regiment.side, regiment.hidden = side, True
                self.assertEqual(bool(view._instances()), side != Side.ENEMY)
                self.assertTrue(regiment.hidden)

    def _view_with_banner(self, active=True):
        from whshr.battlefield import SpriteFrame, SpriteSheet
        regiment = Regiment("player", "Player", 100, 200, 0, Side.PLAYER, models=1 if active else 0,
                            banner="banner")
        marker = SpriteFrame(32, 32, 0, 32, bytes(32 * 32))
        banner = SpriteSheet("BANNER", [marker, marker, marker], [],
                             rects=[(0, 0, 32, 32)] * 3)
        field = SimpleNamespace(
            ui_sheets={"banner": banner}, sprite_sheet=lambda resource: None,
            ground_height=lambda x, y: 2.0,
        )
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(field=field, battle=_seeded(Battle(1000, 800, [regiment])), selected_id="player")
        view.camera = SimpleNamespace(yaw=180)
        view.capacity = 1
        return view

    def test_given_an_active_bannered_regiment_when_the_battle_view_draws_then_one_banner_marker_is_visible(self):
        from whshr.frontend.battle_view import BANNER_MARKER_RAISE, INSTANCE
        instance = INSTANCE.unpack(self._view_with_banner()._instances())

        self.assertEqual(instance[:3], (12.5, 2.0 + BANNER_MARKER_RAISE, 25.0))
        self.assertEqual(instance[3:7], (0.0, 0.0, 32.0, 32.0))
        self.assertEqual(instance[7:], (16.0, 32.0, 1.0))

    def test_given_models_lagging_behind_a_charging_anchor_then_the_banner_follows_the_models(self):
        # The anchor (regiment.x/y) can visibly outrun the models during a charge (they only ever
        # catch up to it at the unit's base speed - notes/game_rules.md "Formations": models walk
        # never faster than the unit's s_rlmv); the banner must hover over the rendered
        # troops' actual current positions, not the anchor, or it visibly floats ahead of the block.
        from whshr.battlefield import SpriteFrame, SpriteSheet
        from whshr.frontend.battle_view import BANNER_MARKER_RAISE, INSTANCE
        regiment = Regiment("player", "Player", 100, 200, 0, Side.PLAYER, models=2, banner="banner")
        regiment.positions = [(80.0, 180.0), (90.0, 190.0)]  # lagging behind the (100, 200) anchor
        marker = SpriteFrame(32, 32, 0, 32, bytes(32 * 32))
        banner = SpriteSheet("BANNER", [marker, marker, marker], [], rects=[(0, 0, 32, 32)] * 3)
        field = SimpleNamespace(ui_sheets={"banner": banner}, sprite_sheet=lambda resource: None,
                               ground_height=lambda x, y: 2.0)
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(field=field, battle=_seeded(Battle(1000, 800, [regiment])), selected_id="player")
        view.camera = SimpleNamespace(yaw=180)
        view.capacity = 1

        instance = INSTANCE.unpack(view._instances())

        center_x, center_y = 85.0, 185.0  # mean of the two lagging model positions, not the anchor
        self.assertEqual(instance[:3], (center_x / WORLD_PER_MESH, 2.0 + BANNER_MARKER_RAISE,
                                        center_y / WORLD_PER_MESH))

    def test_given_a_destroyed_bannered_regiment_when_the_battle_view_draws_then_no_banner_marker_is_visible(self):
        self.assertEqual(self._view_with_banner(active=False)._instances(), b"")

    def test_given_overlapping_regiment_banners_when_one_is_selected_then_its_marker_is_drawn_last(self):
        from whshr.battlefield import SpriteFrame, SpriteSheet
        from whshr.frontend.battle_view import INSTANCE
        player = Regiment("player", "Player", 100, 200, 0, Side.PLAYER, banner="player-banner")
        enemy = Regiment("enemy", "Enemy", 100, 200, 0, Side.ENEMY, banner="enemy-banner")
        marker = SpriteFrame(32, 32, 0, 32, bytes(32 * 32))
        player_sheet = SpriteSheet("PLAYER", [marker, marker, marker], [], rects=[(10, 0, 32, 32)] * 3)
        enemy_sheet = SpriteSheet("ENEMY", [marker, marker, marker], [], rects=[(50, 0, 32, 32)] * 3)
        field = SimpleNamespace(
            ui_sheets={"player-banner": player_sheet, "enemy-banner": enemy_sheet},
            sprite_sheet=lambda resource: None, ground_height=lambda x, y: 2.0,
        )
        view = BattleView.__new__(BattleView)
        view.scene = SimpleNamespace(field=field, battle=_seeded(Battle(1000, 800, [player, enemy])), selected_id="player")
        view.camera, view.capacity = SimpleNamespace(yaw=180), 2

        instances = view._instances()

        first = INSTANCE.unpack_from(instances, 0)
        last = INSTANCE.unpack_from(instances, INSTANCE.size)
        self.assertEqual(first[3:7], (50.0, 0.0, 32.0, 32.0))
        self.assertEqual(last[3:7], (10.0, 0.0, 32.0, 32.0))
        view.scene.selected_id = None
        after_deselect = view._instances()
        self.assertEqual(INSTANCE.unpack_from(after_deselect, INSTANCE.size)[3:7], (10.0, 0.0, 32.0, 32.0))


class CameraTargetTests(unittest.TestCase):
    def test_given_a_camera_then_its_target_x_mark_is_drawn_at_the_target_world_position(self):
        hud = _hud()
        hud._draw_size = (640, 480)
        quad = SimpleNamespace(size=(8, 8))
        hud._icon = lambda frame_index: quad
        calls = []
        hud._draw_map = lambda q, x, y, w=None, h=None, **kw: calls.append((x, y))
        camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=0.0, distance=10.0)

        hud._draw_camera_target(camera)

        expected_px, expected_py = hud._world_to_map_pixel(camera.target_x, camera.target_y)
        self.assertEqual(calls, [(expected_px - 4, expected_py - 4)])

    def test_given_a_battle_draw_then_the_target_mark_is_drawn_before_regiment_markers(self):
        # It must sit at the lowest z-order above the plan map: every other minimap element
        # (waypoints, regiments, tabs) should paint over it.
        regiments = [Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=10, ranks=2, hud_class="inf")]
        hud = _hud(regiments=regiments)
        hud._draw_size = (640, 480)
        hud.minimap_layers = {}
        hud.planmap = None
        hud._icon = lambda frame_index: None
        camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=0.0, distance=10.0)
        order = []
        hud._draw_camera_target = lambda cam: order.append("target")
        hud._draw_regiment_marker = lambda regiment: order.append("regiment")

        hud._draw_minimap(hud._regiment("player"), camera)

        self.assertEqual(order[0], "target")
        self.assertTrue(all(step == "regiment" for step in order[1:]))


class CameraMarkerTests(unittest.TestCase):
    def test_given_a_camera_eye_far_outside_the_field_then_the_marker_is_clamped_to_the_map_area(self):
        # A large zoom (orbit distance) can pull the eye far past the battlefield; the marker
        # should stay pinned at the map's edge rather than spill outside the minimap chrome.
        hud = _hud()
        hud._draw_size = (640, 480)
        quad = SimpleNamespace(size=(8, 8))
        hud._icon = lambda frame_index: quad
        calls = []
        hud._draw_map = lambda q, x, y, w=None, h=None, **kw: calls.append((x, y))
        camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=180.0, distance=600.0)

        hud._draw_camera_marker(camera)

        map_left, map_top, width, height = hud._map_scale()
        x, y = calls[0]
        self.assertGreaterEqual(x, map_left)
        self.assertLessEqual(x + quad.size[0], map_left + width)
        self.assertGreaterEqual(y, map_top)
        self.assertLessEqual(y + quad.size[1], map_top + height)

    def test_given_a_camera_yaw_then_the_marker_frame_is_a_half_turn_from_the_raw_yaw_index(self):
        # The marker sheet's own zero-rotation point sits a half-turn off from yaw's (observed
        # against the running game); the drawn frame must be offset by 4 (of 8) from a naive
        # yaw-only index.
        hud = _hud()
        hud._draw_size = (640, 480)
        quad = SimpleNamespace(size=(8, 8))
        used = {}

        def icon(frame_index):
            used["frame"] = frame_index
            return quad

        hud._icon = icon
        hud._draw_map = lambda *a, **k: None
        camera = SimpleNamespace(target_x=500.0, target_y=400.0, yaw=0.0, distance=10.0)

        hud._draw_camera_marker(camera)

        from whshr.frontend.hud import CAMERA_MARKER_FRAMES
        self.assertEqual(used["frame"], CAMERA_MARKER_FRAMES[4])


if __name__ == "__main__":
    unittest.main()


class ItemMarkerTests(unittest.TestCase):
    """notes/battle_end_objectives.md 12.2: a sparkle over each item still to be picked up, the snowman variant in
    battles that load snow scenery."""

    def _view(self, marks, furniture=(), update_count=0):
        view = BattleView.__new__(BattleView)
        sheet = SimpleNamespace(name="SPARKLE", frames=[SimpleNamespace(anchor_x=16.0, anchor_y=32.0)] * 13,
                                rects=[(index * 32, 0, 32, 32) for index in range(13)])
        view.scene = SimpleNamespace(
            battle=SimpleNamespace(objectives=SimpleNamespace(item_marks=marks), update_count=update_count),
            field=SimpleNamespace(ui_sheets={"sparkle": sheet}, script={"load": {"loadfurn": list(furniture)}},
                                  ground_height=lambda x, y: 0.0))
        return view

    def frames(self, view):
        data = view._item_markers()
        return [int(values[3] // 32) for values in struct.iter_unpack("10f", data)]

    def test_one_sparkle_per_pending_item_cycling_frames_0_to_4(self):
        view = self._view({"K": (240.0, 480.0), "X": (24.0, 24.0)}, update_count=12)
        self.assertEqual(self.frames(view), [1, 1])  # tick 12 -> step 6 -> frame 6 % 5
        view.scene.battle.update_count = 8
        self.assertEqual(self.frames(view), [4, 4])

    def test_snow_battles_use_the_second_variant(self):
        view = self._view({"K": (240.0, 480.0)}, furniture=("SnwRock2",), update_count=4)
        self.assertEqual(self.frames(view), [7])

    def test_no_marker_once_picked_up(self):
        self.assertEqual(self._view({})._item_markers(), b"")


class BattleViewEventConsumptionTests(unittest.TestCase):
    def test_a_reaction_is_shown_once_across_rendered_frames_and_again_on_a_new_tick(self):
        view = BattleView.__new__(BattleView)
        reaction = BattleEvent("Grudgebringers: Engage!", "react", sender="Grudgebringers", message="Engage!")
        battle = SimpleNamespace(events=[reaction], text_resources={})
        view.scene = SimpleNamespace(battle=battle)
        view.battle_log = deque(maxlen=100)
        view.event_log = deque(maxlen=100)
        view.log_scroll = 0
        view._event_batch = None
        view._event_index = 0
        view.battle_sounds = Mock()

        for _ in range(4):
            view._consume_events()
        self.assertEqual(list(view.battle_log), [("Grudgebringers:", "Engage!")])
        self.assertEqual(list(view.event_log), [str(reaction)])
        view.battle_sounds.handle.assert_called_once_with([reaction])

        battle.events.append(BattleEvent("message 1005", "message", text_id=1005))
        battle.text_resources[1005] = "Mission complete!"
        view._consume_events()
        self.assertEqual(list(view.battle_log)[-1], ("", "Mission complete!"))
        self.assertEqual(len(view.battle_log), 2)

        battle.events = [BattleEvent("Grudgebringers: Engage!", "react",
                                     sender="Grudgebringers", message="Engage!")]
        view._consume_events()
        self.assertEqual(len(view.battle_log), 3)
