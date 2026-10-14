"""The battle camera shake (notes/camera_shake.md): a fixed, stepped list of vertical eye offsets, one per tick.

Presentation only: starting or reading a shake never touches the simulation or the battle's random stream.
Triggers (section 5): Da Krunch and Conflagration of Doom (strong), a Giant's death blast (medium).
Not modelled: the Wyvern's and Gyrocopter's in-air crash (medium), since the engine has no crash blast for them yet.
"""

from dataclasses import dataclass

# notes/camera_shake.md 6: the offsets shown from the tick after the trigger, in mesh units (scene +Y, up).
STRONG: tuple[float, ...] = (-1.0, 1.0, -1.0, 1.0, -1.0, 0.8, -0.8, 0.8, -0.8, 0.6, -0.6, 0.4, -0.4, 0.2, -0.2)
MEDIUM: tuple[float, ...] = (-0.6, 0.6, -0.6, 0.6, -0.6, 0.4, -0.4, 0.4, -0.4, 0.2, -0.2)


@dataclass(frozen=True)
class Shake:
    first_tick: int  # the first tick whose view shows the list's first offset (trigger tick + 1)
    offsets: tuple[float, ...]

    def offset(self, tick: int) -> float:
        index = tick - self.first_tick
        return self.offsets[index] if 0 <= index < len(self.offsets) else 0.0


@dataclass
class CameraShake:
    """The running shake. A new trigger restarts the list with its own strength (section 4); the view of the
    trigger tick itself still shows the shake that was running before it."""

    current: Shake | None = None
    previous: Shake | None = None

    def start(self, trigger_tick: int, offsets: tuple[float, ...]) -> None:
        if self.current is not None and self.current.first_tick == trigger_tick + 1:
            self.current = Shake(trigger_tick + 1, offsets)  # two triggers on one tick: the later strength
            return
        self.previous, self.current = self.current, Shake(trigger_tick + 1, offsets)

    def offset(self, tick: int) -> float:
        """The eye's vertical offset (mesh units) in the view of `tick`."""
        if self.current is not None and tick >= self.current.first_tick:
            return self.current.offset(tick)
        return self.previous.offset(tick) if self.previous is not None else 0.0
