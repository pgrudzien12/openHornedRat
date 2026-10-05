"""BDD scenarios for close combat, morale, rally and shooting (whshr.combat), per docs/testing.md.

Timing is expressed in ticks: SEGMENT_TICKS (19) ticks make one segment, SEGMENTS_PER_TURN (10)
segments make one turn (game_rules.md 5.1, 6.2, 7.4).
"""
import math
import unittest
from unittest.mock import patch

from whshr import combat, formation
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def _regiment(identifier, x, y, side, **kwargs):
    models = kwargs.pop("models", 10)
    ranks = kwargs.pop("ranks", 2)
    direction = kwargs.pop("direction", 0)
    return Regiment(identifier, identifier, x, y, direction, side, models=models, ranks=ranks, **kwargs)


def _run(battle, ticks):
    """Tick `battle` `ticks` times and return every event emitted, in order."""
    events = []
    for _ in range(ticks):
        battle.tick()
        events.extend(battle.events)
    return events


def _join_fight(battle, group_id, *regiments, turn=0):
    """Test helper: put `regiments` into a fresh shared fight `group_id`, touching every regiment of
    the opposite side among them, without going through `combat.resolve_contacts`' geometry."""
    battle.fights[group_id] = combat._new_fight(turn, 1)
    # These are established combatants, not newcomers: give them a result segment already seen, so
    # game_rules.md 6.2's "cannot be broken in your first result segment" rule does not exempt them.
    battle.fights[group_id]["rounds"] = {r.identifier: 1 for r in regiments}
    for regiment in regiments:
        regiment.in_melee = True
        regiment.melee_group = group_id
        regiment.melee_touching = frozenset(
            r.identifier for r in regiments if r.side != regiment.side)


class InitiativeTimingTests(unittest.TestCase):
    """game_rules.md 5.1: a unit attacks once per turn, in the segment equal to its Initiative."""

    def test_given_two_engaged_regiments_with_different_initiative_when_ticked_one_full_turn_then_each_strikes_exactly_once(self):
        high_i = _regiment("hi", 0, 0, Side.PLAYER, initiative=10, speed_per_tick=0.0)
        low_i = _regiment("lo", 10, 0, Side.ENEMY, initiative=1, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [high_i, low_i], seed=1)
        _join_fight(battle, "g", high_i, low_i, turn=100)  # next_test_turn far ahead: never due here

        events = _run(battle, combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN)

        strikes = [e for e in events if e.kind == "melee_strike"]
        self.assertEqual(sum(1 for e in strikes if e.data["attacker"] == "hi"), 1)
        self.assertEqual(sum(1 for e in strikes if e.data["attacker"] == "lo"), 1)
        self.assertEqual(next(e for e in strikes if e.data["attacker"] == "hi").data["segment"], 10)
        self.assertEqual(next(e for e in strikes if e.data["attacker"] == "lo").data["segment"], 1)


class BreakTestTimingTests(unittest.TestCase):
    """game_rules.md 6.2: the first break test result comes two turns after contact."""

    def setUp(self):
        # A clear winner (more attacks, better WS/S) against a weaker but not instantly wiped-out
        # defender, both with matching Initiative so both strike every turn; seed 3 makes the winner
        # (the attacker) eventually fail its own Leadership test in this particular matchup.
        self.attacker = _regiment("att", 0, 0, Side.PLAYER, ws=4, strength=4, attacks=1, leadership=8,
                                  initiative=10, models=20, ranks=4, speed_per_tick=0.0)
        self.defender = _regiment("def", 10, 0, Side.ENEMY, ws=3, toughness=3, armour=0, leadership=7,
                                  initiative=10, models=20, ranks=4, speed_per_tick=0.0)
        self.battle = Battle(1000, 1000, [self.attacker, self.defender], seed=3)

    def test_given_a_fresh_contact_when_ticked_through_two_turns_then_no_break_test_happens_yet(self):
        # The result is evaluated in the grid's own creation segment two turns on, so nothing can
        # happen within the first two full turns.
        turn_ticks = combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN
        events = _run(self.battle, turn_ticks * 2)

        self.assertNotIn("leadership_test", [e.kind for e in events])

    def test_given_a_fresh_contact_when_ticked_past_two_turns_then_a_break_test_happens(self):
        events = _run(self.battle, combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 2 + combat.SEGMENT_TICKS * 10)

        self.assertIn("leadership_test", [e.kind for e in events])

    def test_given_a_clanrats_style_charge_when_ticked_through_the_first_turn_then_the_defender_does_not_rout(self):
        # game_rules.md's BF001 diagnosis: a 3-0 first round used to trigger an immediate failed break
        # test and instant rout. With traced timing, no break test at all can happen in the first turn.
        clanrats = _regiment("clanrats", 0, 0, Side.PLAYER, ws=3, strength=3, attacks=1, leadership=7,
                              initiative=4, models=13, ranks=3, speed_per_tick=0.0)
        infantry = _regiment("infantry", 10, 0, Side.ENEMY, ws=3, strength=3, toughness=3, attacks=1,
                             leadership=7, initiative=4, models=16, ranks=4, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [clanrats, infantry], seed=1)

        _run(battle, combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN)

        self.assertFalse(infantry.routing)
        self.assertFalse(clanrats.routing)


class DisengagementTests(unittest.TestCase):
    """game_rules.md 5.7, "Leaving": a unit leaves a fight on destruction, rout, or when no enemy
    remains on it -- not when its own footprint drifts apart, and not when the one enemy it happened
    to be touching leaves while the fight goes on."""

    def test_given_an_ally_still_fighting_when_one_enemy_routs_then_the_others_stay_engaged(self):
        # Two player regiments and two enemies share one fight; one enemy routs. Nobody may leave:
        # the other enemy is still standing in the same fight.
        left = _regiment("left", 0, 0, Side.PLAYER, initiative=5, speed_per_tick=0.0)
        right = _regiment("right", 30, 0, Side.PLAYER, initiative=5, speed_per_tick=0.0)
        first = _regiment("e_first", 0, 12, Side.ENEMY, initiative=5, speed_per_tick=0.0)
        second = _regiment("e_second", 30, 12, Side.ENEMY, initiative=5, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [left, right, first, second], seed=0)
        _join_fight(battle, "g", left, right, first, second)
        first.routing = True  # one enemy has broken; the other has not

        combat.refresh_melee_state(battle)

        self.assertTrue(left.in_melee)
        self.assertTrue(right.in_melee)
        self.assertEqual(left.melee_group, "g")

    def test_given_no_enemy_left_in_the_fight_when_refreshed_then_the_unit_disengages(self):
        player = _regiment("p", 0, 0, Side.PLAYER, initiative=5, speed_per_tick=0.0)
        enemy = _regiment("e", 0, 12, Side.ENEMY, initiative=5, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [player, enemy], seed=0)
        _join_fight(battle, "g", player, enemy)
        enemy.routing = True

        combat.refresh_melee_state(battle)

        self.assertFalse(player.in_melee)
        self.assertIsNone(player.melee_group)

    def test_given_a_shrinking_formation_when_its_footprint_pulls_apart_then_it_stays_engaged(self):
        # Casualties shrink a block's footprint, which must never by itself end a close combat.
        player = _regiment("p", 0, 0, Side.PLAYER, models=20, ranks=4, initiative=5, speed_per_tick=0.0)
        enemy = _regiment("e", 0, 300, Side.ENEMY, models=20, ranks=4, initiative=5, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [player, enemy], seed=0)
        _join_fight(battle, "g", player, enemy)  # engaged, but far apart: geometry must not matter

        combat.kill_models(player, list(range(16)), battle=battle)  # down to 4 models
        combat.kill_models(enemy, list(range(16)), battle=battle)
        combat.refresh_melee_state(battle)
        combat.resolve_contacts(battle)

        self.assertTrue(player.in_melee)
        self.assertTrue(enemy.in_melee)


class PursuitTests(unittest.TestCase):
    """game_rules.md 7.5: the routed unit's opponents switch to another opponent in the same fight if
    there is one, and otherwise pursue."""

    def test_given_a_lone_opponent_when_it_routs_then_the_winner_pursues_it(self):
        winner = _regiment("w", 0, 0, Side.PLAYER, initiative=5, leadership=9, speed_per_tick=1.0)
        loser = _regiment("l", 0, 12, Side.ENEMY, initiative=5, leadership=2, speed_per_tick=1.0)
        battle = Battle(1000, 1000, [winner, loser], seed=0)
        _join_fight(battle, "g", winner, loser)

        combat.start_rout(loser, battle)

        self.assertEqual(winner.attack_target, "l")
        self.assertIn("pursuit_start", [e.kind for e in battle.events])

    def test_given_another_enemy_in_the_fight_when_one_routs_then_the_winner_does_not_pursue(self):
        winner = _regiment("w", 0, 0, Side.PLAYER, initiative=5, speed_per_tick=1.0)
        loser = _regiment("l", 0, 12, Side.ENEMY, initiative=5, speed_per_tick=1.0)
        other = _regiment("o", 12, 0, Side.ENEMY, initiative=5, speed_per_tick=1.0)
        battle = Battle(1000, 1000, [winner, loser, other], seed=0)
        _join_fight(battle, "g", winner, loser, other)

        combat.start_rout(loser, battle)

        self.assertIsNone(winner.attack_target)
        self.assertNotIn("pursuit_start", [e.kind for e in battle.events])

    def test_given_a_pursuit_order_when_the_winner_leaves_the_fight_then_the_order_survives(self):
        # Leaving a fight must not cancel the unit's order: the pursuit is granted on the tick the
        # last enemy breaks, and `refresh_melee_state` releases the winner on the very next one.
        winner = _regiment("w", 0, 0, Side.PLAYER, initiative=5, speed_per_tick=1.0)
        loser = _regiment("l", 0, 12, Side.ENEMY, initiative=5, speed_per_tick=1.0)
        battle = Battle(1000, 1000, [winner, loser], seed=0)
        _join_fight(battle, "g", winner, loser)
        combat.start_rout(loser, battle)
        self.assertEqual(winner.attack_target, "l")

        combat.refresh_melee_state(battle)

        self.assertFalse(winner.in_melee)
        self.assertEqual(winner.attack_target, "l")

    def test_given_player_missile_troops_when_their_opponent_routs_then_they_hold(self):
        archers = _regiment("a", 0, 0, Side.PLAYER, initiative=5, speed_per_tick=1.0,
                            missile_code=2, missile_range=720.0)
        loser = _regiment("l", 0, 12, Side.ENEMY, initiative=5, speed_per_tick=1.0)
        battle = Battle(1000, 1000, [archers, loser], seed=0)
        _join_fight(battle, "g", archers, loser)

        combat.start_rout(loser, battle)

        self.assertIsNone(archers.attack_target)


class RoutPauseTests(unittest.TestCase):
    def test_given_resting_models_when_the_unit_breaks_then_they_scatter_and_pause_by_stagger(self):
        fleeing = _regiment("f", 100, 100, Side.ENEMY, models=2, ranks=1)
        battle = Battle(1000, 1000, [fleeing], seed=0)
        before = list(fleeing.model_positions())
        fleeing.melee_models[0].stagger = 0
        fleeing.melee_models[1].stagger = 7

        combat.start_rout(fleeing, battle)

        self.assertEqual([model.rout_pause_ticks for model in fleeing.melee_models], [6, 27])
        self.assertEqual(fleeing.positions, [(before[0][0] - 1, before[0][1] - 1),
                                             (before[1][0] + 1, before[1][1] + 1)])

    def test_given_a_model_already_walking_when_the_unit_breaks_then_it_gets_no_pause(self):
        fleeing = _regiment("f", 100, 100, Side.ENEMY, models=1)
        battle = Battle(1000, 1000, [fleeing], seed=0)
        before = fleeing.model_positions()[0]
        fleeing.melee_models[0].at_rest = False

        combat.start_rout(fleeing, battle)

        self.assertEqual(fleeing.melee_models[0].rout_pause_ticks, 0)
        self.assertEqual(fleeing.positions[0], before)

    def test_given_a_paired_opponent_when_a_resting_model_breaks_then_both_pause(self):
        fleeing = _regiment("f", 100, 100, Side.ENEMY, models=1)
        winner = _regiment("w", 100, 112, Side.PLAYER, models=1)
        battle = Battle(1000, 1000, [fleeing, winner], seed=0)
        _join_fight(battle, "g", fleeing, winner)
        fleeing.model_positions()
        winner.model_positions()
        fleeing.melee_models[0].stagger = 5
        fleeing.melee_models[0].opponent = (winner.identifier, winner.melee_models[0].uid)
        winner.melee_models[0].opponent = (fleeing.identifier, fleeing.melee_models[0].uid)

        combat.start_rout(fleeing, battle)

        self.assertEqual(fleeing.melee_models[0].rout_pause_ticks, 21)
        self.assertEqual(winner.melee_models[0].rout_pause_ticks, 21)

    def test_given_a_paused_router_when_the_pause_expires_then_its_model_can_walk(self):
        fleeing = _regiment("f", 100, 100, Side.ENEMY, models=1, speed_per_tick=1.0)
        battle = Battle(1000, 1000, [fleeing], seed=0)
        fleeing.model_positions()
        fleeing.melee_models[0].stagger = 0
        combat.start_rout(fleeing, battle)
        before = fleeing.positions[0]
        fleeing.x += 30

        for _ in range(6):
            battle._advance_models(fleeing, 1)
            self.assertEqual(fleeing.positions[0], before)
        battle._advance_models(fleeing, 1)

        self.assertNotEqual(fleeing.positions[0], before)


class MountedMeleeTests(unittest.TestCase):
    def _strike(self, armour, mount, counter):
        rider = _regiment("r", 100, 100, Side.PLAYER, models=1, ranks=1, ws=4,
                          strength=2, attacks=1, armour=armour, mount=mount)
        defender = _regiment("d", 100, 112, Side.ENEMY, models=1, ranks=1, ws=3,
                             toughness=4, armour=0)
        battle = Battle(1000, 1000, [rider, defender], seed=0)
        _join_fight(battle, "g", rider, defender)
        rider.model_positions()
        defender.model_positions()
        rider.charge_counter = counter
        pair = (0, rider.melee_models[0], defender, 0)
        with patch.object(combat.battle_grid, "fighting_models", return_value=[pair]):
            combat._strike_with_models(rider, "g", battle.fights["g"], 0, 1, battle)
        return battle.events[-1], rider, defender

    def test_given_a_mounted_model_when_it_strikes_then_rider_and_mount_roll_separately(self):
        event, rider, _defender = self._strike(8, 1, 2)

        self.assertEqual([detail["source"] for detail in event.data["attacks"]],
                         ["rider", "mount"])
        self.assertEqual([detail["attacks"] for detail in event.data["attacks"]], [1, 1])
        self.assertEqual([detail["wound_need"] for detail in event.data["attacks"]], [5, 3])
        self.assertEqual(rider.charge_counter, 0)

    def test_given_mount_code_without_mounted_armour_when_it_strikes_then_only_rider_rolls(self):
        event, rider, _defender = self._strike(0, 1, 2)

        self.assertEqual([detail["source"] for detail in event.data["attacks"]], ["rider"])
        # game_rules.md 5.5: a foot model's round consumes the counter twice -- once for the +1 S
        # grant, once more once its round is resolved.
        self.assertEqual(rider.charge_counter, 0)

    def test_given_a_mount_with_two_attacks_when_it_strikes_then_it_uses_its_own_attack_count(self):
        event, _rider, _defender = self._strike(8, 4, 0)

        self.assertEqual([detail["attacks"] for detail in event.data["attacks"]], [1, 2])
        self.assertEqual(event.data["attacks"][1]["wound_need"], 3)

    def test_given_a_mounted_rider_when_wounded_then_rider_and_mount_die_together_as_one_model(self):
        # game_rules.md "Mounts": "single wound counter, rider's T/W only, the mount is never
        # separately wounded or killed" -- a mounted model has exactly one ModelState (there is no
        # second, mount-only model to wound or remove independently), whatever the mount's own
        # T/W happen to be in MOUNT_PROFILES; killing the model removes rider and mount together.
        rider = _regiment("r", 100, 100, Side.PLAYER, models=1, ranks=1, toughness=8,
                          armour=8, mount=1)  # Warhorse: T3 W1, well below the rider's own T8
        rider.model_positions()

        self.assertEqual(len(rider.melee_models), 1)

        killed = combat.kill_models(rider, [0], battle=Battle(1000, 1000, [rider]))

        self.assertEqual(killed, 1)
        self.assertEqual(rider.models, 0)


class ChargeCounterConsumptionTests(unittest.TestCase):
    """game_rules.md 5.5: consumed at two points per attacking foot model per round -- once for the
    +1 S grant, once more once that model's round is resolved -- so the bonus only covers the
    opening exchange (roughly half the budget's worth of models), not a fixed model count."""

    def _strike_two_models(self, counter):
        attacker = _regiment("a", 100, 100, Side.PLAYER, models=2, ranks=1, ws=4, strength=2, attacks=1)
        defender = _regiment("d", 100, 112, Side.ENEMY, models=2, ranks=1, ws=3, toughness=4, armour=0)
        battle = Battle(1000, 1000, [attacker, defender], seed=0)
        _join_fight(battle, "g", attacker, defender)
        attacker.model_positions()
        defender.model_positions()
        attacker.charge_counter = counter
        pairs = [(0, attacker.melee_models[0], defender, 0), (1, attacker.melee_models[1], defender, 1)]
        with patch.object(combat.battle_grid, "fighting_models", return_value=pairs):
            combat._strike_with_models(attacker, "g", battle.fights["g"], 0, 1, battle)
        return battle.events[-1], attacker

    def test_given_a_budget_for_both_models_when_they_strike_then_each_consumes_two(self):
        event, attacker = self._strike_two_models(5)

        self.assertEqual([detail["charge_bonus"] for detail in event.data["attacks"]], [1, 1])
        self.assertEqual(attacker.charge_counter, 1)  # 5 - 2 - 2

    def test_given_a_budget_for_only_the_first_model_when_they_strike_then_only_it_gets_the_bonus(self):
        event, attacker = self._strike_two_models(1)

        self.assertEqual([detail["charge_bonus"] for detail in event.data["attacks"]], [1, 0])
        self.assertEqual(attacker.charge_counter, 0)


class ContactAttackTests(unittest.TestCase):
    """game_rules.md 7.7: a pursuer cannot re-engage a fleeing unit, so contact attacks are the only
    damage a chase does -- automatic hits, to-wound and save only."""

    def test_given_a_pursuer_in_reach_when_a_segment_passes_then_it_cuts_down_fugitives(self):
        chaser = _regiment("c", 0, 0, Side.PLAYER, strength=6, attacks=2, speed_per_tick=0.0)
        fleeing = _regiment("f", 0, 6, Side.ENEMY, toughness=2, armour=0, speed_per_tick=0.0)
        fleeing.routing = True
        battle = Battle(1000, 1000, [chaser, fleeing], seed=1)
        chaser.attack_target = "f"

        combat.resolve_contact_attacks(battle)

        events = [e for e in battle.events if e.kind == "contact_attack"]
        self.assertEqual(len(events), 1)
        self.assertGreater(events[0].data["kills"], 0)
        # Automatic hits: every roll records a wound roll and never a to-hit roll.
        for roll in events[0].data["rolls"]:
            self.assertIn("wound", roll)
            self.assertNotIn("hit", roll)

    def test_given_a_target_out_of_reach_when_a_segment_passes_then_nothing_happens(self):
        chaser = _regiment("c", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        fleeing = _regiment("f", 0, 600, Side.ENEMY, speed_per_tick=0.0)
        fleeing.routing = True
        battle = Battle(1000, 1000, [chaser, fleeing], seed=1)
        chaser.attack_target = "f"

        combat.resolve_contact_attacks(battle)

        self.assertEqual([e for e in battle.events if e.kind == "contact_attack"], [])

    def test_given_a_standing_enemy_when_a_segment_passes_then_no_contact_attacks_are_made(self):
        # Contact attacks are for fugitives; a standing enemy is fought in close combat instead.
        chaser = _regiment("c", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        standing = _regiment("s", 0, 6, Side.ENEMY, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [chaser, standing], seed=1)
        chaser.attack_target = "s"

        combat.resolve_contact_attacks(battle)

        self.assertEqual([e for e in battle.events if e.kind == "contact_attack"], [])


class EngagementGeometryTests(unittest.TestCase):
    """game_rules.md, "What triggers engagement": real footprint overlap, not proximity."""

    def test_given_footprints_that_only_come_close_when_checked_then_they_do_not_engage(self):
        first = _regiment("a", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        second = _regiment("b", 0, 30, Side.ENEMY, speed_per_tick=0.0)

        self.assertFalse(formation.penetrates(first.block(), second.block()))

    def test_given_overlapping_footprints_when_checked_then_they_engage(self):
        first = _regiment("a", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        second = _regiment("b", 0, 14, Side.ENEMY, speed_per_tick=0.0)

        self.assertTrue(formation.penetrates(first.block(), second.block()))

    def test_given_a_regiment_in_contact_when_it_turns_then_the_contact_survives_the_turn(self):
        # The footprint is built around the block centre, and the original moves the unit position on
        # every turn so that centre stays put; turning the anchor in place would swing it away.
        first = _regiment("a", 0, 0, Side.PLAYER, models=20, ranks=4, speed_per_tick=0.0)
        second = _regiment("b", 0, 40, Side.ENEMY, models=20, ranks=4, speed_per_tick=0.0)
        self.assertTrue(formation.penetrates(first.block(), second.block()))

        Battle.turn_to(second, 256)

        self.assertTrue(formation.penetrates(first.block(), second.block()))


class PlayerNeutralNeverFightTests(unittest.TestCase):
    """rules.can_fight: Player and Neutral never engage in close combat, even from pure footprint
    contact -- user-corrected from a real playthrough where NPC peasant regiments ended up fighting
    the player's own infantry just from bumping into them. Enemy and Neutral can still fight (that
    is how a mission's own scripted threat against neutrals, e.g. AttackNearestFlag40Unit, actually
    plays out physically); only the Player-Neutral pair is excluded."""

    def test_overlapping_player_and_neutral_footprints_do_not_engage(self):
        player = _regiment("player", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        peasant = _regiment("peasant", 0, 14, Side.NEUTRAL, speed_per_tick=0.0)
        battle = Battle(500, 500, [player, peasant], seed=1995)

        battle.tick()

        self.assertFalse(player.in_melee)
        self.assertFalse(peasant.in_melee)
        self.assertEqual(battle.events, [])

    def test_overlapping_enemy_and_neutral_footprints_still_engage(self):
        enemy = _regiment("enemy", 0, 0, Side.ENEMY, speed_per_tick=0.0)
        peasant = _regiment("peasant", 0, 14, Side.NEUTRAL, speed_per_tick=0.0)
        battle = Battle(500, 500, [enemy, peasant], seed=1995)

        battle.tick()

        self.assertTrue(enemy.in_melee)
        self.assertTrue(peasant.in_melee)

    def test_overlapping_player_and_enemy_footprints_still_engage(self):
        player = _regiment("player", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        enemy = _regiment("enemy", 0, 14, Side.ENEMY, speed_per_tick=0.0)
        battle = Battle(500, 500, [player, enemy], seed=1995)

        battle.tick()

        self.assertTrue(player.in_melee)
        self.assertTrue(enemy.in_melee)

    def test_player_walking_into_a_stationary_neutral_does_not_fight_over_many_ticks(self):
        # A player regiment ordered to move straight through a stationary peasant regiment must
        # never end up fighting it (the collision push-apart deflects the moving party; a standing
        # regiment never gives way, matching _resolve_collisions' existing "standing regiments never
        # give way" rule for same-side pairs -- see test_engine.py's CollisionTests).
        player = _regiment("player", 0, 0, Side.PLAYER, models=10, ranks=2)
        peasant = _regiment("peasant", 0, 5, Side.NEUTRAL, models=10, ranks=2, speed_per_tick=0.0)
        battle = Battle(500, 500, [player, peasant], seed=1995)
        battle.order_move("player", 0, 100)

        for _ in range(20):
            battle.tick()

        self.assertFalse(player.in_melee)
        self.assertFalse(peasant.in_melee)
        self.assertEqual(peasant.models, 10)  # never took casualties


class RankAndDirectionBonusTests(unittest.TestCase):
    """game_rules.md 6.1: rank bonus (deep formations) and direction bonus (flank/rear attacks)."""

    def test_given_a_shallow_formation_when_the_rank_bonus_is_computed_then_it_is_zero(self):
        shallow = _regiment("s", 0, 0, Side.PLAYER, models=6, ranks=2)  # frontage 3, not > 3
        self.assertEqual(combat._rank_bonus(shallow), 0)

    def test_given_a_deep_formation_when_the_rank_bonus_is_computed_then_it_counts_the_ranks_behind_the_first(self):
        deep = _regiment("d", 0, 0, Side.PLAYER, models=16, ranks=4)  # frontage 4, size/width - 1 = 3
        self.assertEqual(combat._rank_bonus(deep), 3)

    def test_given_an_attack_from_the_front_when_the_direction_bonus_is_computed_then_it_is_zero(self):
        defender = _regiment("def", 0, 0, Side.ENEMY, direction=0)  # direction 0 faces +Y (formation.place)
        attacker = _regiment("att", 0, 10, Side.PLAYER)  # in front of the defender's facing
        self.assertEqual(combat._direction_bonus(attacker, defender), 0)

    def test_given_an_attack_from_the_rear_when_the_direction_bonus_is_computed_then_it_is_two(self):
        defender = _regiment("def", 0, 0, Side.ENEMY, direction=0)
        attacker = _regiment("att", 0, -10, Side.PLAYER)  # behind the defender's facing
        self.assertEqual(combat._direction_bonus(attacker, defender), 2)

    def test_given_an_attack_from_the_flank_when_the_direction_bonus_is_computed_then_it_is_one(self):
        defender = _regiment("def", 0, 0, Side.ENEMY, direction=0)
        attacker = _regiment("att", 10, 0, Side.PLAYER)  # to the defender's side
        self.assertEqual(combat._direction_bonus(attacker, defender), 1)

    def test_given_a_kill_deficit_smaller_than_the_rank_bonus_when_the_break_test_is_due_then_the_deep_unit_does_not_lose_the_result(self):
        deep = _regiment("deep", 0, 0, Side.PLAYER, leadership=7)
        shallow = _regiment("shallow", 10, 0, Side.ENEMY, leadership=7)
        battle = Battle(1000, 1000, [deep, shallow], seed=0)
        _join_fight(battle, "g", deep, shallow, turn=0)
        # 1 kill behind, +3 rank bonus already folded in: the deep unit is not on the losing side.
        battle.fights["g"]["tally"] = {Side.PLAYER: 3.0, Side.ENEMY: 2.0}

        combat._resolve_group_break_test("g", [deep, shallow], 2, battle)

        deep_tests = [e for e in battle.events if e.kind == "leadership_test" and e.data["regiment"] == "deep"]
        self.assertEqual(deep_tests, [])

    def test_given_a_kill_deficit_without_a_rank_bonus_when_the_break_test_is_due_then_the_loser_is_tested(self):
        loser = _regiment("loser", 0, 0, Side.PLAYER, leadership=7)
        winner = _regiment("winner", 10, 0, Side.ENEMY, leadership=7)
        battle = Battle(1000, 1000, [loser, winner], seed=0)
        _join_fight(battle, "g", loser, winner, turn=0)
        battle.fights["g"]["tally"] = {Side.PLAYER: 0.0, Side.ENEMY: 2.0}

        combat._resolve_group_break_test("g", [loser, winner], 2, battle)

        leadership = [e for e in battle.events if e.kind == "leadership_test"]
        self.assertEqual(len(leadership), 1)
        self.assertEqual(leadership[0].data["regiment"], "loser")


class FleeBearingTests(unittest.TestCase):
    """game_rules.md "Flight and catching fleeing units": the flight "starts... directly away from
    its opponent" - a bearing fixed once at rout start, not re-aimed every tick at whichever enemy
    is currently nearest. Recomputing it live let two pursuers converging on the same fleeing unit
    from different sides flip which one counted as "nearest" every tick as their distances crossed
    over, reversing the flee bearing each time and stalling everyone in place indefinitely -
    reported as a cavalry charge that never seemed to catch and kill a fleeing goblin unit while a
    second friendly regiment was also chasing it."""

    def test_given_a_routing_unit_then_the_flee_bearing_is_computed_once_not_every_tick(self):
        fleeing = _regiment("f", 500, 500, Side.ENEMY, speed_per_tick=4.0)
        enemy = _regiment("e", 500, 470, Side.PLAYER, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [fleeing, enemy], seed=0)
        combat.start_rout(fleeing, battle)
        calls = []
        original = battle.flee_point
        battle.flee_point = lambda regiment: calls.append(regiment.identifier) or original(regiment)

        for _ in range(10):
            battle.tick()

        self.assertEqual(calls, [])  # never recomputed once the rout has started

    def test_given_two_pursuers_converging_from_different_sides_then_the_fugitive_still_escapes(self):
        fleeing = _regiment("f", 500, 500, Side.ENEMY, speed_per_tick=4.0, initiative=5)
        cavalry = _regiment("cav", 500, 470, Side.PLAYER, speed_per_tick=10.0, initiative=5,
                            attack_target="f")
        infantry = _regiment("inf", 470, 500, Side.PLAYER, speed_per_tick=4.0, initiative=5,
                             attack_target="f")
        edge = {"status": ["bnd_ACTIVE", "bnd_BATTLEEDGE"],
                "lines": [[0, 0, 1000, 0], [1000, 0, 1000, 1000],
                          [1000, 1000, 0, 1000], [0, 1000, 0, 0]]}
        battle = Battle(1000, 1000, [fleeing, cavalry, infantry], seed=0, boundaries=[edge])
        fleeing.routing = True
        fleeing.flee_x, fleeing.flee_y = battle.flee_point(fleeing)
        start_x, start_y = fleeing.x, fleeing.y

        for _ in range(30):
            battle.tick()

        moved = math.hypot(fleeing.x - start_x, fleeing.y - start_y)
        self.assertGreater(moved, 20.0)  # real progress, not stuck oscillating in place


class RallyTimingTests(unittest.TestCase):
    """game_rules.md 7.4: the first rally attempt is one full turn after the rout, then every 3 segments."""

    def test_given_a_regiment_that_just_routed_when_checked_before_its_scheduled_segment_then_no_attempt_is_made(self):
        routing = _regiment("r", 0, 0, Side.PLAYER, leadership=9, routing=True, rally_next_segment=5)
        enemy = _regiment("e", 1000, 1000, Side.ENEMY)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)
        battle.tick_count = 4 * combat.SEGMENT_TICKS  # absolute_segment 4, still before segment 5

        combat.resolve_rally(battle)

        self.assertEqual(battle.events, [])
        self.assertTrue(routing.routing)

    def test_given_a_regiment_whose_scheduled_segment_has_come_when_checked_then_an_attempt_is_made(self):
        routing = _regiment("r", 0, 0, Side.PLAYER, leadership=9, routing=True, rally_next_segment=5)
        enemy = _regiment("e", 1000, 1000, Side.ENEMY)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)
        battle.tick_count = 5 * combat.SEGMENT_TICKS

        combat.resolve_rally(battle)

        self.assertEqual([e.kind for e in battle.events], ["rally_test"])

    def test_given_a_regiment_starting_to_rout_when_the_rout_begins_then_its_first_rally_attempt_is_scheduled_one_turn_later(self):
        attacker = _regiment("att", 0, 0, Side.PLAYER, ws=4, strength=4, attacks=1, leadership=8, initiative=10,
                             models=20, ranks=4, speed_per_tick=0.0)
        defender = _regiment("def", 10, 0, Side.ENEMY, ws=3, toughness=3, armour=0, leadership=7,
                             initiative=10, models=20, ranks=4, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [attacker, defender], seed=3)  # eventually the attacker breaks first
        rout_event, segment_at_rout = None, None
        for _ in range(combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 3):
            battle.tick()
            found = next((e for e in battle.events if e.kind == "rout_start"), None)
            if found is not None:
                rout_event = found
                segment_at_rout = battle.tick_count // combat.SEGMENT_TICKS
                break

        self.assertIsNotNone(rout_event)
        routed = battle.regiments[rout_event.data["regiment"]]
        self.assertTrue(routed.routing)
        self.assertEqual(routed.rally_next_segment, segment_at_rout + combat.SEGMENTS_PER_TURN)


class CasualtiesAndCantRallyTests(unittest.TestCase):
    def test_given_no_enemy_nearby_when_the_leadership_test_passes_then_the_unit_rallies(self):
        routing = _regiment("r", 0, 0, Side.PLAYER, leadership=9, routing=True, rally_next_segment=0)
        enemy = _regiment("e", 1000, 1000, Side.ENEMY)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)  # seed 0: the roll passes Ld 9

        combat.resolve_rally(battle)

        self.assertFalse(routing.routing)
        rally = battle.events[-1]
        self.assertEqual(rally.kind, "rally_test")
        self.assertTrue(rally.data["passed"])

    def test_given_an_enemy_within_the_safe_distance_when_checked_then_no_rally_is_attempted(self):
        routing = _regiment("r", 0, 0, Side.PLAYER, leadership=9, routing=True, rally_next_segment=0)
        enemy = _regiment("e", 50, 0, Side.ENEMY)  # well within FLEE_SAFE_DISTANCE
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)
        self.assertTrue(battle.events[-1].data["blocked_by_enemy"])

    def test_given_cant_rally_psychology_when_checked_then_the_unit_never_rallies(self):
        routing = _regiment("r", 0, 0, Side.PLAYER, leadership=9, routing=True, rally_next_segment=0,
                            psychology=frozenset({"CantRally"}))
        enemy = _regiment("e", 1000, 1000, Side.ENEMY)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)

    def test_given_casualties_at_or_below_a_quarter_of_strength_when_checked_then_the_unit_cannot_rally(self):
        routing = _regiment("r", 0, 0, Side.PLAYER, leadership=9, routing=True, rally_next_segment=0,
                            models=2, original_models=10)  # 8 casualties >= 3 x 2 models left
        enemy = _regiment("e", 1000, 1000, Side.ENEMY)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)
        self.assertTrue(battle.events[-1].data["too_many_casualties"])

    def test_given_a_regiment_that_has_fled_the_field_when_checked_then_it_is_never_offered_a_rally_attempt(self):
        # Bug: fled regiments (routing off the map edge) kept passing rally tests and returning, because
        # resolve_rally only checked `routing`, never `active` (which `fled` makes permanently False).
        fled = _regiment("r", 0, 0, Side.PLAYER, leadership=9, routing=True, fled=True, rally_next_segment=0)
        enemy = _regiment("e", 1000, 1000, Side.ENEMY)
        battle = Battle(2000, 2000, [fled, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertEqual(battle.events, [])
        self.assertTrue(fled.routing)
        self.assertTrue(fled.fled)
        self.assertFalse(fled.active)


class CloseCombatStrikeTests(unittest.TestCase):
    """Given fixed statistics, dice seed, formation, and range, an attack produces the documented
    casualties and emitted battle events (docs/testing.md, "Combat")."""

    def setUp(self):
        # A hard-hitting attacker (WS5, S5, A2) against a weak, low-Leadership defender (WS1, T1, no
        # armour, Ld2), both Initiative 10 so they clash and strike on the very same tick; seed 1 is
        # fixed so the round's exact casualties are reproducible.
        self.attacker = _regiment("att", 0, 0, Side.PLAYER, ws=5, strength=5, attacks=2, leadership=8,
                                  initiative=10, speed_per_tick=0.0)
        self.defender = _regiment("def", 14, 0, Side.ENEMY, ws=1, toughness=1, armour=0, leadership=2,
                                  initiative=10, speed_per_tick=1.5)
        self.battle = Battle(1000, 1000, [self.attacker, self.defender], seed=1)
        # No script/AI drives a scriptless battle any more (whshr.ai was removed): give "def" its
        # charge order explicitly so it is still the joining unit whose models must walk into cells,
        # matching this class's scenario ("attacker" stands still and is already placed).
        self.defender.attack_target = "att"

    def test_given_two_touching_regiments_when_ticked_then_they_clash_and_the_engaged_unit_strikes(self):
        # The grid is seeded around the unit that was engaged, so its models already stand in their
        # cells and fight at once; the joining unit's models still have to walk in (game_rules.md 5.7).
        self.battle.tick()

        kinds = [e.kind for e in self.battle.events]
        self.assertEqual(kinds, ["clash", "melee_strike"])
        # No break test yet: the first one is due two turns after contact (game_rules.md 6.2).
        self.assertNotIn("leadership_test", kinds)
        self.assertFalse(self.defender.routing)
        strike = self.battle.events[1]
        self.assertEqual(strike.data["attacker"], "att")
        # Only the models that hold a cell next to an enemy model fight, not the whole front rank.
        self.assertGreater(strike.data["fighting"], 0)
        self.assertLessEqual(strike.data["fighting"], self.attacker.models)
        self.assertEqual(self.defender.models, 10 - strike.data["kills"])

    def test_given_a_joining_unit_when_its_models_have_walked_in_then_it_strikes_back(self):
        # The joining unit's models start outside their cells and must walk in before they may fight.
        strikers = set()
        for _ in range(combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 2):
            self.battle.tick()
            strikers.update(e.data["attacker"] for e in self.battle.events if e.kind == "melee_strike")

        self.assertTrue(any(model.arrived for model in self.defender.melee_models))
        self.assertEqual(strikers, {"att", "def"})

    def test_given_more_casualties_than_models_when_applied_then_it_is_clamped_to_the_current_size(self):
        removed = combat.apply_casualties(self.defender, 999, self.battle.rng, self.battle)

        self.assertEqual(removed, 10)
        self.assertEqual(self.defender.models, 0)
        self.assertTrue(self.defender.destroyed)

    def test_given_casualties_when_applied_then_the_formation_shrinks_and_leaves_corpses(self):
        combat.apply_casualties(self.defender, 3, self.battle.rng, self.battle)

        self.assertEqual(self.defender.models, 7)
        # Casualties keep playing their animation until they collapse (game_rules.md "Figure animation").
        self.assertEqual(len(self.defender.corpses) + len(self.defender.dying), 3)
        self.assertEqual(len(self.defender.model_positions()), 7)

    def test_given_a_cant_die_defender_when_casualties_are_applied_then_no_models_are_removed(self):
        # game_rules.md 7.6: CantDie models are never removed by wounds.
        immortal = _regiment("i", 0, 0, Side.ENEMY, psychology=frozenset({"CantDie"}))

        removed = combat.apply_casualties(immortal, 5, self.battle.rng, self.battle)

        self.assertEqual(removed, 0)
        self.assertEqual(immortal.models, 10)
        self.assertEqual(immortal.corpses, [])


class ShootingTests(unittest.TestCase):
    def setUp(self):
        # Crossbows (missile code 2), BS5, facing north at a target directly north and in arc.
        self.shooter = _regiment("s", 0, 0, Side.PLAYER, bs=5, missile_code=2, missile_range=720.0,
                                 speed_per_tick=0.0)
        self.target = _regiment("t", 0, 300, Side.ENEMY, toughness=3, armour=0, speed_per_tick=0.0)
        self.battle = Battle(2000, 2000, [self.shooter, self.target], seed=0)

    def _tick_until_volley(self, limit=12):
        """Volleys resolve once all fire events have arrived (a few ticks after the shoot pose begins)."""
        for _ in range(limit):
            self.battle.tick()
            if any(getattr(e, "kind", "") == "shooting" for e in self.battle.events):
                return
        self.fail("no volley within %d ticks" % limit)

    def test_given_a_target_in_range_and_arc_when_ticked_then_it_fires_and_reloads(self):
        self._tick_until_volley()

        self.assertTrue(any(str(e).startswith("s shoots t:") for e in self.battle.events))
        # game_rules.md 8.2: reload is stamped at order time; by the volley tick (~5 ticks later)
        # about 91 of the original 96 ticks remain.
        self.assertGreater(self.shooter.reload_ticks, 90)

    def test_given_a_target_outside_the_front_arc_when_ticked_then_it_does_not_fire(self):
        self.target.x, self.target.y = 300.0, 0.0  # due east: outside the +/-45 degree arc facing north

        self.battle.tick()

        self.assertEqual(self.target.models, 10)
        self.assertEqual(self.shooter.reload_ticks, 0.0)

    def test_given_a_reloading_shooter_when_ticked_then_it_holds_fire_until_ready(self):
        self._tick_until_volley()
        volleys = [1]  # the first volley's own tick

        def run(ticks):
            for _ in range(ticks):
                self.battle.tick()
                volleys[0] += sum(1 for e in self.battle.events if getattr(e, "kind", "") == "shooting")

        run(int(self.shooter.reload_ticks) - 1)
        self.assertEqual(volleys[0], 1)  # still reloading
        self.assertGreater(self.shooter.reload_ticks, 0)

        run(12)  # ready again: fires as soon as the next fire events arrive

        self.assertEqual(volleys[0], 2)


class ChargeBonusEndToEndTests(unittest.TestCase):
    """game_rules.md 5.5, end to end from the contact grant through the strikes that spend it."""

    def _charge_and_strike(self, models, casualties=0):
        charger = _regiment("charger", 0, 0, Side.PLAYER, models=models, ranks=2, ws=4, strength=2, attacks=1)
        target = _regiment("target", 0, 0, Side.ENEMY, models=models, ranks=2, ws=3, toughness=4, armour=0)
        battle = Battle(2000, 2000, [charger, target], seed=0)
        charger.models -= casualties
        charger.attack_target = target.identifier
        combat.resolve_contacts(battle)
        charger.model_positions()
        target.model_positions()
        fighters = min(charger.models, target.models)
        pairs = [(i, charger.melee_models[i], target, i) for i in range(fighters)]
        with patch.object(combat.battle_grid, "fighting_models", return_value=pairs):
            combat._strike_with_models(charger, charger.melee_group,
                                       battle.fights[charger.melee_group], 0, 1, battle)
        return charger, battle.events[-1]

    def test_given_a_full_frontage_charge_when_the_models_strike_then_only_the_opening_models_get_the_bonus(self):
        charger, event = self._charge_and_strike(10)  # frontage 5, budget 7, two drained per model

        self.assertEqual([d["charge_bonus"] for d in event.data["attacks"]], [1, 1, 1, 1] + [0] * 6)
        self.assertEqual(charger.charge_counter, 0)

    def test_given_casualties_before_contact_when_the_models_strike_then_the_bonus_still_covers_the_formed_frontage(self):
        charger, event = self._charge_and_strike(10, casualties=4)  # six models left, formed frontage 5

        self.assertEqual([d["charge_bonus"] for d in event.data["attacks"]], [1, 1, 1, 1, 0, 0])

    def test_given_an_unspent_counter_when_a_new_enemy_engages_it_then_the_counter_is_kept(self):
        charger = _regiment("charger", 0, 0, Side.PLAYER, models=10, ranks=2)
        first = _regiment("first", 0, 0, Side.ENEMY)
        battle = Battle(2000, 2000, [charger, first], seed=0)
        charger.attack_target = first.identifier
        combat.resolve_contacts(battle)
        charger.charge_counter = 3
        first.models = 0
        combat.resolve_contacts(battle)
        charger.attack_target = None

        second = Regiment("second", "second", 0, 0, 0, Side.ENEMY, models=10, ranks=2)
        battle.regiments["second"] = second
        second.attack_target = charger.identifier
        combat.resolve_contacts(battle)

        self.assertTrue(charger.in_melee)
        self.assertEqual(charger.charge_counter, 3)


class ContactAndMeleeStateTests(unittest.TestCase):
    def test_given_casualties_before_a_charge_when_contact_starts_then_the_grant_uses_formed_frontage(self):
        charger = _regiment("charger", 0, 0, Side.PLAYER, models=10, ranks=2)
        target = _regiment("target", 0, 0, Side.ENEMY)
        battle = Battle(2000, 2000, [charger, target], seed=0)
        charger.models = 6  # live front rank shrinks from five models to three
        charger.attack_target = target.identifier

        combat.resolve_contacts(battle)

        self.assertTrue(charger.in_melee)
        self.assertEqual(charger.frontage, 5)
        self.assertEqual(charger.front_rank_models(), 3)
        self.assertEqual(charger.charge_counter, 7)  # floor(1.5 * formed frontage)

    def test_given_a_routing_unit_when_an_enemy_touches_it_then_it_is_not_engaged_in_melee(self):
        routing = _regiment("r", 0, 0, Side.PLAYER, routing=True, speed_per_tick=0.0)
        pursuer = _regiment("p", 5, 0, Side.ENEMY, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [routing, pursuer], seed=0)

        battle.tick()

        self.assertFalse(routing.in_melee)
        self.assertFalse(pursuer.in_melee)

    def test_given_a_fresh_opponent_when_contact_starts_then_a_charge_counter_is_granted(self):
        charger = _regiment("charger", 0, 0, Side.PLAYER, models=10, ranks=2)
        target = _regiment("target", 0, 0, Side.ENEMY)
        battle = Battle(2000, 2000, [charger, target], seed=0)
        charger.attack_target = target.identifier

        combat.resolve_contacts(battle)

        self.assertEqual(charger.charge_counter, int(1.5 * charger.frontage))
        self.assertEqual(charger.last_fought_opponent, target.identifier)

    def test_given_a_regiment_re_engaging_its_last_opponent_when_it_rejoins_then_it_gets_no_bonus(self):
        # game_rules.md 5.5: "re-engaging an opponent you are already fighting sets the counter to 0".
        charger = _regiment("charger", 0, 0, Side.PLAYER, models=10, ranks=2)
        target = _regiment("target", 0, 0, Side.ENEMY)
        battle = Battle(2000, 2000, [charger, target], seed=0)
        charger.attack_target = target.identifier
        combat.resolve_contacts(battle)
        self.assertGreater(charger.charge_counter, 0)

        # Leave the fight (e.g. it broke off) while `target` is still standing, then re-engage it.
        assert charger.melee_group is not None
        battle.fights.pop(charger.melee_group, None)
        for regiment in (charger, target):
            regiment.in_melee = False
            regiment.melee_group = None
            regiment.melee_touching = frozenset()

        combat.resolve_contacts(battle)

        self.assertTrue(charger.in_melee)
        self.assertEqual(charger.charge_counter, 0)

    def test_given_an_unspent_counter_when_a_different_unrelated_fight_starts_then_it_is_untouched(self):
        # game_rules.md 5.5: "nothing clears the counter when a combat ends" -- a regiment that is not
        # itself charging into the new contact keeps whatever it had left, rather than losing it.
        charger = _regiment("charger", 0, 0, Side.PLAYER, models=10, ranks=2)
        first_enemy = _regiment("first", 0, 0, Side.ENEMY)
        battle = Battle(2000, 2000, [charger, first_enemy], seed=0)
        charger.attack_target = first_enemy.identifier
        combat.resolve_contacts(battle)
        charger.charge_counter = 3  # simulate a fight that ended with the budget partly spent

        first_enemy.models = 0  # destroyed: leaves the grid, charge_counter is left alone
        combat.resolve_contacts(battle)
        self.assertFalse(charger.in_melee)
        self.assertEqual(charger.charge_counter, 3)

        second_enemy = Regiment("second", "second", 0, 0, 0, Side.ENEMY, models=10, ranks=2)
        battle.regiments[second_enemy.identifier] = second_enemy
        # `charger` is not the one charging this new opponent (no matching attack_target), so no
        # grant call touches its counter at all -- it simply carries over.
        combat.resolve_contacts(battle)

        self.assertEqual(charger.charge_counter, 3)

    def test_given_footprints_two_model_spacings_apart_when_bounding_circles_overlap_then_they_do_not_clash(self):
        # Two default-shaped regiments (10 models, 2 ranks, both facing +Y) stacked front-to-back: their
        # footprints (half_forward 12 each) are exactly two model spacings (24 units) apart, but their
        # bounding circles (radius ~32) still overlap at that 48-unit centre distance. Must not clash on
        # circle touch, only on the footprints actually meeting (game_rules.md, "Engagement").
        left = _regiment("left", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        right = _regiment("right", 0, 48, Side.ENEMY, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [left, right], seed=0)
        gap = formation.footprint_gap(left.footprint_corners(), right.footprint_corners())
        self.assertAlmostEqual(gap, 2 * formation.MODEL_SPACING, places=6)
        self.assertLess(48.0, left.bounding_radius() + right.bounding_radius())

        battle.tick()

        self.assertEqual([e.kind for e in battle.events if e.kind == "clash"], [])
        self.assertFalse(left.in_melee)
        self.assertFalse(right.in_melee)

    def test_given_a_charging_regiment_when_it_closes_then_it_keeps_moving_until_footprints_touch_then_clashes(self):
        charger = _regiment("charger", 0, 0, Side.PLAYER, models=10, ranks=2, speed_per_tick=6.0)
        target = _regiment("target", 120, 0, Side.ENEMY, models=10, ranks=2, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [charger, target], seed=0)
        battle.order_attack("charger", "target")

        for _ in range(60):
            battle.tick()
            if charger.in_melee:
                break

        self.assertTrue(charger.in_melee)
        self.assertTrue(target.in_melee)
        # Engagement needs the footprints to really overlap, not merely to be close.
        self.assertTrue(formation.penetrates(charger.block(), target.block()))

    def test_given_two_regiments_touching_one_enemy_when_they_clash_then_they_share_one_fight_and_both_strike(self):
        # No 2 vs 1: two player regiments touching the same lone enemy regiment must share a single
        # fight (game_rules.md 5.7's battle grid), and both get to strike it in their own segment.
        left = _regiment("left", 0, 0, Side.PLAYER, initiative=10, speed_per_tick=1.5)
        right = _regiment("right", 10, 12, Side.PLAYER, initiative=10, speed_per_tick=1.5)
        enemy = _regiment("enemy", 10, -10, Side.ENEMY, initiative=10, models=40, ranks=8, speed_per_tick=1.5)
        battle = Battle(2000, 2000, [left, right, enemy], seed=0)

        strikers = set()
        for _ in range(combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 2):
            battle.tick()
            strikers.update(e.data["attacker"] for e in battle.events if e.kind == "melee_strike")

        self.assertTrue(left.in_melee and right.in_melee and enemy.in_melee)
        self.assertEqual(left.melee_group, right.melee_group)
        self.assertEqual(left.melee_group, enemy.melee_group)
        # One grid, one cell pool: every unit's models are placed on the same record.
        grid = battle.fights[left.melee_group]["grid"]
        self.assertEqual({identifier for identifier, _ in grid.cells.values()},
                         {"left", "right", "enemy"})
        self.assertEqual(strikers, {"left", "right", "enemy"})
        fight = battle.fights[left.melee_group]
        self.assertGreater(fight["tally"][Side.PLAYER], 0)  # left and right's kills/bonuses share one tally


class BracedStateTests(unittest.TestCase):
    """game_rules.md "Braced": cleared once the charger it names is gone, or once the braced
    regiment itself joins melee (in_melee already suppresses orders more completely there)."""

    def test_given_a_braced_regiment_when_the_charger_is_no_longer_active_then_it_is_unbraced(self):
        target = _regiment("target", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        charger = _regiment("charger", 500, 500, Side.ENEMY, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [target, charger], seed=0)
        target.braced, target.braced_target = True, "charger"
        charger.models = 0

        combat.refresh_braced_state(battle)

        self.assertFalse(target.braced)
        self.assertIsNone(target.braced_target)

    def test_given_a_braced_regiment_when_the_charger_routs_then_it_is_unbraced(self):
        target = _regiment("target", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        charger = _regiment("charger", 500, 500, Side.ENEMY, speed_per_tick=0.0, routing=True)
        battle = Battle(2000, 2000, [target, charger], seed=0)
        target.braced, target.braced_target = True, "charger"

        combat.refresh_braced_state(battle)

        self.assertFalse(target.braced)
        self.assertIsNone(target.braced_target)

    def test_given_a_braced_regiment_still_facing_an_active_charger_then_it_stays_braced(self):
        target = _regiment("target", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        charger = _regiment("charger", 500, 500, Side.ENEMY, speed_per_tick=0.0)
        charger.attack_target = "target"
        battle = Battle(2000, 2000, [target, charger], seed=0)
        target.braced, target.braced_target = True, "charger"

        combat.refresh_braced_state(battle)

        self.assertTrue(target.braced)
        self.assertEqual(target.braced_target, "charger")

    def test_given_a_braced_regiment_whose_charger_stopped_charging_then_it_is_unbraced(self):
        target = _regiment("target", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        charger = _regiment("charger", 500, 500, Side.ENEMY, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [target, charger], seed=0)
        target.braced, target.braced_target = True, "charger"

        combat.refresh_braced_state(battle)

        self.assertFalse(target.braced)

    def test_given_a_braced_regiment_that_has_joined_melee_then_it_is_unbraced(self):
        target = _regiment("target", 0, 0, Side.PLAYER, speed_per_tick=0.0)
        charger = _regiment("charger", 500, 500, Side.ENEMY, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [target, charger], seed=0)
        target.braced, target.braced_target, target.in_melee = True, "charger", True

        combat.refresh_braced_state(battle)

        self.assertFalse(target.braced)
        self.assertIsNone(target.braced_target)


if __name__ == "__main__":
    unittest.main()


class ScriptedSameSideFightTests(unittest.TestCase):
    """notes/game_rules.md, engagement rules: same-side engagement is refused "when the target is not the
    current opponent", so a script's own target may be a friend (BF001: the assassin Sleaquit hunts Otto
    Hiln, both enemy side). The attacker fights on its own camp (`Side.DUEL`) for that fight only."""

    def _pair(self, target="otto"):
        assassin = _regiment("assassin", 0, 0, Side.ENEMY, models=1, ranks=1, speed_per_tick=0.0)
        otto = _regiment("otto", 0, 6, Side.ENEMY, models=1, ranks=1, speed_per_tick=0.0)
        assassin.attack_target = target
        return assassin, otto, Battle(500, 500, [assassin, otto], seed=1995)

    def test_overlapping_same_side_regiments_without_a_scripted_target_do_not_engage(self):
        assassin, otto, battle = self._pair(target=None)
        battle.tick()
        self.assertFalse(assassin.in_melee or otto.in_melee)

    def test_the_scripted_opponent_is_engaged_even_on_the_same_side(self):
        assassin, otto, battle = self._pair()
        battle.tick()
        self.assertTrue(assassin.in_melee and otto.in_melee)

    def test_the_attacker_takes_its_own_camp_and_the_target_keeps_its_side(self):
        assassin, otto, battle = self._pair()
        battle.tick()
        self.assertEqual(assassin.camp, Side.DUEL)
        self.assertEqual(otto.camp, Side.ENEMY)

    def test_the_camp_is_dropped_when_the_fight_ends(self):
        assassin, otto, battle = self._pair()
        battle.tick()
        otto.models = 0  # killed (e.g. by his own script)
        battle.tick()
        self.assertFalse(assassin.in_melee)
        self.assertEqual(assassin.camp, Side.ENEMY)

    def test_strikes_are_tallied_per_camp_so_the_duel_has_a_loser(self):
        assassin, otto, battle = self._pair()
        events = _run(battle, combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 2)
        strikes = [e for e in events if e.kind == "melee_strike"]
        self.assertTrue(strikes)
        self.assertEqual({e.data["attacker"] for e in strikes} - {"assassin", "otto"}, set())
        self.assertIn(Side.DUEL, next(iter(strikes)).data["tally"])

    def test_a_third_party_of_the_same_side_stays_out_of_the_duel(self):
        assassin, otto, battle = self._pair()
        bystander = _regiment("bystander", 0, 3, Side.ENEMY, models=1, ranks=1, speed_per_tick=0.0)
        battle.regiments["bystander"] = bystander
        battle.tick()
        self.assertFalse(bystander.in_melee)
