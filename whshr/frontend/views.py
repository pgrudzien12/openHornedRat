"""Scene view registry: which view presents which scene type."""

from ..battle_scene import BattleScene
from ..campaign_scenes import (
    BriefingScene, MainMenuScene, MissionMapScene, MovieScene, OpeningNarrationScene,
    ArmyRecordsScene, TroopSelectScene, TroopSelectionScene,
)
from ..glue_scene import GlueScene
from ..result_scene import ResultScene
from .battle_view import BattleView
from .movie_view import MovieView
from .briefing_view import BriefingView
from .glue_view import GlueView
from .menu_view import MainMenuView
from .mission_map_view import MissionMapView
from .opening_view import OpeningNarrationView
from .result_view import ResultView
from .scene_view import PlaceholderView
from .troop_selection_view import TroopSelectionView
from .army_records_view import ArmyRecordsView

VIEWS = {
    OpeningNarrationScene: OpeningNarrationView,
    MovieScene: MovieView,
    MainMenuScene: MainMenuView,
    MissionMapScene: MissionMapView,
    TroopSelectScene: PlaceholderView,
    TroopSelectionScene: TroopSelectionView,
    ArmyRecordsScene: ArmyRecordsView,
    BriefingScene: BriefingView,
    GlueScene: GlueView,
    BattleScene: BattleView,
    ResultScene: ResultView,
}


def view_for(gpu, scene, options=None):
    return VIEWS.get(type(scene), PlaceholderView)(gpu, scene, options)
