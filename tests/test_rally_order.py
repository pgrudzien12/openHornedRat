"""The player's Rally order and the pursuit-restraint test (notes/pursuit_restraint.md).

Scenarios follow the test vectors of section 6: regiment P is player cavalry with effective Ld 7, pursuing since
the boundary into segment 6 (so its scheduled segment is 6). "Boundary -> n" is the boundary tick on which the
segment number becomes n; numbers count down 10..1 within a turn."""

import unittest
from unittest.mock import patch

from tests.script_helpers import FakeDll, word
from whshr import behaviour, combat
from whshr.battle_scene import BattleScene
from whshr.engine import Battle, Regiment
from whshr.rules import Side

EDGE = {"status": ["bnd_ACTIVE", "bnd_BATTLEEDGE"],
        "lines": [[0, 0, 2000, 0], [2000, 0, 2000, 2000], [2000, 2000, 0, 2000], [0, 2000, 0, 0]]}
IDLE = [word("PushPC"), word("Yield"), word("Loop"), behaviour.END]


def boundary_tick(number: int, turn: int = 0) -> int:
    """The tick on which the segment number becomes `number` in `turn`."""
    return (turn * combat.SEGMENTS_PER_TURN + combat.SEGMENTS_PER_TURN - number) * combat.SEGMENT_TICKS


def pursuer(side: Side = Side.PLAYER, scripted: bool = False, **kwargs: object) -> tuple[Battle, Regiment, Regiment]:
    """P pursuing a routing enemy well inside the battle edge, scheduled for segment 6 (pursuit start on the
    boundary into segment 6 of turn 0)."""
    kwargs.setdefault("leadership", 7)
    kwargs.setdefault("models", 8)
    kwargs.setdefault("ranks", 2)
    p = Regiment("p", "P", 900, 1000, 128, side, **kwargs)  # type: ignore[arg-type]
    fugitive = Regiment("fug", "Fugitives", 1020, 1000, 128, Side.ENEMY if side == Side.PLAYER else Side.PLAYER,
                        models=8, ranks=2, routing=True)
    battle = Battle(4000, 4000, [p, fugitive], seed=1995, boundaries=[EDGE],
                    script_dll=FakeDll(IDLE) if scripted else None)
    battle.phase = "battle"
    p.attack_target, p.pursuing = "fug", True
    battle.tick_count = boundary_tick(6)
    combat.schedule_rally_segment(p, battle)
    return battle, p, fugitive


def at_boundary(battle: Battle, number: int, turn: int = 1) -> None:
    """Run the once-per-segment pursuit update on the boundary into segment `number`."""
    battle.tick_count = boundary_tick(number, turn)
    battle._update_pursuits()  # pyright: ignore[reportPrivateUsage]


def restraint_events(battle: Battle) -> list[dict[str, object]]:
    return [event.data for event in battle.events if event.kind == "restraint_test"]


class RallyOrderTests(unittest.TestCase):
    """Section 3: Rally flips the rally-attempt state of a pursuing or broken player regiment, nothing else."""

    def test_given_a_pursuer_with_the_state_off_when_rally_is_pressed_then_only_the_state_turns_on(self):
        battle, p, _ = pursuer()
        battle.order_rally("p")
        self.assertTrue(p.rally_attempt)
        self.assertEqual(p.rally_segment, 6)
        self.assertTrue(p.pursuing)
        self.assertEqual(p.attack_target, "fug")
        self.assertFalse(p.reforming)
        self.assertEqual(battle.events, [])

    def test_given_the_state_on_when_rally_is_pressed_again_then_it_turns_off(self):
        battle, p, _ = pursuer()
        battle.order_rally("p")
        battle.order_rally("p")
        self.assertFalse(p.rally_attempt)

    def test_given_a_broken_player_regiment_when_rally_is_pressed_then_the_state_turns_on(self):
        unit = Regiment("u", "U", 100, 100, 0, Side.PLAYER, models=8, ranks=2, routing=True)
        battle = Battle(1000, 1000, [unit])
        battle.phase = "battle"
        battle.order_rally("u")
        self.assertTrue(unit.rally_attempt)

    def test_given_a_regiment_neither_pursuing_nor_broken_when_rally_is_pressed_then_nothing_changes(self):
        unit = Regiment("u", "U", 100, 100, 0, Side.PLAYER, models=8, ranks=2)
        battle = Battle(1000, 1000, [unit])
        battle.phase = "battle"
        with self.assertRaises(ValueError):
            battle.order_rally("u")
        self.assertFalse(unit.rally_attempt)

    def test_given_an_ai_pursuer_when_rally_is_ordered_then_it_is_refused(self):
        battle, p, _ = pursuer(side=Side.ENEMY)
        with self.assertRaises(ValueError):
            battle.order_rally("p")
        self.assertFalse(p.rally_attempt)

    def test_given_the_hud_rally_button_when_the_scene_handles_it_then_the_focused_pursuer_toggles(self):
        battle, p, fugitive = pursuer()
        scene = BattleScene()
        scene.battle = battle
        scene.selected_id = "p"
        scene.handle(("rally",), context=None)  # type: ignore[arg-type]
        self.assertTrue(p.rally_attempt)
        scene.selected_id = "fug"
        scene.handle(("rally",), context=None)  # type: ignore[arg-type]
        self.assertFalse(fugitive.rally_attempt)


class RestraintScheduleTests(unittest.TestCase):
    """Sections 2 and 4: the test runs only on the scheduled boundary with the state on; then `s := s - 3`."""

    def test_given_the_state_on_when_a_boundary_other_than_the_scheduled_one_comes_then_no_roll(self):
        battle, p, _ = pursuer()
        p.rally_attempt = True
        at_boundary(battle, 8, turn=0)
        self.assertEqual(restraint_events(battle), [])
        self.assertEqual(p.rally_segment, 6)

    def test_given_a_roll_of_seven_against_ld_seven_when_the_scheduled_boundary_comes_then_the_pursuit_ends(self):
        battle, p, _ = pursuer()
        p.rally_attempt = True
        with patch.object(combat, "_2_to_12", return_value=7):
            at_boundary(battle, 6)
        self.assertEqual(p.rally_segment, 3)
        self.assertEqual([(e["roll"], e["passed"]) for e in restraint_events(battle)], [(7, True)])
        self.assertFalse(p.pursuing)
        self.assertIsNone(p.attack_target)
        self.assertFalse(p.rally_attempt)
        self.assertTrue(p.reforming)

    def test_given_a_scripted_pursuer_when_the_restraint_test_passes_then_it_gets_event_0x10_once(self):
        battle, p, _ = pursuer(scripted=True)
        p.rally_attempt = True
        p.x = 1990  # the edge probe would stop it too: one stop is enough
        with patch.object(combat, "_2_to_12", return_value=2):
            at_boundary(battle, 6)
        self.assertEqual([e.code for e in battle.event_bus.unit_states["p"].event_queue], [0x10])
        self.assertTrue(p.pursuing)  # its library handler stops it on its next update

    def test_given_a_roll_of_nine_when_the_scheduled_boundary_comes_then_the_pursuit_continues(self):
        battle, p, _ = pursuer()
        p.rally_attempt = True
        with patch.object(combat, "_2_to_12", return_value=9):
            at_boundary(battle, 6)
        self.assertEqual(p.rally_segment, 3)
        self.assertTrue(p.pursuing)
        self.assertTrue(p.rally_attempt)
        self.assertEqual([e["passed"] for e in restraint_events(battle)], [False])

    def test_given_a_failed_test_when_three_segments_pass_then_it_rolls_again_and_wraps_to_ten(self):
        battle, p, _ = pursuer()
        p.rally_attempt = True
        with patch.object(combat, "_2_to_12", return_value=12):
            at_boundary(battle, 6)
            for number in (5, 4):
                at_boundary(battle, number)
            self.assertEqual(len(restraint_events(battle)), 1)
            at_boundary(battle, 3)
        self.assertEqual(len(restraint_events(battle)), 2)
        self.assertEqual(p.rally_segment, 10)

    def test_given_scheduled_segment_two_when_it_comes_then_the_next_is_nine(self):
        battle, p, _ = pursuer()
        p.rally_attempt, p.rally_segment = True, 2
        with patch.object(combat, "_2_to_12", return_value=12):
            at_boundary(battle, 2)
        self.assertEqual(p.rally_segment, 9)

    def test_the_schedule_cycles_through_every_segment_number(self):
        sequence, segment = [], 10
        for _ in range(10):
            segment = combat.next_rally_segment(segment)
            sequence.append(segment)
        self.assertEqual(sequence, [7, 4, 1, 8, 5, 2, 9, 6, 3, 10])

    def test_given_the_state_off_when_the_scheduled_boundary_comes_then_nothing_happens_and_s_is_kept(self):
        battle, p, _ = pursuer()
        at_boundary(battle, 6)
        self.assertEqual(restraint_events(battle), [])
        self.assertEqual(p.rally_segment, 6)
        self.assertTrue(p.pursuing)

    def test_given_rally_pressed_during_segment_five_then_the_first_roll_waits_for_boundary_six(self):
        battle, p, _ = pursuer()
        battle.tick_count = boundary_tick(5) + 3
        battle.order_rally("p")
        with patch.object(combat, "_2_to_12", return_value=12):
            for number, turn in ((4, 0), (3, 0), (2, 0), (1, 0), (10, 1), (9, 1), (8, 1), (7, 1)):
                at_boundary(battle, number, turn)
            self.assertEqual(restraint_events(battle), [])
            at_boundary(battle, 6, turn=1)
        self.assertEqual(len(restraint_events(battle)), 1)

    def test_given_the_pursuit_just_started_on_this_boundary_then_the_first_roll_is_a_full_turn_later(self):
        battle, p, _ = pursuer()
        p.rally_attempt = True
        battle._update_pursuits()  # pyright: ignore[reportPrivateUsage]  # the start boundary itself
        self.assertEqual(restraint_events(battle), [])
        self.assertEqual(p.rally_segment, 6)

    def test_given_always_pursue_when_the_scheduled_boundary_comes_then_no_roll_but_rescheduled(self):
        battle, p, _ = pursuer(psychology=frozenset({"AlwaysPursue"}))
        p.rally_attempt = True
        with patch.object(combat, "_2_to_12", side_effect=AssertionError("no roll")):
            at_boundary(battle, 6)
        self.assertEqual(p.rally_segment, 3)
        self.assertTrue(p.pursuing)


class RestraintTestTests(unittest.TestCase):
    """Section 4 step 3: a plain Leadership test, no modifier, against the effective Leadership."""

    def test_given_heavy_casualties_cant_rally_and_a_near_enemy_then_the_roll_is_unmodified(self):
        battle, p, _ = pursuer(models=2, original_models=10, psychology=frozenset({"CantRally"}))
        battle.regiments["e2"] = Regiment("e2", "Near", 950, 1000, 0, Side.ENEMY, models=8, ranks=2)
        p.rally_attempt = True
        with patch.object(combat, "_2_to_12", return_value=7):
            at_boundary(battle, 6)
        self.assertEqual([(e["roll"], e["leadership"], e["passed"]) for e in restraint_events(battle)],
                         [(7, 7, True)])
        self.assertFalse(p.pursuing)

    def test_given_a_dead_leader_and_first_model_ld_six_then_it_passes_on_two_to_six_only(self):
        for roll, passed in ((6, True), (7, False)):
            with self.subTest(roll=roll):
                battle, p, _ = pursuer(leadership=6, has_leader=True, leader_leadership=9)
                leader = p.living_leader_index
                assert leader is not None
                combat.kill_models(p, [leader], battle)
                p.rally_attempt = True
                with patch.object(combat, "_2_to_12", return_value=roll):
                    at_boundary(battle, 6)
                self.assertEqual(p.pursuing, not passed)

    def test_given_a_living_leader_then_the_leaders_leadership_is_used(self):
        battle, p, _ = pursuer(leadership=6, has_leader=True, leader_leadership=9)
        p.rally_attempt = True
        with patch.object(combat, "_2_to_12", return_value=9):
            at_boundary(battle, 6)
        self.assertFalse(p.pursuing)


class RallyAttemptStateLifecycleTests(unittest.TestCase):
    """Section 2: pursuit and rout starts reset the state; Independent switches it on only at a rout."""

    def melee(self, independent: bool) -> tuple[Battle, Regiment, Regiment]:
        player = Regiment("p", "P", 100, 100, 0, Side.PLAYER, models=8, ranks=2, independent=independent,
                          rally_attempt=True)
        enemy = Regiment("e", "E", 100, 120, 256, Side.ENEMY, models=8, ranks=2)
        battle = Battle(2000, 2000, [player, enemy], seed=1995)
        battle.phase = "battle"
        battle.tick_count = boundary_tick(4)
        for regiment in (player, enemy):
            regiment.in_melee, regiment.melee_group = True, "g"
        return battle, player, enemy

    def test_given_an_independent_player_unit_when_it_starts_pursuing_then_the_state_is_off(self):
        battle, player, enemy = self.melee(independent=True)
        combat.start_rout(enemy, battle)
        self.assertTrue(player.pursuing)
        self.assertFalse(player.rally_attempt)
        self.assertEqual(player.rally_segment, 4)

    def test_given_an_independent_pursuer_that_never_pressed_rally_then_it_never_rolls(self):
        battle, player, enemy = self.melee(independent=True)
        combat.start_rout(enemy, battle)
        battle.navigation_boundaries = Battle(4000, 4000, [], boundaries=[EDGE]).navigation_boundaries
        player.psychology = frozenset({"AlwaysPursue"})  # keeps the chase budget from ending the pursuit
        for absolute in range(5, 40):
            battle.tick_count = absolute * combat.SEGMENT_TICKS
            battle._update_pursuits()  # pyright: ignore[reportPrivateUsage]
        self.assertTrue(player.pursuing)
        self.assertEqual(restraint_events(battle), [])  # not even the AlwaysPursue "no roll" check ran

    def test_given_an_independent_player_unit_when_it_routs_then_the_state_turns_on(self):
        battle, player, enemy = self.melee(independent=True)
        combat.start_rout(player, battle)
        self.assertTrue(player.rally_attempt)
        self.assertEqual(player.rally_segment, 4)

    def test_given_a_non_independent_player_unit_when_it_routs_then_the_state_is_off(self):
        battle, player, enemy = self.melee(independent=False)
        combat.start_rout(player, battle)
        self.assertFalse(player.rally_attempt)

    def test_given_an_independent_ai_unit_when_it_routs_then_the_state_stays_off(self):
        battle, player, enemy = self.melee(independent=False)
        enemy.independent = True
        combat.start_rout(enemy, battle)
        self.assertFalse(enemy.rally_attempt)

    def test_given_the_state_on_when_the_pursuit_ends_for_another_reason_then_it_is_off(self):
        battle, p, fugitive = pursuer()
        p.rally_attempt = True
        fugitive.routing = False  # rallied: the target check stops the pursuit
        at_boundary(battle, 9, turn=0)
        self.assertFalse(p.pursuing)
        self.assertFalse(p.rally_attempt)


class FlightRallyGateTests(unittest.TestCase):
    """game_rules.md "Rally": a fleeing unit attempts to rally only while its rally-attempt state is on."""

    def test_given_a_fleeing_unit_with_the_state_off_when_its_segment_comes_then_no_attempt_and_s_is_kept(self):
        routing = Regiment("r", "R", 0, 0, 0, Side.ENEMY, models=8, ranks=2, leadership=9, routing=True,
                           rally_segment=10)
        battle = Battle(2000, 2000, [routing], seed=0)
        combat.resolve_rally(battle)
        self.assertEqual(battle.events, [])
        self.assertEqual(routing.rally_segment, 10)
        self.assertTrue(routing.routing)

    def test_given_a_broken_player_unit_ordered_to_rally_when_its_segment_comes_then_it_tests(self):
        routing = Regiment("r", "R", 0, 0, 0, Side.PLAYER, models=8, ranks=2, leadership=9, routing=True,
                           rally_segment=10)
        battle = Battle(2000, 2000, [routing], seed=0)
        battle.phase = "battle"
        battle.order_rally("r")
        with patch.object(combat, "_2_to_12", return_value=5):
            combat.resolve_rally(battle)
        self.assertEqual([e.kind for e in battle.events], ["rally_test"])
        self.assertFalse(routing.routing)
        self.assertFalse(routing.rally_attempt)
        self.assertEqual(routing.rally_segment, 7)


if __name__ == "__main__":
    unittest.main()
