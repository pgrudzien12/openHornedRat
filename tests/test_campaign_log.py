"""BDD scenarios for the campaign session log (docs/testing.md), per notes/engine_architecture.md,
"Campaign session log". Headless: synthetic glue resources and scene stubs only."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest

from whshr.campaign_log import CampaignLogger, campaign_summary, default_log_path
from whshr.glue_content import GlueContent
from whshr.glue_runtime import ActivityResult, GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import Quit, Scene, SceneAssets, SceneMachine, Transition


class _Context:
    def __init__(self, content, log):
        self.content = content
        self.campaign_log = log

    def glue_content(self):
        return self.content


def _content():
    return GlueContent.from_data(resources={
        "MAIN": "[WINDOW]\n[POSITION]\nset:palindex=2\n[END]\n[BITMAP]\nsetbitmap:Backdrop\n[END]\n[END]",
        "LOOP": "[WINDOW]\n[BITMAP]\nsetbitmap:Cell\nset:animstartframe=1\nset:animstopframe=-1\n[END]\n[END]",
        "SUB": "[RUN]\n[START]\nopenwindow:res=MAIN\nwaitforrelease:\n[END]",
        "FLOW": "[RUN]\n[START]\nopenwindow:res=MAIN\nwaitforrelease:\ngosub:res=SUB\nplaymovie:A2\nendgame:\n[END]",
        "MOVIE": "[RUN]\n[START]\nopenwindow:res=MAIN\nwaitforrelease:\nplaymovie:A2\nendgame:\n[END]",
        "ANIM": "[RUN]\n[START]\nopenwindow:res=MAIN\nsetcurwindow:res=MAIN\naddanimobject:res=LOOP\nwaitforrelease:\n[END]",
        "BAD": "[RUN]\n[START]\ngosub:res=NOWHERE\nwaitforrelease:\n[END]",
    })


def _battle_stub(path):
    class _BattleStub(Scene):
        pass

    scene = _BattleStub()
    scene.battle_id = "vanilla:battle/bf001"
    scene.logger = SimpleNamespace(path=path)
    scene.battle = SimpleNamespace(result="victory")
    return scene


class CampaignLogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.dir = Path(self.temporary.name)
        self.path = default_log_path(self.dir / "logs")
        self.log = CampaignLogger(self.path)
        self.addCleanup(self.log.close)
        self.context = _Context(_content(), self.log)

    def rows(self, path=None):
        return [json.loads(line) for line in (path or self.path).read_text(encoding="utf-8").splitlines()]

    def test_scripted_walk_produces_ordered_rows(self):
        machine = SceneMachine(GlueScene("FLOW"), self.context)
        machine.handle(GlueInput("mission-release"))  # leaves the first wait, enters SUB via gosub

        rows = self.rows()
        self.assertEqual([row["type"] for row in rows][:3], ["scene_change", "glue_start", "script_enter"])
        load = next(row for row in rows if row["type"] == "screen_load")
        self.assertEqual((load["window"], load["program"], load["bitmaps"]), ("MAIN", "FLOW", ["Backdrop"]))
        self.assertEqual(load["location"].split(":")[0], "FLOW")
        pairs = [(row["type"], row.get("kind")) for row in rows]
        self.assertLess(pairs.index(("wait_started", "mission-release")),
                        pairs.index(("wait_resolved", "mission-release")))
        self.assertEqual([row["program"] for row in rows if row["type"] == "script_enter"], ["FLOW", "SUB"])
        self.assertTrue(all("time" in row for row in rows))

    def test_movie_request_is_one_row_started_and_one_resolved(self):
        scene = GlueScene("MOVIE")
        scene.enter(self.context)
        scene.handle(GlueInput("mission-release"), self.context)
        request = next(effect for effect in scene.take_effects() if type(effect).__name__ == "StartMovie")
        for _ in range(500):
            scene.update(0.04, self.context)
        scene.handle(ActivityResult(request.request_id, "movie"), self.context)

        movie = [row for row in self.rows() if row.get("kind") == "movie"]
        self.assertEqual([row["type"] for row in movie], ["activity_request", "wait_resolved"])

    def test_long_wait_and_animation_produce_bounded_rows(self):
        scene = GlueScene("ANIM")
        scene.enter(self.context)
        before = len(self.rows())
        for _ in range(20000):
            scene.update(0.016, self.context)

        self.assertEqual(len(self.rows()), before)
        self.assertLess(before, 8)

    def test_diagnostics_use_the_stderr_text(self):
        scene = GlueScene("BAD")
        scene.enter(self.context)

        diagnostic = next(row for row in self.rows() if row["type"] == "diagnostic")
        effect = next(effect for effect in scene.effects if type(effect).__name__ == "Diagnostic")
        self.assertEqual(diagnostic["text"], f"glue: {effect.location}: {effect.message}")

    def test_instruction_trace_is_opt_in(self):
        self.assertNotIn("glue_instruction", [row["type"] for row in self._walk_rows(False)])
        self.assertIn("glue_instruction", [row["type"] for row in self._walk_rows(True)])

    def _walk_rows(self, trace):
        path = self.dir / f"trace-{trace}.jsonl"
        log = CampaignLogger(path, trace_glue=trace)
        GlueScene("FLOW").enter(_Context(_content(), log))
        log.close()
        return self.rows(path)

    def test_campaign_state_change_is_logged_as_before_after(self):
        campaign = SimpleNamespace(coffers=100, flow="F", flow_step=0, mission_window=None, completed=set(),
                                   army_units=set(), march_units=set())
        scene = GlueScene("FLOW", campaign)
        scene.enter(self.context)
        campaign.coffers = 250
        scene.update(0.016, self.context)

        row = next(row for row in self.rows() if row["type"] == "campaign_state")
        self.assertEqual((row["before"]["coffers"], row["after"]["coffers"]), (100, 250))
        self.assertIsNone(campaign_summary(None))

    def test_battle_hand_off_points_at_the_battle_log(self):
        class Stub(Scene):
            pass

        machine = SceneMachine(Stub(), self.context)
        machine._apply(Transition(_battle_stub(Path("logs/b.jsonl")), "glue battle started"))
        machine._apply(Transition(Stub(), "glue battle resolved"))
        machine._apply(Quit("player quit"))

        rows = self.rows()
        start = next(row for row in rows if row["type"] == "battle_start")
        result = next(row for row in rows if row["type"] == "battle_result")
        self.assertEqual(start["battle_log"], str(Path("logs/b.jsonl")))
        self.assertEqual((result["battle_log"], result["result"]), (start["battle_log"], "victory"))
        self.assertEqual([row["to"] for row in rows if row["type"] == "scene_change"],
                         ["Stub", "_BattleStub", "Stub"])
        self.assertEqual(rows[-1]["type"], "quit")

    def test_disabled_or_unwritable_log_changes_nothing_and_never_raises(self):
        blocker = self.dir / "file"
        blocker.write_text("x")
        outcomes = []
        for log in (None, CampaignLogger(None), CampaignLogger(blocker / "sub" / "c.jsonl")):
            scene = GlueScene("FLOW")
            machine = SceneMachine(scene, _Context(_content(), log))
            machine.handle(GlueInput("mission-release"))
            outcomes.append((scene.take_effects(), scene.runtime.state.wait_reason))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])
        self.assertFalse(CampaignLogger(blocker / "sub" / "c.jsonl").enabled)

    def test_failed_asset_load_is_logged_and_still_raises(self):
        class Catalog:
            def get(self, identifier):
                raise KeyError(identifier)

        assets = SceneAssets(None, Catalog(), None, {}, campaign_log=self.log)
        with self.assertRaises(KeyError):
            assets.load("vanilla:missing/thing")
        self.assertEqual([row["type"] for row in self.rows()], ["asset_failed"])


if __name__ == "__main__":
    unittest.main()
