"""BDD scenarios for the Fireball head, trail and explosion timing (bf003_playtest section 2)."""
import unittest

from whshr.frontend.spell_visuals import FireballVisuals, Flight


def _fly(visuals, ticks, serial=1):
    """Fly a bolt along x = 10 * tick for `ticks` ticks, height tick; return the sprite list after each tick."""
    seen = []
    for tick in range(ticks):
        visuals.advance([Flight(serial, 10.0 * tick, 5.0, float(tick))])
        seen.append(visuals.sprites())
    return seen


def _frames(sprites):
    return sorted(sprite.frame for sprite in sprites)


class FireballVisualsTest(unittest.TestCase):
    def test_head_frame_cycles_125_to_128_one_per_tick(self):
        visuals = FireballVisuals()
        heads = [max(s.frame for s in sprites if s.frame <= 128 and s.x == 10.0 * i)
                 for i, sprites in enumerate(_fly(visuals, 9))]
        self.assertEqual(heads, [125, 126, 127, 128, 125, 126, 127, 128, 125])

    def test_head_is_at_the_current_position_and_height(self):
        visuals = FireballVisuals()
        sprites = _fly(visuals, 4)[-1]
        head = [s for s in sprites if s.x == 30.0][0]
        self.assertEqual((head.y, head.height), (5.0, 3.0))

    def test_a_puff_is_left_at_the_previous_position_each_tick_moved(self):
        visuals = FireballVisuals()
        sprites = _fly(visuals, 3)[-1]
        puffs = sorted((s.x, s.height) for s in sprites if s.x != 20.0)
        self.assertEqual(puffs, [(0.0, 0.0), (10.0, 1.0)])

    def test_no_puff_when_the_bolt_did_not_move(self):
        visuals = FireballVisuals()
        for _ in range(3):
            visuals.advance([Flight(1, 4.0, 4.0, 2.0)])
        self.assertEqual(len(visuals.sprites()), 1)

    def test_a_puff_plays_125_to_144_then_disappears_after_20_frames(self):
        visuals = FireballVisuals()
        _fly(visuals, 2)  # the puff at x = 0 is born on the second tick
        frames = []
        for _ in range(21):
            visuals.advance([])
            frames.append([s.frame for s in visuals.sprites() if s.x == 0.0])
        self.assertEqual(frames[:19], [[126 + i] for i in range(19)])  # ages 1..19 -> 126..144
        self.assertEqual(frames[19], [])
        # the first frame (125) was shown on the tick it was left
        visuals2 = FireballVisuals()
        sprites = _fly(visuals2, 2)[-1]
        self.assertIn(125, [s.frame for s in sprites if s.x == 0.0])

    def test_explosion_plays_177_to_185_on_the_ground_at_the_last_position(self):
        visuals = FireballVisuals()
        _fly(visuals, 5)
        shown = []
        for _ in range(9):
            visuals.advance([])
            shown.append([(s.frame, s.x, s.height) for s in visuals.sprites() if s.frame >= 177])
        self.assertEqual(shown, [[(177 + i, 40.0, 0.0)] for i in range(9)])
        visuals.advance([])
        self.assertEqual([s for s in visuals.sprites() if s.frame >= 177], [])

    def test_head_stops_when_the_flight_ends_and_everything_vanishes_afterwards(self):
        visuals = FireballVisuals()
        _fly(visuals, 5)
        visuals.advance([])
        self.assertEqual([s for s in visuals.sprites() if s.frame <= 128 and s.height > 0 and s.x == 40.0], [])
        for _ in range(25):
            visuals.advance([])
        self.assertEqual(visuals.sprites(), [])
        self.assertEqual(visuals.bolts, {})

    def test_two_bolts_are_independent(self):
        visuals = FireballVisuals()
        visuals.advance([Flight(1, 0.0, 0.0, 0.0), Flight(2, 100.0, 0.0, 0.0)])
        visuals.advance([Flight(2, 110.0, 0.0, 0.0)])
        explosions = [s for s in visuals.sprites() if s.frame >= 177]
        self.assertEqual([(s.x, s.frame) for s in explosions], [(0.0, 177)])


if __name__ == "__main__":
    unittest.main()
