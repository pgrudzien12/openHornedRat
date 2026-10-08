# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Main menu and mission briefing views."""

from collections.abc import Sequence
from typing import Any

import pygame

from ..campaign_scenes import BriefingScene, MainMenuScene
from ..scenes import SceneEvent
from .bitmap_font import BitmapFont
from .gpu import Gpu, ScreenQuad
from .glue_bitmap import load_bitmap
from ..glue_render import build_render_model
from ..glue_runtime import WindowInstance
from .scene_view import NativeScreenView, SceneView


def _wrap(font: BitmapFont, text: str, max_width: int) -> list[str]:
    """Split ``text`` into lines that each fit ``max_width`` pixels in ``font``."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class MainMenuView(NativeScreenView[MainMenuScene]):
    """The original OPTIONSCREEN menu, with its paired round button sprites."""

    # The engine handles the original menu's campaign, Load, Credits, Options and Exit actions.
    SHORTCUTS: dict[int, str] = {pygame.K_n: "new_campaign", pygame.K_RETURN: "new_campaign",
                 pygame.K_KP_ENTER: "new_campaign", pygame.K_l: "load_game", pygame.K_q: "quit", pygame.K_ESCAPE: "quit"}
    TARGET_ACTIONS: dict[str, str] = {"newgame": "new_campaign", "loadsavewindow2": "load_game",
                                      "exitprocess": "quit",
                                      "credits": "credits", "optionsdialog": "options"}

    def __init__(self, gpu: Gpu, scene: MainMenuScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        if scene.content is None:
            raise RuntimeError("the main menu scene has not been entered")
        self.model = build_render_model(scene.content, WindowInstance("MAINMENU", None, -1))
        self.screen = self._load_quad(gpu, self.model.bitmaps[0].name)
        self.hotspots = self.model.hotspots
        self.button_up = self._load_quad(gpu, self.hotspots[0].up_bitmap, transparent_blue=True)
        self.button_down = self._load_quad(gpu, self.hotspots[0].down_bitmap, transparent_blue=True)
        self.pressed: int | None = None

    def _load_quad(self, gpu: Gpu, resource_name: str | None, transparent_blue: bool = False) -> ScreenQuad:
        """Read a cached extractor PNG into a GPU texture.

        The two button resources use pure blue as a legacy chroma key rather
        than PNG alpha, so turn that colour transparent before upload.
        """
        if self.scene.content is None or resource_name is None:
            raise RuntimeError("the menu bitmap is not available")
        surface = load_bitmap(self.scene.content, resource_name)
        width, height = surface.get_size()
        rgba = bytearray(pygame.image.tobytes(surface, "RGBA"))
        if transparent_blue:
            for offset in range(0, len(rgba), 4):
                if bytes(rgba[offset:offset + 3]) == b"\x00\x00\xff":
                    rgba[offset + 3] = 0
        quad = ScreenQuad(gpu, (width, height))
        quad.write(rgba)
        return quad

    def _button_at(self, pos: Sequence[float]) -> int | None:
        left, top, scale = self._layout()
        native_x, native_y = ((pos[0] - left) / scale, (pos[1] - top) / scale)
        for index, hotspot in enumerate(self.hotspots):
            if pygame.Rect(hotspot.x, hotspot.y, hotspot.width, hotspot.height).collidepoint(native_x, native_y):
                return index
        return None

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.KEYDOWN:
            action = self.SHORTCUTS.get(event.key)
            if action:
                return (action,)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.pressed = self._button_at(event.pos)
            if self.pressed is not None:
                self._click_cue(self.hotspots[self.pressed].downsfx or 0)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            index, self.pressed = self.pressed, None
            released = self._button_at(event.pos)
            if released is not None:
                self._click_cue(self.hotspots[released].upsfx or 0)
            if index is not None and index == released:
                action = self.TARGET_ACTIONS.get((self.hotspots[index].target or "").lower())
                return (action,) if action else ()
        return ()

    def draw(self) -> None:
        super().draw()
        left, top, scale = self._layout()
        self.screen.draw(left, top, self.NATIVE_SIZE[0] * scale, self.NATIVE_SIZE[1] * scale)
        for index, hotspot in enumerate(self.hotspots):
            sprite = self.button_down if index == self.pressed else self.button_up
            sprite.draw(left + hotspot.x * scale, top + hotspot.y * scale,
                        hotspot.width * scale, hotspot.height * scale)

    def release(self) -> None:
        self.screen.release()
        self.button_up.release()
        self.button_down.release()


class BriefingView(SceneView[BriefingScene]):
    """Shows the mission title and spoken briefing lines; Start Battle enters the battle itself."""

    BODY_SIZE = (900, 480)
    BODY_WIDTH = 860

    def __init__(self, gpu: Gpu, scene: BriefingScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        briefing = scene.briefing
        self.font = BitmapFont(scene.font)
        self.title = gpu.text((900, 24), self.font, background=None)
        self.title.set_lines((briefing["title"],))
        wrapped: list[str] = []
        for line in briefing["lines"]:
            wrapped.extend(_wrap(self.font, line["text"], self.BODY_WIDTH))
            wrapped.append("")
        self.body = gpu.text(self.BODY_SIZE, self.font)
        self.body.set_lines(wrapped)
        self.hint = gpu.text((640, 20), self.font, background=None)
        self.hint.set_lines(("Press Enter or click to start the battle",))

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return ("start_battle",)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return ("start_battle",)
        return ()

    def status(self) -> Sequence[str]:
        return (f"briefing {self.scene.battle_id}, {len(self.scene.briefing['lines'])} lines",)

    def draw(self) -> None:
        super().draw()
        width, height = self.gpu.target.size
        self.title.draw((width - self.title.text_size[0]) // 2, 40)
        self.body.draw((width - self.BODY_SIZE[0]) // 2, 120)
        self.hint.draw((width - self.hint.text_size[0]) // 2, height - 60)

    def release(self) -> None:
        self.title.release()
        self.body.release()
        self.hint.release()
