# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The Load / Save dialog: native geometry of notes/native-windows.md section 8.

The glue window ``Map`` supplies the backdrop; the dialog is a 252 x H child at x = 194 (H = 212 for
Save, 254 for Load). The dialog's layout and art names are the documented front-end constants below,
not WND.DLL data (the dialog is native in the original).
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..load_save_scene import EMPTY_SLOT_LABEL, PROMPT_CAPTION, LoadSaveScene
from ..savegame import AUTOSAVE_SLOT
from ..scenes import SceneEvent
from .dialog_view import DialogView, Point
from .gpu import Gpu

BACKDROP, PALETTE_INDEX = "Map", 2
DIALOG_X, DIALOG_HEIGHT = 194, {"save": 212, "load": 254}
DIALOG_ART = {"save": "LoadSaveWindow", "load": "LoadSaveWindow2"}
SLOT_SIZE, SLOT_X, SLOT_Y, SLOT_PITCH, AUTOSAVE_Y = (232, 36), 8, 8, 36, 194
BUTTON_SIZE, BUTTON_Y = (116, 20), {"save": 188, "load": 230}
OK_X, CANCEL_X = 8, 124
# Section 8.3.6: the prompt is the New Game name prompt's widget over the plain backdrop (dialog hidden).
PROMPT_ART, PROMPT_ORIGIN, CAPTION_OFFSET, EDIT_OFFSET, EDIT_SIZE = "EditScroll", (172, 214), (16, 10), (18, 28), (260, 12)
# Section 8.3.4: slot button content. Tent icon at (6, 6) of the slot; label centred in a 207 px field
# starting at x + 24, vertically as y + 1 + (30 - text height) / 2.
TENT_ART, TENT_OFFSET = "LoadSaveTent{}", (6, 6)
LABEL_X, LABEL_WIDTH, LABEL_Y, LABEL_CELL = 24, 207, 1, 30
# Text colour is palette index 206 (near-black in palette pair 2); a disabled control is olive RGB.
TEXT_INDEX, DISABLED = 206, (127, 127, 0)
RED = (255, 96, 96)  # engine error line (no save directory)
BLACK = (0, 0, 0)  # fallback when the palette has no entry 206


class LoadSaveView(DialogView[LoadSaveScene]):
    def __init__(self, gpu: Gpu, scene: LoadSaveScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, scene.glue_content(), scene.font(2), PALETTE_INDEX, options)
        self.pressed: str | None = None
        self.state: tuple[Any, ...] | None = None
        self.refresh()

    # -- layout -------------------------------------------------------------------------------

    @property
    def origin(self) -> Point:
        return DIALOG_X, (480 - DIALOG_HEIGHT[self.scene.mode]) // 2

    def refresh(self) -> None:
        scene = self.scene
        state = (scene.mode, tuple(scene.slots.items()), scene.selected, scene.editing, scene.text, scene.text_selected, scene.error,
                 self.pressed)
        if state == self.state:
            return
        self.state = state
        self._release_contents()
        ox, oy = self.origin
        self._bitmap(BACKDROP, (0, 0))
        if scene.editing:  # section 8.3.6: only the backdrop remains under the prompt
            self._prompt()
            return
        self._bitmap(DIALOG_ART[scene.mode], (ox, oy))
        for slot in scene.visible_slots:
            self._slot(slot, ox, oy)
        y = oy + BUTTON_Y[scene.mode]
        self._button("ok", ox + OK_X, y, scene.ok_label, scene.ok_enabled)
        self._button("cancel", ox + CANCEL_X, y, scene.cancel_label, True)
        if scene.error:
            self._center(scene.error, oy + DIALOG_HEIGHT[scene.mode] + 8, RED, x=0, width=640)

    @property
    def text_colour(self) -> tuple[int, int, int]:
        colours = self.palette.colours
        return colours[TEXT_INDEX] if len(colours) > TEXT_INDEX else BLACK

    def _slot(self, slot: int, ox: int, oy: int) -> None:
        y = oy + (AUTOSAVE_Y if slot == AUTOSAVE_SLOT else SLOT_Y + SLOT_PITCH * slot)
        selected = self.scene.selected == slot
        self._bitmap("LoadSaveBtn1" + ("Dn" if selected else "Up"), (ox + SLOT_X, y))
        rect = pygame.Rect(ox + SLOT_X, y, *SLOT_SIZE)
        self._bitmap(TENT_ART.format(slot + 1), (rect.x + TENT_OFFSET[0], y + TENT_OFFSET[1]))
        info = self.scene.slots[slot]
        label = info.description if info else EMPTY_SLOT_LABEL
        self._center(label, y + LABEL_Y + (LABEL_CELL - self.font.font.height) // 2, self.text_colour,
                     x=rect.x + LABEL_X, width=LABEL_WIDTH)
        self.buttons.append((rect, f"slot:{slot}"))

    def _button(self, action: str, x: int, y: int, label: str, enabled: bool) -> None:
        pressed = enabled and self.pressed == action
        self._bitmap("LoadSaveBtn0" + ("Dn" if pressed else "Up"), (x, y))
        # Section 8.3.4: centred in the art, no press offset.
        self._center(label, y + (BUTTON_SIZE[1] - self.font.font.height) // 2,
                     self.text_colour if enabled else DISABLED, x=x, width=BUTTON_SIZE[0])
        if enabled:
            self.buttons.append((pygame.Rect(x, y, *BUTTON_SIZE), action))

    def _prompt(self) -> None:
        """The modal one-line description box (24 characters max) on the `EditScroll` panel."""
        px, py = PROMPT_ORIGIN
        self._bitmap(PROMPT_ART, PROMPT_ORIGIN)
        for text, offset, size in ((PROMPT_CAPTION, CAPTION_OFFSET, EDIT_SIZE),
                                   (self.scene.text + ("" if self.scene.text_selected else "_"), EDIT_OFFSET, EDIT_SIZE)):
            label = self.gpu.text(size, self.font, color=self.text_colour, background=None, padding=0,
                                  align="left", fixed_width=True)
            label.set_lines((text,))
            self.labels.append((label, (px + offset[0], py + offset[1])))

    # -- input --------------------------------------------------------------------------------

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return ("cancel",)
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return ("ok",)
            if self.scene.editing:
                if event.key == pygame.K_BACKSPACE:
                    return ("edit:backspace",)
                if event.unicode and event.unicode.isprintable():
                    return (f"text:{event.unicode}",)
            return ()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = self._action_at(event.pos)
            # No click cue anywhere in this dialog: its buttons are plain push buttons, not the shared native buttons
            # of §1.1, and the slot rows and the prompt are silent too (notes/native-windows.md §8.3).
            self.pressed = action if action in ("ok", "cancel") else None
            if action and action.startswith("slot:"):
                return (action,)
            self.refresh()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            action, self.pressed = self.pressed, None
            self.refresh()
            if action and action == self._action_at(event.pos):
                return (action,)
        return ()

    def status(self) -> Sequence[str]:
        return (f"{self.scene.mode} dialog, slot {self.scene.selected}",)
