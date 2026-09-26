# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Scene lifecycle host for the headless glue interpreter.

This scene intentionally has no registered pygame view yet.  It is the bridge
that gives a future ``GlueView`` one long-lived runtime rather than recreating
campaign Python scenes at every window/activity boundary.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from .campaign_log import GlueWatcher
from .glue import MissionRef
from .glue_runtime import (ActivityResult, Diagnostic, EnterCaravan, GlueEffect, GlueInput, GlueRuntime, GlueRuntimeState,
                           MissionSelectRequested, StartBattle, StartDebrief, StartMovie)
from .glue_fonts import glue_font_asset
from .scenes import Quit, Scene, SceneAssets, SceneEvent, Transition

if TYPE_CHECKING:
    from .campaign_state import CampaignState


class GlueScene(Scene):
    """Own one ``GlueRuntime`` and expose its ordered effects to a presentation host."""

    def __init__(self, program: str | None = None, campaign: "CampaignState | None" = None, *,
                 window: str | None = None, speech_enabled: bool = True, accept_battle: str | None = None,
                 accept_mission: MissionRef | None = None, return_scene: Scene | None = None,
                 record_battle: str | None = None, record_debrief: int | str | None = None) -> None:
        if record_battle is not None:
            if program is not None or window is not None:
                raise ValueError("a record battle scene has neither program nor window")
        elif (program is None) == (window is None):
            raise ValueError("GlueScene needs exactly one program or window")
        self.record_battle = str(record_battle).upper() if record_battle is not None else None
        self.record_debrief = record_debrief
        self.program = str(program).upper() if program is not None else None
        self.window = str(window).upper() if window is not None else None
        self.campaign = campaign
        self.speech_enabled = speech_enabled
        self.accept_battle = accept_battle
        self.accept_mission = accept_mission
        self.return_scene = return_scene
        self.runtime: GlueRuntime | None = None
        self.context: SceneAssets | None = None
        self.is_fallback = False  # a blank fallback map is not retried every tick (SceneMachine)
        self.caravan_return: tuple[GlueScene, str] | None = None  # (scene, mode): the caravan that led to this map, for its Caravan button
        self._mission_released = False
        self._fonts: dict[int, Any] = {}
        self._effects: list[GlueEffect] = []
        self._watcher: GlueWatcher | None = None

    @property
    def effects(self) -> tuple[GlueEffect, ...]:
        return tuple(self._effects)

    def _queue(self, effects: Iterable[GlueEffect]) -> None:
        """Queue runtime effects for the host and let the optional campaign log observe the change."""
        effects = tuple(effects)
        self._effects.extend(effects)
        if self._watcher is not None and self.runtime is not None:
            self._watcher.update(self.runtime, effects)

    def take_effects(self) -> tuple[GlueEffect, ...]:
        """Return effects emitted since the previous handoff and clear the queue."""
        effects, self._effects = tuple(self._effects), []
        return effects

    def take_battle_effect(self) -> StartBattle | None:
        for index, effect in enumerate(self._effects):
            if isinstance(effect, StartBattle):
                del self._effects[index]
                return effect
        return None

    def take_movie_effect(self) -> StartMovie | None:
        for index, effect in enumerate(self._effects):
            if isinstance(effect, StartMovie):
                del self._effects[index]
                return effect
        return None

    def take_windowless_caravan_effect(self) -> EnterCaravan | None:
        """A queued caravan request whose window the installation lacks, removed from the queue."""
        for index, effect in enumerate(self._effects):
            if isinstance(effect, EnterCaravan) and not effect.window:
                del self._effects[index]
                return effect
        return None

    def take_debrief_effect(self) -> StartDebrief | None:
        for index, effect in enumerate(self._effects):
            if isinstance(effect, StartDebrief):
                del self._effects[index]
                return effect
        return None

    def take_mission_select_effect(self) -> MissionSelectRequested | None:
        for index, effect in enumerate(self._effects):
            if isinstance(effect, MissionSelectRequested):
                del self._effects[index]
                return effect
        return None

    def require_runtime(self) -> GlueRuntime:
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered first")
        return self.runtime

    def resolve_debrief(self, effect: StartDebrief) -> None:
        """Complete a debrief request without a screen (minimal debrief, :mod:`whshr.debrief`): log what was
        applied or skipped, then resume the script exactly as the completion handler would."""
        self._apply_debrief(effect)
        self.complete_activity(ActivityResult(effect.request_id, "debrief"))

    def finish_battle(self, request_id: int) -> None:
        """A battle this scene started has ended.  A *withdebrief* battle is followed by the debrief, whose
        completion pays the mission (notes/campaign.md section 5, mode 2); a plain one is never paid."""
        state = self.require_runtime().state
        if state.battle_with_debrief:
            state.battle_with_debrief = False
            self._apply_debrief(StartDebrief(request_id, 2, state.debrief_index, False))
        self.complete_activity(ActivityResult(request_id, "battle"))

    def _apply_debrief(self, effect: StartDebrief) -> None:
        from .debrief import complete_debrief

        log = getattr(self.context, "campaign_log", None)
        applied, skipped = complete_debrief(self.campaign, effect, log, flawless=bool(getattr(self.context, "no_battle", False)))
        location = self.program or self.window or self.record_battle or ""
        self._queue(tuple(Diagnostic(location, f"debrief: skipped {text}") for text in skipped))
        log = getattr(self.context, "campaign_log", None)
        if log is not None:
            try:
                log.write("debrief", mode=effect.mode, debrief_index=effect.debrief_index, summary=effect.summary,
                          applied=applied, skipped=skipped)
            except Exception:
                pass

    def enter(self, context: SceneAssets) -> None:
        self.context = context
        if self.runtime is None:
            content = context.glue_content()
            self.runtime = GlueRuntime(content, self.campaign, speech_enabled=self.speech_enabled)
            log = getattr(context, "campaign_log", None)
            if log is not None:
                self._watcher = GlueWatcher(log, type(self).__name__, self.campaign)
                log.write("glue_start", program=self.program, window=self.window)
            if self.record_battle is not None:
                self._queue(self.runtime.start_battle(self.record_battle, self.record_debrief))
            else:
                self._queue(self.runtime.start(self.program) if self.program is not None
                            else self.runtime.start_window(self.window or ""))
            history = getattr(self.campaign, "flow_history", ())
            if self.program is not None and history and self.program == history[0]:
                for flow in history[1:]:  # resume: replay the chain up to the campaign's current flow
                    self._queue(self.runtime.continue_with(flow))

    def complete_activity(self, result: ActivityResult) -> None:
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before completing an activity")
        self._queue(self.runtime.resume(result))

    def start_battle(self, battle: str) -> None:
        self._queue(self.require_runtime().start_battle(battle))

    def start_mission_script(self, script: str) -> None:
        """Run a mission's ``setmissionscript`` in place of this briefing (notes/troop_selection.md
        §6): it autosaves, starts the battle, and afterwards continues to the after-mission caravan."""
        self._queue(self.require_runtime().start(script))

    def release_mission(self) -> Scene | None:
        """The mission release step (notes/activity_results.md §6.1): record the finished mission on
        the campaign, then let the parked flow script on the map continue when the mission calls for it.
        Returns the map scene to go back to (``return_scene``), or None for a briefing opened alone."""
        parent = self.return_scene
        if self.campaign is None or self.accept_mission is None:
            return parent
        if self._mission_released:  # back from the map into the same caravan: nothing more to complete
            if isinstance(parent, GlueScene) and parent.runtime is not None:
                parent.runtime.refresh_selection()
            return parent
        self._mission_released = True
        replacement, released = self.campaign.complete_mission(self.accept_mission)
        if isinstance(parent, GlueScene) and parent.runtime is not None:
            if replacement:
                parent._queue(parent.runtime.continue_with(replacement))
            elif released:
                parent._queue(parent.runtime.handle(GlueInput("mission-release")))
            else:
                parent.runtime.refresh_selection()  # stays on the map with the list rebuilt
        return parent

    def font(self, slot: int) -> Any:
        """Load one verified glue font slot only when a view needs it."""
        slot = int(slot)
        if slot not in self._fonts:
            if self.context is None:
                raise RuntimeError("GlueScene must be entered before loading fonts")
            self._fonts[slot] = self.context.load(glue_font_asset(slot))
        return self._fonts[slot]

    def handle(self, event: SceneEvent, context: SceneAssets) -> Transition | Quit | None:
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before handling input")
        if isinstance(event, GlueInput):
            if event.kind == "hotspot-release" and self._caravan_open():
                return self._leave_caravan(event.target)
            if event.kind == "hotspot-release" and self.window == "STARTCARAVAN" and event.target:
                if event.target.casefold() == "armybook":
                    return self._open_army_book(hire_only=False)
                if event.target.casefold() == "loadsavewindow":
                    return self._open_save_dialog()
                if event.target.casefold() == "abortgame":
                    return self._confirm_abort_game()
                if event.target.casefold() not in {"armybook", "encyclopediabook", "loadsavewindow", "magicbook",
                                                   "optionsdialog"}:
                    return Transition(GlueScene(self._map_program(event.target), self.campaign),
                                      "generic caravan mission map opened")
            if event.kind == "panel-action" and event.target in ("accept_briefing", "open_troop_select") and self.accept_battle:
                from .campaign_scenes import TroopSelectionScene

                return Transition(TroopSelectionScene(self.campaign, self.accept_mission, self.accept_battle, self),
                                  "troop selection opened")
            elif event.kind == "panel-action" and event.target == "open_troop_select" and self.runtime.state.selected_mission:
                from .campaign_scenes import TroopSelectionScene

                return Transition(TroopSelectionScene(self.campaign, self.runtime.state.selected_mission,
                                                       self._selected_battle(), self),
                                  "troop selection opened")
            elif event.kind == "panel-action" and event.target == "open_briefing" and self.runtime.state.selected_mission:
                briefing = self._selected_briefing()
                if briefing:
                    return Transition(GlueScene(briefing, self.campaign, accept_battle=self._selected_battle(),
                                                accept_mission=self.runtime.state.selected_mission, return_scene=self),
                                      "generic mission briefing opened")
            elif event.kind == "panel-action" and event.target in ("abort_briefing", "return_to_caravan") and self.return_scene:
                self._queue(self.runtime.handle(GlueInput("panel-action", "abort_briefing")))
                return Transition(self.return_scene, "generic briefing dismissed")
            elif (event.kind == "panel-action" and event.target == "return_to_caravan"
                  and self._reopen_caravan() and self.caravan_return is not None):
                scene = self.caravan_return[0]
                return Transition(scene, "map returned to its caravan")
            elif event.kind == "panel-action" and event.target == "return_to_caravan" and hasattr(context, "locator"):
                from .campaign_state import CampaignState

                campaign = self.campaign or CampaignState.from_installation(
                    context.locator.installation, self.runtime.content, save_dir=getattr(context, "save_dir", None)
                )
                return Transition(GlueScene(campaign=campaign, window="STARTCARAVAN"),
                                  "generic mission map dismissed")
            else:
                self._queue(self.runtime.handle(event))
        elif isinstance(event, ActivityResult):
            self._queue(self.runtime.resume(event))
        return None

    def _reopen_caravan(self) -> bool:
        """The map's Caravan button pops back to the caravan that led here (notes/activity_results.md
        section 6.2): park the finished script again and open the same caravan window on top."""
        if self.caravan_return is None:
            return False
        scene, mode = self.caravan_return
        if scene.runtime is None or scene.runtime.state.pending is not None:
            return False
        effects = scene.runtime.open_caravan(mode)
        if scene.runtime.state.pending is None:
            return False
        scene._queue(effects)
        return True

    def _caravan_open(self) -> bool:
        pending = self.require_runtime().state.pending
        return pending is not None and pending.kind == "caravan" and pending.restore_context

    def _leave_caravan(self, target: str | None) -> Transition | None:
        """A hotspot of the caravan a script asked for (notes/activity_results.md section 6.2).

        The hotspot's own exit name decides: ``UnwindMission`` pops the parked script, lets it finish and
        releases the mission on the map; ``PopAndResume`` pops it and lets the script carry on. Every other
        hotspot (books, options, speech, save/load) has no activity yet and stays inert."""
        pending = self.require_runtime().state.pending
        if pending is None:
            return None
        name = (target or "").casefold()
        mode = pending.mode
        if name in ("armybook", "hireonlyarmybook"):
            return self._open_army_book(hire_only=name == "hireonlyarmybook")
        if name == "loadsavewindow":
            return self._open_save_dialog()
        if name == "abortgame":
            return self._confirm_abort_game()
        if name not in ("unwindmission", "popandresume"):
            self._queue((Diagnostic("caravan", f"hotspot {target!r} is not yet implemented"),))
            return None
        if name == "popandresume" and self.campaign is not None:
            self.campaign.leave_caravan()  # notes/activity_results.md §6: unhired regiments go, unused reinforcements are cleared
        self._queue(self.require_runtime().stop_speech())  # Dietrich does not go on talking over the next screen
        self.complete_activity(ActivityResult(pending.request_id, "caravan"))
        if name == "unwindmission":
            parent = self.release_mission()
            if parent is not None:
                if mode and isinstance(parent, GlueScene):
                    parent.caravan_return = (self, mode)
                return Transition(parent, "mission released")
        return None

    def _confirm_abort_game(self) -> Transition:
        """AbortGame asks "Are you sure you want quit the campaign?" (notes/activity_results.md section 6);
        Yes abandons the campaign for the main menu, No comes back to this caravan."""
        from .campaign_scenes import MainMenuScene
        from .confirm_scene import ConfirmScene

        def leave() -> None:
            if self.runtime is not None:
                self._queue(self.runtime.stop_speech())  # Dietrich does not go on talking over the menu

        return Transition(ConfirmScene(self, MainMenuScene(), ("GMTXT", 36070), on_yes=leave, reason="caravan aborted"),
                          "abort confirmation opened")

    def _open_save_dialog(self) -> Transition | None:
        """The caravan's Save button (notes/builtin_widgets.md §6): the dialog returns to this scene."""
        from .load_save_scene import SAVE, LoadSaveScene

        if self.campaign is None:
            self._queue((Diagnostic("caravan", "saving needs a campaign"),))
            return None
        release, unavailable = self._save_release()
        return Transition(LoadSaveScene(SAVE, self, self.campaign, release=release, unavailable=unavailable),
                          "save dialog opened")

    def _save_release(self) -> tuple[MissionRef | None, str]:
        """(mission to record as released, reason saving is refused) for a save made from this scene.

        A load resumes on the start caravan, so a save made while a mission's caravan is open must record the
        campaign as it will be after leaving it. The after-mission caravans (``select``/``resume``) are the
        finished mission: it is released in the saved copy. Any other caravan of a mission script sits in the
        middle of the mission (a load could not resume it), so saving there is refused."""
        if self.accept_mission is None or self._mission_released:
            return None, ""
        pending = self.require_runtime().state.pending
        if pending is not None and pending.kind == "caravan" and pending.mode in ("select", "resume"):
            return self.accept_mission, ""
        return None, "The game cannot be saved in the middle of a mission."

    def _open_army_book(self, hire_only: bool) -> Transition | None:
        """The caravan's Army Records (notes/builtin_widgets.md §2.1): ``HireOnlyArmyBook`` charges the coffers
        for a hire, ``ArmyBook`` does not. Both list the company in file order and open on regiment 0."""
        from .campaign_scenes import ArmyRecordsScene
        from .roster_book import RosterBook

        campaign = self.campaign
        if campaign is None or not campaign.company:
            self._queue((Diagnostic("caravan", "the army book needs a company"),))
            return None
        model = RosterBook(campaign.company, coffers=campaign.coffers, reinforcements=campaign.reinforcements,
                           pays=hire_only)
        return Transition(ArmyRecordsScene(self, campaign.company[0].whoami, model), "army records opened")

    def _map_program(self, target: str) -> str:
        """The flow program the caravan's map hotspot opens.

        The hotspot names the campaign's first flow, but the campaign moves on (a mission's
        ``replacescript`` switches flow), so a flow target opens the campaign's flow chain; the runtime
        then replays its set-up up to the saved step (``CampaignState.wait_already_released``) instead
        of offering the opening mission window again.
        """
        flows = getattr(getattr(self.campaign, "graph", None), "get", lambda *_: None)("flow_scripts") or {}
        history = getattr(self.campaign, "flow_history", ())
        return history[0] if target.upper() in flows and history else target

    def _selected_values(self) -> dict[str, int | str]:
        runtime = self.require_runtime()
        if runtime.state.selected_mission is None:
            raise RuntimeError("no mission is selected")
        return runtime.content.mission(runtime.state.selected_mission).values

    def _selected_battle(self) -> str:
        return str(self._selected_values().get("setbattlescript", ""))

    def _selected_briefing(self) -> str | None:
        value = self._selected_values().get("res") or self._selected_values().get("script")
        return None if value is None else str(value)

    def update(self, seconds: float, context: SceneAssets) -> Transition | Quit | None:
        super().update(seconds, context)
        if self.runtime is not None:
            self._queue(self.runtime.tick(round(seconds * 1000)))
        return None

    def snapshot(self) -> GlueRuntimeState:
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before snapshotting")
        return self.runtime.snapshot()

    def restore(self, snapshot: GlueRuntimeState) -> None:
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before restoring")
        self.runtime.restore(snapshot)
        self._queue(())
