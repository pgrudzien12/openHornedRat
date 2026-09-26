"""ScatterModelsToNode: node selection by id, the node radius and per-model destinations (issue #162).

Scenarios follow the "Test cases" section of notes/scatter_models_to_node.md. Battles are built from
synthetic `[NODES]` tables through `Battle.from_script`, so nodes carry their own `id`, `radius` and
status exactly as a loaded `.BTS` does.
"""

import math
import random
import unittest

from whshr import behaviour, nodes
from whshr.engine import Battle

SCATTER = 0x48  # ScatterModelsToNode
SNAP = 0x67  # SnapModelsToFormation


class _FakeScriptDll:
    """Minimal stand-in for behaviour.ScriptDll: scripts(ids) -> {id: [word, ...]}."""

    def __init__(self, scripts: dict[int, list[int]]) -> None:
        self._scripts = scripts

    def scripts(self, ids: list[int]) -> dict[int, list[int]]:
        return {i: self._scripts[i] for i in ids}


def _word(opcode: int) -> int:
    return behaviour.OPCODE_FLAG | opcode


def _node(x: float, y: float, node_id: int = 0, radius: int | None = 16, active: bool = True) -> dict:
    return {"x": x, "y": y, "id": node_id, "radius": radius, "dir": 0,
            "status": ["ns_active"] if active else []}


def _peasants(x: float, y: float, models: int) -> dict:
    return {"id": "Peasants", "name": "Peasants", "sprites": "Peasant,0",
            "set": {"x": x, "y": y, "dir": 0, "script": 0},
            # s_side 0x81 = enemy; the remaining bytes are the unit's size (models, ranks).
            "stats": {"s_side": [0x81, 1, models, 1]}}


def _battle(node_views: list[dict], words: list[int], models: int = 8, at: tuple[float, float] = (600, 600)) -> Battle:
    source = {"field": {"width": 2000, "height": 2000, "script": "BF999"},
              "armies": [{"units": [_peasants(at[0], at[1], models)]}],
              "merc": {"armies": []}, "nodes": node_views}
    return Battle.from_script(source, script_dll=_FakeScriptDll({0: words}))


def _settle(battle: Battle, limit: int = 3000) -> list[tuple[float, float]]:
    """Tick until every model stops walking; return their positions."""
    regiment = battle.regiments["Peasants"]
    for _ in range(limit):
        battle.tick()
        if battle.tick_count > 2 and not regiment.walking:
            break
    return regiment.model_positions()


class ScatterDistanceTests(unittest.TestCase):
    """Case 1: the destination distance is uniform over 0 .. radius - 1 from the node centre."""

    def test_given_a_radius_133_node_when_scattering_many_times_then_distances_are_uniform_below_133(self):
        table = [nodes.ScriptNode(623.0, 702.0, node_id=2, radius=133)]
        rng = random.Random(1995)
        distances = [math.hypot(x - 623.0, y - 702.0)
                     for _ in range(4000)
                     for _, (x, y) in nodes.scatter_destinations(table, 2, 1, rng)]
        self.assertEqual(len(distances), 4000)
        self.assertLess(max(distances), 133.0)
        # Uniform in distance (not area): a quarter below 33, half below 66.5, a quarter above 99.75.
        self.assertAlmostEqual(sum(d < 33.25 for d in distances) / 4000, 0.25, delta=0.03)
        self.assertAlmostEqual(sum(d < 66.5 for d in distances) / 4000, 0.5, delta=0.03)
        self.assertAlmostEqual(sum(d >= 99.75 for d in distances) / 4000, 0.25, delta=0.03)

    def test_given_one_node_when_a_unit_scatters_then_its_models_end_inside_the_node_circle(self):
        battle = _battle([_node(700, 700, node_id=2, radius=60)], [_word(SCATTER), 2, behaviour.END])
        regiment = battle.regiments["Peasants"]
        before = (regiment.x, regiment.y)
        for x, y in _settle(battle):
            self.assertLess(math.hypot(x - 700, y - 700), 60 + 3)  # within a model's arrival distance
        self.assertEqual((regiment.x, regiment.y), before)  # the regiment position does not change


class ScatterNodeSelectionTests(unittest.TestCase):

    def test_given_two_active_nodes_sharing_the_id_when_an_8_model_unit_scatters_then_models_alternate(self):
        # Case 2: model 0 -> node A, model 1 -> node B, model 2 -> A, ...
        table = [nodes.ScriptNode(100.0, 100.0), nodes.ScriptNode(400.0, 400.0, node_id=4, radius=10),
                 nodes.ScriptNode(900.0, 100.0), nodes.ScriptNode(700.0, 700.0, node_id=4, radius=10)]
        chosen = [index for index, _ in nodes.scatter_destinations(table, 4, 8, random.Random(7))]
        self.assertEqual(chosen, [1, 3, 1, 3, 1, 3, 1, 3])

    def test_given_two_nodes_sharing_the_id_when_the_unit_scatters_then_it_splits_across_both_circles(self):
        battle = _battle([_node(450, 600, node_id=4, radius=12), _node(750, 600, node_id=4, radius=12)],
                         [_word(SCATTER), 4, behaviour.END], models=8)
        positions = _settle(battle)
        near_a = sum(math.hypot(x - 450, y - 600) < 15 for x, y in positions)
        near_b = sum(math.hypot(x - 750, y - 600) < 15 for x, y in positions)
        self.assertEqual((near_a, near_b), (4, 4))

    def test_given_no_active_node_with_the_id_when_scattering_then_nothing_moves_and_the_script_continues(self):
        # Case 3: an inactive node with the id is skipped like a missing one.
        battle = _battle([_node(900, 900, node_id=5, radius=30, active=False)],
                         [_word(SCATTER), 5, _word(0x1A), 7, behaviour.END])  # ScatterModelsToNode 5; SetWait 7
        regiment = battle.regiments["Peasants"]
        before = list(regiment.model_positions())
        battle.tick()
        battle.tick()
        self.assertEqual(regiment.model_positions(), before)
        self.assertEqual(battle.event_bus.unit_states["Peasants"].wait_duration, 7)

    def test_given_an_id_0_node_at_list_index_2_when_scattering_to_2_then_the_node_with_id_2_is_used(self):
        # Case 4: the operand is a node id, never a list position (the BF003 bug).
        battle = _battle([_node(100, 100), _node(200, 200), _node(719, 970, radius=21),
                          _node(623, 702, node_id=2, radius=40)],
                         [_word(SCATTER), 2, behaviour.END], at=(600, 650))
        for x, y in _settle(battle):
            self.assertLess(math.hypot(x - 623, y - 702), 40 + 3)


class ScatterRadiusEdgeTests(unittest.TestCase):

    def test_given_radius_0_when_scattering_then_every_destination_is_the_node_centre(self):
        # Case 5.
        table = [nodes.ScriptNode(300.0, 250.0, node_id=1, radius=0)]
        points = [point for _, point in nodes.scatter_destinations(table, 1, 6, random.Random(3))]
        for x, y in points:
            self.assertAlmostEqual(x, 300.0)
            self.assertAlmostEqual(y, 250.0)

    def test_given_a_node_without_a_radius_keyword_when_loaded_then_it_scatters_within_16(self):
        # Case 6.
        table = nodes.from_views([_node(300, 250, node_id=1, radius=None)])
        self.assertEqual(table[0].radius, 16)
        for x, y in (point for _, point in nodes.scatter_destinations(table, 1, 200, random.Random(5))):
            self.assertLess(math.hypot(x - 300, y - 250), 16)


class ScatterFormationStateTests(unittest.TestCase):

    def test_given_scattered_models_when_snapped_to_formation_then_they_return_to_their_slots(self):
        battle = _battle([_node(700, 600, node_id=2, radius=40)],
                         [_word(SCATTER), 2, _word(0x1A), 400, _word(0x1C), _word(SNAP), behaviour.END],
                         at=(500, 500))
        regiment = battle.regiments["Peasants"]
        slots = list(regiment.model_positions())
        for _ in range(300):
            battle.tick()
        self.assertTrue(all(math.hypot(x - 700, y - 600) < 43 for x, y in regiment.model_positions()))
        for _ in range(600):
            battle.tick()
        for (x, y), (sx, sy) in zip(regiment.model_positions(), slots):
            self.assertLess(math.hypot(x - sx, y - sy), 3.5)

    def test_given_a_bf003_style_patrol_loop_when_it_runs_then_models_keep_wandering_inside_the_circle(self):
        # Scatter; Snap; PushPC; Scatter; SetWait 5; Wait; Loop -- the shape of every BF003 peasant script.
        words = [_word(SCATTER), 2, _word(SNAP), _word(0x06), _word(SCATTER), 2, _word(0x1A), 5,
                 _word(0x1C), _word(0x07), behaviour.END]
        battle = _battle([_node(623, 702, node_id=2, radius=133)], words, models=6, at=(645, 670))
        regiment = battle.regiments["Peasants"]
        seen: list[list[tuple[float, float]]] = []
        for tick in range(1500):
            battle.tick()
            if tick >= 300 and tick % 100 == 0:
                seen.append(list(regiment.model_positions()))
        for snapshot in seen:
            for x, y in snapshot:
                self.assertLess(math.hypot(x - 623, y - 702), 133 + 3)
        self.assertNotEqual(seen[0], seen[-1])  # the models are still wandering, not frozen


if __name__ == "__main__":
    unittest.main()
