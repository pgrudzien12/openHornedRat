# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Battle scene: owns one loaded battlefield and advances its deterministic simulation."""

import os
from os import PathLike
from . import battle_log, behaviour, casualties, combat, figure_capture, payments, roster, skirmish_log
from .assets import AssetId
from .battlefield import Battlefield, WORLD_PER_MESH, sprite_files
from .clock import FixedStepClock
from .debrief_screen import UnitOutcome
from .engine import Battle, DEFAULT_SEED, Side
from .battle_events import BattleEvent
from .script import View
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
                 glue_scene: GlueScene | None = None, request_id: int | None = None,
                 player_army: View | None = None) -> None:
        self.battle_id = battle
        self.manifest = SceneManifest(immediate=(battle,) if glue_scene is None and player_army is None else ())
        self.player_army = player_army
        self.clock = FixedStepClock(BATTLE_TICK_SECONDS, max_steps=1)
        self.selected_id: str | None = None  # identifier of the player regiment currently selected, if any
        self.log_dir = log_dir
        self.seed = seed
        self.logger: battle_log.BattleLogger | None = None
        self.skirmishes: SkirmishLogger | None = None  # whshr.skirmish_log.SkirmishLogger, one file per close combat
        self._log_closed = True
        # Running F2 figure captures (whshr.figure_capture), each written to disk once it finishes.
        self.captures: list[figure_capture.FigureCapture] = []
        self.glue_scene = glue_scene
        self.request_id = request_id
        self.no_battle = False

    def enter(self, context: SceneAssets) -> None:
        if self.player_army is None and self.glue_scene is not None and self.glue_scene.campaign is not None:
            self.player_army = self.glue_scene.campaign.marching_army()
        self.field = context.load_battle(self.battle_id, self.player_army)
        script_dll = self._load_script_dll(context)
        # The logger must exist before Battle.from_script so ScriptInterpreter can be handed it
        # directly (script_logger=); WHSHR_TRACE_SCRIPTS=1 turns on its per-opcode trace records
        # (issue #3/#46, "proper logging" for debugging mission scripts -- off by default, since
        # it is far higher volume than the rest of the battle log).
        path = battle_log.default_log_path(self.log_dir, self.battle_id.name) if self.log_dir is not None else None
        self.logger = battle_log.BattleLogger(path, trace_scripts=bool(os.environ.get("WHSHR_TRACE_SCRIPTS")))
        self.battle = Battle.from_script(self.field.script, seed=self.seed, script_dll=script_dll,
                                         script_logger=self.logger)
        self.battle.ground_height = lambda x, y: self.field.ground_height(x, y) * WORLD_PER_MESH
        # Seed every regiment's figures now, in battle order, so the first draw never has to (seeding draws from the
        # battle-wide stagger sequence; doing it lazily in draw order would make live play and replay differ).
        for regiment in self.battle.regiments.values():
            regiment.model_positions()
        if context.glue is not None:
            self.battle.text_resources = context.glue.strings("GMTXT")
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
                player_army=self.player_army,
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

    def running_capture(self, unit_id: str | None) -> figure_capture.FigureCapture | None:
        """The F2 capture still recording `unit_id`, if any (a second F2 extends it)."""
        return next((capture for capture in self.captures if capture.unit_id == unit_id and capture.running), None)

    def close_log(self, reason: str) -> None:
        """Write the `end` record and close the log file; idempotent, so both a normal transition and
        an early frontend shutdown (the player closing the window mid-battle) can safely call it."""
        for capture in self.captures:
            capture.close()
        self.captures = []
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
        elif kind == "capture":
            # Debugging aid only; a replay (no log directory) re-handles the logged request as a no-op.
            unit_id = figure_capture.capture_unit(self.battle, args[0] if args else self.selected_id)
            running = self.running_capture(unit_id)
            if running is not None:
                running.extend(self.battle)
            elif self.log_dir is not None and unit_id is not None:
                self.captures.append(figure_capture.FigureCapture(self.log_dir, self.battle_id.name,
                                                                  self.battle, unit_id))
        elif kind == "win_battle":
            # Testing aid (F10): finish this battle as an instant, lossless win, settled and paid like no-battle
            # mode, so a battle can be skipped in the middle of a playthrough. Only with --debug; a battle already
            # over stays as it is.
            if getattr(context, "debug", False) and self.battle.result is None:
                self.no_battle = True
                self.battle.start_battle()
                self.battle.resolve_no_battle()
        elif kind == "pause":
            if self.battle.phase == "battle" and not self.battle.can_leave:
                self.battle.paused = not self.battle.paused
        elif kind == "objectives_book":
            self.battle.open_book()
        elif kind == "leave_battle":
            if self.battle.can_leave:  # the tent button (notes/battle_end_objectives.md 7)
                self.battle.leave()
        elif kind == "independent":
            if self.selected_id is not None:
                try:
                    self.battle.toggle_independent(self.selected_id)
                except ValueError:
                    pass
        elif kind == "rally":
            if self.selected_id is not None:
                try:
                    self.battle.order_rally(self.selected_id)
                except ValueError:
                    pass  # not a pursuing or broken player regiment (notes/pursuit_restraint.md 3)
        elif kind == "fight_harder":
            if self.selected_id is not None:
                try:
                    self.battle.order_fight_harder(self.selected_id)
                except ValueError:
                    pass
        elif kind == "charge":
            if self.selected_id is not None:
                try:
                    self.battle.order_charge_forward(self.selected_id)
                except ValueError:
                    pass
        elif kind == "arm_item":
            if self.selected_id is not None:
                try:
                    self.battle.arm_item(self.selected_id, args[0])
                except ValueError:
                    pass
        elif kind == "item_target":
            if self.selected_id is not None:
                try:
                    self.battle.order_item_target(self.selected_id, args[0], args[1], args[2])
                except ValueError:
                    pass
        elif kind == "append_waypoint":
            if self.selected_id is not None:
                try:
                    self.battle.append_waypoint(self.selected_id, *args)
                except ValueError:
                    pass
        elif kind == "begin_drag":
            identifier, x, y = args
            try:
                self.battle.begin_deployment_drag(identifier, x, y)
                self.selected_id = identifier
            except (ValueError, KeyError):
                pass
        elif kind == "drag_to":
            x, y, rotate = args
            self.battle.update_deployment_drag(x, y, rotate)
        elif kind == "end_drag":
            self.battle.end_deployment_drag()
        elif kind == "prepare_move":
            if self.selected_id is not None and self.battle.phase == "deployment":
                self.battle.prepare_deployment_move(self.selected_id)
        elif kind == "select":
            # An enemy regiment can be selected too, for its readout/banner/stats only: the
            # order handlers below all refuse a non-player identifier (ValueError, caught), so
            # selecting one never grants it orders.
            (identifier,) = args
            regiment = self.battle.regiments.get(identifier)
            if regiment is not None and regiment.active and not (
                    self.battle.phase == "deployment" and (regiment.routing or regiment.held)):
                self.battle.end_deployment_drag()
                self.selected_id = identifier
                if self.battle.phase == "deployment":
                    self.battle.refresh_visibility()
        elif kind == "deselect":
            self.battle.end_deployment_drag()
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
                    if target_id in self.battle.building_index:
                        self.battle.order_attack_building(self.selected_id, target_id)
                    else:
                        self.battle.order_attack(self.selected_id, target_id)
                except ValueError:
                    pass  # not an enemy regiment, the selection is routing, or the target is gone
        elif kind == "fire":
            target_id, point = args[:2]
            bomb = bool(args[2]) if len(args) > 2 else False
            if self.selected_id is not None:
                try:
                    object_index = None
                    if target_id is None and point is not None:
                        for index, obj in enumerate(self.battle.shooting_objects):
                            radius = float(obj.get("radius") or 0)
                            if radius > 0 and ((float(obj.get("x") or 0)-point[0])**2
                                               + (float(obj.get("y") or 0)-point[1])**2) < radius**2:
                                object_index = index
                                break
                    text_id = self.battle.order_fire(self.selected_id, target_id, point,
                                                     object_index=object_index, bomb=bomb)
                    if text_id is not None:
                        self.battle.pending_feedback.append(BattleEvent(
                            f"GMTXT {text_id}", "ranged_message", regiment=self.selected_id,
                            target=target_id, target_name=(self.battle.shooting_objects[object_index].get("name")
                                                           if object_index is not None else None), text_id=text_id))
                except ValueError:
                    pass
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
            for capture in self.captures:
                capture.observe(self.battle)
                if capture.done:
                    capture.close()
            self.captures = [capture for capture in self.captures if not capture.done]
            if self.battle.result is not None:
                break
        if self.battle.result is not None:
            if self.logger is not None and self.logger.enabled:
                self.logger.write_snapshot(self.battle.update_count, self.battle)
                self.logger.write_result(self.battle.update_count, self.battle)
                self.close_log("result")
            if self.glue_scene is not None:
                # A battle a glue program started shows no result screen of its own: the flow goes straight on to
                # the debrief (notes/native-windows.md 9.11, scenario 4). No-battle mode counts a flawless win.
                if self.no_battle:
                    self._store_flawless_results()
                else:
                    self._store_played_results()
                self.glue_scene.finish_battle(self.request_id or 0)
                return Transition(self.glue_scene, "glue battle resolved")
            return Transition(ResultScene(self.battle.result, self._casualty_summary()), "battle resolved")
        return None

    def _store_flawless_results(self) -> None:
        """No-battle mode counts every mission as a flawless win: every objective met with its full values, no
        casualties (whshr.payments.flawless_results), so the debrief pays in full."""
        campaign = getattr(self.glue_scene, "campaign", None)
        if campaign is None:
            return
        payments.store_flawless(campaign, (self.field.script.get("mission") or {}).get("objectives", ()))

    def _store_played_results(self) -> None:
        """Hand the campaign what the debrief reports: the battle's objective records (or, for a mission-less
        battle, records derived from the outcome by payments.played_results) and each marching regiment's models, routed, casualties, kills and experience gained
        (notes/casualty_bookkeeping.md 2.4)."""
        campaign = getattr(self.glue_scene, "campaign", None)
        if campaign is None:
            return
        terms = getattr(campaign, "mission_cash", None)
        if self.battle.objectives is not None:
            # The records the final pass left (notes/battle_end_objectives.md 3.3), in list order.
            campaign.objective_results = self.battle.objectives.results()
        else:
            lost = sum(1 for r in self.battle.regiments.values() if r.side == Side.PLAYER and not r.models)
            campaign.objective_results = payments.played_results(
                (self.field.script.get("mission") or {}).get("objectives", ()), self.battle.result == "victory",
                terms.letters if terms else (), payments.marching_models(campaign), lost)
        campaign.flawless_result = False
        player = [(identifier, regiment) for identifier, regiment in self.battle.regiments.items()
                  if regiment.side == Side.PLAYER]
        marching = campaign.ordered_march_units
        battle_items = {regiment.whoami: regiment.items for _, regiment in player if regiment.whoami in marching}
        campaign.company = tuple(roster.with_items(record, battle_items[record.whoami])
                                 if record.whoami in battle_items else record for record in campaign.company)
        if len(player) != len(marching):
            campaign.battle_outcome = {}
            casualties.after_battle(campaign)
            return
        outcomes: dict[int, UnitOutcome] = {}
        for whoami, (identifier, regiment) in zip(marching, player):
            routed = regiment.models if regiment.fled else 0
            dead = max(0, self.initial_models[identifier] - regiment.models)
            outcomes[whoami] = UnitOutcome(regiment.models - routed, routed, dead + routed, regiment.kills,
                                           regiment.experience_gained)
        campaign.battle_outcome = outcomes
        campaign.campaign_over_movie = casualties.campaign_over_movie(campaign)
        if campaign.campaign_over_movie is None:  # a lost campaign merges and pays nothing
            casualties.after_battle(campaign)  # wounded bookkeeping before the debrief screen

    def _casualty_summary(self) -> list[str]:
        return [f"{regiment.name}: {regiment.models}/{self.initial_models[identifier]} models"
                for identifier, regiment in sorted(self.battle.regiments.items())]
