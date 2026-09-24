import unittest
from unittest.mock import patch

from whshr import __main__


class GlueCliTests(unittest.TestCase):
    def test_engine_glue_program_is_forwarded_to_the_frontend_runner(self):
        with patch("whshr.frontend.app.run", return_value={"frames": 1, "ticks": 1, "scene": "GlueScene", "quit": None}) as run:
            result = __main__.main([
                "engine", "/tmp", "--glue-program", "FLOWSCRIPTBP01", "--hidden", "--frames", "1",
            ])

        self.assertEqual(result, 0)
        self.assertIn("FLOWSCRIPTBP01", run.call_args.args)

    def test_engine_rejects_battle_and_glue_program_together(self):
        with self.assertRaises(SystemExit):
            __main__.main(["engine", "/tmp", "--battle", "BF001", "--glue-program", "FLOW"])


if __name__ == "__main__":
    unittest.main()
