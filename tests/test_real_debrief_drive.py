"""Real-installation validation (skipped without WARFB): the first Chapter-1 missions played in no-battle mode
reach the end of the Patrol mission, whose debrief request resolves and lets the flow go on (issue #124).
Manual/regression check, not a fixture: the game files are read from the user's own installation."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from whshr.campaign_log import CampaignLogger
from whshr.campaign_scenes import TroopSelectionScene
from whshr.campaign_state import CampaignState
from whshr.game import scene_context
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneMachine

WARFB = os.environ.get("WARFB")


@unittest.skipUnless(WARFB and Path(WARFB).is_dir(), "WARFB is not set")
class RealDebriefDriveTests(unittest.TestCase):
    def test_given_the_first_missions_in_no_battle_mode_when_patrol_ends_then_the_debrief_resolves_and_the_flow_goes_on(self):
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory)
            context = scene_context(WARFB, save_dir=save_dir, no_battle=True)
            log_path = save_dir / "log.jsonl"
            context.campaign_log = CampaignLogger(log_path)
            self.addCleanup(context.campaign_log.close)
            campaign = CampaignState.from_installation(context.locator.installation, context.glue, save_dir=save_dir)
            map_scene = GlueScene(campaign.flow, campaign)
            machine = SceneMachine(map_scene, context)

            for _ in range(5):
                machine.handle(GlueInput("panel-action", "open_troop_select"))
                for _ in range(30):
                    if isinstance(machine.active, TroopSelectionScene):
                        machine.handle("done")
                    machine.update(0.1)
                for _ in range(6000):
                    active = machine.active
                    if active is map_scene:
                        break
                    state = active.runtime.state if isinstance(active, GlueScene) else None
                    if state is not None and state.pending is not None and state.pending.kind == "caravan":
                        machine.handle(GlueInput("hotspot-release", "UnwindMission"))
                    elif state is not None and state.wait_reason == "panel-resume" and state.pending is None:
                        machine.handle(GlueInput("panel-action", "encounter_battle"))
                    else:
                        machine.update(0.1)
                self.assertIs(machine.active, map_scene)

            context.campaign_log.close()
            rows = [json.loads(line) for line in log_path.read_text().splitlines()]
            debriefs = [row for row in rows if row["type"] == "debrief"]
            self.assertEqual([(row["mode"], row["summary"]) for row in debriefs], [(7, True)])
            self.assertTrue(any("bonusadd" in row.get("text", "") for row in rows if row["type"] == "diagnostic"))
            self.assertFalse([row for row in rows if row["type"] == "diagnostic" and "unsupported command" in row["text"]
                              and any(name in row["text"] for name in ("bonus", "testobjective", "addunit"))])
            self.assertEqual(map_scene.runtime.state.pending, None)


if __name__ == "__main__":
    unittest.main()
