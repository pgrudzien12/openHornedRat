# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The New Game name prompt over the main menu (notes/native-windows.md §7.3.2-§7.3.3).

The layout is the documented front-end constants below, not WND.DLL data (the prompt is native in the
original): a 296 x 52 ``NameScroll`` panel at (172, 214), caption at (16, 10), edit box at (18, 28).
Only the keyboard drives it: Enter is OK, Esc is Cancel.
"""

from collections.abc import Sequence
from typing import Any

import pygame

from ..glue_palette import AppPalette
from ..name_prompt_scene import NamePromptScene
from ..new_game import PROMPT_CAPTION
from ..scenes import SceneEvent
from .dialog_view import DialogView
from .gpu import Gpu

BACKDROP, ART = "OptionScreen", "NameScroll"
PANEL_ORIGIN, CAPTION_OFFSET, EDIT_OFFSET, EDIT_SIZE = (172, 214), (16, 10), (18, 28), (260, 12)
BLACK = (0, 0, 0)


class NamePromptView(DialogView[NamePromptScene]):
    def __init__(self, gpu: Gpu, scene: NamePromptScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, scene.glue_content(), scene.font(2), 0, options)
        # The backdrop's own colour table is the palette of the menu and of the panel drawn over it (§7.5).
        self.palette = AppPalette.select(-1, self.content.palette_tables(),
                                         embedded=self.content.bitmap_data(BACKDROP).palette)
        self.state: tuple[Any, ...] | None = None
        self.refresh()

    def refresh(self) -> None:
        scene = self.scene
        state = (scene.text, scene.selected)
        if state == self.state:
            return
        self.state = state
        self._release_contents()
        px, py = PANEL_ORIGIN
        self._bitmap(BACKDROP, (0, 0))
        self._bitmap(ART, PANEL_ORIGIN)
        label = self.gpu.text((EDIT_SIZE[0], self.font.font.height), self.font, color=BLACK, background=None,
                              padding=0, align="left", fixed_width=True)
        label.set_lines((PROMPT_CAPTION,))
        self.labels.append((label, (px + CAPTION_OFFSET[0], py + CAPTION_OFFSET[1])))
        text = self.gpu.text(EDIT_SIZE, self.font, color=BLACK, background=None, padding=0, align="left",
                             fixed_width=True)
        text.set_lines((scene.text + ("" if scene.selected else "_"),))
        self.labels.append((text, (px + EDIT_OFFSET[0], py + EDIT_OFFSET[1])))

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type != pygame.KEYDOWN:
            return ()
        if event.key == pygame.K_ESCAPE:
            return ("cancel",)
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return ("ok",)
        if event.key == pygame.K_BACKSPACE:
            return ("edit:backspace",)
        return (f"text:{event.unicode}",) if event.unicode else ()

    def draw(self) -> None:
        self.refresh()  # the scene changed the text since the last frame
        super().draw()

    def status(self) -> Sequence[str]:
        return ("new game: commander name",)
