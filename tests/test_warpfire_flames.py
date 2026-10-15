"""A Warpfire Thrower's flames as innate green Fireballs (notes/spell_warpfire_visuals.md).

Given a Warpfire Thrower at (1000, 1000) facing 0 on flat ground, shooting at (1000, 1200), when the shot is fired, then
each flame is a separate Fireball effect launched, flown and drawn as the report's vectors say.
"""
import random
import unittest

from whshr import animation, ranged, spell_effects
from whshr.engine import Battle, Regiment
from whshr.frontend.spell_visuals import FireballVisuals, Flight
from whshr.rules import Side

WARPFIRE = "WarpFireThrower"
TARGET = (1000, 1200)
SCATTER_NONE = [0, 0, 0, 0]  # x magnitude, x sign, y magnitude, y sign


class Scripted(random.Random):
    """Hands out the queued draws, then `default` (clamped into the asked range)."""

    def __init__(self, draws, default=0):
        super().__init__(0)
        self.draws = list(draws)
        self.default = default
        self.taken = 0

    def randrange(self, *args):
        self.taken += 1
        if self.draws:
            return self.draws.pop(0)
        return min(self.default, args[-1] - 1)


def thrower(direction=0, sprite=WARPFIRE, leader_sprite=WARPFIRE, **kw):
    return Regiment("w", "Warpfire", 1000, 1000, direction, Side.PLAYER, models=2, ranks=1, shooting_code=15,
                    missile_code=15, unit_class=1, bs=3, sprite=sprite, leader_sprite=leader_sprite, **kw)


def shoot(battle, unit, draws, aim=TARGET, default=0):
    battle.rng = Scripted(draws, default)
    return ranged.launch_shot(battle, unit, (unit.x, unit.y), aim)


def flames(battle):
    return [effect for effect in battle.spell_effects.effects() if effect.warpfire]


def jitter(y, x):
    return [y, x]


def one_flame_battle(*others, direction=0):
    """The report's section 3 example: jittered aim (1000, 1196), no scatter."""
    unit = thrower(direction)
    battle = Battle(2000, 2000, [unit, *others])
    shoot(battle, unit, [0, *jitter(20, 24), *SCATTER_NONE])  # count 1, y jitter -4, x jitter 0
    return battle, unit


class Run:
    """Ticks the effects like the battle and feeds the green Fireball presentation like the battle view does."""

    def __init__(self, battle):
        self.battle, self.visuals, self.ended, self.tick_number = battle, FireballVisuals(), set(), -1
        self.seen = []

    def step(self):
        spell_effects.tick(self.battle)
        self.tick_number += 1
        flights = []
        for effect in self.battle.spell_effects.active:
            if not effect.warpfire or effect.ended or effect.elapsed == 0:
                continue
            flying = effect.tail < 0
            if not flying:
                if effect.serial in self.ended:
                    continue
                self.ended.add(effect.serial)
            flights.append(Flight(effect.serial, effect.x, effect.y, max(0.0, effect.height), not flying, True,
                                  effect.terminal))
        self.visuals.advance(flights)
        return self.visuals.sprites()

    def until(self, tick):
        sprites = []
        while self.tick_number < tick:
            sprites = self.step()
        return sprites


class ShotTests(unittest.TestCase):
    def test_count_is_drawn_first_and_each_flame_makes_six_more_draws(self):
        unit = thrower()
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [2, *([0] * 18)] + [99])
        self.assertEqual(len(flames(battle)), 3)
        self.assertEqual(battle.rng.draws, [99])  # 1 + 6 * 3 draws taken
        self.assertEqual(battle.rng.taken, 19)

    def test_count_is_one_to_six(self):
        for draw, expected in ((0, 1), (5, 6)):
            unit = thrower()
            battle = Battle(2000, 2000, [unit])
            shoot(battle, unit, [draw])
            self.assertEqual(len(flames(battle)), expected)

    def test_y_jitter_is_drawn_before_x_and_runs_from_minus_24_to_plus_23(self):
        unit = thrower()
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [0, *jitter(47, 0), *SCATTER_NONE])
        self.assertEqual(flames(battle)[0].aim, (976, 1223))
        unit = thrower()
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [0, *jitter(0, 47), *SCATTER_NONE])
        self.assertEqual(flames(battle)[0].aim, (1023, 1176))

    def test_each_flame_is_an_innate_fireball_with_the_scatter_draws_after_its_jitter(self):
        unit = thrower()
        battle = Battle(2000, 2000, [unit])
        # flame 1: jitter 24/24, scatter x magnitude 1 positive, y magnitude 2 negative; flame 2 unscattered
        shoot(battle, unit, [1, *jitter(24, 24), 1, 0, 2, 1, *jitter(24, 24), *SCATTER_NONE])
        first, second = flames(battle)
        self.assertEqual((first.code, first.innate), (spell_effects.FIREBALL, True))
        self.assertEqual(second.dest, (1000, 1200))
        step = int(8 * 184 / 576)  # distance from the unit position to the jittered aim, range 576
        self.assertEqual(first.dest, (1000 + step, 1200 - 2 * step))

    def test_all_flames_start_16_ahead_of_the_unit(self):
        unit = thrower()
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [2, *([24] * 2 + SCATTER_NONE) * 3])
        self.assertEqual({effect.start for effect in flames(battle)}, {(1000, 1016)})

    def test_start_follows_the_facing_with_the_integer_rule(self):
        for facing, offset in ((128, (16, 0)), (384, (-16, 0)), (320, (-12, -12)), (64, (11, 11))):
            unit = thrower(facing)
            battle = Battle(2000, 2000, [unit])
            shoot(battle, unit, [0])
            self.assertEqual(flames(battle)[0].start, (1000 + offset[0], 1000 + offset[1]), facing)

    def test_the_destination_comes_from_the_unmoved_position(self):
        battle, _ = one_flame_battle()
        flame = flames(battle)[0]
        self.assertEqual((flame.start, flame.dest, flame.steps), ((1000, 1016), (1000, 1196), 18))

    def test_every_flame_plays_the_fireball_sound_at_the_unit_position(self):
        unit = thrower()
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [2])
        sounds = [e for e in battle.events if e.kind == "sound" and e.data["cue"] == "loop_start"]
        self.assertEqual(len(sounds), 3)
        self.assertTrue(all(e.data["position"] == (1000, 1000) for e in sounds))

    def test_the_flame_is_not_a_cancellable_dispellable_spell(self):
        battle, unit = one_flame_battle()
        self.assertTrue(flames(battle)[0].innate)
        self.assertFalse(spell_effects.spell_active(battle, unit.identifier, spell_effects.FIREBALL))


class PoseTests(unittest.TestCase):
    def test_the_whole_unit_shoots_when_troop_and_leader_sets_are_warpfire(self):
        unit = thrower()
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [0])
        self.assertEqual([model.own_request for model in unit.melee_models], [animation.SHOOT] * 2)

    def test_another_unit_with_a_leader_poses_only_its_leader(self):
        unit = thrower(sprite="Skaven", leader_sprite="Skaven", has_leader=True)
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [0])
        unit.model_positions()
        poses = [model.own_request for model in unit.melee_models]
        self.assertEqual(sorted(poses), [0, animation.SHOOT])
        self.assertEqual(len(flames(battle)), 1)

    def test_such_a_unit_without_a_leader_fires_nothing_but_the_count_is_drawn(self):
        unit = thrower(sprite="Skaven", leader_sprite=None)
        battle = Battle(2000, 2000, [unit])
        shoot(battle, unit, [3, 99])
        self.assertEqual(flames(battle), [])
        self.assertEqual(battle.rng.draws, [99])
        self.assertEqual([e for e in battle.events if e.kind in ("sound", "ranged_message", "innate_launch")], [])
        self.assertEqual([model.own_request for model in unit.melee_models], [0, 0])


class RepeatedShotTests(unittest.TestCase):
    """With the Warpfire table the pose has no fire step, so nothing waits for a fire event: the flames leave on the
    tick of the order and the thrower shoots again after its reload."""

    def test_two_shots_across_a_reload_each_launch_flames_and_no_countdown_hangs(self):
        unit = thrower()
        unit.initiative = 9  # short reload
        battle = Battle(2000, 2000, [unit, Regiment("e", "Enemy", 1000, 1200, 256, Side.ENEMY, models=4, ranks=2)])
        battle.rng = Scripted([], default=0)
        unit.shooting_mode, unit.shooting_target = "target", "e"
        battle.tick()
        first = len(flames(battle))
        self.assertGreaterEqual(first, 1)
        self.assertIsNone(unit.volley_countdown)
        battle.tick()  # the pose request made with the order is applied by the next tick's animation step
        self.assertEqual([model.action for model in unit.melee_models], [animation.SHOOT] * 2)
        for _ in range(300):
            battle.tick()
            if len(flames(battle)) > first:
                break
        self.assertGreater(len(flames(battle)), first)
        self.assertIsNone(unit.volley_countdown)

    def test_the_shot_pose_plays_ten_minus_r_ticks_and_ends_in_the_rest_action(self):
        unit = thrower()
        battle = Battle(2000, 2000, [unit, Regiment("e", "Enemy", 1000, 1200, 256, Side.ENEMY, models=4, ranks=2)])
        battle.rng = Scripted([], default=0)
        unit.shooting_mode, unit.shooting_target = "target", "e"
        battle.tick()
        battle.tick()  # the pose request made with the order is applied by the next tick's animation step
        self.assertEqual(unit.melee_models[0].action, animation.SHOOT)
        for _ in range(12):
            battle.tick()
        self.assertEqual(unit.melee_models[0].action, animation.WEAPON_READY)  # the unit still has a target


class FlightTests(unittest.TestCase):
    def test_the_flame_flies_18_ticks_along_the_report_example_with_the_fireball_arc(self):
        battle, _ = one_flame_battle()
        flame, positions = flames(battle)[0], []
        for _ in range(19):
            spell_effects.tick(battle)
            positions.append((flame.x, flame.y, flame.height))
        self.assertEqual(positions[0], (1000, 1016, 1))
        self.assertEqual(positions[1], (1000, 1026, 2))
        self.assertEqual(positions[8], (1000, 1096, 9))
        self.assertEqual(positions[17], (1000, 1186, 0))
        self.assertEqual(positions[18], (1000, 1196, -1))

    def test_head_frames_cycle_562_to_565_and_the_last_flight_tick_has_no_head(self):
        run = Run(one_flame_battle()[0])
        heads = []
        for _ in range(19):
            heads.append(sorted(s.frame for s in run.step() if s.frame <= 565 and (s.x, s.y) == (1000, 1016 + 10 * len(heads))))
        # T, T+3, T+4: 562, 565, 562 (the report's vectors); a puff at the same spot can share a frame
        self.assertIn(562, heads[0])
        self.assertIn(565, heads[3])
        self.assertIn(562, heads[4])
        self.assertEqual(heads[18], [])  # T+18: nothing at the destination yet

    def test_the_head_is_not_drawn_on_the_last_flight_tick(self):
        run = Run(one_flame_battle()[0])
        run.until(17)
        self.assertEqual([s for s in run.step() if s.height == 0.0 and s.frame <= 565 and s.y == 1196], [])

    def test_trail_puffs_follow_the_fireball_rule(self):
        run = Run(one_flame_battle()[0])
        puffs = [sorted((s.frame, s.y) for s in run.step() if s.height != 0 or True) for _ in range(5)]
        self.assertEqual(puffs[0], [(562, 1016), (562, 1016)])  # head and P0
        self.assertEqual(sorted(y for _, y in puffs[1]), [1016, 1026])  # P0 and the head: no puff at T+1
        self.assertEqual(sorted(y for _, y in puffs[2]), [1016, 1026, 1036])  # P1 at 1026 on T+2
        self.assertEqual(sorted(y for _, y in puffs[3]), [1016, 1026, 1036, 1046])

    def test_a_puff_shows_562_plus_its_age_and_is_gone_on_its_twenty_first_tick(self):
        run = Run(one_flame_battle()[0])
        run.until(18)
        p0 = [s.frame for s in run.step() if s.y == 1016]  # T+19: P0 shows 581 and is the last frame
        self.assertEqual(p0, [581])
        self.assertEqual([s for s in run.step() if s.y == 1016], [])  # T+20: gone

    def test_burst_stands_on_the_ground_the_tick_after_the_flight_ends(self):
        run = Run(one_flame_battle()[0])
        sprites = run.until(18)
        self.assertEqual([s for s in sprites if s.frame >= 582], [])
        self.assertEqual([s for s in sprites if s.y == 1196], [])  # no head and no closing puff yet
        self.assertIn(1186, [s.y for s in sprites])  # P17 at the previous position
        sprites = run.step()  # T+19
        self.assertEqual([(s.frame, s.x, s.y, s.height) for s in sprites if s.frame >= 582], [(582, 1000, 1196, 0.0)])
        self.assertIn(562, [s.frame for s in sprites if s.y == 1196])  # P18 on the destination

    def test_burst_plays_582_to_590_then_is_gone(self):
        run = Run(one_flame_battle()[0])
        run.until(19)
        for tick in range(20, 28):
            frames = [s.frame for s in run.step() if s.frame >= 582]
            self.assertEqual(frames, [582 + tick - 19], tick)
        self.assertEqual([s for s in run.step() if s.frame >= 582], [])  # T+28

    def test_the_last_puff_shows_581_on_t_plus_38_and_nothing_is_drawn_on_t_plus_39(self):
        run = Run(one_flame_battle()[0])
        self.assertEqual([s.frame for s in run.until(38)], [581])
        self.assertEqual(run.step(), [])
        self.assertEqual(run.visuals.bolts, {})

    def test_the_effect_ends_40_ticks_after_the_launch(self):
        battle, _ = one_flame_battle()
        for _ in range(40):  # T .. T+39
            spell_effects.tick(battle)
        self.assertEqual(len(flames(battle)), 1)
        spell_effects.tick(battle)  # T+40
        self.assertEqual(flames(battle), [])

    def test_removing_the_shooter_changes_nothing(self):
        battle, unit = one_flame_battle()
        run = Run(battle)
        run.until(3)
        unit.models = 0
        del battle.regiments[unit.identifier]
        run.until(19)
        self.assertEqual(len(flames(battle)), 1)
        self.assertEqual([s.frame for s in run.step() if s.frame >= 582], [583])
        run.until(39)
        self.assertEqual(len(flames(battle)), 1)
        run.step()
        self.assertEqual(flames(battle), [])

    def test_a_flame_stopped_by_a_hit_bursts_at_the_stop_point_and_ends_22_ticks_later(self):
        victim = Regiment("v", "Victim", 1000, 1100, 0, Side.ENEMY, models=1, ranks=1)
        battle, _ = one_flame_battle(victim)
        battle.rng = Scripted([], default=5)
        run = Run(battle)
        flame = flames(battle)[0]
        ended_on = None
        while ended_on is None:
            run.step()
            if flame.tail >= 0:
                ended_on = run.tick_number
        self.assertLess(ended_on, 18)
        stop = (flame.x, flame.y)
        burst = [(s.frame, s.x, s.y, s.height) for s in run.step() if s.frame >= 582]
        self.assertEqual(burst, [(582, stop[0], stop[1], 0.0)])
        for _ in range(20):
            run.step()
        self.assertEqual(len(flames(battle)), 1)  # H+21
        run.step()
        self.assertEqual(flames(battle), [])  # H+22

    def test_a_unit_struck_by_a_flame_dies_a_warpfire_death(self):
        victim = Regiment("v", "Victim", 1000, 1196, 0, Side.ENEMY, models=1, ranks=1)
        battle, _ = one_flame_battle(victim)
        battle.rng = Scripted([], default=5)
        for _ in range(19):
            spell_effects.tick(battle)
        self.assertEqual(victim.models, 0)
        self.assertEqual(victim.dying[0].death_kind, animation.DEATH_WARPFIRE)

    def test_the_effect_is_never_cancelled_by_a_removed_target_unit(self):
        victim = Regiment("v", "Victim", 1000, 1196, 0, Side.ENEMY, models=1, ranks=1)
        battle, _ = one_flame_battle(victim)
        spell_effects.tick(battle)
        del battle.regiments["v"]
        for _ in range(18):
            spell_effects.tick(battle)
        self.assertEqual(len(flames(battle)), 1)


if __name__ == "__main__":
    unittest.main()
