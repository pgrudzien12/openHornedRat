"""A building's own map object: projectiles, ruins, the Fire pick and spells (notes/building_map_object.md)."""

import unittest
from types import SimpleNamespace

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import map_objects, ranged, spell_effects
from whshr.battle_scene import BattleScene
from whshr.ranged import Projectile
from whshr.rules import Side
from whshr.spell_effects import Impact
from tests.test_spell_effects import EffectTestCase


class Dice:
    """Queued results for `randint`, then the highest face for ever."""

    def __init__(self, *values):
        self.values = list(values)

    def randint(self, _low, high):
        return self.values.pop(0) if self.values else high


def battle(*scenery, objects=(), regiments=()):
    shooter = Regiment("S", "S", 1500, 1500, 0, Side.PLAYER, models=5, ranks=1, hud_class="art",
                       missile_code=11, shooting_code=11, missile_range=2000)
    return Battle(2000, 2000, [shooter, *regiments], seed=1995, scenery=list(scenery), objects=list(objects))


def entry(b, identifier="building:0"):
    return next(obj for obj in b.shooting_objects if obj.get("building") == identifier)


def shot(x, y, z=0.0, building_strength=0, wounds=1, radius=0):
    return Projectile(source="S", code=0, x0=1500, y0=1500, z0=0, x1=x, y1=y, z1=0, radius=radius, strength=3,
                      wounds=wounds, building_strength=building_strength, x=x, y=y, z=z)


TUDOR = {"name": "Tudor2Stry", "x": 500, "y": 500}


class ObjectTests(unittest.TestCase):
    """Section 1 and the section 8 bolt vectors: Tudor2Stry at (500, 500), radius 31, height 88."""

    def test_the_object_is_the_type_circle_at_the_type_height_and_not_solid(self):
        obj = entry(battle(TUDOR))
        self.assertEqual((obj["x"], obj["y"], obj["radius"], obj["height"]), (500, 500, 31, 88))
        self.assertTrue(map_objects.exists(obj))
        self.assertFalse(map_objects.pushes_units(obj))
        self.assertTrue(map_objects.blocks_sight(obj))

    def test_a_bolt_is_stopped_inside_the_circle_up_to_the_building_height(self):
        obj = entry(battle(TUDOR))
        self.assertEqual([map_objects.stops_projectile(obj, x, 500, h)
                          for x, h in ((520, 30), (531, 30), (520, 89), (520, 88))], [True, False, False, True])

    def test_walls_gates_and_towers_that_are_not_building_types_are_no_object(self):
        b = battle({"name": "LngWall", "x": 100, "y": 100}, {"name": "WoodGate", "x": 300, "y": 100},
                   {"name": "TwinTowers", "x": 500, "y": 100}, {"name": "WatchTower", "x": 700, "y": 100})
        self.assertEqual([obj["name"] for obj in b.shooting_objects], ["WatchTower"])
        self.assertEqual([x.name for x in b.buildings], ["WatchTower"])


class ProjectileDamageTests(unittest.TestCase):
    """Section 2: building-strength weapons hit directly in flight, the blast margin only on the terminal impact."""

    def test_a_cannonball_in_flight_inside_the_circle_is_a_direct_automatic_hit(self):
        b = battle(TUDOR)
        b.rng = Dice(3)  # the D4 wound die; S 10 against T 0 needs no roll
        ranged._damage_buildings(b, shot(510, 510, 40, building_strength=10, wounds=4), flight=True)
        self.assertEqual(b.buildings[0].wounds_taken, 3)

    def test_a_cannonball_in_flight_above_the_building_does_nothing(self):
        b = battle(TUDOR)
        ranged._damage_buildings(b, shot(510, 510, 89, building_strength=10, wounds=4), flight=True)
        self.assertEqual(b.buildings[0].wounds_taken, 0)

    def test_a_terminal_mortar_impact_in_the_margin_rolls_half_strength_for_one_wound(self):
        b = battle(TUDOR)
        b.rng = Dice(2)  # S 3 (7 / 2) against T 0 wounds on 2+
        ranged._damage_buildings(b, shot(540, 500, building_strength=7, wounds=3, radius=16), flight=False)
        self.assertEqual(b.buildings[0].wounds_taken, 1)

    def test_a_terminal_impact_just_outside_the_margin_does_nothing(self):
        b = battle(TUDOR)
        b.rng = Dice(6)
        ranged._damage_buildings(b, shot(547, 500, building_strength=7, wounds=3, radius=16), flight=False)
        self.assertEqual(b.buildings[0].wounds_taken, 0)

    def test_the_margin_never_applies_in_flight(self):
        b = battle(TUDOR)
        b.rng = Dice(6)
        ranged._damage_buildings(b, shot(540, 500, building_strength=7, wounds=3, radius=16), flight=True)
        self.assertEqual(b.buildings[0].wounds_taken, 0)


class TentTests(unittest.TestCase):
    """Section 7: a tent is a single-piece building, W 1, that stays an obstacle as a ruin."""

    TENT = {"name": "GrsOrcBoyzTent", "x": 200, "y": 200}

    def test_a_crossbow_bolt_is_stopped_by_a_tent_without_a_wound_roll(self):
        b = battle(self.TENT)
        self.assertTrue(map_objects.stops_projectile(entry(b), 210, 200, 20))
        b.rng = Dice()  # any draw would be popped from here
        ranged._damage_buildings(b, shot(210, 200, 20), flight=True)
        self.assertEqual((b.buildings[0].wounds_taken, b.rng.values), (0, []))

    def test_a_ruined_tent_still_stops_a_bolt_at_its_original_height(self):
        b = battle(self.TENT)
        b.destroy_building(b.buildings[0])
        obj = entry(b)
        self.assertEqual((obj["radius"], obj["height"]), (30, 40))
        self.assertTrue(map_objects.stops_projectile(obj, 210, 200, 20))
        self.assertFalse(map_objects.stops_projectile(obj, 210, 200, 41))


class FirePickTests(unittest.TestCase):
    """Section 4: only units and buildings are Fire candidates; buildings within max(radius, 48), strictly."""

    WELL = {"name": "Well2", "x": 100, "y": 100}

    def test_a_small_building_is_picked_within_48(self):
        b = battle(self.WELL)
        self.assertEqual(b.buildings[0].radius, 13)
        self.assertEqual(b.fire_pick_building(140, 100), 0)
        self.assertIsNone(b.fire_pick_building(148, 100))

    def test_a_plain_collision_object_is_never_picked_and_an_order_on_it_fires_at_the_ground(self):
        b = battle(objects=[{"x": 300, "y": 300, "radius": 60, "status": ["os_active", "os_solid"]}])
        self.assertIsNone(b.fire_pick_building(310, 300))
        self.assertIsNone(b.order_fire("S", point=(310, 300), object_index=0))
        self.assertEqual((b.regiments["S"].shooting_mode, b.regiments["S"].shooting_point), ("ground", (310, 300)))

    def test_a_destroyed_building_is_still_picked_with_text_2007(self):
        b = battle(TUDOR)
        b.destroy_building(b.buildings[0])
        index = b.fire_pick_building(500, 500)
        self.assertIsNotNone(index)
        self.assertEqual(b.order_fire("S", point=(500, 500), object_index=index), 2007)

    def test_a_building_wins_over_a_regiment_under_the_same_click(self):
        enemy = Regiment("E", "E", 520, 500, 0, Side.ENEMY, models=10, ranks=2)
        b = battle(TUDOR, regiments=[enemy])
        scene = BattleScene.__new__(BattleScene)
        scene.battle, scene.selected_id, scene.logger = b, "S", None
        scene.handle(("fire", "E", (510, 500)), SimpleNamespace())
        shooter = b.regiments["S"]
        self.assertEqual((shooter.shooting_mode, shooter.shooting_target), ("building", None))
        self.assertEqual(b.pending_feedback[0].data["text_id"], 2007)

    def test_a_regiment_away_from_buildings_is_picked_as_before(self):
        enemy = Regiment("E", "E", 800, 800, 0, Side.ENEMY, models=10, ranks=2)
        b = battle(TUDOR, regiments=[enemy])
        scene = BattleScene.__new__(BattleScene)
        scene.battle, scene.selected_id, scene.logger = b, "S", None
        scene.handle(("fire", "E", (800, 800)), SimpleNamespace())
        self.assertEqual(b.regiments["S"].shooting_target, "E")


class SpellTests(EffectTestCase):
    """Section 7 (b): bolts wound a building at the spell's S against T 0; area spells destroy it outright."""

    def make_with(self, *scenery):
        self.make()
        b = Battle(5000, 5000, list(self.battle.regiments.values()), seed=1995, scenery=list(scenery))
        b.phase, b.rng = "battle", self.battle.rng
        self.battle = b
        return b

    def test_a_fireball_hit_destroys_a_tent_on_2_or_more(self):
        b = self.make_with({"name": "GrsOrcBoyzTent", "x": 1000, "y": 1000})
        fireball = Impact(caster="W", strength=4, wound_die=1, save=False, fire=True)
        self.dice(0)  # roll 1: fails 2+
        self.assertTrue(spell_effects.impact_test(b, 1010, 1000, 5, fireball, None, False))
        self.assertFalse(b.buildings[0].destroyed)
        self.dice(1)  # roll 2
        spell_effects.impact_test(b, 1010, 1000, 5, fireball, None, False)
        self.assertTrue(b.buildings[0].destroyed)
        self.assertEqual(b.regiments["W"].kills, 1)

    def test_a_bolt_over_a_building_does_not_strike_it(self):
        b = self.make_with({"name": "GrsOrcBoyzTent", "x": 1000, "y": 1000})
        bolt = Impact(caster="W", strength=4, wound_die=1, save=False, fire=True)
        self.dice(5)
        self.assertFalse(spell_effects.impact_test(b, 1010, 1000, 41, bolt, None, False))
        self.assertEqual(b.buildings[0].wounds_taken, 0)

    def test_a_ruined_building_still_stops_a_bolt_but_takes_nothing(self):
        b = self.make_with({"name": "GrsOrcBoyzTent", "x": 1000, "y": 1000})
        b.destroy_building(b.buildings[0])
        bolt = Impact(caster="W", strength=4, wound_die=1, save=False, fire=True)
        self.assertTrue(spell_effects.impact_test(b, 1010, 1000, 5, bolt, None, False))
        self.assertEqual(b.buildings[0].wounds_taken, 0)

    def test_a_blast_margin_rolls_half_strength_for_one_wound(self):
        b = self.make_with(TUDOR)
        flames = Impact(caster="W", strength=4, wound_die=1, save=False, fire=True)
        self.dice(0)  # roll 1: S 2 against T 0 wounds on 2+, fails
        spell_effects.blast(b, 540, 500, 16, flames, None, False)
        self.dice(1)  # roll 2
        spell_effects.blast(b, 540, 500, 16, flames, None, False)
        self.assertEqual(b.buildings[0].wounds_taken, 1)

    def test_da_krunch_destroys_a_building_reaching_within_32(self):
        b = self.make_with({"name": "HumanTent", "x": 40, "y": 300}, {"name": "HumanTent", "x": 62, "y": 300})
        self.launch(spell_effects.DA_KRUNCH, 0, 300)
        self.update(10)
        self.assertEqual([x.destroyed for x in b.buildings], [True, False])
        self.assertEqual(b.regiments["W"].kills, 1)

    def test_conflagration_destroys_a_building_under_the_point_and_one_within_reach_at_the_finale(self):
        b = self.make_with({"name": "HumanTent", "x": 1000, "y": 1000}, {"name": "HumanTent", "x": 1040, "y": 1000},
                           {"name": "HumanTent", "x": 1046, "y": 1000})
        self.launch(spell_effects.CONFLAGRATION, 1000, 1000)  # k = 1: R 16, fuse 9 ticks
        self.update(10)  # the first fall tick
        self.assertEqual([x.destroyed for x in b.buildings], [True, False, False])
        self.update(10)  # through the finale on T+18: d 40 < 30 + 16, d 46 is not
        self.assertEqual([x.destroyed for x in b.buildings], [True, True, False])


if __name__ == "__main__":
    unittest.main()
