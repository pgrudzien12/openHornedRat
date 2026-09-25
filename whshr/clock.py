"""Deterministic fixed-step clock: turns variable frame times into whole simulation steps."""

NANOSECONDS = 1_000_000_000


class FixedStepClock:
    """Accumulates elapsed time and releases it as fixed steps, independent of the frame rate.

    Time is kept in integer nanoseconds so that, for example, three 0.1 s frames always give exactly
    three 0.1 s steps. A long stall (loading, a debugger) releases at most ``max_steps`` steps; the rest
    of the backlog is dropped instead of making the following frames even slower.
    """

    def __init__(self, step: float, max_steps: int = 25) -> None:
        if step <= 0:
            raise ValueError("clock step must be positive")
        if max_steps < 1:
            raise ValueError("clock must allow at least one step per advance")
        self._step = round(step * NANOSECONDS)
        if self._step == 0:
            raise ValueError("clock step must be at least one nanosecond")
        self.max_steps = max_steps
        self._accumulated = 0
        self.ticks = 0
        self.dropped_steps = 0

    @property
    def step(self) -> float:
        """The fixed step duration in seconds."""
        return self._step / NANOSECONDS

    @property
    def alpha(self) -> float:
        """Fraction of the next step already accumulated, for render interpolation."""
        return self._accumulated / self._step

    def advance(self, seconds: float) -> int:
        """Add elapsed time and return how many fixed steps to run now."""
        if seconds < 0:
            raise ValueError("elapsed time must not be negative")
        self._accumulated += round(seconds * NANOSECONDS)
        steps, self._accumulated = divmod(self._accumulated, self._step)
        if steps > self.max_steps:
            self.dropped_steps += steps - self.max_steps
            steps = self.max_steps
        self.ticks += steps
        return steps
