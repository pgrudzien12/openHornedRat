"""Main menu and mission briefing views: clickable text, keyboard shortcuts, no original graphics yet."""

import pygame

from .scene_view import SceneView


def _wrap(font, text, max_width):
    """Split ``text`` into lines that each fit ``max_width`` pixels in ``font``."""
    words, lines, current = text.split(), [], ""
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


class MainMenuView(SceneView):
    """New Campaign starts the first mission briefing; Quit sends a scene-level Quit signal."""

    BUTTONS = (("New Campaign", "new_campaign", (pygame.K_n, pygame.K_RETURN, pygame.K_KP_ENTER)),
               ("Quit", "quit", (pygame.K_q, pygame.K_ESCAPE)))
    SPACING = 70

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.title = gpu.text((760, 70), gpu.title_font, background=None)
        self.title.set_lines(("Warhammer: Shadow of the Horned Rat",))
        self.labels = [gpu.text((360, 56), gpu.title_font) for _ in self.BUTTONS]
        for label, (text, _, keys) in zip(self.labels, self.BUTTONS):
            hint = "/".join(pygame.key.name(key).upper() for key in keys[:1])
            label.set_lines((f"{text}  [{hint}]",))

    def _rect(self, index):
        width, height = self.gpu.target.size
        size = self.labels[index].text_size
        top = height // 2 + index * self.SPACING
        return pygame.Rect((width - size[0]) // 2, top, *size)

    def events(self, event):
        if event.type == pygame.KEYDOWN:
            for _, action, keys in self.BUTTONS:
                if event.key in keys:
                    return (action,)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, (_, action, _keys) in enumerate(self.BUTTONS):
                if self._rect(index).collidepoint(event.pos):
                    return (action,)
        return ()

    def draw(self):
        super().draw()
        width, _ = self.gpu.target.size
        self.title.draw((width - self.title.text_size[0]) // 2, 130)
        for index, label in enumerate(self.labels):
            rect = self._rect(index)
            label.draw(rect.left, rect.top)

    def release(self):
        self.title.release()
        for label in self.labels:
            label.release()


class BriefingView(SceneView):
    """Shows the mission title and spoken briefing lines; Start Battle enters the battle itself."""

    BODY_SIZE = (900, 480)
    BODY_WIDTH = 860

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        briefing = scene.briefing
        self.title = gpu.text((900, 60), gpu.title_font, background=None)
        self.title.set_lines((briefing["title"],))
        wrapped = []
        for line in briefing["lines"]:
            wrapped.extend(_wrap(gpu.small_font, line["text"], self.BODY_WIDTH))
            wrapped.append("")
        self.body = gpu.text(self.BODY_SIZE, gpu.small_font)
        self.body.set_lines(wrapped)
        self.hint = gpu.text((640, 40), gpu.small_font, background=None)
        self.hint.set_lines(("Press Enter or click to start the battle",))

    def events(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return ("start_battle",)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return ("start_battle",)
        return ()

    def status(self):
        return (f"briefing {self.scene.battle_id}, {len(self.scene.briefing['lines'])} lines",)

    def draw(self):
        super().draw()
        width, height = self.gpu.target.size
        self.title.draw((width - self.title.text_size[0]) // 2, 40)
        self.body.draw((width - self.BODY_SIZE[0]) // 2, 120)
        self.hint.draw((width - self.hint.text_size[0]) // 2, height - 60)

    def release(self):
        self.title.release()
        self.body.release()
        self.hint.release()
