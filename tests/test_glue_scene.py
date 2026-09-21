import unittest

from whshr.campaign_scenes import ArmyRecordsScene, TroopSelectionScene
from whshr.frontend.army_records_view import ArmyRecordsView
from whshr.campaign_state import CampaignState
from whshr.frontend.troop_selection_view import TroopSelectionView
from whshr.glue_content import GlueContent
from whshr.glue import MissionRef
from whshr.glue_runtime import ActivityResult, EndGame, GlueInput, OpenWindow, StartBattle, StartMovie, StopMusic
from whshr.glue_scene import GlueScene
from whshr.roster import Regiment, RosterRow
from whshr.scenes import SceneMachine, Transition


class _Context:
    def __init__(self, content):
        self.content = content

    def glue_content(self):
        return self.content


class GlueSceneTests(unittest.TestCase):
    def setUp(self):
        self.context = _Context(GlueContent.from_data(resources={
            "WINDOW": "[WINDOW]\n[POSITION]\nset:palindex=2\n[END]\n[END]",
            "FLOW": "[RUN]\n[START]\nopenwindow:res=WINDOW\nwaitforrelease:\nplaymovie:A2\nendgame:\n[END]",
            "BRIEFING": "[RUN]\n[START]\nwaitforrelease:\n[END]",
            "MAP": "[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n[MISSION]\nset:res=601\nres:BRIEFING\nsetbattlescript:BF001\ncash:1,100,50\n[END]",
            "MAP_FLOW": "[RUN]\n[START]\nopenwindow:res=MAP\nwaitforrelease:\n[END]",
            "STARTCARAVAN": "[WINDOW]\n[END]",
        }))

    def test_scene_owns_runtime_effects_across_input_and_activity_boundaries(self):
        # Driven directly through GlueScene rather than SceneMachine: a StartMovie effect here
        # is a request for the frontend to start a movie activity (SceneMachine routes it to a
        # MovieScene, notes/glue_engine_integration.md GEI6), not something this scene resolves
        # itself, so it stays queued for the host to take and act on.
        scene = GlueScene("flow")
        scene.enter(self.context)

        self.assertEqual(scene.take_effects(), (OpenWindow("WINDOW", None, 2),))
        scene.handle(GlueInput("mission-release"), self.context)
        movie = scene.take_effects()[0]
        self.assertIsInstance(movie, StartMovie)

        scene.handle(ActivityResult(movie.request_id, "movie"), self.context)
        self.assertEqual(scene.take_effects(), (EndGame(),))

    def test_snapshot_restore_is_available_at_scene_boundary(self):
        scene = GlueScene("FLOW")
        SceneMachine(scene, self.context)
        snapshot = scene.snapshot()
        scene.handle(GlueInput("mission-release"), self.context)

        scene.restore(snapshot)

        self.assertEqual(scene.runtime.state.wait_reason, "mission-release")

    def test_briefing_accept_without_a_campaign_skips_troop_selection_and_starts_the_battle(self):
        # notes/troop_selection.md §1.1: no company file skips the screen and runs Done immediately;
        # a development GlueScene has no CampaignState/company either.
        scene = GlueScene("BRIEFING", accept_battle="bf001")
        scene.enter(self.context)

        transition = scene.handle(GlueInput("panel-action", "open_troop_select"), self.context)
        self.assertIsInstance(transition.scene, TroopSelectionScene)
        selection = transition.scene
        selection.enter(self.context)
        self.assertEqual(selection.phase, "skip")

        done = selection.update(0, self.context)

        self.assertIs(done.scene, scene)
        effects = scene.take_effects()
        self.assertEqual(effects[0], StopMusic())
        self.assertIsInstance(effects[1], StartBattle)
        self.assertEqual(effects[1].battle, "BF001")

    def test_briefing_accept_with_a_campaign_opens_troop_selection_and_commits_on_done(self):
        commander = Regiment(2, "Grudgebringer Cavalry", True, 10, 10, 0,
                             RosterRow(2, keep=False, for_hire=False, wizard=False, artillery=False, base_price=8))
        reserve = Regiment(5, "Reserve", True, 10, 10, 0,
                           RosterRow(5, keep=False, for_hire=True, wizard=False, artillery=False, base_price=10))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP", coffers=500,
                                 company=(commander, reserve))
        map_scene = GlueScene("MAP_FLOW", campaign)
        machine = SceneMachine(map_scene, self.context)
        machine.handle(GlueInput("mission-select", "map.0"))
        machine.handle(GlueInput("panel-action", "open_briefing"))
        briefing_scene = machine.active
        self.assertIsInstance(briefing_scene, GlueScene)

        transition = briefing_scene.handle(GlueInput("panel-action", "accept_briefing"), self.context)
        self.assertIsInstance(transition.scene, TroopSelectionScene)
        selection = transition.scene
        selection.enter(self.context)
        self.assertEqual(selection.model.selection, [2])  # only the always-forced commander at open

        self.assertIsNone(selection.handle("done", self.context))  # P0 -> P1
        self.assertEqual(selection.phase, "march_order")
        done = selection.handle("done", self.context)

        self.assertIs(done.scene, briefing_scene)
        self.assertEqual(campaign.march_units, {2})
        self.assertEqual(campaign.army_units, {2, 5})
        self.assertEqual(campaign.coffers, 510)  # 500 + prepaid 100 - (commander 80 + reserve retainer 10)
        self.assertIn(map_scene.runtime.state.selected_mission, campaign.taken_missions)
        effects = briefing_scene.take_effects()
        self.assertIn(StopMusic(), effects)
        self.assertTrue(any(isinstance(e, StartBattle) and e.battle == "BF001" for e in effects))

    def test_bankrupt_troop_selection_opens_p5_and_only_done_can_leave_it(self):
        commander = Regiment(2, "Commander", True, 10, 10, 0,
                             RosterRow(2, keep=False, for_hire=False, wizard=False,
                                       artillery=False, base_price=100))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                 coffers=0, company=(commander,))
        parked = GlueScene("BRIEFING", campaign, accept_battle="bf001")
        parked.enter(self.context)
        selection = TroopSelectionScene(campaign, MissionRef("MAP", 0), "bf001", parked)

        selection.enter(self.context)

        self.assertEqual(selection.phase, "bankrupt")
        self.assertIsNone(selection.handle("abort", self.context))
        self.assertIsNone(selection.handle("toggle:2", self.context))
        self.assertIsNone(selection.handle("page:next", self.context))
        self.assertEqual(campaign.coffers, 0)
        self.assertEqual(parked.take_effects(), ())

    def test_bankruptcy_done_returns_to_the_parked_scene_without_starting_a_battle(self):
        commander = Regiment(2, "Commander", True, 10, 10, 0,
                             RosterRow(2, keep=False, for_hire=False, wizard=False,
                                       artillery=False, base_price=100))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                 coffers=0, company=(commander,))
        parked = GlueScene("BRIEFING", campaign, accept_battle="bf001")
        parked.enter(self.context)
        selection = TroopSelectionScene(campaign, MissionRef("MAP", 0), "bf001", parked)
        selection.enter(self.context)

        transition = selection.handle("done", self.context)

        self.assertIs(transition.scene, parked)
        self.assertEqual(campaign.coffers, 0)
        self.assertEqual(parked.take_effects(), ())

    def test_bankruptcy_view_uses_the_documented_copy_layout_and_done_only(self):
        commander = Regiment(2, "Commander", True, 10, 10, 0,
                             RosterRow(2, keep=False, for_hire=False, wizard=False,
                                       artillery=False, base_price=100))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                 coffers=25, company=(commander,))
        parked = GlueScene("BRIEFING", campaign)
        parked.enter(self.context)
        scene = TroopSelectionScene(campaign, MissionRef("MAP", 0), "bf001", parked)
        scene.enter(self.context)
        view = TroopSelectionView.__new__(TroopSelectionView)
        view.scene = scene
        view.body_font = type("Body", (), {"font": type("Font", (), {"height": 12})()})()
        view.heading_font = type("Heading", (), {"font": type("Font", (), {"height": 22})()})()
        labels, buttons = [], []
        view._string = lambda table, text_id, *args: (table, text_id, args)
        view._center = lambda value, y, colour, **kwargs: labels.append((value, y, colour, kwargs))
        view._button = lambda *args: buttons.append(args)

        view._p5()

        self.assertEqual(labels, [
            (("BKTXT", 601, ()), 146, (0, 0, 0), {"font": view.heading_font}),
            (("BKTXT", 602, (125,)), 168, (0, 0, 0), {}),
            (("BKTXT", 603, (1000,)), 180, (0, 0, 0), {}),
        ])
        self.assertEqual(buttons, [("done", 325, "GreenATab", 304, True)])

    def test_selection_view_refresh_builds_p0_buttons(self):
        view = TroopSelectionView.__new__(TroopSelectionView)
        view.scene = type("Scene", (), {
            "phase": "select", "page": 0, "march_offset": 0, "picked_whoami": None,
            "model": type("Model", (), {"selection": (), "total_cost": 0})(),
        })()
        view.state = None
        view.hover_march_index = view.pressed_button = None
        view._release_contents = lambda: None
        view._bitmap = lambda *_args: None
        called = []
        view._p0 = lambda: called.append("p0")
        view._buttons = lambda: called.append("buttons")

        view.refresh()

        self.assertEqual(called, ["p0", "buttons"])

    def test_army_records_button_enablement_follows_for_hire_not_selection_or_capacity(self):
        commander = Regiment(2, "Commander", True, 10, 10, 0,
                             RosterRow(2, keep=False, for_hire=False, wizard=False, artillery=False, base_price=10))
        recruit = Regiment(5, "Recruit", False, 10, 10, 0,
                           RosterRow(5, keep=False, for_hire=True, wizard=False, artillery=False, base_price=10))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                 coffers=1000, company=(commander, recruit))
        parked = GlueScene("BRIEFING", campaign, accept_battle="bf001")
        parked.enter(self.context)
        selection = TroopSelectionScene(campaign, MissionRef("MAP", 0), "bf001", parked)
        selection.enter(self.context)
        book = ArmyRecordsScene(selection, 5)
        view = ArmyRecordsView.__new__(ArmyRecordsView)
        view.scene = book

        self.assertTrue(view._enabled("book:hire-fire", recruit))
        self.assertFalse(view._enabled("book:hire-fire", commander))

    def test_army_records_left_page_shows_experience_and_normal_cost_for_an_unhired_regiment(self):
        recruit = Regiment(5, "Recruit", False, 10, 10, 13,
                           RosterRow(5, keep=False, for_hire=True, wizard=False, artillery=False, base_price=10),
                           experience=77)
        model = type("Model", (), {"hired": {5: False}})()
        view = ArmyRecordsView.__new__(ArmyRecordsView)
        view.scene = type("Scene", (), {"model": model})()
        view.body_font = type("Body", (), {"font": type("Font", (), {"height": 12})()})()
        view.heading_font = object()
        calls = []
        view._center = lambda value, *_args, **_kwargs: calls.append(value)
        view._center_bold = lambda value, *_args, **_kwargs: calls.append(value)
        view._label = lambda value, *_args: calls.append(value)
        view._string = lambda table, text_id, *args: (table, text_id, args)
        view._bitmap = lambda *_args: None
        view._bitmap_centered = lambda *_args, **_kwargs: None

        view._left_page(recruit)

        self.assertIn(("BKTXT", 501, (100, 10)), calls)
        self.assertIn(("BKTXT", 500, (77,)), calls)

    def test_closing_army_records_returns_to_the_same_selection_scene_and_keeps_its_page(self):
        company = tuple(Regiment(whoami, f"Unit {whoami}", True, 10, 10, 0,
                                 RosterRow(whoami, keep=False, for_hire=True, wizard=False,
                                           artillery=False, base_price=10))
                        for whoami in range(2, 9))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                 coffers=1000, company=company)
        parked = GlueScene("BRIEFING", campaign, accept_battle="bf001")
        parked.enter(self.context)
        selection = TroopSelectionScene(campaign, MissionRef("MAP", 0), "bf001", parked)
        selection.enter(self.context)
        selection.page = 1

        opened = selection.handle("book:8", self.context).scene
        self.assertIsInstance(opened, ArmyRecordsScene)
        opened.handle("book:hire-fire", self.context)
        returned = opened.handle("book:done", self.context)

        self.assertIs(returned.scene, selection)
        self.assertEqual(selection.page, 1)
        self.assertFalse(selection.model.hired[8])

    def test_aborting_army_records_restores_hired_flags_and_removes_cancelled_hires_from_selection(self):
        commander = Regiment(2, "Commander", True, 10, 10, 0,
                             RosterRow(2, keep=False, for_hire=False, wizard=False, artillery=False, base_price=10))
        recruit = Regiment(5, "Recruit", False, 10, 10, 0,
                           RosterRow(5, keep=False, for_hire=True, wizard=False, artillery=False, base_price=10))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                 coffers=1000, company=(commander, recruit))
        parked = GlueScene("BRIEFING", campaign, accept_battle="bf001")
        parked.enter(self.context)
        selection = TroopSelectionScene(campaign, MissionRef("MAP", 0), "bf001", parked)
        selection.enter(self.context)
        book = ArmyRecordsScene(selection, 5)
        book.handle("book:hire-fire", self.context)

        returned = book.handle("book:abort", self.context)

        self.assertIs(returned.scene, selection)
        self.assertFalse(selection.model.hired[5])
        self.assertNotIn(5, selection.model.selection)

    def test_troop_selection_pages_and_reorders_a_scrolled_marching_list(self):
        row = lambda whoami: RosterRow(whoami, keep=False, for_hire=True, wizard=False,
                                       artillery=False, base_price=10)
        company = tuple(Regiment(whoami, f"Unit {whoami}", True, 10, 10, 0, row(whoami))
                        for whoami in range(2, 10))
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="MAP",
                                 coffers=10_000, company=company)
        map_scene = GlueScene("MAP_FLOW", campaign)
        machine = SceneMachine(map_scene, self.context)
        machine.handle(GlueInput("mission-select", "map.0"))
        machine.handle(GlueInput("panel-action", "open_briefing"))
        selection = machine.active.handle(GlueInput("panel-action", "accept_briefing"), self.context).scene
        selection.enter(self.context)

        self.assertEqual(selection.page_count, 2)
        selection.handle("page:next", self.context)
        self.assertEqual(selection.page, 1)
        selection.handle("page:back", self.context)
        self.assertEqual(selection.page, 0)
        for whoami in range(3, 10):
            selection.handle(f"toggle:{whoami}", self.context)
        selection.handle("done", self.context)

        self.assertEqual(selection.phase, "march_order")
        selection.handle("scroll:down", self.context)
        self.assertEqual(selection.march_offset, 1)
        selection.handle("pickup:7", self.context)
        selection.handle("drop:0", self.context)
        self.assertEqual(selection.model.selection, [9, 2, 3, 4, 5, 6, 7, 8])

    def test_briefing_return_restores_its_configured_scene(self):
        return_scene = object()
        scene = GlueScene("BRIEFING", return_scene=return_scene)
        SceneMachine(scene, self.context)

        transition = scene.handle(GlueInput("panel-action", "return_to_caravan"), self.context)

        self.assertIsInstance(transition, Transition)
        self.assertIs(transition.scene, return_scene)

    def test_generic_map_brief_action_opens_the_selected_generic_briefing(self):
        map_scene = GlueScene("MAP_FLOW")
        machine = SceneMachine(map_scene, self.context)

        self.assertEqual(map_scene.runtime.state.selected_mission.key, "map.0")
        machine.handle(GlueInput("mission-select", "map.0"))
        machine.handle(GlueInput("panel-action", "open_briefing"))

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.program, "BRIEFING")
        self.assertEqual(machine.active.accept_battle, "BF001")
        self.assertIs(machine.active.return_scene, map_scene)

    def test_generic_start_caravan_hotspot_opens_its_flow_program(self):
        caravan = GlueScene(window="STARTCARAVAN")
        machine = SceneMachine(caravan, self.context)

        machine.handle(GlueInput("hotspot-release", "FLOW"))

        self.assertIsInstance(machine.active, GlueScene)
        self.assertEqual(machine.active.program, "FLOW")

    def test_generic_start_caravan_abort_returns_to_main_menu(self):
        from whshr.campaign_scenes import MainMenuScene

        caravan = GlueScene(window="STARTCARAVAN")
        machine = SceneMachine(caravan, self.context)

        transition = caravan.handle(GlueInput("hotspot-release", "AbortGame"), self.context)

        self.assertIsInstance(transition.scene, MainMenuScene)


if __name__ == "__main__":
    unittest.main()
