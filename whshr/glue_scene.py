"""Scene lifecycle host for the headless glue interpreter.

This scene intentionally has no registered pygame view yet.  It is the bridge
that gives a future ``GlueView`` one long-lived runtime rather than recreating
campaign Python scenes at every window/activity boundary.
"""

from .campaign_log import GlueWatcher
from .glue_runtime import ActivityResult, Diagnostic, GlueInput, GlueRuntime, StartBattle, StartDebrief, StartMovie
from .glue_fonts import glue_font_asset
from .scenes import Scene, Transition


class GlueScene(Scene):
    """Own one ``GlueRuntime`` and expose its ordered effects to a presentation host."""

    def __init__(self, program=None, campaign=None, *, window=None, speech_enabled=True, accept_battle=None,
                 accept_mission=None, return_scene=None):
        if (program is None) == (window is None):
            raise ValueError("GlueScene needs exactly one program or window")
        self.program = str(program).upper() if program is not None else None
        self.window = str(window).upper() if window is not None else None
        self.campaign = campaign
        self.speech_enabled = speech_enabled
        self.accept_battle = accept_battle
        self.accept_mission = accept_mission
        self.return_scene = return_scene
        self.runtime = None
        self.context = None
        self.caravan_return = None  # (scene, mode): the caravan that led to this map, for its Caravan button
        self._mission_released = False
        self._fonts = {}
        self._effects = []
        self._watcher = None

    @property
    def effects(self):
        return tuple(self._effects)

    def _queue(self, effects):
        """Queue runtime effects for the host and let the optional campaign log observe the change."""
        effects = tuple(effects)
        self._effects.extend(effects)
        if self._watcher is not None and self.runtime is not None:
            self._watcher.update(self.runtime, effects)

    def take_effects(self):
        """Return effects emitted since the previous handoff and clear the queue."""
        effects, self._effects = tuple(self._effects), []
        return effects

    def take_battle_effect(self):
        for index, effect in enumerate(self._effects):
            if isinstance(effect, StartBattle):
                return self._effects.pop(index)
        return None

    def take_movie_effect(self):
        for index, effect in enumerate(self._effects):
            if isinstance(effect, StartMovie):
                return self._effects.pop(index)
        return None

    def take_debrief_effect(self):
        for index, effect in enumerate(self._effects):
            if isinstance(effect, StartDebrief):
                return self._effects.pop(index)
        return None

    def resolve_debrief(self, effect):
        """Complete a debrief request without a screen (minimal debrief, :mod:`whshr.debrief`): log what was
        applied or skipped, then resume the script exactly as the completion handler would."""
        self._apply_debrief(effect)
        self.complete_activity(ActivityResult(effect.request_id, "debrief"))

    def finish_battle(self, request_id):
        """A battle this scene started has ended.  A *withdebrief* battle is followed by the debrief, whose
        completion pays the mission (notes/campaign.md section 5, mode 2); a plain one is never paid."""
        state = self.runtime.state
        if state.battle_with_debrief:
            state.battle_with_debrief = False
            self._apply_debrief(StartDebrief(request_id, 2, state.debrief_index, False))
        self.complete_activity(ActivityResult(request_id, "battle"))

    def _apply_debrief(self, effect):
        from .debrief import complete_debrief

        log = getattr(self.context, "campaign_log", None)
        applied, skipped = complete_debrief(self.campaign, effect, log, flawless=bool(getattr(self.context, "no_battle", False)))
        location = self.program or self.window
        self._queue(tuple(Diagnostic(location, f"debrief: skipped {text}") for text in skipped))
        log = getattr(self.context, "campaign_log", None)
        if log is not None:
            try:
                log.write("debrief", mode=effect.mode, debrief_index=effect.debrief_index, summary=effect.summary,
                          applied=applied, skipped=skipped)
            except Exception:
                pass

    def enter(self, context):
        self.context = context
        if self.runtime is None:
            content = context.glue_content()
            self.runtime = GlueRuntime(content, self.campaign, speech_enabled=self.speech_enabled)
            log = getattr(context, "campaign_log", None)
            if log is not None:
                self._watcher = GlueWatcher(log, type(self).__name__, self.campaign)
                log.write("glue_start", program=self.program, window=self.window)
            self._queue(self.runtime.start(self.program) if self.program is not None
                        else self.runtime.start_window(self.window))
            history = getattr(self.campaign, "flow_history", ())
            if self.program is not None and history and self.program == history[0]:
                for flow in history[1:]:  # resume: replay the chain up to the campaign's current flow
                    self._queue(self.runtime.continue_with(flow))

    def complete_activity(self, result):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before completing an activity")
        self._queue(self.runtime.resume(result))

    def start_battle(self, battle):
        self._queue(self.runtime.start_battle(battle))

    def start_mission_script(self, script):
        """Run a mission's ``setmissionscript`` in place of this briefing (notes/troop_selection.md
        §6): it autosaves, starts the battle, and afterwards continues to the after-mission caravan."""
        self._queue(self.runtime.start(script))

    def release_mission(self):
        """The mission release step (notes/activity_results.md §6.1): record the finished mission on
        the campaign, then let the parked flow script on the map continue when the mission calls for it.
        Returns the map scene to go back to (``return_scene``), or None for a briefing opened alone."""
        parent = self.return_scene
        if self.campaign is None or self.accept_mission is None:
            return parent
        if self._mission_released:  # back from the map into the same caravan: nothing more to complete
            if parent is not None and parent.runtime is not None:
                parent.runtime.refresh_selection()
            return parent
        self._mission_released = True
        replacement, released = self.campaign.complete_mission(self.accept_mission)
        if parent is not None and parent.runtime is not None:
            if replacement:
                parent._queue(parent.runtime.continue_with(replacement))
            elif released:
                parent._queue(parent.runtime.handle(GlueInput("mission-release")))
            else:
                parent.runtime.refresh_selection()  # stays on the map with the list rebuilt
        return parent

    def font(self, slot):
        """Load one verified glue font slot only when a view needs it."""
        slot = int(slot)
        if slot not in self._fonts:
            self._fonts[slot] = self.context.load(glue_font_asset(slot))
        return self._fonts[slot]

    def handle(self, event, context):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before handling input")
        if isinstance(event, GlueInput):
            if event.kind == "hotspot-release" and self._caravan_open():
                return self._leave_caravan(event.target)
            if event.kind == "hotspot-release" and self.window == "STARTCARAVAN" and event.target:
                if event.target.casefold() == "abortgame":
                    from .campaign_scenes import MainMenuScene
                    return Transition(MainMenuScene(), "generic caravan exited")
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
                  and self._reopen_caravan()):
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

    def _reopen_caravan(self):
        """The map's Caravan button pops back to the caravan that led here (notes/activity_results.md
        section 6.2): park the finished script again and open the same caravan window on top."""
        if self.caravan_return is None:
            return False
        scene, mode = self.caravan_return
        if scene.runtime is None or scene.runtime.state.pending is not None:
            return False
        effects = []
        scene.runtime._request("caravan", effects, restore_context=True, mode=mode)
        if scene.runtime.state.pending is None:
            return False
        scene._queue(effects)
        return True

    def _caravan_open(self):
        pending = self.runtime.state.pending
        return pending is not None and pending.kind == "caravan" and pending.restore_context

    def _leave_caravan(self, target):
        """A hotspot of the caravan a script asked for (notes/activity_results.md section 6.2).

        The hotspot's own exit name decides: ``UnwindMission`` pops the parked script, lets it finish and
        releases the mission on the map; ``PopAndResume`` pops it and lets the script carry on. Every other
        hotspot (books, options, speech, save/load) has no activity yet and stays inert."""
        pending = self.runtime.state.pending
        name = (target or "").casefold()
        mode = pending.mode
        if name not in ("unwindmission", "popandresume"):
            self._queue((Diagnostic("caravan", f"hotspot {target!r} is not yet implemented"),))
            return None
        self.complete_activity(ActivityResult(pending.request_id, "caravan"))
        if name == "unwindmission":
            parent = self.release_mission()
            if parent is not None:
                if mode:
                    parent.caravan_return = (self, mode)
                return Transition(parent, "mission released")
        return None

    def _map_program(self, target):
        """The flow program the caravan's map hotspot opens.

        The hotspot names the campaign's first flow, but the campaign moves on (a mission's
        ``replacescript`` switches flow), so a flow target opens the campaign's flow chain; the runtime
        then replays its set-up up to the saved step (``CampaignState.wait_already_released``) instead
        of offering the opening mission window again.
        """
        flows = getattr(getattr(self.campaign, "graph", None), "get", lambda *_: None)("flow_scripts") or {}
        history = getattr(self.campaign, "flow_history", ())
        return history[0] if target.upper() in flows and history else target

    def _selected_values(self):
        return self.runtime.content.mission(self.runtime.state.selected_mission).values

    def _selected_battle(self):
        return self._selected_values().get("setbattlescript", "")

    def _selected_briefing(self):
        return self._selected_values().get("res") or self._selected_values().get("script")

    def update(self, seconds, context):
        super().update(seconds, context)
        if self.runtime is not None:
            self._queue(self.runtime.tick(round(seconds * 1000)))
        return None

    def snapshot(self):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before snapshotting")
        return self.runtime.snapshot()

    def restore(self, snapshot):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before restoring")
        self.runtime.restore(snapshot)
        self._queue(())
