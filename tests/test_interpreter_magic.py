"""Magic opcodes: spell choice, pending spell, casting, power pools (notes/script_magic.md).

Vectors are the report's section 6: wizard W in the enemy army at (0, 0) facing +Y, threat range 240.
"""

import random
import unittest

from tests.script_helpers import word
from whshr import interpreter, magic
from whshr.engine import Battle, Regiment
from whshr.nodes import ScriptNode
from whshr.rules import Side

SKAVEN = ("GeneralDispel", "SkavenWarpLightning", "SkavenMadness", "SkavenPestilentBreath", "SkavenSkitterleap")
ORC = ("GeneralDispel", "WaaaghDaKrunch", "WaaaghGazeOfMork", "WaaaghEreWeGo", "WaaaghMorkSaveUz")


def regiment(identifier, x, y, side=Side.PLAYER, **extra):
    return Regiment(identifier, identifier, x, y, 0, side, models=5, ranks=1, **extra)


class MagicTestCase(unittest.TestCase):
    def make(self, *others, spells=SKAVEN, enemy_power=2, player_power=4, nodes=None):
        self.w = regiment("W", 0, 0, Side.ENEMY, unit_class=interpreter.WIZARD_CLASS,
                          spells=magic.spell_codes(spells))
        self.battle = Battle(5000, 5000, [self.w, *others], seed=1995, script_nodes=nodes)
        self.bus = self.battle.event_bus
        self.bus._power = magic.PowerPools(player_power, enemy_power)
        self.interp = interpreter.ScriptInterpreter(self.battle, self.bus, None)
        self.state = self.bus.unit_states["W"]
        self.state.threat_range = 240

    def call(self, name, operand=None):
        self.state.pc = 0
        return getattr(self.interp, "op_" + name)(self.state, operand, [word(name), operand or 0], "W", 0,
                                                  random.Random(1))

    def target(self):
        return self.state.current_target[0] if self.state.current_target else None

    def result(self):
        return self.target(), self.state.pending_spell, self.bus.power.enemy, bool(self.state.cond_flags)


class SpellTableTests(unittest.TestCase):
    def test_spell_list_keeps_file_order_and_skips_casting_mode_markers(self):
        self.assertEqual(magic.spell_codes(["SkavenMadness", "CastOnce", "SkavenWarpLightning"]), (25, 22))

    def test_pools_are_clamped(self):
        pools = magic.PowerPools(7, 9)
        pools.add(False, 4)
        pools.add(True, -20)
        self.assertEqual((pools.player, pools.enemy), (8, 0))

    def test_marker_bit_spell_has_unlimited_range_but_the_base_cost(self):
        self.assertEqual((magic.cost(535), magic.spell_range(535, random.Random(1))), (1, None))


class ChooseEnemyTests(MagicTestCase):
    def test_list_order_picks_warp_lightning_and_pays(self):
        self.make(regiment("H", 0, 400))
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual(self.result(), ("H", 22, 0, True))

    def test_nothing_acceptable_clears_target_and_pays_nothing(self):
        self.make(regiment("H", 300, 300))
        self.state.current_target = ("H", 0)
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual(self.result(), (None, None, 2, False))

    def test_list_order_beats_skitterleap(self):
        self.make(regiment("H", 0, 200))
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual(self.state.pending_spell, 22)

    def test_skitterleap_jumps_away_from_the_target(self):
        self.make(regiment("H", 0, 200), enemy_power=1)
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual(self.result(), ("H", 23, 0, True))
        self.assertEqual((self.state.target_point, self.state.aim_at_point), ((0.0, -216.0), True))

    def test_skitterleap_range_is_strict(self):
        self.make(regiment("H", 0, 240), enemy_power=1)
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual(self.result(), (None, None, 1, False))

    def test_area_spells_are_never_chosen_and_gaze_is(self):
        self.make(regiment("H", 0, 300), regiment("F", 10, 310, Side.ENEMY), spells=ORC, enemy_power=3)
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual(self.result(), ("H", 17, 1, True))

    def test_ere_we_go_needs_a_friend_next_to_the_target(self):
        self.make(regiment("H", 200, 200), regiment("F", 10, 310, Side.ENEMY), spells=ORC, enemy_power=3)
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual(self.result(), (None, None, 3, False))
        self.make(regiment("H", 200, 200), regiment("F", 210, 210, Side.ENEMY), spells=ORC, enemy_power=3)
        self.call("ChooseEnemyAndSpellPay")
        self.assertEqual((self.state.pending_spell, self.state.target_point, self.state.aim_at_point),
                         (18, (210, 210), True))

    def test_of_class_takes_only_that_class(self):
        self.make(regiment("I", 0, 100, unit_class=1), regiment("A", 0, 300, unit_class=3))
        self.call("ChooseEnemyOfClassAndSpellPay", 24)
        self.assertEqual(self.target(), "A")

    def test_no_pay_form_still_needs_the_cost(self):
        self.make(regiment("H", 0, 400))
        self.call("ChooseEnemyAndSpell")
        self.assertEqual(self.result(), ("H", 22, 2, True))


class ChooseForTargetTests(MagicTestCase):
    def test_nothing_affordable_keeps_the_target(self):
        self.make(regiment("H", 0, 400), enemy_power=0)
        self.state.current_target = ("H", 0)
        self.call("ChooseSpellForTargetPay")
        self.assertEqual(self.result(), ("H", None, 0, False))

    def test_without_target_fails(self):
        self.make(regiment("H", 0, 400))
        self.call("ChooseSpellForTarget")
        self.assertEqual(self.result(), (None, None, 2, False))


class PendingAndCastTests(MagicTestCase):
    def test_set_spell_if_affordable(self):
        self.make(enemy_power=5)
        self.call("SetSpellIfAffordable", 535)
        self.assertEqual((self.state.pending_spell, bool(self.state.cond_flags), self.bus.power.enemy),
                         (535, True, 5))
        self.make(enemy_power=0)
        self.state.pending_spell = 22
        self.call("SetSpellIfAffordable", 535)
        self.assertEqual((self.state.pending_spell, bool(self.state.cond_flags)), (22, False))

    def test_set_cast_point_node(self):
        self.make(regiment("H", 0, 400), nodes=[ScriptNode(1.0, 2.0)] * 35 + [ScriptNode(700.0, 800.0)])
        self.state.current_target = ("H", 0)
        self.state.cond_flags = 1
        self.call("SetCastPointNode", 35)
        self.assertEqual((self.target(), self.state.target_point, bool(self.state.cond_flags)),
                         (None, (700.0, 800.0), True))

    def test_power_opcodes(self):
        self.make(enemy_power=7)
        self.call("AddEnemyPower", 4)
        self.assertEqual(self.bus.power.enemy, 8)
        self.make(enemy_power=2)
        self.call("IfEnemyPower", 2)
        self.assertTrue(self.state.cond_flags)
        self.call("IfEnemyPower", 3)
        self.assertFalse(self.state.cond_flags)

    def test_cast_pending_launches_at_the_target_and_clears(self):
        self.make(regiment("H", 0, 400))
        self.state.current_target, self.state.pending_spell = ("H", 0), 22
        self.call("CastPending")
        self.assertEqual((bool(self.state.cond_flags), self.state.pending_spell, self.state.aim_at_point),
                         (True, None, False))
        self.assertEqual([(event.data["spell"], event.data["y"]) for event in self.battle.events
                          if event.kind == "spell"], [(22, 400)])

    def test_cast_out_of_range_fails_without_refund(self):
        self.make(regiment("H", 0, 700), enemy_power=0)
        self.state.current_target, self.state.pending_spell = ("H", 0), 22
        self.call("CastPending")
        self.assertEqual((bool(self.state.cond_flags), self.state.pending_spell, self.bus.power.enemy),
                         (False, None, 0))
        self.assertEqual([event for event in self.battle.events if event.kind == "message"], [])  # enemy caster

    def test_cast_without_pending_spell_changes_nothing(self):
        self.make(regiment("H", 0, 400))
        self.state.current_target, self.state.aim_at_point = ("H", 0), True
        self.call("CastPending")
        self.assertEqual((bool(self.state.cond_flags), self.target(), self.state.aim_at_point), (False, "H", True))

    def test_aim_at_point_wins_over_the_target(self):
        self.make(regiment("H", 0, 400))
        self.state.current_target, self.state.pending_spell = ("H", 0), 16
        self.state.target_point, self.state.aim_at_point = (0.0, 0.0), True
        self.call("CastPending")
        self.assertEqual([(event.data["x"], event.data["y"]) for event in self.battle.events
                          if event.kind == "spell"], [(0.0, 0.0)])

    def test_cast_only_target_state_drops_the_target(self):
        self.make(regiment("H", 0, 400))
        self.state.current_target, self.state.pending_spell = ("H", 0), 22
        self.state.unit_flags |= interpreter.CAST_ONLY_TARGET_FLAG
        self.call("CastPending")
        self.assertIsNone(self.target())

    def test_drop_pending_spell(self):
        self.make(regiment("H", 0, 400))
        self.state.current_target, self.state.pending_spell, self.state.cond_flags = ("H", 0), 13, 1
        self.call("DropPendingSpell")
        self.assertEqual((self.state.pending_spell, self.target(), bool(self.state.cond_flags)), (None, "H", True))


class QueryTests(MagicTestCase):
    def test_pending_reaches_broken_target(self):
        self.make(regiment("H", 0, 600, routing=True))
        self.state.current_target, self.state.pending_spell = ("H", 0), 22
        self.call("PendingReachesBrokenTarget")
        self.assertFalse(self.state.cond_flags)
        self.battle.regiments["H"].routing = False
        self.call("PendingReachesBrokenTarget")
        self.assertTrue(self.state.cond_flags)
        self.state.current_target = None
        self.call("PendingReachesBrokenTarget")
        self.assertFalse(self.state.cond_flags)

    def test_cast_arc_is_not_skipped_in_melee_but_pending_arc_is(self):
        import math
        for bearing, cast_arc in ((70, True), (71, False)):
            with self.subTest(bearing=bearing):
                angle = (bearing + 0.5) * math.tau / 512
                self.make(regiment("H", 300 * math.sin(angle), 300 * math.cos(angle)))
                self.w.in_melee = True
                self.state.current_target, self.state.pending_spell = ("H", 0), 22
                self.call("TargetInCastArc", 0)
                self.assertEqual(bool(self.state.cond_flags), cast_arc)
                self.call("PendingInRangeArc", 0)
                self.assertTrue(self.state.cond_flags)

    def test_pending_in_range_vectors(self):
        self.make(regiment("H", 0, 600))
        self.state.current_target, self.state.pending_spell = ("H", 0), 5
        self.call("PendingInRange", 1)
        self.assertFalse(self.state.cond_flags)
        self.assertEqual([event.data["text_id"] for event in self.battle.events if event.kind == "message"], [2001])
        self.battle.regiments["H"].x, self.battle.regiments["H"].y = 500, 0
        self.call("PendingInRangeArc", 0)
        self.assertFalse(self.state.cond_flags)
        self.state.current_target = None
        self.call("PendingInRange", 0)
        self.assertFalse(self.state.cond_flags)

    def test_pending_in_range_tests_the_target_even_when_aiming_at_a_point(self):
        self.make(regiment("H", 0, 700))
        self.state.current_target, self.state.pending_spell = ("H", 0), 22
        self.state.target_point, self.state.aim_at_point = (0.0, 10.0), True
        self.call("PendingInRange", 0)
        self.assertFalse(self.state.cond_flags)

    def test_is_special_shooter(self):
        self.make()
        self.w.shooting_code = 17
        self.call("IsSpecialShooter")
        self.assertTrue(self.state.cond_flags)
        self.w.shooting_code = 1
        self.call("IsSpecialShooter")
        self.assertFalse(self.state.cond_flags)


if __name__ == "__main__":
    unittest.main()
