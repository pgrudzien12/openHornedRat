"""The Gyrocopter's steam gun and bomb (notes/gyrocopter_steam_gun.md): panel class, orders, the shot and its look."""
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pygame

from whshr import spell_effects
from whshr.battle_scene import BattleScene
from whshr.engine import Battle, Regiment, hud_class_of
from whshr.frontend import spell_visuals
from whshr.frontend.battle_view import BattleView
from whshr.rules import Side

STEAM = spell_effects.STEAM_GUN


def gyrocopter(name="G", x=1000, y=1000, facing=0, *, cls="arch", bs=10, leader=False):
    craft = Regiment(name, name, x, y, facing, Side.PLAYER, models=1, ranks=1, hud_class=cls, unit_class=3,
                     missile_code=17, shooting_code=17, missile_range=384, bs=bs, initiative=2, speed_per_tick=0,
                     has_leader=leader)
    craft.sprite = "Gyrocopter"
    return craft


def target(name, x, y, side=Side.ENEMY, models=20):
    return Regiment(name, name, x, y, 256, side, models=models, ranks=4, hud_class="inf", toughness=10,
                    speed_per_tick=0)


def fly(craft, elevation=32):
    craft.flight_state().elevation = elevation


class ScriptedRandom(random.Random):
    """Fixed dice: randint and randrange return the listed values in order, then seeded draws."""
    def __init__(self, values):
        super().__init__(1995)
        self.values = list(values)

    def randint(self, a, b):
        return self.values.pop(0) if self.values else super().randint(a, b)

    def randrange(self, start, stop=None, step=1):
        if not self.values:
            return super().randrange(start, stop, step)
        value = self.values.pop(0)
        assert value < (start if stop is None else stop)
        return value


def steam_effects(battle):
    return [effect for effect in spell_effects.table(battle).effects() if effect.code == STEAM]


def run_flight(battle, effect):
    """Update the effects until the cloud finishes; returns (x, y, height) per flight tick."""
    path = []
    while effect.tail < 0 and not effect.ended:
        spell_effects.tick(battle)
        path.append((effect.x, effect.y, effect.height))
    return path


def strikes(battle, unit_id, terminal):
    return [event for event in battle.events
            if event.kind == "spell_strike" and event.data["regiment"] == unit_id
            and event.data["terminal"] == terminal]


class PanelClass(unittest.TestCase):
    def test_the_class_part_of_s_race_decides_the_panel_not_the_s_side_type(self):
        self.assertEqual(hud_class_of(4, 3 * 8 + 2), "arch")  # campaign Gyrocopter: Dwarven type, Archers class
        self.assertEqual(hud_class_of(4, 1 * 8 + 2), "inf")  # the BF033.MRC variant
        self.assertEqual(hud_class_of(3, 2 * 8 + 0), "inf")  # Human Archers type, Cavalry class
        self.assertEqual(hud_class_of(8, 6 * 8 + 4), "mon")  # Orc Infantry type, Monster class (a troll)

    def test_classes_without_a_panel_set_keep_the_s_side_mapping(self):
        self.assertEqual(hud_class_of(0x40, 7 * 8 + 7), "mon")  # rolling stock
        self.assertEqual(hud_class_of(14, 0 * 8 + 6), "inf")  # notype peasants


class SteamGunOrder(unittest.TestCase):
    def setUp(self):
        self.craft = gyrocopter()
        self.enemy = target("E", 1000, 1300)
        self.battle = Battle(3000, 3000, [self.craft, self.enemy], seed=1995)

    def test_fire_launches_one_steam_shot_at_the_clicked_point_at_once(self):
        self.assertTrue(self.battle.fire_steam_gun("G", (1000, 1300)))

        [effect] = steam_effects(self.battle)
        self.assertEqual(effect.aim, (1000, 1300))
        self.assertTrue(effect.innate)
        self.assertEqual(self.craft.reload_ticks, 0)  # no reload stamp
        self.assertIsNone(self.craft.shooting_mode)  # no stored target, no event

    def test_there_is_no_range_arc_or_reload_test(self):
        self.battle.fire_steam_gun("G", (1000, 2000))  # 1000 away
        self.battle.fire_steam_gun("G", (1000, 500))  # behind the craft
        self.battle.fire_steam_gun("G", (1000, 500))  # again at once

        self.assertEqual(len(steam_effects(self.battle)), 3)
        self.assertEqual(self.craft.direction, 0)  # no turn

    def test_a_moving_craft_is_not_halted(self):
        self.craft.target_x, self.craft.target_y = 2000, 2000

        self.battle.fire_steam_gun("G", (1000, 1300))

        self.assertEqual((self.craft.target_x, self.craft.target_y), (2000, 2000))

    def test_a_held_craft_fires_and_a_hidden_one_is_revealed(self):
        self.craft.held = True
        self.craft.hidden = True

        self.assertTrue(self.battle.fire_steam_gun("G", (1000, 1300)))

        self.assertFalse(self.craft.hidden)

    def test_the_order_gate_drops_the_order_silently(self):
        for state in ("in_melee", "routing", "pursuing", "braced"):
            with self.subTest(state=state):
                setattr(self.craft, state, True)
                self.assertFalse(self.battle.fire_steam_gun("G", (1000, 1300)))
                setattr(self.craft, state, False)
        self.assertEqual(steam_effects(self.battle), [])

    def test_a_hovering_craft_keeps_hovering(self):
        fly(self.craft)

        self.battle.fire_steam_gun("G", (1000, 1300))

        self.assertEqual(self.craft.elevation, 32)

    def test_the_scene_fire_order_of_a_gyrocopter_fires_the_steam_gun(self):
        scene = BattleScene.__new__(BattleScene)
        scene.battle, scene.selected_id, scene.logger = self.battle, "G", None

        scene.handle(("fire", "E", (1000, 1300)), None)

        self.assertEqual([effect.aim for effect in steam_effects(self.battle)], [(1000, 1300)])
        self.assertIsNone(self.craft.shooting_target)


class SteamShot(unittest.TestCase):
    """gyrocopter_steam_gun.md 8.4-8.6 on flat ground with no scatter (BS 10)."""

    def shoot(self, craft, aim, *others):
        battle = Battle(3000, 3000, [craft, *others], seed=1995)
        battle.fire_steam_gun(craft.identifier, aim)
        [effect] = steam_effects(battle)
        return battle, effect

    def test_the_cloud_starts_24_ahead_and_flies_18_ticks_to_the_aim_point(self):
        battle, effect = self.shoot(gyrocopter(), (1000, 1144))

        path = run_flight(battle, effect)

        self.assertEqual(effect.start, (1000, 1024))
        self.assertEqual(effect.dest, (1000, 1144))
        self.assertEqual([y for _x, y, _h in path],
                         [1024, 1031, 1038, 1044, 1051, 1058, 1064, 1071, 1078, 1084, 1091, 1098, 1104, 1111,
                          1118, 1124, 1131, 1138, 1144])
        self.assertEqual({h for _x, _y, h in path}, {16})  # grounded: 8 above the ground plus the aim height 8

    def test_the_start_offset_follows_the_unit_facing(self):
        expected = {0: (0, 24), 64: (16, 16), 128: (24, 0), 192: (16, -17), 256: (0, -24), 320: (-17, -17),
                    384: (-24, 0), 448: (-17, 16)}
        for facing, (dx, dy) in expected.items():
            with self.subTest(facing=facing):
                _battle, effect = self.shoot(gyrocopter(facing=facing), (1500, 1500))
                self.assertEqual(effect.start, (1000 + dx, 1000 + dy))

    def test_a_unit_on_the_path_is_hit_once_per_tick_the_cloud_is_inside_it(self):
        crossed = target("U", 1000, 1100)
        battle, effect = self.shoot(gyrocopter(), (1000, 1144), crossed)

        path = run_flight(battle, effect)

        inside = [p for p in path if spell_effects._centre_d(crossed, p[0], p[1]) < crossed.bounding_radius()]
        self.assertGreater(len(inside), 1)
        self.assertEqual(len(strikes(battle, "U", terminal=False)), len(inside))

    def test_friends_are_hit_too(self):
        friend = target("F", 1000, 1100, side=Side.PLAYER)
        battle, effect = self.shoot(gyrocopter(), (1000, 1144), friend)

        run_flight(battle, effect)

        self.assertTrue(strikes(battle, "F", terminal=False))

    def test_the_terminal_impact_always_strikes_at_the_destination_with_the_hit_message(self):
        crossed = target("U", 1000, 1100)
        at_aim = target("A", 1000, 1300)
        battle, effect = self.shoot(gyrocopter(), (1000, 1300), crossed, at_aim)

        run_flight(battle, effect)

        self.assertTrue(strikes(battle, "U", terminal=False))  # struck on the way, yet the cloud flies on
        self.assertEqual(len(strikes(battle, "A", terminal=True)), 1)
        self.assertIn(("A", spell_effects.GMTXT_DIRECT_HIT),
                      [(e.data.get("regiment"), e.data.get("text_id")) for e in battle.events])

    def test_a_shot_into_its_own_footprint_hits_the_craft_only_at_the_terminal_impact(self):
        craft = gyrocopter()
        battle, effect = self.shoot(craft, (1000, 1004))

        run_flight(battle, effect)

        self.assertEqual(effect.start, (1000, 1024))
        self.assertEqual(strikes(battle, "G", terminal=False), [])
        self.assertEqual(len(strikes(battle, "G", terminal=True)), 1)

    def test_an_airborne_craft_never_hits_ground_units_in_flight(self):
        craft = gyrocopter()
        fly(craft)
        crossed = target("U", 1000, 1100)
        at_aim = target("A", 1000, 1300)
        battle, effect = self.shoot(craft, (1000, 1300), crossed, at_aim)

        path = run_flight(battle, effect)

        self.assertEqual((path[0][2], path[-1][2]), (64, 40))  # from E + E to E + 8
        self.assertEqual(strikes(battle, "U", terminal=False), [])
        self.assertEqual(strikes(battle, "A", terminal=False), [])
        self.assertEqual(len(strikes(battle, "A", terminal=True)), 1)

    def test_the_aim_height_is_8_even_at_an_airborne_flier(self):
        other = gyrocopter("H", 1000, 1300)
        fly(other)
        _battle, effect = self.shoot(gyrocopter(), (1000, 1300), other)

        self.assertEqual(effect.aim_height, 8)

    def test_the_hiss_starts_at_the_unit_and_stops_when_the_cloud_finishes(self):
        battle, effect = self.shoot(gyrocopter(), (1000, 1300))
        sounds = [e for e in battle.events if e.kind == "sound"]
        self.assertEqual([(e.data["cue"], e.data["effect"], e.data["position"]) for e in sounds],
                         [("loop_start", spell_effects.SFX_STEAM, (1000, 1000))])

        stopped_at = None
        for tick in range(1, 25):
            spell_effects.tick(battle)
            if any(e.kind == "sound" and e.data["cue"] == "loop_stop" for e in battle.events):
                stopped_at = tick
                break

        self.assertEqual(stopped_at, 19)  # the 19th position is the destination (r = 0)
        self.assertFalse(effect.ended)  # the trail outlives the sound


class Bomb(unittest.TestCase):
    def setUp(self):
        self.craft = gyrocopter(bs=3)
        self.battle = Battle(3000, 3000, [self.craft, target("E", 1000, 1500)], seed=1995)

    def texts(self):
        return [e.data["text_id"] for e in self.battle.events if e.kind == "ranged_message"]

    def test_only_an_archers_or_artillery_class_gyrocopter_can_bomb(self):
        infantry = gyrocopter("I", 500, 500, cls="inf")
        battle = Battle(3000, 3000, [self.craft, infantry])
        self.assertTrue(battle.can_bomb("G"))
        self.assertFalse(battle.can_bomb("I"))

    def test_an_airborne_reloaded_craft_drops_a_scattered_bomb_from_its_elevation(self):
        fly(self.craft)
        self.battle.rng = ScriptedRandom([4, 5, 0, 2, 1])  # d 4; x 5 even; y 2 odd

        self.assertIsNone(self.battle.drop_bomb("G"))

        [bomb] = self.battle.projectiles
        self.assertEqual((bomb.x1, bomb.y1), (1020, 992))
        self.assertEqual(bomb.z0, 32)
        self.assertGreater(self.craft.reload_ticks, 0)

    def test_the_largest_scatter_at_bs_3_is_35(self):
        fly(self.craft)
        self.battle.rng = ScriptedRandom([5, 7, 1, 7, 0])

        self.battle.drop_bomb("G")

        self.assertEqual((self.battle.projectiles[0].x1, self.battle.projectiles[0].y1), (965, 1035))

    def test_a_bomb_during_take_off_drops_from_the_current_height(self):
        fly(self.craft, 16)
        self.battle.rng = ScriptedRandom([1, 0, 0, 0, 0])

        self.battle.drop_bomb("G")

        self.assertEqual(self.battle.projectiles[0].z0, 16)

    def test_a_craft_still_reloading_is_refused_without_a_new_stamp(self):
        fly(self.craft)
        self.craft.reload_ticks = 1

        self.assertEqual(self.battle.drop_bomb("G"), 2003)

        self.assertEqual(self.craft.reload_ticks, 1)
        self.assertEqual(self.battle.projectiles, [])

    def test_a_held_craft_is_refused_as_not_ready(self):
        fly(self.craft)
        self.craft.held = True

        self.assertEqual(self.battle.drop_bomb("G"), 2003)

    def test_a_grounded_craft_is_refused_and_the_reload_is_used_up(self):
        self.assertEqual(self.battle.drop_bomb("G"), 2020)
        self.assertGreater(self.craft.reload_ticks, 0)

        fly(self.craft)
        self.assertEqual(self.battle.drop_bomb("G"), 2003)

    def test_a_lost_misfire_drops_nothing_and_keeps_the_craft_hidden(self):
        fly(self.craft)
        self.craft.hidden = True
        self.battle.rng = ScriptedRandom([6, 3])

        self.battle.drop_bomb("G")

        self.assertEqual(self.battle.projectiles, [])
        self.assertEqual(self.texts(), [2019])
        self.assertTrue(self.craft.hidden)
        self.assertGreater(self.craft.reload_ticks, 0)

    def test_a_destroyed_misfire_kills_a_craft_with_a_leader_without_kill_credit(self):
        craft = gyrocopter("L", leader=True)
        fly(craft)
        battle = Battle(3000, 3000, [craft, target("E", 1000, 1500)], seed=1995)
        battle.rng = ScriptedRandom([6, 1, 0])

        battle.drop_bomb("L")

        self.assertEqual(craft.models, 0)
        self.assertIn(2018, [e.data["text_id"] for e in battle.events if e.kind == "ranged_message"])
        self.assertEqual(battle.projectiles, [])

    def test_a_destroyed_misfire_of_a_leaderless_craft_is_a_lost_shot(self):
        fly(self.craft)
        self.battle.rng = ScriptedRandom([6, 1])

        self.battle.drop_bomb("G")

        self.assertEqual(self.craft.models, 1)
        self.assertEqual(self.texts(), [2019])

    def test_the_scene_bomb_event_shows_the_refusal(self):
        scene = BattleScene.__new__(BattleScene)
        scene.battle, scene.selected_id, scene.logger = self.battle, "G", None

        scene.handle(("bomb",), None)

        self.assertEqual([e.data["text_id"] for e in self.battle.pending_feedback], [2020])


class SteamLook(unittest.TestCase):
    def test_the_steam_cloud_uses_the_grey_puffs_and_leaves_a_trail(self):
        craft = gyrocopter()
        battle = Battle(3000, 3000, [craft], seed=1995)
        battle.fire_steam_gun("G", (1000, 1300))
        visuals, memory = spell_visuals.ProjectileVisuals(), {}
        frames = set()
        for _ in range(45):
            spell_effects.tick(battle)
            shots, _storms = spell_visuals.projectile_shots(spell_effects.table(battle).effects(), memory)
            visuals.advance(shots)
            frames |= {sprite.frame for sprite in visuals.sprites()}

        self.assertTrue(frames)
        self.assertLessEqual(frames, {591, 592, 593, 594})
        self.assertEqual(visuals.sprites(), [])  # the trail has cleared



class FireButton(unittest.TestCase):
    """gyrocopter_steam_gun.md 2: Ctrl on the Fire button drops the bomb; the map click never reads Ctrl."""

    def setUp(self):
        self.craft = gyrocopter()
        self.enemy = target("E", 1000, 1300)
        self.battle = Battle(3000, 3000, [self.craft, self.enemy], seed=1995)
        self.battle.phase = "battle"
        self.minimap_point = None
        self.hud = SimpleNamespace(
            click_minimap_tab=lambda pos: False, minimap_position=lambda pos: self.minimap_point,
            minimap_regiment_at=lambda pos: None, minimap_target_at=lambda pos: "E",
            hit_test=lambda pos: "fire", occupies=lambda pos: True, set_pressed=Mock(),
            press=lambda name: None, order_completed=Mock())
        self.view = BattleView.__new__(BattleView)
        self.view.hud = self.hud
        self.view.scene = SimpleNamespace(selected_id="G", battle=self.battle)
        self.view.camera = SimpleNamespace()
        self.view.order_mode = None
        self.view.cursors, self.view._cursor_mode = None, None
        self.view.event_log = []

    def press_fire(self, ctrl):
        return self.view.events(SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10),
                                                mod=pygame.KMOD_CTRL if ctrl else 0))

    def test_ctrl_on_the_fire_button_drops_the_bomb_without_a_pick_mode(self):
        self.assertEqual(self.press_fire(ctrl=True), (("bomb",),))
        self.assertIsNone(self.view.order_mode)

    def test_without_ctrl_the_fire_button_waits_for_a_click(self):
        self.assertEqual(self.press_fire(ctrl=False), ())
        self.assertEqual(self.view.order_mode, "fire")

    def test_ctrl_fire_while_already_waiting_does_nothing(self):
        self.press_fire(ctrl=False)

        self.assertEqual(self.press_fire(ctrl=True), ())
        self.assertEqual(self.view.order_mode, "fire")

    def test_a_craft_that_cannot_bomb_ignores_ctrl(self):
        self.craft.hud_class = "inf"

        self.assertEqual(self.press_fire(ctrl=True), ())
        self.assertEqual(self.view.order_mode, "fire")

    def test_a_minimap_steam_shot_snaps_to_the_picked_unit_centre(self):
        self.view.order_mode = "fire"
        self.minimap_point = (1010.0, 1290.0)

        [(kind, picked, point)] = self.view._minimap_click((10, 10))

        self.assertEqual((kind, picked), ("fire", "E"))
        self.assertEqual(point, spell_effects.footprint_centre(self.enemy))


if __name__ == "__main__":
    unittest.main()
