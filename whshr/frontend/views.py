"""Scene view registry: which view presents which scene type."""

from ..battle_scene import BattleScene
from ..campaign_scenes import (
    BriefingScene, CaravanScene, IntroScene, MainMenuScene, MissionMapScene, OpeningNarrationScene,
    TroopSelectScene,
)
from ..glue_scene import GlueScene
from ..result_scene import ResultScene
from .battle_view import BattleView
from .caravan_view import CaravanView
from .intro_view import IntroView
from .briefing_view import BriefingView
from .glue_view import GlueView
from .menu_view import MainMenuView
from .mission_map_view import MissionMapView
from .opening_view import OpeningNarrationView
from .result_view import ResultView
from .scene_view import PlaceholderView

VIEWS = {
    OpeningNarrationScene: OpeningNarrationView,
    IntroScene: IntroView,
    MainMenuScene: MainMenuView,
    CaravanScene: CaravanView,
    MissionMapScene: MissionMapView,
    TroopSelectScene: PlaceholderView,
    BriefingScene: BriefingView,
    GlueScene: GlueView,
    BattleScene: BattleView,
    ResultScene: ResultView,
}


def view_for(gpu, scene, options=None):
    return VIEWS.get(type(scene), PlaceholderView)(gpu, scene, options)
