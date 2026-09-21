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

    def load(self, identifier):
        record = self.catalog.get(identifier)
        try:
            loader = self.loaders[record.decoder]
        except KeyError:
            raise ValueError(f"no scene loader for decoder: {record.decoder}") from None
        return self.cache.get(self.locator, self.catalog, record.identifier, loader)

    def acquire(self, identifier, owner):
        """Load a runtime-discovered asset retained by an explicit owner."""
        record = self.catalog.get(identifier)
        try:
            loader = self.loaders[record.decoder]
        except KeyError:
            raise ValueError(f"no scene loader for decoder: {record.decoder}") from None
        return self.cache.acquire(
            self.locator, self.catalog, record.identifier, loader, owner
        )

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
        self.active.enter(self.context)
        self._start_glue_activities()

    def handle(self, event):
        """Give an event to the active scene and apply its transition or quit, if any."""
        if self.quit is None:
            self._apply(self.active.handle(event, self.context))
            self._start_glue_activities()

    def update(self, seconds):
        """Give fixed or measured time to the active scene and apply its transition or quit, if any."""
        if seconds < 0:
            raise ValueError("scene update duration must not be negative")
        if self.quit is None:
            self._apply(self.active.update(seconds, self.context))
            self._start_glue_activities()

    def _start_glue_activities(self):
        self._start_glue_battle()
        self._start_glue_movie()

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
            return
        if not isinstance(transition, Transition):
            raise TypeError("scene callbacks must return Transition, Quit or None")
        self.active.exit(self.context)
        self.active = transition.scene
        self.active.enter(self.context)
        self.history.append(transition)
