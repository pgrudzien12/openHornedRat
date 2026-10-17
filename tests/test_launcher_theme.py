"""The launcher's art-drawn buttons and scrollbar behave like ordinary Tk controls."""

import tkinter as tk
import unittest

from whshr.launcher.theme import ART_DIR, ArrowScrollbar, ImageButton, Theme

ART_NAMES = ("portrait", "header", "footer", "button_wide", "button_small", "scroll_up", "scroll_down")


def make_root() -> tk.Tk:
    try:
        root = tk.Tk()
    except tk.TclError as error:  # no display available
        raise unittest.SkipTest(f"the launcher widgets need a display: {error}") from error
    root.withdraw()
    return root


class LauncherArtTests(unittest.TestCase):
    def test_given_the_launcher_package_then_every_art_image_and_its_states_are_present(self):
        for name in ART_NAMES:
            self.assertTrue((ART_DIR / f"{name}.png").is_file(), name)
        for name in ("button_wide", "button_small", "scroll_up", "scroll_down"):
            for state in ("hover", "pressed"):
                self.assertTrue((ART_DIR / f"{name}_{state}.png").is_file(), f"{name}_{state}")


class ImageButtonTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.root.deiconify()
        self.theme = Theme(self.root)
        self.clicks: list[str] = []
        self.button = ImageButton(self.root, self.theme, "Start game", lambda: self.clicks.append("start"))
        self.button.pack()
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def click(self, release_inside: bool = True):
        self.button.event_generate("<ButtonPress-1>", x=5, y=5)
        release_x = 5 if release_inside else self.button.winfo_width() + 20
        self.button.event_generate("<ButtonRelease-1>", x=release_x, y=5)
        self.root.update()

    def test_given_an_enabled_button_when_clicked_then_its_command_runs_once(self):
        self.click()
        self.assertEqual(self.clicks, ["start"])

    def test_given_a_pressed_button_when_released_outside_then_nothing_runs(self):
        self.click(release_inside=False)
        self.assertEqual(self.clicks, [])

    def test_given_a_disabled_button_when_clicked_then_nothing_runs_until_it_is_enabled(self):
        self.button.set_enabled(False)
        self.click()
        self.assertEqual(self.clicks, [])
        self.button.set_enabled(True)
        self.click()
        self.assertEqual(self.clicks, ["start"])


class ArrowScrollbarTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        self.root.deiconify()
        theme = Theme(self.root)
        self.listbox = tk.Listbox(self.root, height=5)
        for index in range(50):
            self.listbox.insert("end", f"battle {index}")
        self.bar = ArrowScrollbar(self.root, theme, self.listbox.yview)
        self.listbox.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.listbox.pack(side="left")
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def press(self, y: int):
        self.bar.event_generate("<ButtonPress-1>", x=5, y=y)
        self.bar.event_generate("<ButtonRelease-1>", x=5, y=y)
        self.root.update()

    def test_given_a_long_list_when_the_down_arrow_is_clicked_then_the_list_scrolls_down_and_back_up(self):
        self.press(self.bar.winfo_height() - 3)
        self.assertEqual(self.listbox.nearest(0), 1)
        self.press(3)
        self.assertEqual(self.listbox.nearest(0), 0)


if __name__ == "__main__":
    unittest.main()
