"""Engine difficulty levels (whshr.difficulty): an engine extension; Commander keeps the original rules."""

import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

from whshr import casualties, combat, difficulty, magic, ranged, spell_effects
from whshr.difficulty import COMMANDER, SERGEANT, SOLDIER, difficulty_setting
from whshr.engine import Battle, Regiment as BattleRegiment
from whshr.options_scene import OptionsScene
from whshr.rules import Side
from whshr.scenes import Scene
from whshr.troop_selection import STATUS_DESTROYED, TroopSelection
from whshr.savegame import campaign_to_dict, restore_campaign
from tests.test_casualties import _battle, _campaign, _models, _regiment


class LevelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(difficulty_setting.configure, None)

    def test_given_each_level_then_prices_and_reinforcements_scale_by_its_percentages(self):
        self.assertEqual([level.price(1000) for level in (COMMANDER, SERGEANT, SOLDIER)], [1000, 900, 800])
        self.assertEqual([level.reinforcements(5) for level in (COMMANDER, SERGEANT, SOLDIER)], [5, 7, 10])
        self.assertEqual(SERGEANT.reinforcements(1), 1)  # 1.4, rounded half up
        self.assertEqual(SERGEANT.reinforcements(4), 6)  # 5.6

    def test_given_a_saved_level_then_it_survives_reconfiguring_and_a_bad_file_means_commander(self):
        with tempfile.TemporaryDirectory() as directory:
            difficulty_setting.configure(directory)
            self.assertIs(difficulty.current(), COMMANDER)
            difficulty_setting.save(SOLDIER)
            difficulty_setting.configure(directory)
            self.assertIs(difficulty.current(), SOLDIER)
            (Path(directory) / "difficulty.json").write_text('{"difficulty": "nightmare"}')
            difficulty_setting.configure(directory)
            self.assertIs(difficulty.current(), COMMANDER)

    def test_given_the_options_window_then_ok_saves_the_cycled_level_and_cancel_drops_it(self):
        with tempfile.TemporaryDirectory() as directory:
            context = mock.Mock(save_dir=Path(directory))
            scene = OptionsScene(Scene())
            scene.enter(context)
            scene.handle(("options:cycle", "difficulty"), context)  # Commander wraps round to Soldier
            self.assertIs(scene.difficulty, SOLDIER)
            scene.handle("options:ok", context)
            self.assertEqual(json.loads((Path(directory) / "difficulty.json").read_text()), {"difficulty": "soldier"})
            scene = OptionsScene(Scene())
            scene.enter(context)
            scene.handle(("options:cycle", "difficulty"), context)
            scene.handle("options:cancel", context)
            self.assertIs(difficulty.current(), SOLDIER)


class CampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(difficulty_setting.configure, None)

    def test_given_an_easier_level_then_prices_follow_the_level_set_now(self):
        regiment = _regiment(5, models=10)  # 8 crowns a model
        self.assertEqual((regiment.price, regiment.retainer), (80, 8))
        difficulty_setting.save(SERGEANT)
        self.assertEqual((regiment.price, regiment.retainer), (72, 7))
        difficulty_setting.save(SOLDIER)
        self.assertEqual(TroopSelection([regiment], coffers=1000).row(5).price, 64)

    def test_given_an_easier_level_then_a_reinforcement_grant_is_scaled_when_made(self):
        campaign = _campaign(_regiment(5, models=10))
        difficulty_setting.save(SOLDIER)
        campaign.add_reinforcements(5, 3)
        difficulty_setting.save(COMMANDER)
        campaign.add_reinforcements(5, 3)
        self.assertEqual(campaign.reinforcements[5], 9)

    def wiped_out(self) -> object:
        campaign = _campaign(_regiment(2, models=10), _regiment(5, models=10))
        _battle(campaign, r5=(0, 0, 10))  # 10 lost: 6 wounded, 4 dead
        return campaign

    def test_given_commander_then_a_wiped_out_regiment_with_wounded_is_disbanded(self):
        campaign = self.wiped_out()
        casualties.heal_and_disband(campaign)  # type: ignore[arg-type]
        self.assertNotIn(5, {regiment.whoami for regiment in campaign.company})  # type: ignore[attr-defined]

    def test_given_soldier_then_it_is_kept_and_sits_out_the_next_battle_even_when_reinforced(self):
        difficulty_setting.save(SOLDIER)
        campaign = self.wiped_out()
        disbanded = casualties.heal_and_disband(campaign)[1]  # type: ignore[arg-type]
        self.assertEqual(disbanded, [])
        self.assertEqual(_models(campaign, 5), 0)
        self.assertEqual(campaign.sitting_out, {5})  # type: ignore[attr-defined]
        reinforced = [casualties.roster.with_models(regiment, 4) if regiment.whoami == 5 else regiment
                      for regiment in campaign.company]  # type: ignore[attr-defined]
        selection = TroopSelection(reinforced, coffers=1000, sitting_out=campaign.sitting_out)  # type: ignore[attr-defined]
        self.assertEqual(selection.status(5), STATUS_DESTROYED)
        self.assertFalse(selection.toggleable(5))
        campaign.commit_troop_selection(selection.confirm())  # type: ignore[attr-defined]
        self.assertEqual(campaign.sitting_out, set())  # type: ignore[attr-defined]

    def test_given_a_regiment_sitting_out_then_a_save_keeps_it(self):
        difficulty_setting.save(SOLDIER)
        campaign = self.wiped_out()
        casualties.heal_and_disband(campaign)  # type: ignore[arg-type]
        restored = _campaign(_regiment(2, models=10), _regiment(5, models=10))
        restore_campaign(restored, campaign_to_dict(campaign))  # type: ignore[arg-type]
        self.assertEqual(restored.sitting_out, {5})

    def test_given_soldier_then_a_wiped_out_regiment_without_wounded_is_still_disbanded(self):
        difficulty_setting.save(SOLDIER)
        campaign = _campaign(_regiment(2, models=10), _regiment(5, models=1))
        _battle(campaign, r5=(0, 0, 1))  # 1 lost: 0 wounded
        casualties.heal_and_disband(campaign)
        self.assertNotIn(5, {regiment.whoami for regiment in campaign.company})


def unit(identifier: str, side: Side, ws: int = 3, bs: int = 3) -> BattleRegiment:
    return BattleRegiment(identifier, identifier, 50, 50, 0, side, models=5, ws=ws, bs=bs)


class BattleTests(unittest.TestCase):
    def test_given_soldier_then_player_regiments_fight_with_one_more_ws_without_changing_the_profile(self):
        player, enemy = unit("P", Side.PLAYER), unit("E", Side.ENEMY)
        battle = Battle(100, 100, [player, enemy])
        _, before = combat._roll_model_attacks(player, enemy, random.Random(1))  # WS 3 against 3: 4+
        battle.apply_difficulty(SOLDIER)
        _, after = combat._roll_model_attacks(player, enemy, random.Random(1))  # 4 against 3: 3+
        self.assertEqual((before["hit_need"], after["hit_need"]), (4, 3))
        self.assertEqual((player.ws, player.bs, enemy.skill_bonus), (3, 3, 0))

    def test_given_soldier_then_enemies_find_player_regiments_harder_to_hit(self):
        player, enemy = unit("P", Side.PLAYER, ws=6), unit("E", Side.ENEMY)
        battle = Battle(100, 100, [player, enemy])
        _, before = combat._roll_model_attacks(enemy, player, random.Random(1))  # WS 3 against 6: 4+
        battle.apply_difficulty(SOLDIER)
        _, after = combat._roll_model_attacks(enemy, player, random.Random(1))  # 3 against 7 (more than double): 5+
        self.assertEqual((before["hit_need"], after["hit_need"]), (4, 5))

    def test_given_soldier_then_player_shots_scatter_less(self):
        player = unit("P", Side.PLAYER, bs=3)
        battle = Battle(1000, 1000, [player, unit("E", Side.ENEMY)])
        code = next(iter(ranged.WEAPONS))
        bounds = []

        def scatter_bounds() -> list[int]:
            bounds.clear()
            with mock.patch.object(battle.rng, "randint", side_effect=lambda low, high: bounds.append(high) or low):
                ranged._create_projectile(battle, player, code, ranged.WEAPONS[code], (100, 100), (100, 300), 0)
            return bounds[:2]

        before = scatter_bounds()
        battle.apply_difficulty(SOLDIER)
        self.assertEqual([bound + 1 for bound in scatter_bounds()], before)

    def test_given_an_easier_level_then_the_player_pool_starts_full_at_its_raised_maximum(self):
        for level, expected in ((SERGEANT, 10), (SOLDIER, 12)):
            with self.subTest(level=level.name):
                battle = Battle(100, 100, [unit("P", Side.PLAYER), unit("E", Side.ENEMY)])
                battle.apply_difficulty(level)
                power = battle.event_bus.power
                self.assertEqual((power.player, power.player_max), (expected, expected))
                power.add(False, 5)
                self.assertEqual(power.player, expected)
                self.assertLessEqual(power.enemy, magic.MAX_POWER)

    def test_given_a_raised_pool_then_the_wind_stays_within_it(self):
        rng = random.Random(3)
        values = {spell_effects.wind(12, rng, 12) for _ in range(200)}
        self.assertEqual((min(values), max(values)), (8, 12))
        self.assertLessEqual(max(spell_effects.wind(8, rng) for _ in range(200)), magic.MAX_POWER)

    def test_given_commander_then_the_battle_keeps_the_original_rules(self):
        battle = Battle(100, 100, [unit("P", Side.PLAYER), unit("E", Side.ENEMY)])
        rolled = battle.event_bus.power.player
        battle.apply_difficulty(COMMANDER)
        self.assertEqual((battle.event_bus.power.player, battle.event_bus.power.player_max), (rolled, magic.MAX_POWER))
        self.assertEqual(battle.regiments["P"].skill_bonus, 0)


if __name__ == "__main__":
    unittest.main()
