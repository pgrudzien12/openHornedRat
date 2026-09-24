"""Presentation-independent scene lifecycle and transition coordination."""

from abc import ABC
from dataclasses import dataclass, field

from .assets import AssetId
from .cache import AssetCache


@dataclass(frozen=True)
class SceneManifest:
    """Assets a scene needs now and assets safe to prefetch for its likely successor."""

    immediate: tuple[AssetId, ...] = ()
    prefetch: tuple[AssetId, ...] = ()

    def __post_init__(self):
        if len(set(self.immediate)) != len(self.immediate):
            raise ValueError("scene manifest has duplicate immediate assets")
        if len(set(self.prefetch)) != len(self.prefetch):
            raise ValueError("scene manifest has duplicate prefetch assets")
        if set(self.immediate) & set(self.prefetch):
            raise ValueError("an asset cannot be immediate and prefetched in one scene")


@dataclass(frozen=True)
class Transition:
    """A request to replace the active scene after the current callback returns."""

    scene: "Scene"
    reason: str


@dataclass(frozen=True)
class Quit:
    """A request, returned by a scene, to end the application rather than switch scenes.

    Distinct from Transition: there is no successor scene and no further exit/enter calls,
    so the frontend main loop can stop cleanly after seeing SceneMachine.quit set.
    """

    reason: str


@dataclass
class SceneAssets:
    """Typed asset access provided to scenes without exposing source paths to them."""

    locator: object
    catalog: object
    cache: AssetCache
    loaders: dict
    glue: object = None
    # The engine's own save directory (never the original installation's SAVE/, GEI7e).
    save_dir: object = None
    # No-battle mode: BattleScene settles every battle it enters as an immediate, lossless win
    # instead of simulating it, so the campaign can be walked through quickly.
    no_battle: bool = False
    # Optional whshr.campaign_log.CampaignLogger; observation only, never changes behaviour.
    campaign_log: object = None

    def _record_failure(self, identifier, error):
        log = self.campaign_log
        if log is not None:
            try:
                log.asset_failed(identifier, error)
            except Exception:
                pass

    def load(self, identifier):
        try:
            record = self.catalog.get(identifier)
            try:
                loader = self.loaders[record.decoder]
            except KeyError:
                raise ValueError(f"no scene loader for decoder: {record.decoder}") from None
            return self.cache.get(self.locator, self.catalog, record.identifier, loader)
        except Exception as error:
            self._record_failure(identifier, error)
            raise

    def acquire(self, identifier, owner):
        """Load a runtime-discovered asset retained by an explicit owner."""
        try:
            record = self.catalog.get(identifier)
            try:
                loader = self.loaders[record.decoder]
            except KeyError:
                raise ValueError(f"no scene loader for decoder: {record.decoder}") from None
            return self.cache.acquire(
                self.locator, self.catalog, record.identifier, loader, owner
            )
        except Exception as error:
            self._record_failure(identifier, error)
            raise

    def release_owner(self, owner):
        self.cache.release_owner(owner)

    def glue_content(self):
        """Return the one shared, lazily indexed campaign-content repository."""
        if self.glue is None:
            from .glue_content import GlueContent
            self.glue = GlueContent(self.locator.installation)
        return self.glue


class Scene(ABC):
    """A game state with declarative asset needs and optional event/tick transitions."""

    manifest = SceneManifest()

    def enter(self, context):
        """Initialize scene state after it becomes active."""

    def exit(self, context):
        """Release scene state before another scene becomes active."""

    def handle(self, event, context):
        """Handle one presentation event and optionally request a Transition or Quit."""
        return None

    def update(self, seconds, context):
        """Advance deterministic scene time and optionally request a Transition or Quit."""
        if seconds < 0:
            raise ValueError("scene update duration must not be negative")
        return None


@dataclass
class SceneMachine:
    """Owns exactly one active scene and applies transitions in lifecycle order."""

    initial: Scene
    context: object = None
    active: Scene = field(init=False)
    history: list[Transition] = field(default_factory=list, init=False)
    quit: Quit = field(default=None, init=False)

    def __post_init__(self):
        self.active = self.initial
        self._log("scene_change", None, self.active, "initial scene")
        self.active.enter(self.context)
        self._log("entered", None, self.active, "")
        self._start_glue_activities()

    def _log(self, kind, old, new, reason):
        """Feed the optional campaign log; observation only, so any failure is ignored."""
        log = getattr(self.context, "campaign_log", None)
        if log is None:
            return
        try:
            if kind == "quit":
                log.quit(reason)
            elif kind == "entered":
                log.scene_entered(new)
            else:
                log.scene_change(old, new, reason)
        except Exception:
            pass

    def handle(self, event):
        """Give an event to the active scene and apply its transition or quit, if any."""
        if self.quit is None:
            self._apply(self.active.handle(event, self.context))
            self._start_glue_activities()
            self._fall_back_to_map()

    def update(self, seconds):
        """Give fixed or measured time to the active scene and apply its transition or quit, if any."""
        if seconds < 0:
            raise ValueError("scene update duration must not be negative")
        if self.quit is None:
            self._apply(self.active.update(seconds, self.context))
            self._start_glue_activities()
            self._fall_back_to_map()

    def _fall_back_to_map(self):
        """A campaign glue scene that finished with no window, request or wait left has nothing to show:
        reopen the current flow's map at the campaign's saved position instead of a blank screen."""
        from .glue_runtime import EndGame
        from .glue_scene import GlueScene

        scene = self.active
        if not isinstance(scene, GlueScene) or scene.runtime is None or scene.campaign is None or scene.program is None:
            return
        state = scene.runtime.state
        history = getattr(scene.campaign, "flow_history", ())
        if (state.windows or state.pending is not None or state.wait_reason is not None
                or state.current is not None or not history
                or getattr(scene, "is_fallback", False) or any(isinstance(effect, EndGame) for effect in scene.effects)):
            return
        log = getattr(self.context, "campaign_log", None)
        if log is not None:
            try:
                log.write("diagnostic", text="glue scene ended with no window or request; "
                                             "falling back to the campaign map", location=scene.program or scene.window)
            except Exception:
                pass
        fallback = GlueScene(history[0], scene.campaign)
        fallback.is_fallback = True  # a map that is itself blank is not retried every tick
        self._apply(Transition(fallback, "blank glue scene: back to the map"))

    def _start_glue_activities(self):
        self._start_glue_debrief()
        self._start_glue_battle()
        self._start_glue_movie()
        self._start_glue_caravan()

    def _start_glue_debrief(self):
        """A debrief request has no screen yet: it completes at once, applying what the engine can
        (notes/activity_results.md section 5), and the script goes on."""
        from .glue_scene import GlueScene

        while isinstance(self.active, GlueScene):
            effect = self.active.take_debrief_effect()
            if effect is None:
                return
            self.active.resolve_debrief(effect)

    def _start_glue_caravan(self):
        """A caravan request whose window the installation lacks resolves at once, as the mission's
        release step (notes/activity_results.md section 6.2); with a window the scene shows it and the
        player's exit hotspot resolves the request."""
        from .glue_runtime import ActivityResult, EnterCaravan
        from .glue_scene import GlueScene

        if not isinstance(self.active, GlueScene):
            return
        scene = self.active
        for index, effect in enumerate(scene._effects):
            if isinstance(effect, EnterCaravan) and not effect.window:
                scene._effects.pop(index)
                scene.complete_activity(ActivityResult(effect.request_id, "caravan"))
                parent = scene.release_mission() if effect.mode in ("select", "resume") else None
                if parent is not None:
                    self._apply(Transition(parent, "mission released"))
                return

    def _start_glue_battle(self):
        from .glue_scene import GlueScene

        if not isinstance(self.active, GlueScene):
            return
        effect = self.active.take_battle_effect()
        if effect is None:
            return
        from .assets import AssetId
        from .battle_scene import BattleScene

        battle = AssetId("vanilla", "battle", effect.battle.casefold())
        self._apply(Transition(BattleScene(battle, glue_scene=self.active, request_id=effect.request_id),
                               "glue battle started"))

    def _start_glue_movie(self):
        from .glue_scene import GlueScene

        if not isinstance(self.active, GlueScene):
            return
        effect = self.active.take_movie_effect()
        if effect is None:
            return
        from .campaign_scenes import MovieScene

        self._apply(Transition(
            MovieScene(effect.movie, glue_scene=self.active, request_id=effect.request_id, fade=effect.fade),
            "glue movie started"))

    def _apply(self, transition):
        if transition is None:
            return
        if isinstance(transition, Quit):
            self.quit = transition
            self._log("quit", self.active, None, transition.reason)
            return
        if not isinstance(transition, Transition):
            raise TypeError("scene callbacks must return Transition, Quit or None")
        previous = self.active
        self._log("scene_change", previous, transition.scene, transition.reason)
        previous.exit(self.context)
        self.active = transition.scene
        self.active.enter(self.context)
        self.history.append(transition)
        self._log("entered", None, self.active, "")
