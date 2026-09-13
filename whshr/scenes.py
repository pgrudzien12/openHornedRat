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


@dataclass
class SceneAssets:
    """Typed asset access provided to scenes without exposing source paths to them."""

    locator: object
    catalog: object
    cache: AssetCache
    loaders: dict

    def load(self, identifier):
        record = self.catalog.get(identifier)
        try:
            loader = self.loaders[record.decoder]
        except KeyError:
            raise ValueError(f"no scene loader for decoder: {record.decoder}") from None
        return self.cache.get(self.locator, self.catalog, record.identifier, loader)


class Scene(ABC):
    """A game state with declarative asset needs and optional event/tick transitions."""

    manifest = SceneManifest()

    def enter(self, context):
        """Initialize scene state after it becomes active."""

    def exit(self, context):
        """Release scene state before another scene becomes active."""

    def handle(self, event, context):
        """Handle one presentation event and optionally request a transition."""
        return None

    def update(self, seconds, context):
        """Advance deterministic scene time and optionally request a transition."""
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

    def __post_init__(self):
        self.active = self.initial
        self.active.enter(self.context)

    def handle(self, event):
        """Give an event to the active scene and apply its transition, if any."""
        self._apply(self.active.handle(event, self.context))

    def update(self, seconds):
        """Give fixed or measured time to the active scene and apply its transition, if any."""
        if seconds < 0:
            raise ValueError("scene update duration must not be negative")
        self._apply(self.active.update(seconds, self.context))

    def _apply(self, transition):
        if transition is None:
            return
        if not isinstance(transition, Transition):
            raise TypeError("scene callbacks must return Transition or None")
        self.active.exit(self.context)
        self.active = transition.scene
        self.active.enter(self.context)
        self.history.append(transition)
