"""The Magic button, spell list and Magic targeting in the battle HUD and view (notes/player_magic_panel.md).

Given wizard W (Lightning 1, Fireball 1, Azure Blades 1, Dispel Magic 1, Storm of Shemtek 3) focused and idle, player
pool 4: the report's section 10 vectors, driven through the HUD, the view and the scene."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from tests.test_hud import _hud, _panel_pos, pygame
from whshr import interpreter, magic, spell_effects
from whshr.battle_scene import BattleScene
from whshr.engine import Regiment
from whshr.frontend.battle_view import BattleView
from whshr.rules import Side

SPELLS = ("CelestialLightning", "BrightFireball", "CelestialAzureBlades", "GeneralDispel", "CelestialStormOfShemtek")
LIGHTNING, FIREBALL = magic.SPELL_CODES["celestiallightning"], magic.SPELL_CODES["brightfireball"]
STORM = magic.SPELL_CODES["celestialstormofshemtek"]


def row_pos(hud, index):
    return _panel_pos(hud, 210, 75 + 19 * index)


class MagicPanelCase(unittest.TestCase):
    def setUp(self):
        wizard = Regiment("W", "W", 100, 200, 0, Side.PLAYER, models=1, ranks=1, hud_class="wiz",
                          unit_class=interpreter.WIZARD_CLASS, spells=magic.spell_codes(SPELLS))
        enemy = Regiment("E", "E", 100, 700, 256, Side.ENEMY, models=5, ranks=1, hud_class="inf")
        self.hud = _hud(selected="W", regiments=[wizard, enemy])
        self.battle = self.hud.battle
        self.battle.event_bus._power = magic.PowerPools(4, 8)
        self.scene = BattleScene.__new__(BattleScene)
        self.scene.battle, self.scene.selected_id, self.scene.logger = self.battle, "W", None
        self.view = BattleView.__new__(BattleView)
        self.view.hud, self.view.scene = self.hud, self.scene
        self.view.order_mode = None
        self.view.cursors, self.view._cursor_mode = None, None
        self.view.camera = SimpleNamespace()
        self.view.event_log = []

    def click(self, pos, ctrl=False):
        """A full left click (press and release) at a screen position; the view's events go to the scene."""
        mod = pygame.KMOD_CTRL if ctrl else 0
        events = [*self.view.events(SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=pos, mod=mod)),
                  *self.view.events(SimpleNamespace(type=pygame.MOUSEBUTTONUP, button=1, pos=pos, mod=mod))]
        for event in events:
            self.scene.handle(event, SimpleNamespace())
        return events

    def _press(self, name):
        """Press a command slot through the view, bypassing slot geometry."""
        self.hud.hit_test = Mock(return_value=name)
        events = self.view.events(SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0), mod=0))
        del self.hud.hit_test
        for event in events:
            self.scene.handle(event, SimpleNamespace())
        return events

    def queued(self):
        return list(self.battle.event_bus.unit_states["W"].event_queue)


class MagicButtonTests(MagicPanelCase):
    def test_only_a_player_wizard_has_an_enabled_magic_button(self):
        self.assertEqual(self.hud.slots()["BL"], "magic")
        self.assertTrue(self.hud._button_enabled("magic", self.battle.regiments["W"]))
        self.assertFalse(self.hud._button_enabled("magic", self.battle.regiments["E"]))

    def test_the_first_press_shows_the_list_and_the_second_enters_magic_with_no_spell(self):
        self._press("magic")
        self.assertTrue(self.hud.spell_list_open)
        self.assertIsNone(self.view.order_mode)
        self._press("magic")
        self.assertTrue(self.hud.spell_list_open)
        self.assertEqual(self.view.order_mode, "magic")

    def test_rows_answer_in_file_order(self):
        self._press("magic")
        self.assertEqual([self.hud.hit_test(row_pos(self.hud, i)) for i in range(5)],
                         [f"spell:{code}" for code in self.battle.regiments["W"].spells])

    def test_items_replace_the_spell_list(self):
        self._press("magic")
        self.hud.press("items")
        self.assertFalse(self.hud.spell_list_open)
        self.assertTrue(self.hud.item_list_open)

    def test_a_casting_wizard_has_empty_command_slots(self):
        self.battle.select_spell("W", FIREBALL)
        self.battle.order_cast("W", FIREBALL, 100, 600)
        self.assertEqual(self.hud.slots(), {})


class SpellRowTests(MagicPanelCase):
    def test_clicking_lightning_pays_selects_and_arms_the_wand(self):
        self._press("magic")
        self.assertEqual(self.click(row_pos(self.hud, 0)), [("select_spell", LIGHTNING)])
        self.assertEqual(self.battle.player_power, 3)
        self.assertEqual(self.view.order_mode, f"spell:{LIGHTNING}")
        self.assertTrue(self.battle.spell_usable("W", STORM))

    def test_then_fireball_loses_lightnings_cost(self):
        self._press("magic")
        self.click(row_pos(self.hud, 0))
        self.click(row_pos(self.hud, 1))
        self.assertFalse(spell_effects.spell_selected(self.battle, "W", LIGHTNING))
        self.assertEqual((self.battle.player_power, self.view.order_mode), (2, f"spell:{FIREBALL}"))
        self.assertFalse(self.battle.spell_usable("W", STORM))

    def test_a_ground_click_orders_the_spell_and_ends_targeting(self):
        self._press("magic")
        self.click(row_pos(self.hud, 1))
        self.assertEqual(self.view._magic_click(self.view.order_mode, (300.0, 600.0), None, False),
                         (("cast", FIREBALL, 300.0, 600.0, False),))
        self.scene.handle(("cast", FIREBALL, 300.0, 600.0, False), SimpleNamespace())
        self.assertIsNone(self.view.order_mode)
        self.assertTrue(self.hud.spell_list_open)
        [event] = self.queued()
        self.assertEqual((event.code, event.parameter, event.x, event.y), (0x2B, FIREBALL, 300, 600))
        self.assertEqual(self.battle.player_power, 3)

    def test_ctrl_ground_clicks_repeat_while_the_pool_lasts(self):
        self.battle.event_bus._power = magic.PowerPools(2, 8)
        self._press("magic")
        self.click(row_pos(self.hud, 1))  # pool 1
        for event in self.view._magic_click(self.view.order_mode, (300.0, 600.0), None, True):
            self.scene.handle(event, SimpleNamespace())
        self.assertEqual((self.battle.player_power, self.view.order_mode), (0, f"spell:{FIREBALL}"))
        for event in self.view._magic_click(self.view.order_mode, (310.0, 600.0), None, True):
            self.scene.handle(event, SimpleNamespace())
        self.assertIsNone(self.view.order_mode)
        self.assertEqual(len(self.queued()), 2)

    def test_back_clears_the_selection_without_a_refund_and_keeps_the_list(self):
        self._press("magic")
        self.click(row_pos(self.hud, 1))
        self._press("back")
        self.assertFalse(spell_effects.spell_selected(self.battle, "W", FIREBALL))
        self.assertEqual(self.battle.player_power, 3)
        self.assertIsNone(self.view.order_mode)
        self.assertTrue(self.hud.spell_list_open)

    def test_another_command_clears_the_selection(self):
        self._press("magic")
        self.click(row_pos(self.hud, 1))
        self._press("move")
        self.assertFalse(spell_effects.spell_selected(self.battle, "W", FIREBALL))
        self.assertEqual(self.view.order_mode, "move")
        self.assertFalse(self.hud.spell_list_open)

    def test_azure_blades_is_ordered_on_the_row_click(self):
        self._press("magic")
        self.click(row_pos(self.hud, 2))
        self.assertIsNone(self.view.order_mode)
        self.assertEqual([(e.code, e.x, e.y) for e in self.queued()], [(0x2B, 100, 200)])

    def test_an_unusable_row_does_nothing(self):
        self.battle.event_bus._power = magic.PowerPools(2, 8)
        self._press("magic")
        self.assertEqual(self.click(row_pos(self.hud, 4)), [])
        self.assertEqual(self.battle.player_power, 2)

    def test_ctrl_click_cancels_an_active_spell_and_nothing_else(self):
        self._press("magic")
        self.assertEqual(self.click(row_pos(self.hud, 0), ctrl=True), [])
        spell_effects.launch(self.battle, spell_effects.AZURE_BLADES, self.battle.regiments["W"], -1, 100, 200)
        self.assertTrue(spell_effects.spell_active(self.battle, "W", spell_effects.AZURE_BLADES))
        self.assertEqual(self.click(row_pos(self.hud, 2), ctrl=True),
                         [("cancel_spell_effects", spell_effects.AZURE_BLADES)])
        self.assertFalse(spell_effects.spell_active(self.battle, "W", spell_effects.AZURE_BLADES))
        self.assertEqual(self.battle.player_power, 4)

    def test_selecting_another_unit_clears_the_selection(self):
        self._press("magic")
        self.click(row_pos(self.hud, 1))
        self.scene.handle(("select", "E"), SimpleNamespace())
        self.assertFalse(spell_effects.spell_selected(self.battle, "W", FIREBALL))


class NoSpellModeTests(MagicPanelCase):
    def test_clicking_an_enemy_orders_an_auto_cast(self):
        self._press("magic")
        self._press("magic")
        events = self.view._magic_click("magic", (100.0, 700.0), "E", False)
        self.assertEqual(events, (("wizard_target", "E"),))
        self.assertIsNone(self.view.order_mode)
        self.scene.handle(events[0], SimpleNamespace())
        self.assertEqual([(e.code, e.source) for e in self.queued()], [(0x29, "E")])

    def test_open_ground_does_nothing(self):
        self.view.order_mode = "magic"
        self.assertEqual(self.view._magic_click("magic", (0.0, 0.0), None, False), ())


class PowerDisplayTests(MagicPanelCase):
    def test_the_compass_shows_one_marker_per_point(self):
        from whshr.frontend import hud as hud_module

        marker = object()
        self.hud._icon = Mock(return_value=marker)
        draws = []
        self.hud._draw_panel = lambda quad, *args, **kwargs: draws.append((quad, args))
        self.hud._draw_power(0, 0)
        self.assertEqual([args for _quad, args in draws],
                         list(hud_module.POWER_MARKER_POSITIONS[:4]))


if __name__ == "__main__":
    unittest.main()
