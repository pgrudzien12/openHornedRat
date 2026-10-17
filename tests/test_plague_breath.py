"""The Plague Monks' breath: Pestilent Breath's exact stage timing, trail and removal, and the pines it fells
(notes/spell_plague_monk_breath_visuals.md)."""
import unittest
from types import SimpleNamespace
from unittest import mock

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import battlefield, buildings, objectives, spell_effects
from whshr.frontend import spell_visuals
from whshr.rules import Side

BREATH = spell_effects.PESTILENT_BREATH
PINES = [{"name": "Pine", "x": 1250, "y": 1240},       # d = 64 from (1200, 1200)
         {"name": "PineLrg", "x": 1250, "y": 1241},    # d = 64.7, truncated 64
         {"name": "Pine", "x": 1260, "y": 1240},       # d = 72.1
         {"name": "Tudor2Stry", "x": 1210, "y": 1200}]  # not a pine


def monks(models=10, side=Side.ENEMY):
    return Regiment("P", "P", 1000, 1000, 0, side, models=models, ranks=2, hud_class="inf", bs=10)


def battle(*scenery, unit=None):
    unit = unit or monks()
    b = Battle(3000, 3000, [unit], seed=1995, scenery=list(scenery))
    b.phase = "battle"
    return b


class Run:
    """Ticks the effects and the presentation together; `at[k]` is the sprite frames drawn on tick T+k."""

    def __init__(self, b):
        self.battle, self.visuals, self.memory, self.at, self.ruined = b, spell_visuals.ProjectileVisuals(), {}, [], []

    def step(self, count=1):
        for _ in range(count):
            spell_effects.tick(self.battle)
            shots, _runs = spell_visuals.projectile_shots(spell_effects.table(self.battle).effects(), self.memory)
            self.visuals.advance(shots)
            self.at.append([(s.frame, s.x, s.y) for s in self.visuals.sprites()])
            self.ruined.append(set(self.battle.ruined))
        return self


def launched(*scenery, innate=True, unit=None):
    b = battle(*scenery, unit=unit)
    caster = b.regiments["P"]
    assert spell_effects.launch(b, BREATH, caster, -1, 1200, 1200, innate=innate)
    return Run(b)


class StageTimeline(unittest.TestCase):
    def test_the_head_follows_the_exact_stage_table_with_no_lag(self):
        run = launched().step(20)
        heads = [frames[0][0] for frames in run.at[:19]]
        self.assertEqual(heads, [533] * 5 + [534] * 5 + [535] * 4 + [536] * 5)

    def test_the_head_is_gone_the_tick_after_the_finish(self):
        run = launched().step(20)
        self.assertEqual((run.at[18][0][1:], len(run.at[19])), ((1200, 1200), 18))
        self.assertEqual(run.at[19][0][1], 1012)  # oldest remaining puff, not a head at the destination

    def test_a_puff_takes_the_head_frame_of_the_tick_it_is_left(self):
        run = launched().step(20)
        puffs = [frame for frame, _x, _y in run.at[19]]  # puffs 2..19
        self.assertEqual(puffs, [533] * 3 + [534] * 5 + [535] * 4 + [536] * 6)

    def test_there_is_a_puff_at_the_start_on_the_first_tick_and_none_on_the_second(self):
        run = launched().step(3)
        self.assertEqual([len(frames) for frames in run.at], [2, 2, 3])  # head + puff 1; head + puff 1; + puff 2
        self.assertEqual(run.at[0][1][1:], (1000, 1000))

    def test_the_trail_is_removed_oldest_first_and_is_gone_on_the_37th_tick(self):
        run = launched().step(40)
        self.assertEqual([len(frames) for frames in run.at[19:38]], list(range(18, 0, -1)) + [0])
        self.assertEqual(run.at[36], [(536, 1200, 1200)])
        self.assertEqual(run.visuals.shots, {})

    def test_a_breath_with_no_offset_leaves_one_puff_and_grows_in_place(self):
        b = battle()
        spell_effects.launch(b, BREATH, b.regiments["P"], -1, 1000, 1000, innate=True)
        run = Run(b).step(21)
        self.assertEqual([frame for frame, _x, _y in (f[0] for f in run.at[:19])],
                         [533] * 5 + [534] * 5 + [535] * 4 + [536] * 5)
        self.assertEqual([len(f) for f in run.at[:3]], [2, 2, 2])
        self.assertEqual(run.at[19], [])  # the only puff is removed with the head (not drawn)

    def test_the_steam_gun_shares_the_stages_without_lag(self):
        steps, remaining = 18, 14
        self.assertEqual(spell_visuals.breath_stage(remaining - 1, steps), 0)  # T+4
        self.assertEqual(spell_visuals.breath_stage(remaining - 2, steps), 1)  # T+5

    def test_a_cloud_that_went_below_ground_is_not_drawn_on_its_last_tick(self):
        visuals = spell_visuals.ProjectileVisuals()

        def shot(x, remaining, **flags):
            return spell_visuals.Shot((1, 0), BREATH, x, 0.0, 8.0, (0.0, 0.0), (1000.0, 0.0), remaining, 18, **flags)

        for x, remaining in ((0.0, 17), (100.0, 16), (200.0, 15)):
            visuals.advance([shot(x, remaining)])
        visuals.advance([shot(300.0, 14, hidden=True)])  # the tick it went below the ground
        self.assertEqual(sorted(s.x for s in visuals.sprites()), [0.0, 100.0, 200.0])  # puffs only, no head at 300
        visuals.advance([shot(300.0, 14, ending=True)])
        self.assertEqual(sorted(s.x for s in visuals.sprites()), [100.0, 200.0, 300.0])  # last puff, oldest gone


class Start(unittest.TestCase):
    def test_the_innate_breath_starts_at_the_unit_position(self):
        run = launched()
        effect = spell_effects.table(run.battle).effects()[0]
        self.assertEqual((effect.code, effect.innate, effect.start), (BREATH, True, (1000.0, 1000.0)))
        run.step(1)
        self.assertEqual(run.at[0][0][1:], (1000, 1000))


class Cancellation(unittest.TestCase):
    def test_the_innate_breath_is_never_cancelled(self):
        run = launched(*PINES)
        run.step(6)
        run.battle.regiments["P"].models = 0
        self.assertEqual(spell_effects.cancel_owned(run.battle, "P", BREATH), 0)
        run.step(34)
        self.assertEqual(len(run.at[19]), 18)
        self.assertEqual(run.at[36], [(536, 1200, 1200)])
        self.assertEqual(run.ruined[19], {"tree:0", "tree:1"})

    def test_a_cast_breath_vanishes_at_once_when_it_is_cancelled(self):
        run = launched(innate=False)
        run.step(8)
        self.assertEqual(spell_effects.cancel_owned(run.battle, "P", BREATH), 1)
        run.step(1)
        self.assertEqual(run.at[8], [])


class FellingPines(unittest.TestCase):
    def test_pines_within_64_truncated_fall_the_tick_after_the_finish(self):
        run = launched(*PINES).step(21)
        self.assertEqual(run.ruined[18], set())
        self.assertEqual(run.ruined[19], {"tree:0", "tree:1"})  # d = 64 and 64.7; not 72.1, not the house
        self.assertEqual(run.ruined[20], {"tree:0", "tree:1"})

    def test_the_cast_spell_fells_nothing(self):
        run = launched(*PINES, innate=False).step(25)
        self.assertEqual(run.battle.ruined, set())

    def test_the_tree_falls_even_when_the_monks_are_gone(self):
        run = launched(*PINES)
        run.battle.regiments["P"].models = 0
        run.step(20)
        self.assertEqual(run.ruined[19], {"tree:0", "tree:1"})

    def test_a_felled_tree_is_not_felled_again(self):
        b = battle(*PINES)
        self.assertEqual(b.fell_pines(1200, 1200), ["tree:0", "tree:1"])
        self.assertEqual(b.fell_pines(1200, 1200), [])

    def test_the_breath_does_not_shake_the_camera(self):
        run = launched(*PINES)
        with mock.patch.object(Battle, "shake_camera") as shake:
            run.step(25)
        shake.assert_not_called()

    def test_a_cloud_that_went_below_ground_fells_around_its_last_position(self):
        b = battle({"name": "Pine", "x": 1100, "y": 1100})
        effect = spell_effects.Effect(1, BREATH, "P", True, False, (0.0, 0.0), x=1100.0, y=1100.0,
                                      tail=spell_effects.TAIL_TICKS)
        b.spell_effects.add(effect)
        spell_effects.tick(b)
        self.assertEqual(b.ruined, {"tree:0"})

    def test_pine_types_match_the_objective_counter_and_there_are_18(self):
        self.assertEqual(buildings.PINE_TYPES, objectives.TREE_TYPES)
        self.assertEqual(len(buildings.PINE_TYPES), 18)

    def test_a_felled_tree_no_longer_counts_as_standing_for_objective_q(self):
        b = battle(*PINES)
        before = objectives.standing_trees(b)
        felled = b.fell_pines(1200, 1200)
        self.assertEqual((before, objectives.standing_trees(b)), (3, 3 - len(felled)))
        self.assertGreater(len(felled), 0)


def triangle(x):
    return {"verts": [x, 0, 0, x, 1, 0, x, 0, 1], "uv": [0, 0] * 3, "normals": [0, 1, 0],
            "faces": [((0, 1, 2), (0, 0, 0))], "ftex": [0]}


class Drawing(unittest.TestCase):
    def test_the_dead_variant_is_record_plus_59_of_a_pine_record(self):
        furniture = [{"name": f"F{i}", "file": f"M{i}", "flags": 5} for i in range(163)]
        furniture[87] = {"name": "TriPineLrg", "file": "TPINEL", "flags": 5}
        furniture[104] = {"name": "SnwPine", "file": "SPINE", "flags": 5}
        furniture[146] = {"name": "D_TriPineLrg", "file": "TPINEL_D", "flags": 5}
        furniture[163 - 1] = {"name": "D_SnwPine", "file": "SPINE_D", "flags": 5}
        furniture.append({"name": "x", "file": "", "flags": 0})
        game = SimpleNamespace(require=lambda name: name)
        with mock.patch.object(battlefield, "exe_tables", lambda path: ([], furniture, {"exe": path})):
            fallen = battlefield.furniture_fallen(game)
        self.assertEqual(fallen["tripinelrg"], "TPINEL_D.XOF")

    def test_a_felled_pine_is_baked_with_its_dead_mesh(self):
        piece = battlefield.BuildingPiece("tree:3", {"x": 0, "y": 0, "dir": 0}, 0.0, triangle(1.0), triangle(5.0))
        field = SimpleNamespace(building_pieces=[piece], ground_texture_count=0, scenery_texture_count=1,
                                ambient=battlefield.DEFAULT_AMBIENT, light=battlefield.DEFAULT_LIGHT)
        standing = battlefield.Battlefield.building_vertices(field, ())
        felled = battlefield.Battlefield.building_vertices(field, {"tree:3"})
        self.assertNotEqual(standing, felled)


if __name__ == "__main__":
    unittest.main()
