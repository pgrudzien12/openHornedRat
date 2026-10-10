"""BDD scenarios for the Fireball head, trail and explosion timing (bf003_playtest sections 2 and 8.3)."""
import unittest

from whshr.frontend.spell_visuals import FireballVisuals, Flight


def _fly(visuals, ticks, serial=1, end=False):
    """Update a bolt along x = 10 * tick (height = tick) for `ticks` ticks; the last one ends the flight if `end`."""
    seen = []
    for tick in range(ticks):
        visuals.advance([Flight(serial, 10.0 * tick, 5.0, float(tick), end and tick == ticks - 1)])
        seen.append(visuals.sprites())
    return seen


def _heads(sprites):
    return [s for s in sprites if s.frame <= 128 and s.height == s.x / 10]


class FireballVisualsTest(unittest.TestCase):
    def test_head_and_first_puff_are_drawn_on_the_launch_tick_at_the_start_point(self):
        sprites = _fly(FireballVisuals(), 1)[0]
        self.assertEqual([(s.frame, s.x, s.height) for s in sprites], [(125, 0.0, 0.0), (125, 0.0, 0.0)])

    def test_trail_follows_the_report_table_for_a_bolt_flying_along_y(self):
        visuals = FireballVisuals()
        shown = []
        for tick in range(4):
            visuals.advance([Flight(1, 100.0, 100.0 + 10 * tick, 0.0)])
            shown.append(sorted((s.frame, s.y) for s in visuals.sprites()))
        self.assertEqual(shown[0], [(125, 100.0), (125, 100.0)])
        self.assertEqual(shown[1], [(126, 100.0), (126, 110.0)])
        self.assertEqual(shown[2], [(125, 110.0), (127, 100.0), (127, 120.0)])
        self.assertEqual(shown[3], [(125, 120.0), (126, 110.0), (128, 100.0), (128, 130.0)])

    def test_first_puff_shows_its_last_frame_on_the_20th_tick(self):
        visuals = FireballVisuals()
        for tick in range(20):
            visuals.advance([Flight(1, 0.0, 10.0 * tick, 0.0)])
        self.assertIn(144, [s.frame for s in visuals.sprites()])
        visuals.advance([Flight(1, 0.0, 200.0, 0.0)])
        self.assertNotIn(144, [s.frame for s in visuals.sprites()])

    def test_head_frame_cycles_125_to_128_one_per_update(self):
        visuals = FireballVisuals()
        heads = [max(s.frame for s in sprites if s.x == 10.0 * i) for i, sprites in enumerate(_fly(visuals, 9))]
        self.assertEqual(heads, [125, 126, 127, 128, 125, 126, 127, 128, 125])

    def test_head_is_at_the_current_position_and_height(self):
        head = [s for s in _fly(FireballVisuals(), 4)[-1] if s.x == 30.0][0]
        self.assertEqual((head.y, head.height), (5.0, 3.0))

    def test_a_puff_is_left_at_the_previous_position_each_tick_moved(self):
        sprites = _fly(FireballVisuals(), 3)[-1]
        puffs = sorted((s.x, s.height) for s in sprites if s.x != 20.0)
        self.assertEqual(puffs, [(0.0, 0.0), (10.0, 1.0)])  # launch puff, then one per move

    def test_no_new_puff_when_the_bolt_did_not_move(self):
        visuals = FireballVisuals()
        for _ in range(3):
            visuals.advance([Flight(1, 4.0, 4.0, 2.0)])
        self.assertEqual(len(visuals.sprites()), 2)  # the launch puff and the head

    def test_a_puff_plays_125_to_144_then_disappears_after_20_frames(self):
        visuals = FireballVisuals()
        self.assertIn(125, [s.frame for s in _fly(visuals, 1, end=True)[0]])
        frames = []
        for _ in range(21):
            visuals.advance([])
            frames.append([s.frame for s in visuals.sprites() if s.x == 0.0 and s.frame < 177])
        self.assertEqual(frames[:19], [[126 + i] for i in range(19)])
        self.assertEqual(frames[19:], [[], []])

    def test_ending_tick_has_no_head_and_starts_the_explosion_on_the_ground(self):
        sprites = _fly(FireballVisuals(), 5, end=True)[-1]
        self.assertEqual([s for s in sprites if s.frame <= 128 and s.x == 40.0 and s.frame != 125], [])
        self.assertEqual([(s.frame, s.x, s.height) for s in sprites if s.frame >= 177], [(177, 40.0, 0.0)])

    def test_ending_tick_still_leaves_a_puff_when_the_head_moved(self):
        sprites = _fly(FireballVisuals(), 3, end=True)[-1]
        self.assertIn((10.0, 125), [(s.x, s.frame) for s in sprites if s.frame < 177 and s.x == 10.0][:1])

    def test_explosion_shows_177_to_185_over_nine_ticks_then_vanishes(self):
        visuals = FireballVisuals()
        _fly(visuals, 5, end=True)
        shown = []
        for _ in range(8):
            visuals.advance([])
            shown.append([(s.frame, s.x) for s in visuals.sprites() if s.frame >= 177])
        self.assertEqual(shown, [[(178 + i, 40.0)] for i in range(8)])
        visuals.advance([])
        self.assertEqual([s for s in visuals.sprites() if s.frame >= 177], [])

    def test_everything_vanishes_after_the_trail_has_played_out(self):
        visuals = FireballVisuals()
        _fly(visuals, 5, end=True)
        for _ in range(25):
            visuals.advance([])
        self.assertEqual(visuals.sprites(), [])
        self.assertEqual(visuals.bolts, {})

    def test_heads_are_emitted_before_explosions_before_puffs(self):
        visuals = FireballVisuals()
        visuals.advance([Flight(1, 0.0, 0.0, 0.0), Flight(2, 50.0, 0.0, 0.0)])
        visuals.advance([Flight(1, 0.0, 0.0, 0.0, True), Flight(2, 50.0, 0.0, 0.0)])
        order = [(s.frame, s.x) for s in visuals.sprites()]
        self.assertEqual(order, [(126, 50.0), (177, 0.0), (126, 0.0), (126, 50.0)])  # head, explosion, 2 puffs

    def test_two_bolts_are_independent(self):
        visuals = FireballVisuals()
        visuals.advance([Flight(1, 0.0, 0.0, 0.0), Flight(2, 100.0, 0.0, 0.0)])
        visuals.advance([Flight(1, 0.0, 0.0, 0.0, True), Flight(2, 110.0, 0.0, 0.0)])
        self.assertEqual([(s.x, s.frame) for s in visuals.sprites() if s.frame >= 177], [(0.0, 177)])


if __name__ == "__main__":
    unittest.main()
