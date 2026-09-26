# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Saving and restoring a chain of glue scenes (``notes/save_resume.md``, engine version).

What a save has to bring back is the campaign's *scenes*: the scene the player is in (a mission script with its
caravan open, say) and the scenes parked beneath it (the map its mission returns to, the caravan a map's
Caravan button returns to). Each scene is saved with its own interpreter state (:mod:`whshr.glue_state`); the
links between scenes are indices into the saved list, so the cycle between a map and its caravan is fine.
"""

from typing import Any

from .campaign_state import CampaignState
from .glue_content import GlueContent
from .glue_runtime import GlueRuntime, GlueRuntimeState
from .glue_scene import GlueScene
from .glue_state import CODEC, decode_state, encode_state
from .scenes import Scene


def snapshot_chain(root: Scene, overrides: dict[int, GlueRuntimeState] | None = None) -> dict[str, Any] | None:
    """The scene chain reachable from ``root`` as JSON-ready data, or None when a scene in it is not a glue scene
    (a chain that cannot be restored is not saved).

    ``overrides`` maps ``id(scene)`` to the interpreter state to save instead of its current one (the autosave
    state, taken at the ``autosave:`` line while the script has since run on)."""
    overrides = overrides or {}
    scenes: list[GlueScene] = []
    pending: list[Scene | None] = [root]
    while pending:
        scene = pending.pop()
        if scene is None or scene in scenes:
            continue
        if not isinstance(scene, GlueScene) or scene.runtime is None:
            return None
        scenes.append(scene)
        pending.append(scene.return_scene)
        pending.append(scene.caravan_return[0] if scene.caravan_return else None)

    def index(scene: Scene | None) -> int | None:
        return None if scene is None else scenes.index(scene)  # type: ignore[arg-type]

    saved: list[dict[str, Any]] = []
    for scene in scenes:
        runtime = scene.runtime
        assert runtime is not None
        saved.append({
            "program": scene.program, "window": scene.window, "record_battle": scene.record_battle,
            "record_debrief": scene.record_debrief, "accept_battle": scene.accept_battle,
            "accept_mission": CODEC.encode(scene.accept_mission), "speech_enabled": scene.speech_enabled,
            "is_fallback": scene.is_fallback, "mission_released": scene.mission_released,
            "return_scene": index(scene.return_scene),
            "caravan_return": ([index(scene.caravan_return[0]), scene.caravan_return[1]]
                               if scene.caravan_return else None),
            "state": encode_state(overrides.get(id(scene), runtime.state)),
        })
    return {"root": 0, "scenes": saved}


def restore_chain(data: dict[str, Any], campaign: CampaignState, content: GlueContent) -> GlueScene:
    """Rebuild the scenes of :func:`snapshot_chain` on ``campaign`` and return the one the player was in.

    A scene that was running when it was saved (an ``autosave:`` snapshot) is stepped on until it blocks."""
    scenes: list[GlueScene] = []
    for item in data["scenes"]:
        scene = GlueScene(program=item["program"], window=item["window"], record_battle=item["record_battle"],
                          record_debrief=item["record_debrief"], campaign=campaign,
                          speech_enabled=item["speech_enabled"], accept_battle=item["accept_battle"],
                          accept_mission=CODEC.decode(item["accept_mission"]))
        scene.is_fallback = item["is_fallback"]
        scene.mission_released = item["mission_released"]
        scene.runtime = GlueRuntime(content, campaign, speech_enabled=item["speech_enabled"])
        scene.runtime.state = decode_state(item["state"])
        scenes.append(scene)
    for scene, item in zip(scenes, data["scenes"]):
        if item["return_scene"] is not None:
            scene.return_scene = scenes[item["return_scene"]]
        if item["caravan_return"] is not None:
            scene.caravan_return = (scenes[item["caravan_return"][0]], item["caravan_return"][1])
    for scene in scenes:
        state = scene.runtime.state  # type: ignore[union-attr]
        if state.current is not None and state.pending is None and state.wait_reason is None:
            scene.resume_running()
    return scenes[data["root"]]
