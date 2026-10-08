"""The "Reload!" callout: React 12 ten ticks after an artillery shot (notes/reload_callout.md, GitHub #147).

The callout is spoken by the shot-event tail of library scripts 111/112, built here from its words
(notes/script_shooting.md section 5): the interpreter executes it, nothing else says "Reload!"."""

import unittest

from tests.script_helpers import FakeDll, word
from whshr.engine import Battle, Regiment
from whshr.interpreter import Event
from whshr.rules import Side

ARTILLERY, ARCHERS = 4, 3  # s_race classes
NO_MODEL = 0xFFFF
TAIL = [word("IfEventSource"), NO_MODEL, word("IfNot"),
        word("IfClass"), ARTILLERY * 8, word("If"),
        word("IfMachineDestroyed"), word("IfNot"),
        word("SetWait"), 10, word("Wait"), word("React"), 12, word("ReformToScriptRanks"),
        word("EndIf"), word("EndIf"), word("EndIf"), word("Yield")]
TEXTS = {34110: "Reload!", 34112: "I cannot!"}


def unit(identifier, side=Side.PLAYER, race=0, cls=ARTILLERY, x=100, **extra):
    return Regiment(identifier, identifier, x, 100, 0, side, models=3, ranks=1, points=10,
                    unit_class=cls, race=race, hud_class="art" if cls == ARTILLERY else "arch", **extra)


class ReloadCalloutTests(unittest.TestCase):
    def make(self, *units):
        battle = Battle(2000, 2000, list(units), seed=1995, script_dll=FakeDll(TAIL),
                        script_ids={u.identifier: 111 for u in units})
        battle.text_resources = dict(TEXTS)
        return battle

    def fire(self, battle, identifier, model=3):
        battle.event_bus.unit_states[identifier].current_event = Event(code=34, source=identifier, model=model)

    def reacts(self, battle):
        return [(e.data["sender"], e.data["code"], e.data["message"]) for e in battle.events if e.kind == "react"]

    def advance(self, battle, ticks):
        seen = []
        for _ in range(ticks):
            battle.tick()
            seen.extend(self.reacts(battle))
        return seen

    def test_player_artillery_says_reload_ten_ticks_after_the_shot(self):
        # The shot is handled in the first tick; the 10-tick wait ends on the tenth update, so "Reload!" is
        # said exactly there: not one update earlier, not later, and once.
        cannon = unit("cannon")
        battle = self.make(cannon)
        self.fire(battle, "cannon")
        self.assertEqual(self.advance(battle, 9), [])
        self.assertEqual(self.advance(battle, 1), [("cannon", 12, "Reload!")])
        self.assertEqual(self.advance(battle, 5), [])

    def test_it_comes_with_the_human_speech_cue_and_the_portrait_popup(self):
        cannon = unit("cannon")
        battle = self.make(cannon)
        self.fire(battle, "cannon")
        sounds = []
        for _ in range(14):
            battle.tick()
            sounds.extend((e.data["packet"], e.data["effect"]) for e in battle.events if e.kind == "sound")
        self.assertIn((5, 8), sounds)
        self.assertEqual((battle.portrait_popup.unit_id, battle.portrait_popup.expression), ("cannon", 2))

    def test_dwarven_artillery_says_it_too(self):
        battle = self.make(unit("cannon", race=2))
        self.fire(battle, "cannon")
        self.assertEqual([r[1] for r in self.advance(battle, 14)], [12])

    def test_races_without_a_row_say_nothing(self):
        for race in (3, 4, 5):
            with self.subTest(race=race):
                battle = self.make(unit("lobber", race=race))
                self.fire(battle, "lobber")
                self.assertEqual(self.advance(battle, 14), [])

    def test_enemy_army_artillery_never_says_it(self):
        battle = self.make(unit("foe", Side.ENEMY))
        self.fire(battle, "foe")
        self.assertEqual(self.advance(battle, 14), [])

    def test_archers_never_say_it(self):
        battle = self.make(unit("bows", cls=ARCHERS))
        self.fire(battle, "bows")
        self.assertEqual(self.advance(battle, 14), [])

    def test_a_destroyed_machine_says_nothing(self):
        cannon = unit("cannon")
        cannon.has_leader = False
        cannon.clear_anchor()  # a destroyed machine has no leader model and is no longer anchored
        battle = self.make(cannon)
        self.fire(battle, "cannon")
        self.assertEqual(self.advance(battle, 14), [])

    def test_a_shot_with_no_model_behind_it_says_nothing(self):
        battle = self.make(unit("cannon"))
        self.fire(battle, "cannon", model=-1)
        self.assertEqual(self.advance(battle, 14), [])

    def test_two_cannons_firing_together_both_speak_but_one_portrait_shows(self):
        first, second = unit("a"), unit("b", x=300)
        battle = self.make(first, second)
        self.fire(battle, "a")
        self.fire(battle, "b")
        said = self.advance(battle, 14)
        self.assertEqual(sorted(s[0] for s in said), ["a", "b"])
        self.assertEqual(battle.portrait_popup.unit_id, "a")


if __name__ == "__main__":
    unittest.main()
