"""The bestiary uses save keys but pages in its fixed display order."""

import unittest
from types import SimpleNamespace

from whshr.campaign_scenes import EncyclopediaScene
from whshr.encyclopedia import DEFAULT_KEYS, ENTRIES, known_positions
from whshr.glue_scene import GlueScene


class EncyclopediaTests(unittest.TestCase):
    def scene(self, flags=None, *, testbook=False):
        campaign = SimpleNamespace(book_flags={0: set(DEFAULT_KEYS if flags is None else flags)})
        parent = GlueScene(window="STARTCARAVAN", campaign=campaign)
        return EncyclopediaScene(parent, campaign, testbook=testbook)

    def test_defaults_and_new_unlock_follow_display_order(self):
        scene = self.scene()
        self.assertEqual(tuple(ENTRIES[pos][0] for pos in scene.known), (28, 6, 10, 0, 21))
        self.assertEqual((scene.entry, scene.page), (0, 0))
        self.assertFalse(scene.can_back)
        scene = self.scene(set(DEFAULT_KEYS) | {26})
        self.assertEqual(tuple(ENTRIES[pos][0] for pos in scene.known), (28, 6, 10, 26, 0, 21))

    def test_page_and_entry_navigation_remembers_offsets(self):
        scene = self.scene()
        scene.set_next_start(42)
        scene.handle("book:next", None)
        self.assertEqual((scene.entry, scene.page, scene.page_start), (0, 1, 42))
        scene.set_next_start(None)
        scene.handle("book:next", None)
        self.assertEqual((scene.entry, scene.page), (1, 0))
        scene.handle("book:back", None)
        self.assertEqual((scene.entry, scene.page, scene.page_start), (0, 0, 0))
        self.assertIs(scene.handle("book:done", None).scene, scene.parent)

    def test_testbook_sets_all_flags_but_never_displays_key_eleven(self):
        scene = self.scene(set(), testbook=True)
        self.assertEqual(scene.campaign.book_flags[0], set(range(29)))
        self.assertEqual(len(scene.known), 28)
        self.assertNotIn(11, (ENTRIES[pos][0] for pos in scene.known))
        self.assertEqual(known_positions({11}), ())


if __name__ == "__main__":
    unittest.main()
