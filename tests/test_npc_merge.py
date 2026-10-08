"""Allied NPC regiments in G and I battles (notes/allied_npc_merge.md, test vectors of section 7)."""

import unittest
from types import SimpleNamespace

from whshr import npc_merge
from whshr.battle_scene import BattleScene
from whshr.engine import Battle
from whshr.rules import Side

NPC_SIDE = 0x40


def unit(identifier, whoami, models, side=0, x=-10, y=-20, exp=None, **extra):
    position = {"x": x, "y": y, "dir": 17, "whoami": whoami, "hired": 1}
    if exp is not None:
        position["s_Exp"] = exp
    return {"id": identifier, "name": identifier, "hidden": False, "sprites": None,
            "set": position, "stats": {"s_side": [side, models, models, 1]}, **extra}


def source(objectives, npcs, player=(), enemies=()):
    armies = [{"count": len(npcs), "units": npcs}]
    if enemies:
        armies.append({"count": len(enemies), "units": list(enemies)})
    return {"field": {"width": 1000, "height": 1000},
            "mission": {"deploy_troops": False, "objectives": objectives}, "armies": armies,
            "merc": {"armies": [{"count": len(player), "units": list(player)}]},
            "nodes": [{"x": 100 + i * 100, "y": 200 + i * 100, "dir": 64 + i, "id": 0, "radius": 100,
                       "status": ["ns_ACTIVE", "NS_STARTPOS"]} for i in range(5)]}


def company_unit(whoami, models, name, exp):
    return unit(f"Company{whoami}", whoami, models, exp=exp) | {"name": name}


class ArmyMergeTests(unittest.TestCase):
    """Objective G (BF015/BF017): vectors 1, 2 and 7."""

    def build(self, company, player=(), npcs=None, objectives=(("G", 1, 4),)):
        npcs = npcs if npcs is not None else [
            unit("NPC_Cavalry", 2, 12, NPC_SIDE, x=500, y=500), unit("NPC_Avengers", 4, 28, NPC_SIDE, x=600, y=600),
            unit("NPC_Crossbows", 27, 10, NPC_SIDE, x=700, y=700), unit("NPC_Caravan", 100, 2, NPC_SIDE)]
        return Battle.from_script(source([list(o) for o in objectives], npcs, player), company=company)

    def test_given_a_marching_regiment_then_its_npc_is_deleted_and_a_company_regiment_merges_at_current_strength(self):
        company = {2: company_unit(2, 9, "Grudgebringer Cavalry", 77), 4: company_unit(4, 20, "Black Avengers", 150)}
        battle = self.build(company, player=[unit("Cavalry", 2, 9)])

        self.assertNotIn("NPC_Cavalry", battle.regiments)  # the regiment marches: only the player's own unit fights
        avengers = battle.regiments["NPC_Avengers"]
        self.assertEqual((avengers.models, avengers.name, avengers.side), (20, "Black Avengers", Side.NEUTRAL))
        self.assertEqual((avengers.x, avengers.y, avengers.whoami), (600, 600, 4))  # position and whoami from the script

    def test_given_a_regiment_outside_the_company_then_its_npc_is_deleted_and_story_units_are_untouched(self):
        battle = self.build({4: company_unit(4, 20, "Black Avengers", 150)})

        self.assertNotIn("NPC_Crossbows", battle.regiments)
        self.assertIn("NPC_Caravan", battle.regiments)  # whoami 100 is a story unit

    def test_given_a_wiped_out_company_regiment_then_the_merged_npc_is_removed(self):
        battle = self.build({4: company_unit(4, 0, "Black Avengers", 150)})

        self.assertNotIn("NPC_Avengers", battle.regiments)

    def test_given_g_with_a_zero_first_value_or_no_g_then_npcs_keep_their_script_values(self):
        for objectives in ((("G", 0, 4),), (("A", 1, 0),)):
            with self.subTest(objectives=objectives):
                battle = self.build({4: company_unit(4, 20, "Black Avengers", 150)}, objectives=objectives)
                self.assertEqual(battle.regiments["NPC_Avengers"].models, 28)
                self.assertIn("NPC_Crossbows", battle.regiments)

    def test_given_an_npc_without_a_whoami_line_then_it_is_left_alone(self):
        stray = unit("NPC_Stray", 0, 6, NPC_SIDE)
        del stray["set"]["whoami"]
        battle = self.build({0: company_unit(0, 18, "Vannheim's 75th", 5)}, npcs=[stray])

        self.assertEqual(battle.regiments["NPC_Stray"].models, 6)


class ArtillerySwapTests(unittest.TestCase):
    """Objective I (BF029): vectors 5 and 6."""

    def test_given_a_marching_crew_then_the_npc_takes_its_place_and_the_player_unit_is_removed(self):
        npcs = [unit("NPC_Cannon", 15, 2, NPC_SIDE, x=0, y=0), unit("NPC_Great_Cannon", 14, 2, NPC_SIDE),
                unit("NPC_Bright_Wizard", 119, 1, NPC_SIDE)]
        crew = unit("Cannon_Crew", 15, 4, x=300, y=200)
        battle = Battle.from_script(source([["I", 1, 4]], npcs, [crew]))

        self.assertNotIn("Cannon_Crew", battle.regiments)
        cannon = battle.regiments["NPC_Cannon"]
        self.assertEqual((cannon.models, cannon.side), (2, Side.NEUTRAL))
        self.assertEqual((cannon.x, cannon.y), (500, 600))  # the player unit's deployment slot (last node), not the script's (0, 0)
        self.assertNotIn("NPC_Great_Cannon", battle.regiments)  # the player did not march it
        self.assertIn("NPC_Bright_Wizard", battle.regiments)  # whoami 119 is untouched


class WriteBackTests(unittest.TestCase):
    """Vectors 3, 4 and 8: the NPCs of a G or I battle go back to the campaign like player regiments."""

    def play(self, objectives, models_after, fled=False):
        npc = unit("NPC_Avengers", 4, 28, NPC_SIDE)
        company = {4: company_unit(4, 20, "Black Avengers", 150)}
        scene = BattleScene()
        scene.battle = Battle.from_script(source(objectives, [npc, unit("NPC_Peasant", 119, 4, NPC_SIDE)]), company=company)
        scene.initial_models = {key: regiment.models for key, regiment in scene.battle.regiments.items()}
        regiment = scene.battle.regiments["NPC_Avengers"]
        regiment.models, regiment.fled, regiment.kills, regiment.experience_gained = models_after, fled, 3, 40
        return scene, scene._npc_outcomes()

    def test_given_a_surviving_merged_npc_then_it_is_written_with_its_raw_counters(self):
        scene, outcomes = self.play([["G", 1, 4]], 15)

        self.assertEqual(list(scene.battle.npc_regiments.values()), [4])  # whoami 119 is never written
        outcome = outcomes[4]
        self.assertEqual((outcome.models, outcome.routed, outcome.casualties, outcome.kills, outcome.experience_gained),
                         (15, 0, 5, 3, 40))  # 20 at the start, 15 left

    def test_given_a_wiped_out_npc_then_its_casualties_are_reset_to_zero(self):
        _, outcomes = self.play([["G", 1, 4]], 0)

        self.assertEqual((outcomes[4].models, outcomes[4].casualties), (0, 0))

    def test_given_a_fled_npc_then_its_routed_models_are_kept_and_its_casualties_reset(self):
        _, outcomes = self.play([["G", 1, 4]], 12, fled=True)

        self.assertEqual((outcomes[4].models, outcomes[4].routed, outcomes[4].casualties), (0, 12, 0))

    def test_given_a_battle_without_g_or_i_then_no_npc_is_written(self):
        scene, outcomes = self.play([["A", 1, 0]], 15)

        self.assertEqual((scene.battle.npc_regiments, outcomes), ({}, {}))

    def test_given_g_defined_with_a_zero_value_then_npcs_are_written_without_being_merged(self):
        scene, outcomes = self.play([["G", 0, 4]], 20)

        self.assertEqual(list(scene.battle.npc_regiments.values()), [4])
        self.assertEqual(scene.initial_models["NPC_Avengers"], 28)  # script strength, no merge
        self.assertEqual(outcomes[4].casualties, 8)


class HelperTests(unittest.TestCase):
    def test_objective_value_reads_the_first_value_or_none_when_undefined(self):
        listing = [["G", 1, 4], ["a", 3]]
        self.assertEqual((npc_merge.objective_value(listing, "G"), npc_merge.objective_value(listing, "A")), (1, 3))
        self.assertIsNone(npc_merge.objective_value(listing, "I"))
        self.assertIsNone(npc_merge.objective_value(None, "G"))


if __name__ == "__main__":
    unittest.main()
