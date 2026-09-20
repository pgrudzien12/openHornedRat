import unittest
import os
from pathlib import Path

from whshr.campaign import load_wnd_rcdata
from whshr.glue import (
    BitmapRecord,
    GlueProgram,
    HotspotRecord,
    MissionRecord,
    MissionRef,
    UnknownField,
    WindowDefinition,
    coverage_report,
    diagnostic_text,
    parse_glue_resource,
    parse_glue_resources,
    validate_program,
)


class GlueImporterTests(unittest.TestCase):
    def test_given_a_run_resource_when_imported_then_commands_keep_order_duplicates_and_locations(self):
        resource = parse_glue_resource("Flow", """[RUN]
            set:tentpos=0
            playmidi:sighted
            playmidi:sighted ; deliberately repeated
        [END]
        """)

        self.assertIsInstance(resource, GlueProgram)
        self.assertEqual(resource.name, "FLOW")
        self.assertEqual(resource.block_type, "RUN")
        self.assertEqual(
            [(item.command, item.argument, item.location.resource, item.location.line)
             for item in resource.instructions],
            [
                ("set", "tentpos=0", "FLOW", 2),
                ("playmidi", "sighted", "FLOW", 3),
                ("playmidi", "sighted", "FLOW", 4),
            ],
        )

    def test_given_a_window_resource_when_imported_then_records_are_typed_and_source_order_is_retained(self):
        resource = parse_glue_resource("MissionTestWindow", """[WINDOW]
            [BITMAP]
                setbitmap:Map
                set:x=4
            [END]
            [MISSION]
                set:res=601
                res:BriefOne
            [END]
            [BITMAP]
                setbitmap:Overlay
            [END]
            [HOTSPOT]
                set:x=1
                res:NextWindow
            [END]
        [END]
        """)

        self.assertIsInstance(resource, WindowDefinition)
        self.assertEqual([type(record) for record in resource.records],
                         [BitmapRecord, MissionRecord, BitmapRecord, HotspotRecord])
        self.assertEqual(resource.records[0].values["setbitmap"], "Map")
        self.assertEqual(resource.records[1].mission_ref, MissionRef("MISSIONTESTWINDOW", 0))
        self.assertEqual(resource.records[2].values["setbitmap"], "Overlay")
        self.assertEqual(diagnostic_text(resource).splitlines()[1:4],
                         ["  [BITMAP]", "    setbitmap:Map", "    set:x=4"])

    def test_given_duplicate_and_unrecognized_fields_then_the_lossless_record_keeps_them(self):
        resource = parse_glue_resource("Picture", """[WINDOW]
            [BITMAP]
                set:x=1
                set:x=2
                mystery:value
            [END]
        [END]
        """)

        bitmap = resource.records[0]
        self.assertEqual([(field.command, field.argument) for field in bitmap.fields],
                         [("set", "x=1"), ("set", "x=2"), ("mystery", "value")])
        self.assertEqual(bitmap.values["x"], 2)
        self.assertEqual(bitmap.unknown_fields, (
            UnknownField("mystery", "value", bitmap.fields[2].location),
        ))

    def test_given_resources_in_different_mapping_order_then_coverage_output_is_deterministic(self):
        texts = {
            "B": "[RUN]\nplaymovie:A1\nodd:thing\n[END]",
            "A": "[WINDOW]\n[BITMAP]\nsetbitmap:Map\n[END]\n[END]",
        }

        first = coverage_report(parse_glue_resources(texts))
        second = coverage_report(parse_glue_resources(dict(reversed(tuple(texts.items())))))

        self.assertEqual(first, second)
        self.assertEqual(first["resources"], 2)
        self.assertEqual(first["blocks"], {"BITMAP": 1, "RUN": 1, "WINDOW": 1})
        self.assertEqual(first["commands"]["RUN"]["odd"], {"count": 1, "status": "unknown"})
        self.assertEqual(first["commands"]["RUN"]["playmovie"],
                         {"count": 1, "status": "known_external"})

    def test_given_an_unknown_reachable_command_when_program_is_validated_then_its_source_is_reported(self):
        program = parse_glue_resource("BrokenFlow", "[RUN]\nodd:thing\n[END]")

        with self.assertRaisesRegex(ValueError, "BROKENFLOW:2: unsupported glue command 'odd'"):
            validate_program(program)

    @unittest.skipUnless(os.environ.get("WHSHR_INSTALLATION"),
                         "set WHSHR_INSTALLATION for the original-install regression")
    def test_given_the_original_installation_when_all_glue_is_imported_then_inventory_is_complete(self):
        wnd = Path(os.environ["WHSHR_INSTALLATION"]) / "FILE/DLL/WND.DLL"

        resources = parse_glue_resources(load_wnd_rcdata(wnd))
        report = coverage_report(resources)
        unknown = [(group, block, key)
                   for group in ("commands", "fields")
                   for block, entries in report[group].items()
                   for key, details in entries.items()
                   if details["status"] == "unknown"]

        self.assertEqual(len(resources), 535)
        self.assertEqual(unknown, [])


if __name__ == "__main__":
    unittest.main()
