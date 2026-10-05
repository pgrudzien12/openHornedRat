from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from whshr.assets import AssetLocator
from whshr.battle_scene import BATTLE_TICK_SECONDS, BattleScene
from whshr.cache import AssetCache
from whshr.catalog import build
from whshr.glue_content import GlueContent
from whshr.glue_runtime import EndGame
from whshr.glue_scene import GlueScene
from whshr.result_scene import ResultScene
from whshr.rules import Side
from whshr.scenes import SceneAssets, SceneMachine, Scene, Transition


def _unit(identifier, x, y, size=(0x81, 10, 10, 2)):
    # size[0] is the s_side byte (notes/neutral_units.md): 0x81 = enemy (bit 7), type code 1. The
    # merc-army unit below forces Side.PLAYER regardless of its own s_side value, so only the enemy-
    # army default needs a realistic side bit here.
    return {"id": identifier, "name": identifier.replace("_", " "), "sprites": "ClanRats,0",
            "set": {"x": x, "y": y, "dir": 0}, "stats": {"s_side": list(size)}}


SCRIPT = {
    "field": {"width": 1600, "height": 1760, "camera": 45.0},
    "armies": [{"units": [_unit("Clanrat_Warriors", 100, 100), _unit("Clanrat_Warriors", 200, 100)]}],
    "merc": {"armies": [{"units": [_unit("Grudgebringer_Infantry", 500, 500, (1, 16, 16, 4))]}]},
}


class LeaveScene(Scene):
    def __init__(self, successor):
        self.successor = successor

    def handle(self, event, context):
        return Transition(self.successor, "return") if event == "return" else None


class BattleSceneTests(unittest.TestCase):
    def test_given_deployment_when_a_frame_stalls_then_only_one_update_runs_without_catchup(self):
        from tests.test_deployment import source
        self.context.loaders["battle-script"] = lambda _, path: SimpleNamespace(script=source(1))
        scene = BattleScene()
        machine = SceneMachine(scene, self.context)
        machine.update(2.0)
        self.assertEqual(scene.battle.update_count, 1)
        self.assertEqual(scene.battle.tick_count, 0)
        machine.update(0)
        self.assertEqual(scene.battle.update_count, 1)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in ("FILE/SCRIPT/BF001.BTS", "FILE/BINARY/STANDARD.PAL", "REMOTE/BINARY/ANIM/A1.SI"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
        self.loaded = []
        self.context = SceneAssets(AssetLocator(self.root), build(self.root), AssetCache(),
                                   {"battle-script": self._load})

    def tearDown(self):
        self.temporary.cleanup()

    def _load(self, _, path):
        self.loaded.append(path)
        return SimpleNamespace(script=SCRIPT)

    def test_given_battle_script_when_scene_is_entered_then_every_unit_becomes_a_uniquely_named_regiment(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)

        regiments = scene.battle.regiments
        self.assertEqual(self.loaded, [self.root / "FILE/SCRIPT/BF001.BTS"])
        self.assertEqual(sorted(regiments), ["Clanrat_Warriors", "Clanrat_Warriors#2", "Grudgebringer_Infantry"])
        infantry = regiments["Grudgebringer_Infantry"]
        self.assertEqual((infantry.models, infantry.ranks, infantry.side), (16, 4, Side.PLAYER))
        self.assertEqual(len(infantry.model_positions()), 16)

    def test_given_a_glue_battle_when_its_result_is_dismissed_then_its_same_runtime_resumes(self):
        self.context.glue = GlueContent.from_data(resources={
            "FLOW": "[RUN]\n[START]\nplaygame:bf001\nendgame:\n[END]",
        })
        glue = GlueScene("FLOW")
        machine = SceneMachine(glue, self.context)

        self.assertIsInstance(machine.active, BattleScene)
        self.assertIs(machine.active.glue_scene, glue)
        machine.active.battle.result = "victory"
        machine.update(0)
        self.assertIsInstance(machine.active, ResultScene)
        self.assertEqual(glue.take_effects(), ())  # still waiting on the battle request

        machine.handle("continue")
        machine.handle("done")  # the debrief screen closes

        self.assertIs(machine.active, glue)
        self.assertEqual(glue.take_effects(), (EndGame(),))

    def test_given_active_battle_when_a_quarter_second_passes_then_two_100_ms_ticks_have_run(self):
        scene = BattleScene()
        machine = SceneMachine(scene, self.context)

        for _ in range(25):
            machine.update(0.01)

        self.assertEqual(scene.battle.tick_count, 2)

    def test_given_battle_when_left_and_entered_again_then_its_battle_assets_were_released_and_reload(self):
        battle = BattleScene()
        machine = SceneMachine(LeaveScene(battle), self.context)
        machine.handle("return")

        machine.active.exit(self.context)
        machine.active.enter(self.context)

        self.assertEqual(len(self.loaded), 2)

    def test_given_a_click_on_a_player_regiment_when_selected_then_it_becomes_the_selection(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)

        scene.handle(("select", "Grudgebringer_Infantry"), self.context)

        self.assertEqual(scene.selected_id, "Grudgebringer_Infantry")

    def test_given_a_click_on_an_enemy_regiment_then_it_is_selected_for_inspection_only(self):
        # Selecting an enemy regiment is allowed (its HUD readout/banner/stats, same as a player
        # selection), but it must never be usable to issue it orders.
        scene = BattleScene()
        SceneMachine(scene, self.context)

        scene.handle(("select", "Clanrat_Warriors"), self.context)

        self.assertEqual(scene.selected_id, "Clanrat_Warriors")

        scene.handle(("move_to", 600.0, 600.0), self.context)

        self.assertIsNone(scene.battle.regiments["Clanrat_Warriors"].target_x)

    def test_given_a_selected_regiment_when_moved_to_a_ground_point_then_it_is_ordered_there(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)
        scene.handle(("select", "Grudgebringer_Infantry"), self.context)

        scene.handle(("move_to", 600.0, 600.0), self.context)

        regiment = scene.battle.regiments["Grudgebringer_Infantry"]
        self.assertEqual((regiment.target_x, regiment.target_y), (600.0, 600.0))

    def test_given_no_selection_when_a_ground_point_is_clicked_then_no_regiment_is_ordered(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)

        scene.handle(("move_to", 600.0, 600.0), self.context)

        for regiment in scene.battle.regiments.values():
            self.assertFalse(regiment.moving)

    def test_given_an_out_of_field_move_when_ordered_then_the_selection_stays_and_state_is_unchanged(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)
        scene.handle(("select", "Grudgebringer_Infantry"), self.context)
        regiment = scene.battle.regiments["Grudgebringer_Infantry"]
        before = (regiment.x, regiment.y, regiment.target_x, regiment.target_y)

        scene.handle(("move_to", -50.0, 600.0), self.context)

        self.assertEqual(scene.selected_id, "Grudgebringer_Infantry")
        self.assertEqual((regiment.x, regiment.y, regiment.target_x, regiment.target_y), before)

    def test_given_a_selection_when_deselected_then_a_later_ground_click_orders_nothing(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)
        scene.handle(("select", "Grudgebringer_Infantry"), self.context)

        scene.handle(("deselect",), self.context)
        scene.handle(("move_to", 600.0, 600.0), self.context)

        self.assertIsNone(scene.selected_id)
        self.assertFalse(scene.battle.regiments["Grudgebringer_Infantry"].moving)


    def test_given_a_selected_regiment_when_ordered_to_attack_an_enemy_then_it_is_charging(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)
        scene.handle(("select", "Grudgebringer_Infantry"), self.context)

        scene.handle(("attack", "Clanrat_Warriors"), self.context)

        regiment = scene.battle.regiments["Grudgebringer_Infantry"]
        self.assertEqual(regiment.attack_target, "Clanrat_Warriors")

    def test_given_a_moving_selected_regiment_when_halted_then_its_destination_is_cleared(self):
        scene = BattleScene()
        SceneMachine(scene, self.context)
        scene.handle(("select", "Grudgebringer_Infantry"), self.context)
        scene.handle(("move_to", 600.0, 600.0), self.context)

        scene.handle(("halt",), self.context)

        regiment = scene.battle.regiments["Grudgebringer_Infantry"]
        self.assertFalse(regiment.moving)

    def test_given_a_resolved_battle_when_updated_then_it_transitions_to_the_result_scene(self):
        scene = BattleScene()
        machine = SceneMachine(scene, self.context)
        for regiment in scene.battle.regiments.values():
            if regiment.side != Side.PLAYER:
                regiment.models = 0  # every enemy destroyed: the next tick must resolve to victory

        machine.update(BATTLE_TICK_SECONDS)

        self.assertIsInstance(machine.active, ResultScene)
        self.assertEqual(machine.active.result, "victory")
        self.assertTrue(machine.active.summary)

    def test_given_no_battle_mode_when_entered_then_it_settles_immediately_as_a_lossless_victory(self):
        self.context.no_battle = True
        scene = BattleScene()
        machine = SceneMachine(scene, self.context)

        machine.update(BATTLE_TICK_SECONDS)

        self.assertIsInstance(machine.active, ResultScene)
        self.assertEqual(machine.active.result, "victory")
        for line in machine.active.summary:
            if "Grudgebringer" in line:
                self.assertIn("16/16", line)  # no losses
            else:
                self.assertIn("0/", line)  # every enemy destroyed

    def test_given_no_battle_mode_when_reached_through_glue_then_it_resolves_back_into_the_campaign_flow(self):
        # The mode exists to walk the campaign quickly: the glue-triggered path (playgame -> battle
        # -> resume campaign script), not just the standalone-battle -> ResultScene -> main menu path.
        self.context.glue = GlueContent.from_data(resources={
            "FLOW": "[RUN]\n[START]\nplaygame:bf001\nendgame:\n[END]",
        })
        self.context.no_battle = True
        glue = GlueScene("FLOW")
        machine = SceneMachine(glue, self.context)
        self.assertIsInstance(machine.active, BattleScene)

        machine.update(BATTLE_TICK_SECONDS)

        self.assertIs(machine.active, glue)
        self.assertEqual(glue.take_effects(), (EndGame(),))

    def test_given_the_result_scene_when_dismissed_then_it_returns_to_the_main_menu(self):
        from whshr.campaign_scenes import MainMenuScene
        scene = ResultScene("victory", ["Player Regiment: 10/10 models"])
        machine = SceneMachine(scene, self.context)

        machine.handle("continue")
        machine.handle("done")  # the debrief screen closes

        self.assertIsInstance(machine.active, MainMenuScene)


if __name__ == "__main__":
    unittest.main()
