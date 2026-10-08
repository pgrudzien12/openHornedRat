# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Runtime main loop: window, fixed-step scene updates, input, drawing and the debug overlay."""

import os
import sys
from collections.abc import Sequence
from os import PathLike
from pathlib import Path
import time
from typing import Any

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
import zengl  # noqa: E402

from ..assets import AssetId  # noqa: E402
from ..audio_settings import audio_settings  # noqa: E402
from ..battle_scene import BattleScene  # noqa: E402
from .. import campaign_log as campaign_log_module  # noqa: E402
from ..campaign_scenes import OpeningNarrationScene  # noqa: E402
from ..clock import FixedStepClock  # noqa: E402
from ..engine import DEFAULT_SEED  # noqa: E402
from ..game import scene_context  # noqa: E402
from ..glue_scene import GlueScene  # noqa: E402
from ..scenes import Scene, SceneMachine  # noqa: E402
from .cursors import CursorController  # noqa: E402
from .gpu import Gpu  # noqa: E402
from .scene_view import SceneView  # noqa: E402
from .views import view_for  # noqa: E402

# Scene time advances in fixed 10 ms steps; the battle simulation groups them into its own 100 ms ticks.
FIXED_STEP = 0.01
MAX_STEPS_PER_FRAME = 25
MAX_FRAMES_PER_SECOND = 240  # frame cap when vsync is unavailable or the window is hidden
OVERLAY_REFRESH_SECONDS = 0.25
WINDOW_TITLE = "openHornedRat"
FADE_SECONDS = 0.3  # short fade-in from black after every scene switch


def open_window(size: tuple[int, int], hidden: bool = False) -> zengl.Context:
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

    def __init__(self, window: float = 0.5) -> None:
        self.window, self.value = window, 0.0
        self._start: float | None = None
        self._frames = 0

    def frame(self, now: float) -> None:
        if self._start is None:
            self._start = now
        self._frames += 1
        if now - self._start >= self.window:
            self.value = self._frames / (now - self._start)
            self._start, self._frames = now, 0


class FrameProfile:
    """Aggregate frame costs for one visible glue window; print only when it closes."""

    PHASES = ("events", "update", "refresh", "animate", "draw", "present", "flip", "limit", "frame")

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = time.perf_counter()
        self.samples: dict[str, list[float]] = {phase: [0, 0.0, 0.0] for phase in self.PHASES}

    def add(self, phase: str, seconds: float) -> None:
        sample = seconds * 1000
        values = self.samples[phase]
        values[0] += 1
        values[1] += sample
        values[2] = max(values[2], sample)

    def report(self) -> None:
        frames = int(self.samples["frame"][0])
        if not frames:
            return
        duration = max(time.perf_counter() - self.started, 1e-9)
        values = " ".join(
            f"{phase}={items[1] / frames:.2f}/{items[2]:.2f}"
            for phase, items in self.samples.items()
        )
        print(f"Frame profile {self.name}: {frames} frames in {duration:.2f}s "
              f"({frames / duration:.1f} FPS); phase avg ms/frame / max ms/call: {values}; "
              f"update calls={int(self.samples['update'][0])}, refresh calls={int(self.samples['refresh'][0])}",
              file=sys.stderr)


def run(installation: str | PathLike[str], size: tuple[int, int] = (1280, 800), skip_intro: bool = False,
        hidden: bool = False, frames: int | None = None, screenshot: str | PathLike[str] | None = None,
        frame_time: float | None = None, battle: str | None = None, camera: Sequence[float] | None = None,
        log_dir: str | PathLike[str] | None = None, seed: int = DEFAULT_SEED, glue_program: str | None = None,
        save_dir: str | PathLike[str] | None = None, no_battle: bool = False,
        campaign_log_dir: str | PathLike[str] | None = None, profile_frames: bool = False,
        debug: bool = False) -> dict[str, Any]:
    """Run the game until the window closes, or for ``frames`` frames when given.

    ``frame_time`` replaces the measured wall-clock frame duration, so a capture after a number of frames
    shows the same scene time on every run. ``battle`` (e.g. "BF001") starts directly in that battle and
    ``camera`` (yaw, pitch, distance) overrides its initial camera. ``log_dir`` (a path, or ``None`` to
    disable) and ``seed`` are threaded into every ``BattleScene`` reached through the scene flow, so
    ``--battle-log``/``--no-battle-log``/``--seed`` (``python3 -m whshr engine``) apply however the
    battle is reached (the ``--battle`` shortcut, or intro -> menu -> briefing).
    ``glue_program`` is a development shortcut that starts a typed ``[RUN]``
    resource through ``GlueScene`` and its generic static view. ``save_dir`` is the engine's own
    save directory (never the original installation's SAVE/, notes/glue_engine_integration.md GEI7e).
    ``no_battle`` turns on the campaign-progression shortcut: every battle reached through the
    scene flow settles as an immediate, lossless win instead of being simulated.
    ``campaign_log_dir`` (a path, or ``None`` to disable) turns on the JSON Lines campaign session
    log (``whshr.campaign_log``, ``--campaign-log``/``--no-campaign-log``).
    """
    if hidden:
        # A hidden run is a development/test capture (--frames, --screenshot); it has no listener
        # and should not play audio through the machine's real device while running unattended.
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    context = scene_context(installation, save_dir=save_dir, no_battle=no_battle, debug=debug)
    audio_settings.configure(context.save_dir)
    context.battle_log_dir = log_dir
    context.battle_seed = seed
    campaign_log: campaign_log_module.CampaignLogger | None = None
    if campaign_log_dir is not None:
        campaign_log = campaign_log_module.CampaignLogger(campaign_log_module.default_log_path(campaign_log_dir))
        context.campaign_log = campaign_log
        campaign_log.session_start(no_battle=no_battle, save_dir=save_dir, glue_program=glue_program,
                                   battle=battle, skip_intro=skip_intro, seed=seed,
                                   battle_log_dir=log_dir, trace_glue=campaign_log.trace_glue)
    ctx = open_window(size, hidden)
    gpu = Gpu(ctx, size)
    # Wider debug overlay; unrelated to the battle HUD.
    overlay = gpu.text((820, 140))
    initial: Scene = (GlueScene(glue_program) if glue_program else
               BattleScene(AssetId("vanilla", "battle", Path(battle).stem.casefold()), log_dir=log_dir, seed=seed)
               if battle else OpeningNarrationScene(log_dir=log_dir, seed=seed))
    machine = SceneMachine(initial, context)
    options: dict[str, Any] = {"camera": camera, "installation": context.locator.installation}
    view = view_for(gpu, machine.active, options)
    profile: FrameProfile | None = None
    profile_owner: int | None = None

    def profile_name() -> str | None:
        if not profile_frames or not isinstance(machine.active, GlueScene):
            return None
        runtime = machine.active.runtime
        return "/".join(window.name for window in runtime.state.windows) if runtime is not None and runtime.state.windows else "<empty>"

    def sync_profile() -> None:
        nonlocal profile, profile_owner
        name = profile_name()
        owner = id(machine.active) if name is not None else None
        if profile is not None and (profile.name != name or profile_owner != owner):
            profile.report()
            profile = None
            profile_owner = None
        if name is not None and profile is None:
            profile = FrameProfile(name)
            profile_owner = owner

    sync_profile()
    clock = FixedStepClock(FIXED_STEP, MAX_STEPS_PER_FRAME)
    rate = FrameRate()
    limiter = pygame.time.Clock()
    fade_remaining = FADE_SECONDS  # fade in from black on the initial scene too

    def synchronise(current: SceneView[Any]) -> SceneView[Any]:
        nonlocal fade_remaining
        if current.scene is machine.active:
            return current
        current.release()
        CursorController.restore_arrow()  # the next view sets its own cursor; none must leak from this one
        fade_remaining = FADE_SECONDS
        next_view = view_for(gpu, machine.active, options)
        sync_profile()
        return next_view

    if skip_intro and not battle:
        machine.handle("skip")
        view = synchronise(view)
    frame, last, overlay_time, running, show_overlay = 0, time.perf_counter(), float("-inf"), True, True
    battle_log_path = None  # tracked across scene transitions so it survives a battle -> result switch
    try:
        while running:
            if isinstance(machine.active, BattleScene) and machine.active.logger is not None:
                battle_log_path = machine.active.logger.path or battle_log_path
            now = time.perf_counter()
            elapsed, last = now - last, now
            phase_start = time.perf_counter() if profile is not None else 0.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL
                ):
                    running = False
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
                    show_overlay = not show_overlay
                    continue
                for scene_event in view.events(event):
                    machine.handle(scene_event)
                    view = synchronise(view)
                    view.refresh()
                    sync_profile()
                    if machine.quit is not None:
                        running = False

            if profile is not None and phase_start:
                profile.add("events", time.perf_counter() - phase_start)

            seconds = elapsed if frame_time is None else frame_time
            steps = clock.advance(seconds)
            # Battle updates follow the frame's elapsed time once, so a slow frame
            # cannot turn into several deployment/script updates through the UI clock.
            updates = (seconds,) if isinstance(machine.active, BattleScene) else (clock.step,) * steps
            for update_seconds in updates:
                phase_start = time.perf_counter() if profile is not None else 0.0
                machine.update(update_seconds)
                if profile is not None:
                    profile.add("update", time.perf_counter() - phase_start)
                view = synchronise(view)
                phase_start = time.perf_counter() if profile is not None else 0.0
                view.refresh()
                if profile is not None:
                    profile.add("refresh", time.perf_counter() - phase_start)
                sync_profile()
                if machine.quit is not None:
                    running = False
            if running:
                phase_start = time.perf_counter() if profile is not None else 0.0
                view.animate(seconds)
                if profile is not None:
                    profile.add("animate", time.perf_counter() - phase_start)
            fade_remaining = max(0.0, fade_remaining - seconds)

            rate.frame(now)
            if now - overlay_time >= OVERLAY_REFRESH_SECONDS or frames is not None:
                overlay_time = now
                overlay.set_lines((
                    f"FPS {rate.value:.0f}", f"tick {clock.ticks}", f"scene {type(machine.active).__name__}",
                    *view.status(),
                ))

            phase_start = time.perf_counter() if profile is not None else 0.0
            ctx.new_frame()
            view.draw()
            if fade_remaining > 0:
                alpha = fade_remaining / FADE_SECONDS
                gpu.fade.draw(0, 0, *gpu.target.size, tint=(0.0, 0.0, 0.0, alpha))
            if show_overlay:
                overlay.draw(8, 8)
            if profile is not None:
                profile.add("draw", time.perf_counter() - phase_start)
            phase_start = time.perf_counter() if profile is not None else 0.0
            gpu.target.present()
            ctx.end_frame()
            if profile is not None:
                profile.add("present", time.perf_counter() - phase_start)
            frame += 1
            if frames is not None and frame >= frames:
                if screenshot is not None:
                    gpu.target.save_png(screenshot)
                running = False
            phase_start = time.perf_counter() if profile is not None else 0.0
            pygame.display.flip()
            if profile is not None:
                profile.add("flip", time.perf_counter() - phase_start)
            phase_start = time.perf_counter() if profile is not None else 0.0
            limiter.tick(MAX_FRAMES_PER_SECOND)
            if profile is not None:
                profile.add("limit", time.perf_counter() - phase_start)
                profile.add("frame", time.perf_counter() - now)
    finally:
        if profile is not None:
            profile.report()
        # The window can close or Ctrl+Q can fire mid-battle, bypassing the scene machine's own
        # transition/exit path (`machine.quit` above only covers a Quit a scene itself returns): make
        # sure an open battle log is still finalized so it stays a usable, complete record.
        if isinstance(machine.active, BattleScene):
            machine.active.close_log("player quit" if machine.quit is None else machine.quit.reason)
            if machine.active.logger is not None and machine.active.logger.path:
                battle_log_path = machine.active.logger.path
        view.release()
        pygame.quit()
        if campaign_log is not None:
            campaign_log.session_end("player quit" if machine.quit is None else machine.quit.reason,
                                     frames=frame, scene=type(machine.active).__name__)
            campaign_log.close()
    if battle_log_path is not None:
        print(f"Battle log: {battle_log_path}")
    if campaign_log is not None and campaign_log.path is not None:
        print(f"Campaign log: {campaign_log.path}")
    return {
        "frames": frame, "ticks": clock.ticks, "scene": type(machine.active).__name__,
        "quit": machine.quit.reason if machine.quit is not None else None,
    }
