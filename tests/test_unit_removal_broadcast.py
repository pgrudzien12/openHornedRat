"""The "unit removed" broadcast, event 0x16 (notes/unit_removal_broadcast.md): a unit wiped out tells every other unit
in the battle once its last model has collapsed, so a shooter's script drops it as a target (the BF006 crossbows that
kept firing at an empty spot); a script's RemoveFromBattle is quiet."""

import unittest

from tests.script_helpers import FakeDll, word
from whshr import animation, behaviour, combat, interpreter
from whshr.engine import Battle, Regiment
from whshr.rules import Side


class RemovalBroadcastTests(unittest.TestCase):
    def setUp(self):
        self.shooters = Regiment("S", "Crossbows", 100, 100, 0, Side.PLAYER, models=10, ranks=2)
        self.ally = Regiment("A", "Cart", 300, 100, 0, Side.NEUTRAL, models=2, ranks=1, unit_class=7)
        self.goblins = Regiment("X", "Goblins", 100, 400, 256, Side.ENEMY, models=1, ranks=1)
        self.reserve = Regiment("H", "Reserve", 900, 900, 256, Side.ENEMY, models=10, ranks=2)
        self.reserve.hidden = True
        self.battle = Battle(1000, 1000, [self.shooters, self.ally, self.goblins, self.reserve], seed=1995)
        self.battle.phase = "battle"

    def removals(self, unit_id: str) -> list[str | None]:
        return [event.source for event in self.battle.event_bus.unit_states[unit_id].event_queue
                if event.code == 0x16]

    def kill_last_model(self, death_kind: int) -> None:
        combat.kill_models(self.goblins, [0], battle=self.battle, death_kind=death_kind, killer="S")

    def test_given_the_last_model_shot_then_every_other_unit_hears_of_the_removal_on_the_next_tick(self):
        self.kill_last_model(animation.DEATH_MISSILE)
        self.battle.tick()
        for unit_id in ("S", "A", "H"):
            self.assertEqual(self.removals(unit_id), ["X"], unit_id)
        self.assertEqual(self.removals("X"), [])

    def test_given_the_broadcast_went_out_then_it_is_not_repeated(self):
        self.kill_last_model(animation.DEATH_MISSILE)
        for _ in range(5):
            self.battle.tick()
        self.assertEqual(self.removals("S"), ["X"])

    def test_given_a_close_combat_death_then_the_broadcast_waits_for_the_collapse(self):
        self.kill_last_model(animation.DEATH_ORDINARY)
        delay = self.goblins.dying[0].ticks_left
        self.assertGreater(delay, 1)
        for _ in range(delay - 1):
            self.battle.tick()
        self.assertEqual(self.removals("S"), [])
        for _ in range(2):
            self.battle.tick()
        self.assertEqual(self.removals("S"), ["X"])

    def test_given_a_unit_with_models_left_then_nothing_is_broadcast(self):
        self.battle.tick()
        self.assertEqual(self.removals("S"), [])

    def test_given_a_script_removes_the_unit_then_the_removal_is_quiet(self):
        self.battle.remove_from_play(self.goblins)
        self.battle.tick()
        self.assertEqual(self.removals("S"), [])

    def test_given_the_broadcast_then_no_target_is_cleared_directly(self):
        state = self.battle.event_bus.unit_states["S"]
        state.current_target = ("X", 0)
        self.kill_last_model(animation.DEATH_MISSILE)
        self.battle.tick()
        self.assertEqual(state.current_target, ("X", 0))


BATTLE_EDGE = {"status": ["bnd_ACTIVE", "bnd_BATTLEEDGE"],
               "lines": [[100, 100, 300, 100], [300, 100, 300, 300], [300, 300, 100, 300], [100, 300, 100, 100]]}


class FlightDepartureTests(unittest.TestCase):
    """Vector (d): a routing unit whose centre leaves the battle area only broadcasts 0x0E; the units aiming at it
    keep their targets until their own scripts drop it (notes/unit_removal_broadcast.md 3, 5.4)."""

    def make(self, script_dll):
        self.fugitive = Regiment("X", "Fugitives", 290, 200, 128, Side.ENEMY, models=1, ranks=1, speed_per_tick=20)
        self.chaser = Regiment("Y", "Chasers", 150, 150, 0, Side.PLAYER, models=1, ranks=1, speed_per_tick=0)
        self.chaser.attack_target = "X"
        self.battle = Battle(500, 500, [self.fugitive, self.chaser], boundaries=[BATTLE_EDGE], seed=1995,
                             script_dll=script_dll)
        self.battle.phase = "battle"
        self.state = self.battle.event_bus.unit_states["Y"]
        self.state.current_target = ("X", 0)
        self.fugitive.routing = True
        self.fugitive.flee_x, self.fugitive.flee_y = 1000, 200

    def run_to_departure(self):
        for _ in range(50):
            self.battle.tick()
            if self.fugitive.flight_departed:
                return
        self.fail("the fugitive never left the battle area")

    def test_given_scripts_then_departure_leaves_the_chasers_targets_to_its_script(self):
        self.make(FakeDll([behaviour.END]))
        self.run_to_departure()
        self.assertEqual(self.chaser.attack_target, "X")
        self.assertEqual(self.state.current_target, ("X", 0))
        self.assertEqual([(e.code, e.source) for e in self.state.event_queue if e.code == 0x0E], [(0x0E, "X")])

    def test_given_the_0x0E_then_query_23_and_drop_target_forget_the_fugitive(self):
        self.make(FakeDll([behaviour.END]))
        self.run_to_departure()
        departure = next(e for e in self.state.event_queue if e.code == 0x0E)
        interp = self.battle.interpreter
        assert interp is not None
        self.state.current_event = departure
        interp.op_Query(self.state, 23, [word("Query"), 23], "Y", 0, self.battle.rng)
        self.assertEqual([e.code for e in self.state.event_queue if e.code == 0x19], [0x19])
        interp.op_DropTarget(self.state, None, [word("DropTarget")], "Y", 0, self.battle.rng)
        self.assertIsNone(self.chaser.attack_target)
        self.assertIsNone(self.state.current_target)

    def test_given_no_scripts_then_departure_clears_the_targets_itself(self):
        self.make(None)
        self.run_to_departure()
        self.assertIsNone(self.chaser.attack_target)
        self.assertIsNone(self.state.current_target)
        self.assertEqual([(e.code, e.source) for e in self.state.event_queue if e.code == 0x0E], [(0x0E, "X")])


if __name__ == "__main__":
    unittest.main()
