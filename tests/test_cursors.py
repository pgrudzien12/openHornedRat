"""GameCursors: loading Win32 RT_GROUP_CURSOR resources by name (WHSHR.EXE) or numeric id
(GMCUR.DLL), notes/troop_selection.md Section 2 and notes/pe_resources.md."""

import struct
import sys
import unittest
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whshr.frontend.cursors import GameCursors  # noqa: E402

Resource = namedtuple("Resource", "type name")


def _group_bytes(member_id, count=1):
    data = bytearray(20)
    struct.pack_into("<H", data, 4, count)
    struct.pack_into("<H", data, 18, member_id)
    return bytes(data)


class FakeImage:
    def __init__(self, resources, data_by_key):
        self._resources = resources
        self._data = data_by_key

    def resources(self):
        return self._resources

    def data(self, resource):
        return self._data[resource]


class GameCursorsTests(unittest.TestCase):
    def _installation(self):
        return SimpleNamespace(require=lambda name: f"/fake/{name}")

    def _patch_pe(self, image):
        fake_module = SimpleNamespace(PE=lambda path: image)
        return patch("whshr.frontend.cursors.module", return_value=fake_module)

    def test_given_a_numeric_key_then_the_matching_numbered_group_is_selected(self):
        member = 42
        group_100 = Resource(12, 100)
        group_101 = Resource(12, 101)
        cursor = Resource(1, member)
        resources = [group_100, group_101, cursor]
        data = {group_100: _group_bytes(9999), group_101: _group_bytes(member), cursor: b"decoded"}
        cursors = GameCursors(self._installation(), dll="GMCUR.DLL")

        with self._patch_pe(FakeImage(resources, data)):
            with patch("whshr.frontend.cursors._cursor_from_dib", return_value="CURSOR-101") as decode, \
                patch("whshr.frontend.cursors.pygame.mouse.set_cursor", Mock()):
                cursors.set(101)

        decode.assert_called_once_with(b"decoded")

    def test_given_a_string_key_then_the_matching_named_group_is_case_insensitive(self):
        member = 7
        group_sword = Resource(12, "SWORDCURSOR")
        group_staff = Resource(12, "STAFFCURSOR")
        cursor = Resource(1, member)
        resources = [group_sword, group_staff, cursor]
        data = {group_sword: _group_bytes(member), group_staff: _group_bytes(9999), cursor: b"decoded"}
        cursors = GameCursors(self._installation(), dll="WHSHR.EXE")

        with self._patch_pe(FakeImage(resources, data)):
            with patch("whshr.frontend.cursors._cursor_from_dib", return_value="CURSOR-SWORD") as decode, \
                patch("whshr.frontend.cursors.pygame.mouse.set_cursor", Mock()):
                cursors.set("swordcursor")

        decode.assert_called_once_with(b"decoded")

    def test_given_a_load_failure_then_it_is_cached_and_never_retried(self):
        cursors = GameCursors(self._installation(), dll="GMCUR.DLL")
        with self._patch_pe(FakeImage([], {})) as module_patch:
            cursors.set(999)
            cursors.set(999)

        self.assertEqual(module_patch.call_count, 1)  # the PE image is parsed once and then cached
        self.assertIs(cursors._cursors[999], False)


if __name__ == "__main__":
    unittest.main()
