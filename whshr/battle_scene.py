# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle scene: owns one loaded battlefield and advances its deterministic simulation."""

import os
from os import PathLike
from . import battle_log, behaviour, combat, payments, skirmish_log
from .assets import AssetId
from .battlefield import Battlefield, sprite_files
from .clock import FixedStepClock
from .engine import Battle, DEFAULT_SEED
from .skirmish_log import SkirmishLogger
from .result_scene import ResultScene
from .glue_scene import GlueScene
from .scenes import Quit, Scene, SceneAssets, SceneEvent, SceneManifest, Transition

BATTLE_TICK_SECONDS = 0.1  # the original battle clock ticks every 100 ms
FIRST_BATTLE = AssetId("vanilla", "battle", "bf001")


class BattleScene(Scene):
    """Loads a battle through the scene assets and runs its simulation on fixed 100 ms ticks.

    `log_dir`, when given, turns on a `whshr.battle_log.BattleLogger` for this battle (JSON Lines under
    `log_dir`, one file per battle, named by `battle_log.default_log_path`); `log_dir=None` disables
    logging. `seed` is threaded into `Battle.from_script` so a recorded battle and its replay start
    from the same deterministic state (notes/engine_architecture.md, "Battle logs and replay").
    """

    # Set by `enter`; a scene is only used after it has been entered.
    field: Battlefield
    battle: Battle
    initial_models: dict[str, int]

    def __init__(self, battle: AssetId = FIRST_BATTLE, log_dir: str | PathLike[str] | None = None, seed: int = DEFAULT_SEED,
                 glue_scene: GlueScene | None = None, request_id: int | None = None) -> None:
        self.battle_id = battle
        self.manifest = SceneManifest(immediate=(battle,))
        self.clock = FixedStepClock(BATTLE_TICK_SECONDS)
        self.selected_id: str | None = None  # identifier of the player regiment currently selected, if any
        self.log_dir = log_dir
        self.seed = seed
        self.logger: battle_log.BattleLogger | None = None
        self.skirmishes: SkirmishLogger | None = None  # whshr.skirmish_log.SkirmishLogger, one file per close combat
        self._log_closed = True
        self.glue_scene = glue_scene
        self.request_id = request_id
        self.no_battle = False

    def enter(self, context: SceneAssets) -> None:
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
        self.no_battle = bool(getattr(context, "no_battle", False))
        if self.no_battle:
            self.battle.start_battle()
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

    def _load_script_dll(self, context: SceneAssets) -> behaviour.ScriptDll | None:
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

    def exit(self, context: SceneAssets) -> None:
        # Terrain, scenery and sprites are battle-scoped: leaving the battle releases them.
        self.close_log("scene left")
        context.cache.release(self.battle_id)

    def close_log(self, reason: str) -> None:
        """Write the `end` record and close the log file; idempotent, so both a normal transition and
        an early frontend shutdown (the player closing the window mid-battle) can safely call it."""
        if self.logger is not None and not self._log_closed:
            self.logger.write_end(self.battle.update_count, reason)
            if self.skirmishes is not None:
                self.skirmishes.close(self.battle)
            self._log_closed = True

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        """Player intent from the view: select, move, attack, halt or deselect."""
        if self.logger is not None and self.logger.enabled:
            self.logger.write_order(self.battle.update_count, event)
        kind, *args = event
        if kind == "start_battle":
            self.battle.start_battle()
        elif kind == "pause":
            if self.battle.phase == "battle":
                self.battle.paused = not self.battle.paused
        elif kind == "independent":
            if self.selected_id is not None:
                try:
                    self.battle.toggle_independent(self.selected_id)
                except ValueError:
                    pass
        elif kind == "append_waypoint":
            if self.selected_id is not None:
                try:
                    self.battle.append_waypoint(self.selected_id, *args)
                except ValueError:
                    pass
        elif kind == "select":
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
        elif kind == "ranks_up":
            if self.selected_id is not None:
                try:
                    regiment = self.battle.regiments[self.selected_id]
                    self.battle.order_reform(self.selected_id, regiment.ranks + 1)
                except (ValueError, KeyError):
                    pass
        elif kind == "ranks_down":
            if self.selected_id is not None:
                try:
                    regiment = self.battle.regiments[self.selected_id]
                    self.battle.order_reform(self.selected_id, regiment.ranks - 1)
                except (ValueError, KeyError):
                    pass
        elif kind == "turn_left":
            if self.selected_id is not None:
                try:
                    self.battle.order_turn_left(self.selected_id)
                except ValueError:
                    pass
        elif kind == "turn_right":
            if self.selected_id is not None:
                try:
                    self.battle.order_turn_right(self.selected_id)
                except ValueError:
                    pass
        elif kind == "about_face":
            if self.selected_id is not None:
                try:
                    self.battle.order_about_face(self.selected_id)
                except ValueError:
                    pass
        elif kind == "face_point":
            x, y = args
            if self.selected_id is not None:
                try:
                    self.battle.order_face_point(self.selected_id, x, y)
                except ValueError:
                    pass
        return None

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
        super().update(seconds, context)
        for _ in range(self.clock.advance(seconds)):
            tick_number = self.battle.update_count
            self.battle.tick(BATTLE_TICK_SECONDS)
            if self.logger is not None and self.logger.enabled:
                for battle_event in self.battle.events:
                    self.logger.write_event(tick_number, battle_event)
                if self.battle.update_count % combat.SEGMENT_TICKS == 0:
                    self.logger.write_snapshot(self.battle.update_count, self.battle)
            if self.skirmishes is not None:
                self.skirmishes.observe(self.battle)
            if self.battle.result is not None:
                break
        if self.battle.result is not None:
            if self.logger is not None and self.logger.enabled:
                self.logger.write_snapshot(self.battle.update_count, self.battle)
                self.logger.write_result(self.battle.update_count, self.battle)
                self.close_log("result")
            if self.glue_scene is not None and self.no_battle:
                # No-battle mode: the completion handler runs at once, without a result screen.
                self._store_flawless_results()
                self.glue_scene.finish_battle(self.request_id or 0)
                return Transition(self.glue_scene, "glue battle resolved")
            return Transition(ResultScene(self.battle.result, self._casualty_summary(),
                                          glue_scene=self.glue_scene, request_id=self.request_id),
                              "battle resolved")
        return None

    def _store_flawless_results(self) -> None:
        """No-battle mode counts every mission as a flawless win: every objective met with its full values, no
        casualties (whshr.payments.flawless_results), so the debrief pays in full."""
        campaign = getattr(self.glue_scene, "campaign", None)
        if campaign is None:
            return
        payments.store_flawless(campaign, (self.field.script.get("mission") or {}).get("objectives", ()))

    def _casualty_summary(self) -> list[str]:
        return [f"{regiment.name}: {regiment.models}/{self.initial_models[identifier]} models"
                for identifier, regiment in sorted(self.battle.regiments.items())]
