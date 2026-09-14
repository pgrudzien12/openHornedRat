"""Temporary game runner that drives the campaign scene state machine."""

from pathlib import Path
import shutil
import subprocess
import tempfile

from .assets import AssetLocator
from .battlefield import load_battlefield
from .cache import AssetCache
from .campaign_scenes import IntroScene, MainMenuScene, default_scene_loaders
from .catalog import build
from .scenes import SceneAssets, SceneMachine
from .si import process_si


def _smacker_path(summary, output):
    for object_ in summary["objects"].values():
        if "smk" in object_ and "output" in object_:
            return Path(output) / Path(summary["file"]).stem / object_["output"]
    raise ValueError(f"{summary['file']} has no extracted Smacker video")


def scene_context(installation, loaders=None):
    """Validate an installation and return the lazy asset access shared by all scenes."""
    locator = AssetLocator(installation)
    locator.validate()
    if loaders is None:
        loaders = {
            **default_scene_loaders(),
            "battle-script": lambda _record, path: load_battlefield(locator.installation, path),
        }
    return SceneAssets(locator, build(locator.installation), AssetCache(), loaders)


def start(installation, player="ffplay", skip_intro=False, loaders=None):
    """Start the current game flow and return after it has reached the menu state."""
    context = scene_context(installation, loaders)
    locator, catalog = context.locator, context.catalog
    machine = SceneMachine(IntroScene(), context)

    if skip_intro:
        machine.handle("skip")
    else:
        executable = shutil.which(player)
        if executable is None:
            raise FileNotFoundError(f"cutscene player not found on PATH: {player}")
        with tempfile.TemporaryDirectory(prefix="whshr-intro-") as temporary:
            source = catalog.resolve(locator.installation, "vanilla:cutscene/a1")
            video = _smacker_path(process_si(source, temporary), temporary)
            print(f"Playing intro: {video.name}")
            # Smacker's header rate is not the game's playback rate. Re-time each decoded
            # frame to the verified 125 ms engine cadence without requiring ffplay's removed -r option.
            result = subprocess.run((
                executable, "-autoexit", "-loglevel", "error", "-vf", "setpts=N/(8*TB)", str(video),
            ))
            if result.returncode:
                raise RuntimeError(f"cutscene player exited with status {result.returncode}")
        machine.update(machine.active.duration_seconds)

    if not isinstance(machine.active, MainMenuScene):
        raise RuntimeError("intro flow did not reach the main menu")
    print("Main menu reached.")
    return machine
