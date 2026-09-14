"""Scene view registry: which view presents which scene type."""

from ..battle_scene import BattleScene
from ..campaign_scenes import BriefingScene, IntroScene, MainMenuScene
from ..result_scene import ResultScene
from .battle_view import BattleView
from .intro_view import IntroView
from .menu_view import BriefingView, MainMenuView
from .result_view import ResultView
from .scene_view import PlaceholderView

VIEWS = {
    IntroScene: IntroView,
    MainMenuScene: MainMenuView,
    BriefingScene: BriefingView,
    BattleScene: BattleView,
    ResultScene: ResultView,
}


def view_for(gpu, scene, options=None):
    return VIEWS.get(type(scene), PlaceholderView)(gpu, scene, options)
