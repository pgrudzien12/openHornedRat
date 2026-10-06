"""Both native books open from direct and script-requested caravan windows."""

import unittest

from whshr.campaign_scenes import EncyclopediaScene, MagicBookScene
from whshr.campaign_state import CampaignState, caravan_window
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene


class _Context:
    def __init__(self, content):
        self.content = content

    def glue_content(self):
        return self.content


class CaravanBookRouteTests(unittest.TestCase):
    def setUp(self):
        self.modes = ("select", "resume", "recruit", "recruitnospeech", "infoLA", "infoLB",
                      "infoREA", "infoREC", "infoBMA", "infoBPC", "infoENA", "infoENE",
                      "infoSZA", "infoSZB", "infoWED")
        names = {"STARTCARAVAN", "START", "CARAVANDIETRICH", "CARAVANMS", "CARAVANECTS"}
        for mode in self.modes:
            names.add(caravan_window(mode))
            names.add(caravan_window(mode, True))
        window = ("[WINDOW]\n[POSITION]\nset:x=0\nset:y=0\nset:vx=640\nset:vy=480\n[END]\n"
                  "[HOTSPOT]\nset:x=0\nset:y=349\nset:vx=180\nset:vy=42\nres:EncyclopediaBook\n[END]\n"
                  "[HOTSPOT]\nset:x=0\nset:y=246\nset:vx=164\nset:vy=46\nres:MagicBook\n[END]\n")
        self.context = _Context(GlueContent.from_data(resources={name: window for name in names}))
        self.campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                      book_flags={0: {0, 6, 10, 21, 28}})

    def assert_books_open(self, scene):
        for target, expected in (("EncyclopediaBook", EncyclopediaScene), ("MagicBook", MagicBookScene)):
            with self.subTest(window=scene.require_runtime().state.windows[-1].name, target=target):
                transition = scene.handle(GlueInput("hotspot-release", target), self.context)
                self.assertIsInstance(transition.scene, expected)
                self.assertIs(transition.scene.handle("book:done", self.context).scene, scene)

    def test_direct_caravan_windows(self):
        for name in ("STARTCARAVAN", "START", "CARAVANDIETRICH", "CARAVANMS", "CARAVANECTS"):
            scene = GlueScene(window=name, campaign=self.campaign)
            scene.enter(self.context)
            self.assert_books_open(scene)

    def test_script_requested_caravan_modes_including_recruit_variants(self):
        for recruitable in (False, True):
            self.campaign.recruitable = lambda: recruitable
            for mode in self.modes:
                scene = GlueScene(window="STARTCARAVAN", campaign=self.campaign)
                scene.enter(self.context)
                scene.require_runtime().open_caravan(mode)
                with self.subTest(mode=mode, recruitable=recruitable):
                    self.assertEqual(scene.require_runtime().state.windows[-1].name,
                                     caravan_window(mode, recruitable))
                    self.assert_books_open(scene)


if __name__ == "__main__":
    unittest.main()
