# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Movie playback view: the verified 8 fps Smacker video through a palette-lookup shader, and its
original WAV cues played through pygame's mixer at their scheduled start. Presents any cutscene
started as the boot-time intro or as a glue ``playmovie`` activity (whshr.campaign_scenes.MovieScene).

The scene's own elapsed time is the single source of truth for both the due video frame and which
audio cues have started; this view only presents it.
"""

import io
import struct
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import pygame

from ..campaign_scenes import MovieScene
from ..audio_settings import audio_settings
from ..scenes import SceneEvent

from ..smacker import Smacker, frame_index_at
from ..cutscene import SubtitleTimeline, subtitle_color
from .bitmap_font import BitmapFont
from .gpu import QUAD_VERTEX_SHADER, Gpu
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

    def __init__(self, gpu: Gpu, width: int, height: int) -> None:
        self.gpu = gpu
        nearest: dict[str, str] = {"min_filter": "nearest", "mag_filter": "nearest",
                   "wrap_x": "clamp_to_edge", "wrap_y": "clamp_to_edge"}
        self.indices = gpu.ctx.image((width, height), "r8unorm")
        self.palette = gpu.ctx.image((256, 1), "rgba8unorm")
        resources: list[Any] = [
            {"type": "sampler", "binding": 0, "image": self.indices, **nearest},
            {"type": "sampler", "binding": 1, "image": self.palette, **nearest},
        ]
        self.pipeline = gpu.ctx.pipeline(
            vertex_shader=QUAD_VERTEX_SHADER,
            fragment_shader=VIDEO_FRAGMENT_SHADER,
            layout=[{"name": "indices", "binding": 0}, {"name": "palette", "binding": 1}],
            resources=resources,
            uniforms={"screen_size": gpu.target.size, "rect": (0, 0, width, height)},
            framebuffer=[gpu.target.color],
            topology="triangle_strip", vertex_count=4,
        )

    def write(self, indices: bytes | bytearray, palette_rgb: Sequence[int]) -> None:
        """``indices``: w*h palette-index bytes. ``palette_rgb``: 256*3 RGB bytes."""
        self.indices.write(bytes(indices))
        rgba = bytearray(256 * 4)
        for i in range(256):
            rgba[i * 4:i * 4 + 3] = palette_rgb[i * 3:i * 3 + 3]
            rgba[i * 4 + 3] = 255
        self.palette.write(bytes(rgba))

    def draw(self, left: float, top: float, width: float, height: float) -> None:
        uniforms = self.pipeline.uniforms
        if uniforms is None:
            raise RuntimeError("the video pipeline has no uniforms")
        uniforms["rect"][:] = struct.pack("4f", left, top, width, height)
        self.pipeline.render()

    def release(self) -> None:
        self.gpu.ctx.release(self.pipeline)
        self.gpu.ctx.release(self.indices)
        self.gpu.ctx.release(self.palette)


def _ensure_mixer() -> bool:
    """Best-effort mixer setup; audio stays silently unavailable without a usable audio device."""
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
        if pygame.mixer.get_num_channels() < MIXER_CHANNELS:
            pygame.mixer.set_num_channels(MIXER_CHANNELS)
        
        return True
    except pygame.error:
        return False


class MovieView(SceneView[MovieScene]):
    """Plays one cutscene: upright, aspect-correct, letterboxed on black; skip on key or click. A film with
    narration captions first shows them as a text-only page (notes/cutscene_narration.md 3, 4.1)."""

    # notes/cutscene_narration.md 3: a 125-pixel margin on every side of the 640x480 front end.
    NARRATION_WIDTH = 640 - 2 * 125
    NARRATION_HEIGHT = 480 - 2 * 125

    def __init__(self, gpu: Gpu, scene: MovieScene, options: dict[str, Any] | None = None) -> None:
        super().__init__(gpu, scene, options)
        self.smk = self._find_video(scene.media)
        self.video = VideoQuad(gpu, self.smk.w, self.smk.h)
        self.last_frame = -1
        self.audio_ok = _ensure_mixer()
        self.cues = sorted(self._find_cues(scene.media), key=lambda cue: cue[0]) if self.audio_ok else []
        self.next_cue = 0
        self.playing = 0
        self.subtitles = SubtitleTimeline(scene.media, scene.texts)
        self.subtitle_font = BitmapFont(scene.subtitle_font)
        self.subtitle = gpu.text((640, 80), self.subtitle_font, color=(255, 255, 255),
                                 background=None, padding=0)
        self.subtitle_text: tuple[str, Any] | None = None
        # The text page before the film (scene phase "narration"): white SUBTEXT at 1:1 on black, every line
        # centred, the block centred vertically (notes/cutscene_narration.md 3).
        self.narration = gpu.text((self.NARRATION_WIDTH, self.NARRATION_HEIGHT), self.subtitle_font,
                                  color=(255, 255, 255), background=None, padding=0, align="center")
        self.narration.set_lines(self._wrap(scene.narration, self.NARRATION_WIDTH))
        if scene.phase == "movie":
            self._sync(0.0)

    @staticmethod
    def _find_video(media: Mapping[str, Any]) -> Smacker:
        for entry in media["objects"].values():
            if "smk" in entry and "blob" in entry:
                return Smacker(entry["blob"])
        raise ValueError("movie media has no Smacker video")

    @staticmethod
    def _find_cues(media: Mapping[str, Any]) -> Iterator[tuple[float, pygame.mixer.Sound]]:
        for entry in media["objects"].values():
            if "wav" in entry and "blob" in entry:
                sound = pygame.mixer.Sound(io.BytesIO(entry["blob"]))
                sound.set_volume(audio_settings.volume("dialogue"))
                yield entry["start"] / 1000, sound

    def events(self, event: pygame.event.Event) -> Sequence[SceneEvent]:
        if self.scene.phase == "narration":
            # notes/cutscene_narration.md 4.1: Enter, or the left button pressed over the film area, ends the page
            # at once; the press is consumed, so it does not also skip the film.
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return ("continue",)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                left, top, width, height = self._film_rect()
                if left <= event.pos[0] < left + width and top <= event.pos[1] < top + height:
                    return ("continue",)
            return ()
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            return ("skip",)
        return ()

    def _sync(self, elapsed: float) -> None:
        frame = frame_index_at(elapsed, self.smk.nframes)
        if frame != self.last_frame:
            self.smk.decode_to(frame)
            self.video.write(self.smk.img, self.smk.pal)
            self.last_frame = frame
        while self.next_cue < len(self.cues) and self.cues[self.next_cue][0] <= elapsed:
            if self.cues[self.next_cue][1].play() is not None:  # pyright: ignore[reportUnnecessaryComparison]
                self.playing += 1
            self.next_cue += 1
        subtitle = self.subtitles.current(elapsed)
        text = subtitle.text_at(elapsed) if subtitle else ""
        style = (text, subtitle_color(subtitle.speaker) if subtitle else None)
        if style != self.subtitle_text:
            if subtitle and style[1] is not None:
                self.subtitle.set_color(style[1])
            self.subtitle.set_lines(self._wrap_subtitle(text))
            self.subtitle_text = style

    def _wrap_subtitle(self, text: str) -> tuple[str, ...]:
        """Keep subtitle text in the original film's narrow lower strip."""
        return self._wrap(text, self.subtitle.size[0])

    def _wrap(self, text: str, max_width: int) -> tuple[str, ...]:
        if not text:
            return ()
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or self.subtitle_font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        return (*lines, current) if current else tuple(lines)

    def animate(self, seconds: float) -> None:
        if self.scene.phase == "movie":
            self._sync(self.scene.elapsed_seconds)

    def status(self) -> Sequence[str]:
        audio = f"{self.playing} cues" if self.audio_ok else "no audio device"
        return (
            f"movie {self.scene.elapsed_seconds:.1f}/{self.scene.duration_seconds:.1f} s, "
            f"frame {self.last_frame}/{self.smk.nframes - 1}, {audio}",
        )

    def draw(self) -> None:
        super().draw()
        (screen_w, screen_h) = self.gpu.target.size
        if self.scene.phase == "narration":
            text_w, text_h = self.narration.text_size
            self.narration.draw((screen_w - text_w) / 2, (screen_h - text_h) / 2)
            return
        left, top, width, height = self._film_rect()
        scale = width / self.smk.w
        self.video.draw(left, top, width, height)
        if self.subtitle_text is not None and self.subtitle_text[0]:
            # The video can scale up for a better presentation, but the
            # original subtitle bitmap remains 1:1.  Its left edge is the
            # left edge of the original centered 640-pixel film box.
            self.subtitle.draw((screen_w - self.smk.w) / 2, top + height + 5 * scale)

    def _film_rect(self) -> tuple[float, float, float, float]:
        """Where the film is drawn: (left, top, width, height) in target pixels."""
        screen_w, screen_h = self.gpu.target.size
        # Reserve the original subtitle strip under the 640x272 film before
        # choosing a scale, so captions never obscure the video itself.
        subtitle_strip = 32
        scale = min(screen_w / self.smk.w, screen_h / (self.smk.h + subtitle_strip))
        width, height = self.smk.w * scale, self.smk.h * scale
        return (screen_w - width) / 2, (screen_h - (self.smk.h + subtitle_strip) * scale) / 2, width, height

    def release(self) -> None:
        self.video.release()
        self.subtitle.release()
        self.narration.release()
        for _, sound in self.cues:
            sound.stop()
