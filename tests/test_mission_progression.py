"""Mission list progression (GEI10): depend / inactivedepend on generic rows, list rebuilt after commitment."""
import copy
import importlib.util
import os
import unittest
from pathlib import Path

from whshr.campaign_state import CampaignState, offered_refs
from whshr.glue import MissionRecord, MissionRef
from whshr.glue_content import GlueContent
from whshr.glue_runtime import GlueInput
from whshr.glue_scene import GlueScene
from whshr.scenes import SceneMachine

# Two chapters whose windows reuse the same mission name ids (601/602), as the real windows do.
CHAPTER_A = ("[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
             "[MISSION]\nset:res=601\nres:BRIEFING\nsetbattlescript:BF001\n[END]\n"
             "[MISSION]\nset:res=602\nset:depend=601\nres:BRIEFING\nsetbattlescript:BF002\n[END]\n"
             "[MISSION]\nset:res=603\nset:inactivedepend=602\nres:BRIEFING\nsetbattlescript:BF003\n[END]")
CHAPTER_B = ("[WINDOW]\n[MISSIONWINDOW]\nset:x=30\nset:y=15\n[END]\n"
             "[MISSION]\nset:res=601\nres:BRIEFING\nsetbattlescript:BF004\n[END]\n"
             "[MISSION]\nset:res=602\nres:BRIEFING\nsetbattlescript:BF005\n[END]")


def _records(content, name):
    return [r for r in content.window(name).records if isinstance(r, MissionRecord)]


def _refs(window, *indices):
    return tuple(MissionRef(window, i) for i in indices)


class OfferedListTests(unittest.TestCase):
    def setUp(self):
        self.content = GlueContent.from_data(resources={"A": CHAPTER_A, "B": CHAPTER_B})

    def test_given_no_mission_taken_then_only_ungated_rows_and_open_inactive_gates_are_offered(self):
        self.assertEqual(offered_refs(_records(self.content, "A"), ()), _refs("A", 0, 2))

    def test_given_the_dependency_is_taken_then_the_dependent_row_appears_and_the_inactive_gate_hides(self):
        taken = {MissionRef("A", 0)}
        self.assertEqual(offered_refs(_records(self.content, "A"), taken), _refs("A", 1))

    def test_given_the_dependent_is_taken_too_then_the_inactive_gate_opens_again(self):
        taken = {MissionRef("A", 0), MissionRef("A", 1)}
        self.assertEqual(offered_refs(_records(self.content, "A"), taken), _refs("A", 2))

    def test_given_the_same_name_id_in_another_chapter_then_taking_it_there_does_not_hide_this_window(self):
        taken = {MissionRef("A", 0)}
        self.assertEqual(offered_refs(_records(self.content, "B"), taken), _refs("B", 0, 1))


class MapListRebuildTests(unittest.TestCase):
    def setUp(self):
        self.content = GlueContent.from_data(resources={
            "A": CHAPTER_A, "B": CHAPTER_B, "BRIEFING": "[RUN]\n[START]\nwaitforrelease:\n[END]",
            "A_FLOW": "[RUN]\n[START]\nopenwindow:res=A\nwaitforrelease:\n[END]",
            "B_FLOW": "[RUN]\n[START]\nopenwindow:res=B\nwaitforrelease:\n[END]",
        })

        class Context:
            def glue_content(inner):
                return self.content
        self.context = Context()

    def _map(self, window, flow):
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window=window,
                                 content=self.content)
        scene = GlueScene(flow, campaign)
        machine = SceneMachine(scene, self.context)
        return campaign, scene, machine

    def test_given_a_gated_row_then_it_cannot_be_selected_until_its_dependency_is_taken(self):
        campaign, scene, _ = self._map("A", "A_FLOW")
        scene.handle(GlueInput("mission-select", "a.1"), self.context)
        self.assertEqual(scene.runtime.state.selected_mission, MissionRef("A", 0))  # first offered row kept

        campaign.mark_mission_taken(MissionRef("A", 0))
        scene.handle(GlueInput("mission-select", "a.1"), self.context)
        self.assertEqual(scene.runtime.state.selected_mission, MissionRef("A", 1))

    def test_given_a_briefing_aborted_before_commitment_then_the_mission_stays_offered_and_selected(self):
        campaign, scene, machine = self._map("A", "A_FLOW")
        selected = scene.runtime.state.selected_mission
        machine.handle(GlueInput("panel-action", "open_briefing"))
        machine.handle(GlueInput("panel-action", "abort_briefing"))

        self.assertIs(machine.active, scene)
        self.assertEqual(campaign.taken_missions, set())
        self.assertEqual(scene.runtime.state.selected_mission, selected)
        self.assertEqual(offered_refs(_records(self.content, "A"), campaign.taken_missions), _refs("A", 0, 2))

    def test_given_a_committed_mission_when_the_map_is_resumed_then_the_list_is_rebuilt_and_reselected(self):
        campaign, scene, _ = self._map("A", "A_FLOW")
        self.assertEqual(scene.runtime.state.selected_mission, MissionRef("A", 0))

        campaign.mark_mission_taken(MissionRef("A", 0))   # committed at troop selection, not yet finished
        scene.runtime.refresh_selection()

        self.assertEqual(scene.runtime.state.selected_mission, MissionRef("A", 1))
        self.assertEqual(campaign.selected_mission, MissionRef("A", 1))

    def test_given_two_chapters_then_a_commitment_only_changes_the_window_it_belongs_to(self):
        campaign, scene, _ = self._map("B", "B_FLOW")
        campaign.mark_mission_taken(MissionRef("A", 0))
        scene.runtime.refresh_selection()
        self.assertEqual(scene.runtime.state.selected_mission, MissionRef("B", 0))
        campaign.mark_mission_taken(MissionRef("B", 0))
        scene.runtime.refresh_selection()
        self.assertEqual(scene.runtime.state.selected_mission, MissionRef("B", 1))

    def test_given_no_campaign_then_every_row_stays_selectable_ungated(self):
        scene = GlueScene("A_FLOW")
        SceneMachine(scene, self.context)
        scene.handle(GlueInput("mission-select", "a.1"), self.context)
        self.assertEqual(scene.runtime.state.selected_mission, MissionRef("A", 1))

    @unittest.skipUnless(importlib.util.find_spec("pygame"), "Pygame is not installed")
    def test_given_a_campaign_then_the_view_rows_follow_the_same_gates(self):
        from whshr.frontend.glue_view import _mission_rows
        from whshr.glue_render import GlueRenderModel, RenderMissionList
        model = GlueRenderModel("A", 0, 0, 640, 480, 0, (), (), (), (), (),
                                (RenderMissionList(0, 0, _refs("A", 0, 1, 2)),))
        rows = _mission_rows(self.content, (model,), None, {MissionRef("A", 0)})
        self.assertEqual([row[0] for row in rows], list(_refs("A", 1)))
        self.assertEqual(len(_mission_rows(self.content, (model,), None)), 3)  # no campaign: ungated


class FlowAdvanceTests(unittest.TestCase):
    def test_given_finished_ids_in_another_window_then_this_window_still_counts_as_offering_rows(self):
        content = GlueContent.from_data(resources={"A": CHAPTER_A, "B": CHAPTER_B})
        graph = {"flow_scripts": {"F": ({"action": "add_window", "window": "B"},
                                        {"action": "add_window", "window": "A"})},
                 "mission_windows": {"B": [], "A": []}}
        campaign = CampaignState(graph, flow="F", mission_window="B", content=content)
        campaign.completed.update({601, 602})  # name ids finished in another window
        campaign.taken_missions.add(MissionRef("A", 0))
        self.assertTrue(campaign._anything_offered())

    def test_given_every_row_of_the_window_is_taken_then_nothing_is_offered(self):
        content = GlueContent.from_data(resources={"B": CHAPTER_B})
        campaign = CampaignState({"flow_scripts": {}, "mission_windows": {}}, mission_window="B", content=content)
        campaign.taken_missions.update(_refs("B", 0, 1))
        self.assertFalse(campaign._anything_offered())


def _installation_root():
    return os.environ.get("WHSHR_INSTALLATION") or os.environ.get("WARFB")


@unittest.skipUnless(_installation_root(), "set WHSHR_INSTALLATION or WARFB for the original-install walk")
class OriginalFlowsTests(unittest.TestCase):
    def test_given_every_flow_then_walking_any_eligible_mission_never_leaves_an_empty_or_stuck_map(self):
        start = CampaignState.from_installation(Path(_installation_root()))
        content, graph = start.content, start.graph

        def offered(state):
            return state.offered_missions(_records(content, state.mission_window))

        def snapshot(state):
            clone = copy.copy(state)
            clone.flow_history = list(state.flow_history)
            clone.completed = set(state.completed)
            clone.taken_missions = set(state.taken_missions)
            return clone

        seen, problems = set(), []

        def walk(state, path):
            if not offered(state):
                problems.append(("empty", state.flow, state.mission_window, path))
                return
            key = (state.flow, state.flow_step,
                   frozenset(r for r in state.taken_missions if r.window == state.mission_window.upper()))
            if key in seen or len(path) > 40:
                return
            seen.add(key)
            for ref in offered(state):
                nxt = snapshot(state)
                replacement, released = nxt.complete_mission(ref)
                if replacement or not released:
                    walk(nxt, path + [ref.key])
                # released with no later window: the chapter's flow script runs on to its end

        for flow in graph["flow_scripts"]:
            state = snapshot(start)
            state.flow, state.flow_history = flow, [flow]
            state._open_next_window(0)
            walk(state, [flow])

        self.assertEqual(problems, [])
        self.assertGreater(len(seen), 20)

    def test_given_the_gated_windows_then_the_notes_rules_hold_for_taken_sets(self):
        start = CampaignState.from_installation(Path(_installation_root()))
        windows = start.graph["mission_windows"]
        gated = [name for name, missions in windows.items()
                 if any(m.get("depend") or m.get("inactivedepend") for m in missions)]
        self.assertGreaterEqual(len(gated), 3)
        for name in gated:
            records = _records(start.content, name)
            refs_by_id = {m["name_id"]: m["mission_ref"] for m in windows[name]}
            for mission in windows[name]:
                depend = mission.get("depend")
                if depend in refs_by_id:
                    self.assertNotIn(mission["mission_ref"], offered_refs(records, ()))
                    self.assertIn(mission["mission_ref"], offered_refs(records, {refs_by_id[depend]}))
                elif depend:  # a gate on a mission outside the window is a no-op
                    self.assertIn(mission["mission_ref"], offered_refs(records, ()))


if __name__ == "__main__":
    unittest.main()
