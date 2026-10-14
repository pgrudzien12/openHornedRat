"""Spell bolts against a flier whose height changes (notes/airborne_units.md A8, GitHub #388).

Flat ground, caster W at (0, 0), flier F 288 ahead with footprint radius 25, no scatter (BS 10, every draw 0)."""

from tests.test_spell_effects import EffectTestCase, unit
from whshr import spell_effects
from whshr.rules import Side


class FlierBoltTests(EffectTestCase):
    radii = {"F": 25, "G": 30}

    def setUp(self):
        self.f = unit("F", 0, 288, sprite="Gyrocopter", models=1)
        self.f.flight_state().elevation = 32

    def struck(self) -> list[str]:
        return [event.data.get("regiment") for event in self.battle.events if event.kind == "spell_strike"]

    def cast(self, code: int, elevation_after_launch: int | None = None, updates: int = 30, *others) -> None:
        self.make(self.f, *others)
        self.launch(code, 0, 288)
        if elevation_after_launch is not None:
            self.f.flight.elevation = elevation_after_launch
        self.update(updates)

    def ends(self) -> list[str]:
        return [event.data["reason"] for event in self.bolt_ends()]

    def test_a1_a_fireball_hits_a_hovering_flier_in_flight(self):
        self.cast(spell_effects.FIREBALL)
        self.assertEqual((self.struck(), self.ends()), (["F"], ["hit"]))

    def test_a2_a_flier_that_lands_during_the_flight_is_passed_over(self):
        self.cast(spell_effects.FIREBALL, elevation_after_launch=20)  # band 20..36, the bolt at 38 and 39
        self.assertEqual(self.struck(), [])
        self.assertEqual(self.ends(), ["terminal"])  # at height 0: it cannot strike the airborne flier

    def test_a3_a_flier_that_takes_off_during_the_flight_is_passed_under(self):
        self.f.flight.elevation = 0
        self.cast(spell_effects.FIREBALL, elevation_after_launch=12)
        self.assertEqual((self.struck(), self.ends()), ([], ["below_ground"]))

    def test_a3_still_on_the_ground_it_is_hit(self):
        self.f.flight.elevation = 0
        self.cast(spell_effects.FIREBALL)
        self.assertEqual(self.struck(), ["F"])

    def test_a4_lightning_aimed_straight_at_a_hovering_flier_misses(self):
        self.cast(spell_effects.LIGHTNING)
        self.assertEqual((self.struck(), self.ends()), ([], ["terminal"]))

    def test_a7_lightning_hits_a_grounded_flier_with_its_terminal_impact(self):
        self.f.flight.elevation = 0
        self.cast(spell_effects.LIGHTNING)
        self.assertEqual((self.struck(), self.ends()), (["F"], ["terminal"]))

    def test_the_terminal_impact_strikes_a_ground_unit_under_the_flier(self):
        ground = unit("G", 0, 288, side=Side.ENEMY)
        self.make(ground, self.f)  # G is picked first at the aim point, so A = 0: the bolt flies at ground level
        self.launch(spell_effects.LIGHTNING, 0, 288)
        self.update(30)
        self.assertEqual(self.struck(), ["G"])

    def test_a8_the_hunting_spear_passes_under_a_hovering_flier_and_expires(self):
        self.cast(spell_effects.HUNTING_SPEAR, updates=200)
        self.assertEqual(self.struck(), [])
        self.assertEqual(self.effects(), [])

    def test_a10_the_spear_hits_once_the_flier_is_down_to_8(self):
        self.make(self.f)
        self.launch(spell_effects.HUNTING_SPEAR, 0, 288)
        self.update(60)
        self.assertEqual(self.struck(), [])
        self.f.flight.elevation = 8
        self.update(30)
        self.assertIn("F", self.struck())

    def test_a11_an_airborne_casters_fireball_starts_at_the_ground(self):
        self.make()
        caster = self.w
        caster.sprite = caster.leader_sprite = "Wyvern"
        caster.flight_state().elevation = 32
        effect = self.launch(spell_effects.FIREBALL, 0, 288)
        self.assertIsNotNone(effect)
        self.assertIsNone(self.effects()[0].launch_height)

    def test_gaze_of_mork_starts_at_an_airborne_casters_elevation(self):
        self.make()
        self.w.sprite = self.w.leader_sprite = "Wyvern"
        self.w.flight_state().elevation = 32
        self.launch(spell_effects.GAZE, 0, 288)
        self.assertEqual(self.effects()[0].launch_height, 32)

    def test_the_aim_height_is_read_at_the_aim_point_before_scatter(self):
        self.make(self.f)
        self.assertEqual(spell_effects.flying_aim_height(self.battle, 0, 288 + 40), 40)  # within the 48 pick circle
        self.assertEqual(spell_effects.flying_aim_height(self.battle, 0, 288 + 60), 0)
