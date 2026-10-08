# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle result scene: shown once a standalone battle resolves to victory or defeat (engine step 5).

Kept separate from `whshr.campaign_scenes` (which this module would otherwise create an import
cycle with, since it imports `whshr.battle_scene.BattleScene`) by importing `MainMenuScene` lazily,
inside `handle`, rather than at module load time.
"""
from .scenes import Quit, Scene, SceneAssets, SceneEvent, Transition

DISMISS_EVENTS: tuple[str, ...] = ("continue", "dismiss")


class ResultScene(Scene):
    """Shows a standalone battle's outcome and a short casualty summary, then returns to the main menu.

    A battle a glue program started never shows it: the flow goes straight on to the debrief
    (notes/native-windows.md 9.11, scenario 4; `BattleScene.update`).
    """

    def __init__(self, result: str, summary: list[str]) -> None:
        self.result = result  # "victory" or "defeat" (whshr.engine.Battle.result)
        self.summary = summary  # list of short strings, e.g. "Grudgebringer Infantry: 12/16 models"

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if event in DISMISS_EVENTS:
            from .campaign_scenes import MainMenuScene
            return Transition(MainMenuScene(), "battle result acknowledged")
        return None
