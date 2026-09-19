"""BDD scenarios for battle logging and deterministic replay (docs/testing.md), per
notes/engine_architecture.md, "Battle logs and replay". Uses small synthetic installations and battle
scripts only; the real installation is a manual regression check, not a committed fixture.
"""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest

from whshr import battle_replay, combat
from whshr.assets import AssetLocator
from whshr.battle_log import BattleLogger, default_log_path
from whshr.battle_scene import BATTLE_TICK_SECONDS, BattleScene
from whshr.cache import AssetCache
from whshr.catalog import build
from whshr.engine import Battle, Regiment
from whshr.scenes import SceneAssets, SceneMachine


def _unit(identifier, x, y, profile=None):
    return {"id": identifier, "name": identifier.replace("_", " "), "sprites": "ClanRats,0",
            "set": {"x": x, "y": y, "dir": 0}, "stats": {}, "profile": profile or {"M": 4, "I": 3}}


# Far apart: no contact happens on its own, so the scenario stays alive across many ticks and player
# orders, exercising recording and replay without a combat round ending it early.
MOVEMENT_SCRIPT = {
    "field": {"width": 1600, "height": 1760, "camera": 45.0},
    "armies": [{"units": [_unit("Enemy_Rats", 1500, 1700)]}],
    "merc": {"armies": [{"units": [_unit("Player_Cav", 100, 100)]}]},
}


class SyntheticInstallation(unittest.TestCase):
    """Base fixture: a small temporary WARFB tree plus a stdlib SceneAssets with a fake battle-script
    loader (docs/testing.md, "Use small synthetic installations and battle data")."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.log_dir = self.root / "logs"

    def tearDown(self):
        self.temporary.cleanup()

    def _context(self, script=MOVEMENT_SCRIPT):
        return SceneAssets(AssetLocator(self.root), build(self.root), AssetCache(),
                           {"battle-script": lambda _record, _path: SimpleNamespace(script=script)})


class RecordAndReplayTests(SyntheticInstallation):
    def test_given_a_battle_with_orders_when_recorded_and_replayed_then_snapshots_match_and_it_reports_identical(self):
        context = self._context()
        scene = BattleScene(log_dir=self.log_dir, seed=7)
        machine = SceneMachine(scene, context)
        scene.handle(("select", "Player_Cav"), context)
        scene.handle(("move_to", 400, 400), context)
        for _ in range(25):
            machine.update(BATTLE_TICK_SECONDS)
        scene.handle(("move_to", 900, 900), context)
        for _ in range(25):
            machine.update(BATTLE_TICK_SECONDS)
        machine.active.exit(context)  # as leaving the scene (or a player quit) would

        self.assertTrue(scene.logger.path.is_file())
        replay_context = self._context()
        replayed, header, divergence, _timeline = battle_replay.replay(
            self.root, scene.logger.path, context=replay_context)

        self.assertIsNone(divergence)
        self.assertEqual(header["battle_asset"], "vanilla:battle/bf001")
        self.assertEqual(replayed.battle.tick_count, scene.battle.tick_count)
        self.assertEqual(replayed.battle.regiments["Player_Cav"].x, scene.battle.regiments["Player_Cav"].x)

    def test_given_every_line_of_a_written_log_when_parsed_then_it_is_valid_json_and_the_header_comes_first(self):
        context = self._context()
        scene = BattleScene(log_dir=self.log_dir, seed=1)
        machine = SceneMachine(scene, context)
        for _ in range(20):
            machine.update(BATTLE_TICK_SECONDS)
        machine.active.exit(context)

        lines = scene.logger.path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]  # raises if any line is not valid JSON
        self.assertGreater(len(records), 0)
        self.assertEqual(records[0]["type"], "header")
        self.assertEqual(records[-1]["type"], "end")

    def test_given_a_result_check_when_a_snapshot_is_written_then_per_side_counts_are_logged(self):
        context = self._context()
        scene = BattleScene(log_dir=self.log_dir, seed=1)
        machine = SceneMachine(scene, context)
        for _ in range(combat.SEGMENT_TICKS):  # exactly one segment: the first snapshot tick
            machine.update(BATTLE_TICK_SECONDS)
        machine.active.exit(context)

        records = [json.loads(line) for line in scene.logger.path.read_text(encoding="utf-8").splitlines()]
        snapshots = [r for r in records if r["type"] == "snapshot"]
        self.assertEqual(len(snapshots), 1)
        counts = snapshots[0]["side_counts"]
        self.assertEqual(counts["player"], {"active": 1, "routing": 0, "fled": 0, "destroyed": 0, "total": 1})
        self.assertEqual(counts["enemy"], {"active": 1, "routing": 0, "fled": 0, "destroyed": 0, "total": 1})


class DisabledLoggingTests(SyntheticInstallation):
    def test_given_the_log_directory_is_not_writable_when_the_battle_runs_then_it_still_completes(self):
        blocker = self.root / "not_a_directory"
        blocker.write_bytes(b"x")  # a file where the logger will try to create a directory
        context = self._context()
        scene = BattleScene(log_dir=blocker / "sub", seed=1)
        machine = SceneMachine(scene, context)

        self.assertFalse(scene.logger.enabled)
        for _ in range(5):
            machine.update(BATTLE_TICK_SECONDS)  # must not raise
        self.assertEqual(scene.battle.tick_count, 5)

    def test_given_logging_disabled_when_the_battle_runs_then_it_still_completes(self):
        context = self._context()
        scene = BattleScene(log_dir=None, seed=1)
        machine = SceneMachine(scene, context)

        self.assertFalse(scene.logger.enabled)
        for _ in range(5):
            machine.update(BATTLE_TICK_SECONDS)
        self.assertEqual(scene.battle.tick_count, 5)


class DefaultLogPathTests(unittest.TestCase):
    def test_given_a_directory_and_battle_name_when_building_the_default_path_then_it_is_timestamped(self):
        from datetime import datetime

        path = default_log_path("logs", "bf001", when=datetime(2026, 9, 15, 1, 2, 3))
        self.assertEqual(path, Path("logs/battle-20260915-010203-bf001.jsonl"))


class CombatEventLoggingTests(unittest.TestCase):
    """Given a combat round, when logged, the event carries rolls, casualties and the Leadership
    test data (a bug-diagnosability requirement: the Otto Hiln cavalry rout)."""

    def test_given_a_melee_strike_when_logged_then_the_event_carries_rolls_bonuses_and_leadership_data(self):
        # Both Initiative 10 so they strike on the very first tick (game_rules.md 5.1) and every turn
        # after; a moderate advantage (WS4 S4 vs WS3 T3, both 20 models/4 ranks) whittles the loser down
        # without destroying it outright, so its scheduled break test (two turns after contact,
        # game_rules.md 6.2) is reached and fails with this fixed seed.
        attacker = Regiment("att", "Attacker", 0, 0, 0, True, models=20, ranks=4, initiative=10,
                            ws=4, strength=4, attacks=1, leadership=8, speed_per_tick=0.0)
        defender = Regiment("def", "Defender", 10, 0, 0, False, models=20, ranks=4, initiative=10,
                            ws=3, toughness=3, armour=0, leadership=7, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [attacker, defender], seed=3)
        logger = BattleLogger(Path(tempfile.mkdtemp()) / "combat.jsonl")

        for _ in range(combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 3):
            battle.tick()
            for event in battle.events:
                logger.write_event(battle.tick_count, event)
            if attacker.routing or defender.routing:
                break
        logger.close()

        records = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()]
        strike = next(r for r in records if r["kind"] == "melee_strike")
        self.assertIn("kills", strike)
        self.assertIn("rank_bonus", strike)
        self.assertIn("direction_bonus", strike)
        self.assertIn("tally", strike)
        # "attacks" is now one entry per fighting model (game_rules.md 5.7: models pair off on the
        # battle grid), each carrying that model's own target numbers and rolls.
        self.assertEqual(len(strike["attacks"]), strike["fighting"])
        first_model = strike["attacks"][0]
        self.assertIn("target_model", first_model)
        self.assertIn("gang_bonus", first_model)
        self.assertEqual(len(first_model["rolls"]), first_model["attacks"])
        first_roll = first_model["rolls"][0]
        self.assertIn("hit", first_roll)
        self.assertIn("result", first_roll)

        leadership = next(r for r in records if r["kind"] == "leadership_test")
        self.assertIn("leadership", leadership)
        self.assertIn("roll", leadership)
        self.assertIn("modifier", leadership)
        self.assertIn("passed", leadership)
        self.assertIn("cant_break", leadership)

        rout = next(r for r in records if r["kind"] == "rout_start")
        self.assertIn("flee_x", rout)
        self.assertIn("flee_y", rout)


class FleeingRemovalLoggingTests(unittest.TestCase):
    """Given a regiment fleeing across the field edge, removal is logged with its position."""

    def test_given_a_routing_regiment_when_it_crosses_the_field_edge_then_removal_is_logged_with_position(self):
        fleeing = Regiment("r", "Fleeing", 1595, 500, 128, True, models=5, speed_per_tick=1000.0, routing=True)
        battle = Battle(1600, 1760, [fleeing], seed=1)

        battle.tick()

        self.assertTrue(fleeing.fled)
        fled_events = [e for e in battle.events if e.kind == "fled"]
        self.assertEqual(len(fled_events), 1)
        self.assertEqual(fled_events[0].data["regiment"], "r")
        self.assertEqual(fled_events[0].data["width"], 1600)
        self.assertEqual(fled_events[0].data["height"], 1760)
        self.assertGreater(fled_events[0].data["x"], 1600)  # logged position is genuinely outside the field


if __name__ == "__main__":
    unittest.main()
