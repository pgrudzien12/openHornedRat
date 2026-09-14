"""Intro cutscene view: the verified 8 fps Smacker video through a palette-lookup shader, and its
original WAV cues played through pygame's mixer at their scheduled start.

The scene's own elapsed time (whshr.campaign_scenes.IntroScene) is the single source of truth for
both the due video frame and which audio cues have started; this view only presents it.
"""

import io
import struct

import pygame

from ..smacker import Smacker, frame_index_at
from .gpu import QUAD_VERTEX_SHADER
from .scene_view import SceneView

VIDEO_FRAGMENT_SHADER = """
#version 330 core

uniform sampler2D indices;
uniform sampler2D palette;

in vec2 uv;
out vec4 frag_color;

void main() {
    ivec2 texel = ivec2(uv * vec2(textureSize(indices, 0)));
    int index = int(texelFetch(indices, texel, 0).r * 255.0 + 0.5);
    frag_color = vec4(texelFetch(palette, ivec2(index, 0), 0).rgb, 1.0);
}
"""

MIXER_CHANNELS = 32  # the A1 intro layers up to ~28 overlapping wind/thunder/leaves cues


class VideoQuad:
    """A palette-index video frame (r8 texture + 256-colour palette texture) drawn as a screen quad."""

    def __init__(self, gpu, width, height):
        self.gpu = gpu
        nearest = {"min_filter": "nearest", "mag_filter": "nearest",
                   "wrap_x": "clamp_to_edge", "wrap_y": "clamp_to_edge"}
        self.indices = gpu.ctx.image((width, height), "r8unorm")
        self.palette = gpu.ctx.image((256, 1), "rgba8unorm")
        self.pipeline = gpu.ctx.pipeline(
            vertex_shader=QUAD_VERTEX_SHADER,
            fragment_shader=VIDEO_FRAGMENT_SHADER,
            layout=[{"name": "indices", "binding": 0}, {"name": "palette", "binding": 1}],
            resources=[
                {"type": "sampler", "binding": 0, "image": self.indices, **nearest},
                {"type": "sampler", "binding": 1, "image": self.palette, **nearest},
            ],
            uniforms={"screen_size": gpu.target.size, "rect": (0, 0, width, height)},
            framebuffer=[gpu.target.color],
            topology="triangle_strip", vertex_count=4,
        )

    def write(self, indices, palette_rgb):
        """``indices``: w*h palette-index bytes. ``palette_rgb``: 256*3 RGB bytes."""
        self.indices.write(bytes(indices))
        rgba = bytearray(256 * 4)
        for i in range(256):
            rgba[i * 4:i * 4 + 3] = palette_rgb[i * 3:i * 3 + 3]
            rgba[i * 4 + 3] = 255
        self.palette.write(bytes(rgba))

    def draw(self, left, top, width, height):
        self.pipeline.uniforms["rect"][:] = struct.pack("4f", left, top, width, height)
        self.pipeline.render()

    def release(self):
        self.gpu.ctx.release(self.pipeline)
        self.gpu.ctx.release(self.indices)
        self.gpu.ctx.release(self.palette)


def _ensure_mixer():
    """Best-effort mixer setup; audio stays silently unavailable without a usable audio device."""
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        if pygame.mixer.get_num_channels() < MIXER_CHANNELS:
            pygame.mixer.set_num_channels(MIXER_CHANNELS)
        return True
    except pygame.error:
        return False


class IntroView(SceneView):
    """Plays the A1 cutscene: upright, aspect-correct, letterboxed on black; skip on key or click."""

    def __init__(self, gpu, scene, options=None):
        super().__init__(gpu, scene, options)
        self.smk = self._find_video(scene.media)
        self.video = VideoQuad(gpu, self.smk.w, self.smk.h)
        self.last_frame = -1
        self.audio_ok = _ensure_mixer()
        self.cues = sorted(self._find_cues(scene.media), key=lambda cue: cue[0]) if self.audio_ok else []
        self.next_cue = 0
        self.playing = 0
        self._sync(0.0)

    @staticmethod
    def _find_video(media):
        for entry in media["objects"].values():
            if "smk" in entry and "blob" in entry:
                return Smacker(entry["blob"])
        raise ValueError("intro media has no Smacker video")

    @staticmethod
    def _find_cues(media):
        for entry in media["objects"].values():
            if "wav" in entry and "blob" in entry:
                yield entry["start"] / 1000, pygame.mixer.Sound(io.BytesIO(entry["blob"]))

    def events(self, event):
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            return ("skip",)
        return ()

    def _sync(self, elapsed):
        frame = min(frame_index_at(elapsed), self.smk.nframes - 1)
        if frame != self.last_frame:
            self.smk.decode_to(frame)
            self.video.write(self.smk.img, self.smk.pal)
            self.last_frame = frame
        while self.next_cue < len(self.cues) and self.cues[self.next_cue][0] <= elapsed:
            if self.cues[self.next_cue][1].play() is not None:
                self.playing += 1
            self.next_cue += 1

    def animate(self, seconds):
        self._sync(self.scene.elapsed_seconds)

    def status(self):
        audio = f"{self.playing} cues" if self.audio_ok else "no audio device"
        return (
            f"intro {self.scene.elapsed_seconds:.1f}/{self.scene.duration_seconds:.1f} s, "
            f"frame {self.last_frame}/{self.smk.nframes - 1}, {audio}",
        )

    def draw(self):
        super().draw()
        (screen_w, screen_h) = self.gpu.target.size
        scale = min(screen_w / self.smk.w, screen_h / self.smk.h)
        width, height = self.smk.w * scale, self.smk.h * scale
        self.video.draw((screen_w - width) / 2, (screen_h - height) / 2, width, height)

    def release(self):
        self.video.release()
        for _, sound in self.cues:
            sound.stop()
