import os
import re
import unittest
from pathlib import Path

from whshr.campaign import load_wnd_rcdata
from whshr.glue import parse_glue_resource, parse_glue_resources
from whshr.glue_spec import COMMAND_SPEC, DELEGATED, SPECIFIED, format_report, specification_report

NOTE = Path(__file__).resolve().parents[1] / "notes" / "glue_interpreter.md"


def _cited_sections(text):
    return [part.strip() for part in re.split(r"[,;]", text.replace("§", "")) if part.strip()]


class GlueSpecificationTests(unittest.TestCase):
    def test_given_a_script_using_specified_and_unknown_commands_when_reported_then_each_is_classified_with_counts(self):
        resources = {
            "A": parse_glue_resource("A", "[RUN]\n[START]\ngosub:X\ngosub:Y\nset:animseq=2\nmystery:1\n[END]\n[END]"),
            "B": parse_glue_resource("B", "[RUN]\n[START]\ngosub:X\naddtroop:3=1\n[END]\n[END]"),
        }

        report = specification_report(resources)
        rows = {row["command"]: row for row in report["commands"]}

        self.assertEqual((rows["gosub"]["statements"], rows["gosub"]["scripts"], rows["gosub"]["level"]),
                         (3, 2, SPECIFIED))
        self.assertEqual(rows["set:animseq"]["level"], SPECIFIED)
        self.assertEqual(rows["addtroop"]["level"], DELEGATED)
        self.assertEqual(rows["mystery"]["level"], "unspecified")
        self.assertEqual(report["unspecified"], ["mystery"])
        self.assertIn("UNSPECIFIED: mystery", format_report(report))

    def test_given_window_resources_when_reported_then_only_script_commands_are_counted(self):
        resources = {"W": parse_glue_resource("W", "[WINDOW]\n[BITMAP]\nsetbitmap:Map\n[END]\n[END]")}

        self.assertEqual(specification_report(resources)["commands"], [])

    def test_given_the_registry_then_every_cited_section_exists_as_a_heading_or_a_numbered_item_in_the_note(self):
        text = NOTE.read_text(encoding="utf-8")
        headings = {match.group(1) for match in re.finditer(r"(?m)^#{2,3} (\d+(?:\.\d+)?)[ .]", text)}

        missing = sorted({(name, section)
                          for name, spec in COMMAND_SPEC.items()
                          for section in _cited_sections(spec.section)
                          if section not in headings})

        self.assertEqual(missing, [])

    def test_given_the_registry_then_delegated_entries_name_the_note_that_owns_the_detail(self):
        for name, spec in COMMAND_SPEC.items():
            if spec.level == DELEGATED:
                self.assertRegex(spec.open_question, r"notes/\w+\.md", name)

    @unittest.skipUnless(os.environ.get("WHSHR_INSTALLATION"),
                         "set WHSHR_INSTALLATION for the original-install regression")
    def test_given_the_original_installation_when_reported_then_no_used_command_is_unspecified(self):
        wnd = Path(os.environ["WHSHR_INSTALLATION"]) / "FILE/DLL/WND.DLL"

        report = specification_report(parse_glue_resources(load_wnd_rcdata(wnd)))

        self.assertEqual(report["unspecified"], [])
        self.assertGreater(len(report["commands"]), 50)


if __name__ == "__main__":
    unittest.main()
