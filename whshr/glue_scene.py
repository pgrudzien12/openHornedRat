"""Scene lifecycle host for the headless glue interpreter.

This scene intentionally has no registered pygame view yet.  It is the bridge
that gives a future ``GlueView`` one long-lived runtime rather than recreating
campaign Python scenes at every window/activity boundary.
"""

from .glue_runtime import ActivityResult, GlueInput, GlueRuntime
from .scenes import Scene


class GlueScene(Scene):
    """Own one ``GlueRuntime`` and expose its ordered effects to a presentation host."""

    def __init__(self, program, campaign=None, *, speech_enabled=True):
        self.program = str(program).upper()
        self.campaign = campaign
        self.speech_enabled = speech_enabled
        self.runtime = None
        self._effects = []

    @property
    def effects(self):
        return tuple(self._effects)

    def take_effects(self):
        """Return effects emitted since the previous handoff and clear the queue."""
        effects, self._effects = tuple(self._effects), []
        return effects

    def enter(self, context):
        content = context.glue_content()
        self.runtime = GlueRuntime(content, self.campaign, speech_enabled=self.speech_enabled)
        self._effects.extend(self.runtime.start(self.program))

    def handle(self, event, context):
        if self.runtime is None:
            raise RuntimeError("GlueScene must be entered before handling input")
        if isinstance(event, GlueInput):
            self._effects.extend(self.runtime.handle(event))
        elif isinstance(event, ActivityResult):
            self._effects.extend(self.runtime.resume(event))
        return None

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
