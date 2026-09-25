# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Shared lazy-asset context for the campaign scene flow, consumed by the real-time engine."""
from os import PathLike
from pathlib import Path
from typing import Any

from .assets import AssetLocator
from .battlefield import load_battlefield
from .briefing import load_briefing
from .cache import AssetCache, Loader
from .catalog import AssetRecord
from .campaign_scenes import default_scene_loaders
from .catalog import build
from .glue_content import GlueContent
from .scenes import SceneAssets
from .paths import Installation
from .si import process_si


def scene_context(installation: Installation | str | PathLike[str], loaders: dict[str, Loader] | None = None,
                  save_dir: str | PathLike[str] | None = None, no_battle: bool = False) -> SceneAssets:
    """Validate an installation and return the lazy asset access shared by all scenes.

    ``save_dir`` is the engine's own save directory (never the original installation's SAVE/,
    notes/glue_engine_integration.md GEI7e). ``no_battle`` turns on the campaign-progression
    shortcut (every `BattleScene` it reaches settles as an immediate, lossless win instead of
    being simulated; whshr.engine.Battle.resolve_no_battle).
    """
    locator = AssetLocator(installation)
    locator.validate()
    glue = GlueContent(locator.installation)
    if loaders is None:
        def load_glue(record: AssetRecord, _path: Path) -> Any:
            kind, name = record.identifier.kind, record.identifier.name
            if kind == "glue-window":
                return glue.window(name)
            if kind == "glue-program":
                return glue.program(name)
            if kind == "bitmap":
                return glue.bitmap_data(name)
            if kind == "string":
                return glue.strings(name)
            raise ValueError(f"unsupported glue content asset: {record.identifier}")

        loaders = {
            **default_scene_loaders(),
            "battle-script": lambda _record, path: load_battlefield(locator.installation, path),
            "omni-si-media": lambda _record, path: process_si(path),
            "campaign-briefing": lambda record, _path: load_briefing(
                locator.installation, record.identifier.name, content=glue
            ),
            "glue-content": load_glue,
        }
    return SceneAssets(locator, build(locator.installation), AssetCache(), loaders, glue=glue, save_dir=save_dir,
                       no_battle=no_battle)
