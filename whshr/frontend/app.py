"""Runtime main loop: window, fixed-step scene updates, input, drawing and the debug overlay."""

import os
from pathlib import Path
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
import zengl  # noqa: E402

from ..assets import AssetId  # noqa: E402
from ..battle_scene import BattleScene  # noqa: E402
from ..campaign_scenes import OpeningNarrationScene  # noqa: E402
from ..clock import FixedStepClock  # noqa: E402
from ..engine import DEFAULT_SEED  # noqa: E402
from ..game import scene_context  # noqa: E402
from ..glue_scene import GlueScene  # noqa: E402
from ..scenes import SceneMachine  # noqa: E402
from .gpu import Gpu  # noqa: E402
from .views import view_for  # noqa: E402

# Scene time advances in fixed 10 ms steps; the battle simulation groups them into its own 100 ms ticks.
FIXED_STEP = 0.01
MAX_STEPS_PER_FRAME = 25
MAX_FRAMES_PER_SECOND = 240  # frame cap when vsync is unavailable or the window is hidden
OVERLAY_REFRESH_SECONDS = 0.25
WINDOW_TITLE = "openHornedRat"
FADE_SECONDS = 0.3  # short fade-in from black after every scene switch


def open_window(size, hidden=False):
    """Open an OpenGL 3.3 core window and return its zengl context."""
    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    flags = pygame.OPENGL | pygame.DOUBLEBUF | (pygame.HIDDEN if hidden else 0)
    try:
        pygame.display.set_mode(size, flags, vsync=0 if hidden else 1)
    except pygame.error:  # Some drivers refuse a vsync request; run without it.
        pygame.display.set_mode(size, flags)
    pygame.display.set_caption(WINDOW_TITLE)
    zengl.init()
    return zengl.context()


class FrameRate:
    """Frames per second measured over short wall-clock windows."""

    def __init__(self, window=0.5):
        self.window, self.value = window, 0.0
        self._start, self._frames = None, 0

    def frame(self, now):
        if self._start is None:
            self._start = now
        self._frames += 1
        if now - self._start >= self.window:
            self.value = self._frames / (now - self._start)
            self._start, self._frames = now, 0


def run(installation, size=(1280, 800), skip_intro=False, hidden=False, frames=None, screenshot=None,
        frame_time=None, battle=None, camera=None, log_dir=None, seed=DEFAULT_SEED, glue_program=None):
    """Run the game until the window closes, or for ``frames`` frames when given.

    ``frame_time`` replaces the measured wall-clock frame duration, so a capture after a number of frames
    shows the same scene time on every run. ``battle`` (e.g. "BF001") starts directly in that battle and
    ``camera`` (yaw, pitch, distance) overrides its initial camera. ``log_dir`` (a path, or ``None`` to
    disable) and ``seed`` are threaded into every ``BattleScene`` reached through the scene flow, so
    ``--battle-log``/``--no-battle-log``/``--seed`` (``python3 -m whshr engine``) apply however the
    battle is reached (the ``--battle`` shortcut, or intro -> menu -> briefing).
    ``glue_program`` is a development shortcut that starts a typed ``[RUN]``
    resource through ``GlueScene`` and its generic static view.
    """
    context = scene_context(installation)
    ctx = open_window(size, hidden)
    gpu = Gpu(ctx, size)
    # Wider debug overlay; unrelated to the battle HUD.
    overlay = gpu.text((820, 140))
    initial = (GlueScene(glue_program) if glue_program else
               BattleScene(AssetId("vanilla", "battle", Path(battle).stem.casefold()), log_dir=log_dir, seed=seed)
               if battle else OpeningNarrationScene(log_dir=log_dir, seed=seed))
    machine = SceneMachine(initial, context)
    options = {"camera": camera}
    view = view_for(gpu, machine.active, options)
    clock = FixedStepClock(FIXED_STEP, MAX_STEPS_PER_FRAME)
    rate = FrameRate()
    limiter = pygame.time.Clock()
    fade_remaining = FADE_SECONDS  # fade in from black on the initial scene too

    def synchronise(current):
        nonlocal fade_remaining
        if current.scene is machine.active:
            return current
        current.release()
        fade_remaining = FADE_SECONDS
        return view_for(gpu, machine.active, options)

    if skip_intro and not battle:
        machine.handle("skip")
        view = synchronise(view)
    frame, last, overlay_time, running = 0, time.perf_counter(), float("-inf"), True
    battle_log_path = None  # tracked across scene transitions so it survives a battle -> result switch
    try:
        while running:
            if isinstance(machine.active, BattleScene) and machine.active.logger is not None:
                battle_log_path = machine.active.logger.path or battle_log_path
            now = time.perf_counter()
            elapsed, last = now - last, now
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL
                ):
                    running = False
                    continue
                for scene_event in view.events(event):
                    machine.handle(scene_event)
                    view = synchronise(view)
                    if hasattr(view, "refresh"):
                        view.refresh()
                    if machine.quit is not None:
                        running = False

            seconds = elapsed if frame_time is None else frame_time
            for _ in range(clock.advance(seconds)):
                machine.update(clock.step)
                view = synchronise(view)
                if hasattr(view, "refresh"):
                    view.refresh()
                if machine.quit is not None:
                    running = False
            if running:
                view.animate(seconds)
            fade_remaining = max(0.0, fade_remaining - seconds)

            rate.frame(now)
            if now - overlay_time >= OVERLAY_REFRESH_SECONDS or frames is not None:
                overlay_time = now
                overlay.set_lines((
                    f"FPS {rate.value:.0f}", f"tick {clock.ticks}", f"scene {type(machine.active).__name__}",
                    *view.status(),
                ))

            ctx.new_frame()
            view.draw()
            if fade_remaining > 0:
                alpha = fade_remaining / FADE_SECONDS
                gpu.fade.draw(0, 0, *gpu.target.size, tint=(0.0, 0.0, 0.0, alpha))
            overlay.draw(8, 8)
            gpu.target.present()
            ctx.end_frame()
            frame += 1
            if frames is not None and frame >= frames:
                if screenshot is not None:
                    gpu.target.save_png(screenshot)
                running = False
            pygame.display.flip()
            limiter.tick(MAX_FRAMES_PER_SECOND)
    finally:
        # The window can close or Ctrl+Q can fire mid-battle, bypassing the scene machine's own
        # transition/exit path (`machine.quit` above only covers a Quit a scene itself returns): make
        # sure an open battle log is still finalized so it stays a usable, complete record.
        if isinstance(machine.active, BattleScene):
            machine.active.close_log("player quit" if machine.quit is None else machine.quit.reason)
            if machine.active.logger is not None and machine.active.logger.path:
                battle_log_path = machine.active.logger.path
        pygame.quit()
    if battle_log_path is not None:
        print(f"Battle log: {battle_log_path}")
    return {
        "frames": frame, "ticks": clock.ticks, "scene": type(machine.active).__name__,
        "quit": machine.quit.reason if machine.quit is not None else None,
    }
