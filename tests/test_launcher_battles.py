import tempfile
import unittest
from pathlib import Path

from whshr.launcher.battles import list_battles
from whshr.paths import Installation


class BattlesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "FILE" / "SCRIPT").mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, name, text):
        (self.root / "FILE" / "SCRIPT" / name).write_text(text, encoding="latin-1")

    def test_given_battle_and_plot_scripts_when_listed_then_only_the_battle_is_returned(self):
        self._write("BF001.BTS", "[BATTLESCRIPT]\n[FIELD]\nloadScript:BF001\nset:map=MAP001\n[END]\n[END]\n")
        self._write("PLOT1.BTS", "[BATTLESCRIPT]\n[FIELD]\n[END]\n[END]\n")

        battles = list_battles(Installation(self.root))

        self.assertEqual([b.id for b in battles], ["BF001"])
        self.assertEqual(battles[0].map, "MAP001")
