# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Scene view registry: which view presents which scene type."""
from typing import Any

from ..scenes import Scene
from .gpu import Gpu

from ..battle_scene import BattleScene
from ..campaign_scenes import (
    BriefingScene, MainMenuScene, MissionMapScene, MovieScene, OpeningNarrationScene,
    ArmyRecordsScene, TroopSelectScene, TroopSelectionScene,
)
from ..glue_scene import GlueScene
from ..load_save_scene import LoadSaveScene
from ..result_scene import ResultScene
from .battle_view import BattleView
from .movie_view import MovieView
from .briefing_view import BriefingView
from .glue_view import GlueView
from .load_save_view import LoadSaveView
from .menu_view import MainMenuView
from .mission_map_view import MissionMapView
from .opening_view import OpeningNarrationView
from .result_view import ResultView
from .scene_view import PlaceholderView, SceneView
from .troop_selection_view import TroopSelectionView
from .army_records_view import ArmyRecordsView

VIEWS: dict[type[Scene], type[SceneView[Any]]] = {
    OpeningNarrationScene: OpeningNarrationView,
    MovieScene: MovieView,
    MainMenuScene: MainMenuView,
    MissionMapScene: MissionMapView,
    TroopSelectScene: PlaceholderView,
    TroopSelectionScene: TroopSelectionView,
    ArmyRecordsScene: ArmyRecordsView,
    BriefingScene: BriefingView,
    GlueScene: GlueView,
    LoadSaveScene: LoadSaveView,
    BattleScene: BattleView,
    ResultScene: ResultView,
}


def view_for(gpu: Gpu, scene: Scene, options: dict[str, Any] | None = None) -> SceneView[Any]:
    return VIEWS.get(type(scene), PlaceholderView)(gpu, scene, options)
