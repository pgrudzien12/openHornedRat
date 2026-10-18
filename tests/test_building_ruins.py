"""Destroyed buildings turn into their ruin pieces (notes/building_ruins.md, GitHub #374)."""

import random
import unittest
from array import array
from types import SimpleNamespace
from unittest import mock

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import battlefield, buildings
from whshr.rules import Side


class Draws(random.Random):
    """Returns the listed values for successive `randrange` calls, then 0."""

    def __init__(self, *values):
        super().__init__(0)
        self.values = list(values)

    def randrange(self, start, stop=None, step=1):
        del start, stop, step
        return self.values.pop(0) if self.values else 0


def battle(*scenery):
    shooter = Regiment("S", "S", 1500, 1500, 0, Side.PLAYER, models=5, ranks=1, hud_class="art",
                       missile_code=11, shooting_code=11, missile_range=2000)
    foe = Regiment("E", "E", 1900, 1900, 0, Side.ENEMY, models=5, ranks=1)
    b = Battle(2000, 2000, [shooter, foe], seed=1995, scenery=list(scenery))
    b.phase = "battle"
    return b


def sounds(b):
    return [(e.data["cue"], e.data["packet"], e.data["effect"], e.data["position"])
            for e in b.events if e.kind == "sound" and str(e.data.get("handle", "")).startswith("collapse")]


TUDOR = {"name": "Tudor2Stry", "x": 500, "y": 500, "dir": 64}
TENT = {"name": "GrsOrcBoyzTent", "x": 200, "y": 200}


class ScheduleTests(unittest.TestCase):
    """Section 3: 45 puffs thickening up to the swap on effect tick 138, 25 thinning out to the end on 224."""

    def test_the_swap_and_end_ticks(self):
        self.assertEqual((buildings.COLLAPSE_SWAP_TICK, buildings.COLLAPSE_END_TICK), (138, 224))
        self.assertEqual((len(buildings.PUFFS_BEFORE), len(buildings.PUFFS_AFTER)), (45, 25))

    def test_the_puffs_come_closer_together_before_the_swap(self):
        self.assertEqual(buildings.PUFFS_BEFORE[:3], [0, 5, 10])
        self.assertEqual(buildings.PUFFS_BEFORE[-2:], [136, 137])
        self.assertEqual(buildings.PUFFS_AFTER[0], 138)
        self.assertEqual(buildings.PUFFS_AFTER[-1], 216)

    def test_a_puff_point_uses_three_draws_in_order(self):
        collapse = buildings.Collapse("building:0", 500, 500, 31, 88, 0)
        puff = buildings.puff_at(collapse, Draws(128, 10, 4), 7)  # a quarter turn: +x; 44 - 4
        self.assertEqual((puff.x, puff.y, puff.height, puff.started), (510, 500, 40, 7))

    def test_axis_offsets_round_down(self):
        collapse = buildings.Collapse("building:0", 500, 500, 31, 88, 0)
        puff = buildings.puff_at(collapse, Draws(384, 10, 0), 0)  # -x: floor(-256 * 10 / 256)
        self.assertEqual((puff.x, puff.y), (490, 500))


class SwapTests(unittest.TestCase):
    def test_a_single_model_building_turns_into_its_ruin_at_once_without_a_collapse(self):
        b = battle(TENT)
        b.destroy_building(b.buildings[0])
        self.assertEqual((b.ruined, b.collapses, sounds(b)), ({"building:0"}, [], []))

    def test_a_multi_model_building_turns_into_its_ruin_at_the_peak_of_its_collapse(self):
        b = battle(TUDOR)
        b.destroy_building(b.buildings[0])
        self.assertTrue(b.buildings[0].destroyed)  # the game state does not wait for the swap
        self.assertEqual(b.ruined, set())
        self.assertEqual(sounds(b), [("loop_start", 2, 12, (500.0, 500.0))])
        for _ in range(buildings.COLLAPSE_SWAP_TICK):
            b.tick()
        self.assertEqual(b.ruined, set())
        b.tick()
        self.assertEqual(b.ruined, {"building:0"})
        while b.collapses:
            b.tick()
        self.assertEqual(sounds(b)[-1][0], "loop_stop")
        self.assertEqual(b.tick_count, buildings.COLLAPSE_END_TICK + 1)

    def test_the_collapse_spawns_its_smoke_puffs_on_schedule(self):
        b = battle(TUDOR)
        b.destroy_building(b.buildings[0])
        b.tick()
        self.assertEqual([p.started for p in b.collapse_puffs], [0])
        for _ in range(10):
            b.tick()
        self.assertEqual([p.started for p in b.collapse_puffs], [0, 5, 10])


class ShootingTests(unittest.TestCase):
    """Section 5, without behaviour scripts (the scripts drop the target themselves on event 0x18)."""

    def test_a_unit_firing_at_a_building_stops_when_it_falls(self):
        b = battle(TUDOR)
        index = b.fire_pick_building(500, 500)
        b.order_fire("S", point=(500, 500), object_index=index)
        b.destroy_building(b.buildings[0])
        self.assertIsNone(b.regiments["S"].shooting_mode)

    def test_a_fire_order_at_the_ruin_keeps_shooting_at_it(self):
        b = battle(TUDOR)
        b.destroy_building(b.buildings[0])
        index = b.fire_pick_building(500, 500)
        self.assertEqual(b.order_fire("S", point=(500, 500), object_index=index), 2007)
        b.tick()
        self.assertEqual(b.regiments["S"].shooting_mode, "building")


def triangle(x):
    """A one-triangle mesh in the flat PBX layout (whshr.pbx.parse_mesh)."""
    return {"verts": [x, 0, 0, x, 1, 0, x, 0, 1], "uv": [0, 0] * 3, "normals": [0, 1, 0],
            "faces": [((0, 1, 2), (0, 0, 0))], "ftex": [0]}


class DrawingTests(unittest.TestCase):
    """Sections 1, 2: the ruin is read from furniture record i + 59 and replaces the intact mesh in place."""

    def test_a_ruined_piece_is_baked_with_its_ruin_mesh_and_the_intact_one_is_gone(self):
        piece = battlefield.BuildingPiece("building:0", {"x": 0, "y": 0, "dir": 0}, 0.0, triangle(1.0), triangle(5.0))
        field = SimpleNamespace(building_pieces=[piece], ground_texture_count=0, scenery_texture_count=1,
                                ambient=battlefield.DEFAULT_AMBIENT, light=battlefield.DEFAULT_LIGHT)
        intact = battlefield.Battlefield.building_vertices(field, ())
        ruin = battlefield.Battlefield.building_vertices(field, {"building:0"})
        self.assertEqual(len(intact), len(ruin))
        self.assertNotEqual(intact, ruin)
        self.assertIsInstance(ruin, array)

    def test_the_building_buffer_holds_any_mix_of_intact_and_ruined_pieces(self):
        def mesh(triangles):
            return {"verts": [0, 0, 0, 1, 0, 0, 0, 1, 0], "uv": [0, 0] * 3, "normals": [0, 1, 0],
                    "faces": [((0, 1, 2), (0, 0, 0))] * triangles, "ftex": [0] * triangles}

        grows = battlefield.BuildingPiece("building:0", {"x": 0, "y": 0, "dir": 0}, 0.0, mesh(1), mesh(3))
        shrinks = battlefield.BuildingPiece("building:1", {"x": 0, "y": 0, "dir": 0}, 0.0, mesh(4), mesh(1))
        field = SimpleNamespace(building_pieces=[grows, shrinks], ground_texture_count=0, scenery_texture_count=1,
                                ambient=battlefield.DEFAULT_AMBIENT, light=battlefield.DEFAULT_LIGHT)
        capacity = battlefield.Battlefield.building_capacity(field)
        mixes = [(), {"building:0"}, {"building:1"}, {"building:0", "building:1"}]
        sizes = [len(battlefield.Battlefield.building_vertices(field, ruined)) for ruined in mixes]
        self.assertEqual(capacity, max(sizes))  # only building:0 ruined is the largest mix
        self.assertGreater(capacity, max(sizes[0], sizes[3]))

    def test_the_ruin_is_record_plus_59_of_a_building_record_whatever_its_name(self):
        furniture = [{"name": f"F{i}", "file": f"M{i}", "flags": 5} for i in range(146)]
        furniture[57] = {"name": "BlackWoodShack", "file": "SHACK2", "flags": 24}
        furniture[116] = {"name": "D_BlackWoodShac", "file": "SHACK2_D", "flags": 5}
        game = SimpleNamespace(require=lambda name: name)
        with mock.patch.object(battlefield, "exe_tables", lambda path: ([], furniture, {"exe": path})):
            ruins = battlefield.furniture_ruins(game)
        self.assertEqual(ruins, {"blackwoodshack": "SHACK2_D.XOF"})


if __name__ == "__main__":
    unittest.main()
