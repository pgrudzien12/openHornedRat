# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The OK-only error box on a plain dark screen (same look as the Yes/No confirmation box).

PROVISIONAL: the original uses an operating-system message box; the panel is the engine's own.
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..message_scene import MessageScene
from ..scenes import SceneEvent
from .confirm_view import BLACK, BUTTON_SIZE, MARGIN, PALETTE_INDEX, PANEL_ORIGIN, PANEL_SIZE, WHITE, YELLOW, wrap
from .dialog_view import DialogView
from .gpu import Gpu

OK_LABEL = "OK"
BUTTON_X, BUTTON_Y = PANEL_ORIGIN[0] + (PANEL_SIZE[0] - BUTTON_SIZE[0]) // 2, PANEL_ORIGIN[1] + PANEL_SIZE[1] - 34


class MessageView(DialogView[MessageScene]):
    def __init__(self, gpu: Gpu, scene: MessageScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, scene.glue_content(), scene.font(2), PALETTE_INDEX, options)
        self.pressed = False
        self.refresh()

    def refresh(self) -> None:
        self._release_contents()
        px, py = PANEL_ORIGIN
        panel = pygame.Surface(PANEL_SIZE)
        panel.fill((16, 16, 24))
        pygame.draw.rect(panel, (200, 200, 200), panel.get_rect(), 2)
        self._append(panel, PANEL_ORIGIN)
        height = self.font.font.height
        self._center(self.scene.caption, py + 8, YELLOW, x=px, width=PANEL_SIZE[0])
        for index, line in enumerate(wrap(self.font, self.scene.text, PANEL_SIZE[0] - 2 * MARGIN)[:3]):
            self._center(line, py + 8 + (2 + index) * height, WHITE, x=px, width=PANEL_SIZE[0])
        self._bitmap("LoadSaveBtn0" + ("Dn" if self.pressed else "Up"), (BUTTON_X, BUTTON_Y))
        self._center(OK_LABEL, BUTTON_Y + (BUTTON_SIZE[1] - height) // 2, BLACK, x=BUTTON_X, width=BUTTON_SIZE[0])
        self.buttons.append((pygame.Rect(BUTTON_X, BUTTON_Y, *BUTTON_SIZE), "ok"))

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.KEYDOWN:
            return ("ok",) if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE) else ()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._action_at(event.pos) == "ok"
            self.refresh()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was, self.pressed = self.pressed, False
            self.refresh()
            if was and self._action_at(event.pos) == "ok":
                return ("ok",)
        return ()
