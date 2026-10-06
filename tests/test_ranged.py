"""Independent deterministic acceptance cases for public ranged combat handoff section 6."""
import unittest
from types import SimpleNamespace

from whshr import animation, combat, interpreter, ranged
from whshr.engine import Battle, Regiment
from whshr.rules import Side
from whshr.battle_scene import BattleScene


def unit(name, x, y, side=Side.PLAYER, *, code=1, models=10, cls="arch", bs=10, initiative=2):
    return Regiment(name, name, x, y, 0, side, models=models, ranks=2,
                    hud_class=cls, missile_code=code, shooting_code=code,
                    missile_range=ranged.WEAPONS[code].reach if code else None,
                    bs=bs, initiative=initiative, speed_per_tick=0)


class FixedRandom:
    """Only combat dice are fixed; animation can use the battle's seeded Random."""
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, low, high):
        return next(self.values)

    def choice(self, values):
        return values[0]

    def randrange(self, limit):
        return 0


class RangedOrders(unittest.TestCase):
    def setUp(self):
        self.shooter = unit("bow", 100, 100)
        self.enemy = unit("enemy", 100, 400, Side.ENEMY, code=0)
        self.battle = Battle(2000, 2000, [self.shooter, self.enemy], seed=11)

    def test_explicit_ten_model_volley_releases_three_from_posting_models(self):
        self.assertEqual(self.battle.order_fire("bow", "enemy"), 2008)
        self.battle.tick()
        self.assertEqual(self.shooter.reload_ticks, 101)
        self.assertEqual(self.shooter.shooting_target, "enemy")
        launches = []
        for _ in range(6):
            self.battle.tick()
            launches += [e for e in self.battle.events if e.kind == "projectile_launch"]
        self.assertEqual(len(launches), 3)
        self.assertEqual(len(self.battle.projectiles), 3)
        self.assertTrue(all(p.code == 1 and p.source == "bow" for p in self.battle.projectiles))

    def test_ground_refusal_checks_reload_then_arc_then_range(self):
        self.shooter.reload_ticks = 5
        self.battle.order_fire("bow", point=(600, 100))
        self.battle.tick()
        self.assertEqual([e.data["text_id"] for e in self.battle.events if e.kind == "ranged_message"], [2003])
        self.shooter.reload_ticks = 0
        self.battle.order_fire("bow", point=(100, 900))
        self.battle.tick()
        self.assertEqual([e.data["text_id"] for e in self.battle.events if e.kind == "ranged_message"], [2001])
        self.battle.order_fire("bow", point=(600, 100))
        self.battle.tick()
        self.assertEqual([e.data["text_id"] for e in self.battle.events if e.kind == "ranged_message"], [2002])

    def test_exact_arc_and_range_boundaries_are_refused(self):
        self.battle.order_fire("bow", point=(200, 200))  # exactly 45 degrees
        self.battle.tick()
        self.assertEqual([e.data["text_id"] for e in self.battle.events if e.kind == "ranged_message"], [2002])
        self.battle.order_fire("bow", point=(100, 676))  # exactly 576 world units
        self.battle.tick()
        self.assertEqual([e.data["text_id"] for e in self.battle.events if e.kind == "ranged_message"], [2001])

    def test_crossbow_waits_for_friend_then_fires_when_clear(self):
        bow = unit("cross", 100, 100, code=2)
        friend = unit("friend", 100, 250, code=0)
        battle = Battle(1000, 1000, [bow, friend, self.enemy], seed=2)
        battle.order_fire("cross", "enemy")
        for _ in range(7):
            battle.tick()
        self.assertEqual(len(battle.projectiles), 0)
        self.assertEqual(bow.shooting_target, "enemy")
        friend.x = 400
        for _ in range(7):
            battle.tick()
        self.assertGreater(len(battle.projectiles), 0)

    def test_target_moves_before_release_then_flight_does_not_home(self):
        self.battle.order_fire("bow", "enemy")
        self.battle.tick()
        self.enemy.x = 150
        for _ in range(6):
            self.battle.tick()
        self.assertTrue(self.battle.projectiles)
        self.assertTrue(all(p.x1 == 150 for p in self.battle.projectiles))
        self.enemy.x = 500
        destination = self.battle.projectiles[0].x1
        for _ in range(3):
            self.battle.tick()
        self.assertEqual(self.battle.projectiles[0].x1, destination)

    def test_target_lost_before_release_consumes_post_without_launch(self):
        self.battle.order_fire("bow", "enemy")
        self.battle.tick()
        self.enemy.models = 0
        self.shooter.fire_posts = 1
        self.shooter.fire_post_positions = [(100, 100)]
        ranged._launch_posts(self.battle)
        self.assertEqual(self.battle.projectiles, [])
        self.assertIsNone(self.shooter.shooting_mode)

    def test_independent_search_advances_toward_distant_enemy(self):
        self.shooter.independent = True
        self.enemy.y = 900
        self.battle.order_fire("bow", "bow")
        self.battle.tick()
        self.assertEqual(self.shooter.shooting_mode, "search")
        self.assertIsNotNone(self.shooter.target_y)

    def test_mobile_target_turns_then_fires_but_anchored_gun_does_not(self):
        self.enemy.x, self.enemy.y = 300, 100
        self.shooter.speed_per_tick = 4
        self.battle.order_fire("bow", "enemy")
        launches = 0
        for _ in range(100):
            self.battle.tick()
            launches += sum(e.kind == "projectile_launch" for e in self.battle.events)
            if launches:
                break
        self.assertGreater(launches, 0)
        self.assertEqual(self.shooter.shooting_target, "enemy")

        gun = unit("gun", 100, 100, code=11, models=4, cls="art")
        enemy = unit("enemy", 300, 100, Side.ENEMY, code=0)
        battle = Battle(1000, 1000, [gun, enemy])
        battle.order_fire("gun", "enemy")
        for _ in range(30):
            battle.tick()
        self.assertEqual(gun.direction, 0)
        self.assertEqual(gun.reload_ticks, 0)
        self.assertEqual(battle.projectiles, [])

    def test_full_pool_consumes_further_post(self):
        self.battle.projectiles = [ranged.Projectile("bow", 1, 0, 0, 0, 1, 1, 0, 0, 3, 1)
                                   for _ in range(32)]
        self.battle.order_fire("bow", "enemy")
        self.battle.tick()
        self.shooter.fire_posts = 1
        self.shooter.fire_post_positions = [(100, 100)]
        ranged._launch_posts(self.battle)
        self.assertEqual(len(self.battle.projectiles), 32)
        self.assertEqual(self.shooter.fire_posts, 0)

    def test_scene_dispatches_fire_without_starting_a_charge(self):
        scene = BattleScene.__new__(BattleScene)
        scene.battle, scene.selected_id, scene.logger = self.battle, "bow", None
        scene.handle(("fire", "enemy", (100, 400)), SimpleNamespace())
        self.assertEqual(self.shooter.shooting_target, "enemy")
        self.assertIsNone(self.shooter.attack_target)
        self.assertEqual(self.battle.pending_feedback[0].data["text_id"], 2008)

    def test_script_fire_at_point_uses_ranged_point_state(self):
        state = self.battle.event_bus.unit_states["bow"]
        state.target_point = (100, 300)
        state.aim_at_point = True
        runner = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        runner.op_FireAtTarget(state, None, [], "bow", 0, self.battle.rng)
        # notes/script_shooting.md 1.1: FireAtTarget is the launcher -- one projectile at the point, no charge.
        self.assertEqual([(p.x1, p.y1) for p in self.battle.projectiles], [(100, 300)])
        self.assertFalse(state.aim_at_point)
        self.assertIsNone(self.shooter.attack_target)

    def test_ctrl_gyrocopter_bomb_requires_airborne_and_drops_at_self(self):
        craft = unit("gyro", 100, 100, code=17, models=1)
        enemy = unit("enemy", 100, 200, Side.ENEMY, code=0)
        battle = Battle(1000, 1000, [craft, enemy])
        self.assertEqual(battle.order_fire("gyro", "enemy", bomb=True), 2020)
        self.assertIsNone(craft.shooting_mode)
        craft.airborne = True
        battle.order_fire("gyro", "enemy", bomb=True)
        battle.tick()
        craft.fire_posts = 1
        craft.fire_post_positions = [(100, 100)]
        battle.rng = FixedRandom([1, 0, 0])
        ranged._launch_posts(battle)
        self.assertEqual((battle.projectiles[0].x1, battle.projectiles[0].y1), (100, 100))
        self.assertEqual(battle.projectiles[0].z0, 72)

    def test_building_target_uses_ninety_percent_range_fallback(self):
        gun = unit("gun", 100, 100, code=11, models=4, cls="art")
        enemy = unit("enemy", 100, 400, Side.ENEMY, code=0)
        building = {"x": 100, "y": 1800, "radius": 20, "status": ["os_solid"]}
        battle = Battle(2000, 2000, [gun, enemy], objects=[building])
        self.assertEqual(battle.order_fire("gun", point=(100, 1800), object_index=0), 2007)
        battle.tick()
        self.assertAlmostEqual(gun.volley_aim[1], 100 + .9 * 1152)


class RangedDamage(unittest.TestCase):
    def test_intervening_unit_is_first_hit_during_flight(self):
        firer = unit("cross", 0, 0, code=2)
        blocker = unit("blocker", 0, 25, Side.ENEMY, code=0, models=1)
        target = unit("target", 0, 180, Side.ENEMY, code=0, models=1)
        battle = Battle(1000, 1000, [firer, blocker, target])
        battle.rng = FixedRandom([6, 1, 1] * 10)
        p = ranged.Projectile("cross", 2, 0, 0, 0, 0, 180, 0, 0, 4, 1,
                              x=0, y=0, z=0)
        battle.projectiles.append(p)
        for _ in range(5):
            ranged._step_projectiles(battle)
        self.assertFalse(battle.projectiles)
        self.assertEqual(blocker.models, 0)
        self.assertEqual(target.models, 1)

    def test_scenery_below_a_high_flight_does_not_intercept(self):
        firer = unit("rock", 0, 0, code=8, models=4, cls="art")
        enemy = unit("enemy", 0, 300, Side.ENEMY, code=0)
        scenery = {"x": 0, "y": 100, "radius": 20, "status": ["os_solid"]}
        battle = Battle(1000, 1000, [firer, enemy], objects=[scenery])
        p = ranged.Projectile("rock", 8, 0, 0, 24, 0, 300, 0, 60, 5, 6,
                              x=0, y=0, z=24)
        battle.projectiles.append(p)
        for _ in range(11):
            ranged._step_projectiles(battle)
        self.assertEqual(len(battle.projectiles), 1)

    def test_terminal_blast_can_return_to_firer(self):
        firer = unit("gun", 0, 0, code=11, models=4, cls="art")
        enemy = unit("enemy", 0, 300, Side.ENEMY, code=0)
        battle = Battle(1000, 1000, [firer, enemy])
        battle.rng = FixedRandom([6, 1, 4] * 20)
        p = ranged.Projectile("gun", 11, 0, 0, 0, 0, 0, 0, 24, 10, 4,
                              elapsed=8, x=0, y=0, z=0)
        battle.projectiles.append(p)
        ranged._step_projectiles(battle)
        self.assertLess(firer.models, 4)

    def test_direct_and_margin_blast_and_friendly_fire(self):
        firer = unit("gun", 0, 0, code=11, models=4, cls="art")
        direct = unit("direct", 0, 100, Side.ENEMY, code=0, models=3)
        margin = unit("margin", 32, 100, Side.PLAYER, code=0, models=3)
        battle = Battle(1000, 1000, [firer, direct, margin], seed=3)
        battle.rng = FixedRandom([6, 1, 4] * 20)
        p = ranged.Projectile("gun", 11, 0, 0, 0, 0, 100, 0, 24, 10, 4, x=0, y=100, z=0)
        ranged._impact(battle, p, flight=False)
        hits = {e.data["regiment"]: e for e in battle.events if e.kind == "projectile_hit"}
        self.assertTrue(hits["direct"].data["direct"])
        self.assertFalse(hits["margin"].data["direct"])
        self.assertLess(direct.models, 3)

    def test_building_uses_building_strength_and_first_model(self):
        firer = unit("gun", 0, 0, code=11, models=4, cls="art")
        building = Regiment("building", "building", 0, 100, 0, Side.ENEMY,
                            models=2, ranks=1, unit_class=9, armour=13)
        battle = Battle(1000, 1000, [firer, building])
        battle.rng = FixedRandom([6, 1, 4] * 10)
        p = ranged.Projectile("gun", 11, 0, 0, 0, 0, 100, 0, 24, 10, 4,
                              x=0, y=100, z=0, building_strength=10)
        ranged._impact(battle, p, flight=False)
        self.assertEqual(building.models, 1)

    def test_missile_corpse_appears_next_tick(self):
        firer = unit("bow", 0, 0)
        victim = unit("victim", 0, 100, Side.ENEMY, code=0, models=1)
        battle = Battle(1000, 1000, [firer, victim], seed=1)
        battle.rng = FixedRandom([6, 1, 1] * 10)
        p = ranged.Projectile("bow", 1, 0, 0, 0, 0, 100, 0, 0, 10, 1, x=0, y=100, z=0)
        ranged._impact(battle, p, flight=False)
        self.assertEqual(victim.models, 0)
        self.assertEqual(len(victim.dying), 1)
        self.assertEqual(victim.dying[0].death_kind, animation.DEATH_MISSILE)
        battle.tick()
        self.assertEqual(len(victim.corpses), 1)

    def test_innate_warpfire_reaches_the_burn_death_path(self):
        firer = Regiment("thrower", "thrower", 0, 0, 0, Side.PLAYER,
                          models=2, ranks=1, hud_class="inf", shooting_code=15,
                          missile_code=15, missile_range=576)
        victim = unit("victim", 0, 100, Side.ENEMY, code=0, models=1)
        battle = Battle(1000, 1000, [firer, victim])
        battle.rng = FixedRandom([1, 0, 0, 6] + [6, 0, 0, 6] * 10)
        firer.shooting_mode, firer.shooting_target = "target", "victim"
        ranged._launch_innate(battle, firer, 15, (0, 0))
        for _ in range(9):
            ranged._step_innate(battle)
        self.assertEqual(victim.models, 0)
        self.assertEqual(victim.dying[0].death_kind, animation.DEATH_WARPFIRE)

    def test_warpfire_thrower_death_puffs_then_blast(self):
        thrower = Regiment("thrower", "thrower", 100, 100, 0, Side.PLAYER,
                           models=1, sprite="WARPFIRE")
        victim = unit("victim", 100, 120, Side.ENEMY, code=0, models=1)
        battle = Battle(1000, 1000, [thrower, victim])
        battle.rng = FixedRandom([6, 1, 6] * 20)
        combat.kill_models(thrower, [0], battle, animation.DEATH_MISSILE)
        self.assertEqual([entry[0] for entry in battle.death_blasts], [0, 2, 4, 6, 8, 9])
        for _ in range(10):
            battle.tick()
        self.assertEqual(victim.models, 0)

    def test_giant_death_blast_is_reachable(self):
        giant = Regiment("giant", "giant", 100, 100, 0, Side.PLAYER,
                          models=1, sprite="GIANT")
        victim = unit("victim", 100, 120, Side.ENEMY, code=0, models=1)
        battle = Battle(1000, 1000, [giant, victim])
        battle.rng = FixedRandom([6, 1, 6] * 10)
        combat.kill_models(giant, [0], battle, animation.DEATH_MISSILE)
        battle.tick()
        self.assertEqual(victim.models, 0)

    def test_two_crew_gun_ready_one_crew_refuses(self):
        gun = unit("gun", 100, 100, code=11, models=2, cls="art", initiative=3)
        enemy = unit("enemy", 100, 400, Side.ENEMY, code=0)
        battle = Battle(1000, 1000, [gun, enemy])
        battle.order_fire("gun", "enemy")
        battle.tick()
        self.assertEqual(gun.reload_ticks, 198)
        gun.models = 1
        gun.reload_ticks = 0
        gun.volley_countdown = None
        battle.tick()
        self.assertEqual(gun.reload_ticks, 0)

    def test_both_artillery_misfires(self):
        for second, destroyed in ((2, False), (1, True)):
            gun = unit("gun", 100, 100, code=11, models=4, cls="art")
            enemy = unit("enemy", 100, 400, Side.ENEMY, code=0)
            battle = Battle(1000, 1000, [gun, enemy])
            battle.order_fire("gun", "enemy")
            gun.fire_posts = 1
            gun.fire_post_positions = [(100, 100)]
            battle.rng = FixedRandom([6, second] + [1] * 10)
            ranged._launch_posts(battle)
            self.assertEqual(gun.machine_alive, not destroyed)
            self.assertEqual(gun.anchor_cleared, destroyed)
            self.assertEqual(len(battle.projectiles), 0)
            self.assertEqual([e.data["text_id"] for e in battle.events if e.kind == "ranged_message"],
                             [2018 if destroyed else 2019])


class MixedBattleReplay(unittest.TestCase):
    def test_ranged_fire_continues_into_a_melee_and_replays_deterministically(self):
        def play():
            shooter = unit("archers", 100, 100)
            ally = Regiment("infantry", "infantry", 140, 300, 384, Side.PLAYER,
                            models=10, ranks=2, speed_per_tick=4)
            enemy = Regiment("enemy", "enemy", 100, 300, 0, Side.ENEMY,
                             models=10, ranks=2)
            battle = Battle(1000, 1000, [shooter, ally, enemy], seed=22)
            battle.order_fire("archers", "enemy")
            battle.order_attack("infantry", "enemy")
            events = []
            for _ in range(80):
                battle.tick()
                events.extend((event.kind, event.data) for event in battle.events)
            return events, ally.in_melee, enemy.models

        first = play()
        self.assertEqual(first, play())
        self.assertTrue(first[1])
        self.assertTrue(any(kind == "projectile_launch" for kind, _ in first[0]))


if __name__ == "__main__":
    unittest.main()
