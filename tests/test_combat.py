"""BDD scenarios for close combat, morale, rally and shooting (whshr.combat), per docs/testing.md.

Timing is expressed in ticks: SEGMENT_TICKS (19) ticks make one segment, SEGMENTS_PER_TURN (10)
segments make one turn (game_rules.md 5.1, 6.2, 7.4).
"""
import math
import unittest

from whshr import combat, formation
from whshr.engine import Battle, Regiment


def _regiment(identifier, x, y, player, **kwargs):
    models = kwargs.pop("models", 10)
    ranks = kwargs.pop("ranks", 2)
    direction = kwargs.pop("direction", 0)
    return Regiment(identifier, identifier, x, y, direction, player, models=models, ranks=ranks, **kwargs)


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
    battle.fights[group_id] = combat._new_fight(turn)
    for regiment in regiments:
        regiment.in_melee = True
        regiment.melee_group = group_id
        regiment.melee_touching = frozenset(
            r.identifier for r in regiments if r.player != regiment.player)


class InitiativeTimingTests(unittest.TestCase):
    """game_rules.md 5.1: a unit attacks once per turn, in the segment equal to its Initiative."""

    def test_given_two_engaged_regiments_with_different_initiative_when_ticked_one_full_turn_then_each_strikes_exactly_once(self):
        high_i = _regiment("hi", 0, 0, True, initiative=10, speed_per_tick=0.0)
        low_i = _regiment("lo", 10, 0, False, initiative=1, speed_per_tick=0.0)
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
        self.attacker = _regiment("att", 0, 0, True, ws=4, strength=4, attacks=1, leadership=8,
                                  initiative=10, models=20, ranks=4, speed_per_tick=0.0)
        self.defender = _regiment("def", 10, 0, False, ws=3, toughness=3, armour=0, leadership=7,
                                  initiative=10, models=20, ranks=4, speed_per_tick=0.0)
        self.battle = Battle(1000, 1000, [self.attacker, self.defender], seed=3)

    def test_given_a_fresh_contact_when_ticked_through_two_turns_then_no_break_test_happens_yet(self):
        turn_ticks = combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN
        events = _run(self.battle, turn_ticks * 2 + combat.SEGMENT_TICKS * 9)  # up to turn 2's segment 1

        self.assertNotIn("leadership_test", [e.kind for e in events])

    def test_given_a_fresh_contact_when_ticked_past_two_turns_then_a_break_test_happens(self):
        events = _run(self.battle, combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN * 2 + combat.SEGMENT_TICKS * 10)

        self.assertIn("leadership_test", [e.kind for e in events])

    def test_given_a_clanrats_style_charge_when_ticked_through_the_first_turn_then_the_defender_does_not_rout(self):
        # game_rules.md's BF001 diagnosis: a 3-0 first round used to trigger an immediate failed break
        # test and instant rout. With traced timing, no break test at all can happen in the first turn.
        clanrats = _regiment("clanrats", 0, 0, True, ws=3, strength=3, attacks=1, leadership=7,
                              initiative=4, models=13, ranks=3, speed_per_tick=0.0)
        infantry = _regiment("infantry", 10, 0, False, ws=3, strength=3, toughness=3, attacks=1,
                             leadership=7, initiative=4, models=16, ranks=4, speed_per_tick=0.0)
        battle = Battle(1000, 1000, [clanrats, infantry], seed=1)

        _run(battle, combat.SEGMENT_TICKS * combat.SEGMENTS_PER_TURN)

        self.assertFalse(infantry.routing)
        self.assertFalse(clanrats.routing)


class RankAndDirectionBonusTests(unittest.TestCase):
    """game_rules.md 6.1: rank bonus (deep formations) and direction bonus (flank/rear attacks)."""

    def test_given_a_shallow_formation_when_the_rank_bonus_is_computed_then_it_is_zero(self):
        shallow = _regiment("s", 0, 0, True, models=6, ranks=2)  # frontage 3, not > 3
        self.assertEqual(combat._rank_bonus(shallow), 0)

    def test_given_a_deep_formation_when_the_rank_bonus_is_computed_then_it_counts_the_ranks_behind_the_first(self):
        deep = _regiment("d", 0, 0, True, models=16, ranks=4)  # frontage 4, size/width - 1 = 3
        self.assertEqual(combat._rank_bonus(deep), 3)

    def test_given_an_attack_from_the_front_when_the_direction_bonus_is_computed_then_it_is_zero(self):
        defender = _regiment("def", 0, 0, False, direction=0)  # direction 0 faces +Y (formation.place)
        attacker = _regiment("att", 0, 10, True)  # in front of the defender's facing
        self.assertEqual(combat._direction_bonus(attacker, defender), 0)

    def test_given_an_attack_from_the_rear_when_the_direction_bonus_is_computed_then_it_is_two(self):
        defender = _regiment("def", 0, 0, False, direction=0)
        attacker = _regiment("att", 0, -10, True)  # behind the defender's facing
        self.assertEqual(combat._direction_bonus(attacker, defender), 2)

    def test_given_an_attack_from_the_flank_when_the_direction_bonus_is_computed_then_it_is_one(self):
        defender = _regiment("def", 0, 0, False, direction=0)
        attacker = _regiment("att", 10, 0, True)  # to the defender's side
        self.assertEqual(combat._direction_bonus(attacker, defender), 1)

    def test_given_a_kill_deficit_smaller_than_the_rank_bonus_when_the_break_test_is_due_then_the_deep_unit_does_not_lose_the_result(self):
        deep = _regiment("deep", 0, 0, True, leadership=7)
        shallow = _regiment("shallow", 10, 0, False, leadership=7)
        battle = Battle(1000, 1000, [deep, shallow], seed=0)
        _join_fight(battle, "g", deep, shallow, turn=0)
        # 1 kill behind, +3 rank bonus already folded in: the deep unit is not on the losing side.
        battle.fights["g"]["tally"] = {True: 3.0, False: 2.0}

        combat._resolve_group_break_test("g", [deep, shallow], 2, battle)

        deep_tests = [e for e in battle.events if e.kind == "leadership_test" and e.data["regiment"] == "deep"]
        self.assertEqual(deep_tests, [])

    def test_given_a_kill_deficit_without_a_rank_bonus_when_the_break_test_is_due_then_the_loser_is_tested(self):
        loser = _regiment("loser", 0, 0, True, leadership=7)
        winner = _regiment("winner", 10, 0, False, leadership=7)
        battle = Battle(1000, 1000, [loser, winner], seed=0)
        _join_fight(battle, "g", loser, winner, turn=0)
        battle.fights["g"]["tally"] = {True: 0.0, False: 2.0}

        combat._resolve_group_break_test("g", [loser, winner], 2, battle)

        leadership = [e for e in battle.events if e.kind == "leadership_test"]
        self.assertEqual(len(leadership), 1)
        self.assertEqual(leadership[0].data["regiment"], "loser")


class RallyTimingTests(unittest.TestCase):
    """game_rules.md 7.4: the first rally attempt is one full turn after the rout, then every 3 segments."""

    def test_given_a_regiment_that_just_routed_when_checked_before_its_scheduled_segment_then_no_attempt_is_made(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True, rally_next_segment=5)
        enemy = _regiment("e", 1000, 1000, False)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)
        battle.tick_count = 4 * combat.SEGMENT_TICKS  # absolute_segment 4, still before segment 5

        combat.resolve_rally(battle)

        self.assertEqual(battle.events, [])
        self.assertTrue(routing.routing)

    def test_given_a_regiment_whose_scheduled_segment_has_come_when_checked_then_an_attempt_is_made(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True, rally_next_segment=5)
        enemy = _regiment("e", 1000, 1000, False)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)
        battle.tick_count = 5 * combat.SEGMENT_TICKS

        combat.resolve_rally(battle)

        self.assertEqual([e.kind for e in battle.events], ["rally_test"])

    def test_given_a_regiment_starting_to_rout_when_the_rout_begins_then_its_first_rally_attempt_is_scheduled_one_turn_later(self):
        attacker = _regiment("att", 0, 0, True, ws=4, strength=4, attacks=1, leadership=8, initiative=10,
                             models=20, ranks=4, speed_per_tick=0.0)
        defender = _regiment("def", 10, 0, False, ws=3, toughness=3, armour=0, leadership=7,
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
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True, rally_next_segment=0)
        enemy = _regiment("e", 1000, 1000, False)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)  # seed 0: the roll passes Ld 9

        combat.resolve_rally(battle)

        self.assertFalse(routing.routing)
        rally = battle.events[-1]
        self.assertEqual(rally.kind, "rally_test")
        self.assertTrue(rally.data["passed"])

    def test_given_an_enemy_within_the_safe_distance_when_checked_then_no_rally_is_attempted(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True, rally_next_segment=0)
        enemy = _regiment("e", 50, 0, False)  # well within FLEE_SAFE_DISTANCE
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)
        self.assertTrue(battle.events[-1].data["blocked_by_enemy"])

    def test_given_cant_rally_psychology_when_checked_then_the_unit_never_rallies(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True, rally_next_segment=0,
                            psychology=frozenset({"CantRally"}))
        enemy = _regiment("e", 1000, 1000, False)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)

    def test_given_casualties_at_or_below_a_quarter_of_strength_when_checked_then_the_unit_cannot_rally(self):
        routing = _regiment("r", 0, 0, True, leadership=9, routing=True, rally_next_segment=0,
                            models=2, original_models=10)  # 8 casualties >= 3 x 2 models left
        enemy = _regiment("e", 1000, 1000, False)
        battle = Battle(2000, 2000, [routing, enemy], seed=0)

        combat.resolve_rally(battle)

        self.assertTrue(routing.routing)
        self.assertTrue(battle.events[-1].data["too_many_casualties"])

    def test_given_a_regiment_that_has_fled_the_field_when_checked_then_it_is_never_offered_a_rally_attempt(self):
        # Bug: fled regiments (routing off the map edge) kept passing rally tests and returning, because
        # resolve_rally only checked `routing`, never `active` (which `fled` makes permanently False).
        fled = _regiment("r", 0, 0, True, leadership=9, routing=True, fled=True, rally_next_segment=0)
        enemy = _regiment("e", 1000, 1000, False)
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
        self.attacker = _regiment("att", 0, 0, True, ws=5, strength=5, attacks=2, leadership=8,
                                  initiative=10, speed_per_tick=0.0)
        self.defender = _regiment("def", 10, 0, False, ws=1, toughness=1, armour=0, leadership=2,
                                  initiative=10, speed_per_tick=1.5)
        self.battle = Battle(1000, 1000, [self.attacker, self.defender], seed=1)

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
        self.assertEqual(len(self.defender.corpses), 3)
        self.assertEqual(len(self.defender.model_positions()), 7)

    def test_given_a_cant_die_defender_when_casualties_are_applied_then_no_models_are_removed(self):
        # game_rules.md 7.6: CantDie models are never removed by wounds.
        immortal = _regiment("i", 0, 0, False, psychology=frozenset({"CantDie"}))

        removed = combat.apply_casualties(immortal, 5, self.battle.rng, self.battle)

        self.assertEqual(removed, 0)
        self.assertEqual(immortal.models, 10)
        self.assertEqual(immortal.corpses, [])


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

    def test_given_footprints_two_model_spacings_apart_when_bounding_circles_overlap_then_they_do_not_clash(self):
        # Two default-shaped regiments (10 models, 2 ranks, both facing +Y) stacked front-to-back: their
        # footprints (half_forward 12 each) are exactly two model spacings (24 units) apart, but their
        # bounding circles (radius ~32) still overlap at that 48-unit centre distance. Must not clash on
        # circle touch, only on the footprints actually meeting (game_rules.md, "Engagement").
        left = _regiment("left", 0, 0, True, speed_per_tick=0.0)
        right = _regiment("right", 0, 48, False, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [left, right], seed=0)
        gap = formation.footprint_gap(left.footprint_corners(), right.footprint_corners())
        self.assertAlmostEqual(gap, 2 * formation.MODEL_SPACING, places=6)
        self.assertLess(48.0, left.bounding_radius() + right.bounding_radius())

        battle.tick()

        self.assertEqual([e.kind for e in battle.events if e.kind == "clash"], [])
        self.assertFalse(left.in_melee)
        self.assertFalse(right.in_melee)

    def test_given_a_charging_regiment_when_it_closes_then_it_keeps_moving_until_footprints_touch_then_clashes(self):
        charger = _regiment("charger", 0, 0, True, models=10, ranks=2, speed_per_tick=6.0)
        target = _regiment("target", 120, 0, False, models=10, ranks=2, speed_per_tick=0.0)
        battle = Battle(2000, 2000, [charger, target], seed=0)
        battle.order_attack("charger", "target")

        for _ in range(60):
            battle.tick()
            if charger.in_melee:
                break

        self.assertTrue(charger.in_melee)
        self.assertTrue(target.in_melee)
        gap = formation.footprint_gap(charger.footprint_corners(), target.footprint_corners())
        self.assertLessEqual(gap, combat.CONTACT_MARGIN)

    def test_given_two_regiments_touching_one_enemy_when_they_clash_then_they_share_one_fight_and_both_strike(self):
        # No 2 vs 1: two player regiments touching the same lone enemy regiment must share a single
        # fight (game_rules.md 5.7's battle grid), and both get to strike it in their own segment.
        left = _regiment("left", 0, 0, True, initiative=10, speed_per_tick=1.5)
        right = _regiment("right", 10, 12, True, initiative=10, speed_per_tick=1.5)
        enemy = _regiment("enemy", 10, -10, False, initiative=10, models=40, ranks=8, speed_per_tick=1.5)
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
        self.assertGreater(fight["tally"][True], 0)  # left and right's kills/bonuses share one tally


if __name__ == "__main__":
    unittest.main()
