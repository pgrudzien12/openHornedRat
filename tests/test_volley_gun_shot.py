"""The Volley Gun's shot: three puffs, three launches (notes/volley_gun_shot.md, GitHub #342)."""

import random
import unittest

from tests.script_helpers import FakeDll, word
from whshr import animation
from whshr.animation import SHOOT, STAND
from whshr.engine import Battle, ModelState, Regiment
from whshr import ranged
from whshr.rules import Side

ARTILLERY = 4  # s_race class


class Draws(random.Random):
    """Returns the listed values for successive `randrange` calls (the r0, r1, r2 skips), then 0."""

    def __init__(self, *values):
        super().__init__(0)
        self.values = list(values)

    def randrange(self, *_args, **_kwargs):
        return self.values.pop(0) if self.values else 0


def timeline(*skips):
    """(extra-post ticks, fire-step tick, ticks spent in the shot), tick 1 being the first shoot tick."""
    model, rng = ModelState(uid=0), Draws(*skips)
    extra, fire, tick = [], None, 0
    while True:
        tick += 1
        animation.step(model, SHOOT, rng, "volley")
        if model.action == STAND:
            return extra, fire, tick - 1
        if model.extra_post:
            extra.append(tick)
        if model.fire_event:
            fire = tick


def volley_gun(x=1000, y=1000, direction=0):
    return Regiment("V", "V", x, y, direction, Side.PLAYER, models=3, ranks=1, unit_class=ARTILLERY,
                    hud_class="art", sprite="Crew", leader_sprite="VoleyGun", has_leader=True, missile_code=7,
                    shooting_code=7, missile_range=ranged.WEAPONS[7].reach, bs=3)


class ProgramTests(unittest.TestCase):
    """Section 3 and the section 5 timeline: P1 = 7 - r0, P2 = P1 + 5 - r1, P3 = P2 + 5 - r2, stand at P3 + 5."""

    def test_the_report_timeline(self):
        self.assertEqual(timeline(2, 0, 3), ([5, 10], 12, 16))

    def test_the_slowest_shot(self):
        self.assertEqual(timeline(0, 0, 0), ([7, 12], 17, 21))

    def test_the_fastest_shot(self):
        self.assertEqual(timeline(3, 3, 3), ([4, 6], 8, 12))

    def test_requests_during_the_shot_are_dropped(self):
        model, rng = ModelState(uid=0), Draws(0, 0, 0)
        animation.step(model, SHOOT, rng, "volley")
        animation.step(model, animation.DEAD, rng, "volley")
        self.assertEqual((model.action, model.pending_action), (SHOOT, None))

    def test_a_cannon_makes_no_extra_post(self):
        model, rng = ModelState(uid=0), Draws(0)
        posts = []
        for _ in range(11):
            animation.step(model, SHOOT, rng, "gun")
            posts.append(model.extra_post)
        self.assertNotIn(True, posts)


class ScriptPostTests(unittest.TestCase):
    """Section 0.1: an extra post is the current request event with no figure; the countdown is untouched."""

    def make(self):
        gun = volley_gun()
        battle = Battle(3000, 3000, [gun], seed=1995, script_dll=FakeDll([word("Yield")]), script_ids={"V": 111})
        state = battle.event_bus.unit_states["V"]
        state.anim_event, state.anim_divisor, state.anim_countdown = 34, 1, 1
        return battle, gun, state

    def test_an_extra_post_queues_the_request_event_without_a_figure(self):
        battle, _, state = self.make()
        battle.event_bus.post_without_figure("V")
        event = state.event_queue[-1]
        self.assertEqual((event.code, event.source, event.model, state.anim_countdown), (34, "V", -1, 1))

    def test_the_90_percent_fallback_code_is_posted_as_it_is(self):
        battle, _, state = self.make()
        state.anim_event = 35
        battle.event_bus.post_without_figure("V")
        self.assertEqual(state.event_queue[-1].code, 35)

    def test_without_a_request_event_nothing_is_posted(self):
        battle, _, state = self.make()
        state.anim_event = 0
        battle.event_bus.post_without_figure("V")
        self.assertEqual(list(state.event_queue), [])


class EngineShotTests(unittest.TestCase):
    """Without scripts: one ordered shot gives three puffs and three launches, the first two from the unit
    position and the third from the machine figure (sections 1, 4; invariants of section 5)."""

    def test_one_shot_order_gives_three_puffs_and_three_launches(self):
        gun = volley_gun()
        battle = Battle(3000, 3000, [gun], seed=1995)
        battle.phase = "battle"
        battle.order_fire("V", point=(1000, 1240))
        battle.rng = random.Random(7)  # no misfire on the three launches
        puffs, launches = [], []
        for _ in range(30):
            mark = len(battle.events)
            battle.tick()
            puffs.extend(p for p in battle.muzzle_puffs if p not in puffs)
            launches.extend((e.data["x"], e.data["y"]) for e in battle.events[mark:] if e.kind == "projectile_launch")
        self.assertEqual(len(puffs), 3)
        self.assertTrue(all((p.x, p.y) == (1000, 1024) for p in puffs))
        self.assertEqual(len(launches), 3)
        self.assertEqual(launches[:2], [(1000, 1000), (1000, 1000)])
        self.assertEqual(launches[2], gun.positions[gun.leader_model_index or 0])


if __name__ == "__main__":
    unittest.main()
