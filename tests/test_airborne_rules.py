"""Battle rules while airborne (notes/airborne_units.md Part B, GitHub #388)."""

import unittest

from whshr import combat, interpreter, ranged, visibility
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def flier(identifier="F", x=500.0, y=500.0, side=Side.PLAYER, elevation=32) -> Regiment:
    unit = Regiment(identifier, "Gyrocopter", x, y, 0, side, models=1, ranks=1, sprite="Gyrocopter")
    unit.flight_state().elevation = elevation
    return unit


def infantry(identifier="I", x=500.0, y=500.0, side=Side.PLAYER, **extra) -> Regiment:
    return Regiment(identifier, "Infantry", x, y, 0, side, models=10, ranks=2, **extra)


def battle_of(*units: Regiment) -> Battle:
    battle = Battle(3000, 3000, list(units), seed=1995)
    battle.phase = "battle"
    return battle


class CollisionTests(unittest.TestCase):
    """B2.3 and vectors B6-B8: the mover's pass classifies the other footprint, and an airborne one is skipped."""

    def test_an_airborne_flier_moving_into_friends_is_pushed(self):
        f, i = flier(x=500, y=505), infantry()
        battle = battle_of(f, i)
        battle._push_apart_pass(f, [f, i])
        self.assertNotEqual((f.x, f.y), (500, 505))

    def test_a_ground_unit_moving_into_an_airborne_flier_is_not_pushed(self):
        f, i = flier(x=500, y=505), infantry()
        battle = battle_of(f, i)
        battle._push_apart_pass(i, [f, i])
        self.assertEqual((i.x, i.y, f.x, f.y), (500, 500, 500, 505))

    def test_a_landed_flier_is_ordinary_again(self):
        f, i = flier(x=500, y=505, elevation=0), infantry()
        battle = battle_of(f, i)
        battle._push_apart_pass(i, [f, i])
        self.assertNotEqual((i.x, i.y), (500, 500))

    def test_two_airborne_fliers_ignore_each_other(self):
        first, second = flier("F1"), flier("F2", y=505)
        battle = battle_of(first, second)
        battle._push_apart_pass(first, [first, second])
        self.assertEqual((first.x, first.y), (500, 500))


class ContactTests(unittest.TestCase):
    """B2.3, B2.4, B2.5 and vectors B9, B11, B13: only an airborne mover makes contact."""

    def test_a_ground_unit_cannot_touch_a_hovering_flier(self):
        self.assertFalse(combat._contact_possible(infantry(side=Side.ENEMY), flier()))

    def test_a_moving_airborne_flier_touches_ground_enemies(self):
        f = flier()
        f.target_x, f.target_y = 900.0, 500.0
        self.assertTrue(combat._contact_possible(infantry(side=Side.ENEMY), f))

    def test_two_fliers_never_touch(self):
        f1, f2 = flier("F1"), flier("F2", side=Side.ENEMY)
        f1.target_x, f1.target_y = 900.0, 500.0
        self.assertFalse(combat._contact_possible(f1, f2))

    def test_ground_units_touch_as_before(self):
        self.assertTrue(combat._contact_possible(infantry(), infantry("J", side=Side.ENEMY)))


class SteeringTests(unittest.TestCase):
    """B2.2: an airborne unit is plain scenery to everyone else's steering, whatever its side or state."""

    def footprint_keys(self, f: Regiment, mover: Regiment) -> list[str]:
        battle = battle_of(f, mover)
        footprints, units = battle._route_footprints(mover, ("move",))
        return [fp.key for fp in footprints if fp.key not in units]

    def test_a_hovering_flier_is_a_scenery_obstacle(self):
        self.assertIn("air:F", self.footprint_keys(flier(), infantry("I", x=100, y=100)))

    def test_a_routing_flier_still_blocks(self):
        f = flier(side=Side.ENEMY)
        f.routing = True
        self.assertIn("air:F", self.footprint_keys(f, infantry("I", x=100, y=100)))

    def test_a_landed_flier_is_an_ordinary_unit_footprint(self):
        self.assertNotIn("air:F", self.footprint_keys(flier(elevation=0), infantry("I", x=100, y=100)))


class ChargeAimTests(unittest.TestCase):
    """B2.4 and vector B9: a charge at an airborne unit aims at its centre."""

    def test_the_aim_point_is_the_centre(self):
        f, c = flier(side=Side.ENEMY), infantry("C", x=500, y=100)
        battle = battle_of(f, c)
        runner = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        self.assertEqual(runner._charge_aim_point(c, f), battle.formation_centre(f))


class TargetSearchTests(unittest.TestCase):
    """B2.7 and vectors B17-B18: the FindTarget family never picks an airborne unit."""

    def search(self, *others: Regiment) -> str | None:
        shooter = infantry("S", x=500, y=100, missile_code=1, shooting_code=1, missile_range=ranged.WEAPONS[1].reach,
                           hud_class="arch")
        battle = battle_of(shooter, *others)
        runner = interpreter.ScriptInterpreter(battle, battle.event_bus, None)
        return runner._weapon_target_search(shooter, 0, limited=False)

    def test_the_ground_enemy_is_picked_over_a_nearer_flier(self):
        self.assertEqual(self.search(flier(y=300, side=Side.ENEMY), infantry("I", y=600, side=Side.ENEMY)), "I")

    def test_a_lone_flier_is_not_found_until_it_lands(self):
        f = flier(y=300, side=Side.ENEMY)
        self.assertIsNone(self.search(f))
        self.assertEqual(self.search(flier(y=300, side=Side.ENEMY, elevation=0)), "F")


class SightTests(unittest.TestCase):
    """B2.6 and vectors B15-B16: an airborne unit blocks other units' sight lines like scenery."""

    def sees(self, elevation: int) -> bool:
        looker, target = infantry("L", x=500, y=100), infantry("T", x=500, y=400, side=Side.ENEMY)
        battle = battle_of(looker, target, flier(x=500, y=250, elevation=elevation))
        start, end = battle.formation_centre(looker), battle.formation_centre(target)
        return visibility.clear_ray(start, end, (), battle.sight_objects(looker, target))

    def test_an_airborne_flier_on_the_line_blocks_the_ray(self):
        self.assertFalse(self.sees(32))

    def test_a_grounded_flier_does_not(self):
        self.assertTrue(self.sees(0))

    def test_a_flier_behind_the_target_does_not_block(self):
        looker, target = infantry("L", x=500, y=100), infantry("T", x=500, y=400, side=Side.ENEMY)
        battle = battle_of(looker, target, flier(x=500, y=700))
        self.assertEqual(battle.sight_objects(looker, target), battle.objects)


class CrossbowLineTests(unittest.TestCase):
    """B2.7: an airborne friend over the line does not block a crossbow volley."""

    def test_an_airborne_friend_is_not_on_the_line(self):
        shooter = infantry("S", x=500, y=100, missile_code=2, shooting_code=2)
        battle = battle_of(shooter, flier(x=500, y=300))
        self.assertFalse(ranged._blocked_crossbow(battle, shooter, (500, 500)))
        battle = battle_of(shooter, infantry("G", x=500, y=300))
        self.assertTrue(ranged._blocked_crossbow(battle, shooter, (500, 500)))


if __name__ == "__main__":
    unittest.main()
