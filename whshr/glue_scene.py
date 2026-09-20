"""Scene lifecycle host for the headless glue interpreter.

This scene intentionally has no registered pygame view yet.  It is the bridge
that gives a future ``GlueView`` one long-lived runtime rather than recreating
campaign Python scenes at every window/activity boundary.
"""

from .glue_runtime import ActivityResult, GlueInput, GlueRuntime, StartBattle
from .glue_fonts import glue_font_asset
from .scenes import Scene, Transition


class GlueScene(Scene):
    """Own one ``GlueRuntime`` and expose its ordered effects to a presentation host."""

    def __init__(self, program, campaign=None, *, speech_enabled=True, accept_battle=None, return_scene=None):
        self.program = str(program).upper()
        self.campaign = campaign
        self.speech_enabled = speech_enabled
        self.accept_battle = accept_battle
        self.return_scene = return_scene
        self.runtime = None
        self.context = None
        self._fonts = {}
        self._effects = []

    @property
    def effects(self):
        return tuple(self._effects)

    def take_effects(self):
        """Return effects emitted since the previous handoff and clear the queue."""
        effects, self._effects = tuple(self._effects), []
        return effects

    def take_battle_effect(self):
        for index, effect in enumerate(self._effects):
            if isinstance(effect, StartBattle):
                return self._effects.pop(index)
        return None

    def enter(self, context):
        self.context = context
        if self.runtime is None:
            content = context.glue_content()
            self.runtime = GlueRuntime(content, self.campaign, speech_enabled=self.speech_enabled)
            self._effects.extend(self.runtime.start(self.program))

    def complete_activity(self, result):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before completing an activity")
        self._effects.extend(self.runtime.resume(result))

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
            if event.kind == "panel-action" and event.target in ("accept_briefing", "open_troop_select") and self.accept_battle:
                self._effects.extend(self.runtime.start_battle(self.accept_battle))
            elif event.kind == "panel-action" and event.target == "open_troop_select" and self.runtime.state.selected_mission:
                self._effects.extend(self.runtime.start_battle(self._selected_battle()))
            elif event.kind == "panel-action" and event.target == "open_briefing" and self.runtime.state.selected_mission:
                briefing = self._selected_briefing()
                if briefing:
                    return Transition(GlueScene(briefing, self.campaign,
                                                accept_battle=self._selected_battle(), return_scene=self),
                                      "generic mission briefing opened")
            elif event.kind == "panel-action" and event.target in ("abort_briefing", "return_to_caravan") and self.return_scene:
                self._effects.extend(self.runtime.handle(GlueInput("panel-action", "abort_briefing")))
                return Transition(self.return_scene, "generic briefing dismissed")
            else:
                self._effects.extend(self.runtime.handle(event))
        elif isinstance(event, ActivityResult):
            self._effects.extend(self.runtime.resume(event))
        return None

    def _selected_values(self):
        return self.runtime.content.mission(self.runtime.state.selected_mission).values

    def _selected_battle(self):
        return self._selected_values().get("setbattlescript", "")

    def _selected_briefing(self):
        return self._selected_values().get("res") or self._selected_values().get("script")

    def update(self, seconds, context):
        super().update(seconds, context)
        if self.runtime is not None:
            self._effects.extend(self.runtime.tick(round(seconds * 1000)))
        return None

    def snapshot(self):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before snapshotting")
        return self.runtime.snapshot()

    def restore(self, snapshot):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before restoring")
        self.runtime.restore(snapshot)
