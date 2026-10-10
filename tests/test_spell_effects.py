"""Spell effects: the effect table, the magical hit, bolts and beams, lasting spells, dispel and winds.

Vectors are notes/spell_effects.md section 5 (V1-V12) and notes/spell_lasting_effects.md section 9. Common set-up:
caster W at (0, 0) facing +Y on flat ground; the effect step runs once per "update" (the launch tick is update 1).
"""

import random
import unittest
from unittest import mock

from whshr.engine import Battle, Regiment  # first: it resolves the combat/interpreter import cycle
from whshr import interpreter, magic, spell_effects
from whshr.battle_events import BattleEvent
from whshr.rules import Side
from whshr.spell_effects import Impact


class ScriptedRng(random.Random):
    """Returns the listed raw draws as "rand mod n" (then 0 for ever), like the report's dice."""

    def __init__(self, draws=()):
        super().__init__(0)
        self.draws = list(draws)

    def _next(self):
        return self.draws.pop(0) if self.draws else 0

    def randrange(self, start, stop=None, step=1):
        low, high = (0, start) if stop is None else (start, stop)
        return low + self._next() % (high - low)

    def randint(self, a, b):
        return a + self._next() % (b - a + 1)


def unit(identifier, x, y, side=Side.ENEMY, models=10, **extra):
    extra.setdefault("has_leader", True)
    return Regiment(identifier, identifier, x, y, 0, side, models=models, ranks=1, **extra)


class EffectTestCase(unittest.TestCase):
    radii: dict = {}

    def make(self, *others, wizard_side=Side.PLAYER, bs=10, **wizard):
        self.w = unit("W", 0, 0, wizard_side, models=1, unit_class=interpreter.WIZARD_CLASS, bs=bs, **wizard)
        self.battle = Battle(5000, 5000, [self.w, *others], seed=1995)
        self.battle.phase = "battle"
        self.battle.rng = ScriptedRng()
        self.radii = {"W": 10, **self.radii}
        patcher = mock.patch.object(Regiment, "bounding_radius", lambda r: self.radii.get(r.identifier, 30))
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.battle

    def dice(self, *draws):
        self.battle.rng.draws = list(draws)

    def launch(self, code, x, y, caster=None, innate=False):
        return spell_effects.launch(self.battle, code, caster or self.w, -1, x, y, innate=innate)

    def update(self, times=1):
        for _ in range(times):
            spell_effects.tick(self.battle)

    def messages(self, text_id):
        return [event for event in self.battle.events if event.data.get("text_id") == text_id]

    def effects(self):
        return spell_effects.table(self.battle).effects()

    def bolt_ends(self):
        return [event for event in self.battle.events if event.kind == "spell_bolt_end"]


class ActivatedItemTests(unittest.TestCase):
    def test_banner_starts_at_leader_and_existing_target_overrides_clicked_point(self):
        bearer = unit("G", 0, 0, Side.PLAYER, items=("ItemBannerOfWrath",))
        enemy = unit("E", 0, 300, Side.ENEMY)
        battle = Battle(1000, 1000, [bearer, enemy])
        battle.event_bus.unit_states["G"].current_target = ("E", 0)
        battle.rng = ScriptedRng()

        battle.arm_item("G", "ItemBannerOfWrath")
        battle.order_item_target("G", "ItemBannerOfWrath", 400, 0)

        effect = spell_effects.table(battle).effects()[0]
        self.assertEqual(effect.code, spell_effects.LIGHTNING)
        self.assertEqual(effect.aim, spell_effects.reference_figure(enemy))
        self.assertEqual(effect.start, spell_effects.reference_figure(bearer))

    def test_grudgebringer_uses_no_power_and_rearms_on_the_wind(self):
        bearer = unit("G", 0, 0, Side.PLAYER, items=("ItemGrudgeBringer",))
        enemy = unit("E", 0, 400, Side.ENEMY)
        battle = Battle(1000, 1000, [bearer, enemy])
        battle.rng = ScriptedRng()
        before = battle.event_bus.power.player

        self.assertTrue(battle.arm_item("G", "ItemGrudgeBringer"))
        battle.order_item_target("G", "ItemGrudgeBringer", 0, 400)
        self.assertEqual([effect.code for effect in spell_effects.table(battle).effects()], [spell_effects.FIREBALL])
        self.assertEqual(battle.event_bus.power.player, before)
        with self.assertRaises(ValueError):
            battle.arm_item("G", "ItemGrudgeBringer")
        battle.tick_count = spell_effects.WIND_TICKS
        battle.tick()
        self.assertTrue(battle.arm_item("G", "ItemGrudgeBringer"))
        battle.order_item_target("G", "ItemGrudgeBringer", 0, 400)
        self.assertEqual([effect.code for effect in spell_effects.table(battle).effects()],
                         [spell_effects.FIREBALL, spell_effects.FIREBALL])

    def test_grudgebringer_can_issue_repeated_ctrl_orders_from_one_selection(self):
        bearer = unit("G", 0, 0, Side.PLAYER, items=("ItemGrudgeBringer",))
        battle = Battle(1000, 1000, [bearer, unit("E", 0, 400, Side.ENEMY)])
        battle.event_bus.power.player = 1

        battle.arm_item("G", "ItemGrudgeBringer")
        battle.order_item_target("G", "ItemGrudgeBringer", 0, 400)
        battle.order_item_target("G", "ItemGrudgeBringer", 0, 400)

        self.assertEqual([effect.code for effect in spell_effects.table(battle).effects()],
                         [spell_effects.FIREBALL, spell_effects.FIREBALL])
        self.assertEqual(battle.event_bus.power.player, 1)

    def test_out_of_arc_item_fails_with_feedback_and_stays_used(self):
        bearer = unit("G", 0, 0, Side.PLAYER, items=("ItemGrudgeBringer",))
        battle = Battle(1000, 1000, [bearer, unit("E", 0, 400, Side.ENEMY)])

        battle.arm_item("G", "ItemGrudgeBringer")
        battle.order_item_target("G", "ItemGrudgeBringer", 400, 0)

        self.assertEqual(spell_effects.table(battle).effects(), [])
        self.assertIn("ItemGrudgeBringer", bearer.used_items)
        self.assertIn(2021, [event.data.get("text_id") for event in battle.pending_feedback])  # reported with the next tick

    def test_cancelled_or_held_item_remains_used_and_potion_is_once_per_battle(self):
        bearer = unit("G", 0, 0, Side.PLAYER,
                      items=("ItemBannerOfWrath", "ItemPotionOfStrength"), held=True)
        battle = Battle(1000, 1000, [bearer, unit("E", 0, 400, Side.ENEMY)])

        self.assertTrue(battle.arm_item("G", "ItemBannerOfWrath"))
        battle.order_item_target("G", "ItemBannerOfWrath", 0, 400)
        self.assertEqual(spell_effects.table(battle).effects(), [])
        self.assertIn("ItemBannerOfWrath", bearer.used_items)
        earlier = BattleEvent("Earlier message", "message", text_id=9999)
        battle.events.append(earlier)
        battle.pending_feedback.append(earlier)
        self.assertFalse(battle.arm_item("G", "ItemPotionOfStrength"))
        self.assertFalse(bearer.potion_strength)
        self.assertEqual(battle.events, [earlier])
        self.assertEqual(battle.pending_feedback, [earlier])
        with self.assertRaises(ValueError):
            battle.arm_item("G", "ItemPotionOfStrength")

    def test_potion_increases_melee_strength_for_the_battle(self):
        from whshr import combat

        bearer = unit("G", 0, 0, Side.PLAYER, models=3, strength=3, leader_strength=4,
                      items=("ItemPotionOfStrength",))
        enemy = unit("E", 0, 10, Side.ENEMY, toughness=5)
        battle = Battle(100, 100, [bearer, enemy])
        battle.events.append(BattleEvent("Earlier event", "message", text_id=9998))
        battle.pending_feedback.append(BattleEvent("Earlier feedback", "message", text_id=9999))
        feedback_before = list(battle.events)
        pending_before = list(battle.pending_feedback)
        bearer.model_positions()
        assert bearer.living_leader_index is not None
        leader = bearer.melee_models[bearer.living_leader_index]
        ordinary = next(model for model in bearer.melee_models if model.uid != bearer.leader_uid)
        with mock.patch.object(battle.rng, "randint", return_value=6):
            _, before = combat._roll_model_attacks(bearer, enemy, battle.rng, model=leader)
            _, ordinary_before = combat._roll_model_attacks(bearer, enemy, battle.rng, model=ordinary)
            self.assertFalse(battle.arm_item("G", "ItemPotionOfStrength"))
            _, after = combat._roll_model_attacks(bearer, enemy, battle.rng, model=leader)
            _, ordinary_after = combat._roll_model_attacks(bearer, enemy, battle.rng, model=ordinary)
        self.assertLess(after["wound_need"], before["wound_need"])
        self.assertEqual(ordinary_after["wound_need"], ordinary_before["wound_need"])
        self.assertEqual(bearer.displayed_leader_strength, 7)
        self.assertEqual(battle.events, feedback_before)
        self.assertEqual(battle.pending_feedback, pending_before)

    def test_grudgebringer_passive_stays_with_leader_after_its_use_is_spent(self):
        from whshr import combat

        bearer = unit("G", 0, 0, Side.PLAYER, models=3, ws=3, strength=3,
                      leader_ws=5, leader_strength=4, items=("ItemGrudgeBringer",))
        enemy = unit("E", 0, 10, Side.ENEMY, ws=5, toughness=5)
        battle = Battle(100, 100, [bearer, enemy])
        bearer.model_positions()
        assert bearer.living_leader_index is not None
        leader = bearer.melee_models[bearer.living_leader_index]
        ordinary = next(model for model in bearer.melee_models if model.uid != bearer.leader_uid)
        with mock.patch.object(battle.rng, "randint", return_value=6):
            _, leader_roll = combat._roll_model_attacks(bearer, enemy, battle.rng, model=leader)
            _, ordinary_roll = combat._roll_model_attacks(bearer, enemy, battle.rng, model=ordinary)
            battle.arm_item("G", "ItemGrudgeBringer")
            _, spent_roll = combat._roll_model_attacks(bearer, enemy, battle.rng, model=leader)
        self.assertEqual((leader_roll["hit_need"], leader_roll["wound_need"]),
                         (spent_roll["hit_need"], spent_roll["wound_need"]))
        self.assertLess(leader_roll["hit_need"], ordinary_roll["hit_need"])
        self.assertLess(leader_roll["wound_need"], ordinary_roll["wound_need"])

    def test_dead_leader_is_not_replaced_by_reform(self):
        from whshr import combat

        bearer = unit("G", 0, 0, Side.PLAYER, models=6, items=("ItemPotionOfStrength",))
        enemy = unit("E", 0, 100, Side.ENEMY)
        battle = Battle(500, 500, [bearer, enemy])
        bearer.model_positions()
        old_uid = bearer.leader_uid
        combat.kill_models(bearer, [bearer.living_leader_index], battle)
        self.assertIsNone(bearer.living_leader_index)
        self.assertEqual(bearer.leader_uid, old_uid)
        self.assertTrue(any(event.code == 0x17 for event in battle.event_bus.unit_states["G"].event_queue))
        battle._begin_reform(bearer, 2)
        self.assertIsNone(bearer.living_leader_index)
        with self.assertRaises(ValueError):
            battle.arm_item("G", "ItemPotionOfStrength")

    def test_reform_keeps_the_same_leader_in_the_centre_slot(self):
        from whshr import formation

        bearer = unit("G", 0, 0, Side.PLAYER, models=6, items=("ItemPotionOfStrength",))
        battle = Battle(500, 500, [bearer])
        bearer.model_positions()
        leader_uid = bearer.leader_uid
        leader_index = bearer.living_leader_index
        assert leader_index is not None
        bearer.positions[leader_index] = (200.0, 200.0)

        battle._begin_reform(bearer, 2)

        self.assertEqual(bearer.leader_uid, leader_uid)
        assert bearer.living_leader_index is not None
        self.assertEqual(bearer.reform_slots[bearer.living_leader_index],
                         formation.reform_slot_order(6, 2)[0])


def record_hits():
    hits = []
    original = spell_effects.magical_hit

    def recorder(battle, target, impact, trace=None):
        hits.append((target.identifier, impact.strength))
        original(battle, target, impact, trace)
    return hits, mock.patch.object(spell_effects, "magical_hit", recorder)


class BeamTests(EffectTestCase):
    def test_warp_lightning_hits_on_tick_20_and_its_terminal_impact_fires_the_same_tick(self):
        """V1: N = 21; the in-flight hit at y 362 stops the beam and, 38 < 40 from the destination, the terminal
        impact follows in the same tick with message 2004."""
        self.radii = {"E": 40}
        self.make(unit("E", 0, 400, toughness=3, wounds=5))
        self.assertTrue(self.launch(spell_effects.WARP_LIGHTNING, 0, 400))
        self.assertEqual(self.effects()[0].steps, 21)
        self.update(19)
        self.battle.regiments["E"].model_positions()
        self.assertEqual(self.battle.regiments["E"].melee_models[7].wounds_taken, 0)
        self.dice(27, 1, 3)  # model 7, D6 2 (S5 vs T3 needs 2+), wounds 3 + 1
        self.update()
        self.assertEqual(self.battle.regiments["E"].melee_models[7].wounds_taken, 4)
        self.assertEqual(len(self.messages(2004)), 1)
        self.assertGreaterEqual(self.effects()[0].tail, 0)

    def test_finished_bolt_keeps_the_spell_active_through_its_tail(self):
        self.make()
        self.launch(spell_effects.LIGHTNING, 0, 100)
        self.update(5)
        self.assertTrue(spell_effects.spell_active(self.battle, "W", spell_effects.LIGHTNING))
        self.update(spell_effects.TAIL_TICKS + 1)
        self.assertFalse(spell_effects.spell_active(self.battle, "W", spell_effects.LIGHTNING))
        self.assertEqual(self.effects(), [])

    def test_gaze_of_mork_hits_each_unit_once_per_tick_inside_it(self):
        """V2: A at y 150 and B at y 300 (footprint 30) are each hit on three ticks; nothing at the destination."""
        self.radii = {"A": 30, "B": 30}
        self.make(unit("A", 0, 150), unit("B", 0, 300))
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.GAZE, 0, 400)
            self.update(25)
        self.assertEqual([name for name, _ in hits], ["A"] * 3 + ["B"] * 3)
        self.assertEqual(self.messages(2004), [])

    def test_scatter_uses_the_casters_bs_and_the_spell_range(self):
        """V3: BS 3, d 400, Lightning range 576: step 5; draws 13, 4, 7, 3 -> (25, 365), N 19."""
        self.make(bs=3)
        self.dice(13, 4, 7, 3)
        self.launch(spell_effects.LIGHTNING, 0, 400)
        effect = self.effects()[0]
        self.assertEqual((effect.dest, effect.steps), ((25, 365), 19))

    def test_a_ridge_removes_the_beam_without_impact(self):
        """V11: a 20-high ridge at y 180-220 under an 8-high beam."""
        self.radii = {"E": 40}
        self.make(unit("E", 0, 400))
        self.battle.ground_height = lambda x, y: 20.0 if 180 <= y <= 220 else 0.0
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.LIGHTNING, 0, 400)
            self.update(25)
        self.assertEqual(hits, [])


    def test_a_beam_survives_at_height_zero_and_a_ridge_one_higher_removes_it_after_the_test(self):
        """bf003_playtest 8.2: Lightning L = A = 4, start (0, 0), destination (0, 200), N = 11; height = 8 - ground.
        r = 6 at (0, 91) over ground 8 flies on at exactly 0; r = 5 at (0, 110) over a 9-high ridge tests at -1
        (a ground unit there is struck), then the beam is removed with no terminal impact."""
        self.radii = {"E": 5}
        self.make(unit("E", 0, 110))
        self.battle.ground_height = lambda x, y: {91: 8.0, 110: 9.0}.get(int(y), 0.0)
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.LIGHTNING, 0, 200)
            effect = self.effects()[0]
            self.assertEqual((effect.dest, effect.steps), ((0, 200), 11))
            self.update(6)
            self.assertEqual(((effect.x, effect.y), self.bolt_ends()), ((0, 91), []))
            self.update()
        self.assertEqual([name for name, _ in hits], ["E"])
        self.assertEqual([(end.data["reason"], end.data["height"]) for end in self.bolt_ends()], [("below_ground", -1)])
        self.assertEqual(self.messages(2004), [])

    def test_without_the_ridge_the_beam_reaches_its_terminal_impact_at_r_2(self):
        self.make()
        self.battle.ground_height = lambda x, y: 0.0
        self.launch(spell_effects.LIGHTNING, 0, 200)
        self.update(9)
        self.assertEqual(self.bolt_ends(), [])
        self.update()
        self.assertEqual([(end.data["reason"], end.data["y"]) for end in self.bolt_ends()], [("terminal", 200)])


    def test_a_stopping_bolt_that_hits_at_its_destination_strikes_once_and_has_no_terminal_impact(self):
        """spell_effects.md 2.4: the terminal impact needs the projectile still alive (review of #236)."""
        self.radii = {"E": 5}
        self.make(unit("E", 0, 360))
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.PIERCING, 0, 360)
            self.update(spell_effects.FIXED_FLIGHT + 1)
        self.assertEqual([name for name, _ in hits], ["E"])
        self.assertEqual([end.data["reason"] for end in self.bolt_ends()], ["hit"])
        self.assertEqual(self.messages(2004), [])

    def test_wind_blast_logs_no_bolt_launch(self):
        self.make()
        self.launch(spell_effects.WIND_BLAST, 0, 300)
        self.assertEqual([event for event in self.battle.events if event.kind == "spell_bolt_launch"], [])


class MagicalHitTests(EffectTestCase):
    def setUp(self):
        self.make(unit("E", 0, 400, toughness=3, wounds=5, psychology=frozenset({"MagicResistent"})))
        self.e = self.battle.regiments["E"]

    def hit(self, *draws, save=False):
        self.dice(*draws)
        spell_effects.magical_hit(self.battle, self.e, Impact("W", 5, 6, save, False))
        return [model.wounds_taken for model in self.e.melee_models]

    def test_magic_resistance_ignores_a_hit_on_an_even_draw(self):
        """V4: model 7, to-wound passes, MR draw 8 (even) -> ignored."""
        self.assertEqual(sum(self.hit(27, 1, 8)), 0)

    def test_magic_resistance_lets_an_odd_draw_through(self):
        self.assertEqual(self.hit(27, 1, 9, 2)[7], 3)

    def test_failed_wound_roll_does_nothing(self):
        self.assertEqual(sum(self.hit(27, 0)), 0)  # D6 = 1 < 2

    def test_wounds_stay_on_the_one_model(self):
        self.e.wounds = 2
        self.hit(23, 1, 9, 5)  # 6 wounds on model 3: it dies, nothing overflows
        self.assertEqual((self.e.models, sum(m.wounds_taken for m in self.e.melee_models)), (9, 0))
        self.assertEqual(self.e.melee_models[0].credit, None)

    def test_armour_save_applies_only_when_allowed(self):
        self.e.armour = 4  # 3+ save, S5 -> 5+
        self.assertEqual(sum(self.hit(27, 1, 4, save=True)), 0)  # save roll 5
        self.assertEqual(sum(self.hit(27, 1, 9, 0)), 1)  # no save roll: the next draw is the MR one


class SpearAndFireballTests(EffectTestCase):
    def test_hunting_spear_reaches_a_stationary_target_and_strikes_six_times(self):
        """V5: arrival hit on update 28 at y 324, then the chain S6..S1 on update 29."""
        self.radii = {"E": 40}
        self.make(unit("E", 0, 360))
        hits, patch = record_hits()
        with patch:
            self.assertTrue(self.launch(spell_effects.HUNTING_SPEAR, 0, 360))
            self.update(27)
            self.assertEqual(hits, [])
            self.update()
            self.assertEqual(hits, [("E", 6)])
            self.update()
        self.assertEqual(hits, [("E", 6), ("E", 6), ("E", 5), ("E", 4), ("E", 3), ("E", 2), ("E", 1)])
        self.assertEqual(self.effects(), [])

    def test_hunting_spear_chain_misses_on_raised_ground(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 360))
        self.battle.ground_height = lambda x, y: 40.0
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.HUNTING_SPEAR, 0, 360)
            self.update(29)
        self.assertEqual(hits, [("E", 6)])

    def test_hunting_spear_needs_a_unit_under_the_point(self):
        self.make()
        self.assertFalse(self.launch(spell_effects.HUNTING_SPEAR, 0, 360))
        self.assertEqual(len(self.messages(2021)), 1)

    def test_fireball_at_the_ground_hits_silently_with_its_last_test(self):
        """V7: no terminal impact and no direct-hit message against a ground point."""
        self.radii = {"E": 10}
        self.make(unit("E", 0, 300))
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.FIREBALL, 0, 300)
            self.update(19)
        self.assertEqual(hits, [("E", 4)])
        self.assertEqual(self.messages(2004), [])

    def test_fireball_is_not_removed_on_its_first_tick_when_ground_under_the_start_rises_a_fraction(self):
        """bf003_playtest 3.2 vector 2: height 1 - 0.0001 with the arc included, so the bolt flies on and tests."""
        self.radii = {"E": 10}
        self.make(unit("E", 0, 300))
        self.battle.ground_height = lambda x, y: 16.0001 if (x, y) == (0, 0) else 16.0
        self.launch(spell_effects.FIREBALL, 0, 300)
        self.update()
        effect = self.effects()[0]
        self.assertEqual((effect.x, effect.y, effect.arc, effect.remaining), (0, 0, 1, 17))
        self.assertFalse(effect.ended)
        self.assertEqual(self.bolt_ends(), [])

    def test_the_first_tested_position_is_exactly_the_start_point(self):
        self.make()
        self.w.x, self.w.y = 628.7, 869.3
        self.launch(spell_effects.FIREBALL, 628.7, 1169.3)
        self.update()
        effect = self.effects()[0]
        self.assertEqual((effect.x, effect.y), effect.start)

    def test_the_in_flight_test_runs_at_a_negative_height_then_the_bolt_is_removed_without_a_terminal_impact(self):
        """Vector 3: r = 0, arc -1, a ground unit at the destination: struck silently, then removed."""
        self.radii = {"E": 10}
        self.make(unit("E", 0, 300))
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.FIREBALL, 0, 300)
            self.update(19)
        self.assertEqual(hits, [("E", 4)])
        self.assertEqual(self.bolt_ends()[-1].data["reason"], "below_ground")
        self.assertLess(self.bolt_ends()[-1].data["height"], 0)

    def test_a_bolt_that_kills_a_model_logs_launch_strike_with_deaths_and_the_end_reason(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 300, models=7))
        self.dice(*([0] * 3), 5, 0, 5, 0)  # whatever the dice, the hit rolls are recorded
        self.launch(spell_effects.FIREBALL, 0, 300)
        self.update(19)
        kinds = [event.kind for event in self.battle.events]
        self.assertEqual(kinds.count("spell_bolt_launch"), 1)
        strikes = [event for event in self.battle.events if event.kind == "spell_strike"]
        self.assertTrue(strikes)
        for strike in strikes:
            self.assertEqual(strike.data["regiment"], "E")
            self.assertIn("wound_roll", strike.data)
            self.assertEqual(strike.data["models_before"] - strike.data["models_after"], strike.data.get("killed", 0))
        self.assertEqual(len(self.bolt_ends()), 1)

    def test_a_forced_kill_is_logged_as_a_death(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 300, models=7))
        self.battle.rng = ScriptedRng([0, 5, 0])  # model 0, wound roll 6, wound die 1
        self.launch(spell_effects.FIREBALL, 0, 300)
        self.battle.rng.draws = [0, 5, 0]
        self.update(19)
        strike = next(event for event in self.battle.events if event.kind == "spell_strike")
        self.assertEqual(strike.data["outcome"], "wounded")
        self.assertEqual(strike.data["killed"], 1)
        self.assertEqual(strike.data["models_after"], strike.data["models_before"] - 1)
        self.assertEqual(self.bolt_ends()[0].data["reason"], "hit")

    def test_a_dispelled_bolt_logs_the_cancellation(self):
        self.make()
        self.launch(spell_effects.FIREBALL, 0, 300)
        self.update(2)
        spell_effects.cancel(self.battle, self.effects()[0])
        self.assertEqual([event.data["reason"] for event in self.bolt_ends()], ["cancelled"])

    def test_burning_head_panics_every_unit_containing_the_point(self):
        """V9: Ld 7; a draw of 9 gives 11 > 7 and routs; a draw of 4 gives 6 and passes."""
        self.radii = {"X": 40, "Y": 40}
        self.make(unit("X", 0, 400, leadership=7), unit("Y", 0, 410, leadership=7))
        self.dice(9, 4)
        spell_effects._panic_inside(self.battle, 0, 400)
        self.assertEqual((self.battle.regiments["X"].routing, self.battle.regiments["Y"].routing), (True, False))


class FrameworkTests(EffectTestCase):
    def test_the_effect_list_has_no_capacity_and_runs_in_launch_order(self):
        """Engine design: no fixed number of effects; each launch adds one at the end of the list."""
        self.make()
        for _ in range(100):
            self.assertTrue(self.launch(spell_effects.LIGHTNING, 0, 100))
        self.assertTrue(self.launch(spell_effects.PESTILENT_BREATH, 0, 100, innate=True))
        serials = [effect.serial for effect in self.effects()]
        self.assertEqual(serials, sorted(serials))
        self.assertEqual(len(serials), 101)

    def test_launch_reveals_the_caster(self):
        self.make()
        self.w.hidden = True
        self.launch(spell_effects.LIGHTNING, 0, 100)
        self.assertFalse(self.w.hidden)

    def test_a_removed_wizard_takes_its_bolts_with_it(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 400))
        hits, patch = record_hits()
        with patch:
            self.launch(spell_effects.LIGHTNING, 0, 400)
            self.update(3)
            self.battle.remove_from_play(self.w)
            self.update(25)
        self.assertEqual((hits, self.effects()), ([], []))

    def test_removing_the_target_cancels_the_spear(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 360))
        self.launch(spell_effects.HUNTING_SPEAR, 0, 360)
        self.update(3)
        self.battle.remove_from_play(self.battle.regiments["E"])
        self.update()
        self.assertEqual(self.effects(), [])

    def test_lasting_effect_of_a_monster_caster_survives_its_removal(self):
        self.radii = {"P": 40}
        shaman = unit("S", 0, 0, Side.ENEMY, models=1, unit_class=7, shooting_code=16)
        self.make(shaman, unit("P", 0, 300, Side.PLAYER))
        spell_effects.launch(self.battle, spell_effects.MADNESS, shaman, -1, 0, 300)
        self.battle.remove_from_play(shaman)
        self.update(5)
        self.assertTrue(spell_effects.maddened(self.battle, "P"))


class MadnessTests(EffectTestCase):
    def setUp(self):
        self.radii = {"P": 40, "Q": 40, "A": 40}

    def queued(self, unit_id):
        return [event.code for event in self.battle.event_bus.unit_states[unit_id].event_queue]

    def test_the_unit_under_the_point_changes_side_and_hears_0x31(self):
        self.make(unit("P", 500, 500, Side.PLAYER), wizard_side=Side.ENEMY)
        self.assertTrue(self.launch(spell_effects.MADNESS, 520, 500))
        self.assertEqual(self.battle.regiments["P"].side, Side.ENEMY)
        self.assertEqual(self.queued("P"), [0x31])
        self.assertTrue(spell_effects.maddened(self.battle, "P"))

    def test_the_nearest_reference_figure_is_taken(self):
        self.make(unit("P", 500, 500, Side.PLAYER, models=1), unit("Q", 515, 500, Side.PLAYER, models=1),
                  wizard_side=Side.ENEMY)
        self.launch(spell_effects.MADNESS, 520, 500)
        self.assertEqual((self.battle.regiments["P"].side, self.battle.regiments["Q"].side),
                         (Side.PLAYER, Side.ENEMY))

    def test_a_nearer_friend_makes_the_cast_fail(self):
        self.make(unit("P", 500, 500, Side.ENEMY, models=1), unit("A", 518, 500, Side.PLAYER, models=1))
        self.assertFalse(self.launch(spell_effects.MADNESS, 520, 500))
        self.assertEqual(len(self.messages(2021)), 1)
        self.assertEqual(self.battle.regiments["P"].side, Side.ENEMY)

    def test_a_maddened_unit_cannot_be_maddened_again(self):
        other = unit("O", 0, 0, Side.ENEMY, models=1, unit_class=interpreter.WIZARD_CLASS)
        self.make(unit("P", 500, 500, Side.PLAYER), other, wizard_side=Side.ENEMY)
        self.launch(spell_effects.MADNESS, 520, 500)
        self.assertFalse(spell_effects.launch(self.battle, spell_effects.MADNESS, other, -1, 520, 500))

    def test_a_maddened_enemy_joins_the_allied_side(self):
        self.make(unit("P", 500, 500, Side.ENEMY))
        self.launch(spell_effects.MADNESS, 500, 500)
        self.assertEqual(self.battle.regiments["P"].side, Side.NEUTRAL)

    def test_the_end_restores_the_saved_side_over_a_set_side_and_sends_0x32(self):
        self.make(unit("P", 500, 500, Side.PLAYER), wizard_side=Side.ENEMY)
        self.launch(spell_effects.MADNESS, 500, 500)
        self.battle.event_bus.unit_states["P"].event_queue.clear()
        self.battle.event_bus.unit_states["P"].unit_flags2 |= spell_effects.MADDENED_SCRIPT_FLAG
        self.update(180)
        self.battle.regiments["P"].side = Side.NEUTRAL  # a SetSide during the madness
        self.assertTrue(spell_effects.maddened(self.battle, "P"))
        self.update()
        self.assertEqual(self.battle.regiments["P"].side, Side.PLAYER)
        self.assertEqual(self.queued("P"), [0x32])
        self.assertFalse(self.battle.event_bus.unit_states["P"].unit_flags2 & spell_effects.MADDENED_SCRIPT_FLAG)

    def test_dispel_is_measured_from_the_aim_point(self):
        """B 9: a Mork Save Uz on M 70 from the aim point dispels the Madness although P walked away."""
        self.radii = {"P": 40, "M": 40}
        self.make(unit("P", 500, 500, Side.PLAYER), unit("M", 570, 500, Side.ENEMY), wizard_side=Side.ENEMY)
        self.launch(spell_effects.MADNESS, 500, 500)
        self.battle.regiments["P"].x = 800
        self.assertTrue(self.launch(spell_effects.MORK_SAVE_UZ, 570, 500))
        self.dice(30)
        self.update()
        self.assertEqual(self.battle.regiments["P"].side, Side.PLAYER)
        self.assertEqual(len(self.messages(2006)), 1)


class SkitterleapTests(EffectTestCase):
    def test_the_caster_lands_on_the_fifth_update_keeping_facing(self):
        self.make()
        self.launch(spell_effects.SKITTERLEAP, 0, 900)
        self.update(4)
        self.assertEqual((self.w.x, self.w.y), (0, 0))
        self.update()
        self.assertEqual((self.w.x, self.w.y, self.w.direction), (0, 900, 0))
        self.assertTrue(all(abs(y - 900) < 30 for _, y in self.w.positions))

    def test_a_talisman_near_the_landing_point_stops_the_leap(self):
        self.radii = {"T": 40}
        self.make(unit("T", 60, 900, items=("ItemTalismanOfObsidian",)))
        self.launch(spell_effects.SKITTERLEAP, 0, 900)
        self.update(6)
        self.assertEqual((self.w.x, self.w.y), (0, 0))

    def test_the_scripted_marker_leap_cannot_be_dispelled(self):
        self.radii = {"T": 40}
        self.make(unit("T", 60, 900, items=("ItemTalismanOfObsidian",)))
        self.launch(spell_effects.SKITTERLEAP + 512, 0, 900)
        self.update(5)
        self.assertEqual((self.w.x, self.w.y), (0, 900))


class EreWeGoTests(EffectTestCase):
    def test_stacked_casts_leave_initiative_20(self):
        """B 3 stacking table."""
        self.radii = {"E": 40}
        self.make(unit("E", 0, 300, toughness=4, initiative=3))
        e = self.battle.regiments["E"]
        self.launch(spell_effects.ERE_WE_GO, 0, 300)
        self.assertEqual((e.toughness, e.initiative), (5, 20))
        self.update(50)
        self.launch(spell_effects.ERE_WE_GO, 0, 300)
        self.assertEqual((e.toughness, e.initiative), (6, 20))
        self.update(131)  # #1 ends on its 181st update
        self.assertEqual((e.toughness, e.initiative), (5, 3))
        self.update(50)
        self.assertEqual((e.toughness, e.initiative), (4, 20))

    def test_a_single_cast_is_restored_after_180_ticks(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 300, toughness=3, initiative=2))
        self.launch(spell_effects.ERE_WE_GO, 0, 300)
        self.update(180)
        self.assertEqual(self.battle.regiments["E"].initiative, 20)
        self.update()
        self.assertEqual((self.battle.regiments["E"].toughness, self.battle.regiments["E"].initiative), (3, 2))


class FistsTests(EffectTestCase):
    def setUp(self):
        self.make(unit("E", 400, 410, toughness=3, wounds=5), wizard_side=Side.ENEMY)
        self.launch(spell_effects.FISTS, 400, 400)
        self.e = self.battle.regiments["E"]

    def strike(self, *draws):
        self.dice(*draws)
        self.update()
        return sum(model.wounds_taken for model in self.e.melee_models)

    def test_a_roll_of_four_wounds_once(self):
        self.assertEqual(self.strike(3, 0), 1)

    def test_consecutive_sixes_chain(self):
        self.assertEqual(self.strike(5, 0, 5, 0, 2), 2)  # 6, model, 6, model, 3

    def test_a_one_does_nothing(self):
        self.assertEqual(self.strike(0), 0)

    def test_reach_is_sixteen_inclusive(self):
        self.e.y = 417
        self.assertEqual(self.strike(3, 0), 0)
        self.e.y = 416
        self.update(3)
        self.assertEqual(self.strike(3, 0), 1)

    def test_strikes_every_fourth_tick_45_times(self):
        strikes = []
        with mock.patch.object(spell_effects, "_fists_strike", lambda battle, effect: strikes.append(1)):
            self.update(181)
        self.assertEqual((len(strikes), self.effects()), (45, []))


class DispelTests(EffectTestCase):
    def test_dispel_magic_passes_every_third_tick_and_ends_after_a_success(self):
        """B 9: enemy effect 70 from D; a 60 fails at tick 0, a 10 succeeds at tick 3."""
        self.radii = {"P": 40, "E": 40}
        enemy = unit("S", 1000, 1000, Side.ENEMY, models=1, unit_class=interpreter.WIZARD_CLASS)
        self.make(enemy, unit("P", 70, 0, Side.PLAYER))
        spell_effects.launch(self.battle, spell_effects.ERE_WE_GO, enemy, -1, 70, 0)
        self.launch(spell_effects.DISPEL_MAGIC, 0, 0)
        self.dice(60)
        self.update(3)
        self.assertTrue(spell_effects.spell_active(self.battle, "S", spell_effects.ERE_WE_GO))
        self.dice(10)
        self.update()
        self.assertFalse(spell_effects.spell_active(self.battle, "S", spell_effects.ERE_WE_GO))
        self.assertEqual(len(self.messages(2006)), 1)
        self.assertEqual(self.effects(), [])

    def test_dispel_magic_is_once_per_battle(self):
        self.make()
        self.launch(spell_effects.DISPEL_MAGIC, 0, 0)
        self.assertTrue(spell_effects.dispel_selected(self.battle, "W"))

    def test_reach_is_strictly_below_80_and_every_eligible_effect_rolls(self):
        enemy = unit("S", 1000, 0, Side.ENEMY, models=1, unit_class=interpreter.WIZARD_CLASS)
        self.make(enemy)
        spell_effects.launch(self.battle, spell_effects.FISTS, enemy, -1, 0, 79)
        spell_effects.launch(self.battle, spell_effects.FISTS, enemy, -1, 0, 80)
        self.dice(0, 0)
        self.assertTrue(spell_effects.dispel_pass(self.battle, self.w, 50, None))
        self.assertEqual([effect.aim for effect in self.effects()], [(0, 80)])
        self.assertEqual(self.battle.rng.draws, [])

    def test_own_effects_and_effects_on_the_protected_unit_are_exempt(self):
        self.make()
        self.launch(spell_effects.FISTS, 0, 0)
        self.assertFalse(spell_effects.dispel_pass(self.battle, self.w, 100, None))

    def test_the_ai_reads_only_the_first_hostile_effect(self):
        self.radii = {"S": 10}
        enemy = unit("S", 0, 200, Side.ENEMY, models=1, unit_class=interpreter.WIZARD_CLASS)
        self.make(enemy)
        spell_effects.launch(self.battle, spell_effects.FISTS, enemy, -1, 0, 3000)
        self.assertTrue(spell_effects.dispel_choice(self.battle, self.w, lambda a, b: True))
        self.assertFalse(spell_effects.dispel_choice(self.battle, self.w, lambda a, b: False))
        enemy.hidden = True
        self.assertFalse(spell_effects.dispel_choice(self.battle, self.w, lambda a, b: True))


class WindTests(unittest.TestCase):
    def wind(self, current, draw):
        return spell_effects.wind(current, ScriptedRng([draw]))

    def test_wind_table(self):
        cases = [(0, 0, 1), (0, 1, 1), (0, 7, 7), (2, 3, 5), (6, 0, 2), (6, 7, 8), (8, 5, 8)]
        self.assertEqual([self.wind(c, d) for c, d, _ in cases], [expected for _, _, expected in cases])

    def test_winds_fall_at_the_start_of_tick_501_player_first(self):
        battle = Battle(1000, 1000, [unit("A", 0, 0)], seed=1)
        battle.event_bus._power = magic.PowerPools(2, 6)
        battle.rng = ScriptedRng([3, 7])
        battle.tick_count = 499
        spell_effects.blow_wind(battle)
        self.assertEqual((battle.event_bus.power.player, battle.event_bus.power.enemy), (2, 6))
        battle.tick_count = 500
        spell_effects.blow_wind(battle)
        self.assertEqual((battle.event_bus.power.player, battle.event_bus.power.enemy), (5, 8))


class CastPendingTests(EffectTestCase):
    def test_ai_skips_a_spell_whose_effect_is_still_active(self):
        self.radii = {"H": 40}
        self.make(unit("H", 0, 400, Side.PLAYER), wizard_side=Side.ENEMY,
                  spells=magic.spell_codes(("SkavenWarpLightning", "SkavenMadness")))
        self.battle.event_bus._power = magic.PowerPools(0, 8)
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["W"]
        self.launch(spell_effects.WARP_LIGHTNING, 0, 400)
        state.current_target = ("H", 0)
        interp.op_ChooseSpellForTarget(state, None, [0], "W", 0, random.Random(1))
        self.assertEqual(state.pending_spell, spell_effects.MADNESS)

    def test_cast_pending_creates_the_effect(self):
        self.radii = {"H": 40}
        self.make(unit("H", 0, 400, Side.PLAYER), wizard_side=Side.ENEMY)
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["W"]
        state.current_target, state.pending_spell = ("H", 0), spell_effects.WARP_LIGHTNING
        interp.op_CastPending(state, None, [0], "W", 0, random.Random(1))
        self.assertTrue(state.cond_flags)
        self.assertEqual([effect.code for effect in self.effects()], [spell_effects.WARP_LIGHTNING])


class AzureAndFlockTests(EffectTestCase):
    def test_azure_blades_rolls_every_model_of_a_block_whose_circle_contains_the_target(self):
        """C3 6: W at (0,0); E (16 models, T3, no save) centred 30 away with radius 33: core, every model rolls."""
        self.radii = {"W": 8, "E": 33}
        self.make(unit("E", 0, 30, models=16, toughness=3, has_leader=False))
        self.assertTrue(self.launch(spell_effects.AZURE_BLADES, 0, 0))
        self.dice(*[2, 0, 0] * 16)  # D6 3 passes 3+, save roll fails, 1 wound
        self.update()
        self.assertEqual(self.battle.regiments["E"].models, 0)
        self.assertEqual(len(self.messages(2004)), 1)

    def test_azure_blades_margin_takes_k_picks_at_half_strength(self):
        """C3 6: E (12 models) radius 30 centred 30 away: margin, k = trunc(8 x 12 / 38) = 2 picks at S2."""
        self.radii = {"W": 8, "E": 30}
        self.make(unit("E", 0, 30, models=12, toughness=3, has_leader=False))
        self.launch(spell_effects.AZURE_BLADES, 0, 0)
        self.dice(0, 4, 0, 1, 4, 0)  # pick, D6 5 (S2 vs T3 needs 5+), failed save; twice
        self.update()
        self.assertEqual((self.battle.regiments["E"].models, len(self.messages(2005))), (10, 1))

    def test_azure_blades_strikes_180_times(self):
        self.radii = {"W": 8}
        self.make()
        strikes = []
        with mock.patch.object(spell_effects, "blast", lambda *args, **kw: strikes.append(1)):
            self.launch(spell_effects.AZURE_BLADES, 0, 0)
            self.update(181)
        self.assertEqual((len(strikes), self.effects()), (180, []))

    def test_flock_strikes_on_ticks_10_18_26_and_ends_on_38(self):
        self.make()
        strikes = []
        with mock.patch.object(spell_effects, "blast",
                               lambda battle, *args, **kw: strikes.append(battle.tick_count)):
            self.launch(spell_effects.FLOCK, 100, 100)
            for tick in range(40):
                self.battle.tick_count = tick
                self.update()
        self.assertEqual((strikes, self.effects()), ([10, 18, 26], []))


class AreaSpellTests(EffectTestCase):
    def test_flamestorm_burns_every_tick_from_18_with_a_messaged_column_end_and_never_ends(self):
        self.make()
        calls = []
        with mock.patch.object(spell_effects, "blast",
                               lambda battle, x, y, r, impact, excluded, messages: calls.append(messages)):
            self.launch(spell_effects.FLAMESTORM, 0, 400)
            self.update(18)
            self.assertEqual(calls, [])
            self.update(19)
            self.assertEqual(len(calls), 20)  # T+18 .. T+36, two on T+36
            self.assertEqual(calls[-1], True)
            self.update(1000)
        self.assertEqual(len(self.effects()), 1)
        self.assertEqual(len(spell_effects.solid_areas(self.battle)), 1)

    def test_a_new_flamestorm_replaces_the_casters_previous_one(self):
        self.make()
        self.launch(spell_effects.FLAMESTORM, 0, 400)
        self.launch(spell_effects.FLAMESTORM, 0, 200)
        self.assertEqual([effect.aim for effect in self.effects()], [(0, 200)])
        self.assertEqual(len(spell_effects.solid_areas(self.battle)), 1)

    def test_thorn_holds_units_strictly_within_32_and_releases_within_64(self):
        self.make(unit("E", 0, 431), unit("F", 0, 432))
        self.launch(spell_effects.TANGLING_THORN, 0, 400)
        self.assertEqual((self.battle.regiments["E"].held, self.battle.regiments["F"].held), (True, False))
        self.update(5000)
        self.assertTrue(self.battle.regiments["E"].held)
        spell_effects.cancel(self.battle, self.effects()[0])
        self.assertFalse(self.battle.regiments["E"].held)

    def test_fireball_impact_near_the_thorn_burns_it(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 420))
        self.launch(spell_effects.TANGLING_THORN, 0, 400)
        self.launch(spell_effects.FIREBALL, 0, 420)
        self.update(20)
        self.assertFalse(any(effect.code == spell_effects.TANGLING_THORN for effect in self.effects()))
        self.assertFalse(self.battle.regiments["E"].held)

    def test_da_krunch_slays_every_unit_reaching_within_32(self):
        self.radii = {"E": 40, "F": 40}
        self.make(unit("E", 0, 371, models=30), unit("F", 0, 372))
        self.launch(spell_effects.DA_KRUNCH, 0, 300)
        self.update(10)
        self.assertEqual((self.battle.regiments["E"].models, self.battle.regiments["F"].models), (0, 10))
        self.assertEqual(self.battle.regiments["E"].melee_models, [])
        self.update()
        self.assertEqual(len(spell_effects.solid_areas(self.battle)), 1)
        self.update(36)  # standing through T+46
        self.assertEqual(len(spell_effects.solid_areas(self.battle)), 1)
        self.update()  # T+47: the foot lifts
        self.assertEqual(spell_effects.solid_areas(self.battle), [])
        self.update(10)  # the lift; the effect ends on T+57
        self.assertEqual(self.effects(), [])

    def test_conflagration_radius_fuse_panic_and_fall(self):
        """C1 7: draw 1 -> k 2, R 24; panic on T and T+9; fall T+18..T+27, n = trunc(20 x 14 / 24) = 11."""
        self.radii = {"A": 40}
        self.make(unit("A", 0, 10, models=20, leadership=12))
        self.dice(1)
        self.launch(spell_effects.CONFLAGRATION, 0, 0)
        self.assertEqual(self.effects()[0].value, 2)
        self.update(18)
        self.assertEqual(self.battle.regiments["A"].models, 20)
        self.update()
        self.assertEqual(self.battle.regiments["A"].models, 9)


class ChannelledSpellTests(EffectTestCase):
    def test_storm_fires_2d6_plus_one_bolts_alternating_targets(self):
        """C2 1.6: draws 3, 4 -> 10 bolts; with A and B near the point the bolts alternate B, A, B, A."""
        self.make(unit("A", 0, 450), unit("B", 30, 400), wizard_side=Side.PLAYER)
        self.dice(3, 4)
        self.launch(spell_effects.STORM, 0, 400)
        storm = self.effects()[0]
        self.assertEqual(storm.value, 10)
        targets = []
        with mock.patch.object(spell_effects, "_fly", lambda battle, effect, bolt: True):
            for _ in range(60):
                before = storm.flying
                self.update()
                if storm.flying and not before:
                    targets.append(storm.target)
                if storm.ended:
                    break
        self.assertEqual(targets[:4], ["B", "A", "B", "A"])
        self.assertTrue(spell_effects.channelling(self.battle, "W") or storm.ended)

    def test_storm_is_cancelled_when_its_target_leaves(self):
        self.make(unit("A", 0, 450))
        self.launch(spell_effects.STORM, 0, 400)
        self.update(5)
        self.battle.remove_from_play(self.battle.regiments["A"])
        self.update()
        self.assertEqual(self.effects(), [])

    def test_curse_halves_and_a_recast_restores_first(self):
        self.radii = {"E": 40, "F": 40}
        self.make(unit("E", 0, 300, initiative=4, speed_per_tick=9.0), unit("F", 300, 300, initiative=3))
        self.launch(spell_effects.CURSE, 0, 300)
        e = self.battle.regiments["E"]
        self.assertEqual((e.initiative, e.speed_per_tick), (2, 4.5))
        self.w.direction = 0
        self.launch(spell_effects.CURSE, 300, 300)
        self.assertEqual((e.initiative, e.speed_per_tick, self.battle.regiments["F"].initiative), (4, 9.0, 1))

    def test_curse_on_a_mounted_unit_ends_on_a_failed_test_in_segment_10(self):
        self.radii = {"E": 40}
        self.make(unit("E", 0, 300, initiative=4, leadership=7, mount=1))
        self.launch(spell_effects.CURSE, 0, 300)
        self.battle.tick_count = 0  # segment 10
        self.dice(4)
        self.update()
        self.assertEqual(len(self.effects()), 1)
        self.dice(9)
        self.update()
        self.assertEqual((self.effects(), self.battle.regiments["E"].initiative), ([], 4))

    def test_flying_bower_lands_exactly_on_the_point_at_t74(self):
        self.radii = {"W": 16}
        self.make()
        self.launch(spell_effects.FLYING_BOWER, 0, 900)
        self.update(20)
        self.assertTrue(spell_effects.lifted(self.battle, "W"))
        self.update(54)
        self.assertTrue(spell_effects.lifted(self.battle, "W"))
        self.update()
        self.assertEqual((self.w.x, self.w.y), (0, 900))
        self.assertFalse(spell_effects.lifted(self.battle, "W"))

    def test_bower_is_pushed_off_a_friend_but_not_off_an_enemy(self):
        self.radii = {"W": 16, "F": 40, "E": 40}
        self.make(unit("F", 0, 900, Side.PLAYER), unit("E", 0, 1500))
        self.launch(spell_effects.FLYING_BOWER, 10, 900)
        self.assertEqual(self.effects()[0].aim, (48, 900))
        self.launch(spell_effects.FLYING_BOWER, 10, 1500)
        self.assertEqual(self.effects()[1].aim, (10, 1500))

    def test_sapphire_arch_swallows_within_48_and_a_later_arch_releases(self):
        self.radii = {"P": 40, "Q": 40, "R": 40}
        self.make(unit("P", 530, 530), unit("Q", 534, 534), unit("R", 535, 535))
        self.launch(spell_effects.SAPPHIRE_ARCH, 500, 500)
        self.update(162)
        self.assertEqual([spell_effects.lifted(self.battle, name) for name in "PQR"], [True, True, False])
        self.assertEqual((self.battle.regiments["P"].x, self.battle.regiments["P"].y), (-40, -40))
        self.update(20)
        self.launch(spell_effects.SAPPHIRE_ARCH, 900, 200)
        self.update(21)
        self.assertEqual((self.battle.regiments["P"].x, self.battle.regiments["P"].y), (930, 230))
        self.assertFalse(spell_effects.lifted(self.battle, "P"))
        self.assertEqual(self.battle.regiments["P"].models, 10)

    def test_arch_release_after_more_than_900_clock_ticks_kills(self):
        self.radii = {"P": 40}
        self.make(unit("P", 530, 530))
        spell_effects.table(self.battle).in_arch.add("P")
        spell_effects.table(self.battle).stamps["P"] = (0, (30.0, 30.0))
        self.battle.tick_count = 2000
        self.launch(spell_effects.SAPPHIRE_ARCH, 900, 200)
        self.update(21)
        self.assertEqual(self.battle.regiments["P"].models, 0)


class DoomwheelTests(EffectTestCase):
    def test_bolt_aims_at_the_nearest_unit_within_its_distance_then_rolls_failure(self):
        """C3 6: dice 3, 4, 2 -> D 288, Q (0, 288); E at (30, 300) found; fail draw 11 -> 5 -> not fired."""
        doom = unit("D", 0, 0, Side.PLAYER, models=1)
        self.make(unit("E", 30, 300), unit("F", 0, -200), doom)
        launched = []
        with mock.patch.object(spell_effects, "launch", lambda battle, code, caster, origin, x, y, innate=False:
                               launched.append((x, y))):
            self.dice(2, 3, 1, 4)  # bolt 1 fired at E; bolts 2 and 3 (D 12) find W at 12 and fire
            spell_effects.doomwheel_volley(self.battle, doom)
            self.assertEqual(launched, [(30, 300), (0, 0), (0, 0)])
            launched.clear()
            self.dice(2, 3, 1, 11, 0, 0, 0, 5, 0, 0, 0, 5)  # every failure draw is 5 mod 6
            spell_effects.doomwheel_volley(self.battle, doom)
        self.assertEqual((launched, len(self.messages(2021))), ([], 3))

    def test_no_unit_in_reach_falls_back_96_ahead_with_jitter(self):
        doom = unit("D", 0, 0, Side.PLAYER, models=1)
        self.make(doom)
        self.w.x = 5000
        launched = []
        with mock.patch.object(spell_effects, "launch", lambda battle, code, caster, origin, x, y, innate=False:
                               launched.append((x, y))):
            self.dice(0, 0, 0, 50, 5, 0)  # D 12, none found; y jitter 50, x jitter 5
            spell_effects.doomwheel_volley(self.battle, doom)
        self.assertEqual(launched[0], (-35, 106))


class WindBlastTests(EffectTestCase):
    def test_range_is_a_fresh_multiple_of_four_inches(self):
        self.assertEqual(magic.spell_range(spell_effects.WIND_BLAST, ScriptedRng([2])), 288)
        self.assertEqual(magic.spell_range(spell_effects.WIND_BLAST, ScriptedRng([5])), 576)

    def test_the_gust_lays_a_permanent_trail(self):
        self.make()
        self.dice(4)  # R2 = 480
        self.launch(spell_effects.WIND_BLAST, 0, 540)
        self.update(300)
        areas = spell_effects.solid_areas(self.battle)
        self.assertTrue(0 < len(areas) <= 30)
        self.assertEqual(len(self.effects()), 1)


class EngineHookTests(EffectTestCase):
    def test_area_objects_are_solid_scenery_while_their_effect_lives(self):
        """C1 0: the thorn's area object is a solid active map object for movement, sight and missiles."""
        self.make()
        objects, missiles = len(self.battle.objects), len(self.battle.shooting_objects)
        self.launch(spell_effects.TANGLING_THORN, 0, 400)
        added = self.battle.objects[-1]
        self.assertEqual((added["x"], added["y"], added["radius"]), (0, 400, 32))
        self.assertIn("os_solid", added["status"])
        self.assertEqual(len(self.battle.shooting_objects), missiles + 1)
        spell_effects.cancel(self.battle, self.effects()[0])
        self.assertEqual((len(self.battle.objects), len(self.battle.shooting_objects)), (objects, missiles))

    def test_a_lifted_unit_engages_nobody_and_is_not_drawn(self):
        from whshr.rules import may_engage
        self.make(unit("E", 0, 30))
        enemy = self.battle.regiments["E"]
        self.assertTrue(may_engage(self.w, enemy))
        self.w.lifted = True
        self.assertFalse(may_engage(self.w, enemy) or may_engage(enemy, self.w))
        self.assertFalse(self.w.visible_to_player)

    def test_a_held_unit_refuses_move_turn_and_flight(self):
        self.make(unit("E", 0, 410))
        self.battle.phase = "battle"
        self.launch(spell_effects.TANGLING_THORN, 0, 400)
        self.assertTrue(self.battle.regiments["E"].held)
        player = unit("P", 0, 420, Side.PLAYER)
        self.battle.regiments["P"] = player
        player.held = True
        with self.assertRaises(ValueError):
            self.battle.order_move("P", 0, 900)
        with self.assertRaises(ValueError):
            self.battle.order_turn_left("P")
        interp = interpreter.ScriptInterpreter(self.battle, self.battle.event_bus, None)
        state = self.battle.event_bus.unit_states["E"]
        interp.op_FleeAhead(state, None, [0], "E", 0, random.Random(1))
        self.assertFalse(self.battle.regiments["E"].routing)


if __name__ == "__main__":
    unittest.main()
