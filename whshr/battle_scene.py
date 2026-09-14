"""Battle scene: owns one loaded battlefield and advances its deterministic simulation."""

from .assets import AssetId
from .clock import FixedStepClock
from .engine import Battle
from .scenes import Scene, SceneManifest

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

    def enter(self, context):
        self.field = context.load(self.battle_id)
        self.battle = Battle.from_script(self.field.script)

    def exit(self, context):
        # Terrain, scenery and sprites are battle-scoped: leaving the battle releases them.
        context.cache.release(self.battle_id)

    def update(self, seconds, context):
        super().update(seconds, context)
        for _ in range(self.clock.advance(seconds)):
            self.battle.tick(BATTLE_TICK_SECONDS)
        return None
