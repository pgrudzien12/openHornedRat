# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The Load / Save dialog: native geometry of notes/builtin_widgets.md section 6.

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
PROMPT_ORIGIN, PROMPT_SIZE = (172, 214), (296, 58)  # the edit box, over the dialog
BLACK, DISABLED = (0, 0, 0), (127, 127, 127)  # text on the tan slot and button art
YELLOW, WHITE, RED = (255, 255, 0), (255, 255, 255), (255, 96, 96)  # text on the dark prompt panel and errors
OK_LABEL, CANCEL_LABEL = 163, 164  # GMTXT "OK" / "CANCEL"


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
        state = (scene.mode, tuple(scene.slots.items()), scene.selected, scene.editing, scene.text, scene.error,
                 self.pressed)
        if state == self.state:
            return
        self.state = state
        self._release_contents()
        ox, oy = self.origin
        self._bitmap(BACKDROP, (0, 0))
        self._bitmap(DIALOG_ART[scene.mode], (ox, oy))
        for slot in scene.visible_slots:
            self._slot(slot, ox, oy)
        y = oy + BUTTON_Y[scene.mode]
        self._button("ok", ox + OK_X, y, OK_LABEL, scene.ok_enabled)
        self._button("cancel", ox + CANCEL_X, y, CANCEL_LABEL, True)
        if scene.error:
            self._center(scene.error, oy + DIALOG_HEIGHT[scene.mode] + 8, RED, x=0, width=640)
        if scene.editing:
            self._prompt()

    def _slot(self, slot: int, ox: int, oy: int) -> None:
        y = oy + (AUTOSAVE_Y if slot == AUTOSAVE_SLOT else SLOT_Y + SLOT_PITCH * slot)
        selected = self.scene.selected == slot
        self._bitmap("LoadSaveBtn1" + ("Dn" if selected else "Up"), (ox + SLOT_X, y))
        rect = pygame.Rect(ox + SLOT_X, y, *SLOT_SIZE)
        # Text is drawn above every picture, so a label under the prompt panel would show through it.
        if self.scene.editing and rect.colliderect(pygame.Rect(PROMPT_ORIGIN, PROMPT_SIZE)):
            return
        info = self.scene.slots[slot]
        label = info.description if info else EMPTY_SLOT_LABEL
        self._center(label, y + (SLOT_SIZE[1] - self.font.font.height) // 2, BLACK,
                     x=ox + SLOT_X, width=SLOT_SIZE[0])
        if not self.scene.editing:
            self.buttons.append((rect, f"slot:{slot}"))

    def _button(self, action: str, x: int, y: int, label_id: int, enabled: bool) -> None:
        pressed = enabled and self.pressed == action
        self._bitmap("LoadSaveBtn0" + ("Dn" if pressed else "Up"), (x, y))
        try:
            label = self.content.string("GMTXT", label_id)
        except KeyError:
            label = action.upper()
        offset = 1 if pressed else 0
        self._center(label, y + (BUTTON_SIZE[1] - self.font.font.height) // 2 + offset,
                     BLACK if enabled else DISABLED, x=x + offset, width=BUTTON_SIZE[0])
        if enabled:
            self.buttons.append((pygame.Rect(x, y, *BUTTON_SIZE), action))

    def _prompt(self) -> None:
        """The modal one-line description box (25 characters max)."""
        px, py = PROMPT_ORIGIN
        panel = pygame.Surface(PROMPT_SIZE)
        panel.fill((16, 16, 24))
        pygame.draw.rect(panel, (200, 200, 200), panel.get_rect(), 2)
        self._append(panel, (px, py))
        self._center(PROMPT_CAPTION, py + 8, YELLOW, x=px, width=PROMPT_SIZE[0])
        self._center(self.scene.text + "_", py + 8 + 2 * self.font.font.height, WHITE, x=px, width=PROMPT_SIZE[0])

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
