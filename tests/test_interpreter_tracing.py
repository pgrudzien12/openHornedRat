"""Tests for opcode-level tracing and gap reporting (issue #3/#46).

Two mechanisms, added after two real bugs (InitUnit clobbering script_id, SetBehaviour preempting
script gating) were only found by manually cross-referencing regiment positions across dozens of
battle-log snapshots -- a slow, unreliable way to debug a bytecode interpreter:

1. `BattleLogger.write_opcode` / `ScriptInterpreter`'s `trace_scripts` path: an opt-in, per-opcode
   execution trace (tick, unit, script, pc, opcode, operand, outcome, and a small state snapshot),
   off by default (it's much higher volume than the rest of the battle log), turned on via the
   `WHSHR_TRACE_SCRIPTS` environment variable in `whshr.battle_scene.BattleScene.enter`.
2. `ScriptInterpreter._report_gap`: always-on (regardless of tracing), surfaces a missing or
   crashing opcode as a normal `BattleEvent` the first time a given (unit, script, opcode) hits it,
   so a broken/unimplemented opcode is visible in every battle log without needing to opt into
   full tracing -- deduplicated so a tight retry loop doesn't spam the same complaint every tick.
"""

from pathlib import Path
from unittest import mock
import re
import tempfile
import unittest

from whshr import battle_log, behaviour, interpreter
from whshr.assets import AssetId, AssetLocator
from whshr.battle_scene import BattleScene
from whshr.cache import AssetCache
from whshr.catalog import build
from whshr.engine import Battle, Regiment
from whshr.scenes import SceneAssets, SceneMachine


def _find_unimplemented_opcode():
    """An opcode with no handler right now, picked dynamically so this test survives new opcodes
    being implemented over time."""
    with open("whshr/interpreter.py", encoding="utf-8") as handle:
        defined = set(re.findall(r"def op_(\w+)", handle.read()))
    for opcode, name in behaviour.OPCODE_NAMES.items():
        if name not in defined:
            return opcode, name
    raise AssertionError("every catalogued opcode has a handler; pick a different test fixture")


class _FakeScriptDll:
    """A minimal stand-in for behaviour.ScriptDll: scripts(ids) -> {id: [word, ...]}."""

    def __init__(self, scripts):
        self._scripts = scripts

    def scripts(self, ids):
        return {i: self._scripts[i] for i in ids}


def _word(opcode):
    return behaviour.OPCODE_FLAG | opcode


class BattleLoggerOpcodeRecordTests(unittest.TestCase):
    """write_opcode's record shape and its trace_scripts/enabled gating."""

    def test_write_opcode_is_a_noop_when_disabled(self):
        logger = battle_log.BattleLogger(path=None, trace_scripts=True)
        self.assertFalse(logger.enabled)
        logger.write_opcode(0, unit_id="t", script_id=0, pc=0, opcode=0x17,
                             opcode_name="Yield", operand=None, outcome="ok", state={})
        # No exception, nothing to read back (path=None) -- this is the whole assertion.

    def test_write_opcode_record_shape(self, tmp_path=None):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            logger = battle_log.BattleLogger(path, trace_scripts=True)
            logger.write_opcode(5, unit_id="Goblin_Stickers", script_id=0, pc=11, opcode=0x33,
                                 opcode_name="SetBehaviour", operand=15, outcome="ok",
                                 state={"cond_flags": 0, "attack_target": None})
            logger.close()
            import json
            record = json.loads(path.read_text().splitlines()[0])
        self.assertEqual(record["type"], "opcode")
        self.assertEqual(record["tick"], 5)
        self.assertEqual(record["unit_id"], "Goblin_Stickers")
        self.assertEqual(record["script_id"], 0)
        self.assertEqual(record["pc"], 11)
        self.assertEqual(record["opcode_name"], "SetBehaviour")
        self.assertEqual(record["operand"], 15)
        self.assertEqual(record["outcome"], "ok")
        self.assertEqual(record["state"]["attack_target"], None)


class TraceScriptsIntegrationTests(unittest.TestCase):
    """ScriptInterpreter.run() actually writes trace records when the logger asks for them."""

    def setUp(self):
        self.regiment = Regiment("enemy_1", "Enemy", 100, 100, 0, False, models=10, ranks=2)
        self.battle = Battle(500, 500, [self.regiment], seed=1995)
        self.opcode, self.opcode_name = _find_unimplemented_opcode()
        length = behaviour.LENGTHS[self.opcode]
        # opcode word, then (length - 1) filler operand words, then Yield, then End.
        words = [_word(self.opcode)] + [0] * (length - 1) + [_word(0x17), behaviour.END]
        self.script_dll = _FakeScriptDll({0: words})

    def test_no_trace_records_written_when_trace_scripts_is_off(self):
        logger = battle_log.BattleLogger(path=None, trace_scripts=False)
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, self.script_dll, logger=logger)
        state = self.battle.event_bus.unit_states["enemy_1"]
        state.script_id = 0
        # Should not raise even though the logger is disabled and trace_scripts is off.
        interp.run("enemy_1", state, 0, self.battle.rng)

    def test_trace_records_written_for_every_dispatched_opcode(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            logger = battle_log.BattleLogger(path, trace_scripts=True)
            interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, self.script_dll, logger=logger)
            state = self.battle.event_bus.unit_states["enemy_1"]
            state.script_id = 0
            interp.run("enemy_1", state, 3, self.battle.rng)
            logger.close()
            records = [json.loads(line) for line in path.read_text().splitlines()]

        opcode_records = [r for r in records if r["type"] == "opcode"]
        # The unimplemented opcode (skipped), then Yield (which stops the tick) -- both traced.
        self.assertEqual(len(opcode_records), 2)
        self.assertEqual(opcode_records[0]["outcome"], "unimplemented")
        self.assertEqual(opcode_records[0]["opcode_name"], self.opcode_name)
        self.assertEqual(opcode_records[0]["tick"], 3)
        self.assertEqual(opcode_records[1]["outcome"], "ok")
        self.assertEqual(opcode_records[1]["opcode_name"], "Yield")


class GapReportingTests(unittest.TestCase):
    """_report_gap: always-on, deduplicated BattleEvents for missing/broken opcodes."""

    def setUp(self):
        self.regiment = Regiment("enemy_1", "Enemy", 100, 100, 0, False, models=10, ranks=2)
        self.battle = Battle(500, 500, [self.regiment], seed=1995)
        self.opcode, self.opcode_name = _find_unimplemented_opcode()
        length = behaviour.LENGTHS[self.opcode]
        words = [_word(self.opcode)] + [0] * (length - 1) + [_word(0x17), behaviour.END]
        self.script_dll = _FakeScriptDll({0: words})
        self.interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, self.script_dll)

    def test_hitting_a_missing_opcode_appends_exactly_one_battle_event(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        state.script_id = 0
        self.interp.run("enemy_1", state, 0, self.battle.rng)

        gap_events = [e for e in self.battle.events if e.kind == "script_gap"]
        self.assertEqual(len(gap_events), 1)
        self.assertIn(self.opcode_name, gap_events[0])
        self.assertEqual(gap_events[0].data["opcode_name"], self.opcode_name)

    def test_repeated_hits_in_the_same_script_are_not_reported_twice(self):
        state = self.battle.event_bus.unit_states["enemy_1"]
        state.script_id = 0
        for tick in range(5):
            self.battle.events = []  # Battle.tick() normally clears this; simulate that here
            state.pc = 0  # re-enter the same instruction each "tick" like a real loop would
            self.interp.run("enemy_1", state, tick, self.battle.rng)

        # Across 5 separate run() calls hitting the exact same (unit, script, opcode), only the
        # very first should have produced a battle event (dedup key survives across calls).
        state.pc = 0
        self.battle.events = []
        self.interp.run("enemy_1", state, 5, self.battle.rng)
        gap_events = [e for e in self.battle.events if e.kind == "script_gap"]
        self.assertEqual(len(gap_events), 0)


class BattleSceneTraceEnvironmentVariableTests(unittest.TestCase):
    """WHSHR_TRACE_SCRIPTS turns on BattleScene's logger's trace_scripts flag."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in ("FILE/SCRIPT/BF003.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.log_dir = Path(self.temporary.name) / "logs"

    def tearDown(self):
        self.temporary.cleanup()

    def _enter_scene(self):
        scene = BattleScene(battle=AssetId("vanilla", "battle", "bf003"), log_dir=self.log_dir)
        SceneMachine(scene, SceneAssets(
            AssetLocator(self.root), build(self.root), AssetCache(),
            {"battle-script": lambda _, __: type("Field", (), {"script": {
                "field": {"width": 1440, "height": 1680},
                "armies": [{"units": []}], "merc": None}})()}))
        return scene

    def test_trace_scripts_off_by_default(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("WHSHR_TRACE_SCRIPTS", None)
            scene = self._enter_scene()
        try:
            self.assertFalse(scene.logger.trace_scripts)
        finally:
            scene.logger.close()

    def test_trace_scripts_on_via_environment_variable(self):
        with mock.patch.dict("os.environ", {"WHSHR_TRACE_SCRIPTS": "1"}):
            scene = self._enter_scene()
        try:
            self.assertTrue(scene.logger.trace_scripts)
        finally:
            scene.logger.close()


if __name__ == "__main__":
    unittest.main()
