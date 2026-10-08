import math
import random
import unittest

from whshr import combat, formation
from whshr.engine import Battle, MODEL_ARRIVAL_DISTANCE, Regiment, TICK_SECONDS, speed_per_tick
from whshr.rules import Side


class BattleTests(unittest.TestCase):
    def setUp(self):
        # M4 I3, matching the game_rules.md worked example: s_rlmv = trunc(4.8*4+3)/2 = 11.
        self.speed = speed_per_tick(4, 3)
        self.player = Regiment("player", "Player", 10, 10, 0, Side.PLAYER, models=1, ranks=1,
                               speed_per_tick=self.speed)
        # Far enough apart that these plain movement-only scenarios never bring the two footprints into
        # close-combat contact (whshr.formation.penetrates); combat tests live in tests/test_combat.py.
        self.enemy = Regiment("enemy", "Enemy", 90, 90, 0, Side.ENEMY, models=1, ranks=1,
                              speed_per_tick=self.speed)
        self.battle = Battle(100, 100, [self.player, self.enemy])

    def test_given_player_regiment_when_ordered_inside_field_then_it_moves_and_faces_destination(self):
        self.battle.order_move("player", 70, 10)
        self.battle.tick()

        # A single model turns on the spot (no snap, no pivot shift, no speed penalty) and moves at
        # full speed along its current facing while the turn toward the destination proceeds.
        self.assertGreater(self.player.direction, 0)
        self.assertLess(self.player.direction, 128)
        self.assertAlmostEqual(math.hypot(self.player.x - 10, self.player.y - 10), self.speed)
        self.assertTrue(self.player.moving)
        self.assertTrue(self.player.walking)

    def test_given_a_destination_within_32_units_when_ordered_then_the_unit_halts_at_once_and_re_forms(self):
        # notes/movement_formation.md 1.4: a plan that finds the point within 32 units halts and re-forms.
        self.battle.order_move("player", self.player.x, self.player.y + self.speed / 2)
        self.battle.tick()

        self.assertAlmostEqual(self.player.y, 10)
        self.assertFalse(self.player.moving)

    def test_given_enemy_or_outside_destination_when_ordered_then_the_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not player-controlled"):
            self.battle.order_move("enemy", 20, 20)
        with self.assertRaisesRegex(ValueError, "outside"):
            self.battle.order_move("player", 101, 10)

    def test_given_a_moving_or_charging_player_regiment_when_halted_then_its_order_is_cancelled(self):
        self.battle.order_move("player", 70, 10)
        self.battle.order_halt("player")
        self.assertFalse(self.player.moving)
        self.assertIsNone(self.player.attack_target)

        self.battle.order_attack("player", "enemy")
        self.battle.order_halt("player")
        self.assertFalse(self.player.moving)
        self.assertIsNone(self.player.attack_target)

    def test_given_a_routing_or_enemy_regiment_when_halted_then_the_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not player-controlled"):
            self.battle.order_halt("enemy")
        self.player.routing = True
        with self.assertRaisesRegex(ValueError, "routing"):
            self.battle.order_halt("player")

    def test_given_documented_movement_stat_when_computing_speed_then_it_matches_the_worked_example(self):
        # game_rules.md: "An M4 I3 infantry unit covers about 9.8 inches per turn moving freely."
        per_turn_inches = speed_per_tick(4, 3) * 190 / 24  # 190 ticks per turn, 24 world units per inch
        self.assertAlmostEqual(per_turn_inches, 9.8, places=1)

    def test_given_a_regiment_without_a_decoded_profile_when_built_then_it_gets_the_documented_placeholder(self):
        self.assertEqual(speed_per_tick(None, None), speed_per_tick(4, 3))

    def test_given_the_worked_example_s_rlmv_when_charge_reach_is_computed_then_it_matches_the_documented_formula(self):
        # game_rules.md "Charge": reaches at most 12 * (s_rlmv + 1) units; M4 I3 -> s_rlmv = 11.
        self.assertAlmostEqual(self.player.charge_reach, 12 * (11 + 1))


class LeaderLeadershipTests(unittest.TestCase):
    def test_living_leader_uses_own_ld_then_survivors_use_regiment_ld(self):
        from whshr.engine import _decode_combat_profile

        decoded = _decode_combat_profile({"profile": {"BS": 3, "Ld": 5},
                                          "leader": {"profile": {"BS": 7, "Ld": 9}}})
        self.assertEqual(decoded["bs"], 3)
        self.assertEqual(decoded["leader_leadership"], 9)
        unit = Regiment("archers", "Archers", 100, 100, 0, Side.PLAYER,
                        models=4, ranks=1, has_leader=True, **decoded)
        battle = Battle(1000, 1000, [unit])
        self.assertEqual(unit.effective_leadership, 9)
        unit.fight_harder = True
        self.assertEqual(unit.effective_leadership, 10)
        combat.kill_models(unit, [unit.living_leader_index], battle)
        self.assertEqual(unit.effective_leadership, 6)

    def test_zero_ld_leader_uses_regiment_ld(self):
        unit = Regiment("archers", "Archers", 100, 100, 0, Side.PLAYER,
                        models=4, ranks=1, has_leader=True, leadership=6, leader_leadership=0)
        Battle(1000, 1000, [unit])
        self.assertEqual(unit.effective_leadership, 6)


class MountedMovementTests(unittest.TestCase):
    """game_rules.md "Mounts": a mounted rider uses the mount's M and the rider's I."""

    def _regiment_from_script(self, mount, armour):
        unit = {
            "id": "rider", "name": "Rider", "set": {"x": 100, "y": 100},
            "stats": {"s_side": [0, 10, 10, 2], "s_mount": [mount, armour]},
            "profile": {"M": 4, "I": 3},
        }
        source = {"field": {"width": 1000, "height": 1000},
                  "armies": [{"units": [unit]}], "merc": None}
        return Battle.from_script(source).regiments["rider"]

    def test_given_a_warhorse_rider_when_built_then_speed_and_charge_reach_use_the_mounts_movement(self):
        # game_rules.md "Mounts": "A rider on a Warhorse (M7) with I3 gets a speed stat of 18
        # against 11 on foot (M4 I3) -- about 64% more of everything above, and a charge reach of
        # 228 world units (9.5") instead of 144 (6")."
        mounted = self._regiment_from_script(1, 8)
        unmounted = self._regiment_from_script(1, 0)

        self.assertAlmostEqual(mounted.speed_per_tick, speed_per_tick(7, 3))
        self.assertAlmostEqual(unmounted.speed_per_tick, speed_per_tick(4, 3))
        self.assertAlmostEqual(mounted.speed_per_tick / unmounted.speed_per_tick, 18 / 11, places=2)
        self.assertAlmostEqual(mounted.charge_reach, 228)
        self.assertAlmostEqual(unmounted.charge_reach, 144)

    def test_given_other_mounts_when_built_then_each_uses_its_own_movement_with_the_riders_initiative(self):
        for mount, movement in ((2, 6), (3, 8), (4, 5)):
            with self.subTest(mount=mount):
                regiment = self._regiment_from_script(mount, 13)
                self.assertAlmostEqual(regiment.speed_per_tick, speed_per_tick(movement, 3))

    def test_given_a_mount_without_mounted_armour_when_built_then_the_rider_keeps_foot_speed(self):
        for armour in (0, 7):
            with self.subTest(armour=armour):
                regiment = self._regiment_from_script(3, armour)
                self.assertAlmostEqual(regiment.speed_per_tick, speed_per_tick(4, 3))

    def test_given_no_rider_initiative_when_mounted_then_speed_uses_the_regiments_default_initiative(self):
        unit = {"stats": {"s_mount": [1, 8]}, "profile": {"M": 4}}

        from whshr.engine import _decode_combat_profile
        decoded = _decode_combat_profile(unit)

        self.assertEqual(decoded["initiative"], 3)
        self.assertAlmostEqual(decoded["speed_per_tick"], speed_per_tick(7, 3))

    def test_given_equal_formations_when_one_has_a_mount_then_charge_grant_uses_the_same_frontage(self):
        for armour in (0, 8):
            with self.subTest(armour=armour):
                rider = self._regiment_from_script(1, armour)
                enemy = Regiment("enemy", "Enemy", rider.x, rider.y, 0, Side.ENEMY,
                                 models=10, ranks=2)
                battle = Battle(1000, 1000, [rider, enemy])
                rider.attack_target = enemy.identifier

                combat.resolve_contacts(battle)

                self.assertEqual(rider.charge_counter, 7)

    def test_given_mounted_and_unmounted_riders_when_contact_attacking_then_mount_speed_does_not_change_reach(self):
        for armour in (0, 8):
            rider = self._regiment_from_script(1, armour)
            rider.models = 1
            rider.positions = [(0, 0)]
            target = Regiment("target", "Target", 0, 0, 0, Side.ENEMY)
            for distance, in_reach in ((12, True), (13, False)):
                with self.subTest(armour=armour, distance=distance):
                    target.positions = [(distance, 0)]
                    _victims, rolls = combat._contact_attack_rolls(rider, target, random.Random(0))
                    self.assertEqual(bool(rolls), in_reach)


class BracedOrderGatingTests(unittest.TestCase):
    """game_rules.md "Braced": move/attack orders are ignored while braced -- for a player's own
    click exactly as for a script's own order (whshr.interpreter.op_FearWhenCharged, op_ChargeTarget);
    Halt is the one order still accepted, and it clears the status."""

    def setUp(self):
        self.speed = speed_per_tick(4, 3)
        self.player = Regiment("player", "Player", 10, 10, 0, Side.PLAYER, models=1, ranks=1,
                               speed_per_tick=self.speed)
        self.enemy = Regiment("enemy", "Enemy", 90, 90, 0, Side.ENEMY, models=1, ranks=1,
                              speed_per_tick=self.speed)
        self.battle = Battle(100, 100, [self.player, self.enemy])
        self.player.braced = True
        self.player.braced_target = "enemy"

    def test_given_a_braced_regiment_when_moved_then_the_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "braced"):
            self.battle.order_move("player", 70, 10)

    def test_given_a_braced_regiment_when_attacked_then_the_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "braced"):
            self.battle.order_attack("player", "enemy")

    def test_given_a_braced_regiment_when_halted_then_the_order_is_accepted_and_clears_braced(self):
        self.battle.order_halt("player")
        self.assertFalse(self.player.braced)
        self.assertIsNone(self.player.braced_target)

    def test_given_script_resources_with_variant_suffixes_when_built_then_their_resource_names_are_normalized(self):
        source = {
            "field": {"width": 100, "height": 100},
            "armies": [{"units": [{
                "id": "unit", "name": "Unit", "sprites": "ClanRats,0", "banner": "BannerHiln,0",
                "leader": {"portrait": "Commander,0"}, "set": {"x": 10, "y": 10}, "stats": {},
            }]}],
            "merc": None,
        }

        regiment = Battle.from_script(source).regiments["unit"]

        self.assertEqual((regiment.sprite, regiment.banner, regiment.portrait),
                         ("ClanRats", "BannerHiln", "Commander"))

    def test_given_a_units_s_pntval_stat_when_built_then_it_becomes_the_regiments_points(self):
        # game_rules.md: unit worth (AI threat scoring, whshr.interpreter's IfThreatOutweighsWorth)
        # is size x s_pntval x a class multiplier -- points must reach Regiment for that to work.
        source = {
            "field": {"width": 100, "height": 100},
            "armies": [{"units": [{
                "id": "unit", "name": "Unit", "set": {"x": 10, "y": 10}, "stats": {"s_pntval": [7]},
            }]}],
            "merc": None,
        }

        regiment = Battle.from_script(source).regiments["unit"]

        self.assertEqual(regiment.points, 7)

    def test_given_no_s_pntval_stat_when_built_then_points_defaults_to_zero(self):
        source = {
            "field": {"width": 100, "height": 100},
            "armies": [{"units": [{
                "id": "unit", "name": "Unit", "set": {"x": 10, "y": 10}, "stats": {},
            }]}],
            "merc": None,
        }

        regiment = Battle.from_script(source).regiments["unit"]

        self.assertEqual(regiment.points, 0)


class FormationMovementTests(unittest.TestCase):
    """Models walk to their formation slots instead of teleporting with the block."""

    def setUp(self):
        self.speed = speed_per_tick(4, 3)
        self.regiment = Regiment("player", "Player", 0, 0, 0, Side.PLAYER, models=6, ranks=2,
                                 speed_per_tick=self.speed)
        self.battle = Battle(1000, 1000, [self.regiment])

    def test_given_a_regiment_when_it_first_ticks_then_models_start_already_in_formation(self):
        self.battle.tick()

        self.assertEqual(len(self.regiment.model_positions()), 6)
        self.assertFalse(self.regiment.walking)

    def test_given_a_turning_order_when_ticked_once_then_models_have_not_yet_reached_their_new_slots(self):
        # A destination to the side turns the block, so a rigid teleport and a catch-up walk disagree.
        self.battle.order_move("player", 500, 0)

        self.battle.tick()

        positions, ideal = self.regiment.model_positions(), formation_positions(self.regiment)
        distances = [math.hypot(x - ix, y - iy) for (x, y), (ix, iy) in zip(positions, ideal)]
        self.assertTrue(any(distance > 1.0 for distance in distances))
        self.assertTrue(self.regiment.walking)

    def test_given_a_regiment_walking_to_a_far_order_when_many_ticks_pass_then_it_settles_back_in_formation(self):
        self.battle.order_move("player", 500, 0)
        for _ in range(2000):
            self.battle.tick()

        self.assertFalse(self.regiment.moving)
        self.assertFalse(self.regiment.walking)
        expected = formation_positions(self.regiment)
        for (x, y), (ex, ey) in zip(self.regiment.model_positions(), expected):
            self.assertLessEqual(math.hypot(x - ex, y - ey), 3)


class CatchUpWalkTests(unittest.TestCase):
    """game_rules.md "Models chase the unit": each model walks from its stored world position."""

    def test_given_four_ranks_when_the_anchor_moves_then_front_and_rear_models_take_rank_dependent_steps(self):
        regiment = Regiment("block", "Block", 0, 0, 0, Side.PLAYER, models=20, ranks=4,
                            speed_per_tick=speed_per_tick(4, 3))
        battle = Battle(1000, 1000, [regiment])
        before = list(regiment.model_positions())
        regiment.y = 100

        battle._advance_models(regiment, 1)

        self.assertEqual(regiment.melee_models[0].current_speed, 1)
        self.assertAlmostEqual(regiment.positions[0][1] - before[0][1], 36 * 2.4 / 256)
        self.assertAlmostEqual(regiment.positions[16][1] - before[16][1], 12 * 2.4 / 256)

    def test_given_a_model_already_walking_when_its_slot_changes_direction_then_it_keeps_its_heading_until_budget_runs_out(self):
        regiment = Regiment("model", "Model", 0, 0, 0, Side.PLAYER,
                            speed_per_tick=speed_per_tick(4, 3))
        battle = Battle(1000, 1000, [regiment])
        regiment.model_positions()
        regiment.x = 100
        battle._advance_models(regiment, 1)
        first_x, first_y = regiment.positions[0]
        regiment.y = 100

        battle._advance_models(regiment, 1)

        self.assertGreater(regiment.positions[0][0], first_x)
        self.assertEqual(regiment.positions[0][1], first_y)
        self.assertEqual(regiment.melee_models[0].current_speed, 2)

    def test_given_a_slot_within_three_units_when_advanced_then_the_model_is_at_rest(self):
        regiment = Regiment("model", "Model", 0, 0, 0, Side.PLAYER)
        battle = Battle(1000, 1000, [regiment])
        regiment.model_positions()
        regiment.x = 2

        moving = battle._advance_models(regiment, 1)

        self.assertFalse(moving)
        self.assertEqual(regiment.positions[0], (0, 0))
        self.assertTrue(regiment.melee_models[0].at_rest)

    def test_given_a_broken_regiment_when_models_catch_up_then_speed_is_not_capped_at_s_rlmv(self):
        regiment = Regiment("model", "Model", 0, 0, 0, Side.PLAYER, routing=True,
                            speed_per_tick=speed_per_tick(4, 3))
        battle = Battle(1000, 1000, [regiment])
        regiment.model_positions()
        regiment.x = 100

        for _ in range(20):
            battle._advance_models(regiment, 1)

        self.assertEqual(regiment.melee_models[0].current_speed, 20)

    def test_given_a_wagon_when_models_catch_up_then_its_two_models_use_the_four_deep_rank_factors(self):
        source = {"field": {"width": 1000, "height": 1000}, "merc": None,
                  "armies": [{"units": [{
                      "id": "wagon", "name": "Wagon", "set": {"x": 0, "y": 0},
                      "stats": {"s_side": [0, 2, 2, 2], "s_race": [7 * 8]},
                      "profile": {"M": 4, "I": 3},
                  }]}]}
        battle = Battle.from_script(source)
        regiment = battle.regiments["wagon"]
        before = list(regiment.model_positions())
        regiment.y = 100

        battle._advance_models(regiment, 1)

        self.assertAlmostEqual(regiment.positions[0][1] - before[0][1], 36 * 2.4 / 256)
        self.assertAlmostEqual(regiment.positions[1][1] - before[1][1], 32 * 2.4 / 256)  # 28 + stagger 29 & 6 == 4


class ReformOrderGatingTests(unittest.TestCase):
    """game_rules.md "Formation changes": refused while fleeing, held or charging; the requested rank
    count is clamped into `formation.rank_range`."""

    def setUp(self):
        self.regiment = Regiment("block", "Block", 0, 0, 0, Side.PLAYER, models=8, ranks=2,
                                 speed_per_tick=speed_per_tick(4, 3))
        self.enemy = Regiment("enemy", "Enemy", 200, 0, 0, Side.ENEMY, models=1, ranks=1)
        self.battle = Battle(1000, 1000, [self.regiment, self.enemy])

    def test_given_a_player_regiment_when_ordered_then_it_reslots_and_begins_reforming(self):
        before = list(self.regiment.model_positions())

        self.battle.order_reform("block", 4)

        self.assertEqual(self.regiment.ranks, 4)
        self.assertTrue(self.regiment.reforming)
        self.assertEqual(len(self.regiment.reform_slots), 8)
        # every model keeps its own current position until Battle.tick moves it
        self.assertEqual(self.regiment.positions, before)

    def test_given_a_request_outside_the_clamp_when_ordered_then_it_is_pulled_into_range(self):
        self.battle.order_reform("block", 1)  # formation.rank_range(8) == (2, 4)

        self.assertEqual(self.regiment.ranks, 2)

    def test_given_a_fleeing_regiment_when_reform_is_ordered_then_it_is_refused(self):
        self.regiment.routing = True

        with self.assertRaisesRegex(ValueError, "routing"):
            self.battle.order_reform("block", 4)

    def test_given_a_held_regiment_when_reform_is_ordered_then_it_is_refused(self):
        self.regiment.held = True

        with self.assertRaisesRegex(ValueError, "held"):
            self.battle.order_reform("block", 4)

    def test_given_a_charging_regiment_when_reform_is_ordered_then_it_is_refused(self):
        self.battle.order_attack("block", "enemy")

        with self.assertRaisesRegex(ValueError, "charging"):
            self.battle.order_reform("block", 4)

    def test_given_a_regiment_in_melee_when_reform_is_ordered_then_it_is_refused(self):
        self.regiment.in_melee = True

        with self.assertRaisesRegex(ValueError, "charging or in melee"):
            self.battle.order_reform("block", 4)

    def test_given_a_non_player_or_out_of_range_request_when_ordered_then_it_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not player-controlled"):
            self.battle.order_reform("enemy", 2)


class ReformSlottingTests(unittest.TestCase):
    """game_rules.md "Formation changes": the leader is handed the front-rank centre slot directly,
    and every other model takes the nearest not-yet-placed slot."""

    def test_given_a_rank_count_change_when_reslotted_then_the_shape_matches_the_documented_layout(self):
        regiment = Regiment("block", "Block", 0, 0, 0, Side.PLAYER, models=18, ranks=4,
                            speed_per_tick=speed_per_tick(4, 3))
        battle = Battle(1000, 1000, [regiment])
        regiment.model_positions()

        battle.order_reform("block", 3)

        self.assertEqual(formation.rank_sizes(18, 3), [6, 6, 6])
        self.assertEqual(len(regiment.reform_slots), 18)
        targets = formation.place(regiment.x, regiment.y, regiment.direction, regiment.reform_slots)
        self.assertEqual(len(set(targets)), 18)  # every model gets a distinct slot
        self.assertEqual(set(regiment.reform_slots), set(formation.block_slots(18, 3)))

    def test_given_no_leader_identity_when_reslotted_then_the_model_nearest_the_centre_stands_in(self):
        regiment = Regiment("model", "Model", 0, 0, 0, Side.PLAYER, models=3, ranks=1,
                            speed_per_tick=speed_per_tick(4, 3))
        battle = Battle(1000, 1000, [regiment])
        positions = regiment.model_positions()
        # model 1 already sits on the front-rank centre slot (0, 0)
        self.assertEqual(positions[1], (0.0, 0.0))

        battle.order_reform("model", 1)

        self.assertEqual(regiment.reform_slots[1], (0.0, 0.0))


class FlatReformMoverTests(unittest.TestCase):
    """notes/reform_while_moving.md 3 (shuffle mode): every figure steps a flat `s_rlmv / 8` world units/tick
    with no cap and no ramp-up; inside the last 6 world units the step is divided by `7 - d` and each axis
    capped at 1; a figure whose rounded offset to its slot is zero arrives and snaps its heading to the unit
    facing; at-rest figures are skipped until a new layout wakes them."""

    def _regiment(self, **kwargs):
        fields = {"models": 1, "ranks": 1, "direction": 0, "speed_per_tick": speed_per_tick(4, 3)}
        fields.update(kwargs)
        regiment = Regiment("m", "M", 0, 0, fields.pop("direction"), Side.PLAYER, **fields)
        return regiment, Battle(1000, 1000, [regiment])

    @staticmethod
    def _start(regiment, positions, slots):
        """A shuffle re-form set up by hand: figures at `positions`, assigned `slots`, all awake."""
        regiment.model_positions()
        regiment.positions = list(positions)
        regiment.reform_slots = list(slots)
        regiment.reforming = True
        for model in regiment.melee_models:
            model.at_rest = False

    @staticmethod
    def _s_rlmv(regiment):
        return regiment.speed_per_tick * 16 / 1.8

    def test_moving_cavalry_finishes_reform_while_its_anchor_advances(self):
        regiment, battle = self._regiment(models=12, ranks=3, speed_per_tick=2.25)
        regiment.x = regiment.y = 100.0
        regiment.model_positions()
        self._start(regiment, [(x, y - 20) for x, y in regiment.positions],
                    formation.block_slots(regiment.models, regiment.ranks))
        regiment.target_x, regiment.target_y = 100.0, 400.0

        for _ in range(45):
            battle.tick()

        self.assertFalse(regiment.reforming)
        self.assertGreater(regiment.y, 150.0)

    def test_given_a_model_far_from_its_slot_when_advanced_then_it_steps_s_rlmv_over_8_without_a_cap(self):
        regiment, battle = self._regiment(speed_per_tick=20 * 1.8 / 16)  # s_rlmv 20
        self._start(regiment, [(0.0, 0.0)], [(0.0, 10.0)])

        battle._advance_reforming_models(regiment, 1)

        self.assertAlmostEqual(regiment.positions[0][1], 2.5)  # 20 / 8, no cap outside the last 6 units

    def test_given_a_fast_model_inside_the_deceleration_zone_when_advanced_then_each_axis_is_capped_at_one(self):
        regiment, battle = self._regiment(speed_per_tick=20 * 1.8 / 16)
        self._start(regiment, [(0.0, 0.0)], [(0.0, 5.0)])

        battle._advance_reforming_models(regiment, 1)

        self.assertAlmostEqual(regiment.positions[0][1], 1.0)  # 2.5 / (7 - 5) = 1.25, capped

    def test_given_a_fast_model_stepping_in_a_negative_direction_when_decelerating_then_it_is_capped_too(self):
        regiment, battle = self._regiment(speed_per_tick=20 * 1.8 / 16)
        self._start(regiment, [(0.0, 0.0)], [(0.0, -5.0)])

        battle._advance_reforming_models(regiment, 1)

        self.assertAlmostEqual(regiment.positions[0][1], -1.0)  # engine caps both signs (report 3 allows it)

    def test_given_a_slow_model_three_units_from_its_slot_when_advanced_then_its_step_is_divided(self):
        regiment, battle = self._regiment(speed_per_tick=8 * 1.8 / 16)  # s_rlmv 8
        self._start(regiment, [(0.0, 0.0)], [(0.0, 3.0)])

        battle._advance_reforming_models(regiment, 1)

        self.assertAlmostEqual(regiment.positions[0][1], 0.25)  # 1.0 / (7 - 3)

    def test_given_a_reaimed_figure_when_its_slot_is_ahead_then_its_heading_points_at_the_slot(self):
        regiment, battle = self._regiment(direction=128)
        self._start(regiment, [(0.0, -30.0)], [(0.0, 0.0)])
        slot = formation.place(regiment.x, regiment.y, regiment.direction, regiment.reform_slots)[0]

        battle._advance_reforming_models(regiment, 1)

        model = regiment.melee_models[0]
        bearing = math.atan2(slot[0] - 0.0, slot[1] + 30.0)
        self.assertAlmostEqual(model.heading_x, math.sin(bearing))
        self.assertAlmostEqual(model.heading_y, math.cos(bearing))

    def test_given_a_figure_whose_rounded_offset_is_zero_when_advanced_then_it_arrives_and_snaps_heading(self):
        regiment, battle = self._regiment(direction=128)
        slot = formation.place(0, 0, 128, [(0.0, 0.0)])[0]
        self._start(regiment, [(slot[0] - 0.4, slot[1] + 0.3)], [(0.0, 0.0)])

        still_moving = battle._advance_reforming_models(regiment, 1)

        self.assertFalse(still_moving)
        self.assertAlmostEqual(regiment.positions[0][0], slot[0])
        self.assertAlmostEqual(regiment.positions[0][1], slot[1])
        model = regiment.melee_models[0]
        self.assertTrue(model.at_rest)
        angle = 128 * math.tau / 512
        self.assertAlmostEqual(model.heading_x, math.sin(angle))
        self.assertAlmostEqual(model.heading_y, math.cos(angle))

    def test_given_a_figure_one_unit_off_its_slot_when_advanced_then_it_still_steps(self):
        regiment, battle = self._regiment()
        self._start(regiment, [(0.0, -1.0)], [(0.0, 0.0)])

        self.assertTrue(battle._advance_reforming_models(regiment, 1))
        self.assertGreater(regiment.positions[0][1], -1.0)

    def test_given_a_figure_at_rest_when_advanced_then_it_is_skipped(self):
        regiment, battle = self._regiment()
        self._start(regiment, [(0.0, -30.0)], [(0.0, 0.0)])
        regiment.melee_models[0].at_rest = True

        battle._advance_reforming_models(regiment, 1)

        self.assertEqual(regiment.positions[0], (0.0, -30.0))

    def test_given_a_figure_in_a_timed_pause_when_advanced_then_it_waits_and_the_reform_goes_on(self):
        regiment, battle = self._regiment()
        self._start(regiment, [(0.0, 0.0)], [(0.0, 0.0)])
        regiment.melee_models[0].freeze_ticks = 2

        self.assertTrue(battle._advance_reforming_models(regiment, 1))
        self.assertEqual(regiment.melee_models[0].freeze_ticks, 1)
        self.assertTrue(regiment.reforming)

    def _two_model_regiment(self, walker, slots):
        regiment, battle = self._regiment(models=2, ranks=1)
        self._start(regiment, [walker, (0.0, 0.0)], slots)
        regiment.melee_models[1].at_rest = True
        return regiment, battle

    def test_given_a_walker_about_to_step_onto_a_settled_comrade_when_advanced_then_slots_are_exchanged(self):
        regiment, battle = self._two_model_regiment((0.0, -5.5), [(0.0, 40.0), (0.0, 0.0)])

        battle._advance_reforming_models(regiment, 1)

        self.assertEqual(regiment.reform_slots, [(0.0, 0.0), (0.0, 40.0)])
        self.assertEqual(regiment.positions[0], (0.0, -5.5))  # inherited the place; did not step

    def test_given_a_swap_when_advanced_then_the_woken_model_walks_to_the_walkers_original_target(self):
        regiment, battle = self._two_model_regiment((0.0, -5.5), [(0.0, 40.0), (0.0, 0.0)])

        battle._advance_reforming_models(regiment, 1)
        self.assertFalse(regiment.melee_models[1].at_rest)
        battle._advance_reforming_models(regiment, 1)

        self.assertGreater(regiment.positions[1][1], 0.0)

    def test_given_no_settled_comrade_nearby_when_advanced_then_slots_are_unchanged(self):
        regiment, battle = self._two_model_regiment((0.0, -50.0), [(0.0, 40.0), (0.0, 0.0)])

        battle._advance_reforming_models(regiment, 1)

        self.assertEqual(regiment.reform_slots, [(0.0, 40.0), (0.0, 0.0)])
        self.assertGreater(regiment.positions[0][1], -50.0)

    def test_given_the_last_model_settles_when_ticked_then_reforming_clears_and_a_complete_event_fires(self):
        regiment, battle = self._regiment()
        regiment.model_positions()
        battle.reform_to_ranks(regiment, 1)

        battle.tick()

        self.assertFalse(regiment.reforming)
        self.assertEqual(regiment.reform_slots, [])
        self.assertTrue(any(event.kind == "reform_complete" for event in battle.events))

    def test_given_a_reform_in_progress_when_the_unit_also_moves_then_its_translation_speed_is_halved(self):
        regiment, battle = self._regiment(models=8, ranks=2)
        regiment.model_positions()
        # Straight ahead along the current facing, so the order needs no turn and the step is pure
        # translation (a turn's own snap/pivot correction is a separate, already-tested mechanic).
        battle.order_move("m", 0, 500)
        battle.order_reform("m", 4)

        battle.tick()

        self.assertAlmostEqual(regiment.y, regiment.speed_per_tick * 0.5)

    def test_given_a_moving_reform_when_ticked_then_figures_are_carried_and_step_on_top(self):
        # Report 10, first vector: anchor moving +X at 1.0/tick (already halved), figure at unit-relative
        # (0, -30), slot (0, 0), s_rlmv 20 -> world position += (1.0, 0) carried + (0, 2.5) shuffle step.
        regiment, battle = self._regiment(direction=128, speed_per_tick=20 * 1.8 / 16)
        regiment.model_positions()
        battle.order_move("m", 500, 0)
        self._start(regiment, [(0.0, -30.0)], [(0.0, 0.0)])
        before_x = regiment.x

        battle.tick()

        moved = regiment.x - before_x
        self.assertAlmostEqual(moved, regiment.speed_per_tick * 0.5)
        self.assertAlmostEqual(regiment.positions[0][0], moved, places=5)
        self.assertGreater(regiment.positions[0][1], -30.0 + 2.0)

    def test_given_a_multi_model_unit_when_reforming_completes_then_every_model_is_at_rest_by_its_slot(self):
        regiment, battle = self._regiment(models=8, ranks=2)
        battle.order_reform("m", 4)

        for _ in range(60):
            battle.tick()

        self.assertFalse(regiment.reforming)
        self.assertTrue(all(model.at_rest for model in regiment.melee_models))
        targets = formation.place(regiment.x, regiment.y, regiment.direction,
                                  formation.block_slots(regiment.models, regiment.ranks))
        # A walker that inherits a settled comrade's slot stops where it stands, about half a spacing off.
        for (x, y), (tx, ty) in zip(regiment.positions, targets):
            self.assertLessEqual(math.hypot(x - tx, y - ty), MODEL_ARRIVAL_DISTANCE)

    def test_given_cavalry_100_units_off_when_reforming_then_it_settles_in_about_47_ticks(self):
        # Report 3 settle-time table: s_rlmv 20, 100 units -> about 47 ticks (+-1).
        regiment, battle = self._regiment(speed_per_tick=20 * 1.8 / 16)
        self._start(regiment, [(0.0, -100.0)], [(0.0, 0.0)])

        ticks = 0
        while regiment.reforming and ticks < 200:
            battle._advance_reforming_models(regiment, 1)
            ticks += 1

        self.assertLessEqual(abs(ticks - 47), 2)


class WalkBackReformTests(unittest.TestCase):
    """notes/reform_while_moving.md 2, 6, 8: the Rally re-form uses walk-back mode -- the ordinary catch-up walk,
    figures carried, the unit's speed not halved, arrival keeps the heading -- and engagement ends any re-form."""

    def _regiment(self, **kwargs):
        regiment = Regiment("m", "M", 100, 100, 0, Side.PLAYER, models=kwargs.pop("models", 10),
                            ranks=kwargs.pop("ranks", 2), speed_per_tick=20 * 1.8 / 16, **kwargs)
        return regiment, Battle(1000, 1000, [regiment])

    def test_given_a_rally_re_form_when_laid_out_then_it_is_in_walk_back_mode_in_raster_order(self):
        regiment, battle = self._regiment()
        regiment.model_positions()
        regiment.positions = [(x - 40, y) for x, y in regiment.positions]

        battle.reform_to_ranks(regiment, 3, walk_back=True)

        self.assertTrue(regiment.reforming)
        self.assertTrue(regiment.reform_walk_back)
        self.assertEqual(regiment.reform_slots, formation.block_slots(regiment.models, 3))

    def test_given_a_walk_back_re_form_when_the_unit_moves_then_its_speed_is_not_halved(self):
        regiment, battle = self._regiment()
        regiment.model_positions()
        battle.order_move("m", 100, 600)
        battle.reform_to_ranks(regiment, 3, walk_back=True)

        battle.tick()

        self.assertAlmostEqual(regiment.y - 100, regiment.speed_per_tick)

    def test_given_a_walk_back_re_form_when_every_figure_is_at_rest_then_it_ends_without_snapping_headings(self):
        regiment, battle = self._regiment()
        regiment.model_positions()
        regiment.positions = [(x - 30, y) for x, y in regiment.positions]
        battle.reform_to_ranks(regiment, 3, walk_back=True)

        for _ in range(200):
            battle.tick()
            if not regiment.reforming:
                break

        self.assertFalse(regiment.reforming)
        self.assertFalse(regiment.reform_walk_back)
        self.assertTrue(any(event.kind == "reform_complete" for event in battle.events))
        # The figures walked in from the -X side: their last heading still points roughly +X, not front (+Y).
        self.assertTrue(any(model.heading_x > 0.5 for model in regiment.melee_models))

    def test_given_a_walk_back_re_form_when_a_new_layout_is_given_then_walk_back_persists(self):
        regiment, battle = self._regiment()
        regiment.model_positions()
        regiment.positions = [(x - 30, y) for x, y in regiment.positions]
        battle.reform_to_ranks(regiment, 3, walk_back=True)

        battle.reform_to_ranks(regiment, 2)

        self.assertTrue(regiment.reform_walk_back)

    def test_given_a_finished_walk_back_re_form_when_re_formed_again_then_it_is_a_shuffle(self):
        regiment, battle = self._regiment()
        regiment.model_positions()
        battle.reform_to_ranks(regiment, 3, walk_back=True)
        for _ in range(100):
            battle.tick()

        battle.reform_to_ranks(regiment, 3)

        self.assertFalse(regiment.reform_walk_back)

    def test_given_a_re_forming_unit_when_it_engages_then_the_re_form_ends_without_a_complete_event(self):
        regiment, battle = self._regiment()
        regiment.model_positions()
        regiment.positions = [(x - 30, y) for x, y in regiment.positions]
        battle.reform_to_ranks(regiment, 3)

        Battle.end_reform_for_engagement(regiment)

        self.assertFalse(regiment.reforming)
        self.assertEqual(regiment.reform_slots, [])
        self.assertEqual(len(regiment.positions), regiment.models)
        self.assertFalse(any(event.kind == "reform_complete" for event in battle.events))


class OrdersDuringReformTests(unittest.TestCase):
    """notes/reform_while_moving.md 4: player Move, Face point, Charge and Attack orders given while the unit
    re-forms are held and applied once the re-form ends; a later order replaces a held one."""

    def setUp(self):
        self.regiment = Regiment("m", "M", 100, 100, 0, Side.PLAYER, models=10, ranks=2,
                                 speed_per_tick=20 * 1.8 / 16)
        self.enemy = Regiment("e", "E", 100, 700, 256, Side.ENEMY, models=10, ranks=2)
        self.battle = Battle(1000, 1000, [self.regiment, self.enemy], seed=1995)
        self.battle.phase = "battle"
        self.regiment.model_positions()
        self.regiment.positions = [(x - 30, y) for x, y in self.regiment.positions]
        self.battle.reform_to_ranks(self.regiment, 3, walk_back=True)

    def _settle(self):
        for _ in range(200):
            self.battle.tick()
            if not self.regiment.reforming:
                return
        self.fail("re-form never ended")

    def test_given_a_re_forming_unit_when_ordered_to_move_then_the_order_is_held_and_the_unit_stays(self):
        self.battle.order_move("m", 100, 500)
        self.battle.tick()

        self.assertEqual(self.regiment.pending_order, ("order_move", 100, 500))
        self.assertIsNone(self.regiment.target_x)
        self.assertEqual((self.regiment.x, self.regiment.y), (100, 100))

    def test_given_a_held_move_when_the_re_form_ends_then_the_move_starts(self):
        self.battle.order_move("m", 100, 500)
        self._settle()
        self.battle.tick()

        self.assertIsNone(self.regiment.pending_order)
        self.assertGreater(self.regiment.y, 100)

    def test_given_a_held_order_when_another_order_follows_then_it_is_replaced(self):
        self.battle.order_move("m", 100, 500)
        self.battle.order_attack("m", "e")

        self.assertEqual(self.regiment.pending_order, ("order_attack", "e"))

    def test_given_a_re_forming_unit_when_ordered_to_attack_then_it_waits_and_attacks_after_the_re_form(self):
        self.battle.order_attack("m", "e")
        self.battle.tick()
        self.assertIsNone(self.regiment.attack_target)
        self.assertEqual(self.regiment.y, 100)

        self._settle()
        self.battle.tick()

        self.assertEqual(self.regiment.attack_target, "e")

    def test_given_a_held_order_when_halted_then_it_is_dropped_and_the_re_form_restarts(self):
        self.battle.order_move("m", 100, 500)

        self.battle.order_halt("m")

        self.assertIsNone(self.regiment.pending_order)

    def test_given_a_held_face_point_when_the_re_form_ends_then_the_turn_starts(self):
        self.battle.order_face_point("m", 600, 100)
        self.assertEqual(self.regiment.pending_order, ("order_face_point", 600, 100))

        self._settle()
        self.battle.tick()

        self.assertIsNone(self.regiment.pending_order)
        self.assertIsNotNone(self.regiment.turn_order_key)

    def test_given_a_unit_not_re_forming_when_ordered_to_move_then_the_move_starts_at_once(self):
        self._settle()

        self.battle.order_move("m", 100, 500)

        self.assertIsNone(self.regiment.pending_order)
        self.assertIsNotNone(self.regiment.target_x)


class ReformFormationDifferenceTests(unittest.TestCase):
    """game_rules.md "Formation differences" and "A formation change costs no time of its own"."""

    def _wagon_battle(self):
        source = {"field": {"width": 1000, "height": 1000}, "merc": None,
                  "armies": [{"units": [{
                      "id": "wagon", "name": "Wagon", "set": {"x": 0, "y": 0},
                      "stats": {"s_side": [0, 2, 2, 2], "s_race": [7 * 8]},
                      "profile": {"M": 4, "I": 3},
                  }]}]}
        return Battle.from_script(source)

    def test_given_a_wagon_when_reform_is_ordered_then_it_keeps_the_catch_up_walk(self):
        battle = self._wagon_battle()
        wagon = battle.regiments["wagon"]
        wagon.model_positions()

        battle.order_reform("wagon", 2)

        self.assertFalse(wagon.reforming)
        self.assertEqual(wagon.reform_slots, [])

    def test_given_a_wagon_and_a_block_when_reforming_then_wagon_speeds_are_rank_dependent_and_the_blocks_uniform(self):
        battle = self._wagon_battle()
        wagon = battle.regiments["wagon"]
        wagon.model_positions()
        wagon.y = 100
        before = list(wagon.positions)
        battle._advance_models(wagon, 1)
        wagon_steps = [b[1] - a[1] for a, b in zip(before, wagon.positions)]
        self.assertNotAlmostEqual(wagon_steps[0], wagon_steps[1])

        block = Regiment("block", "Block", 0, 0, 0, Side.PLAYER, models=4, ranks=2,
                         speed_per_tick=speed_per_tick(4, 3))
        battle = Battle(1000, 1000, [block])
        block.model_positions()
        block.positions = [(-30.0, -50.0), (30.0, -50.0), (-30.0, -80.0), (30.0, -80.0)]
        block.reforming = True
        block.reform_slots = [(0.0, 100.0)] * 4
        before = list(block.positions)
        battle._advance_reforming_models(block, 1)
        steps = {round(math.hypot(b[0] - a[0], b[1] - a[1]), 6) for a, b in zip(before, block.positions)}
        self.assertEqual(len(steps), 1)

    def test_given_an_already_settled_shape_when_reform_is_ordered_then_it_completes_with_no_extra_delay(self):
        block = Regiment("block", "Block", 0, 0, 0, Side.PLAYER, models=8, ranks=2,
                         speed_per_tick=speed_per_tick(4, 3))
        battle = Battle(1000, 1000, [block])
        block.model_positions()
        battle.order_reform("block", 4)
        block.positions = formation.place(0, 0, 0, block.reform_slots)

        battle._advance_reforming_models(block, 1)

        self.assertFalse(block.reforming)

    def test_given_a_leader_index_when_reslotted_then_it_takes_the_front_rank_centre_directly(self):
        positions = [(float(i * 10), 500.0) for i in range(6)]  # all far from the slots

        slots = formation.reform_assignment(0, 0, 0, 6, 2, positions, leader_index=5)

        self.assertEqual(slots[5], formation.reform_slot_order(6, 2)[0])


class ChargeStretchWorkedExampleTests(unittest.TestCase):
    """game_rules.md "Models chase the unit, they are not carried by it": the full worked Empire
    infantry example (`s_rlmv` 11, 4 ranks) -- marching-speed parity, the charge stretch, a re-aiming
    charge's full-speed translation, and the post-charge concertina recovery."""

    def _block(self, x=0, y=0):
        return Regiment("block", "Block", x, y, 0, Side.PLAYER, models=20, ranks=4,
                        speed_per_tick=speed_per_tick(4, 3))

    @staticmethod
    def _rear_rank_lag(regiment, index=16):
        ideal = formation.place(regiment.x, regiment.y, regiment.direction,
                                formation.block_slots(regiment.models, regiment.ranks))
        px, py = regiment.positions[index]
        ix, iy = ideal[index]
        return math.hypot(px - ix, py - iy)

    def test_given_a_block_marching_freely_when_many_ticks_pass_then_the_rear_rank_holds_a_stable_gap(self):
        # "the rearmost rank's minimum step ... is identical" to the anchor's moving-freely speed: the
        # gap opened while ramping up to speed stops growing once both sides reach a steady march.
        block = self._block()
        battle = Battle(6000, 6000, [block])
        battle.order_move("block", 0, 5000)
        for _ in range(250):
            battle.tick()
        lag_early = self._rear_rank_lag(block)
        for _ in range(100):
            battle.tick()
        lag_late = self._rear_rank_lag(block)

        self.assertLessEqual(lag_late, lag_early + 1.0)

    def test_given_a_full_infantry_charge_when_it_completes_then_the_rear_rank_trails_by_about_40_units(self):
        # "the back rank ends up on the order of 40 world units ... behind" -- reproduced here with the
        # target placed at the documented charge distance (144 units, "about 84 ticks").
        block = self._block()
        # The target sits well beyond charge reach so the charge is still running -- not already
        # resolved into contact -- at the documented 84-tick mark.
        target = Regiment("target", "Target", 0, 5000, 0, Side.ENEMY, models=1, ranks=1)
        target.speed_per_tick = 0
        battle = Battle(6000, 6000, [block, target])
        battle.order_attack("block", "target")
        for _ in range(84):
            battle.tick()

        self.assertAlmostEqual(block.y, 144, delta=5)
        self.assertAlmostEqual(self._rear_rank_lag(block), 40, delta=15)

    def test_given_a_charge_that_must_reaim_when_ticked_then_the_anchor_keeps_full_charge_speed(self):
        # A charge keeps full anchor speed on every turning tick (unlike an ordinary wheel, which halves
        # it, or a halted turn, which stops it). A frontage-1 column removes the turn's own corner-pivot
        # shift, isolating the translation term.
        column = Regiment("column", "Column", 0, 0, 0, Side.PLAYER, models=4, ranks=4,
                          speed_per_tick=speed_per_tick(4, 3))
        angle = 60 * math.tau / 512  # > 32/512 turn: a charge always re-aims rather than snapping
        target = Regiment("target", "Target", 140 * math.sin(angle), 140 * math.cos(angle), 0,
                          Side.ENEMY, models=1, ranks=1)
        target.speed_per_tick = 0
        battle = Battle(4000, 4000, [column, target])
        battle.order_attack("column", "target")

        reaim_steps, settled_step = [], None
        for _ in range(15):
            before = (column.x, column.y)
            battle.tick()
            step = math.hypot(column.x - before[0], column.y - before[1])
            if column.turn_mode == "charge_reaim":
                reaim_steps.append(step)
            elif column.turn_mode is None and step > 0:
                settled_step = step

        self.assertTrue(reaim_steps)
        self.assertIsNotNone(settled_step)
        for step in reaim_steps:
            self.assertAlmostEqual(step, settled_step, places=6)

    def test_given_a_45_degree_turning_charge_then_the_rear_rank_is_more_stretched_than_a_straight_one(self):
        # "Turning during a charge makes the stretch worse": ~16 units more on a 5x4 block.
        lags = {}
        for turning in (False, True):
            bearing = math.radians(45 if turning else 0)
            block = self._block()
            target = Regiment("target", "Target", 5000 * math.sin(bearing), 5000 * math.cos(bearing), 0,
                              Side.ENEMY, models=1, ranks=1)
            target.speed_per_tick = 0
            battle = Battle(9000, 9000, [block, target])
            battle.order_attack("block", "target")
            for _ in range(84):
                battle.tick()
            lags[turning] = sum(self._rear_rank_lag(block, i) for i in range(15, 20)) / 5

        self.assertGreaterEqual(lags[True], lags[False])
        self.assertAlmostEqual(lags[True] - lags[False], 16, delta=10)

    def test_given_a_charging_block_when_it_halts_then_the_rear_rank_gap_recovers_in_about_three_seconds(self):
        # "the block visibly concertinas back together over roughly three seconds" once the anchor stops.
        block = self._block()
        target = Regiment("target", "Target", 0, 5000, 0, Side.ENEMY, models=1, ranks=1)
        target.speed_per_tick = 0
        battle = Battle(6000, 6000, [block, target])
        battle.order_attack("block", "target")
        for _ in range(84):
            battle.tick()
        lag_at_halt = self._rear_rank_lag(block)
        battle.order_halt("block")

        for _ in range(40):  # 4 s at 10 ticks/s -- "roughly three seconds", with headroom
            battle.tick()

        self.assertGreater(lag_at_halt, 20)
        self.assertLessEqual(self._rear_rank_lag(block), 3.5)  # MODEL_ARRIVAL_DISTANCE, plus headroom


class ChargeStartFreezeTests(unittest.TestCase):
    """game_rules.md "Models chase the unit": figures pause briefly when a charge starts."""

    def setUp(self):
        self.charger = Regiment("charger", "Charger", 0, 0, 0, Side.PLAYER,
                                models=8, ranks=2, speed_per_tick=speed_per_tick(4, 3))
        self.target = Regiment("target", "Target", 0, 130, 0, Side.ENEMY)
        self.battle = Battle(1000, 1000, [self.charger, self.target])

    def test_given_a_charge_in_reach_when_ticked_then_each_model_waits_its_staggered_delay(self):
        before = list(self.charger.model_positions())
        self.battle.order_attack("charger", "target")

        self.battle.tick()

        self.assertGreater(self.charger.y, 0)
        self.assertEqual(self.charger.positions, before)
        self.assertEqual([model.freeze_ticks for model in self.charger.melee_models], [(29 * n & 7) for n in range(8)])

        for _ in range(7):
            self.battle.tick()

        self.assertGreater(self.charger.positions[0][1], before[0][1])
        self.assertEqual(self.charger.positions[3], before[3])  # stagger & 7 == 7, the longest wait
        self.assertTrue(all(model.freeze_ticks == 0 for model in self.charger.melee_models))

        self.battle.tick()

        self.assertGreater(self.charger.positions[3][1], before[3][1])

    def test_given_an_attack_order_outside_charge_reach_then_freeze_starts_only_on_entering_reach(self):
        self.target.y = 200
        self.battle.order_attack("charger", "target")

        self.battle.tick()

        self.assertIsNone(self.charger.charge_started_target)
        self.assertTrue(all(model.freeze_ticks == 0 for model in self.charger.melee_models))

        for _ in range(40):
            self.battle.tick()
            if self.charger.charge_started_target == "target":
                break

        self.assertEqual(self.charger.charge_started_target, "target")
        self.assertTrue(any(model.freeze_ticks > 0 for model in self.charger.melee_models))

    def test_given_a_halted_charge_when_the_same_target_is_ordered_again_then_freeze_restarts(self):
        self.battle.order_attack("charger", "target")
        for _ in range(10):
            self.battle.tick()
        self.assertTrue(all(model.freeze_ticks == 0 for model in self.charger.melee_models))
        self.battle.order_halt("charger")
        self.battle.order_attack("charger", "target")

        self.battle.tick()

        self.assertEqual([model.freeze_ticks for model in self.charger.melee_models],
                         [(29 * n & 7) for n in range(8)])

    def test_given_a_charge_is_cancelled_then_its_pending_model_delays_are_cleared(self):
        self.battle.order_attack("charger", "target")
        self.battle.tick()
        self.battle.order_halt("charger")
        self.battle.order_move("charger", 0, 100)

        self.battle.tick()

        self.assertTrue(all(model.freeze_ticks == 0 for model in self.charger.melee_models))


class GradualTurningTests(unittest.TestCase):
    """game_rules.md "Turning, wheeling and reversing": facing changes over multiple ticks."""

    def _battle(self, ranks):
        regiment = Regiment("block", "Block", 100, 100, 0, Side.PLAYER,
                            models=20, ranks=ranks, speed_per_tick=speed_per_tick(4, 3))
        return Battle(1000, 1000, [regiment]), regiment

    def test_given_a_sixty_degree_order_when_ticked_then_the_block_halts_and_turns_gradually(self):
        battle, regiment = self._battle(4)
        half_frontage = (regiment.frontage - 1) * 6
        battle.order_move("block", 100 + 300 * math.sin(math.pi / 3),
                          100 + 300 * math.cos(math.pi / 3))

        battle.tick()

        self.assertEqual(regiment.turn_mode, "halted")
        self.assertAlmostEqual(regiment.direction, 11 * (144 - 7 * 7) / 256)
        angle = regiment.direction * math.tau / 512
        self.assertAlmostEqual(regiment.x + half_frontage * math.cos(angle), 100 + half_frontage)
        self.assertAlmostEqual(regiment.y - half_frontage * math.sin(angle), 100)

    def test_given_a_thirty_degree_order_when_ticked_then_the_block_wheels_at_half_speed(self):
        battle, regiment = self._battle(4)
        half_frontage = (regiment.frontage - 1) * 6
        battle.order_move("block", 100 + 300 * math.sin(math.pi / 6),
                          100 + 300 * math.cos(math.pi / 6))

        battle.tick()

        self.assertEqual(regiment.turn_mode, "wheel")
        self.assertAlmostEqual(regiment.direction, 11 * (144 - 7 * 7) / 512)
        angle = regiment.direction * math.tau / 512
        pivot_x = regiment.x + half_frontage * math.cos(angle)
        pivot_y = regiment.y - half_frontage * math.sin(angle)
        self.assertAlmostEqual(math.hypot(pivot_x - (100 + half_frontage), pivot_y - 100),
                               regiment.speed_per_tick / 2)

    def test_given_the_same_models_in_wide_and_deep_blocks_then_the_wide_block_turns_slower(self):
        deep_battle, deep = self._battle(4)
        wide_battle, wide = self._battle(2)
        target = (100 + 300 * math.sin(math.pi / 3), 100 + 300 * math.cos(math.pi / 3))
        deep_battle.order_move("block", *target)
        wide_battle.order_move("block", *target)

        deep_battle.tick()
        wide_battle.tick()

        self.assertAlmostEqual(deep.direction, 11 * 95 / 256)
        self.assertAlmostEqual(wide.direction, 11 * 23 / 256)

    def test_given_a_new_eastward_order_then_the_ninety_degree_snap_happens_only_once(self):
        battle, regiment = self._battle(4)
        battle.order_move("block", 500, 100)

        battle.tick()
        first_direction = regiment.direction
        battle.tick()

        self.assertEqual(first_direction, 128)
        self.assertLessEqual(abs(Battle._turn_delta(regiment.direction, first_direction)), 10)
        self.assertEqual((regiment.ranks, regiment.frontage), (5, 4))

    def test_given_a_charging_target_changes_bearing_then_the_charge_reaims_at_the_next_segment(self):
        charger = Regiment("charger", "Charger", 100, 100, 0, Side.PLAYER,
                           models=20, ranks=4, speed_per_tick=speed_per_tick(4, 3))
        target = Regiment("target", "Target", 100, 400, 0, Side.ENEMY)
        battle = Battle(1000, 1000, [charger, target])
        battle.order_attack("charger", "target")
        battle.tick()
        self.assertEqual(charger.direction, 0)
        target.x = 300

        for _ in range(18):
            battle.tick()

        self.assertEqual(charger.direction, 0)
        battle.tick()  # tick 19 begins a new segment

        self.assertEqual(charger.turn_mode, "charge_reaim")
        self.assertGreater(charger.direction, 0)


def formation_positions(regiment):
    from whshr import formation
    return formation.place(regiment.x, regiment.y, regiment.direction,
                           formation.block_slots(regiment.models, regiment.ranks))


class SeededPositionsTests(unittest.TestCase):
    """Display and logging read figure positions without seeding them: seeding draws from the battle-wide stagger
    sequence, so a reader that seeds would make live play and replay differ."""

    def test_given_an_unseeded_regiment_when_read_for_display_then_it_stays_unseeded(self):
        regiment = Regiment("r", "R", 100, 100, 0, Side.PLAYER, models=6, ranks=2)
        Battle(1000, 1000, [regiment])

        self.assertEqual(regiment.seeded_positions(), [])
        self.assertEqual(regiment.melee_models, [])

    def test_given_a_seeded_regiment_when_read_for_display_then_its_positions_are_returned(self):
        regiment = Regiment("r", "R", 100, 100, 0, Side.PLAYER, models=6, ranks=2)
        Battle(1000, 1000, [regiment])
        regiment.model_positions()

        self.assertEqual(regiment.seeded_positions(), regiment.positions)


class OrdinaryMovePlanTests(unittest.TestCase):
    """notes/movement_formation.md 1.4: an ordinary move re-plans at intervals, turns a large angle by halves, and
    halts within 32 units of its point; a multi-leg route visits every leg (GitHub #183)."""

    def _move(self, bearing, distance, models=11, ranks=3):
        regiment = Regiment("w", "W", 500, 500, 0, Side.PLAYER, models=models, ranks=ranks, speed_per_tick=2.0)
        battle = Battle(1000, 1000, [regiment], seed=1)
        battle.phase = "battle"
        point = (500 + distance * math.sin(math.radians(bearing)), 500 + distance * math.cos(math.radians(bearing)))
        battle.order_move("w", *point)
        for _ in range(400):
            if not regiment.moving:
                break
            battle.tick()
        return regiment, point

    def test_given_a_close_off_axis_destination_when_moving_then_the_unit_stops_within_32_units(self):
        for bearing, distance in ((90, 80), (135, 80), (170, 80), (60, 40), (90, 25)):
            with self.subTest(bearing=bearing, distance=distance):
                regiment, point = self._move(bearing, distance)
                self.assertFalse(regiment.moving)
                self.assertLessEqual(math.dist((regiment.x, regiment.y), point), 32)

    def test_given_a_long_straight_move_when_it_ends_then_it_halts_short_of_the_point_and_re_forms(self):
        regiment, point = self._move(0, 300)

        self.assertFalse(regiment.moving)
        self.assertLess(regiment.y, point[1])
        self.assertLessEqual(point[1] - regiment.y, 32)
        self.assertTrue(regiment.reforming)

    def test_given_a_large_turn_when_planned_then_the_halted_turn_owes_half_the_angle(self):
        regiment = Regiment("w", "W", 500, 500, 0, Side.PLAYER, models=11, ranks=3, speed_per_tick=2.0)
        battle = Battle(1000, 1000, [regiment], seed=1)
        battle.phase = "battle"
        regiment.target_x, regiment.target_y = 800.0, 500.0  # 128/512 to the right, far away, no snap (not issued)
        regiment.turn_order_key = ("move", 0, 0)

        battle._advance_move(regiment, (800.0, 500.0), regiment.speed_per_tick, ("move", 800.0, 500.0), 1.0)

        self.assertEqual(regiment.turn_mode, "halted")
        assert regiment.turn_goal is not None
        self.assertAlmostEqual(regiment.turn_goal, 64, delta=9)

    def _planner(self, waypoint):
        regiment = Regiment("w", "W", 0, 0, 0, Side.PLAYER, models=11, ranks=3, speed_per_tick=18 * 1.8 / 16)
        battle = Battle(1000, 1000, [regiment], seed=1)
        battle.phase = "battle"
        regiment.target_x, regiment.target_y = waypoint
        regiment.turn_order_key = ("move", 0, 0)  # under way already: no start snap
        return regiment, battle

    def test_given_a_waypoint_within_32_units_and_a_small_turn_when_planned_then_the_move_halts(self):
        # notes/close_point_move.md 5: P (0,0), facing 0, waypoint (5, 30): turn <= 64, d <= 32 -> halt and re-form.
        regiment, battle = self._planner((5.0, 30.0))

        battle._advance_move(regiment, (5.0, 30.0), regiment.speed_per_tick, ("move", 5.0, 30.0), 1.0)

        self.assertFalse(regiment.moving)
        self.assertTrue(regiment.reforming)

    def test_given_a_far_waypoint_with_a_moderate_turn_when_planned_then_it_wheels_and_sets_the_countdown(self):
        # notes/close_point_move.md 5: waypoint (20, 40): d 44, turn 38 -> keep moving, wheel owing 38, countdown 88.
        regiment, battle = self._planner((20.0, 40.0))

        battle._advance_move(regiment, (20.0, 40.0), regiment.speed_per_tick, ("move", 20.0, 40.0), 1.0)

        self.assertTrue(regiment.moving)
        self.assertEqual(regiment.turn_mode, "wheel")
        self.assertAlmostEqual(regiment.move_plan_countdown, 2 * math.hypot(20, 40) - 18, places=4)

    def test_given_a_re_forming_unit_owing_a_halted_turn_when_updated_then_nothing_happens(self):
        regiment, battle = self._planner((300.0, 0.0))
        regiment.reforming = True
        regiment.move_plan_countdown = 50.0
        Battle._owe_turn(regiment, 40, "halted", 8)
        before = (regiment.x, regiment.y, regiment.direction)

        battle._advance_move(regiment, (300.0, 0.0), regiment.speed_per_tick, ("move", 0, 0), 1.0)

        self.assertEqual((regiment.x, regiment.y, regiment.direction), before)
        self.assertEqual(regiment.move_plan_countdown, 50.0)

    def test_given_a_point_inside_the_pivot_circle_when_ordered_then_the_unit_halts_instead_of_spinning(self):
        # PROVISIONAL deviation (notes/close_point_move.md 3, 6): the original's rules spin forever here.
        for bearing, distance in ((60, 10), (60, 18), (90, 20), (150, 32), (150, 40)):
            with self.subTest(bearing=bearing, distance=distance):
                regiment, point = self._move(bearing, distance)
                self.assertFalse(regiment.moving)

    def test_given_a_three_point_route_when_followed_then_the_middle_point_is_visited(self):
        regiment = Regiment("w", "W", 100, 100, 0, Side.PLAYER, models=1, ranks=1, speed_per_tick=3.0)
        battle = Battle(1000, 1000, [regiment], seed=1)
        battle.phase = "battle"
        regiment.target_x, regiment.target_y = 100.0, 200.0
        regiment.waypoints = [(200.0, 200.0), (200.0, 300.0)]
        visited = []
        for _ in range(400):
            battle.tick()
            current = (regiment.target_x, regiment.target_y)
            if regiment.moving and (not visited or visited[-1] != current):
                visited.append(current)

        self.assertEqual(visited, [(100.0, 200.0), (200.0, 200.0), (200.0, 300.0)])


class FormationTurnExceptionTests(unittest.TestCase):
    """game_rules.md "Turning, wheeling and reversing": per-formation-type exceptions (#65)."""

    def _battle(self, **kwargs):
        regiment = Regiment("r", "R", 100, 100, 0, Side.PLAYER,
                            speed_per_tick=speed_per_tick(4, 3), **kwargs)
        return Battle(1000, 1000, [regiment]), regiment

    def test_given_a_single_model_when_ordered_east_then_it_turns_without_snap_pivot_or_speed_penalty(self):
        battle, regiment = self._battle(models=1, ranks=1)
        battle.order_move("r", 500, 100)

        battle.tick()

        s_rlmv = regiment.speed_per_tick * 16 / 1.8
        self.assertAlmostEqual(regiment.direction, s_rlmv * (144 - 1.5 ** 2) / 256)
        self.assertAlmostEqual(math.hypot(regiment.x - 100, regiment.y - 100), regiment.speed_per_tick)

    def test_given_a_reforming_block_when_ordered_east_then_it_neither_snaps_nor_turns_nor_moves(self):
        # notes/reform_while_moving.md 10: re-forming, owing a halted turn -> no turn, no translation.
        battle, regiment = self._battle(models=20, ranks=4)
        regiment.reforming = True

        battle._advance_toward(regiment, (500, 100), regiment.speed_per_tick, True, ("move", 500, 100), 1.0)

        self.assertEqual(regiment.direction, 0)
        self.assertEqual((regiment.x, regiment.y), (100, 100))

    def test_given_a_reforming_block_owing_a_wheel_when_moving_then_it_keeps_its_facing_and_translates(self):
        # notes/reform_while_moving.md 10: re-forming, needs a 30 degree wheel -> no turn; translates along its facing.
        battle, regiment = self._battle(models=20, ranks=4)
        regiment.reforming = True
        target = (100 + 400 * math.sin(math.radians(30)), 100 + 400 * math.cos(math.radians(30)))

        battle._advance_toward(regiment, target, regiment.speed_per_tick, True, ("move", *target), 1.0)

        self.assertEqual(regiment.direction, 0)
        self.assertAlmostEqual(regiment.x, 100)
        self.assertAlmostEqual(regiment.y, 100 + regiment.speed_per_tick)

    def test_given_a_reforming_pursuer_when_it_turns_then_its_anchor_is_not_pivot_shifted(self):
        battle, regiment = self._battle(models=20, ranks=4)
        regiment.reforming = regiment.pursuing = True
        regiment.turn_mode, regiment.turn_shift, regiment.turn_sign, regiment.turn_remaining = "wheel", 7, 1, 60

        Battle._step_turn(regiment, 1.0)

        self.assertGreater(regiment.direction, 0)
        self.assertEqual((regiment.x, regiment.y), (100, 100))

    def test_given_a_running_move_when_its_destination_is_re_aimed_behind_then_it_does_not_snap(self):
        # game_rules.md "Real time and movement": the snap happens only when a move order is issued. A script
        # re-aim (IfTargetInChargeReach moves the destination) under a running move only re-plans the turn.
        battle, regiment = self._battle(models=12, ranks=3)
        battle.order_move("r", 100, 600)
        battle.tick()
        self.assertEqual(regiment.direction, 0)

        regiment.target_x, regiment.target_y = 100.0, -400.0  # now straight behind
        battle.tick()

        self.assertNotEqual(regiment.direction, 256)
        self.assertEqual(regiment.turn_mode, "halted")

    def test_given_a_new_move_order_behind_when_issued_then_it_snaps_180(self):
        battle, regiment = self._battle(models=12, ranks=3)
        battle.order_move("r", 100, 600)
        battle.tick()

        battle.order_move("r", 100, 10)
        battle.tick()

        self.assertEqual(regiment.direction, 256)

    def test_given_a_wagon_when_the_camera_moves_then_facing_snaps_to_the_camera_relative_grid(self):
        battle, regiment = self._battle(models=2, ranks=1)
        regiment.unit_class = 7
        regiment.direction = 40

        battle.set_view_angle(10)

        self.assertEqual(regiment.direction, 10)
        battle.set_view_angle(30)
        self.assertEqual(regiment.direction, 30)

    def test_given_an_unchanged_view_angle_then_the_wagon_is_not_re_snapped(self):
        battle, regiment = self._battle(models=2, ranks=1)
        regiment.unit_class = 7
        battle.set_view_angle(10)
        regiment.direction = 40

        battle.set_view_angle(10)

        self.assertEqual(regiment.direction, 40)

    def test_given_a_non_wagon_when_the_camera_moves_then_its_facing_is_untouched(self):
        battle, regiment = self._battle(models=20, ranks=4)
        regiment.direction = 40
        battle.set_view_angle(10)
        self.assertEqual(regiment.direction, 40)

    def test_given_an_artillery_unit_then_it_is_anchored_by_rule_and_others_are_not(self):
        battle, gun = self._battle(models=5, ranks=3)
        self.assertFalse(gun.anchored)
        gun.hud_class = "art"
        self.assertTrue(gun.anchored)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.player = Regiment("player", "Player", 100, 100, 0, Side.PLAYER, models=18, ranks=4)
        self.enemy = Regiment("enemy", "Enemy", 300, 300, 0, Side.ENEMY, models=18, ranks=4)
        self.battle = Battle(1000, 1000, [self.player, self.enemy])

    def test_given_a_point_inside_a_player_regiment_when_picked_then_its_identifier_is_returned(self):
        self.assertEqual(self.battle.regiment_at(100, 100), "player")

    def test_given_a_point_inside_an_enemy_regiment_when_picked_then_it_is_not_selectable(self):
        self.assertIsNone(self.battle.regiment_at(300, 300))

    def test_given_an_empty_point_when_picked_then_nothing_is_returned(self):
        self.assertIsNone(self.battle.regiment_at(500, 500))


class CollisionTests(unittest.TestCase):
    """Simple, deterministic collisions: regiments do not end up walking through each other."""

    def test_given_two_regiments_ordered_into_each_other_when_ticked_then_their_footprints_stop_overlapping(self):
        left = Regiment("left", "Left", 0, 0, 0, Side.PLAYER, models=18, ranks=4, speed_per_tick=5.0)
        right = Regiment("right", "Right", 200, 0, 0, Side.PLAYER, models=18, ranks=4, speed_per_tick=5.0)
        battle = Battle(1000, 1000, [left, right])
        battle.order_move("left", 300, 0)
        battle.order_move("right", 0, 0)

        for _ in range(80):
            battle.tick()

        distance = math.hypot(right.x - left.x, right.y - left.y)
        self.assertGreaterEqual(distance, left.bounding_radius() + right.bounding_radius() - 1e-6)

    def test_given_regiments_deployed_overlapping_when_no_orders_are_given_then_neither_is_pushed(self):
        # BF001 deploys the Grudgebringer cavalry and infantry closer than their bounding circles.
        cavalry = Regiment("cavalry", "Cavalry", 1090, 639, 0, Side.PLAYER, models=12, ranks=3)
        infantry = Regiment("infantry", "Infantry", 1112, 585, 0, Side.PLAYER, models=16, ranks=4)
        battle = Battle(1600, 1760, [cavalry, infantry])

        for _ in range(10):
            battle.tick()

        self.assertEqual((cavalry.x, cavalry.y, infantry.x, infantry.y), (1090, 639, 1112, 585))
        self.assertFalse(cavalry.walking or infantry.walking)

    def test_given_regiment_ordered_into_a_standing_friend_when_ticked_then_both_give_way_and_end_clear(self):
        standing = Regiment("standing", "Standing", 200, 0, 0, Side.PLAYER, models=18, ranks=4, speed_per_tick=5.0)
        walker = Regiment("walker", "Walker", 0, 0, 0, Side.PLAYER, models=18, ranks=4, speed_per_tick=5.0)
        battle = Battle(1000, 1000, [standing, walker])
        battle.order_move("walker", 400, 0)

        for _ in range(80):
            battle.tick()

        self.assertNotEqual((standing.x, standing.y), (200, 0))  # pushed apart by half the overlap each
        distance = math.hypot(standing.x - walker.x, standing.y - walker.y)
        self.assertGreaterEqual(distance, standing.bounding_radius() + walker.bounding_radius() - 1e-6)


class AttackOrderTests(unittest.TestCase):
    def setUp(self):
        self.player = Regiment("player", "Player", 0, 0, 0, Side.PLAYER, models=10, ranks=2, speed_per_tick=5.0)
        self.enemy = Regiment("enemy", "Enemy", 300, 0, 0, Side.ENEMY, models=10, ranks=2, speed_per_tick=5.0)
        self.battle = Battle(1000, 1000, [self.player, self.enemy])

    def test_given_a_player_regiment_when_ordered_to_attack_an_enemy_then_it_charges_toward_it(self):
        self.battle.order_attack("player", "enemy")
        self.battle.tick()

        self.assertEqual(self.player.attack_target, "enemy")
        self.assertGreater(self.player.x, 0)  # moved toward the enemy
        self.assertIsNone(self.player.target_x)  # not an ordinary move order

    def test_given_an_attack_order_against_a_player_regiment_then_it_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not.*a player regiment"):
            self.battle.order_attack("player", "player")

    def test_given_a_non_player_regiment_when_ordered_to_attack_then_it_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not player-controlled"):
            self.battle.order_attack("enemy", "player")

    def test_given_two_regiments_charging_each_other_when_they_touch_then_they_enter_melee(self):
        self.battle.order_attack("player", "enemy")
        self.enemy.attack_target = "player"  # enemy is not player-controlled: drive it directly for the test

        for _ in range(80):
            self.battle.tick()
            if self.player.in_melee:
                break

        self.assertTrue(self.player.in_melee)
        self.assertTrue(self.enemy.in_melee)
        self.assertFalse(self.player.moving)


class BattleOutcomeTests(unittest.TestCase):
    """A full, deterministic battle resolves to a win or lose condition and stops simulating."""

    def test_given_an_overwhelming_player_force_when_battle_runs_then_it_ends_in_victory(self):
        player = Regiment("player", "Player", 0, 0, 0, Side.PLAYER, models=40, ranks=4, speed_per_tick=6.0,
                          ws=6, strength=6, attacks=3, leadership=9)
        enemy = Regiment("enemy", "Enemy", 60, 0, 0, Side.ENEMY, models=5, ranks=1, speed_per_tick=6.0,
                         ws=1, toughness=1, leadership=2)
        battle = Battle(1000, 1000, [player, enemy], seed=7)
        battle.order_attack("player", "enemy")

        for _ in range(500):
            battle.tick()
            if battle.result is not None:
                break

        self.assertEqual(battle.result, "victory")
        self.assertLess(battle.tick_count, 500)
        # the battle stops simulating once resolved: later ticks are no-ops
        ticks_at_result = battle.tick_count
        battle.tick()
        self.assertEqual(battle.tick_count, ticks_at_result + 1)
        self.assertEqual(battle.events, [])

    def test_given_an_overwhelming_enemy_force_when_battle_runs_then_it_ends_in_defeat(self):
        player = Regiment("player", "Player", 0, 0, 0, Side.PLAYER, models=5, ranks=1, speed_per_tick=6.0,
                          ws=1, toughness=1, leadership=2)
        enemy = Regiment("enemy", "Enemy", 60, 0, 0, Side.ENEMY, models=40, ranks=4, speed_per_tick=6.0,
                         ws=6, strength=6, attacks=3, leadership=9)
        battle = Battle(1000, 1000, [player, enemy], seed=11)
        enemy.attack_target = "player"

        for _ in range(500):
            battle.tick()
            if battle.result is not None:
                break

        self.assertEqual(battle.result, "defeat")

    def test_given_a_no_battle_skip_when_resolved_then_it_is_an_immediate_lossless_victory(self):
        player = Regiment("player", "Player", 0, 0, 0, Side.PLAYER, models=20, ranks=2)
        enemy = Regiment("enemy", "Enemy", 60, 0, 0, Side.ENEMY, models=30, ranks=3)
        neutral = Regiment("neutral", "Neutral", 30, 0, 0, Side.NEUTRAL, models=10, ranks=1)
        battle = Battle(1000, 1000, [player, enemy, neutral], seed=1)

        battle.resolve_no_battle()

        self.assertEqual(battle.result, "victory")
        self.assertEqual(player.models, 20)  # no losses
        self.assertEqual(enemy.models, 0)  # every enemy destroyed
        self.assertEqual(neutral.models, 10)  # neutral regiments are untouched


if __name__ == "__main__":
    unittest.main()


class ModelStaggerValueTests(unittest.TestCase):
    def _battle(self, *sizes):
        regiments = [Regiment(f"r{i}", f"R{i}", 100.0 + 400 * i, 100.0, 0, Side.PLAYER, models=n, ranks=4)
                     for i, n in enumerate(sizes)]
        return Battle(4000, 4000, regiments), regiments

    def test_given_two_regiments_when_models_created_then_stagger_follows_battle_wide_creation_order(self):
        battle, (first, second) = self._battle(10, 7)
        first.model_positions()
        second.model_positions()
        self.assertEqual([m.stagger for m in first.melee_models], [29 * n % 65536 for n in range(10)])
        self.assertEqual([m.stagger for m in second.melee_models], [29 * n % 65536 for n in range(10, 17)])

    def test_given_a_large_battle_when_models_created_then_full_16_bit_values_are_kept(self):
        battle, (big,) = self._battle(3000)
        big.model_positions()
        values = [m.stagger for m in big.melee_models]
        self.assertEqual(values, [29 * n % 65536 for n in range(3000)])
        self.assertGreater(max(values), 7)

    def test_given_large_sample_when_split_then_thirds_and_bit_masks_are_balanced(self):
        battle, (big,) = self._battle(6000)
        big.model_positions()
        values = [m.stagger for m in big.melee_models]
        for modulus, mask in ((3, None), (None, 3), (None, 7)):
            if modulus:
                buckets = [v % modulus for v in values]
                groups = modulus
            else:
                buckets = [v & mask for v in values]
                groups = mask + 1
            for group in range(groups):
                share = buckets.count(group) / len(values)
                self.assertAlmostEqual(share, 1 / groups, delta=0.03)

    def test_given_standalone_regiment_when_models_created_then_stagger_is_still_the_lcg_sequence(self):
        regiment = Regiment("solo", "Solo", 100.0, 100.0, 0, Side.PLAYER, models=5, ranks=1)
        regiment.model_positions()
        self.assertEqual([m.stagger for m in regiment.melee_models], [0, 29, 58, 87, 116])


class NodeTableTests(unittest.TestCase):
    """Scripts address [NODES] entries by position (from 0); the `id` field is mostly 0 and not a key."""

    def test_nodes_are_keyed_by_position_even_when_every_id_is_zero(self):
        source = {
            "field": {"width": 500, "height": 500},
            "armies": [], "merc": None,
            "nodes": [{"x": 10, "y": 20, "id": 0}, {"x": 30, "y": 40, "id": 0}, {"x": 50, "y": 60, "id": 2}],
        }
        battle = Battle.from_script(source)
        self.assertEqual(battle.nodes, {0: (10.0, 20.0), 1: (30.0, 40.0), 2: (50.0, 60.0)})
