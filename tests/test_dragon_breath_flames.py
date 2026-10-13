"""Dragon breath flames as innate Fireball effects (notes/bf014_dragon_mission_audit.md 3 and 7).

Given the dragon at (1120, 600) facing 384 on flat ground, breathing at node 17 (986, 609),
when the breath is launched, then each flame is a separate Fireball effect drawn and flown as the report's vectors say.
"""
import random
import unittest

from whshr import interpreter, ranged, spell_effects
from whshr.engine import Battle, Regiment
from whshr.frontend.spell_visuals import FireballVisuals, Flight, breath_display_height
from whshr.rules import Side

NODE_17 = (986, 609)


class Scripted(random.Random):
    """Hands out the queued draws, then 0."""

    def __init__(self, draws):
        super().__init__(0)
        self.draws = list(draws)

    def randrange(self, *args):
        return self.draws.pop(0) if self.draws else 0


def dragon(x=1120, y=600, **kw):
    return Regiment('d', 'Dragon', x, y, 384, Side.ENEMY, models=1, ranks=1, shooting_code=14, unit_class=1,
                    bs=6, **kw)


def flames(battle):
    return [effect for effect in battle.spell_effects.effects() if effect.breath]


def breathe(battle, unit, aim=NODE_17, draws=()):
    battle.rng = Scripted(draws)
    ranged.launch_shot(battle, unit, (unit.x, unit.y), aim)


class BreathLaunchTests(unittest.TestCase):
    def test_flame_count_spread_and_scatter_follow_the_report_vector(self):
        unit = dragon()
        battle = Battle(2000, 2000, [unit])
        breathe(battle, unit, draws=[3, 0, 79, 4, 0, 0, 1])
        launched = flames(battle)
        self.assertEqual(len(launched), 7)
        first = launched[0]
        self.assertEqual(first.code, spell_effects.FIREBALL)
        self.assertTrue(first.innate)
        self.assertEqual(first.aim, (1025, 569))
        self.assertEqual(first.dest, (1029, 569))
        self.assertEqual(first.start, (1048, 600))
        self.assertEqual(first.steps, 18)

    def test_spread_is_minus_forty_to_plus_thirty_nine_per_axis(self):
        unit = dragon()
        battle = Battle(2000, 2000, [unit])
        breathe(battle, unit, draws=[0, 79, 0, 0, 0, 0, 0, 0, 79, 0, 0, 0, 0])
        aims = [effect.aim for effect in flames(battle)]
        self.assertEqual(aims[0], (NODE_17[0] - 40, NODE_17[1] + 39))
        self.assertEqual(aims[1], (NODE_17[0] + 39, NODE_17[1] - 40))

    def test_rejected_breath_still_spends_the_count_draw(self):
        unit = dragon()
        battle = Battle(2000, 2000, [unit])
        breathe(battle, unit, aim=(1300, 600), draws=[3, 55])
        self.assertEqual(flames(battle), [])
        self.assertEqual(battle.rng.draws, [55])

    def test_every_flame_plays_the_fireball_launch_sound(self):
        unit = dragon()
        battle = Battle(2000, 2000, [unit])
        breathe(battle, unit, draws=[0])
        self.assertEqual(len(flames(battle)), 4)
        self.assertTrue(all(effect.sounds for effect in flames(battle)))


class FlameFlightTests(unittest.TestCase):
    def fly(self, battle):
        seen = []
        while flames(battle) and not flames(battle)[0].ended and flames(battle)[0].tail < 0:
            spell_effects.tick(battle)
            effect = flames(battle)[0]
            seen.append((effect.x, effect.y, effect.height))
        return seen

    def single_flame(self, others=()):
        unit = dragon()
        battle = Battle(2000, 2000, [unit, *others], seed=1995)
        breathe(battle, unit, draws=[3, 0, 79, 4, 0, 0, 1])
        for extra in flames(battle)[1:]:
            spell_effects.table(battle).remove(extra)
        battle.rng = random.Random(1)
        return battle

    def test_flat_flight_runs_forty_to_twenty_in_nineteen_tests(self):
        seen = self.fly(self.single_flame())
        self.assertEqual(len(seen), 19)
        self.assertEqual(seen[0], (1048, 600, 40))
        self.assertEqual(seen[1], (1046, 598, 38))
        self.assertEqual(seen[9], (1038, 584, 30))
        self.assertEqual(seen[17], (1030, 570, 21))
        self.assertEqual(seen[18], (1029, 569, 20))

    def test_ground_unit_under_the_path_is_flown_over_and_struck_where_the_flame_lands(self):
        target = Regiment('u', 'U', 1029, 569, 0, Side.PLAYER, models=10, ranks=2)
        battle = self.single_flame([target])
        self.fly(battle)
        strikes = [e for e in battle.events if e.kind == "spell_strike"]
        self.assertEqual([(e.data["regiment"], e.data["terminal"]) for e in strikes], [("u", True)])

    def test_unit_away_from_the_landing_point_is_never_struck(self):
        target = Regiment('u', 'U', 1000, 500, 0, Side.PLAYER, models=10, ranks=2)
        battle = self.single_flame([target])
        self.fly(battle)
        self.assertEqual([e for e in battle.events if e.kind == "spell_strike"], [])

    def test_every_unit_struck_is_sent_the_rout_event(self):
        target = Regiment('u', 'U', 1029, 569, 0, Side.PLAYER, models=10, ranks=2)
        battle = self.single_flame([target])
        battle.interpreter = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        self.fly(battle)
        self.assertIn(0x0C, [event.code for event in battle.event_bus.unit_states['u'].event_queue])

    def test_flame_strikes_at_eight_with_one_wound_and_no_save(self):
        bolt = spell_effects.BREATH_FLAME
        self.assertEqual((bolt.strength, bolt.wound_die, bolt.save, bolt.fire, bolt.routs), (8, 1, False, True, True))


class FlameDisplayTests(unittest.TestCase):
    def test_flame_is_drawn_on_a_straight_line_down_to_the_target_ground(self):
        unit = dragon()
        battle = Battle(2000, 2000, [unit])
        breathe(battle, unit, draws=[3, 0, 79, 4, 0, 0, 1])
        effect = flames(battle)[0]
        drawn = []
        for _ in range(19):
            spell_effects.tick(battle)
            drawn.append(breath_display_height(effect))
        self.assertEqual(drawn[0], 40)
        self.assertEqual(drawn[-1], 0)
        self.assertEqual(drawn, sorted(drawn, reverse=True))

    def test_trail_runs_from_the_moved_start_to_the_landing_point(self):
        unit = dragon()
        battle = Battle(2000, 2000, [unit])
        breathe(battle, unit, draws=[0, 0, 79, 4, 0, 0, 1])
        effect = flames(battle)[0]
        visuals = FireballVisuals()
        for _ in range(20):
            spell_effects.tick(battle)
            if effect.serial in [e.serial for e in flames(battle)] and effect.elapsed:
                visuals.advance([Flight(effect.serial, effect.x, effect.y, breath_display_height(effect),
                                        effect.tail >= 0)])
                if effect.tail >= 0:
                    break
        puffs = {(s.x, s.y) for s in visuals.sprites() if s.frame < 177}
        self.assertIn(effect.start, puffs)
        self.assertIn(effect.dest, puffs)


if __name__ == "__main__":
    unittest.main()
