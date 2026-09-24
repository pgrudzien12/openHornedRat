"""Battle result scene: shown once a battle resolves to victory or defeat (engine step 5).

Kept separate from `whshr.campaign_scenes` (which this module would otherwise create an import
cycle with, since it imports `whshr.battle_scene.BattleScene`) by importing `MainMenuScene` lazily,
inside `handle`, rather than at module load time.
"""
from .glue_runtime import ActivityResult
from .scenes import Scene, Transition

DISMISS_EVENTS = ("continue", "dismiss")


class ResultScene(Scene):
    """Shows the battle's outcome and a short casualty summary.

    A battle a glue program started (`glue_scene` + `request_id`) hands back to that program on
    dismissal, resolving its pending battle request so the campaign continues (notes/activity_results.md
    §2.1: the flow decides what a win or a loss means); a standalone battle returns to the main menu.
    """

    def __init__(self, result, summary, glue_scene=None, request_id=None):
        self.result = result  # "victory" or "defeat" (whshr.engine.Battle.result)
        self.summary = summary  # list of short strings, e.g. "Grudgebringer Infantry: 12/16 models"
        self.glue_scene = glue_scene
        self.request_id = request_id

    def handle(self, event, context):
        if event in DISMISS_EVENTS:
            if self.glue_scene is not None:
                self.glue_scene.complete_activity(ActivityResult(self.request_id, "battle"))
                return Transition(self.glue_scene, "glue battle resolved")
            from .campaign_scenes import MainMenuScene
            return Transition(MainMenuScene(), "battle result acknowledged")
        return None
