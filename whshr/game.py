"""Shared lazy-asset context for the campaign scene flow, consumed by the real-time engine."""

from .assets import AssetLocator
from .battlefield import load_battlefield
from .briefing import load_briefing
from .cache import AssetCache
from .campaign_scenes import default_scene_loaders
from .catalog import build
from .scenes import SceneAssets
from .si import process_si


def scene_context(installation, loaders=None):
    """Validate an installation and return the lazy asset access shared by all scenes."""
    locator = AssetLocator(installation)
    locator.validate()
    if loaders is None:
        loaders = {
            **default_scene_loaders(),
            "battle-script": lambda _record, path: load_battlefield(locator.installation, path),
            "omni-si-media": lambda _record, path: process_si(path),
            "campaign-briefing": lambda record, _path: load_briefing(
                locator.installation, record.identifier.name
            ),
        }
    return SceneAssets(locator, build(locator.installation), AssetCache(), loaders)
