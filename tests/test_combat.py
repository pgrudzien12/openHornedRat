"""BDD scenarios for close combat, morale, rally and shooting (whshr.combat), per docs/testing.md."""
import unittest

from whshr import combat
from whshr.engine import Battle, Regiment


def _regiment(identifier, x, y, player, **kwargs):
    models = kwargs.pop("models", 10)
    ranks = kwargs.pop("ranks", 2)
    return Regiment(identifier, identifier, x, y, 0, player, models=models, ranks=ranks, **kwargs)


class CloseCombatTests(unittest.TestCase):
    """Given fixed statistics, dice seed, formation, and range, an attack produces the documented
    casualties, morale result, and emitted battle events (docs/testing.md, "Combat")."""

    def setUp(self):
        # A hard-hitting attacker (WS5, S5, A2) against a weak, low-Leadership defender (WS1, T1, no
        # armour, Ld2): seed 1 is fixed so the round's exact casualties are reproducible.
        self.attacker = _regiment("att", 0, 0, True, ws=5, strength=5, attacks=2, leadership=8,
                                  speed_per_tick=0.0)
        self.defender = _regiment("def", 10, 0, False, ws=1, toughness=1, armour=0, leadership=2,
                                  speed_per_tick=1.5)
        self.battle = Battle(1000, 1000, [self.attacker, self.defender], seed=1)

    def test_given_two_touching_regiments_when_ticked_then_they_clash_and_fight_in_the_same_tick(self):
        self.battle.tick()

        self.assertEqual(self.defender.models, 6)
        self.assertEqual(self.attacker.models, 10)
        # Events are still printable strings (docs/testing.md, "Battle.events may stay a list the view
        # can still print"), but each also carries a `kind` and structured `data` for the battle log.
        self.assertEqual(self.battle.events, [
            "att clashes with def!",
            "att and def fight: 4 vs 0 casualties.",
            "def takes a Leadership test (Ld 2, roll 12 + 4): fails.",
            "def routs!",
            "def cannot rally: an enemy is 65 units away.",  # same tick's rally check, still in contact
        ])
        combat_round = self.battle.events[1]
        self.assertEqual(combat_round.kind, "combat_round")
        self.assertEqual(combat_round.data["first_kills"], 4)
        self.assertEqual(combat_round.data["second_kills"], 0)
        self.assertEqual(len(combat_round.data["first_attacks"]["rolls"]), 10)  # one entry per attack
        leadership = self.battle.events[2]
        self.assertEqual(leadership.kind, "leadership_test")
        self.assertEqual(leadership.data["regiment"], "def")
        self.assertFalse(leadership.data["passed"])
        rout = self.battle.events[3]
        self.assertEqual(rout.kind, "rout_start")
        self.assertIn("flee_x", rout.data)

    def test_given_a_lost_combat_round_when_the_break_test_fails_then_the_loser_routs_and_flees(self):
        self.battle.tick()

        self.assertTrue(self.defender.routing)
        self.assertFalse(self.defender.in_melee)
        self.battle.tick()
        # A routed opponent frees the winner from melee the following tick (whshr.combat.refresh_melee_state).
        self.assertFalse(self.attacker.in_melee)
        self.assertGreater(self.defender.x, 10)  # fleeing away from the attacker (game_rules.md 7.7)

    def test_given_cant_break_psychology_when_the_round_is_lost_then_the_unit_never_routs(self):
        self.defender.psychology = frozenset({"CantBreak"})

        self.battle.tick()

        self.assertFalse(self.defender.routing)

    def test_given_casualties_when_applied_then_the_formation_shrinks_and_leaves_corpses(self):
        combat.apply_casualties(self.defender, 3, self.battle.rng)

        self.assertEqual(self.defender.models, 7)
        self.assertEqual(len(self.defender.corpses), 3)
        self.assertEqual(len(self.defender.model_positions()), 7)

    def test_given_more_casualties_than_models_when_applied_then_it_is_clamped_to_the_current_size(self):
        removed = combat.apply_casualties(self.defender, 999, self.battle.rng)

        self.assertEqual(removed, 10)
        self.assertEqual(self.defender.models, 0)
        self.assertTrue(self.defender.destroyed)


class RallyTests(unittest.TestCase):
    def test_given_no_enemy_nearby_when_the_leadership_test_passes_then_the_unit_rallies(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True)
        enemy = _regiment("e", 1000, 1000, False)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)  # seed 0: the roll passes Ld 9

        combat.resolve_rally(battle)

        self.assertFalse(routing.routing)
        self.assertIn("r takes a rally test (Ld 9, roll 8): rallies.", battle.events)
        rally = battle.events[-1]
        self.assertEqual(rally.kind, "rally_test")
        self.assertTrue(rally.data["passed"])

    def test_given_an_enemy_within_the_safe_distance_when_checked_then_no_rally_is_attempted(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True)
        enemy = _regiment("e", 50, 0, False)  # well within FLEE_SAFE_DISTANCE
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)

    def test_given_cant_rally_psychology_when_checked_then_the_unit_never_rallies(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True,
                            psychology=frozenset({"CantRally"}))
        enemy = _regiment("e", 1000, 1000, False)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)


class ShootingTests(unittest.TestCase):
    def setUp(self):
        # Crossbows (missile code 2), BS5, facing north at a target directly north and in arc.
        self.shooter = _regiment("s", 0, 0, True, bs=5, missile_code=2, missile_range=720.0,
                                 speed_per_tick=0.0)
        self.target = _regiment("t", 0, 300, False, toughness=3, armour=0, speed_per_tick=0.0)
        self.battle = Battle(2000, 2000, [self.shooter, self.target], seed=0)

    def test_given_a_target_in_range_and_arc_when_ticked_then_it_fires_and_reloads(self):
        self.battle.tick()

        self.assertEqual(self.target.models, 8)  # seed 0: 2 casualties from this volley
        self.assertIn("s shoots t: 2 casualties.", self.battle.events)
        # game_rules.md 8.2: an I3 crossbow unit reloads in 96 ticks.
        self.assertAlmostEqual(self.shooter.reload_ticks, 96)

    def test_given_a_target_outside_the_front_arc_when_ticked_then_it_does_not_fire(self):
        self.target.x, self.target.y = 300.0, 0.0  # due east: outside the +/-45 degree arc facing north

        self.battle.tick()

        self.assertEqual(self.target.models, 10)
        self.assertEqual(self.shooter.reload_ticks, 0.0)

    def test_given_a_reloading_shooter_when_ticked_then_it_holds_fire_until_ready(self):
        self.battle.tick()
        reload_ticks = int(self.shooter.reload_ticks)
        models_after_first_volley = self.target.models

        for _ in range(reload_ticks - 1):
            self.battle.tick()
        self.assertEqual(self.target.models, models_after_first_volley)  # still reloading
        self.assertGreater(self.shooter.reload_ticks, 0)

        self.battle.tick()  # the reload countdown reaches zero on this tick: it fires again

        self.assertLess(self.target.models, models_after_first_volley)


class ContactAndMeleeStateTests(unittest.TestCase):
    def test_given_a_routing_unit_when_an_enemy_touches_it_then_it_is_not_engaged_in_melee(self):
        routing = _regiment("r", 0, 0, True, routing=True, speed_per_tick=0.0)
        pursuer = _regiment("p", 5, 0, False, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [routing, pursuer], seed=0)

        battle.tick()

        self.assertFalse(routing.in_melee)
        self.assertFalse(pursuer.in_melee)


if __name__ == "__main__":
    unittest.main()
