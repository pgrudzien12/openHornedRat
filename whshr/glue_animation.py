"""Deterministic 50 ms animation state for glue ``[BITMAP]`` records."""

from dataclasses import dataclass
import re


STEP_MILLISECONDS = 50


@dataclass(frozen=True)
class AnimationUpdate:
    bitmap: str
    redrawn: bool
    finished: bool = False


class GlueBitmapAnimator:
    """Advance one bitmap using the original descending-frame state machine."""

    def __init__(self, spec):
        self.base = spec["bitmap"]
        self.current = int(spec.get("animstartframe", -1))
        self.restart = int(spec.get("animrestartframe", self.current))
        self.stop = int(spec.get("animstopframe", self.current))
        self.period = int(spec.get("timecnt", 0))
        self.loop_delay = int(spec.get("looptimecnt", 0))
        self.delay = self.period
        self._millisecond_remainder = 0
        self._timer_remainder = 0
        self.drawn_name = self.base

    @property
    def finished(self):
        return self.current == self.stop

    def tick(self, milliseconds):
        """Apply one original-style animation step at most, returning its update."""
        if milliseconds < 0:
            raise ValueError("tick duration must not be negative")
        elapsed = self._millisecond_remainder + int(milliseconds)
        self._timer_remainder += elapsed // 25
        self._millisecond_remainder = elapsed % 25
        if self._timer_remainder < 2:
            return AnimationUpdate(self.drawn_name, False)
        self._timer_remainder &= 1  # Late timer messages do not catch up multiple frames.
        return self.step()

    def step(self):
        if self.current == self.stop:
            return AnimationUpdate(self.drawn_name, False, True)
        if self.delay > 0:
            self.delay -= 1
            return AnimationUpdate(self.drawn_name, False)
        if self.current != -1:
            self.drawn_name = re.sub(r"\d+$", "", self.base) + str(self.current)
        frame = self.drawn_name
        extra = 0
        if self.current >= 0:
            self.current -= 1
            if self.current < 0:
                if self.stop == -1:
                    self.current = self.restart
                    extra = self.loop_delay
                else:
                    self.current = -1
        self.delay = self.period + extra
        return AnimationUpdate(frame, True)
