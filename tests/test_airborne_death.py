"""A flier killed in the air falls, crashes and shakes the camera (notes/airborne_units.md A5, GitHub #388)."""

import unittest
from unittest.mock import patch

from whshr import animation, camera_shake, combat, flight, ranged
from whshr.engine import Battle, Regiment
from whshr.rules import Side


def wyvern(elevation: int = 32, sprite: str = "Wyvern") -> Regiment:
    unit = Regiment("W", "Wyvern", 1000, 1000, 0, Side.ENEMY, models=1, ranks=1, sprite=sprite, leader_sprite=sprite)
    unit.flight_state().elevation = elevation
    return unit


def battle_of(*units: Regiment) -> Battle:
    battle = Battle(3000, 3000, list(units), seed=1995)
    battle.phase = "battle"
    return battle


def ticks(battle: Battle, count: int) -> None:
    for _ in range(count):
        battle.tick()


class FallTests(unittest.TestCase):
    """Vectors A10, A14-A16."""

    def test_a_wyvern_killed_in_the_air_falls_40_ticks_then_lies_down_and_crashes(self):
        w = wyvern()
        battle = battle_of(w)
        combat.kill_models(w, [0], battle, animation.DEATH_MISSILE)
        self.assertTrue(w.destroyed)  # the unit is gone at the first death tick
        self.assertEqual(len(w.falling), 1)
        falling = w.falling[0]
        with patch.object(ranged, "crash_blast") as blast:
            ticks(battle, 40)
            self.assertEqual((falling.elevation, w.corpses), (0, []))
            self.assertAlmostEqual(abs(complex(falling.x - 1000, falling.y - 1000)), 80, places=6)
            battle.tick()  # t41: the corpse frame
            self.assertEqual([c.group for c in w.corpses], [flight.WRECK_GROUP])
            blast.assert_not_called()
            self.assertIsNone(battle.camera_shake.current)
            battle.tick()  # t42: the blast, then the medium shake
            blast.assert_called_once()
            self.assertEqual(blast.call_args.args[4], animation.DEATH_MISSILE)
        self.assertEqual(battle.camera_shake.current.offsets, camera_shake.MEDIUM)
        self.assertEqual(w.falling, [])

    def test_a_gyrocopter_crashes_on_tick_34_and_burns_its_victims(self):
        g = wyvern(sprite="Gyrocopter")
        battle = battle_of(g)
        combat.kill_models(g, [0], battle, animation.DEATH_MISSILE)
        with patch.object(ranged, "crash_blast") as blast:
            ticks(battle, 33)
            blast.assert_not_called()
            battle.tick()
            self.assertEqual(blast.call_args.args[4], animation.DEATH_FIRE)
        self.assertTrue(any(effect[2] == 15 for effect in battle.impact_effects))  # the explosion sprite

    def test_a_flier_killed_during_its_take_off_counts_as_in_the_air(self):
        g = wyvern(elevation=8, sprite="Gyrocopter")
        battle = battle_of(g)
        combat.kill_models(g, [0], battle, animation.DEATH_MISSILE)
        self.assertEqual(len(g.falling), 1)

    def test_a_flier_killed_on_the_ground_lies_down_with_no_blast_or_shake(self):
        w = wyvern(elevation=0)
        battle = battle_of(w)
        with patch.object(ranged, "crash_blast") as blast:
            combat.kill_models(w, [0], battle, animation.DEATH_MISSILE)
            ticks(battle, 60)
        blast.assert_not_called()
        self.assertEqual(w.falling, [])
        self.assertIsNone(battle.camera_shake.current)


class CrashBlastTests(unittest.TestCase):
    """A5.4 and vectors A11-A13."""

    def test_the_margin_count(self):
        # Vector A11: footprint 40, crash point 50 from the centre, 20 models: (40 + 72 - 50) x 20 / 112 = 11 picks.
        unit = Regiment("E", "Enemy", 1050, 1000, 0, Side.PLAYER, models=20, ranks=4)
        battle = battle_of(unit)
        with patch.object(Regiment, "bounding_radius", return_value=40.0), \
                patch.object(ranged, "_damage_unit") as damage:
            ranged.crash_blast(battle, "W", 1000, 1000, animation.DEATH_MISSILE)
        args = damage.call_args
        self.assertEqual((args.args[3], args.args[4]), (False, 11))
        self.assertTrue(args.kwargs["quiet"])

    def test_a_direct_hit_strikes_every_model_and_credits_the_crashed_unit(self):
        friend = Regiment("F", "Friend", 1000, 1000, 0, Side.ENEMY, models=10, ranks=2)
        battle = battle_of(friend)
        with patch.object(ranged, "_damage_unit") as damage:
            ranged.crash_blast(battle, "W", 1000, 1000, animation.DEATH_MISSILE)
        self.assertTrue(damage.call_args.args[3])
        self.assertEqual(damage.call_args.args[2].source, "W")

    def test_an_airborne_unit_over_the_crash_is_not_hit(self):
        other = wyvern()
        other.identifier = "O"
        battle = battle_of(other)
        with patch.object(ranged, "_damage_unit") as damage:
            ranged.crash_blast(battle, "W", 1000, 1000, animation.DEATH_MISSILE)
        damage.assert_not_called()

    def test_no_messages(self):
        victim = Regiment("V", "Victim", 1000, 1000, 0, Side.PLAYER, models=10, ranks=2)
        battle = battle_of(victim)
        ranged.crash_blast(battle, "W", 1000, 1000, animation.DEATH_MISSILE)
        self.assertEqual([e for e in battle.events if e.kind == "projectile_hit"], [])


if __name__ == "__main__":
    unittest.main()
