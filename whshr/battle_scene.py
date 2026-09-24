"""Battle scene: owns one loaded battlefield and advances its deterministic simulation."""

import os

from . import battle_log, behaviour, combat, skirmish_log
from .assets import AssetId
from .battlefield import sprite_files
from .clock import FixedStepClock
from .engine import Battle, DEFAULT_SEED
from .glue_runtime import ActivityResult
from .result_scene import ResultScene
from .scenes import Scene, SceneManifest, Transition

BATTLE_TICK_SECONDS = 0.1  # the original battle clock ticks every 100 ms
FIRST_BATTLE = AssetId("vanilla", "battle", "bf001")


class BattleScene(Scene):
    """Loads a battle through the scene assets and runs its simulation on fixed 100 ms ticks.

    `log_dir`, when given, turns on a `whshr.battle_log.BattleLogger` for this battle (JSON Lines under
    `log_dir`, one file per battle, named by `battle_log.default_log_path`); `log_dir=None` disables
    logging. `seed` is threaded into `Battle.from_script` so a recorded battle and its replay start
    from the same deterministic state (notes/engine_architecture.md, "Battle logs and replay").
    """

    def __init__(self, battle=FIRST_BATTLE, log_dir=None, seed=DEFAULT_SEED, glue_scene=None, request_id=None):
        self.battle_id = battle
        self.manifest = SceneManifest(immediate=(battle,))
        self.field = None
        self.battle = None
        self.clock = FixedStepClock(BATTLE_TICK_SECONDS)
        self.selected_id = None  # identifier of the player regiment currently selected, if any
        self.log_dir = log_dir
        self.seed = seed
        self.logger = None
        self.skirmishes = None  # whshr.skirmish_log.SkirmishLogger, one file per close combat
        self._log_closed = True
        self.glue_scene = glue_scene
        self.request_id = request_id

    def enter(self, context):
        self.field = context.load(self.battle_id)
        script_dll = self._load_script_dll(context)
        # The logger must exist before Battle.from_script so ScriptInterpreter can be handed it
        # directly (script_logger=); WHSHR_TRACE_SCRIPTS=1 turns on its per-opcode trace records
        # (issue #3/#46, "proper logging" for debugging mission scripts -- off by default, since
        # it is far higher volume than the rest of the battle log).
        path = battle_log.default_log_path(self.log_dir, self.battle_id.name) if self.log_dir is not None else None
        self.logger = battle_log.BattleLogger(path, trace_scripts=bool(os.environ.get("WHSHR_TRACE_SCRIPTS")))
        self.battle = Battle.from_script(self.field.script, seed=self.seed, script_dll=script_dll,
                                         script_logger=self.logger)
        self.initial_models = {identifier: regiment.models for identifier, regiment in self.battle.regiments.items()}
        if getattr(context, "no_battle", False):
            self.battle.resolve_no_battle()
        self.skirmishes = skirmish_log.SkirmishLogger(self.log_dir, self.battle_id.name)
        self._log_closed = False
        if self.logger.enabled:
            try:
                sprite_bases = sprite_files(context.locator.installation, "troops")
            except Exception:  # a header must never block the battle; sprite_base then stays unresolved
                sprite_bases = {}
            self.logger.write_header(
                battle_asset=str(self.battle_id), bts_path=self.field.script.get("file"), seed=self.seed,
                width=self.battle.width, height=self.battle.height,
                regiments=battle_log.regiment_header_rows(self.battle, sprite_bases))

    def _load_script_dll(self, context):
        """Load this battle's SCRIPT/BFxxx.DLL (its `loadScript` name) for the bytecode interpreter
        (issue #3/#46); None if the field has no loadScript name or the DLL can't be found or loaded,
        in which case `Battle` drives no regiment automatically. A missing/broken script DLL must
        never block the battle from starting (same defensive stance as sprite_bases above)."""
        name = self.field.script.get("field", {}).get("script")
        if not name:
            return None
        try:
            path = context.locator.installation.find("FILE", "SCRIPT", f"{name}.DLL")
            return behaviour.ScriptDll(path) if path is not None else None
        except Exception:
            return None

    def exit(self, context):
        # Terrain, scenery and sprites are battle-scoped: leaving the battle releases them.
        self.close_log("scene left")
        context.cache.release(self.battle_id)

    def close_log(self, reason):
        """Write the `end` record and close the log file; idempotent, so both a normal transition and
        an early frontend shutdown (the player closing the window mid-battle) can safely call it."""
        if self.logger is not None and not self._log_closed:
            self.logger.write_end(self.battle.tick_count if self.battle is not None else 0, reason)
            if self.skirmishes is not None:
                self.skirmishes.close(self.battle)
            self._log_closed = True

    def handle(self, event, context):
        """Player intent from the view: select, move, attack, halt or deselect."""
        if self.logger is not None and self.logger.enabled:
            self.logger.write_order(self.battle.tick_count, event)
        kind, *args = event
        if kind == "select":
            # An enemy regiment can be selected too, for its readout/banner/stats only: the
            # order handlers below all refuse a non-player identifier (ValueError, caught), so
            # selecting one never grants it orders.
            (identifier,) = args
            if identifier in self.battle.regiments:
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
        elif kind == "halt":
            if self.selected_id is not None:
                try:
                    self.battle.order_halt(self.selected_id)
                except ValueError:
                    pass  # no player selection, or the unit is routing/in melee
        return None

    def update(self, seconds, context):
        super().update(seconds, context)
        for _ in range(self.clock.advance(seconds)):
            tick_number = self.battle.tick_count
            self.battle.tick(BATTLE_TICK_SECONDS)
            if self.logger is not None and self.logger.enabled:
                for battle_event in self.battle.events:
                    self.logger.write_event(tick_number, battle_event)
                if self.battle.tick_count % combat.SEGMENT_TICKS == 0:
                    self.logger.write_snapshot(self.battle.tick_count, self.battle)
            if self.skirmishes is not None:
                self.skirmishes.observe(self.battle)
            if self.battle.result is not None:
                break
        if self.battle.result is not None:
            if self.logger is not None and self.logger.enabled:
                self.logger.write_snapshot(self.battle.tick_count, self.battle)
                self.logger.write_result(self.battle.tick_count, self.battle)
                self.close_log("result")
            if self.glue_scene is not None:
                self.glue_scene.complete_activity(ActivityResult(self.request_id, "battle"))
                return Transition(self.glue_scene, "glue battle resolved")
            return Transition(ResultScene(self.battle.result, self._casualty_summary()), "battle resolved")
        return None

    def _casualty_summary(self):
        return [f"{regiment.name}: {regiment.models}/{self.initial_models[identifier]} models"
                for identifier, regiment in sorted(self.battle.regiments.items())]
