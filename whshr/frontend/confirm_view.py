# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The Yes/No confirmation box on a plain dark screen.

The panel geometry and the button art (the Load/Save dialog's 116 x 20 button) are front-end constants
of this native box, not WND.DLL data; the question text is read from the installation's string tables.
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..confirm_scene import NO_LABEL, TITLE, YES_LABEL, ConfirmScene
from ..scenes import SceneEvent
from .dialog_view import DialogView
from .gpu import Gpu

PALETTE_INDEX = 2
PANEL_SIZE = (360, 120)
PANEL_ORIGIN = ((640 - PANEL_SIZE[0]) // 2, (480 - PANEL_SIZE[1]) // 2)
BUTTON_SIZE, BUTTON_Y = (116, 20), PANEL_ORIGIN[1] + PANEL_SIZE[1] - 34
BUTTONS = (("yes", YES_LABEL, PANEL_ORIGIN[0] + 40), ("no", NO_LABEL, PANEL_ORIGIN[0] + PANEL_SIZE[0] - 40 - 116))
YELLOW, WHITE = (255, 255, 0), (255, 255, 255)
MARGIN = 20


def wrap(font: Any, text: str, width: int) -> list[str]:
    """Greedy word wrap of ``text`` to ``width`` pixels."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.size(candidate)[0] > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current] if current else lines


class ConfirmView(DialogView[ConfirmScene]):
    def __init__(self, gpu: Gpu, scene: ConfirmScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, scene.glue_content(), scene.font(2), PALETTE_INDEX, options)
        self.pressed: str | None = None
        self.refresh()

    def refresh(self) -> None:
        self._release_contents()
        px, py = PANEL_ORIGIN
        panel = pygame.Surface(PANEL_SIZE)
        panel.fill((16, 16, 24))
        pygame.draw.rect(panel, (200, 200, 200), panel.get_rect(), 2)
        self._append(panel, PANEL_ORIGIN)
        height = self.font.font.height
        self._center(TITLE, py + 8, YELLOW, x=px, width=PANEL_SIZE[0])
        for index, line in enumerate(wrap(self.font, self.scene.question, PANEL_SIZE[0] - 2 * MARGIN)):
            self._center(line, py + 8 + (2 + index) * height, WHITE, x=px, width=PANEL_SIZE[0])
        for action, label, x in BUTTONS:
            pressed = self.pressed == action
            self._bitmap("LoadSaveBtn0" + ("Dn" if pressed else "Up"), (x, BUTTON_Y))
            offset = 1 if pressed else 0
            self._center(label, BUTTON_Y + (BUTTON_SIZE[1] - height) // 2 + offset, YELLOW,
                         x=x + offset, width=BUTTON_SIZE[0])
            self.buttons.append((pygame.Rect(x, BUTTON_Y, *BUTTON_SIZE), action))

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.KEYDOWN:
            return {pygame.K_y: ("yes",), pygame.K_RETURN: ("yes",), pygame.K_KP_ENTER: ("yes",),
                    pygame.K_n: ("no",), pygame.K_ESCAPE: ("no",)}.get(event.key, ())
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._action_at(event.pos)
            self.refresh()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            action, self.pressed = self.pressed, None
            self.refresh()
            if action and action == self._action_at(event.pos):
                return (action,)
        return ()
