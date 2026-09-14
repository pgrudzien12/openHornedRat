"""Battle scene: owns one loaded battlefield and advances its deterministic simulation."""

from .assets import AssetId
from .clock import FixedStepClock
from .engine import Battle
from .result_scene import ResultScene
from .scenes import Scene, SceneManifest, Transition

BATTLE_TICK_SECONDS = 0.1  # the original battle clock ticks every 100 ms
FIRST_BATTLE = AssetId("vanilla", "battle", "bf001")


class BattleScene(Scene):
    """Loads a battle through the scene assets and runs its simulation on fixed 100 ms ticks."""

    def __init__(self, battle=FIRST_BATTLE):
        self.battle_id = battle
        self.manifest = SceneManifest(immediate=(battle,))
        self.field = None
        self.battle = None
        self.clock = FixedStepClock(BATTLE_TICK_SECONDS)
        self.selected_id = None  # identifier of the player regiment currently selected, if any

    def enter(self, context):
        self.field = context.load(self.battle_id)
        self.battle = Battle.from_script(self.field.script)
        self.initial_models = {identifier: regiment.models for identifier, regiment in self.battle.regiments.items()}

    def exit(self, context):
        # Terrain, scenery and sprites are battle-scoped: leaving the battle releases them.
        context.cache.release(self.battle_id)

    def handle(self, event, context):
        """Player intent from the view: ("select", id), ("deselect",), ("move_to", x, y) or
        ("attack", enemy_id)."""
        kind, *args = event
        if kind == "select":
            (identifier,) = args
            if identifier in self.battle.regiments and self.battle.regiments[identifier].player:
                self.selected_id = identifier
        elif kind == "deselect":
            self.selected_id = None
        elif kind == "move_to":
            x, y = args
            if self.selected_id is not None:
                try:
                    self.battle.order_move(self.selected_id, x, y)
                except ValueError:
                    pass  # outside the field, the selection is routing, or it is no longer player-controlled
        elif kind == "attack":
            (target_id,) = args
            if self.selected_id is not None:
                try:
                    self.battle.order_attack(self.selected_id, target_id)
                except ValueError:
                    pass  # not an enemy regiment, the selection is routing, or the target is gone
        return None

    def update(self, seconds, context):
        super().update(seconds, context)
        for _ in range(self.clock.advance(seconds)):
            self.battle.tick(BATTLE_TICK_SECONDS)
            if self.battle.result is not None:
                break
        if self.battle.result is not None:
            return Transition(ResultScene(self.battle.result, self._casualty_summary()), "battle resolved")
        return None

    def _casualty_summary(self):
        return [f"{regiment.name}: {regiment.models}/{self.initial_models[identifier]} models"
                for identifier, regiment in sorted(self.battle.regiments.items())]
