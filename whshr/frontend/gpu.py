"""GPU helpers: the frame render target, textured screen-space quads and text labels."""

import struct

import pygame

from ..image import write_png

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

ALPHA_BLEND = {
    "enable": True,
    "src_color": "src_alpha", "dst_color": "one_minus_src_alpha",
    "src_alpha": "one", "dst_alpha": "one_minus_src_alpha",
}


class RenderTarget:
    """Off-screen colour and depth images that every pipeline draws into; presented once per frame."""

    def __init__(self, ctx, size):
        self.size = size
        self.color = ctx.image(size, "rgba8unorm")
        self.depth = ctx.image(size, "depth24plus")

    def clear(self, rgb):
        self.color.clear_value = (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0)
        self.color.clear()
        self.depth.clear()

    def present(self):
        self.color.blit()

    def save_png(self, path):
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

    def __init__(self, gpu, size, filter="nearest"):
        self.gpu = gpu
        self.size = size
        self.texture = gpu.ctx.image(size, "rgba8unorm")
        self.pipeline = gpu.ctx.pipeline(
            vertex_shader=QUAD_VERTEX_SHADER,
            fragment_shader=QUAD_FRAGMENT_SHADER,
            layout=[{"name": "image", "binding": 0}],
            resources=[{
                "type": "sampler", "binding": 0, "image": self.texture,
                "min_filter": filter, "mag_filter": filter, "wrap_x": "clamp_to_edge", "wrap_y": "clamp_to_edge",
            }],
            uniforms={"screen_size": gpu.target.size, "rect": (0, 0, *size), "tint": (1, 1, 1, 1)},
            blend=ALPHA_BLEND,
            framebuffer=[gpu.target.color],
            topology="triangle_strip",
            vertex_count=4,
        )

    def write(self, rgba):
        """Upload top-down RGBA bytes of exactly the quad's texture size."""
        self.texture.write(rgba)

    def draw(self, left, top, width=None, height=None, tint=(1.0, 1.0, 1.0, 1.0)):
        width = self.size[0] if width is None else width
        height = self.size[1] if height is None else height
        self.pipeline.uniforms["rect"][:] = struct.pack("4f", left, top, width, height)
        self.pipeline.uniforms["tint"][:] = struct.pack("4f", *tint)
        self.pipeline.render()

    def release(self):
        self.gpu.ctx.release(self.pipeline)
        self.gpu.ctx.release(self.texture)


class TextLabel(ScreenQuad):
    """Lines of text rendered with pygame's font once per change and uploaded as a texture."""

    def __init__(self, gpu, size, font, color=(235, 230, 210), background=(0, 0, 0, 150), padding=6):
        super().__init__(gpu, size)
        self.font, self.color, self.background, self.padding = font, color, background, padding
        self.text_size = (0, 0)
        self._lines = None

    def set_lines(self, lines):
        """Re-render only when the text changes; returns the used size in pixels."""
        lines = tuple(lines)
        if lines == self._lines:
            return self.text_size
        self._lines = lines
        rendered = [self.font.render(line, True, self.color) for line in lines if line]
        width = min(self.size[0], max((line.get_width() for line in rendered), default=0) + 2 * self.padding)
        height = min(self.size[1], sum(line.get_height() for line in rendered) + 2 * self.padding)
        surface = pygame.Surface(self.size, pygame.SRCALPHA)
        if rendered and self.background:
            surface.fill(self.background, (0, 0, width, height))
        top = self.padding
        for line in rendered:
            surface.blit(line, (self.padding, top))
            top += line.get_height()
        self.write(pygame.image.tobytes(surface, "RGBA"))
        self.text_size = (width, height)
        return self.text_size


class Gpu:
    """The zengl context, the frame render target and shared fonts."""

    def __init__(self, ctx, size):
        self.ctx = ctx
        self.target = RenderTarget(ctx, size)
        self.small_font = pygame.font.Font(None, 22)
        self.title_font = pygame.font.Font(None, 40)
        # A single opaque white pixel, stretched and tinted black for scene-transition fades.
        self.fade = ScreenQuad(self, (1, 1))
        self.fade.write(b"\xff\xff\xff\xff")

    def text(self, size, font=None, **options):
        return TextLabel(self, size, font or self.small_font, **options)
