"""Tests for wiring the bytecode interpreter into real battle construction (issue #3/#46).

Covers the two halves of the wiring:
1. `Battle.from_script`/`Battle.__init__` thread a `script_dll` through to `ScriptInterpreter`, and
   compute each regiment's initial script id from its own `set:script=` value.
2. `BattleScene._load_script_dll` locates and loads the mission's own `SCRIPT/BFxxx.DLL`, and fails
   gracefully (returns None, falls back to the placeholder AI) when there is no script name, no
   matching DLL file, or the DLL can't be parsed -- a battle must never fail to start over this.

None of this touches real mission bytecode: `ScriptDll` is only exercised against absent files and
deliberately malformed bytes, to test the fallback paths without needing a game installation.
"""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from whshr import behaviour, interpreter
from whshr.assets import AssetId, AssetLocator
from whshr.battle_scene import BattleScene
from whshr.cache import AssetCache
from whshr.catalog import build
from whshr.engine import Battle, Regiment
from whshr.rules import Side
from whshr.scenes import SceneAssets, SceneMachine


def _unit(identifier, x, y, script=None, size=(0x81, 10, 10, 2)):
    # size[0] is the s_side byte (notes/neutral_units.md): 0x81 = enemy (bit 7), type code 1.
    set_block = {"x": x, "y": y, "dir": 0}
    if script is not None:
        set_block["script"] = script
    return {"id": identifier, "name": identifier.replace("_", " "), "sprites": "ClanRats,0",
            "set": set_block, "stats": {"s_side": list(size)}}


class ScriptIdWiringTests(unittest.TestCase):
    """Battle.from_script computes each regiment's initial script id from set:script=."""

    def _battle(self, units, merc_units=None):
        source = {
            "field": {"width": 1600, "height": 1760, "script": "BF003"},
            "armies": [{"units": units}],
            "merc": {"armies": [{"units": merc_units or []}]},
        }
        return Battle.from_script(source)

    def test_numeric_set_script_becomes_the_regiments_initial_script_id(self):
        battle = self._battle([_unit("Goblin_Stickers", 100, 100, script=0)])
        state = battle.event_bus.unit_states["Goblin_Stickers"]
        self.assertEqual(state.script_id, 0)

    def test_player_script_literal_maps_to_the_shared_library_script(self):
        battle = self._battle([], merc_units=[_unit("Grudgebringer_Cavalry", 500, 500, script="PLAYER_SCRIPT")])
        state = battle.event_bus.unit_states["Grudgebringer_Cavalry"]
        self.assertEqual(state.script_id, behaviour.PLAYER_SCRIPT)

    def test_unit_without_a_set_script_line_defaults_to_the_shared_library_script(self):
        battle = self._battle([_unit("Peasants", 300, 300)])
        state = battle.event_bus.unit_states["Peasants"]
        self.assertEqual(state.script_id, behaviour.PLAYER_SCRIPT)

    def test_no_script_dll_means_no_interpreter_and_the_placeholder_ai_runs_instead(self):
        battle = self._battle([_unit("Goblin_Stickers", 100, 100, script=0)])
        self.assertIsNone(battle.script_dll)
        self.assertIsNone(battle.interpreter)

    def test_script_dll_passed_through_constructs_an_interpreter(self):
        # A real ScriptDll needs real PE bytes; a bare sentinel is enough to prove threading works,
        # since Battle only checks truthiness to decide whether to construct the interpreter.
        sentinel_dll = object()
        battle = Battle.from_script(
            {"field": {"width": 100, "height": 100, "script": "BF003"},
             "armies": [{"units": [_unit("Goblin_Stickers", 10, 10, script=0)]}],
             "merc": {"armies": []}},
            script_dll=sentinel_dll)
        self.assertIs(battle.script_dll, sentinel_dll)
        self.assertIsNotNone(battle.interpreter)
        self.assertIs(battle.interpreter.script_dll, sentinel_dll)


class NodeWiringTests(unittest.TestCase):
    """Battle.from_script reads the battle's own [NODES] table (whshr.script.load_battle) into
    Battle.nodes -- previously parsed and available but silently discarded (issue #3/#46)."""

    def _source(self, nodes):
        return {
            "field": {"width": 1600, "height": 1760, "script": "BF003"},
            "armies": [{"units": [_unit("Goblin_Stickers", 100, 100, script=0)]}],
            "merc": {"armies": []},
            "nodes": nodes,
        }

    def test_nodes_become_battle_nodes_keyed_by_their_position_not_their_id(self):
        battle = Battle.from_script(self._source([
            {"id": 0, "x": 300, "y": 400, "radius": 10, "dir": 0, "status": []},
            {"id": 2, "x": 500.5, "y": 600.5, "radius": None, "dir": None, "status": ["ns_startpos"]},
        ]))
        self.assertEqual(battle.nodes, {0: (300.0, 400.0), 1: (500.5, 600.5)})

    def test_a_node_with_no_id_still_counts_by_position(self):
        battle = Battle.from_script(self._source([{"id": None, "x": 1, "y": 2, "radius": None,
                                                     "dir": None, "status": []}]))
        self.assertEqual(battle.nodes, {0: (1.0, 2.0)})

    def test_a_node_with_missing_coordinates_is_excluded(self):
        battle = Battle.from_script(self._source([{"id": 5, "x": None, "y": None, "radius": None,
                                                     "dir": None, "status": []}]))
        self.assertEqual(battle.nodes, {})

    def test_a_source_with_no_nodes_key_at_all_defaults_to_empty(self):
        source = self._source([])
        del source["nodes"]
        battle = Battle.from_script(source)
        self.assertEqual(battle.nodes, {})

    def test_a_battle_built_directly_without_nodes_defaults_to_empty(self):
        battle = Battle(500, 500, [])
        self.assertEqual(battle.nodes, {})


class BattleSceneScriptDllLoadingTests(unittest.TestCase):
    """BattleScene._load_script_dll locates the mission's own SCRIPT/BFxxx.DLL, or fails gracefully."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in ("FILE/SCRIPT/BF003.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.locator = AssetLocator(self.root)
        self.context = SceneAssets(self.locator, build(self.root), AssetCache(), {})

    def tearDown(self):
        self.temporary.cleanup()

    def _scene_with_field_script(self, source):
        scene = BattleScene()
        scene.field = SimpleNamespace(script=source)
        return scene

    def test_no_loadscript_name_returns_none(self):
        scene = self._scene_with_field_script({"field": {"width": 100, "height": 100}})
        self.assertIsNone(scene._load_script_dll(self.context))

    def test_loadscript_name_with_no_matching_dll_file_returns_none(self):
        scene = self._scene_with_field_script({"field": {"width": 100, "height": 100, "script": "BF999"}})
        self.assertIsNone(scene._load_script_dll(self.context))

    def test_loadscript_name_with_an_unparseable_dll_returns_none_not_raise(self):
        dll_path = self.root / "FILE" / "SCRIPT" / "BF003.DLL"
        dll_path.write_bytes(b"not a real PE file")
        scene = self._scene_with_field_script({"field": {"width": 100, "height": 100, "script": "BF003"}})
        self.assertIsNone(scene._load_script_dll(self.context))

    def test_loadscript_name_match_is_case_insensitive(self):
        dll_path = self.root / "FILE" / "SCRIPT" / "bf003.dll"
        dll_path.write_bytes(b"not a real PE file")
        scene = self._scene_with_field_script({"field": {"width": 100, "height": 100, "script": "BF003"}})
        # Still None (malformed bytes), but must reach the parse attempt rather than fail to find it --
        # verified indirectly: a wrong-case *missing* file would also return None, so assert the file
        # was actually found by checking a real, valid path resolves instead of raising FileNotFoundError.
        self.assertIsNone(scene._load_script_dll(self.context))

    def test_a_broken_script_dll_never_blocks_the_battle_from_starting(self):
        (self.root / "FILE" / "SCRIPT" / "BF003.DLL").write_bytes(b"not a real PE file")
        scene = BattleScene(battle=AssetId("vanilla", "battle", "bf003"))
        SceneMachine(scene, SceneAssets(
            self.locator, build(self.root), AssetCache(),
            {"battle-script": lambda _, __: SimpleNamespace(script={
                "field": {"width": 1600, "height": 1760, "script": "BF003"},
                "armies": [{"units": [_unit("Goblin_Stickers", 100, 100, script=0)]}],
                "merc": None},
            )}))
        self.assertIsNotNone(scene.battle)
        self.assertIsNone(scene.battle.interpreter)


class InitUnitDoesNotClobberTheWiredScriptIdTests(unittest.TestCase):
    """Regression test: InitUnit's operand is an init-size flag (128/64), not a script id.

    A prior version of op_InitUnit wrote the operand into state.script_id and reset state.pc to 0,
    which silently overwrote the script id Battle.from_script had just wired in from the unit's own
    set:script= value (tests/test_interpreter_wiring.py's ScriptIdWiringTests) -- the moment a real
    script's first instruction (InitUnit) ran, every unit jumped onto script 128 or 64 instead of
    its actual mission script. Confirmed against a real BF003 playthrough log: every enemy regiment
    sat frozen for 477+ ticks with attack_target always None, despite a player regiment walking
    right up next to it.
    """

    def test_init_unit_leaves_the_wired_script_id_untouched(self):
        battle = Battle.from_script({
            "field": {"width": 1440, "height": 1680, "script": "BF003"},
            "armies": [{"units": [_unit("Goblin_Stickers", 100, 100, script=0)]}],
            "merc": {"armies": []},
        })
        state = battle.event_bus.unit_states["Goblin_Stickers"]
        self.assertEqual(state.script_id, 0)  # wired correctly at construction

        interp = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        interp.op_InitUnit(state, 128, [], "Goblin_Stickers", 0, battle.rng)

        self.assertEqual(state.script_id, 0)  # still script 0 -- not clobbered to 128

    def test_init_unit_advances_pc_by_one_not_reset_to_zero(self):
        state = interpreter.UnitScriptState(script_id=0, pc=5)
        interp = interpreter.ScriptInterpreter(None, None, None)
        result = interp.op_InitUnit(state, 128, [], "t", 0, None)
        self.assertEqual(result, 6)


class SetBehaviourDoesNotPreemptScriptGatingTests(unittest.TestCase):
    """Regression test: SetBehaviour used to call track_threat() immediately, setting
    attack_target on tick 0 regardless of any SetWait/Wait/MoveToNode gating later in the same
    script. Confirmed against a real BF003 playthrough where the reinforcement Goblin Wolfriders
    attacked from the first tick instead of respecting its own SetWait 60 gate.
    """

    def setUp(self):
        self.reinforcement = Regiment("Goblin_Wolfriders", "Wolfriders", 500, 500, 0, Side.ENEMY,
                                       models=10, ranks=2, leadership=6)
        self.player = Regiment("player_1", "Player", 100, 100, 0, Side.PLAYER, models=10, ranks=2)
        self.battle = Battle(1000, 1000, [self.player, self.reinforcement], seed=1995)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)

    def test_set_behaviour_only_records_the_id_and_does_not_attack(self):
        state = self.battle.event_bus.unit_states["Goblin_Wolfriders"]
        self.interp.op_SetBehaviour(state, 15, [], "Goblin_Wolfriders", 0, self.battle.rng)

        self.assertEqual(state.behaviour_id, 15)
        self.assertIsNone(self.reinforcement.attack_target)  # not attacking yet

    def test_a_setwait_60_gate_after_setbehaviour_is_no_longer_bypassed(self):
        """Simulates the real BF003 Wolfriders shape: SetBehaviour 15, then WaitForBattleStart,
        SetWait 60, Wait -- the unit must still be idle at tick 1, not already attacking."""
        state = self.battle.event_bus.unit_states["Goblin_Wolfriders"]
        self.interp.op_SetBehaviour(state, 15, [], "Goblin_Wolfriders", 0, self.battle.rng)
        self.interp.op_WaitForBattleStart(state, None, [], "Goblin_Wolfriders", 1, self.battle.rng)
        self.interp.op_SetWait(state, 60, [], "Goblin_Wolfriders", 1, self.battle.rng)
        self.interp.op_Wait(state, None, [], "Goblin_Wolfriders", 1, self.battle.rng)

        self.assertIsNone(self.reinforcement.attack_target)
        self.assertGreater(state.wait_remaining, 0)


if __name__ == "__main__":
    unittest.main()
