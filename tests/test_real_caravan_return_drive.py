"""Real-installation validation (skipped without WARFB): after the first mission's caravan, the map's Caravan
button returns to that same caravan window, and its Dietrich hotspot speaks its click speech (issue #124)."""
import os
import tempfile
import unittest
from pathlib import Path

from whshr.campaign_scenes import TroopSelectionScene
from whshr.campaign_state import CampaignState
from whshr.game import scene_context
from whshr.glue_render import build_render_model
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneMachine

WARFB = os.environ.get("WARFB")


@unittest.skipUnless(WARFB and Path(WARFB).is_dir(), "WARFB is not set")
class RealCaravanReturnDriveTests(unittest.TestCase):
    def test_given_the_first_caravan_when_the_map_caravan_button_is_pressed_then_the_same_caravan_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory)
            context = scene_context(WARFB, save_dir=save_dir, no_battle=True)
            campaign = CampaignState.from_installation(context.locator.installation, context.glue)
            map_scene = GlueScene(campaign.flow, campaign)
            machine = SceneMachine(map_scene, context)
            machine.handle(GlueInput("panel-action", "open_troop_select"))
            caravan = None
            for _ in range(6000):
                if isinstance(machine.active, TroopSelectionScene):
                    machine.handle("done")
                active = machine.active
                state = active.runtime.state if isinstance(active, GlueScene) else None
                if state is not None and state.pending is not None and state.pending.kind == "caravan":
                    caravan = active
                    break
                machine.update(0.1)
            self.assertIsNotNone(caravan)
            window = caravan.runtime.state.windows[-1].name
            machine.handle(GlueInput("hotspot-release", "UnwindMission"))
            self.assertIs(machine.active, map_scene)

            machine.handle(GlueInput("panel-action", "return_to_caravan"))

            self.assertIs(machine.active, caravan)
            self.assertEqual(caravan.runtime.state.windows[-1].name, window)
            print("map Caravan button -> active window:", window)
            model = build_render_model(context.glue, caravan.runtime.state.windows[-1])
            speech = [(h.click_text, h.click_count) for h in model.hotspots if h.click_text is not None]
            self.assertTrue(speech)
            for text_id, count in speech:
                print("click speech", text_id, [context.glue.string("BRTXT", text_id + i) for i in range(count)])


if __name__ == "__main__":
    unittest.main()
