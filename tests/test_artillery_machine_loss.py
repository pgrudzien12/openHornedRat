"""What happens to an artillery crew when its machine is lost (notes/artillery_machine_loss.md).

The unit is the report's §5 Empire mortar crew: orgsize 4, the machine (W3, Ld 0) is the leader, plus crew W1 Ld 7.
"""
import unittest

from whshr import combat, interpreter, ranged
from whshr.engine import Battle, Regiment
from whshr.rules import Side

ROUT, LEADER_KILLED = 0x0C, 0x17


class Draws:
    """A scripted random stream: every call returns the next value, whatever its range, and is counted."""

    def __init__(self, *values: int) -> None:
        self.values = list(values)
        self.calls = 0

    def _next(self) -> int:
        self.calls += 1
        return self.values.pop(0) if self.values else 0

    def randrange(self, *_args: int) -> int:
        return self._next()

    def randint(self, *_args: int) -> int:
        return self._next()

    def random(self) -> float:
        return 0.5


def mortar(models: int = 4, scripts: bool = True) -> tuple[Battle, Regiment]:
    crew = Regiment("M", "Mortar Crew", 500, 500, 0, Side.PLAYER, models=models, ranks=1, unit_class=4,
                    has_leader=True, leader_leadership=0, leader_wounds=3, orgsize=4, leadership=7)
    crew.hud_class = "art"
    enemy = Regiment("E", "Enemy", 500, 1500, 256, Side.ENEMY, models=10, ranks=2)
    battle = Battle(2000, 2000, [crew, enemy], seed=1995)
    if scripts:
        battle.interpreter = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
    crew.model_positions()
    return battle, crew


def queue(battle: Battle) -> list[int]:
    return [event.code for event in battle.event_bus.unit_states["M"].event_queue]


def collapse(battle: Battle, crew: Regiment) -> None:
    """The next model update: every 1-tick collapse ends."""
    battle._step_dying(crew)


class DestroyingMisfireTests(unittest.TestCase):
    """§1 and V1: full strength, the explosion kills the machine and one crew model."""

    def setUp(self) -> None:
        self.battle, self.crew = mortar()
        self.machine = self.crew.melee_models[self.crew.living_leader_index or 0]
        self.machine_at = self.crew.model_positions()[self.crew.living_leader_index or 0]
        crew_ids = [model.uid for model in self.crew.melee_models if model is not self.machine]
        self.first_crew = crew_ids[0]
        # the machine's own draw, then crew A odd (wounded, killed), B even, C even, then the Leadership test
        self.draws = Draws(0, 1, 0, 0, 7)
        self.battle.rng = self.draws  # type: ignore[assignment]
        ranged._destroy_machine(self.battle, self.crew)

    def test_the_machine_dies_first_and_stays_in_the_unit_while_it_collapses(self) -> None:
        self.assertNotIn(self.machine, self.crew.melee_models)
        self.assertIn(self.machine, [dying.model for dying in self.crew.dying])
        self.assertEqual(self.machine.wounds_taken, 3)
        self.assertIsNone(self.machine.credit)
        self.assertTrue(self.crew.machine_in_roster)
        self.assertTrue(self.crew.machine_alive)  # "machine gone" only once it has left the unit

    def test_the_anchor_clears_at_once(self) -> None:
        self.assertFalse(self.crew.anchored)

    def test_one_draw_per_model_machine_first_and_one_leadership_draw(self) -> None:
        self.assertEqual(self.draws.calls, 4 + 1)
        self.assertEqual(self.crew.models, 2)  # crew A killed on its odd draw

    def test_the_failed_leadership_test_asks_for_a_rout_and_never_starts_the_flight(self) -> None:
        self.assertFalse(self.crew.routing)
        self.assertEqual(queue(self.battle), [ROUT])

    def test_the_machine_leaves_as_a_wreck_where_it_stood_then_leader_killed_is_queued(self) -> None:
        collapse(self.battle, self.crew)
        self.assertFalse(self.crew.machine_in_roster)
        self.assertFalse(self.crew.machine_alive)
        self.assertIn(self.machine_at, [(corpse.x, corpse.y) for corpse in self.crew.corpses])
        codes = queue(self.battle)
        self.assertEqual(codes[:2], [ROUT, LEADER_KILLED])  # full strength: no test for the machine's removal


class BelowStrengthTests(unittest.TestCase):
    """V2: the crew had already lost a man; the machine's removal test uses Ld 0 and fails."""

    def test_the_machine_removal_asks_for_a_rout_below_leader_killed(self) -> None:
        battle, crew = mortar(models=3)
        battle.rng = Draws(0, 0, 0, 7, 2)  # type: ignore[assignment]  # nobody wounded; Ld draw; removal test 2
        ranged._destroy_machine(battle, crew)
        self.assertEqual(crew.models, 2)
        collapse(battle, crew)
        # LIFO: 0x17 is the newest, so the crew converts before the machine-removal 0x0C is handled
        self.assertEqual(queue(battle), [ROUT, ROUT, LEADER_KILLED])


class NoSurvivorTests(unittest.TestCase):
    """V3: no crew model survives, so there is no Leadership test and no draw for it."""

    def test_no_survivor_no_leadership_draw(self) -> None:
        battle, crew = mortar(models=2)
        draws = Draws(0, 1)
        battle.rng = draws  # type: ignore[assignment]
        ranged._destroy_machine(battle, crew)
        self.assertEqual((draws.calls, crew.models, queue(battle)), (2, 0, []))


class WithoutScriptsTests(unittest.TestCase):
    def test_an_artillery_crew_does_not_rout_from_the_explosion(self) -> None:
        battle, crew = mortar(scripts=False)
        battle.rng = Draws(0, 0, 0, 0, 12)  # type: ignore[assignment]
        ranged._destroy_machine(battle, crew)
        self.assertFalse(crew.routing)


class MeleeKillTests(unittest.TestCase):
    """§4: a machine killed by ordinary wounds stays the leader, and stays manned, until its collapse ends."""

    def test_leader_killed_waits_for_the_end_of_the_collapse(self) -> None:
        battle, crew = mortar()
        index = crew.living_leader_index
        assert index is not None
        combat.kill_models(crew, [index], battle)
        self.assertTrue((crew.anchored, crew.machine_alive) == (True, True))
        self.assertNotIn(LEADER_KILLED, queue(battle))
        for _ in range(80):
            collapse(battle, crew)
        self.assertEqual((crew.anchored, crew.machine_alive), (False, False))
        self.assertIn(LEADER_KILLED, queue(battle))


class ReadyToFireTests(unittest.TestCase):
    """V4, operand 0."""

    def ready(self, battle: Battle) -> tuple[bool, list[int]]:
        interp = battle.interpreter
        assert interp is not None
        state = battle.event_bus.unit_states["M"]
        interp.op_ReadyToFire(state, 0, [], "M", 0, battle.rng)
        return bool(state.cond_flags), [event.data["text_id"] for event in battle.events if event.kind == "message"]

    def gone(self) -> tuple[Battle, Regiment]:
        battle, crew = mortar()
        battle.rng = Draws(0, 0, 0, 0, 7)  # type: ignore[assignment]
        ranged._destroy_machine(battle, crew)
        collapse(battle, crew)
        return battle, crew

    def test_machine_dead_but_still_collapsing_and_reloaded_is_ready(self) -> None:
        battle, crew = mortar()
        battle.rng = Draws(0, 0, 0, 0, 7)  # type: ignore[assignment]
        ranged._destroy_machine(battle, crew)
        self.assertEqual(self.ready(battle), (True, []))

    def test_machine_gone_while_reloading_is_silent(self) -> None:
        battle, crew = self.gone()
        crew.reload_ticks = 50
        self.assertEqual(self.ready(battle), (False, []))

    def test_machine_gone_still_artillery_and_reloaded_prints_2015(self) -> None:
        battle, _ = self.gone()
        self.assertEqual(self.ready(battle), (False, [2015]))

    def test_after_the_crew_becomes_infantry_there_is_no_artillery_test(self) -> None:
        battle, crew = self.gone()
        crew.unit_class = 1  # SetClass 8, run by the crew's "leader killed" handler
        self.assertEqual(self.ready(battle), (True, []))


class CollapsingUnitHitTests(unittest.TestCase):
    def test_a_blast_on_a_unit_whose_last_models_are_still_collapsing_hits_nobody(self) -> None:
        battle, crew = mortar(models=2)
        combat.kill_models(crew, [0, 1], battle, death_kind=0)  # ordinary kills: both still collapsing
        self.assertEqual((crew.models, crew.active), (0, True))
        blast = ranged.Projectile("E", 6, 0, 0, 0, crew.x, crew.y, 0, 48, 3, 1, x=crew.x, y=crew.y)
        ranged._damage_unit(battle, crew, blast, False, 2)
        self.assertEqual(len(crew.dying), 2)


if __name__ == "__main__":
    unittest.main()
