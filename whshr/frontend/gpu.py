# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""GPU helpers: the frame render target, textured screen-space quads and text labels."""

import struct
from collections.abc import Iterable, Sequence
from os import PathLike
from typing import Any

import pygame
import zengl

from ..image import write_png

Size = tuple[int, int]
Rgb = tuple[int, int, int]
Rgba = tuple[int, int, int, int]
Font = Any  # a pygame.font.Font or a BitmapFont (both offer render/size)


QUAD_VERTEX_SHADER = """
#version 330 core

uniform vec2 screen_size;
uniform vec4 rect;  // left, top, width, height in window pixels, top-left origin

out vec2 uv;

const vec2 corners[4] = vec2[](vec2(0.0, 0.0), vec2(1.0, 0.0), vec2(0.0, 1.0), vec2(1.0, 1.0));

void main() {
    vec2 corner = corners[gl_VertexID];
    vec2 pixel = rect.xy + corner * rect.zw;
    gl_Position = vec4(pixel.x / screen_size.x * 2.0 - 1.0, 1.0 - pixel.y / screen_size.y * 2.0, 0.0, 1.0);
    uv = corner;  // texture row 0 is the top row of the uploaded image
}
"""

QUAD_FRAGMENT_SHADER = """
#version 330 core

uniform sampler2D image;
uniform vec4 tint;

in vec2 uv;
out vec4 frag_color;

void main() {
    frag_color = texture(image, uv) * tint;
}
"""

ALPHA_BLEND: zengl.BlendSettings = {
    "enable": True,
    "src_color": "src_alpha", "dst_color": "one_minus_src_alpha",
    "src_alpha": "one", "dst_alpha": "one_minus_src_alpha",
}


class RenderTarget:
    """Off-screen colour and depth images that every pipeline draws into; presented once per frame."""

    def __init__(self, ctx: zengl.Context, size: Size) -> None:
        self.size = size
        self.color = ctx.image(size, "rgba8unorm")
        self.depth = ctx.image(size, "depth24plus")

    def clear(self, rgb: Sequence[int]) -> None:
        self.color.clear_value = (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0)
        self.color.clear()
        self.depth.clear()

    def present(self) -> None:
        self.color.blit()

    def save_png(self, path: str | PathLike[str]) -> None:
        """Write the current frame as a top-down RGB PNG (OpenGL rows are stored bottom-up)."""
        width, height = self.size
        rgba = self.color.read()
        rgb = bytearray(width * height * 3)
        for channel in range(3):
            rgb[channel::3] = rgba[channel::4]
        row = width * 3
        write_png(path, width, height, b"".join(
            rgb[offset:offset + row] for offset in range((height - 1) * row, -1, -row)
        ))


class ScreenQuad:
    """An RGBA texture drawn at a pixel rectangle of the render target, alpha-blended."""

    def __init__(self, gpu: "Gpu", size: Size, filter: str = "nearest") -> None:
        self.gpu = gpu
        self.size = size
        self.texture = gpu.ctx.image(size, "rgba8unorm")
        resources: list[Any] = [{
            "type": "sampler", "binding": 0, "image": self.texture,
            "min_filter": filter, "mag_filter": filter, "wrap_x": "clamp_to_edge", "wrap_y": "clamp_to_edge",
        }]
        self.pipeline = gpu.ctx.pipeline(
            vertex_shader=QUAD_VERTEX_SHADER,
            fragment_shader=QUAD_FRAGMENT_SHADER,
            layout=[{"name": "image", "binding": 0}],
            resources=resources,
            uniforms={"screen_size": gpu.target.size, "rect": (0, 0, *size), "tint": (1, 1, 1, 1)},
            blend=ALPHA_BLEND,
            framebuffer=[gpu.target.color],
            topology="triangle_strip",
            vertex_count=4,
        )

    def write(self, rgba: bytes | bytearray) -> None:
        """Upload top-down RGBA bytes of exactly the quad's texture size."""
        self.texture.write(rgba)

    def draw(self, left: float, top: float, width: float | None = None, height: float | None = None,
             tint: Sequence[float] = (1.0, 1.0, 1.0, 1.0)) -> None:
        width = self.size[0] if width is None else width
        height = self.size[1] if height is None else height
        uniforms = self.pipeline.uniforms
        if uniforms is None:
            raise RuntimeError("the quad pipeline has no uniforms")
        uniforms["rect"][:] = struct.pack("4f", left, top, width, height)
        uniforms["tint"][:] = struct.pack("4f", *tint)
        self.pipeline.render()

    def release(self) -> None:
        self.gpu.ctx.release(self.pipeline)
        self.gpu.ctx.release(self.texture)


class TextLabel(ScreenQuad):
    """Lines of text rendered with pygame's font once per change and uploaded as a texture."""

    def __init__(self, gpu: "Gpu", size: Size, font: Font, color: Rgb = (235, 230, 210),
                 background: Rgba | None = (0, 0, 0, 150), padding: int = 6, align: str = "left",
                 fixed_width: bool = False, outline: bool = False) -> None:
        # An outline stroke needs 1 px of room outside the glyph box on every side, or the top row
        # of the first line (and either edge) gets clipped by the surface bounds; reserve it here
        # so callers can size a label to the text they actually want visible.
        self._margin = 1 if outline else 0
        super().__init__(gpu, (size[0] + 2 * self._margin, size[1] + 2 * self._margin))
        if align not in ("left", "center"):
            raise ValueError(f"unsupported text alignment: {align!r}")
        self.font, self.color, self.background, self.padding = font, color, background, padding
        self.align = align
        self.fixed_width = fixed_width
        self.outline = outline
        self.text_size: Size = (0, 0)
        self._lines: tuple[str, ...] | None = None

    def set_lines(self, lines: Iterable[str]) -> Size:
        """Re-render only when the text changes; returns the used size in pixels."""
        lines = tuple(lines)
        if lines == self._lines:
            return self.text_size
        self._lines = lines
        texts = [line for line in lines if line]
        rendered = [self.font.render(line, True, self.color) for line in texts]
        content_width = max((line.get_width() for line in rendered), default=0) + 2 * self.padding
        box_width, box_height = self.size[0] - 2 * self._margin, self.size[1] - 2 * self._margin
        width = box_width if self.fixed_width else min(box_width, content_width)
        height = min(box_height, sum(line.get_height() for line in rendered) + 2 * self.padding)
        surface = pygame.Surface(self.size, pygame.SRCALPHA)
        if rendered and self.background:
            surface.fill(self.background, (self._margin, self._margin, width, height))
        top = self.padding + self._margin
        for text, line in zip(texts, rendered):
            left = self._margin + (self.padding if self.align == "left" else (width - line.get_width()) // 2)
            if self.outline:
                # A 1 px black outline in every direction approximates the original's 5x5 stamped
                # outline (notes/briefing_dialogue.md §3.3) without rendering 24 extra offsets.
                black = self.font.render(text, True, (0, 0, 0))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx or dy:
                            surface.blit(black, (left + dx, top + dy))
            surface.blit(line, (left, top))
            top += line.get_height()
        self.write(pygame.image.tobytes(surface, "RGBA"))
        self.text_size = (width + 2 * self._margin, height + 2 * self._margin)
        return self.text_size

    def set_color(self, color: Sequence[int]) -> None:
        """Change glyph color and invalidate the cached raster when needed."""
        color = tuple(color)
        if color != self.color:
            self.color = color
            self._lines = None


class BattleLogPanel(ScreenQuad):
    """4-line scrollable battle log: each entry is a (sender, message) pair.

    The sender is rendered in bold and the message follows on the same line; both use the
    same small font at the battle HUD's own size. Color is red per the original's style.
    """

    LINES = 4

    def __init__(self, gpu: "Gpu", size: Size, bold_font: Font, normal_font: Font,
                 color: Rgb = (220, 50, 50), background: Rgba | None = (0, 0, 0, 140)) -> None:
        super().__init__(gpu, size)
        self.bold_font = bold_font
        self.normal_font = normal_font
        self.color = color
        self.background = background
        self._entries: tuple[tuple[str, str], ...] | None = None

    def set_entries(self, entries: Sequence[tuple[str, str]]) -> None:
        """Render *entries* (list of (sender, message) tuples, newest last) into the panel."""
        entries = tuple(entries[-self.LINES:])
        if entries == self._entries:
            return
        self._entries = entries
        surface = pygame.Surface(self.size, pygame.SRCALPHA)
        if self.background:
            surface.fill(self.background)
        line_h = max(self.bold_font.get_linesize(), self.normal_font.get_linesize())
        y = 2
        for sender, message in entries:
            bold_surf = self.bold_font.render(sender, True, self.color)
            surface.blit(bold_surf, (4, y))
            x = 4 + bold_surf.get_width() + 3
            remaining = self.size[0] - x - 4
            if remaining > 0:
                msg_surf = self.normal_font.render(message, True, self.color)
                if msg_surf.get_width() > remaining:
                    msg_surf = msg_surf.subsurface((0, 0, remaining, msg_surf.get_height()))
                surface.blit(msg_surf, (x, y))
            y += line_h
            if y + line_h > self.size[1]:
                break
        self.write(pygame.image.tobytes(surface, "RGBA"))


class UnitInfoPanel(ScreenQuad):
    """Selected unit name, class and casualty readout in the HUD panel."""

    def __init__(self, gpu: "Gpu", size: Size, bold_font: Font, normal_font: Font,
                 color: Rgb = (0, 0, 0), background: Rgba | None = (0, 0, 0, 140)) -> None:
        super().__init__(gpu, size)
        self.bold_font = bold_font
        self.normal_font = normal_font
        self.color = color
        self.background = background
        self._info: tuple[Any, ...] | None = None

    def set_info(self, name: str | None, unit_class: str | None, models: int | None, max_models: int | None) -> None:
        info = (name, unit_class, models, max_models)
        if info == self._info:
            return
        self._info = info
        surface = pygame.Surface(self.size, pygame.SRCALPHA)
        if self.background:
            surface.fill(self.background)
        w, h = self.size
        y = 0
        line_h = self.normal_font.get_linesize()
        name_splitted = name.split() if name else []
        for part in name_splitted:
            name_surf = self.normal_font.render(part, True, self.color)
            surface.blit(name_surf, (0, y))
            y += line_h
        # if unit_class:
        #     class_surf = self.normal_font.render(unit_class, True, self.color)
        #     surface.blit(class_surf, (4, y))
        if models is not None and max_models is not None:
            cas = f"{models}/{max_models}"
            cas_surf = self.normal_font.render(cas, True, self.color)
            surface.blit(cas_surf, (w - cas_surf.get_width(), h - cas_surf.get_height()))
        self.write(pygame.image.tobytes(surface, "RGBA"))


class Gpu:
    """The zengl context, the frame render target and shared fonts."""

    def __init__(self, ctx: zengl.Context, size: Size) -> None:
        self.ctx = ctx
        self.target = RenderTarget(ctx, size)
        self.small_font = pygame.font.Font(None, 22)
        self.title_font = pygame.font.Font(None, 40)
        self.battle_log_font = pygame.font.Font(None, 16)
        self.battle_log_font_bold = pygame.font.Font(None, 16)
        self.battle_log_font_bold.bold = True
        # A single opaque white pixel, stretched and tinted black for scene-transition fades.
        self.fade = ScreenQuad(self, (1, 1))
        self.fade.write(b"\xff\xff\xff\xff")

    def text(self, size: Size, font: Font | None = None, **options: Any) -> TextLabel:
        return TextLabel(self, size, font or self.small_font, **options)

    def battle_log(self, size: Size, **options: Any) -> BattleLogPanel:
        return BattleLogPanel(self, size, self.battle_log_font_bold, self.battle_log_font, **options)

    def unit_info(self, size: Size, **options: Any) -> UnitInfoPanel:
        return UnitInfoPanel(self, size, self.battle_log_font_bold, self.battle_log_font, **options)
