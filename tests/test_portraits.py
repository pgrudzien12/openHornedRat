import struct
import tempfile
import unittest
from pathlib import Path

from whshr.portraits import EYE_SEQUENCE, MOUTH_TALK_FRAMES, PortraitAnimator, dietrich_portrait, speaker_portrait


class PortraitAnimatorTests(unittest.TestCase):
    def test_talking_sequence_cycles_the_documented_mouth_frames(self):
        # notes/glue_portraits.md §3.2-3.3: one step per 25 ms tick, each mouth step shown for
        # 2 (frame 6) or 3 ticks.
        animator = PortraitAnimator(sequence=1)
        self.assertEqual(animator.mouth_frame, MOUTH_TALK_FRAMES[0])

        animator.advance(25 * 3)  # first mouth step's duration

        self.assertEqual(animator.mouth_frame, MOUTH_TALK_FRAMES[1])

    def test_the_eye_loop_opens_then_blinks_for_the_documented_tick_counts(self):
        animator = PortraitAnimator(sequence=1)
        self.assertEqual(animator.eye_frame, EYE_SEQUENCE[0][0])

        animator.advance(25 * EYE_SEQUENCE[0][1])  # exhaust the first (open-eyes) step exactly

        self.assertEqual(animator.eye_frame, EYE_SEQUENCE[1][0])  # blink frame 7

    def test_applyseq_2_holds_the_mouth_closed_but_the_eyes_keep_blinking(self):
        animator = PortraitAnimator(sequence=1)
        animator.apply(2)

        self.assertEqual(animator.mouth_frame, 1)
        animator.advance(25 * 50)
        self.assertEqual(animator.mouth_frame, 1)  # still held closed
        self.assertEqual(animator.eye_frame, EYE_SEQUENCE[1][0])  # blinking is unaffected by animseq


class DietrichPortraitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.binary = Path(self.temporary.name) / "FILE/BINARY"
        self.binary.mkdir(parents=True)
        palette = bytearray(256 * 4)
        for index in range(256):
            palette[index * 4:index * 4 + 4] = bytes((index, index, (index + 1) % 256, (index + 2) % 256))
        (self.binary / "STANDARD.PAL").write_bytes(palette)

    def tearDown(self):
        self.temporary.cleanup()

    def _write_sheet(self, name, frames):
        fol, bop = bytearray(), bytearray()
        for pixels in frames:
            offset = len(bop)
            fol += struct.pack("<hhhhIB", 0, 0, 2, 2, offset, 1) + b"\0\0\0"
            bop += bytes(pixels)
        (self.binary / f"{name}.FOL").write_bytes(fol)
        (self.binary / f"{name}.BOP").write_bytes(bop)

    def test_given_scribe_and_background_frames_then_the_scribe_overlays_nonzero_pixels(self):
        self._write_sheet("BACKALL", [(1, 1, 1, 1)] * 15 + [(2, 3, 4, 5)])
        self._write_sheet("SCRI", [(0, 9, 0, 10)])

        width, height, rgba = dietrich_portrait(self.temporary.name)

        self.assertEqual((width, height), (2, 2))
        self.assertEqual(rgba, bytes((2, 3, 4, 255, 9, 10, 11, 255,
                                     4, 5, 6, 255, 10, 11, 12, 255)))

    def test_unknown_glue_portrait_index_is_not_silently_rendered_as_dietrich(self):
        with self.assertRaisesRegex(ValueError, "no verified portrait"):
            speaker_portrait(self.temporary.name, 99, 0)


if __name__ == "__main__":
    unittest.main()
