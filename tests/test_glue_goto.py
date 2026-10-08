"""The deferred ``goto`` (notes/glue_interpreter.md 2.2, 2.3, 4.2 and quirk 3 of section 10)."""

import unittest

from whshr.glue_content import GlueContent
from whshr.glue_runtime import Diagnostic, EndGame, GlueRuntime, MissionSelectRequested, OpenWindow, PlayMusic
from whshr.glue_state import decode_state, encode_state

WINDOW = "[WINDOW]\n[POSITION]\nset:palindex=2\n[END]\n[END]"
RESOURCES = {
    "MAIN": WINDOW,
    "TARGET": "[RUN]\n[START]\nendgame:\n[END]",
}


def run(program: str, **extra: str):
    runtime = GlueRuntime(GlueContent.from_data(resources={**RESOURCES, "P": program, **extra}))
    return runtime, runtime.start("P")


class DeferredGotoTests(unittest.TestCase):
    def test_goto_as_the_last_statement_runs_the_target_when_the_script_ends(self):
        runtime, effects = run("[RUN]\n[START]\ngoto:TARGET\n[END]")

        self.assertIn(EndGame(), effects)
        self.assertEqual(runtime.state.pending_goto, "")

    def test_goto_does_not_stop_the_run_so_later_lines_still_execute_first(self):
        _, effects = run("[RUN]\n[START]\ngoto:TARGET\nplaymidi:TUNE\n[END]")

        self.assertLess(effects.index(PlayMusic("TUNE")), effects.index(EndGame()))

    def test_a_later_window_load_clears_the_pending_goto(self):
        runtime, effects = run("[RUN]\n[START]\ngoto:TARGET\nopenwindow:res=MAIN\n[END]")

        self.assertTrue(any(isinstance(effect, OpenWindow) for effect in effects))
        self.assertNotIn(EndGame(), effects)
        self.assertEqual(runtime.state.pending_goto, "")

    def test_a_later_gosub_clears_the_pending_goto(self):
        _, effects = run("[RUN]\n[START]\ngoto:TARGET\ngosub:SUB\n[END]", SUB="[RUN]\n[START]\nreturn:\n[END]")

        self.assertNotIn(EndGame(), effects)

    def test_a_gosub_to_a_missing_script_does_not_clear_the_pending_goto(self):
        _, effects = run("[RUN]\n[START]\ngoto:TARGET\ngosub:NOWHERE\n[END]")

        self.assertTrue(any(isinstance(effect, Diagnostic) for effect in effects))
        self.assertIn(EndGame(), effects)

    def test_a_load_that_fails_changes_nothing(self):
        _, effects = run("[RUN]\n[START]\ngoto:TARGET\nopenwindow:res=MISSING\n[END]")

        self.assertIn(EndGame(), effects)

    def test_the_goto_wins_over_gomissionselect(self):
        _, effects = run("[RUN]\n[START]\ngomissionselect:\ngoto:TARGET\n[END]")

        self.assertIn(EndGame(), effects)
        self.assertNotIn(MissionSelectRequested(), effects)

    def test_a_window_load_also_clears_gomissionselect(self):
        _, effects = run("[RUN]\n[START]\ngomissionselect:\nopenwindow:res=MAIN\n[END]")

        self.assertNotIn(MissionSelectRequested(), effects)

    def test_conditional_gotos_are_still_reported_unsupported_and_never_jump(self):
        for command, set_bit in (("iftruegoto", "setgluestatus:\n"), ("iffalsegoto", "")):
            with self.subTest(command=command):
                _, effects = run(f"[RUN]\n[START]\nsetgluestatusmask:1\n{set_bit}{command}:TARGET\n[END]")
                self.assertNotIn(EndGame(), effects)
                self.assertTrue(any(isinstance(effect, Diagnostic) for effect in effects))

    def test_a_pending_goto_survives_a_save(self):
        runtime, _ = run("[RUN]\n[START]\ngoto:TARGET\nwaitforresume:\n[END]")
        self.assertEqual(runtime.state.pending_goto, "TARGET")

        restored = decode_state(encode_state(runtime.state))

        self.assertEqual(restored.pending_goto, "TARGET")


if __name__ == "__main__":
    unittest.main()
