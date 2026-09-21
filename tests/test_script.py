from pathlib import Path
import tempfile
import unittest

from whshr import script

SAMPLE = """[MERCARMY]
[UNITS]
; Mercenary Army
set:count=1
addunit:Grudgebringer<Cavalry
set:whoami=2
set:hired=1
setstats:s_side=2,12,12,4
setstats:s_pntval=13
hidden:
banner:BannerMrcCmdr,0
addleader:Cmdr._Bernhardt
setstats:s_move=4,4,5,4,4,2,4,2,9
leaderportrait:Commander,0
endleader:
endunit:
[END]
[END]
"""


def _strip(node):
    """A comparable, order-independent projection of one parse() node tree."""
    return {'kind': node['kind'], 'name': node['name'], 'label': node['label'], 'set': node['set'],
            'stats': node['stats'], 'cmds': node['cmds'], 'children': [_strip(c) for c in node['children']]}


class ScriptWriteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, name, text):
        path = self.root / name
        path.write_text(text)
        return path

    def test_given_a_parsed_tree_when_written_and_reparsed_then_it_matches_the_original(self):
        path = self._write("sample.MRC", SAMPLE)
        original = script.parse(str(path))

        written = script.write(original)
        roundtrip_path = self._write("roundtrip.MRC", written)
        reparsed = script.parse(str(roundtrip_path))

        self.assertEqual(_strip(original), _strip(reparsed))

    def test_given_a_section_with_a_blank_label_comment_then_it_is_preserved_not_dropped(self):
        path = self._write("blank_label.MRC", "[FIELD]\n;\nset:x=1\n[END]\n")
        original = script.parse(str(path))
        self.assertEqual(original["label"], "")

        roundtrip_path = self._write("blank_label_out.MRC", script.write(original))
        reparsed = script.parse(str(roundtrip_path))

        self.assertEqual(reparsed["label"], "")

    def test_given_a_written_unit_block_then_it_uses_the_documented_set_and_setstats_syntax(self):
        path = self._write("sample.MRC", SAMPLE)
        original = script.parse(str(path))

        text = script.write(original)

        self.assertIn("set:whoami=2", text)
        self.assertIn("setstats:s_pntval=13", text)
        self.assertIn("hidden:", text)
        self.assertIn("addleader:Cmdr._Bernhardt", text)
        self.assertIn("endleader:", text)
        self.assertIn("endunit:", text)


if __name__ == "__main__":
    unittest.main()
