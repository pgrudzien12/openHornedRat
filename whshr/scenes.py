# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""Presentation-independent scene lifecycle and transition coordination."""

from abc import ABC
from collections.abc import Hashable
from dataclasses import dataclass, field
from os import PathLike
from typing import TYPE_CHECKING, Any

from .assets import AssetId
from .cache import AssetCache, Loader
from .catalog import AssetCatalog
from .assets import AssetLocator
from .glue_content import GlueContent

if TYPE_CHECKING:
    from .campaign_log import CampaignLogger

SceneEvent = Any  # a presentation event: an intent tuple such as ("select", id), a GlueInput or an ActivityResult


@dataclass(frozen=True)
class SceneManifest:
    """Assets a scene needs now and assets safe to prefetch for its likely successor."""

    immediate: tuple[AssetId, ...] = ()
    prefetch: tuple[AssetId, ...] = ()

    def __post_init__(self) -> None:
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

    locator: AssetLocator
    catalog: AssetCatalog
    cache: AssetCache
    loaders: dict[str, Loader]
    glue: GlueContent | None = None
    # The engine's own save directory (never the original installation's SAVE/, GEI7e).
    save_dir: str | PathLike[str] | None = None
    # No-battle mode: BattleScene settles every battle it enters as an immediate, lossless win
    # instead of simulating it, so the campaign can be walked through quickly.
    no_battle: bool = False
    # Optional whshr.campaign_log.CampaignLogger; observation only, never changes behaviour.
    campaign_log: "CampaignLogger | None" = None

    def _record_failure(self, identifier: AssetId | str, error: BaseException) -> None:
        log = self.campaign_log
        if log is not None:
            try:
                log.asset_failed(identifier, error)
            except Exception:
                pass

    def load(self, identifier: AssetId | str) -> Any:
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

    def acquire(self, identifier: AssetId | str, owner: Hashable) -> Any:
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

    def release_owner(self, owner: Hashable) -> None:
        self.cache.release_owner(owner)

    def glue_content(self) -> GlueContent:
        """Return the one shared, lazily indexed campaign-content repository."""
        if self.glue is None:
            from .glue_content import GlueContent
            self.glue = GlueContent(self.locator.installation)
        return self.glue


class Scene(ABC):
    """A game state with declarative asset needs and optional event/tick transitions."""

    manifest = SceneManifest()

    def enter(self, context: SceneAssets) -> None:
        """Initialize scene state after it becomes active."""

    def exit(self, context: SceneAssets) -> None:
        """Release scene state before another scene becomes active."""

    def handle(self, event: SceneEvent, context: SceneAssets) -> "Transition | Quit | None":
        """Handle one presentation event and optionally request a Transition or Quit."""
        return None

    def update(self, seconds: float, context: SceneAssets) -> "Transition | Quit | None":
        """Advance deterministic scene time and optionally request a Transition or Quit."""
        if seconds < 0:
            raise ValueError("scene update duration must not be negative")
        return None


@dataclass
class SceneMachine:
    """Owns exactly one active scene and applies transitions in lifecycle order."""

    initial: Scene
    context: Any = None  # the SceneAssets the scenes share (focused tests pass a lighter stand-in)
    active: Scene = field(init=False)
    history: list[Transition] = field(default_factory=list, init=False)
    quit: Quit | None = field(default=None, init=False)

    def __post_init__(self):
        self.active = self.initial
        self._log("scene_change", None, self.active, "initial scene")
        self.active.enter(self.context)
        self._log("entered", None, self.active, "")
        self._start_glue_activities()

    def _log(self, kind: str, old: Scene | None, new: Scene | None, reason: str) -> None:
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

    def handle(self, event: SceneEvent) -> None:
        """Give an event to the active scene and apply its transition or quit, if any."""
        if self.quit is None:
            self._apply(self.active.handle(event, self.context))
            self._start_glue_activities()
            self._fall_back_to_map()

    def update(self, seconds: float) -> None:
        """Give fixed or measured time to the active scene and apply its transition or quit, if any."""
        if seconds < 0:
            raise ValueError("scene update duration must not be negative")
        if self.quit is None:
            self._apply(self.active.update(seconds, self.context))
            self._start_glue_activities()
            self._fall_back_to_map()

    def _fall_back_to_map(self) -> None:
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

    def _start_glue_activities(self) -> None:
        self._start_glue_debrief()
        self._start_glue_battle()
        self._start_glue_movie()
        self._start_glue_caravan()

    def _start_glue_debrief(self) -> None:
        """A debrief request has no screen yet: it completes at once, applying what the engine can
        (notes/activity_results.md section 5), and the script goes on."""
        from .glue_scene import GlueScene

        while isinstance(self.active, GlueScene):
            effect = self.active.take_debrief_effect()
            if effect is None:
                return
            self.active.resolve_debrief(effect)

    def _start_glue_caravan(self) -> None:
        """A caravan request whose window the installation lacks resolves at once, as the mission's
        release step (notes/activity_results.md section 6.2); with a window the scene shows it and the
        player's exit hotspot resolves the request."""
        from .glue_runtime import ActivityResult
        from .glue_scene import GlueScene

        if not isinstance(self.active, GlueScene):
            return
        scene = self.active
        effect = scene.take_windowless_caravan_effect()
        if effect is None:
            return
        scene.complete_activity(ActivityResult(effect.request_id, "caravan"))
        parent = scene.release_mission() if effect.mode in ("select", "resume") else None
        if parent is not None:
            self._apply(Transition(parent, "mission released"))

    def _start_glue_battle(self) -> None:
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

    def _start_glue_movie(self) -> None:
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

    def _apply(self, transition: "Transition | Quit | None") -> None:
        if transition is None:
            return
        if isinstance(transition, Quit):
            self.quit = transition
            self._log("quit", self.active, None, transition.reason)
            return
        if not isinstance(transition, Transition):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("scene callbacks must return Transition, Quit or None")
        previous = self.active
        self._log("scene_change", previous, transition.scene, transition.reason)
        previous.exit(self.context)
        self.active = transition.scene
        self.active.enter(self.context)
        self.history.append(transition)
        self._log("entered", None, self.active, "")
