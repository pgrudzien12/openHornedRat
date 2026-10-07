import io
import unittest
from contextlib import redirect_stderr

from whshr.frontend.app import FrameProfile


class FrameProfileTests(unittest.TestCase):
    def test_given_glue_frames_when_reported_then_the_summary_identifies_the_window_and_slow_phase(self):
        profile = FrameProfile("STARTCARAVAN")
        profile.add("update", 0.002)
        profile.add("refresh", 0.006)
        profile.add("frame", 0.010)
        output = io.StringIO()

        with redirect_stderr(output):
            profile.report()

        line = output.getvalue()
        self.assertIn("STARTCARAVAN", line)
        self.assertIn("refresh=6.00/6.00", line)
        self.assertIn("frame=10.00/10.00", line)


if __name__ == "__main__":
    unittest.main()
