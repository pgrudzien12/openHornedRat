"""Battle result scene: shown once a battle resolves to victory or defeat (engine step 5).

Kept separate from `whshr.campaign_scenes` (which this module would otherwise create an import
cycle with, since it imports `whshr.battle_scene.BattleScene`) by importing `MainMenuScene` lazily,
inside `handle`, rather than at module load time.
"""
from .scenes import Scene, Transition

DISMISS_EVENTS = ("continue", "dismiss")


class ResultScene(Scene):
    """Shows the battle's outcome and a short casualty summary; any dismissal returns to the menu."""

    def __init__(self, result, summary):
        self.result = result  # "victory" or "defeat" (whshr.engine.Battle.result)
        self.summary = summary  # list of short strings, e.g. "Grudgebringer Infantry: 12/16 models"

    def handle(self, event, context):
        if event in DISMISS_EVENTS:
            from .campaign_scenes import MainMenuScene
            return Transition(MainMenuScene(), "battle result acknowledged")
        return None
