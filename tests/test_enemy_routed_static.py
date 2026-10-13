"""EnemyRoutedStatic and the routing war-machine crew (notes/runaway_routers_broken.md 0, 2): the crew's 0x0F / 0x09
reaction is true only for its own target, and an anchored crew never starts a rout. Vectors of section 2.5:
C = crew, W = an enemy cavalry unit."""

import unittest

from whshr import combat
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event, ScriptInterpreter
from whshr.rules import Side


def unit(identifier, x, y, side, **kwargs):
    return Regiment(identifier, identifier, x, y, 0, side, models=kwargs.pop("models", 4), ranks=1, **kwargs)


class EnemyRoutedStaticTests(unittest.TestCase):
    def setUp(self):
        self.crew = unit("c", 0, 0, Side.ENEMY, hud_class="art")
        self.w = unit("w", 0, 200, Side.PLAYER)
        self.x = unit("x", 200, 0, Side.PLAYER)
        self.battle = Battle(1000, 1000, [self.crew, self.w, self.x], seed=1995)
        self.interp = ScriptInterpreter(self.battle, self.battle.event_bus, None)
        self.state = self.battle.event_bus.unit_states["c"]

    def static(self, source, code=0x09):
        self.state.current_event = Event(code=code, source=source)
        self.state.cond_flags = True  # the leftover of CaseEvent: the opcode must overwrite it
        self.interp.op_EnemyRoutedStatic(self.state, None, [], "c", 0, None)
        return bool(self.state.cond_flags)

    def test_a_braced_crew_whose_charger_stopped_short_stands_down(self):
        self.state.current_target = ("w", 0)
        self.crew.braced = True
        self.assertTrue(self.static("w"))

    def test_an_unbraced_crew_outside_melee_does_not(self):
        self.state.current_target = ("w", 0)
        self.assertFalse(self.static("w"))

    def test_a_routing_crew_has_no_target_and_never_rallies_here(self):
        self.crew.routing = True
        self.assertFalse(self.static("w"))
        self.assertFalse(self.static("w", code=0x0F))

    def test_another_unit_routing_is_not_its_business(self):
        self.state.current_target = ("x", 0)
        self.crew.braced = True
        self.assertFalse(self.static("w", code=0x0F))

    def test_in_melee_alone_after_its_foe_left_the_grid(self):
        self.state.current_target = ("w", 0)
        self.crew.in_melee, self.crew.melee_group = True, "fight1"
        self.assertTrue(self.static("w", code=0x0F))

    def test_in_melee_with_another_foe_it_switches_target(self):
        self.state.current_target = ("w", 0)
        for regiment in (self.crew, self.x):
            regiment.in_melee, regiment.melee_group = True, "fight1"
        self.crew.model_positions()
        self.crew.melee_models[0].opponent = ("w", 0)
        self.crew.melee_models[1].opponent = ("x", 0)

        self.assertFalse(self.static("w", code=0x0F))
        self.assertEqual(self.state.current_target, ("x", 0))
        self.assertIsNone(self.crew.melee_models[0].opponent)
        self.assertEqual(self.crew.melee_models[1].opponent, ("x", 0))


class AnchoredRoutTests(unittest.TestCase):
    def test_an_anchored_war_machine_never_starts_a_rout_but_its_target_is_cleared(self):
        crew = unit("c", 0, 0, Side.ENEMY, hud_class="art")
        battle = Battle(1000, 1000, [crew, unit("w", 0, 200, Side.PLAYER)], seed=1995)
        crew.attack_target = "w"
        combat.start_rout(crew, battle)
        self.assertFalse(crew.routing)
        self.assertIsNone(crew.attack_target)

    def test_once_the_machine_is_destroyed_the_crew_can_rout(self):
        crew = unit("c", 0, 0, Side.ENEMY, hud_class="art")
        battle = Battle(1000, 1000, [crew, unit("w", 0, 200, Side.PLAYER)], seed=1995)
        crew.clear_anchor()
        combat.start_rout(crew, battle)
        self.assertTrue(crew.routing)


if __name__ == "__main__":
    unittest.main()
