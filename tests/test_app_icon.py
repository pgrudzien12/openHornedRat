"""The application icon ships in every size the desktops, the launcher window and the packages use."""

import struct
import unittest

from whshr.app_icon import ENGINE_WINDOW_ICON_SIZE, ICON_DIR, ICON_SIZES, WINDOW_ICON_SIZES, icon_path


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


class AppIconTests(unittest.TestCase):
    def test_given_the_package_then_every_icon_size_is_a_square_png_of_that_size(self):
        for size in ICON_SIZES:
            with self.subTest(size):
                self.assertEqual(png_size(icon_path(size).read_bytes()), (size, size))

    def test_given_the_windows_then_the_sizes_they_load_exist(self):
        self.assertLessEqual(set(WINDOW_ICON_SIZES) | {ENGINE_WINDOW_ICON_SIZE}, set(ICON_SIZES))

    def test_given_the_packages_then_the_windows_and_macos_icon_files_exist(self):
        self.assertEqual((ICON_DIR / "ohr.ico").read_bytes()[:4], b"\x00\x00\x01\x00")
        self.assertEqual((ICON_DIR / "ohr.icns").read_bytes()[:4], b"icns")


if __name__ == "__main__":
    unittest.main()
