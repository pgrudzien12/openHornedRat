# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""JSON Lines battle controller with the real GPU view and deterministic scene ticks.

One input line is one command. Each response is one JSON line on stdout. The process
keeps the battle and OpenGL context alive between commands; image files stay local.
"""

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

from ..assets import AssetId
from ..battle_auto import camera_values, describe, parse_order, target_values
from ..battle_scene import BATTLE_TICK_SECONDS, BattleScene
from ..engine import DEFAULT_SEED
from ..game import scene_context
from ..scenes import SceneMachine
from .app import open_window
from .battle_view import BattleView
from .gpu import Gpu
from .scene_view import SceneView
from .views import view_for


class BattleSession:
    """Own one direct-entry battle and its view for a local control session."""

    def __init__(self, installation: str | os.PathLike[str], battle: str = "BF001",
                 size: tuple[int, int] = (1280, 800), seed: int = DEFAULT_SEED,
                 log_dir: str | os.PathLike[str] | None = None,
                 camera: Sequence[float] | None = None) -> None:
        if camera is not None:
            camera = camera_values(camera)
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        self.context = scene_context(installation)
        self.scene = BattleScene(AssetId("vanilla", "battle", Path(battle).stem.casefold()),
                                 log_dir=log_dir, seed=seed)
        self.gpu = Gpu(open_window(size, hidden=True), size)
        self.machine = SceneMachine(self.scene, self.context)
        self.options: dict[str, Any] = {"camera": camera, "installation": self.context.locator.installation}
        self.view: SceneView[Any] = view_for(self.gpu, self.machine.active, self.options)
        self.view.refresh()

    def _sync_view(self) -> None:
        if self.view.scene is not self.machine.active:
            self.view.release()
            self.view = view_for(self.gpu, self.machine.active, self.options)
        self.view.refresh()

    def command(self, command: dict[str, Any]) -> dict[str, Any]:
        op = command.get("op")
        if op == "state":
            return {"ok": True, "state": describe(self.scene)}
        if op == "order":
            if self.machine.active is not self.scene:
                raise ValueError("battle has ended")
            event = parse_order(command)
            self.machine.handle(event)
            self._sync_view()
            return {"ok": True, "event": event, "state": describe(self.scene)}
        if op == "step":
            count = command.get("ticks", 1)
            if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 10000:
                raise ValueError("ticks must be an integer from 0 to 10000")
            advanced = 0
            for _ in range(count):
                if self.machine.active is not self.scene:
                    break
                self.machine.update(BATTLE_TICK_SECONDS)
                self._sync_view()
                # BattleView.animate publishes camera geometry to Battle and can re-snap wagons.
                # Those view changes are not scene orders in the replay log. This controller
                # runs the same headless simulation as battle-replay; camera is for captures only.
                advanced += 1
            return {"ok": True, "advanced": advanced, "state": describe(self.scene)}
        if op == "capture":
            path = command.get("path")
            if not isinstance(path, str) or not path:
                raise ValueError("capture needs a nonempty path")
            output = Path(path)
            output.parent.mkdir(parents=True, exist_ok=True)
            self.gpu.ctx.new_frame()
            try:
                self.view.draw()
                self.gpu.target.save_png(output)
            finally:
                self.gpu.ctx.end_frame()
            return {"ok": True, "path": str(output), "state": describe(self.scene)}
        if op == "camera":
            if not isinstance(self.view, BattleView):
                raise ValueError("camera is only available during a battle")
            yaw, pitch, distance = camera_values(command.get("values"))
            self.view.camera.yaw = yaw
            self.view.camera.pitch = pitch
            self.view.camera.distance = distance
            self.view.camera.set_target(self.view.camera.target_x, self.view.camera.target_y)
            return {"ok": True, "camera": [self.view.camera.yaw, self.view.camera.pitch,
                                            self.view.camera.distance]}
        if op == "target":
            if not isinstance(self.view, BattleView):
                raise ValueError("camera target is only available during a battle")
            x, y = target_values(command.get("point"))
            self.view.camera.set_target(x, y)
            return {"ok": True, "target": [self.view.camera.target_x, self.view.camera.target_y]}
        raise ValueError(f"unknown operation: {op}")

    def close(self) -> None:
        self.scene.close_log("automated session closed")
        self.view.release()
        pygame.quit()


def run(installation: str | os.PathLike[str], battle: str = "BF001",
        size: tuple[int, int] = (1280, 800), seed: int = DEFAULT_SEED,
        log_dir: str | os.PathLike[str] | None = None,
        camera: Sequence[float] | None = None) -> None:
    """Read commands until EOF; errors are returned as JSON so the session stays usable."""
    session = BattleSession(installation, battle, size, seed, log_dir, camera)
    try:
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    raise ValueError("command must be a JSON object")
                response = session.command(command)
            except (ValueError, KeyError, TypeError, OSError) as error:
                response = {"ok": False, "error": str(error)}
            print(json.dumps(response, separators=(",", ":")), flush=True)
    finally:
        session.close()
